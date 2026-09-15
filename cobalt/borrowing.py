"""Managed scalar/struct places, CFG liveness, capabilities and lifetimes.

Capabilities are non-owning. Their live intervals follow uses of pointer values
and bindings, including expanded deferred bodies, rather than lexical scope.
"""
from .dataflow import Cell, Fact, snapshot
from .semantic import is_pointer, pointee


def liveness(fn):
    """Backwards may-use analysis of the acyclic CFG, with assignment kills."""
    blocks = {b['id']: b for b in fn['blocks']}
    entry, before, after = {}, {}, {}
    def visit(bid):
        if bid in entry: return entry[bid]
        b = blocks[bid]
        live = set(b['terminator'].get('operands', []))
        for dest in b['terminator'].get('targets', []): live.update(visit(dest))
        for op in reversed(b['operations']):
            after[op['id']] = set(live)
            live.difference_update(op['results'])
            args, kind = op['operands'], op['kind']
            if kind in ('alloca', 'parameter', 'init', 'assign'):
                live.discard(args[0]); live.update(args[1:])
            elif kind not in ('destroy', 'lifetime_end', 'defer_register', 'defer_execute'):
                live.update(args)
            before[op['id']] = set(live)
        entry[bid] = live
        return live
    for bid in blocks: visit(bid)
    return before, after


class BorrowAnalysis:
    def __init__(self, analyzer, fn):
        self.a, self.fn, self.lowerer = analyzer, fn, analyzer.lowerer
        self.before_live, self.after_live = liveness(fn)
        self.caps = {}
        self.places = {p['id']: p for p in fn['places']}
        self.external = {}
        self.parameter_referents = {}
        self.enabled = any(is_pointer(analyzer.type_names[p['type']]) for p in fn['places'] + fn['values']) or any(
            op['kind'] in ('borrow_shared', 'borrow_mut', 'reborrow') for b in fn['blocks'] for op in b['operations'])
        # An input pointer's referent is caller-owned storage, distinct from the
        # local parameter binding. It is never a local destruction obligation.
        for b in fn['blocks']:
            for op in b['operations']:
                if op['kind'] != 'parameter': continue
                p = self.places[op['operands'][0]]
                typ = analyzer.type_names[p['type']]
                if not is_pointer(typ): continue
                pid, lid = self.lowerer.ids.new('place'), self.lowerer.ids.new('life')
                ref = dict(id=pid, type=self.lowerer.type_id(pointee(typ)), ownership='Unowned', initialization='Initialized',
                           mutability='Mutable' if typ.startswith('mut ') else 'Immutable', lifetime=lid,
                           parent=None, field_path=[], object_identity=None, source_span=op['source_span'])
                fn['places'].append(ref); self.places[pid] = ref
                fn['lifetimes'].append(dict(id=lid, referent=pid, status='Live', lower_bound='caller',
                                           upper_bound='caller', source_span=op['source_span']))
                self.external[pid] = (op['attributes']['parameter_index'], ())
                self.parameter_referents[p['id']] = pid
                def children(ref, target_type, path=()):
                    pid, lid = ref['id'], ref['lifetime']
                    if target_type not in self.lowerer.structs: return
                    self.lowerer.components[pid] = {}
                    for name, field_type in self.lowerer.structs[target_type].items():
                        fid, flife = self.lowerer.ids.new('place'), self.lowerer.ids.new('life')
                        child = dict(ref, id=fid, type=self.lowerer.type_id(field_type), parent=pid,
                                     field_path=list(path)+[name], lifetime=flife)
                        fn['places'].append(child); self.places[fid] = child
                        self.lowerer.components[pid][name] = child
                        fn['lifetimes'].append(dict(id=flife, referent=fid, parent=lid, status='Live',
                            lower_bound='caller', upper_bound=lid, source_span=op['source_span']))
                        self.external[fid] = (op['attributes']['parameter_index'], path+(name,))
                        children(child, field_type, path+(name,))
                children(ref, pointee(typ))

    def error(self, op, code, message, rules, entities=()):
        self.a.error(op, code, message, 'P10' if code == 'lifetime_violation' else 'P9', rules, entities)
        return False

    def active(self, live, state, facts):
        ids = set()
        for ref in live:
            item = state.get(ref) if ref in state else facts.get(ref)
            if item: ids.update(item.capabilities)
        todo = list(ids)
        while todo:
            parent = self.caps[todo.pop()].get('derived_from')
            if parent and parent not in ids: ids.add(parent); todo.append(parent)
        return ids

    def ancestors(self, cid):
        result = set()
        while cid:
            result.add(cid); cid = self.caps[cid].get('derived_from')
        return result

    def statuses(self, active):
        suspended = {p for cid in active for p in self.ancestors(cid) - {cid}
                     if self.caps[p]['access'] == 'MutableExclusive'}
        return {cid: 'Suspended' if cid in suspended else 'Active' for cid in sorted(active)}

    def conflict(self, referent, write, via=None):
        ancestors = self.ancestors(via) if via else set()
        conflicts = []
        for cid in sorted(self.live_caps):
            if cid in ancestors: continue
            other = self.caps[cid]['referent']
            overlap = self.overlaps(referent, other)
            conflicting = overlap and (write or self.caps[cid]['access'] == 'MutableExclusive')
            if self.places[referent].get('parent') or self.places[other].get('parent'):
                evidence = dict(place=referent, capability=cid, referent=other, overlap=overlap, conflicting=conflicting)
                checks = self.current_op['attributes'].setdefault('overlap_checks', [])
                if evidence not in checks: checks.append(evidence)
                array_element = any(part.startswith('[') for pid in (referent,other) for part in self.places[pid].get('field_path', []))
                rule = ('BORROW-063' if array_element else 'BORROW-031') if overlap else ('CONTROL_FLOW-010' if array_element else 'BORROW-030')
                if rule not in self.current_op['rule_refs']: self.current_op['rule_refs'].append(rule)
                if not overlap:
                    fact = f'disjoint({referent},{other})'
                    if fact not in self.current_op['facts_established']: self.current_op['facts_established'].append(fact)
            if conflicting: conflicts.append(cid)
        return conflicts

    def overlaps(self, first, second):
        """Equal storage and ancestor/descendant places overlap; siblings do not.

        The supported places are scalar storage and scalar-field struct roots/fields.
        Array indexing, unions, and unknown projection paths are not admitted.
        """
        def lineage(pid):
            result = set()
            while pid:
                result.add(pid); pid = self.places[pid].get('parent')
            return result
        return first in lineage(second) or second in lineage(first)

    def before(self, op, state, facts):
        self.current_op = op
        if not self.enabled:
            self.live_caps = set()
            return True
        self.saved_state = dict(state)
        self.live_caps = self.active(self.before_live[op['id']], state, facts)
        op['attributes']['capability_state_before'] = self.statuses(self.live_caps)
        args, kind = op['operands'], op['kind']
        if kind not in ('read', 'copy', 'move', 'assign', 'destroy', 'struct_storage_end', 'temporary_end') or not args or args[0] not in self.places: return True
        pid = args[0]
        # Reading/moving the pointer binding does not access its referent.
        if is_pointer(self.a.type_names[self.places[pid]['type']]): return True
        if kind == 'destroy' and state.get(pid, Cell()).states == frozenset({'Uninitialized'}): return True
        conflicts = self.conflict(pid, kind in ('move', 'assign', 'destroy', 'struct_storage_end', 'temporary_end'))
        if conflicts:
            code = 'lifetime_violation' if kind in ('destroy', 'struct_storage_end', 'temporary_end') else 'borrow_conflict'
            return self.error(op, code, 'Operation would invalidate or conflict with a live borrow.',
                              ['BORROW-001','BORROW-005','BORROW-006'], [pid, *conflicts])
        return True

    def create(self, op, referent, access, parent=None):
        for rule in ('STATIC-LIFE-001', 'BORROW-068', 'BORROW-069'):
            if rule not in op['rule_refs']: op['rule_refs'].append(rule)
        cid, lid = self.lowerer.ids.new('cap'), self.lowerer.ids.new('life')
        life = dict(id=lid, referent=referent, status='Live', parent=self.caps[parent]['lifetime'] if parent else self.places[referent]['lifetime'],
                    lower_bound=op['id'], upper_bound='last_required_use', source_span=op['source_span'])
        cap = dict(id=cid, referent=referent, access=access, lifetime=lid, status='Active',
                   origin=op['id'], derived_from=parent, source_span=op['source_span'])
        self.fn['lifetimes'].append(life); self.fn['capabilities'].append(cap); self.caps[cid] = cap
        op['attributes'].setdefault('created_capabilities', []).append(cid)
        op['effects'].setdefault('borrows', []).append(f'create({cid},{referent},{access})')
        op['effects'].setdefault('lifetimes', []).append(f'contained_in({lid},{life["parent"]})')
        if parent and self.caps[parent]['referent'] != referent:
            op['effects']['lifetimes'].append(f'contained_in({lid},{self.places[referent]["lifetime"]})')
        op['facts_established'].append(f'active({cid})')
        return cid

    def access(self, op, pointer, state, write=False, borrowing=False, allow_uninitialized=False):
        if not pointer.valid or not pointer.capabilities: return False
        valid = True
        for cid in sorted(pointer.capabilities):
            cap = self.caps[cid]; ref = cap['referent']
            if not allow_uninitialized and state.get(ref, Cell()).states != frozenset({'Initialized'}):
                valid = self.error(op, 'lifetime_violation', 'Managed referent is no longer initialized and live.', ['BORROW-006','BORROW-064'], [cid, ref])
            if write and cap['access'] != 'MutableExclusive':
                valid = self.error(op, 'borrow_conflict', 'Shared capability does not permit mutable access.', ['BORROW-009'], [cid])
            conflicts = self.conflict(ref, write, cid)
            if conflicts:
                valid = self.error(op, 'borrow_conflict', 'Access conflicts with another live capability.', ['BORROW-014','BORROW-027'], [cid, *conflicts])
        return valid

    def operation(self, op, state, facts, typ):
        args, kind, attrs = op['operands'], op['kind'], op['attributes']
        if kind in ('array_bounds','array_read','array_assign','array_borrow','array_move'):
            from .arrays import operation
            return operation(self, op, state, facts)
        if kind == 'parameter' and args[0] in self.parameter_referents:
            ref = self.parameter_referents[args[0]]
            state[ref] = Cell(frozenset({'Initialized'}))
            for child in self.lowerer.component_paths(ref).values():
                state[child['id']] = Cell(frozenset({'Initialized'}))
            access = 'MutableExclusive' if self.places[ref]['mutability'] == 'Mutable' else 'SharedRead'
            cid = self.create(op, ref, access)
            state[args[0]] = Cell(frozenset({'Initialized'}), capabilities=frozenset({cid}))
            op['effects']['initialization'] = [f'initialize({args[0]})']
            return Fact(True)
        if kind in ('borrow_shared', 'borrow_mut'):
            ref = args[0]; write = attrs['access'] == 'MutableExclusive'
            valid = state.get(ref, Cell()).states == frozenset({'Initialized'})
            if not valid:
                self.error(op, 'invalid_borrow', 'Cannot borrow uninitialized, moved, or consumed storage.', ['BORROW-064'], [ref])
            if write and self.places[ref]['mutability'] != 'Mutable':
                valid = self.error(op, 'borrow_conflict', 'Mutable borrow requires mutable storage.', ['BORROW-015'], [ref])
            conflicts = self.conflict(ref, write)
            if conflicts:
                valid = self.error(op, 'borrow_conflict', 'Borrow conflicts with a live capability.', ['BORROW-004','BORROW-010'], [ref, *conflicts])
            return Fact(valid, capabilities=frozenset({self.create(op, ref, attrs['access'])}) if valid else frozenset())
        if kind == 'indexed_field_borrow':
            from .arrays import projected_borrow
            return projected_borrow(self, op, state, facts)
        if kind == 'field_borrow':
            pointer = facts.get(args[0], Fact(False))
            write = attrs['access'] == 'MutableExclusive'
            valid = pointer.valid and bool(pointer.capabilities)
            projected = []
            for cid in sorted(pointer.capabilities):
                cap = self.caps[cid]
                child = self.lowerer.component_paths(cap['referent']).get(attrs['field'])
                if child is None:
                    valid = False
                    continue
                ref = child['id']
                if state.get(ref, Cell()).states != frozenset({'Initialized'}):
                    moved=bool(state.get(ref,Cell()).states & {'Moved','PartiallyMoved'})
                    if not (write and attrs.get('allow_moved_for_assignment') and moved):
                        valid = self.error(op, 'invalid_borrow', 'Projected field is not initialized and available.', ['BORROW-064'], [ref])
                if write and cap['access'] != 'MutableExclusive':
                    valid = self.error(op, 'borrow_conflict', 'Shared struct capability does not permit mutable field access.', ['BORROW-009'], [cid])
                conflicts = self.conflict(ref, write, cid)
                if conflicts:
                    valid = self.error(op, 'borrow_conflict', 'Projected field conflicts with a live capability.', ['BORROW-031'], [ref, *conflicts])
                projected.append((cid, ref))
            attrs['projected_places'] = sorted({ref for _, ref in projected})
            ids = {self.create(op, ref, attrs['access'], cid) for cid, ref in projected} if valid else set()
            return Fact(valid, capabilities=frozenset(ids))
        if kind == 'reborrow':
            pointer = facts.get(args[0], Fact(False)); write = attrs['access'] == 'MutableExclusive'
            valid = self.access(op, pointer, state, write, True)
            ids = {self.create(op, self.caps[cid]['referent'], attrs['access'], cid) for cid in sorted(pointer.capabilities)} if valid else set()
            return Fact(valid, capabilities=frozenset(ids))
        if kind in ('deref_read', 'deref_assign', 'deref_move'):
            pointer = facts.get(args[0], Fact(False))
            valid = self.access(op, pointer, state, kind in ('deref_assign','deref_move'),
                                allow_uninitialized=kind=='deref_assign')
            refs = sorted({self.caps[cid]['referent'] for cid in pointer.capabilities})
            if refs and all(ref in self.structs.children for ref in refs):
                return self.structs.dereference(op, refs, state, facts, valid)
            if kind == 'deref_assign':
                rhs = facts.get(args[1], Fact(False)); valid = valid and rhs.valid and attrs['type_valid']
                if valid:
                    for ref in refs:
                        # If the pointer may select several referents, each may
                        # retain its old value. Do not invent a definite constant.
                        state[ref] = Cell(frozenset({'Initialized'}), rhs.constant if len(refs) == 1 else None,
                                          rhs.objects if len(refs) == 1 else state[ref].objects | rhs.objects)
                    op['effects']['initialization'] = [f'write_through({args[0]},{ref})' for ref in refs]
                return Fact(valid)
            if kind=='deref_move':
                cells=[state.get(ref,Cell()) for ref in refs]
                op['attributes']['referent_states_before']={ref:snapshot(cell) for ref,cell in zip(refs,cells)}
                for ref,cell in zip(refs,cells):
                    if cell.states != frozenset({'Initialized'}):
                        code='use_after_move' if cell.states & {'Moved','PartiallyMoved'} else 'uninitialized_read'
                        self.a.error(op,code,'Moving through a managed pointer requires an initialized, available referent.','P8',['OWNERSHIP-005'],[ref])
                        valid=False
                if valid:
                    definite=len(refs)==1
                    constant=cells[0].constant if cells and all(c.constant==cells[0].constant for c in cells) else None
                    objects=frozenset().union(*(cell.objects for cell in cells))
                    op['attributes'].update(result_ownership='Owned',referents=refs,
                        target_selection='definite' if definite else 'one_of_referents',
                        result_identity_selection='selected_referent')
                    op['effects']['ownership']=[f'transfer_from_referent_if_selected({args[0]},{ref},{op["results"][0]})' for ref in refs]
                    op['effects']['initialization']=[f'move_referent_if_selected({ref})' for ref in refs]
                    op['facts_invalidated']=[f'initialized({ref})' for ref in refs]
                    for ref,cell in zip(refs,cells):
                        state[ref]=Cell(frozenset({'Moved'}) if definite else cell.states | {'Moved'},objects=cell.objects)
                    op['attributes']['referent_states_after']={ref:snapshot(state[ref]) for ref in refs}
                    return Fact(True,constant,objects)
                op['attributes']['referent_states_after']={ref:snapshot(state.get(ref,Cell())) for ref in refs}
                return Fact(False)
            cells = [state.get(ref, Cell()) for ref in refs]
            constant = cells[0].constant if cells and all(c.constant == cells[0].constant for c in cells) else None
            if valid: op['effects']['borrows'] = [f'read_through({args[0]},{ref})' for ref in refs]
            return Fact(valid, constant, frozenset({f'object_{op["id"]}'}))
        return None

    def after(self, op, state, facts, fact, valid, typ):
        if not self.enabled: return fact, valid
        kind, args = op['kind'], op['operands']
        if kind in ('read', 'copy', 'move') and is_pointer(typ):
            # Loading a pointer checks that its capability is still live, but
            # initialization is checked by the later dereference operation.
            # This also lets a mutable pointer reinitialize a moved referent.
            if not (kind == 'read' and pointee(typ) in self.lowerer.structs):
                valid = valid and self.access(op, fact, state, allow_uninitialized=True)
            if kind == 'copy' and valid:
                ids = {self.create(op, self.caps[cid]['referent'], 'SharedRead', cid) for cid in sorted(fact.capabilities)}
                fact = Fact(True, capabilities=frozenset(ids))
            op['effects'].pop('ownership', None)
            op['attributes']['result_ownership'] = 'Unowned'
            if valid: op['effects'].setdefault('borrows', []).append(f'{kind}_capability({args[0]})')
        elif kind in ('init', 'assign', 'destroy') and args and is_pointer(self.a.type_names[self.places[args[0]]['type']]):
            op['effects'].pop('ownership', None); op['effects'].pop('destruction', None)
            op['facts_established'] = [f for f in op['facts_established'] if not f.startswith('owns(')]
            op['facts_invalidated'] = [f for f in op['facts_invalidated'] if not f.startswith('owns(')]
            if kind=='assign' and valid:
                previous=self.saved_state.get(args[0],Cell()).capabilities
                current=state.get(args[0],Cell()).capabilities
                op['attributes'].update(binding_mutability=self.places[args[0]]['mutability'],
                    pointer_capabilities_before=sorted(previous),pointer_capabilities_after=sorted(current))
                op['effects'].setdefault('borrows',[]).append(
                    f'rebind_pointer_binding({args[0]},{",".join(sorted(previous))},{",".join(sorted(current))})')
            if kind == 'destroy': op['attributes']['executes_if_initialized'] = False
        elif kind == 'call':
            pointer_args = [(i, facts.get(arg, Fact(False))) for i, arg in enumerate(args[1:]) if facts.get(arg, Fact(False)).capabilities]
            for _, pointer in pointer_args:
                write = any(self.caps[c]['access'] == 'MutableExclusive' for c in pointer.capabilities)
                valid = self.access(op, pointer, state, write) and valid
            if valid:
                for _, pointer in pointer_args:
                    for cid in sorted(pointer.capabilities):
                        cap = self.caps[cid]
                        if cap['access'] == 'MutableExclusive':
                            ref = cap['referent']; old = state[ref]
                            state[ref] = Cell(old.states, None, old.objects, old.capabilities)
                            for child in self.lowerer.component_paths(ref).values():
                                field = child['id']; previous = state[field]
                                state[field] = Cell(previous.states, None, previous.objects, previous.capabilities)
            if is_pointer(typ):
                summary = self.a.return_borrows.get(op['attributes']['function'])
                if summary is None or op['attributes']['function'] in self.a.analysis_stack:
                    self.error(op, 'unsupported_borrow_return', 'Returned borrow requires an analyzed, non-recursive input-lifetime relationship.', ['LIFETIME-007']); valid = False
                else:
                    ids = set()
                    for index, path in sorted(summary):
                        if index >= len(args)-1: valid = False; continue
                        for cid in sorted(facts.get(args[index+1], Fact(False)).capabilities):
                            ref = self.caps[cid]['referent']
                            for name in path:
                                ref = self.lowerer.components[ref][name]['id']
                            if path or (not typ.startswith('mut ') and self.caps[cid]['access'] == 'MutableExclusive'):
                                ids.add(self.create(op, ref, 'MutableExclusive' if typ.startswith('mut ') else 'SharedRead', cid))
                            else: ids.add(cid)
                    fact = Fact(valid and bool(ids), capabilities=frozenset(ids))
                    valid = valid and fact.valid
            if pointer_args:
                op['effects']['ownership'] = [f'by_value_argument({arg})' for arg in args[1:] if not facts.get(arg, Fact(False)).capabilities]
                op['effects']['borrows'] = [f'call_requires({cid})' for _, p in pointer_args for cid in sorted(p.capabilities)]
        elif kind == 'return_prepare' and args:
            pointer = facts.get(args[0], Fact(False))
            for field_path, field in pointer.fields:
                for cid in sorted(field.capabilities):
                    ref = self.caps[cid]['referent']
                    if ref not in self.external:
                        valid = self.error(op, 'lifetime_violation',
                                           'Cannot return a struct containing a managed pointer to local storage.',
                                           ['BORROW-018','BORROW-079'], [cid, ref])
            if pointer.capabilities:
                indices = set()
                for cid in sorted(pointer.capabilities):
                    ref = self.caps[cid]['referent']
                    if ref not in self.external:
                        valid = self.error(op, 'lifetime_violation', 'Cannot return a managed pointer to local storage.', ['BORROW-018','BORROW-079'], [cid, ref])
                    else: indices.add(self.external[ref])
                if valid:
                    self.a.return_borrows.setdefault(self.fn['id'], set()).update(indices)
                    op['effects'] = {'borrows': [f'return_capability({cid}) constrained_by_input' for cid in sorted(pointer.capabilities)]}
        elif kind == 'discard' and args and facts.get(args[0], Fact(False)).capabilities:
            op['effects'] = {'borrows': [f'discard_pointer({args[0]})']}
        if not valid:
            state.clear(); state.update(self.saved_state)
            op['effects'] = {}; op['facts_established'] = []; op['facts_invalidated'] = []
        return fact, valid

    def finish(self, op, state, facts):
        if not self.enabled: return
        active = self.active(self.after_live[op['id']], state, facts)
        created = set(op['attributes'].get('created_capabilities', []))
        ended = (self.live_caps | created) - active
        op['attributes']['capability_state_after'] = self.statuses(active)
        if op['attributes']['validation'] != 'valid': return
        for check in op['attributes'].get('overlap_checks', []):
            if not check['overlap']:
                fact = f'disjoint({check["place"]},{check["referent"]})'
                if fact not in op['facts_established']: op['facts_established'].append(fact)
        before_status = op['attributes'].get('capability_state_before', {})
        for cid, status in op['attributes']['capability_state_after'].items():
            previous = before_status.get(cid)
            if status == 'Suspended' and previous != 'Suspended':
                op['effects'].setdefault('borrows', []).append(f'suspend_capability({cid})')
                if 'BORROW-027' not in op['rule_refs']: op['rule_refs'].append('BORROW-027')
            elif status == 'Active' and previous == 'Suspended':
                op['effects'].setdefault('borrows', []).append(f'resume_capability({cid})')
                if 'BORROW-028' not in op['rule_refs']: op['rule_refs'].append('BORROW-028')
        if ended:
            if 'LIFETIME-003' not in op['rule_refs']: op['rule_refs'].append('LIFETIME-003')
            op['attributes']['ended_capabilities'] = sorted(ended)
            op['effects'].setdefault('borrows', []).extend(f'end_borrow({cid})' for cid in sorted(ended))
            op['effects'].setdefault('lifetimes', []).extend(f'end({self.caps[cid]["lifetime"]})' for cid in sorted(ended))
            op['facts_invalidated'].extend(f'active({cid})' for cid in sorted(ended))
        if op['results']:
            caps = facts.get(op['results'][0], Fact(False)).capabilities
            if len(caps) == 1:
                value = next(v for v in self.fn['values'] if v['id'] == op['results'][0])
                value['capability'] = next(iter(caps))
        if op['operands'] and op['operands'][0] in self.places:
            p = self.places[op['operands'][0]]
            if is_pointer(self.a.type_names[p['type']]):
                for key in ('state_before', 'state_after'):
                    if key in op['attributes']:
                        op['attributes'][key]['ownership'] = ['Unowned']

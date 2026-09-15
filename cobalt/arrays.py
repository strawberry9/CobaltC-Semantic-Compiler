"""Checked runtime access, borrowing and moves of scalar and struct array elements."""
from .dataflow import Cell, Fact, snapshot


def operation(borrows, op, state, facts):
    args, attrs, kind = op['operands'], op['attributes'], op['kind']
    analyzer = borrows.a
    if kind == 'array_bounds':
        index = facts.get(args[0], Fact(False))
        length = attrs['array_length']
        valid = index.valid
        known = index.constant
        minimum=index.minimum
        maximum=index.maximum
        if known is None and minimum is not None and minimum==maximum:known=minimum
        definitely_valid=(length>0 and known is not None and 0<=known<length)
        outside=(length==0 or (known is not None and not 0<=known<length)
                 or (maximum is not None and maximum<0)
                 or (minimum is not None and minimum>=length))
        if valid and outside:
            analyzer.error(op, 'index_out_of_bounds', 'Array index is provably outside its bounds.', 'P5', ['TYPE-036'])
            valid = False
        proven_in_range=(length>0 and minimum is not None and maximum is not None
                         and minimum>=0 and maximum<length)
        success_min=max(minimum,0) if minimum is not None else 0
        success_max=min(maximum,length-1) if maximum is not None and length else (length-1 if length else None)
        success_constant=known if definitely_valid else (success_min if success_min==success_max and length else None)
        attrs.update(failure_mode='abort', result_condition='operation_succeeded',
                     runtime_check=valid and not definitely_valid and not proven_in_range,
                     bounds_check='constant' if definitely_valid or proven_in_range else 'runtime')
        if minimum is not None or maximum is not None:
            attrs['index_range_before_bounds']=[minimum,maximum]
        if valid and (minimum is not None or maximum is not None):
            attrs['index_range_on_success']=[success_min,success_max]
        if valid:
            op['preconditions'] = [f'integer_index({args[0]})']
            op['postconditions'] = [f'0 <= {op["results"][0]} < {length} on success']
        return Fact(valid, success_constant if valid else known, index.objects,minimum=success_min if valid else minimum,
                    maximum=success_max if valid else maximum)

    root = args[0]
    index = facts.get(args[1], Fact(False))
    if not index.valid: return Fact(False)
    elements = list(borrows.lowerer.components[root].values())
    proofs=attrs.get('dimension_bounds_proofs')
    if not proofs:
        proofs=[args[1]]
        if attrs.get('inner_bounds_proof'): proofs.append(attrs['inner_bounds_proof'])
    candidates=elements
    index_facts=[]
    for dimension,proof in enumerate(proofs):
        current=facts.get(proof,Fact(False))
        if not current.valid: return Fact(False)
        index_facts.append(current)
        groups=[elements] if dimension==0 else [list(borrows.lowerer.components.get(candidate['id'],{}).values()) for candidate in candidates]
        selected=[]
        for children in groups:
            if current.constant is not None:
                if current.constant < len(children): selected.append(children[current.constant])
            elif current.minimum is not None or current.maximum is not None:
                first=max(current.minimum,0) if current.minimum is not None else 0
                last=min(current.maximum,len(children)-1) if current.maximum is not None else len(children)-1
                if first<=last:selected.extend(children[first:last+1])
            else: selected.extend(children)
        candidates=selected
        if dimension==attrs.get('projected_field_dimension',0) and attrs.get('projected_field'):
            candidates=[borrows.lowerer.component_paths(p['id'])[attrs['projected_field']] for p in candidates]
    ids=[p['id'] for p in candidates]
    selection=','.join(proofs)
    index=index_facts[0]
    attrs.update(possible_elements=ids,bounds_proof=proofs[0],
                 target_selection='definite' if len(ids)==1 else 'one_of_elements')
    attrs['element_states_before'] = {pid:snapshot(state.get(pid, Cell())) for pid in ids}
    valid = bool(ids)
    write = kind in ('array_assign','array_move') or (kind == 'array_borrow' and attrs['access']=='MutableExclusive')
    for pid in ids:
        conflicts = borrows.conflict(pid, write)
        if conflicts:
            valid = borrows.error(op, 'borrow_conflict', 'A possible indexed element conflicts with a live borrow.',
                                  ['BORROW-063','BORROW-042'], [pid,*conflicts])
        if kind != 'array_assign' and state.get(pid, Cell()).states != frozenset({'Initialized'}):
            moved = bool(state.get(pid, Cell()).states & {'Moved','PartiallyMoved'})
            analyzer.error(op, 'use_after_move' if moved else 'uninitialized_read',
                           'Every possible indexed element must be initialized and available.',
                           'P8' if moved else 'P7', ['OWNERSHIP-005'] if moved else ['INITIALIZATION-001'], [pid])
            valid = False
    aggregate = bool(ids) and ids[0] in borrows.structs.children
    if aggregate:
        attrs['element_field_states_before'] = {pid:borrows.structs.field_states(pid,state) for pid in ids}
    if aggregate and kind != 'array_borrow':
        result = aggregate_access(borrows,op,state,facts,ids,valid)
    elif kind == 'array_borrow':
        if write and borrows.places[root]['mutability'] != 'Mutable':
            valid = borrows.error(op, 'borrow_conflict', 'Mutable element borrowing requires a mutable array.', ['BORROW-015'], [root])
        capabilities = [borrows.create(op, pid, attrs['access']) for pid in ids] if valid else []
        if valid:
            attrs['capability_alternatives'] = capabilities
            attrs['result_ownership'] = 'Unowned'
            op['effects'].setdefault('borrows', []).append(f'borrow_selected_element({root},{selection})')
        result = Fact(valid, capabilities=frozenset(capabilities))
    elif kind == 'array_move':
        cells = [state.get(pid, Cell()) for pid in ids]
        constant = cells[0].constant if cells and all(c.constant==cells[0].constant for c in cells) else None
        objects = frozenset().union(*(c.objects for c in cells))
        if valid:
            attrs['result_ownership'] = 'Owned'
            attrs['result_identity_selection'] = 'selected_element'
            op['effects'] = {'ownership':[], 'initialization':[]}
            op['facts_invalidated'].extend([f'initialized({root})',f'owns({root})'])
            for pid in ids:
                old = state[pid]
                state[pid] = Cell(frozenset({'Moved'})) if len(ids)==1 else Cell(old.states | {'Moved'}, old.constant, old.objects)
                op['effects']['ownership'].append(f'transfer_selected_element({root},{selection},{pid},{op["results"][0]})')
                op['effects']['initialization'].append(f'moved_if_selected({selection},{pid})')
                op['facts_invalidated'].extend([f'initialized({pid})',f'owns({pid})'])
        result = Fact(valid, constant, objects)
    elif write:
        rhs = facts.get(args[attrs.get('value_operand',2)], Fact(False))
        valid = valid and rhs.valid and attrs['type_valid']
        if attrs['const_binding'] or borrows.places[root]['mutability'] != 'Mutable':
            analyzer.error(op, 'immutable_assignment', 'Indexed assignment requires a mutable array.', 'P5', ['TYPE-066'], [root])
            valid = False
        if valid:
            definite = len(ids)==1
            op['effects'] = {'initialization':[], 'ownership':[], 'destruction':[]}
            for pid in ids:
                old = state.get(pid, Cell())
                states = frozenset({'Initialized'}) if definite else old.states | {'Initialized'}
                constant = rhs.constant if definite or old.constant==rhs.constant else None
                objects = rhs.objects if definite else old.objects | rhs.objects
                state[pid] = Cell(states, constant, objects)
                op['effects']['initialization'].append(f'initialize_if_selected({selection},{pid})')
                op['effects']['ownership'].append(f'transfer_if_selected({args[attrs.get("value_operand",2)]},{pid})')
                if 'Initialized' in old.states:
                    op['effects']['destruction'].append(f'destroy_previous_if_selected_and_owned({selection},{pid}) after successful RHS evaluation')
            borrows.structs.refresh(state)
            if all(state[p['id']].states == frozenset({'Initialized'}) for p in elements):
                old_root=state.get(root, Cell())
                if not old_root.objects:
                    state[root]=Cell(old_root.states, objects=frozenset({f'object_{op["id"]}_aggregate'}))
                op['facts_established'].extend([f'initialized({root})',f'owns({root})'])
        result = Fact(valid)
    else:
        cells = [state.get(pid, Cell()) for pid in ids]
        constant = cells[0].constant if cells and all(c.constant==cells[0].constant for c in cells) else None
        if valid:
            op['effects']['ownership'] = [f'copy_selected_element({root},{selection},{op["results"][0]})']
            attrs['result_ownership'] = 'Owned'
        result = Fact(valid, constant, frozenset({f'object_{op["id"]}'}))
    if attrs.get('projected_field') and result.valid and kind in ('array_move','array_assign'):
        borrows.structs.refresh(state)
        ancestors=set()
        for pid in ids:
            parent=borrows.structs.parents.get(pid)
            while parent:
                ancestors.add(parent); parent=borrows.structs.parents.get(parent)
        for parent in sorted(ancestors):
            cell=state[parent]
            if kind=='array_assign' and cell.states==frozenset({'Initialized'}):
                if not cell.objects:
                    state[parent]=Cell(cell.states,objects=frozenset({f'object_{op["id"]}_aggregate_{parent}'}))
                op['facts_established'].extend([f'initialized({parent})',f'owns({parent})'])
            else:
                op['facts_invalidated'].extend([f'initialized({parent})',f'owns({parent})'])
    if aggregate:
        borrows.structs.refresh(state)
        attrs['element_field_states_after'] = {pid:borrows.structs.field_states(pid,state) for pid in ids}
    attrs['element_states_after'] = {pid:snapshot(state.get(pid, Cell())) for pid in ids}
    return result


def projected_borrow(borrows, op, state, facts):
    args, attrs = op['operands'], op['attributes']
    pointer = facts.get(args[0], Fact(False))
    proofs=attrs.get('dimension_bounds_proofs',[args[1]])
    indices=[facts.get(proof,Fact(False)) for proof in proofs]
    if not pointer.valid or not pointer.capabilities or not all(index.valid for index in indices): return Fact(False)
    write = attrs['access'] == 'MutableExclusive'
    lengths=attrs.get('dimension_lengths',[attrs['array_length']])
    projected = []
    valid = True
    for cid in sorted(pointer.capabilities):
        cap = borrows.caps[cid]
        paths = borrows.lowerer.component_paths(cap['referent'])
        selections=[()]
        for index,length in zip(indices,lengths):
            choices=[index.constant] if index.constant is not None else range(length)
            selections=[prefix+(number,) for prefix in selections for number in choices]
        for selection in selections:
            prefix=attrs.get('field','')
            suffix='.'.join(f'[{number}]' for number in selection)
            selected_path=(prefix+'.' if prefix and suffix else prefix)+suffix
            if attrs.get('field_suffix'): selected_path+='.'+attrs['field_suffix']
            child = paths.get(selected_path)
            if child is None:
                valid = False
                continue
            ref = child['id']
            if state.get(ref, Cell()).states != frozenset({'Initialized'}):
                moved=bool(state.get(ref,Cell()).states & {'Moved','PartiallyMoved'})
                if not (write and attrs.get('allow_moved_for_assignment') and moved):
                    valid = borrows.error(op,'invalid_borrow','Projected element is not initialized and available.',['BORROW-064'],[ref])
            if write and cap['access'] != 'MutableExclusive':
                valid = borrows.error(op,'borrow_conflict','Shared struct capability does not permit mutable element access.',['BORROW-009'],[cid])
            conflicts = borrows.conflict(ref, write, cid)
            if conflicts:
                valid = borrows.error(op,'borrow_conflict','Projected element conflicts with a live capability.',['BORROW-063','BORROW-031'],[ref,*conflicts])
            projected.append((cid,ref))
    refs = sorted({ref for _,ref in projected})
    attrs.update(projected_places=refs,possible_elements=refs,bounds_proof=proofs[0],
                 target_selection='definite' if len(refs)==1 else 'one_of_elements')
    if len(proofs)>1: attrs['dimension_candidate_paths']=[list(selection) for selection in selections]
    ids = [borrows.create(op,ref,attrs['access'],cid) for cid,ref in projected] if valid else []
    if valid:
        attrs.update(capability_alternatives=ids,result_ownership='Unowned')
    return Fact(valid,capabilities=frozenset(ids))


def aggregate_access(borrows, op, state, facts, ids, valid):
    """Transfer one struct selection, with per-descendant alternative states."""
    args, attrs, kind = op['operands'], op['attributes'], op['kind']
    root = args[0]
    selection = ','.join(attrs.get('dimension_bounds_proofs', [args[1]]))
    if not attrs.get('dimension_bounds_proofs') and attrs.get('inner_bounds_proof'):
        selection += ','+attrs['inner_bounds_proof']
    paths = borrows.structs.children
    definite = len(ids) == 1
    if kind == 'array_assign':
        rhs = facts.get(args[attrs.get('value_operand',2)], Fact(False))
        valid = valid and rhs.valid and attrs['type_valid']
        if attrs['const_binding'] or borrows.places[root]['mutability'] != 'Mutable':
            borrows.a.error(op,'immutable_assignment','Indexed assignment requires a mutable array.','P5',['TYPE-066'],[root])
            valid = False
        if not valid: return Fact(False)
        op['effects'] = {'initialization':[], 'ownership':[], 'destruction':[]}
        fields = dict(rhs.fields)
        for pid in ids:
            targets = [(pid,rhs)] + [(p['id'],fields[name]) for name,p in paths[pid].items()]
            for target,value in targets:
                old = state.get(target,Cell())
                state[target] = Cell(frozenset({'Initialized'}) if definite else old.states | {'Initialized'},
                                     value.constant if definite or old.constant==value.constant else None,
                                     value.objects if definite else old.objects | value.objects)
                op['effects']['initialization'].append(f'initialize_if_selected({selection},{target})')
                op['effects']['ownership'].append(f'transfer_struct_component_if_selected({args[attrs.get("value_operand",2)]},{pid},{target})')
                if target not in paths and 'Initialized' in old.states:
                    op['effects']['destruction'].append(f'destroy_previous_if_selected_and_owned({selection},{target}) after successful RHS evaluation')
        borrows.structs.refresh(state)
        if all(state[p['id']].states == frozenset({'Initialized'}) for p in borrows.lowerer.components[root].values()):
            old=state[root]
            if not old.objects: state[root]=Cell(old.states,objects=frozenset({f'object_{op["id"]}_aggregate'}))
            op['facts_established'].extend([f'initialized({root})',f'owns({root})'])
        return Fact(True)
    if not valid: return Fact(False)
    moving = kind == 'array_move'
    def value(cells, identity):
        constant = cells[0].constant if all(c.constant==cells[0].constant for c in cells) else None
        objects = frozenset().union(*(c.objects for c in cells)) if moving else frozenset({identity})
        return Fact(True,constant,objects)
    result = value([state[pid] for pid in ids],f'object_{op["id"]}')
    fields = tuple((name,value([state[paths[pid][name]['id']] for pid in ids],f'object_{op["id"]}_field_{i}'))
                   for i,name in enumerate(paths[ids[0]]))
    attrs.update(result_ownership='Owned',result_field_states=borrows.structs.value_field_states(fields))
    if moving:
        attrs['result_identity_selection']='selected_element'
        op['effects']={'ownership':[], 'initialization':[]}
        op['facts_invalidated'].extend([f'initialized({root})',f'owns({root})'])
        for pid in ids:
            for target in [pid,*(p['id'] for p in paths[pid].values())]:
                old=state[target]
                state[target]=Cell(frozenset({'Moved'})) if definite else Cell(old.states | {'Moved'},old.constant,old.objects)
                op['effects']['ownership'].append(f'transfer_selected_struct_component({root},{selection},{target},{op["results"][0]})')
                op['effects']['initialization'].append(f'moved_if_selected({selection},{target})')
                op['facts_invalidated'].extend([f'initialized({target})',f'owns({target})'])
    else:
        op['effects']['ownership']=[f'independent_selected_struct_copy({root},{selection},{op["results"][0]})']
    return Fact(True,result.constant,result.objects,fields=fields)

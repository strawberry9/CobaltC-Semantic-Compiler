"""Initialization and whole-value/component transfers of local scalar-field structs.

Field cells are authoritative at CFG joins. Root initialization is a summary,
never permission to read an uninitialized component.
"""
from .dataflow import Cell, Fact, snapshot


class StructAnalysis:
    def __init__(self, analyzer, fn):
        self.a = analyzer
        self.value_types = {v['id']: analyzer.type_names[v['type']] for v in fn['values']}
        self.functions = {f['id']: f for f in analyzer.lowerer.functions}
        self.place_types = {p['id']: analyzer.type_names[p['type']] for p in fn['places']}
        self.place_entities = {p['id']:p for p in fn['places']}
        places = {p['id'] for p in fn['places']}
        self.children = {pid: analyzer.lowerer.component_paths(pid) for pid in analyzer.lowerer.components if pid in places}
        self.parents = {p['id']: p['parent'] for p in fn['places'] if p.get('parent')}

    def root_for(self, op):
        first = next(iter(op['operands']), None)
        return first if first in self.children else self.parents.get(first)

    def summarize(self, root, state):
        fields = self.children[root]
        if not fields: return
        cells = [state.get(p['id'], Cell()) for p in fields.values()]
        if all(c.states == frozenset({'Initialized'}) for c in cells): status = 'Initialized'
        elif all(c.states == frozenset({'Moved'}) for c in cells): status = 'Moved'
        elif all(c.states == frozenset({'Uninitialized'}) for c in cells): status = 'Uninitialized'
        elif all(c.states == frozenset({'Consumed'}) for c in cells): status = 'Consumed'
        elif any(c.states & {'Moved','PartiallyMoved'} for c in cells): status = 'PartiallyMoved'
        else: status = 'PartiallyInitialized'
        old = state.get(root, Cell())
        state[root] = Cell(frozenset({status}), objects=old.objects)

    def field_states(self, root, state):
        return {name: snapshot(state.get(p['id'], Cell())) for name, p in self.children[root].items()}

    def refresh(self, state):
        for root in reversed(list(self.children)):
            if root in state: self.summarize(root, state)

    def before(self, op, state):
        self.refresh(state)
        root = self.root_for(op)
        if root is None: return
        self.summarize(root, state)
        op['attributes']['aggregate_place'] = root
        op['attributes']['aggregate_state_before'] = snapshot(state.get(root, Cell()))
        op['attributes']['field_states_before'] = self.field_states(root, state)
        ancestor = self.parents.get(root)
        while ancestor:
            op['attributes'].setdefault('ancestor_states_before', {})[ancestor] = snapshot(state.get(ancestor, Cell()))
            ancestor = self.parents.get(ancestor)

    def operation(self, op, state, facts):
        root = self.root_for(op)
        if op['kind'] in ('read', 'copy', 'move') and root is not None and op['operands'][0] == root:
            return self.transfer(op, root, state)
        if op['kind'] == 'parameter' and root in self.children:
            state[root] = Cell(frozenset({'Initialized'}), objects=frozenset({f'object_{op["id"]}'}))
            op['effects'] = {'initialization': [f'initialize({root})'], 'ownership': [f'receive_owned_argument({root})']}
            for index, (name, child) in enumerate(self.children[root].items()):
                pid = child['id']
                state[pid] = Cell(frozenset({'Initialized'}), objects=frozenset({f'object_{op["id"]}_field_{index}'}))
                op['effects']['initialization'].append(f'initialize_field({root},{pid})')
                op['effects']['ownership'].append(f'receive_argument_field({root},{name},{pid})')
            op['facts_established'] = [fact for pid in [root, *(p['id'] for p in self.children[root].values())]
                                       for fact in (f'initialized({pid})', f'owns({pid})')]
            return Fact(True)
        if op['kind'] == 'call' and self.value_types.get(op['results'][0]) in self.a.lowerer.structs:
            valid = all(facts.get(arg, Fact(False)).valid for arg in op['operands'][1:])
            fields = tuple((name, Fact(True, objects=frozenset({f'object_{op["id"]}_field_{index}'})))
                           for index, name in enumerate(self.a.lowerer.type_paths(self.value_types[op['results'][0]])))
            if valid:
                op['effects']['ownership'] = [f'by_value_argument({arg})' for arg in op['operands'][1:]]
                op['attributes']['result_ownership'] = 'Owned'
                op['attributes']['result_field_states'] = self.value_field_states(fields)
            return Fact(valid, objects=frozenset({f'object_{op["id"]}'}), fields=fields)
        if op['kind'] in ('array_extract', 'array_move_extract'):
            moving = op['kind'] == 'array_move_extract'
            source = facts.get(op['operands'][0], Fact(False))
            index = facts.get(op['operands'][1], Fact(False))
            if not source.valid or not index.valid: return Fact(False)
            fields = dict(source.fields)
            paths = [f'[{index.constant}]'] if index.constant is not None else [f'[{i}]' for i in range(op['attributes']['array_length'])]
            selected = [fields.get(path, Fact(False)) for path in paths]
            if not selected or not all(f.valid for f in selected): return Fact(False)
            constant = selected[0].constant if all(f.constant == selected[0].constant for f in selected) else None
            op['attributes'].update(result_ownership='Owned', possible_elements=paths,
                                    bounds_proof=op['operands'][1],
                                    target_selection='definite' if len(paths)==1 else 'one_of_elements')
            if moving:
                op['attributes']['result_identity_selection'] = 'selected_element'
                op['effects']['ownership'] = [f'transfer_temporary_element_if_selected({op["operands"][0]},{op["operands"][1]},{op["results"][0]})']
            else:
                op['effects']['ownership'] = [f'independent_temporary_element_copy({op["operands"][0]},{op["operands"][1]},{op["results"][0]})']
            result_fields = []
            result_type = self.value_types[op['results'][0]]
            for i,name in enumerate(self.a.lowerer.type_paths(result_type)):
                alternatives = [fields.get(path+'.'+name,Fact(False)) for path in paths]
                if not all(f.valid for f in alternatives): return Fact(False)
                known = alternatives[0].constant if all(f.constant==alternatives[0].constant for f in alternatives) else None
                objects = (frozenset().union(*(f.objects for f in alternatives)) if moving else
                           frozenset({f'object_{op["id"]}_field_{i}'}))
                result_fields.append((name,Fact(True,known,objects)))
            if result_type in self.a.lowerer.structs:
                op['attributes']['result_field_states'] = self.value_field_states(result_fields)
            result_objects = (frozenset().union(*(f.objects for f in selected)) if moving else
                              frozenset({f'object_{op["id"]}'}))
            return Fact(True, constant, result_objects, fields=tuple(result_fields))
        if op['kind'] in ('struct_extract', 'struct_move_extract'):
            moving = op['kind'] == 'struct_move_extract'
            source = facts.get(op['operands'][0], Fact(False))
            path = op['attributes']['field']
            selected = dict(source.fields).get(path, Fact(False))
            if not source.valid or not selected.valid: return Fact(False)
            fields = tuple((name[len(path)+1:], field if moving else Fact(True, field.constant,
                            frozenset({f'object_{op["id"]}_field_{index}'})))
                           for index, (name, field) in enumerate(source.fields) if name.startswith(path+'.'))
            op['attributes']['result_ownership'] = 'Owned'
            if moving: op['attributes']['result_identity_selection'] = 'selected_subtree'
            if self.value_types[op['results'][0]] in self.a.lowerer.structs:
                op['attributes']['result_field_states'] = self.value_field_states(fields)
            op['effects']['ownership'] = ([f'transfer_temporary_field({op["operands"][0]},{path},{op["results"][0]})'] if moving else
                                          [f'independent_temporary_field_copy({op["operands"][0]},{path},{op["results"][0]})'])
            objects = selected.objects if moving else frozenset({f'object_{op["id"]}'})
            return Fact(True, selected.constant, objects, fields=fields)
        if op['kind'] in ('struct_construct','array_construct'):
            fields = []
            for name, ref in zip(op['attributes']['fields'], op['operands']):
                value = facts.get(ref, Fact(False))
                fields.append((name, Fact(value.valid, value.constant, value.objects, value.capabilities)))
                fields.extend((name+'.'+path, fact) for path,fact in value.fields)
            fields = tuple(fields)
            valid = op['attributes']['type_valid'] and all(f.valid for _, f in fields)
            if valid:
                op['effects']['initialization'] = [f'construct_field({name},{ref})' for name, ref in zip(op['attributes']['fields'], op['operands'])]
                op['effects']['ownership'] = [f'transfer_to_field({ref},{name})' for name, ref in zip(op['attributes']['fields'], op['operands'])]
            return Fact(valid, objects=frozenset({f'object_{op["id"]}'}), fields=fields)
        if op['kind'] == 'struct_storage_end':
            state[op['operands'][0]] = Cell(frozenset({'Consumed'}))
            op['facts_invalidated'] = [f'initialized({op["operands"][0]})', f'owns({op["operands"][0]})']
            return Fact(True)
        if op['kind'] == 'temporary_end':
            root=op['operands'][0]
            if root not in self.children: return None
            paths=self.children[root]
            leaves=[(name,place) for name,place in paths.items()
                    if not any(other.startswith(name+'.') for other in paths)]
            op['effects']['destruction']=[f'destroy_temporary_field_if_owned({root},{name})'
                for name,place in leaves if 'Initialized' in state.get(place['id'],Cell()).states]
            for place in [root,*[p['id'] for p in paths.values()]]:
                state[place]=Cell(frozenset({'Consumed'}))
                op['facts_invalidated'].extend([f'initialized({place})',f'owns({place})'])
            op['effects']['lifetimes']=[f'end({self.place_entities[place]["lifetime"]})' for place in [root,*[p['id'] for p in paths.values()]]]
            return Fact(True)
        if op['kind'] == 'discard':
            value = facts.get(op['operands'][0], Fact(False))
            if value.fields:
                if value.valid:
                    leaves = [name for name, _ in value.fields if not any(path.startswith(name+'.') for path,_ in value.fields)]
                    moved_index = op['attributes'].get('moved_element_index')
                    moved_path = op['attributes'].get('moved_field_path')
                    if moved_index:
                        index = facts.get(moved_index, Fact(False))
                        selected = f'[{index.constant}]' if index.constant is not None else None
                        destruction = []
                        for name in leaves:
                            element = name.split('.', 1)[0]
                            if selected == element: continue
                            if selected is None:
                                destruction.append(f'discard_if_not_selected({op["operands"][0]},{moved_index},{name})')
                            else:
                                destruction.append(f'discard_field({op["operands"][0]},{name})')
                        op['attributes']['transferred_element_index'] = moved_index
                        op['effects']['destruction'] = destruction
                    elif moved_path:
                        op['attributes']['transferred_field_path'] = moved_path
                        op['effects']['destruction'] = [f'discard_field({op["operands"][0]},{name})' for name in leaves
                            if name != moved_path and not name.startswith(moved_path+'.')]
                    else:
                        op['effects']['destruction'] = [f'discard_field({op["operands"][0]},{name})' for name in leaves]
                return Fact(value.valid)
        return None

    def dereference(self, op, roots, state, facts, valid):
        """Copy or replace whole structs after capability permission checks.

        Multiple referents are alternatives, so writes retain each possible old
        value. Every target is validated before any field is changed.
        """
        args, attrs = op['operands'], op['attributes']
        attrs['struct_referents'] = roots
        if all(self.place_types[root] in self.a.lowerer.arrays for root in roots):
            attrs['array_referents'] = roots
        def states():
            return {root: dict(aggregate=snapshot(state.get(root, Cell())),
                               fields=self.field_states(root, state)) for root in roots}
        attrs['referent_states_before'] = states()
        for root in roots:
            for child in (self.children[root].values() if op['kind'] != 'deref_assign' else ()):
                if state.get(child['id'], Cell()).states != frozenset({'Initialized'}):
                    self.a.error(op, 'uninitialized_read', 'Whole-struct dereference requires every field to be initialized.',
                                 'P7', ['INITIALIZATION-001','INITIALIZATION-002'], [child['id']])
                    valid = False
        if op['kind'] == 'deref_read':
            if not valid:
                attrs['referent_states_after'] = states()
                return Fact(False)
            fields = []
            for index, name in enumerate(self.children[roots[0]]):
                cells = [state[self.children[root][name]['id']] for root in roots]
                constant = cells[0].constant if all(c.constant == cells[0].constant for c in cells) else None
                fields.append((name, Fact(True, constant, frozenset({f'object_{op["id"]}_field_{index}'}))))
            fields = tuple(fields)
            attrs['result_field_states'] = self.value_field_states(fields)
            attrs['result_ownership'] = 'Owned'
            op['rule_refs'].extend(['OWNERSHIP-003','TRANS-COPY-001'])
            op['effects']['ownership'] = [f'independent_copy_through({args[0]},{op["results"][0]})']
            op['effects']['ownership'].extend(f'independent_field_copy({self.children[root][name]["id"]},{op["results"][0]},{name})'
                                             for root in roots for name, _ in fields)
            attrs['referent_states_after'] = states()
            return Fact(True, objects=frozenset({f'object_{op["id"]}'}), fields=fields)
        if op['kind'] == 'deref_move':
            if not valid:
                attrs['referent_states_after'] = states()
                return Fact(False)
            definite=len(roots)==1
            fields=[]
            for name in self.children[roots[0]]:
                cells=[state[self.children[root][name]['id']] for root in roots]
                constant=cells[0].constant if all(cell.constant==cells[0].constant for cell in cells) else None
                fields.append((name,Fact(True,constant,frozenset().union(*(cell.objects for cell in cells)))))
            objects=frozenset().union(*(state[root].objects for root in roots))
            attrs.update(result_ownership='Owned',target_selection='definite' if definite else 'one_of_referents',
                          result_identity_selection='selected_referent',result_field_states=self.value_field_states(fields))
            op['effects']['ownership']=[f'transfer_referent_if_selected({args[0]},{root},{op["results"][0]})' for root in roots]
            op['effects']['initialization']=[f'move_referent_if_selected({root})' for root in roots]
            op['facts_invalidated']=[f'initialized({root})' for root in roots]
            for root in roots:
                for place in [root,*[child['id'] for child in self.children[root].values()]]:
                    old=state.get(place,Cell())
                    state[place]=Cell(frozenset({'Moved'}) if definite else old.states | {'Moved'},objects=old.objects)
                    op['facts_invalidated'].append(f'owns({place})')
            self.refresh(state)
            attrs['referent_states_after']=states()
            return Fact(True,objects=objects,fields=tuple(fields))
        rhs = facts.get(args[1], Fact(False))
        valid = valid and rhs.valid and attrs['type_valid']
        if valid:
            definite = len(roots) == 1
            attrs['target_selection'] = 'definite' if definite else 'one_of_referents'
            op['rule_refs'].extend(['TRANS-ASSIGN-001','TRANS-DESTROY-001'])
            op['effects']['destruction'] = []
            op['effects']['ownership'] = []
            op['effects']['initialization'] = []
            for root in roots:
                old = state[root]
                state[root] = Cell(frozenset({'Initialized'}) if definite else old.states | {'Initialized'},
                                   objects=rhs.objects if definite else old.objects | rhs.objects)
                for name, field in rhs.fields:
                    pid = self.children[root][name]['id']; previous = state[pid]
                    constant = field.constant if definite or previous.constant == field.constant else None
                    state[pid] = Cell(frozenset({'Initialized'}) if definite else previous.states | {'Initialized'},
                                      constant, field.objects if definite else previous.objects | field.objects)
                    if pid not in self.children and 'Initialized' in previous.states:
                        op['effects']['destruction'].append(f'destroy_previous_field_if_selected({args[0]},{root},{pid}) after successful RHS evaluation')
                    op['effects']['ownership'].append(f'transfer_field_if_selected({args[1]},{name},{root},{pid})')
                op['effects']['initialization'].append(f'replace_struct_if_selected({args[0]},{root})')
        attrs['referent_states_after'] = states()
        return Fact(valid)

    def transfer(self, op, root, state):
        kind = op['kind']; result = op['results'][0]
        children = self.children[root]
        cells = {name: state.get(p['id'], Cell()) for name, p in children.items()}
        whole = state.get(root, Cell())
        op['preconditions'] = [f'initialized({pid})' for pid in [root, *(p['id'] for p in children.values())]]
        if whole.states != frozenset({'Initialized'}) or any(c.states != frozenset({'Initialized'}) for c in cells.values()):
            moved = 'Moved' in whole.states or any('Moved' in c.states for c in cells.values())
            self.a.error(op, 'use_after_move' if moved else 'uninitialized_read',
                'Whole-struct access requires every field to be initialized and available on every incoming path.',
                'P8' if moved else 'P7', ['OWNERSHIP-005','OWNERSHIP-009','OWNERSHIP-010'] if moved else ['INITIALIZATION-001','INITIALIZATION-002'],
                [root, *(children[name]['id'] for name, c in cells.items() if c.states != frozenset({'Initialized'}))])
            return Fact(False)
        fields = tuple((name, Fact(True, cell.constant,
            frozenset({f'object_{op["id"]}_field_{index}'}) if kind == 'copy' else cell.objects))
            for index, (name, cell) in enumerate(cells.items()))
        objects = frozenset({f'object_{op["id"]}'}) if kind == 'copy' else whole.objects
        op['attributes']['result_ownership'] = 'Unowned' if kind == 'read' else 'Owned'
        op['attributes']['result_field_states'] = {
            name: snapshot(Cell(frozenset({'Initialized'}), f.constant, f.objects)) for name, f in fields}
        if kind == 'move':
            for pid in [root, *(p['id'] for p in children.values())]:
                state[pid] = Cell(frozenset({'Moved'}))
                op['facts_invalidated'].extend([f'initialized({pid})', f'owns({pid})'])
            op['effects'] = {'ownership': [f'transfer({root},{result})'] +
                [f'transfer_field({p["id"]},{result},{name})' for name, p in children.items()],
                'initialization': [f'moved({pid})' for pid in [root, *(p['id'] for p in children.values())]]}
        elif kind == 'copy':
            op['effects'] = {'ownership': [f'independent_copy({root},{result})'] +
                [f'independent_field_copy({p["id"]},{result},{name})' for name, p in children.items()]}
        return Fact(True, objects=objects, fields=fields)

    @staticmethod
    def value_field_states(fields):
        return {name: snapshot(Cell(frozenset({'Initialized'}), fact.constant, fact.objects))
                for name, fact in fields}

    def call_and_return(self, op, facts):
        if op['kind'] == 'call':
            callee = self.functions[op['attributes']['function']]
            parameters = {o['attributes']['parameter_index']: o['operands'][0]
                          for b in callee['blocks'] for o in b['operations'] if o['kind'] == 'parameter'}
            arguments = []
            for index, arg in enumerate(op['operands'][1:]):
                if self.value_types.get(arg) not in self.a.lowerer.structs: continue
                fields = facts[arg].fields
                parameter = parameters[index]
                arguments.append(dict(index=index, value=arg, parameter_place=parameter,
                                      field_states=self.value_field_states(fields)))
                op['effects'].setdefault('ownership', []).append(f'transfer_argument({arg},{parameter})')
                for name, _ in fields:
                    child = self.a.lowerer.component_paths(parameter)[name]['id']
                    op['effects']['ownership'].append(f'transfer_argument_field({arg},{name},{child})')
            if arguments: op['attributes']['struct_arguments'] = arguments
            if op['attributes'].get('result_ownership') == 'Owned':
                ownership = op['effects'].setdefault('ownership', [])
                ownership.append(f'receive_return_value({callee["id"]},{op["results"][0]})')
                ownership.extend(f'receive_return_field({op["results"][0]},{name})'
                                 for name in op['attributes']['result_field_states'])
        elif op['kind'] == 'return_prepare' and op['operands']:
            arg = op['operands'][0]
            if self.value_types.get(arg) in self.a.lowerer.structs:
                fields = facts[arg].fields
                op['attributes']['returned_field_states'] = self.value_field_states(fields)
                op['effects'].setdefault('ownership', []).extend(
                    f'transfer_field_to_caller({arg},{name}) after cleanup' for name, _ in fields)

    def after(self, op, state, facts, valid):
        if valid: self.call_and_return(op, facts)
        elif op['kind'] == 'call':
            op['attributes'].pop('result_field_states', None)
            op['attributes'].pop('result_ownership', None)
        root = self.root_for(op)
        if root is None: return
        if valid and op['kind'] in ('init', 'assign') and op['operands'][0] == root:
            rhs = facts[op['operands'][1]]
            for name, fact in rhs.fields:
                field = self.children[root][name]['id']
                state[field] = Cell(frozenset({'Initialized'}), fact.constant, fact.objects)
                op['facts_established'].extend([f'initialized({field})', f'owns({field})'])
                op['effects']['initialization'].append(f'initialize_field({root},{field})')
            if op['kind'] == 'assign':
                op['effects']['destruction'] = [f'destroy_previous_if_owned({p["id"]}) after successful RHS evaluation'
                    for name, p in self.children[root].items()
                    if p['id'] not in self.children and 'Initialized' in op['attributes']['field_states_before'][name]['initialization']]
        self.refresh(state)
        if op['kind'] != 'struct_storage_end': self.summarize(root, state)
        op['attributes']['aggregate_state_after'] = snapshot(state.get(root, Cell()))
        op['attributes']['field_states_after'] = self.field_states(root, state)
        for ancestor in op['attributes'].get('ancestor_states_before', {}):
            cell = state.get(ancestor, Cell())
            if valid and op['kind'] in ('init','assign') and cell.states == frozenset({'Initialized'}) and not cell.objects:
                state[ancestor] = Cell(cell.states, objects=frozenset({f'object_{op["id"]}_aggregate_{ancestor}'}))
            op['attributes'].setdefault('ancestor_states_after', {})[ancestor] = snapshot(state.get(ancestor, Cell()))
            if valid and op['kind'] in ('init','assign','move'):
                if state[ancestor].states == frozenset({'Initialized'}):
                    op['facts_established'].extend([f'initialized({ancestor})',f'owns({ancestor})'])
                else:
                    op['facts_invalidated'].extend([f'initialized({ancestor})',f'owns({ancestor})'])
        if op['kind']=='destroy' and any('Moved' in s['initialization'] for s in op['attributes']['field_states_before'].values()):
            op['rule_refs'].extend(r for r in ('OWNERSHIP-011','OWNERSHIP-012') if r not in op['rule_refs'])
        if valid and op['operands'][0] != root and op['operands'][0] in self.parents and op['kind'] in ('init', 'assign', 'move'):
            status = next(iter(state[root].states))
            if status == 'Initialized' and not state[root].objects:
                state[root] = Cell(state[root].states, objects=frozenset({f'object_{op["id"]}_aggregate'}))
                op['attributes']['aggregate_state_after'] = snapshot(state[root])
            initialization = snapshot(state[root])['initialization'][0]
            op['facts_established'].append(f'aggregate_initialization({root},{initialization})')
            if op['kind']=='move':
                op['facts_invalidated'].extend([f'initialized({root})', f'owns({root})'])
                op['effects'].setdefault('ownership', []).append(f'aggregate_ownership({root},{status})')
            elif 'Moved' in op['attributes']['field_states_before'][self.field_name(op)]['initialization']:
                op['rule_refs'].extend(r for r in ('OWNERSHIP-013','OWNERSHIP-014') if r not in op['rule_refs'])
                if status == 'Initialized':
                    op['facts_established'].extend([f'initialized({root})', f'owns({root})'])

    def field_name(self, op):
        root=self.parents[op['operands'][0]]
        return next(name for name,p in self.children[root].items() if p['id']==op['operands'][0])

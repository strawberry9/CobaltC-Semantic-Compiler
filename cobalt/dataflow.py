"""Path-sensitive initialization/ownership and constant evaluation over the CFG.

The current parser admits acyclic flow only. Joins retain all possible place states;
reads require Initialized on every reachable incoming path. Values are SSA identities.
"""
from dataclasses import dataclass
from collections import deque
from .semantic import INTEGERS, limits, is_pointer


@dataclass(frozen=True)
class Cell:
    states: frozenset = frozenset({'Uninitialized'})
    constant: object = None
    objects: frozenset = frozenset()
    capabilities: frozenset = frozenset()
    minimum: object = None
    maximum: object = None


@dataclass(frozen=True)
class Fact:
    valid: bool
    constant: object = None
    objects: frozenset = frozenset()
    capabilities: frozenset = frozenset()
    fields: tuple = ()
    minimum: object = None
    maximum: object = None


def merge(states):
    keys=set().union(*(s.keys() for s in states))
    out={}
    for key in sorted(keys):
        cells=[s.get(key,Cell()) for s in states]
        constant=cells[0].constant if all(c.constant==cells[0].constant for c in cells) else None
        ranges=[cell_range(c) for c in cells]
        minimum=min(r[0] for r in ranges) if all(r[0] is not None for r in ranges) else None
        maximum=max(r[1] for r in ranges) if all(r[1] is not None for r in ranges) else None
        out[key]=Cell(frozenset().union(*(c.states for c in cells)),constant,
                      frozenset().union(*(c.objects for c in cells)),
                      frozenset().union(*(c.capabilities for c in cells)),minimum,maximum)
    return out


def cell_range(cell):
    """Return inclusive integer bounds, using a known constant as a singleton."""
    if cell.constant is not None and type(cell.constant) is int:
        return (cell.constant,cell.constant)
    return cell.minimum,cell.maximum


def snapshot(cell):
    owners={'Initialized':'Owned','Moved':'Moved','Uninitialized':'Unowned','Consumed':'Unowned','PartiallyInitialized':'Unowned','PartiallyMoved':'PartiallyMoved'}
    return dict(initialization=sorted({'PartiallyInitialized' if s=='PartiallyMoved' else s for s in cell.states}),ownership=sorted({owners[s] for s in cell.states}),object_identities=sorted(cell.objects))


class Analyzer:
    def __init__(self,lowerer):
        self.lowerer=lowerer;self.d=lowerer.d
        self.type_names={t['id']:t['name'] for t in lowerer.types.values()}

    def run(self):
        self.return_borrows = {}
        functions = {fn['id']: fn for fn in self.lowerer.functions}
        visiting, done = set(), set()
        self.analysis_stack = visiting
        def analyze(fn):
            if fn['id'] in done or fn['id'] in visiting: return
            visiting.add(fn['id'])
            for block in fn['blocks']:
                for op in block['operations']:
                    if op['kind'] == 'call': analyze(functions[op['attributes']['function']])
            self.function(fn)
            visiting.remove(fn['id']); done.add(fn['id'])
        for fn in self.lowerer.functions: analyze(fn)

    def function(self,fn):
        from .borrowing import BorrowAnalysis
        from .structs import StructAnalysis
        borrows = BorrowAnalysis(self, fn)
        structs = StructAnalysis(self, fn)
        borrows.structs = structs
        structs.borrow_analysis = borrows
        blocks={b['id']:b for b in fn['blocks']}; places={p['id']:p for p in fn['places']}
        values={v['id']:v for v in fn['values']}; facts={}
        producers={result:op for block in fn['blocks'] for op in block['operations'] for result in op['results']}
        producer_positions={result:(block['id'],index) for block in fn['blocks'] for index,op in enumerate(block['operations']) for result in op['results']}
        operations_by_block={block['id']:block['operations'] for block in fn['blocks']}
        indegree={bid:0 for bid in blocks}; incoming={bid:[] for bid in blocks}
        for b in blocks.values():
            for dest in b['terminator'].get('targets',[]):indegree[dest]+=1
        incoming[fn['entry_block']].append({})
        queue=deque(bid for bid in blocks if indegree[bid]==0)
        processed=0
        while queue:
            bid=queue.popleft();b=blocks[bid];processed+=1
            reachable=bool(incoming[bid]);state=merge(incoming[bid]) if reachable else {}
            for op in b['operations']:
                a=op['attributes'];a['reachable']=reachable
                if not reachable:
                    a['validation']='unreachable';continue
                structs.before(op, state)
                kind=op['kind'];args=op['operands'];result=op['results'][0] if op['results'] else None
                typ=self.type_names[values[result]['type']] if result else None
                fact=Fact(typ!='error'); valid=True
                before=state.get(args[0],Cell()) if args and args[0] in places else None
                if before is not None:a['state_before']=snapshot(before)
                permitted = borrows.before(op, state, facts)
                handled = borrows.operation(op, state, facts, typ) if permitted else Fact(False)
                if handled is None: handled = structs.operation(op, state, facts)
                if handled is not None:
                    fact = handled; valid = fact.valid
                elif kind=='alloca':
                    state[args[0]]=Cell();op['facts_established']=[f'uninitialized({args[0]})']
                elif kind=='parameter':
                    valid=self.type_names[places[args[0]]['type']]!='error'
                    if valid:
                        typ_name=self.type_names[places[args[0]]['type']]
                        bounds=limits(typ_name) if typ_name in INTEGERS else (None,None)
                        state[args[0]]=Cell(frozenset({'Initialized'}),objects=frozenset({f'object_{op["id"]}'}),minimum=bounds[0],maximum=bounds[1])
                        op['effects']={'initialization':[f'initialize({args[0]})'],'ownership':[f'owns({args[0]})']}
                elif kind=='const':
                    constant=a['constant'];valid=typ!='error'
                    if typ in INTEGERS:
                        lo,hi=limits(typ)
                        if not lo<=constant<=hi:
                            self.error(op,'literal_range',f'Literal {constant} is outside {typ}.','P5',['PARSE-020']);valid=False
                    fact=Fact(valid,constant,frozenset({f'object_{op["id"]}'}))
                elif kind in ('read','copy','move'):
                    op['preconditions']=[f'initialized({args[0]})']
                    valid=before.states==frozenset({'Initialized'}) and typ!='error'
                    if not valid and typ!='error':
                        moved='Moved' in before.states
                        self.error(op,'use_after_move' if moved else 'uninitialized_read',
                            'Place is not initialized on every incoming path.' if not moved else 'Place may have been moved on an incoming path.',
                            'P8' if moved else 'P7',['OWNERSHIP-005'] if moved else ['INITIALIZATION-001','INITIALIZATION-002'],[args[0]])
                    objects=before.objects if kind!='copy' else frozenset({f'object_{op["id"]}'})
                    minimum,maximum=cell_range(before)
                    fact=Fact(valid,before.constant,objects,before.capabilities,minimum=minimum,maximum=maximum)
                    if valid and kind=='move':
                        state[args[0]]=Cell(frozenset({'Moved'}))
                        op['effects']={'ownership':[f'transfer({args[0]},{result})'],'initialization':[f'moved({args[0]})']}
                        op['facts_invalidated']=[f'initialized({args[0]})',f'owns({args[0]})']
                    elif valid and kind=='copy':op['effects']={'ownership':[f'independent_copy({args[0]},{result})']}
                    a['result_ownership']='Unowned' if kind=='read' else 'Owned'
                elif kind in ('init','assign'):
                    rhs=facts.get(args[1],Fact(False));valid=rhs.valid and a['type_valid']
                    if kind=='assign' and (a['const_binding'] or places[args[0]]['mutability']=='Immutable'):
                        self.error(op,'immutable_assignment','Assignment requires a mutable destination (Section 29).','P5',['TYPE-066'],[args[0]]);valid=False
                    if a.get('const_binding') and kind=='init' and rhs.constant is None:
                        self.error(op,'constant_required','This implementation requires a statically evaluable scalar constant initializer.','P5');valid=False
                    if valid:
                        op['preconditions']=[f'valid({args[1]})']
                        if kind=='assign' and 'Initialized' in before.states:
                            op['effects']['destruction']=[f'destroy_previous_if_owned({args[0]}) after successful RHS evaluation']
                        state[args[0]]=Cell(frozenset({'Initialized'}),rhs.constant,rhs.objects,rhs.capabilities,rhs.minimum,rhs.maximum)
                        op['effects'].update(initialization=[f'initialize({args[0]},{args[1]})'],ownership=[f'transfer({args[1]},{args[0]})'])
                        op['facts_established']=[f'initialized({args[0]})',f'owns({args[0]})']
                        op['facts_invalidated']=[f'previous_state({args[0]})']
                elif kind in ('binary','arithmetic_checked','unary','unary_checked'):
                    fs=[facts.get(arg,Fact(False)) for arg in args];valid=all(f.valid for f in fs) and typ!='error'
                    constant=None
                    if valid and all(f.constant is not None for f in fs):
                        x=fs[0].constant;y=fs[1].constant if len(fs)>1 else None;operator=a['operator']
                        if kind in ('unary','unary_checked'):constant=not x if operator=='!' else -x if operator=='-' else x
                        else:constant={'+':lambda:x+y,'-':lambda:x-y,'*':lambda:x*y,'==':lambda:x==y,'!=':lambda:x!=y,'<':lambda:x<y,'<=':lambda:x<=y,'>':lambda:x>y,'>=':lambda:x>=y}[operator]()
                        if typ in INTEGERS:
                            lo,hi=limits(typ)
                            if not lo<=constant<=hi:
                                self.error(op,'arithmetic_failure',f'Provable {typ} arithmetic overflow.','P5',['TYPE-055','TYPE-056']);valid=False;constant=None
                    if kind in ('arithmetic_checked','unary_checked'):
                        a.update(failure_mode='abort',result_condition='operation_succeeded',runtime_check=constant is None)
                    fact=Fact(valid,constant,frozenset({f'object_{op["id"]}'}))
                elif kind=='phi':
                    # Only reachable predecessors can contribute a result.
                    fs=[facts[x] for x in args if x in facts]
                    valid=bool(fs) and all(f.valid for f in fs)
                    constant=fs[0].constant if fs and all(f.constant==fs[0].constant for f in fs) else None
                    fact=Fact(valid,constant,frozenset().union(*(f.objects for f in fs)),frozenset().union(*(f.capabilities for f in fs)))
                elif kind=='call':
                    valid=typ!='error' and all(facts.get(x,Fact(False)).valid for x in args[1:])
                    fact=Fact(valid,objects=frozenset({f'object_{op["id"]}'}))
                    if valid:op['effects']={'ownership':[f'by_value_argument({x})' for x in args[1:]]}
                elif kind=='return_prepare':
                    valid=all(facts.get(x,Fact(False)).valid for x in args) and a.get('type_valid',True)
                    if valid:op['effects']={'ownership':[f'transfer_to_caller({x}) after cleanup' for x in args]}
                elif kind=='destroy':
                    # A conditional cleanup obligation is explicit, never a fabricated initialized fact.
                    a['executes_if_initialized']='Initialized' in before.states
                    if 'Initialized' in before.states:
                        op['effects']={'destruction':[f'destroy_if_owned({args[0]})'],'ownership':[f'consume_if_owned({args[0]})']}
                        op['facts_invalidated']=[f'owns({args[0]})',f'initialized({args[0]})']
                    state[args[0]]=Cell(frozenset({'Consumed'}))
                elif kind=='lifetime_end':
                    op['effects']={'lifetimes':[f'end({args[0]})']}
                    op['facts_invalidated']=[f'live({args[0]})']
                elif kind=='discard':
                    valid=facts.get(args[0],Fact(False)).valid
                    if valid:op['effects']={'destruction':[f'discard({args[0]})']}
                elif kind=='temporary_end':
                    cell=state.get(args[0],Cell());valid='Initialized' in cell.states
                    if valid:
                        op['effects']={'destruction':[f'destroy_temporary_if_owned({args[0]})'],
                                       'lifetimes':[f'end({places[args[0]]["lifetime"]})']}
                        op['facts_invalidated']=[f'initialized({args[0]})',f'owns({args[0]})']
                    state[args[0]]=Cell(frozenset({'Consumed'}))
                elif kind=='missing_return':
                    self.error(op,'missing_return','A successful path reaches the end of a non-void function.','P11',['TYPE-037']);valid=False
                elif kind=='invalid':valid=False;fact=Fact(False)
                elif kind=='defer_register':op['facts_established']=[f'pending({args[0]})']
                elif kind=='defer_execute':
                    op['preconditions']=[f'pending({args[0]})'];op['facts_invalidated']=[f'pending({args[0]})']
                valid = valid and permitted
                fact, valid = borrows.after(op, state, facts, fact, valid, typ)
                structs.after(op, state, facts, valid)
                a['validation']='valid' if valid else 'invalid'
                if result:
                    fact=Fact(valid and fact.valid,fact.constant,fact.objects if valid else frozenset(),
                              fact.capabilities if valid else frozenset(),fact.fields if valid else (),
                              fact.minimum if valid else None,fact.maximum if valid else None)
                    facts[result]=fact
                    a['object_identities']=sorted(fact.objects)
                    if fact.valid:
                        op['facts_established'].append(f'typed({result},{typ})')
                        if fact.constant is not None:a['constant_value']=fact.constant
                    else:values[result]['type']=self.lowerer.type_id('error')
                if before is not None:
                    after=state.get(args[0],Cell());a['state_after']=snapshot(after)
                    if valid and before!=after:op['postconditions'].append(f'{args[0]} = {"|".join(sorted(after.states))}')
                borrows.finish(op, state, facts)
            term=b['terminator'];targets=term.get('targets',[]);selected=list(targets)
            if reachable and term['kind']=='branch':
                if term.get('operands'):
                    cond=facts.get(term['operands'][0],Fact(False))
                    if cond.valid and type(cond.constant) is bool:selected=[targets[0 if cond.constant else 1]]
                    elif not cond.valid:selected=[]
                elif term.get('attributes',{}).get('checked_value'):
                    checked_value=term['attributes']['checked_value']
                    f=facts.get(checked_value,Fact(False))
                    if not f.valid:selected=[targets[1]]
                    elif f.constant is not None or (producers.get(checked_value,{}).get('kind')=='array_bounds' and not producers[checked_value]['attributes'].get('runtime_check',True)):
                        selected=[targets[0]]
            for dest in targets:
                if reachable and dest in selected:
                    edge_state=dict(state)
                    if term['kind']=='branch' and len(targets)==2 and term.get('operands'):
                        outcome=(dest==targets[0])
                        refinements=self.refine_comparison(term['operands'][0],outcome,producers,producer_positions,operations_by_block,facts,places,edge_state)
                        if refinements:
                            attrs=term.setdefault('attributes',{})
                            evidence=attrs.setdefault('branch_refinements',[])
                            for refinement in refinements:
                                item=dict(target=dest,condition_result=term['operands'][0],
                                          branch='true' if outcome else 'false',**refinement)
                                if item not in evidence:evidence.append(item)
                    incoming[dest].append(edge_state)
                indegree[dest]-=1
                if indegree[dest]==0:queue.append(dest)
        if processed!=len(blocks):raise AssertionError('Cycle encountered in the acyclic milestone CFG')

    def refine_comparison(self,condition,outcome,producers,producer_positions,operations_by_block,facts,places,state):
        """Refine a place on a branch that constrains it against an integer constant."""
        comparison=producers.get(condition)
        if not comparison or comparison['kind']!='binary':return []
        operator=comparison['attributes'].get('operator')
        if operator not in ('==','!=','<','<=','>','>='):return []
        left,right=comparison['operands']

        def source_place(value):
            producer=producers.get(value)
            if producer and producer['kind'] in ('read','copy') and producer['operands'] and producer['operands'][0] in places:
                return producer['operands'][0]
            return None

        refinements=[]
        for candidate,constant_value in ((left,facts.get(right,Fact(False))),
                                         (right,facts.get(left,Fact(False)))):
            source=producers.get(candidate)
            place=source_place(candidate)
            source_position=producer_positions.get(candidate)
            comparison_position=producer_positions.get(condition)
            # A call between loading the place and comparing it can change that
            # place through a managed pointer, so the old SSA value proves
            # nothing about the current place state on the outgoing edge.
            if source and source_position and comparison_position:
                if source_position[0]!=comparison_position[0]:continue
                ops=operations_by_block[source_position[0]]
                lo,hi=sorted((source_position[1],comparison_position[1]))
                if any(op['kind']=='call' for op in ops[lo+1:hi]):continue
            if not place or not constant_value.valid or type(constant_value.constant) not in (int,bool,str):continue
            old=state.get(place,Cell())
            if old.states!=frozenset({'Initialized'}):continue
            value=constant_value.constant
            if operator in ('==','!='):
                equality=outcome if operator=='==' else not outcome
                if not equality or type(value) not in (int,bool,str):continue
                if old.constant is not None and old.constant!=value:continue
                state[place]=Cell(old.states,value,old.objects,old.capabilities,
                                  value if type(value) is int else old.minimum,
                                  value if type(value) is int else old.maximum)
                refinements.append(dict(place=place,value=value,operator=operator,
                                        reason=f'{operator} branch proves equality'))
                continue
            if type(value) is not int or self.type_names[places[place]['type']] not in INTEGERS:continue
            normalized=operator if candidate==left else {'<':'>','<=':'>=','>':'<','>=':'<='}[operator]
            if not outcome:normalized={'<':'>=','<=':'>','>':'<=','>=':'<'}[normalized]
            minimum,maximum=cell_range(old)
            if normalized=='<':maximum=min(maximum,value-1) if maximum is not None else value-1
            elif normalized=='<=':maximum=min(maximum,value) if maximum is not None else value
            elif normalized=='>':minimum=max(minimum,value+1) if minimum is not None else value+1
            elif normalized=='>=':minimum=max(minimum,value) if minimum is not None else value
            if minimum is not None and maximum is not None and minimum>maximum:continue
            constant=minimum if minimum is not None and minimum==maximum else old.constant
            state[place]=Cell(old.states,constant,old.objects,old.capabilities,minimum,maximum)
            refinements.append(dict(place=place,operator=operator,minimum=minimum,maximum=maximum,
                                    reason=f'{operator} branch narrows integer range'))
        return refinements

    def error(self,op,code,message,phase,rules=(),entities=()):
        self.d.add(code,message,op['source_span'],phase,rules,entities)

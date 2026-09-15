import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class RuntimeStructArrayTests(unittest.TestCase):
    init='[Point { x=1,y=7 },Point { x=3,y=7 }]'
    prefix='mut Point[2] points='+init+'; '
    def compile(self,body,params='i32 index',functions='',declaration=None):
        doc=compile_text('module demo; '+(declaration or 'struct Point { i32 x; i32 y; } ')+functions+' fn test('+params+'):i32 { '+body+' }')
        validate(doc)
        return doc
    def valid(self,body,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc
    def reject(self,body,code,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertIn(code,[d['code'] for d in doc['diagnostics']],doc['diagnostics'])
        return doc
    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]
    def test_unknown_read_copies_complete_fields(self):
        doc=self.valid(self.prefix+'Point point=points[index]; return point.y;')
        read=self.ops(doc,'array_read')[0]
        self.assertEqual(len(read['attributes']['possible_elements']),2)
        self.assertEqual(set(read['attributes']['result_field_states']),{'x','y'})
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],7)
        sources={obj for fields in read['attributes']['element_field_states_before'].values() for cell in fields.values() for obj in cell['object_identities']}
        copied={obj for cell in read['attributes']['result_field_states'].values() for obj in cell['object_identities']}
        self.assertTrue(sources.isdisjoint(copied))
    def test_known_read_and_replacement(self):
        doc=self.valid(self.prefix+'i32 chosen=0; points[chosen]=Point { x=9,y=8 }; Point point=points[chosen]; return point.x;')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],9)
        self.assertEqual(len(self.ops(doc,'array_assign')[0]['effects']['destruction']),2)
    def test_unknown_write_is_conditional(self):
        doc=self.valid(self.prefix+'points[index]=Point { x=9,y=8 }; return points[0].x;')
        self.assertNotIn('constant_value',self.ops(doc,'copy')[-1]['attributes'])
        self.reject('mut Point[2] points; points[index]=Point { x=9,y=8 }; Point[2] copied=points; return 0;','uninitialized_read')
    def test_move_transfers_field_identity_alternatives(self):
        doc=self.valid(self.prefix+'Point point=move points[index]; return point.y;')
        move=self.ops(doc,'array_move')[0]
        before=move['attributes']['element_field_states_before']
        for name,cell in move['attributes']['result_field_states'].items():
            expected={obj for fields in before.values() for obj in fields[name]['object_identities']}
            self.assertEqual(set(cell['object_identities']),expected)
        for fields in move['attributes']['element_field_states_after'].values():
            self.assertTrue(all(set(cell['initialization'])=={'Initialized','Moved'} for cell in fields.values()))
        destroyed=[o for o in self.ops(doc,'destroy') if 'Moved' in o['attributes']['state_before']['initialization']]
        self.assertEqual(len(destroyed),4)
        self.assertTrue(all(o['attributes']['guard']=='initialized_and_owned' for o in destroyed))
    def test_move_rejection_and_restoration(self):
        prefix=self.prefix+'Point point=move points[index]; '
        self.reject(prefix+'return points[0].x;','use_after_move')
        self.reject(prefix+'Point second=points[index]; return 0;','use_after_move')
        self.reject(prefix+'points[index]=Point { x=9,y=8 }; Point[2] copied=points; return 0;','use_after_move')
        self.valid(prefix+'points='+self.init+'; Point[2] copied=points; return copied[0].x;')
        self.valid(prefix+'points[0]=Point { x=9,y=8 }; points[1]=Point { x=9,y=8 }; Point[2] copied=points; return copied[0].x;')
    def test_borrows_and_projected_access(self):
        self.valid(self.prefix+'mut Point* ptr=&mut points[index]; ptr->x=9; return ptr->y;')
        self.reject(self.prefix+'Point* ptr=&points[index]; points[0].x=9; return ptr->y;','borrow_conflict')
        self.reject(self.prefix+'Point* ptr=&points[index]; Point point=move points[index]; return ptr->y;','borrow_conflict')
        self.valid(self.prefix+'Point* ptr=&points[index]; i32 value=ptr->y; points[index]=Point { x=9,y=8 }; return value;')
    def test_partial_fields_bounds_and_mutability(self):
        self.reject('mut Point[2] points; points[0]=Point { x=1,y=2 }; Point point=points[index]; return 0;','uninitialized_read')
        self.reject(self.prefix+'i32 taken=move points[0].x; Point point=points[index]; return 0;','use_after_move')
        self.reject(self.prefix+'i32 selected=2; Point point=points[selected]; return 0;','index_out_of_bounds')
        self.reject('Point[2] points='+self.init+'; points[index]=Point { x=9,y=8 }; return 0;','immutable_assignment')
    def test_failed_rhs_and_conflict_rollback(self):
        doc=self.reject(self.prefix+'points[index]=Point { x=true,y=8 }; return points[0].x;','type_error')
        assign=self.ops(doc,'array_assign')[0]
        self.assertEqual(assign['effects'],{})
        self.assertEqual(assign['attributes']['element_field_states_before'],assign['attributes']['element_field_states_after'])
    def test_nested_struct_and_array_descendants(self):
        decl='struct Leaf { i32 x; } struct Point { Leaf leaf; i32[2] values; } '
        init='[Point { leaf=Leaf { x=1 }, values=[2,3] },Point { leaf=Leaf { x=4 }, values=[5,6] }]'
        self.valid('mut Point[2] points='+init+'; Point point=move points[index]; points='+init+'; return point.values[0];',declaration=decl)
    def test_single_and_empty_structs(self):
        self.valid('mut Point[1] points=[Point { x=1,y=2 }]; Point point=move points[index]; points[index]=point; Point[1] copied=points; return copied[0].x;')
        self.valid('mut Empty[2] values=[Empty {},Empty {}]; Empty value=move values[index]; values=[Empty {},Empty {}]; return 0;',declaration='struct Empty {} ')
        self.reject('Point[0] points=[]; Point point=points[index]; return 0;','index_out_of_bounds')
    def test_calls_returns_and_returned_borrow(self):
        funcs='fn read(Point point):i32 { return point.y; } fn field(Point* ptr):i32* { return &ptr->y; } '
        self.valid(self.prefix+'i32* ptr=field(&points[index]); i32 saved=*ptr; return read(move points[index]);',functions=funcs)
        self.reject('return 0;','lifetime_violation',functions='fn bad(Point[2] points,i32 index):Point* { return &points[index]; } ')
    def test_defer_join_evaluation_and_determinism(self):
        self.reject(self.prefix+'defer { points[0].x; }; Point point=move points[index]; return 0;','use_after_move')
        self.reject(self.prefix+'if(flag) { Point point=move points[index]; } return points[0].x;','use_after_move',params='i32 index,bool flag')
        body=self.prefix+'Point point=points[next()]; return point.y;'
        funcs='fn next():i32 { return 0; } '
        doc=self.valid(body,functions=funcs)
        self.assertEqual(len(self.ops(doc,'call')),1)
        self.assertEqual(dumps(doc),dumps(self.compile(body,functions=funcs)))
    def test_return_struct_value_and_known_move(self):
        functions='fn select(Point[2] values,i32 index):Point { return move values[index]; } '
        self.valid(self.prefix+'Point point=select(points,index); return point.y;',functions=functions)
        doc=self.valid(self.prefix+'i32 selected=0; Point point=move points[selected]; return points[1].x;')
        move=self.ops(doc,'array_move')[0]
        self.assertEqual(len(move['attributes']['possible_elements']),1)
        self.assertTrue(all(cell['initialization']==['Moved'] for fields in move['attributes']['element_field_states_after'].values() for cell in fields.values()))

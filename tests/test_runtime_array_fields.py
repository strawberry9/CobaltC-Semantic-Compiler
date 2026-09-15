import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class RuntimeArrayFieldTests(unittest.TestCase):
    prefix='mut Point[2] points=[Point { x=1,y=7 },Point { x=3,y=7 }]; '
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
    def test_reads_and_known_writes(self):
        doc=self.valid(self.prefix+'return points[index].y;')
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['constant_value'],7)
        doc=self.valid(self.prefix+'i32 chosen=0; points[chosen].x=9; return points[chosen].x;')
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['constant_value'],9)
    def test_sibling_availability_after_move(self):
        prefix=self.prefix+'i32 taken=move points[index].x; '
        self.valid(prefix+'return points[index].y;')
        self.reject(prefix+'return points[0].x;','use_after_move')
        self.reject(prefix+'Point point=points[index]; return 0;','use_after_move')
        self.valid(prefix+'points[0].x=7; points[1].x=8; Point[2] copied=points; return copied[0].x;')
        self.reject(prefix+'points[index].x=9; Point[2] copied=points; return 0;','use_after_move')
    def test_partial_initialization_and_ancestor_identity(self):
        self.valid('mut Point[2] points; points[0].x=1; points[1].x=2; return points[index].x;')
        self.reject('mut Point[2] points; points[index].x=1; return points[0].x;','uninitialized_read')
        doc=self.valid('mut Point[1] points; points[index].x=1; points[index].y=2; Point[1] copied=points; return copied[0].x;')
        assign=self.ops(doc,'array_assign')[-1]
        self.assertTrue(assign['attributes']['aggregate_state_after']['object_identities'])
        element=assign['attributes']['field_states_after']['[0]']
        self.assertTrue(element['object_identities'])
    def test_borrows_disjoint_fields_and_conflicting_parent(self):
        self.valid(self.prefix+'mut i32* ptr=&mut points[index].x; points[index].y=9; return *ptr;')
        self.reject(self.prefix+'i32* ptr=&points[index].x; points[0].x=9; return *ptr;','borrow_conflict')
        self.reject(self.prefix+'i32* ptr=&points[index].x; points[index]=Point { x=9,y=8 }; return *ptr;','borrow_conflict')
        self.valid(self.prefix+'i32* ptr=&points[index].x; i32 saved=*ptr; points[index].x=9; return saved;')
    def test_nested_substruct_and_array_field_operations(self):
        decl='struct Leaf { i32 x; i32 y; } struct Point { Leaf leaf; i32[2] values; } '
        prefix='mut Point[2] points=[Point { leaf=Leaf { x=1,y=2 },values=[3,4] },Point { leaf=Leaf { x=5,y=6 },values=[7,8] }]; '
        self.valid(prefix+'Leaf selected=move points[index].leaf; i32[2] values=points[index].values; return selected.x;',declaration=decl)
        self.valid(prefix+'points[index].leaf=Leaf { x=9,y=8 }; points[index].values=[7,8]; return points[index].leaf.x;',declaration=decl)
    def test_type_bounds_and_mutability(self):
        self.reject(self.prefix+'return points[index].missing;','unknown_field')
        self.reject(self.prefix+'i32 chosen=2; return points[chosen].x;','index_out_of_bounds')
        self.reject(self.prefix.replace('mut Point','Point')+'points[index].x=9; return 0;','immutable_assignment')
        self.reject(self.prefix+'points[index].x=true; return 0;','type_error')
    def test_move_identity_cleanup_and_rollback(self):
        doc=self.valid(self.prefix+'return move points[index].x;')
        move=self.ops(doc,'array_move')[0]
        expected={obj for cell in move['attributes']['element_states_before'].values() for obj in cell['object_identities']}
        self.assertEqual(set(move['attributes']['object_identities']),expected)
        destroyed=[o for o in self.ops(doc,'destroy') if 'Moved' in o['attributes']['state_before']['initialization']]
        self.assertEqual(len(destroyed),2)
        doc=self.reject(self.prefix+'i32* ptr=&points[index].x; i32 taken=move points[index].x; return *ptr;','borrow_conflict')
        move=self.ops(doc,'array_move')[0]
        self.assertEqual(move['effects'],{})
        self.assertEqual(move['attributes']['element_states_before'],move['attributes']['element_states_after'])
    def test_call_lifetime_and_defer(self):
        self.valid(self.prefix+'i32* ptr=identity(&points[index].x); return *ptr;',functions='fn identity(i32* value):i32* { return value; } ')
        self.reject('return 0;','lifetime_violation',functions='fn bad(Point[2] points,i32 index):i32* { return &points[index].x; } ')
        self.reject(self.prefix+'defer { points[index].x; }; return move points[index].x;','use_after_move')
    def test_single_evaluation_and_determinism(self):
        body=self.prefix+'return points[next()].x;'
        funcs='fn next():i32 { return 0; } '
        doc=self.valid(body,functions=funcs)
        self.assertEqual(len(self.ops(doc,'call')),1)
        self.assertEqual(dumps(doc),dumps(self.compile(body,functions=funcs)))
        self.assertIn('projected',render(doc))

import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class StructArrayTests(unittest.TestCase):
    declaration='struct Point { i32 x; i32 y; } '
    init='[Point { x=1,y=2 },Point { x=3,y=4 }]'
    prefix='mut Point[2] points='+init+'; '
    def compile(self,body,params='',functions='',declaration=None):
        doc=compile_text('module demo; '+(declaration or self.declaration)+functions+' fn test('+params+'):i32 { '+body+' }')
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
    def test_construction_and_field_reads(self):
        doc=self.valid(self.prefix+'return points[0].x+points[1].y;')
        self.assertEqual(self.ops(doc,'arithmetic_checked')[0]['attributes']['constant_value'],5)
        self.assertEqual(doc['compilation']['compiler']['support_profile'],'struct-array-milestone')
    def test_independent_element_and_whole_array_copies(self):
        doc=self.valid(self.prefix+'mut Point point=points[0]; Point[2] copied=points; point.x=9; points[0].x=7; return copied[0].x;')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],1)
    def test_partial_field_move_and_restoration(self):
        prefix=self.prefix+'i32 taken=move points[0].x; '
        self.valid(prefix+'return points[0].y+points[1].x;')
        self.reject(prefix+'Point point=points[0]; return 0;','use_after_move')
        self.reject(prefix+'Point[2] copied=points; return 0;','use_after_move')
        self.valid(prefix+'points[0].x=7; Point[2] copied=points; return copied[0].x;')
    def test_whole_element_move_preserves_identity(self):
        doc=self.valid(self.prefix+'Point point=move points[0]; points[0]=Point { x=7,y=8 }; return point.x;')
        move=self.ops(doc,'move')[0]
        self.assertEqual(set(move['attributes']['object_identities']),set(move['attributes']['aggregate_state_before']['object_identities']))
    def test_partial_initialization(self):
        prefix='mut Point[2] points; points[0].x=1; points[0].y=2; '
        self.valid(prefix+'return points[0].x;')
        self.reject(prefix+'Point[2] copied=points; return 0;','uninitialized_read')
        self.valid(prefix+'points[1]=Point { x=3,y=4 }; Point[2] copied=points; return copied[1].x;')
    def test_element_borrows_and_overlap(self):
        self.valid(self.prefix+'mut Point* ptr=&mut points[0]; ptr->x=7; points[1].x=9; return ptr->x;')
        self.valid(self.prefix+'i32* ptr=&points[0].x; points[0].y=7; return *ptr;')
        self.reject(self.prefix+'i32* ptr=&points[0].x; points[0]=Point { x=7,y=8 }; return *ptr;','borrow_conflict')
        self.reject(self.prefix+'Point* ptr=&points[0]; Point[2] moved=move points; return ptr->x;','borrow_conflict')
    def test_nested_struct_and_scalar_array_fields(self):
        self.valid('mut Box[1] boxes=[Box { point=Point { x=1,y=2 }, values=[7,8] }]; boxes[0].values[index]=9; boxes[0].point.x=7; return boxes[0].point.x;',params='i32 index',declaration=self.declaration+'struct Box { Point point; i32[2] values; } ')
    def test_by_value_calls_and_returns(self):
        functions='fn identity(Point[2] values):Point[2] { return move values; } fn first(Point value):i32 { return value.x; } '
        self.valid(self.prefix+'Point[2] copied=identity(points); Point[2] moved=identity(move points); return first(moved[0]);',functions=functions)
    def test_cleanup_scalar_leaves_and_moved_skips(self):
        doc=self.valid(self.prefix+'i32 taken=move points[0].x; return taken;')
        destroys=self.ops(doc,'destroy')
        self.assertEqual(len(destroys),5)
        self.assertEqual(sum(not o['attributes']['executes_if_initialized'] for o in destroys),1)
    def test_defer_and_branch_join(self):
        self.reject(self.prefix+'defer { points[0].x; }; return move points[0].x;','use_after_move')
        self.reject(self.prefix+'if(flag) { Point taken=move points[0]; } return points[0].x;','use_after_move',params='bool flag')
    def test_empty_arrays_and_empty_elements(self):
        self.valid('Point[0] points=[]; Point[0] copied=points; return 0;')
        self.valid('Empty[2] values=[Empty {},Empty {}]; Empty first=move values[0]; return 0;',declaration='struct Empty {} ')
    def test_bounds_mutability_and_wrong_initializer(self):
        self.reject(self.prefix+'return points[2].x;','index_out_of_bounds')
        self.reject('Point[2] points='+self.init+'; points[0].x=7; return 0;','immutable_assignment')
        self.reject('Point[1] points=[1]; return 0;','type_error')
    def test_dynamic_and_temporary_boundaries(self):
        for action in ('Point point=points[index];','Point point=move points[index];','Point* ptr=&points[index];','points[index]=Point { x=7,y=8 };'):
            self.valid(self.prefix+action+'return 0;',params='i32 index')
        self.valid('Point point=make()[0]; return point.x;',functions='fn make():Point[2] { return '+self.init+'; } ')
    def test_element_borrow_return_lifetime(self):
        self.valid(self.prefix+'i32* ptr=field(&points[0]); return *ptr;',functions='fn field(Point* point):i32* { return &point->x; } ')
        self.reject('return 0;','lifetime_violation',functions='fn bad(Point[2] points):Point* { return &points[0]; } ')
    def test_deterministic_explanation(self):
        body=self.prefix+'return points[0].x;'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('array',render(doc))

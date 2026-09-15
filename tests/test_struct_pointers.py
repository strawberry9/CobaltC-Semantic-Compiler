import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class StructPointerTests(unittest.TestCase):
    prefix = 'module demo; struct Point { i32 x; i32 y; } '

    def compile(self, body, functions='', params=''):
        return compile_text(self.prefix+functions+' fn test('+params+'):i32 { '+body+' }')

    def valid(self, body, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        validate(doc)
        return doc

    def rejected(self, body, code, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertIn(code, [d['code'] for d in doc['diagnostics']], doc['diagnostics'])
        validate(doc)
        return doc

    def ops(self, doc, kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def test_shared_projection_syntax_and_constants(self):
        doc = self.valid('Point point=Point{x=3,y=5}; Point* ptr=&point; return ptr->x + (*ptr).y;')
        self.assertEqual(self.ops(doc, 'arithmetic_checked')[0]['attributes']['constant_value'], 8)
        self.assertEqual([o['attributes']['field'] for o in self.ops(doc, 'field_borrow')], ['x','y'])

    def test_mutable_projection_rhs_reads_same_field(self):
        doc = self.valid('mut Point point=Point{x=3,y=5}; mut Point* ptr=&mut point; ptr->x=ptr->x+1; (*ptr).y=9; return point.x+point.y;')
        self.assertEqual(self.ops(doc, 'arithmetic_checked')[-1]['attributes']['constant_value'], 13)

    def test_shared_pointer_cannot_write_or_borrow_mutably(self):
        for action in ('ptr->x=9;', 'mut i32* field=&mut ptr->x; *field=9;'):
            self.rejected('Point point=Point{x=1,y=2}; Point* ptr=&point; '+action+' return 0;', 'borrow_conflict')

    def test_whole_borrow_requires_initialized_and_mutable_storage(self):
        self.rejected('mut Point point; point.x=1; Point* ptr=&point; return ptr->x;', 'invalid_borrow')
        self.rejected('Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; return ptr->x;', 'borrow_conflict')
        self.rejected('Point point=Point{x=1,y=2}; i32 moved=move point.x; Point* ptr=&point; return ptr->y;', 'invalid_borrow')

    def test_disjoint_projected_mutable_borrows(self):
        doc = self.valid('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; mut i32* left=&mut ptr->x; mut i32* right=&mut (*ptr).y; *left=7; *right=8; return *left+*right;')
        self.assertEqual(self.ops(doc, 'arithmetic_checked')[0]['attributes']['constant_value'], 15)
        self.assertTrue(any(not c['overlap'] for o in self.ops(doc, 'field_borrow') for c in o['attributes'].get('overlap_checks', [])))

    def test_same_field_projected_conflicts(self):
        for action in ('ptr->x=9;', 'i32 value=ptr->x;', 'mut i32* second=&mut ptr->x; *second=4;'):
            self.rejected('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; mut i32* first=&mut ptr->x; '+action+' return *first;', 'borrow_conflict')

    def test_sibling_access_and_last_use_resume(self):
        self.valid('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; i32* first=&ptr->x; ptr->y=4; i32 result=*first; ptr->x=8; return result+ptr->x;')

    def test_root_alias_conflicts_and_last_use(self):
        self.rejected('mut Point point=Point{x=1,y=2}; Point* ptr=&point; point.x=4; return ptr->x;', 'borrow_conflict')
        self.rejected('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; Point moved=move point; return ptr->x;', 'borrow_conflict')
        self.valid('mut Point point=Point{x=1,y=2}; Point* ptr=&point; i32 value=ptr->x; point.x=4; return value;')

    def test_struct_parameters_and_caller_field_invalidation(self):
        doc = self.valid('mut Point point=Point{x=1,y=2}; update(&mut point); return point.x;',
                         functions='fn update(mut Point* ptr):void { ptr->x=9; }')
        copy = self.ops(doc, 'copy')[-1]
        self.assertNotIn('constant_value', copy['attributes'])
        self.valid('Point point=Point{x=1,y=2}; return read(&point);', functions='fn read(Point* ptr):i32 { return ptr->x; }')
        fn = doc['functions'][0]
        caller_places = [p for p in fn['places'] if p['parent']]
        self.assertEqual(len(caller_places), 2)
        self.assertFalse(any(o['operands'][0] in {p['id'] for p in caller_places} for o in self.ops(doc, 'destroy')))

    def test_call_conflicts_with_live_projected_borrow(self):
        self.rejected('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; i32* field=&ptr->x; update(ptr); return *field;', 'borrow_conflict',
                      functions='fn update(mut Point* ptr):void { ptr->y=4; }')

    def test_shared_and_mutable_input_derived_struct_returns(self):
        self.valid('Point point=Point{x=1,y=2}; Point* ptr=identity(&point); return ptr->x;', functions='fn identity(Point* ptr):Point* { return ptr; }')
        self.valid('mut Point point=Point{x=1,y=2}; mut Point* ptr=identity(&mut point); ptr->x=8; return point.x;', functions='fn identity(mut Point* ptr):mut Point* { return ptr; }')

    def test_returned_projection_preserves_field_identity(self):
        doc = self.valid('Point point=Point{x=4,y=8}; i32* field=select(&point); return *field;', functions='fn select(Point* ptr):i32* { return &ptr->y; }')
        self.assertEqual(self.ops(doc, 'deref_read')[-1]['attributes']['constant_value'], 8)
        doc = self.valid('mut Point point=Point{x=4,y=8}; mut i32* field=select(&mut point); *field=9; return point.y;', functions='fn select(mut Point* ptr):mut i32* { return &mut ptr->y; }')
        self.assertEqual(self.ops(doc, 'copy')[-1]['attributes']['constant_value'], 9)

    def test_returned_projection_through_wrapper(self):
        self.valid('Point point=Point{x=4,y=8}; i32* field=wrap(&point); return *field;', functions='fn select(Point* ptr):i32* { return &ptr->y; } fn wrap(Point* ptr):i32* { return select(ptr); }')

    def test_returned_projection_alternatives(self):
        doc = self.valid('Point point=Point{x=4,y=8}; i32* field=select(&point, flag); return *field;', params='bool flag',
                         functions='fn select(Point* ptr, bool flag):i32* { if (flag) { return &ptr->x; } return &ptr->y; }')
        self.assertNotIn('constant_value', self.ops(doc, 'deref_read')[-1]['attributes'])

    def test_return_local_struct_or_field_pointer_rejected(self):
        for typ, expression in [('Point*', '&point'), ('i32*', '&ptr->x')]:
            doc = compile_text(self.prefix+'fn bad():'+typ+' { Point point=Point{x=1,y=2}; Point* ptr=&point; return '+expression+'; }')
            self.assertIn('lifetime_violation', [d['code'] for d in doc['diagnostics']])

    def test_deferred_projection_keeps_root_borrow_live(self):
        self.rejected('mut Point point=Point{x=1,y=2}; Point* ptr=&point; defer { ptr->x; }; point.x=4; return 0;', 'borrow_conflict')
        self.valid('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; defer { ptr->x=8; }; ptr->y=4; return ptr->y;')

    def test_branch_borrow_liveness(self):
        self.valid('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; if (flag) { i32* field=&ptr->x; i32 value=*field; } ptr->x=9; return ptr->x;', params='bool flag')

    def test_projection_diagnostics_and_bounded_unsupported_operations(self):
        self.rejected('Point point=Point{x=1,y=2}; Point* ptr=&point; return ptr->missing;', 'unknown_field')
        self.rejected('i32 value=1; i32* ptr=&value; return ptr->x;', 'invalid_field_access')
        self.rejected('Point point=Point{x=1,y=2}; Point* ptr=&point; i32 value=move ptr->x; return 0;', 'borrow_conflict')

    def test_whole_struct_reborrow_suspension_and_resume(self):
        self.valid('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; Point* shared=&*ptr; i32 value=shared->x; ptr->y=9; return value+ptr->y;')
        self.rejected('mut Point point=Point{x=1,y=2}; mut Point* ptr=&mut point; Point* shared=&*ptr; ptr->y=9; return shared->x;', 'borrow_conflict')

    def test_projection_lifetime_constrained_by_capability_and_field(self):
        doc = self.valid('return ptr->x;', params='Point* ptr')
        fn = doc['functions'][0]
        op = self.ops(doc, 'field_borrow')[0]
        cid = op['attributes']['created_capabilities'][0]
        cap = next(c for c in fn['capabilities'] if c['id']==cid)
        parent = next(c for c in fn['capabilities'] if c['id']==cap['derived_from'])
        field = next(p for p in fn['places'] if p['id']==cap['referent'])
        self.assertIn(f'contained_in({cap["lifetime"]},{parent["lifetime"]})', op['effects']['lifetimes'])
        self.assertIn(f'contained_in({cap["lifetime"]},{field["lifetime"]})', op['effects']['lifetimes'])

    def test_report_and_determinism(self):
        body = 'Point point=Point{x=1,y=2}; Point* ptr=&point; return ptr->x;'
        doc = self.valid(body)
        self.assertEqual(dumps(doc), dumps(self.compile(body)))
        html = render(doc)
        self.assertIn('field x', html)
        self.assertIn('struct pointer', html)

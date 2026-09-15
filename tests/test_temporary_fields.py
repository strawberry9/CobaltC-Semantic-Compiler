import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render

class TemporaryFieldTests(unittest.TestCase):
    prefix='module demo; struct Point { i32 x; i32 y; } struct Box { Point point; i32 other; } '
    make='fn make():Box { return Box{point=Point{x=1,y=2},other=3}; } '

    def compile(self, body, functions=''):
        return compile_text(self.prefix+self.make+functions+' fn test():i32 { '+body+' }')

    def valid(self, body, functions=''):
        doc=self.compile(body,functions)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        validate(doc)
        return doc

    def ops(self,doc,kind):
        return [o for f in doc['functions'] if f['name']=='test' for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def test_constructor_field_constant_and_complete_temporary_cleanup(self):
        doc=self.valid('return Point{x=7,y=8}.x;')
        extract=self.ops(doc,'struct_extract')[0]
        self.assertEqual(extract['attributes']['constant_value'],7)
        self.assertEqual(len(self.ops(doc,'discard')[0]['effects']['destruction']),2)

    def test_nested_return_projection_evaluates_call_once(self):
        doc=self.valid('return make().point.y;')
        self.assertEqual(len(self.ops(doc,'call')),1)
        extract=self.ops(doc,'struct_extract')[0]
        self.assertEqual(extract['attributes']['field'],'point.y')
        self.assertNotIn('constant_value',extract['attributes'])
        self.assertEqual(len(self.ops(doc,'discard')[0]['effects']['destruction']),3)

    def test_substruct_extraction_rebases_fields_and_has_independent_identity(self):
        doc=self.valid('mut Point selected=Box{point=Point{x=7,y=8},other=9}.point; selected.x=4; return selected.y;')
        extract=self.ops(doc,'struct_extract')[0]
        self.assertEqual(set(extract['attributes']['result_field_states']),{'x','y'})
        constructors=self.ops(doc,'struct_construct')
        source_ids={identity for o in constructors for identity in o['attributes']['object_identities']}
        self.assertTrue(source_ids.isdisjoint(extract['attributes']['object_identities']))
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],8)

    def test_extracted_value_passed_and_returned_by_value(self):
        self.valid('return total(make().point);','fn total(Point value):i32 { return value.x+value.y; }')
        self.valid('Point selected=select(); return selected.x;','fn select():Point { return make().point; }')

    def test_extracted_substruct_discard_has_separate_cleanup(self):
        doc=self.valid('make().point; return 0;')
        discards=self.ops(doc,'discard')
        self.assertEqual([len(o['effects']['destruction']) for o in discards],[3,2])
        self.assertNotEqual(discards[0]['operands'],discards[1]['operands'])

    def test_move_source_then_extract_has_no_double_local_destruction(self):
        doc=self.valid('Point value=Point{x=1,y=2}; i32 selected=(move value).x; return selected;')
        self.assertEqual(sum(not o['attributes']['executes_if_initialized'] for o in self.ops(doc,'destroy')),2)
        self.assertEqual(self.ops(doc,'struct_extract')[0]['attributes']['constant_value'],1)

    def test_invalid_fields_and_invalid_source(self):
        for body,code in [('return make().missing;','unknown_field'),('return (1).x;','invalid_field_access'),('return Point{x=1}.x;','missing_field_initializer')]:
            doc=self.compile(body)
            self.assertIn(code,[d['code'] for d in doc['diagnostics']],doc['diagnostics'])
            self.assertNotEqual(doc['compilation']['result'],'valid')
        doc=self.compile('return Point{x=1}.x;')
        self.assertTrue(all(not o['effects'] for o in self.ops(doc,'struct_extract')))

    def test_temporary_borrows_and_assignment_keep_their_boundaries(self):
        for body,code in [('i32* ptr=&make().point.x; return 0;','unsupported_temporary_borrow'),
                          ('make().point.x=9; return 0;','unsupported_temporary_place')]:
            doc=self.compile(body)
            self.assertIn(code,[d['code'] for d in doc['diagnostics']])
            self.assertEqual(doc['compilation']['result'],'incomplete')

    def test_moved_temporary_substruct_is_supported(self):
        self.valid('Point value=move make().point; return value.x;')

    def test_empty_substruct_defer_and_deterministic_report(self):
        self.valid('Empty value=Container{empty=Empty{},number=1}.empty; return 0;', 'struct Empty {} struct Container { Empty empty; i32 number; }')
        body='defer { make().point.x; }; return Point{x=1,y=2}.y;'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('temporary',render(doc))

import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class MultidimensionalTemporaryStructArrayTests(unittest.TestCase):
    declaration = 'struct Point { i32 x; i32 y; } '
    values = '[[Point { x=1,y=2 },Point { x=3,y=4 }],[Point { x=5,y=6 },Point { x=7,y=8 }]]'
    factory = 'fn make_grid():Point[2][2] { return '+values+'; } '

    def compile(self, body, params='i32 row,i32 column', factory=None, declarations=None):
        source = ('module demo; '+(declarations or self.declaration)+
                  (factory or self.factory)+'fn test('+params+'):i32 { '+body+' }')
        doc = compile_text(source)
        validate(doc)
        return doc

    def valid(self, body, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        return doc

    def ops(self, doc, kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind'] == kind]

    def test_runtime_chained_extracts_copy_a_struct(self):
        doc = self.valid('Point point=make_grid()[row][column]; return point.x;')
        extracts = self.ops(doc, 'array_extract')
        self.assertEqual(len(extracts), 2)
        self.assertEqual([op['attributes']['array_length'] for op in extracts], [2, 2])
        self.assertEqual([len(op['attributes']['possible_elements']) for op in extracts], [2, 2])
        self.assertEqual(set(extracts[-1]['attributes']['result_field_states']), {'x', 'y'})

    def test_literal_and_mixed_indices_narrow_each_layer(self):
        for expression, counts in [('make_grid()[0][column]', [1, 2]),
                                   ('make_grid()[row][1]', [2, 1]),
                                   ('make_grid()[0][1]', [1, 1])]:
            with self.subTest(expression=expression):
                doc = self.valid('Point point='+expression+'; return point.y;')
                self.assertEqual([len(op['attributes']['possible_elements'])
                                  for op in self.ops(doc, 'array_extract')], counts)

    def test_field_read_from_temporary_grid(self):
        doc = self.valid('return make_grid()[row][column].x;')
        self.assertEqual(len(self.ops(doc, 'array_extract')), 2)
        self.assertEqual(len(self.ops(doc, 'struct_extract')), 1)
        self.assertIn('temporary', render(doc).lower())

    def test_each_index_evaluates_once_in_order(self):
        helpers = 'fn row_index():i32 { return 0; } fn column_index():i32 { return 1; } '
        doc = self.valid('return make_grid()[row_index()][column_index()].y;',
                         params='', factory=self.factory+helpers)
        ops = [op for block in doc['functions'][-1]['blocks'] for op in block['operations']]
        kinds = [op['kind'] for op in ops]
        calls = [i for i, kind in enumerate(kinds) if kind == 'call']
        bounds = [i for i, kind in enumerate(kinds) if kind == 'array_bounds']
        extracts = [i for i, kind in enumerate(kinds) if kind == 'array_extract']
        discards = [i for i, kind in enumerate(kinds) if kind == 'discard']
        self.assertEqual(len(calls), 3)  # factory, row index, column index
        self.assertEqual(len(bounds), 2)
        self.assertEqual(len(extracts), 2)
        self.assertEqual(len(discards), 3)  # factory array, intermediate row, selected struct
        self.assertLess(calls[0], calls[1])
        self.assertLess(calls[1], bounds[0])
        self.assertLess(bounds[0], extracts[0])
        self.assertLess(extracts[0], discards[0])
        self.assertLess(discards[0], calls[2])
        self.assertLess(calls[2], bounds[1])
        self.assertLess(bounds[1], extracts[1])
        self.assertLess(extracts[1], discards[1])

    def test_source_and_intermediate_cleanup_follow_copies(self):
        doc = self.valid('Point point=make_grid()[row][column]; return point.x;')
        extracts = self.ops(doc, 'array_extract')
        discards = [op for op in self.ops(doc, 'discard')
                    if op['operands'][0] in [extracts[0]['operands'][0], extracts[0]['results'][0]]]
        self.assertEqual(len(discards), 2)
        destroy_counts = [len(op['effects'].get('destruction', [])) for op in discards]
        self.assertEqual(destroy_counts, [8, 4])
        call = self.ops(doc, 'call')[0]
        source_ids = {identity for state in call['attributes']['result_field_states'].values()
                      for identity in state['object_identities']}
        row_ids = {identity for state in extracts[0]['attributes']['result_field_states'].values()
                   for identity in state['object_identities']}
        point_ids = {identity for state in extracts[1]['attributes']['result_field_states'].values()
                     for identity in state['object_identities']}
        self.assertTrue(source_ids.isdisjoint(row_ids))
        self.assertTrue(row_ids.isdisjoint(point_ids))

    def test_row_extraction_and_three_dimensions(self):
        self.valid('Point[2] row=make_grid()[row_index]; Point point=row[column]; return point.x;',
                   params='i32 row_index,i32 column')
        cube = 'fn make_cube():Point[2][2][1] { return [[[Point { x=1,y=2 }],[Point { x=3,y=4 }]],[[Point { x=5,y=6 }],[Point { x=7,y=8 }]]]; } '
        doc = self.valid('return make_cube()[row][column][0].y;', factory=cube)
        self.assertEqual(len(self.ops(doc, 'array_extract')), 3)
        self.assertEqual([op['attributes']['array_length'] for op in self.ops(doc, 'array_extract')], [2, 2, 1])

    def test_temporary_places_remain_read_only_except_element_moves(self):
        for body in ('Point* value=&make_grid()[row][column]; return 0;',
                     'make_grid()[row][column]=Point { x=1,y=2 }; return 0;',
                     'make_grid()[row][column].x=9; return 0;'):
            with self.subTest(body=body):
                doc = self.compile(body)
                self.assertNotEqual(doc['compilation']['result'], 'valid')

    def test_bounds_fail_at_the_selected_dimension(self):
        for expression in ('make_grid()[2][column].x', 'make_grid()[row][2].x'):
            with self.subTest(expression=expression):
                doc = self.compile('return '+expression+';')
                self.assertIn('index_out_of_bounds', [d['code'] for d in doc['diagnostics']])
                self.assertEqual(len(self.ops(doc, 'array_bounds')), 2)

    def test_report_and_esir_are_deterministic(self):
        source = 'return make_grid()[row][column].y;'
        self.assertEqual(dumps(self.compile(source)), dumps(self.compile(source)))


if __name__ == '__main__':
    unittest.main()

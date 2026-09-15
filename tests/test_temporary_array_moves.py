import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class TemporaryArrayMoveTests(unittest.TestCase):
    declaration = 'struct Point { i32 x; i32 y; } '
    grid = '[[Point { x=1,y=2 },Point { x=3,y=4 }],[Point { x=5,y=6 },Point { x=7,y=8 }]]'

    def compile(self, body, *, factory=None, params='i32 row,i32 column', declaration=None, functions=''):
        if factory is None:
            factory = 'fn make_grid():Point[2][2] { return '+self.grid+'; } '
        doc = compile_text('module demo; '+(declaration or self.declaration)+factory+functions+
                           f'fn test({params}):i32 {{ {body} }}')
        validate(doc)
        return doc

    def valid(self, body, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        return doc

    def ops(self, doc, kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind'] == kind]

    def test_scalar_move_transfers_selected_identity_and_cleans_other_elements(self):
        doc = self.valid('i32 value=move make_values()[index]; return value;',
                         factory='fn make_values():i32[3] { return [4,5,6]; } ',
                         params='i32 index')
        move = self.ops(doc, 'array_move_extract')[0]
        call = self.ops(doc, 'call')[0]
        self.assertEqual(move['attributes']['target_selection'], 'one_of_elements')
        self.assertEqual(set(move['attributes']['object_identities']),
                         set().union(*(set(call['attributes']['result_field_states'][f'[{index}]']['object_identities'])
                                       for index in range(3))))
        cleanup = next(op for op in self.ops(doc, 'discard') if op['attributes'].get('moved_element_index'))
        self.assertEqual(len(cleanup['effects']['destruction']), 3)
        self.assertTrue(all(effect.startswith('discard_if_not_selected') for effect in cleanup['effects']['destruction']))

    def test_known_struct_move_preserves_identity_and_skips_selected_cleanup(self):
        doc = self.valid('Point point=move make_grid()[0][1]; return point.x;', params='')
        moves = self.ops(doc, 'array_move_extract')
        self.assertEqual([op['attributes']['possible_elements'] for op in moves], [['[0]'], ['[1]']])
        call = self.ops(doc, 'call')[0]
        original = call['attributes']['result_field_states']['[0].[1].x']['object_identities']
        moved = moves[-1]['attributes']['result_field_states']['x']['object_identities']
        self.assertEqual(moved, original)
        cleanups = [op for op in self.ops(doc, 'discard') if op['attributes'].get('moved_element_index')]
        self.assertEqual(len(cleanups), 2)
        self.assertEqual(len(cleanups[0]['effects']['destruction']), 4)
        self.assertEqual(cleanups[1]['effects']['destruction'], ['discard_field('+cleanups[1]['operands'][0]+',[0].x)',
                                                                  'discard_field('+cleanups[1]['operands'][0]+',[0].y)'])

    def test_runtime_nested_moves_preserve_possible_identities_and_conditional_cleanup(self):
        doc = self.valid('Point point=move make_grid()[row][column]; return point.y;')
        moves = self.ops(doc, 'array_move_extract')
        self.assertEqual(len(moves), 2)
        self.assertEqual([op['attributes']['target_selection'] for op in moves], ['one_of_elements', 'one_of_elements'])
        self.assertEqual(len(moves[-1]['attributes']['result_field_states']['y']['object_identities']), 4)
        cleanups = [op for op in self.ops(doc, 'discard') if op['attributes'].get('moved_element_index')]
        self.assertTrue(all(cleanup['effects']['destruction'] for cleanup in cleanups))
        self.assertTrue(all(effect.startswith('discard_if_not_selected')
                            for cleanup in cleanups for effect in cleanup['effects']['destruction']))

    def test_move_can_flow_through_by_value_call_and_bounds_failure_aborts(self):
        functions = 'fn take(Point point):i32 { return point.x; } '
        doc = self.valid('return take(move make_grid()[row][column]);', functions=functions)
        self.assertEqual(len(self.ops(doc, 'array_move_extract')), 2)
        doc = self.compile('Point point=move make_grid()[2][column]; return point.x;')
        self.assertIn('index_out_of_bounds', [diag['code'] for diag in doc['diagnostics']])
        self.assertEqual(self.ops(doc, 'array_move_extract')[0]['attributes']['validation'], 'unreachable')

    def test_explanations_and_output_are_deterministic(self):
        body = 'Point point=move make_grid()[row][column]; return point.x;'
        doc = self.valid(body)
        self.assertEqual(dumps(doc), dumps(self.compile(body)))
        self.assertIn('transfer the element of temporary', render(doc))


if __name__ == '__main__':
    unittest.main()

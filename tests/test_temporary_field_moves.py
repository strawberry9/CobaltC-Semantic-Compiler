import unittest

from cobalt.driver import compile_text
from cobalt.esir import validate


class TemporaryFieldMoveTests(unittest.TestCase):
    point = 'struct Point { i32 x; i32 y; } '

    def compile(self, body, *, declarations=None, factory=None, params=''):
        declarations = declarations or self.point
        factory = factory or 'fn make():Point { return Point { x=7,y=8 }; } '
        doc = compile_text('module demo; '+declarations+factory+f'fn test({params}):i32 {{ {body} }}')
        validate(doc)
        return doc

    def valid(self, body, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        return doc

    def ops(self, doc, kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind'] == kind]

    def test_scalar_field_move_preserves_identity_and_skips_its_cleanup(self):
        doc = self.valid('i32 value=move make().x; return value;')
        move = self.ops(doc, 'struct_move_extract')[0]
        call = self.ops(doc, 'call')[0]
        self.assertEqual(move['attributes']['result_identity_selection'], 'selected_subtree')
        self.assertEqual(move['attributes']['object_identities'], call['attributes']['result_field_states']['x']['object_identities'])
        cleanup = self.ops(doc, 'discard')[0]
        self.assertEqual(cleanup['effects']['destruction'], [f'discard_field({cleanup["operands"][0]},y)'])

    def test_substruct_move_rebases_and_transfers_descendant_states(self):
        declarations = self.point+'struct Outer { Point point; i32 tag; } '
        factory = 'fn make():Outer { return Outer { point=Point { x=3,y=4 },tag=5 }; } '
        doc = self.valid('Point point=move make().point; return point.x;', declarations=declarations, factory=factory)
        move = self.ops(doc, 'struct_move_extract')[0]
        self.assertEqual(set(move['attributes']['result_field_states']), {'x','y'})
        original = self.ops(doc, 'call')[0]['attributes']['result_field_states']
        self.assertEqual(move['attributes']['result_field_states']['x']['object_identities'], original['point.x']['object_identities'])
        self.assertEqual(self.ops(doc, 'discard')[0]['effects']['destruction'], [f'discard_field({self.ops(doc, "discard")[0]["operands"][0]},tag)'])

    def test_runtime_temporary_element_field_move_keeps_selected_subtree(self):
        declarations = self.point+'struct Outer { Point point; i32 tag; } '
        factory = ('fn make():Outer[2] { return [Outer { point=Point { x=1,y=2 },tag=3 },'
                   'Outer { point=Point { x=4,y=5 },tag=6 }]; } ')
        doc = self.valid('Point point=move make()[index].point; return point.y;',
                         declarations=declarations, factory=factory, params='i32 index')
        array_move = self.ops(doc, 'array_move_extract')[0]
        field_move = self.ops(doc, 'struct_move_extract')[0]
        self.assertEqual(field_move['attributes']['result_field_states']['y']['object_identities'],
                         array_move['attributes']['result_field_states']['point.y']['object_identities'])
        cleanup = next(op for op in self.ops(doc, 'discard') if op['attributes'].get('moved_field_path'))
        self.assertEqual(cleanup['attributes']['transferred_field_path'], 'point')
        self.assertEqual(len(cleanup['effects']['destruction']), 1)
        self.assertTrue(cleanup['effects']['destruction'][0].endswith(',tag)'))

    def test_nested_runtime_field_move_is_deterministic(self):
        declarations = self.point+'struct Outer { Point[2] points; i32 tag; } '
        factory = ('fn make():Outer[2] { return [Outer { points=[Point { x=1,y=2 },Point { x=3,y=4 }],tag=5 },'
                   'Outer { points=[Point { x=6,y=7 },Point { x=8,y=9 }],tag=10 }]; } ')
        body = 'Point point=move make()[row].points[column]; return point.x;'
        first = self.valid(body, declarations=declarations, factory=factory, params='i32 row,i32 column')
        second = self.compile(body, declarations=declarations, factory=factory, params='i32 row,i32 column')
        self.assertEqual(first, second)
        self.assertEqual(len(self.ops(first, 'array_move_extract')), 2)
        self.assertEqual(self.ops(first, 'struct_move_extract')[0]['attributes']['field'], 'points')


if __name__ == '__main__':
    unittest.main()

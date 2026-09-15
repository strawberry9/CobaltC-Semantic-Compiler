import unittest

from cobalt.driver import compile_text
from cobalt.esir import validate


class ManagedPointerArrayMoveTests(unittest.TestCase):
    def compile(self,body,*,declarations='',params='i32 index'):
        header='struct Point { i32 x; i32 y; } '
        doc=compile_text('module demo; '+header+declarations+f'fn test({params}):i32 {{ {body} }}')
        validate(doc);return doc

    def valid(self,body,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc

    def ops(self,doc,kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind']==kind]

    def test_scalar_element_move_and_reinitialization_through_pointer(self):
        declarations='struct Data { i32[2] values; i32 tag; } '
        doc=self.valid('mut Data data=Data { values=[1,2],tag=3 }; mut Data* ptr=&mut data; '
                       'i32 old=move ptr->values[0]; ptr->values[0]=9; return old+ptr->values[0];',
                       declarations=declarations)
        self.assertEqual(self.ops(doc,'deref_move')[0]['attributes']['validation'],'valid')
        self.assertEqual(self.ops(doc,'deref_assign')[0]['attributes']['validation'],'valid')

    def test_struct_element_move_preserves_identity_and_can_replace(self):
        declarations='struct Data { Point[2] points; i32 tag; } '
        init='[Point { x=1,y=2 },Point { x=3,y=4 }]'
        doc=self.valid(f'mut Data data=Data {{ points={init},tag=5 }}; mut Data* ptr=&mut data; '
                       'Point old=move ptr->points[index]; ptr->points[index]=Point { x=7,y=8 }; return old.x;',
                       declarations=declarations)
        move=self.ops(doc,'deref_move')[0]
        self.assertEqual(move['attributes']['target_selection'],'one_of_referents')
        self.assertEqual(len(move['attributes']['result_field_states']['x']['object_identities']),2)
        self.assertEqual(self.ops(doc,'deref_assign')[0]['attributes']['validation'],'valid')

    def test_nested_cell_and_projected_field_moves(self):
        declarations='struct Data { i32[2][2] grid; Point[2][2] points; i32 tag; } '
        prefix='mut Data data=Data { grid=[[1,2],[3,4]], points=[[Point {x=5,y=6},Point {x=7,y=8}],[Point {x=9,y=10},Point {x=11,y=12}]],tag=0 }; mut Data* ptr=&mut data; '
        self.valid(prefix+'i32 cell=move ptr->grid[row][column]; ptr->grid[row][column]=7; return cell;',
                   declarations=declarations,params='i32 row,i32 column')
        doc=self.valid(prefix+'i32 field=move ptr->points[row][column].x; '
                       'ptr->points[row][column].x=13; return field;',
                       declarations=declarations,params='i32 row,i32 column')
        self.assertEqual(len(self.ops(doc,'indexed_field_borrow')),2)
        self.assertEqual(len(self.ops(doc,'deref_move')),1)

    def test_shared_parent_cannot_move(self):
        declarations='struct Data { i32[2] values; i32 tag; } '
        shared='Data data=Data { values=[1,2],tag=3 }; Data* ptr=&data; i32 old=move ptr->values[0]; return old;'
        doc=self.compile(shared,declarations=declarations)
        self.assertIn('borrow_conflict',[diag['code'] for diag in doc['diagnostics']])

    def test_whole_array_and_row_move_restore_managed_storage(self):
        declarations='struct Data { i32[2] values; i32[2][2] grid; i32 tag; } '
        doc=self.valid('mut Data data=Data { values=[1,2],grid=[[3,4],[5,6]],tag=7 }; '
                       'mut Data* ptr=&mut data; i32[2] old=move ptr->values; '
                       'ptr->values=[8,9]; i32[2] row=move ptr->grid[1]; ptr->grid[1]=[10,11]; '
                       'return old[0]+row[0]+ptr->values[1]+ptr->grid[1][0];',declarations=declarations)
        self.assertEqual(len(self.ops(doc,'deref_move')),2)
        self.assertTrue(all(op['attributes']['validation']=='valid' for op in self.ops(doc,'deref_assign')))


if __name__=='__main__':
    unittest.main()

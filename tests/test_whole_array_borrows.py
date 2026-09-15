import unittest

from cobalt.driver import compile_text
from cobalt.esir import validate
from cobalt.explain import render


class WholeArrayBorrowTests(unittest.TestCase):
    header = 'module demo; struct Data { i32[2] values; i32 tag; } '

    def compile(self, body, functions='', params=''):
        doc = compile_text(self.header + functions + f' fn test({params}):i32 {{ {body} }}')
        validate(doc)
        return doc

    def valid(self, body, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        return doc

    def reject(self, body, code, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertIn(code, [d['code'] for d in doc['diagnostics']], doc['diagnostics'])
        return doc

    def ops(self, doc, kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind'] == kind]

    def test_shared_whole_array_borrow_copies_complete_array(self):
        doc = self.valid('i32[2] values=[1,2]; i32[2]* pointer=&values; '
                         'i32[2] copied=*pointer; return copied[1];')
        read = self.ops(doc, 'deref_read')[0]
        self.assertEqual(read['attributes']['result_ownership'], 'Owned')
        self.assertEqual(self.ops(doc, 'copy')[-1]['attributes']['constant_value'], 2)

    def test_mutable_whole_array_borrow_replaces_array(self):
        doc = self.valid('mut i32[2] values=[1,2]; mut i32[2]* pointer=&mut values; '
                         '*pointer=[7,8]; i32[2] copied=*pointer; return copied[0];')
        assignment = self.ops(doc, 'deref_assign')[0]
        self.assertEqual(len(assignment['effects']['destruction']), 2)
        self.assertEqual(self.ops(doc, 'copy')[-1]['attributes']['constant_value'], 7)

    def test_nested_and_struct_arrays_keep_complete_snapshots(self):
        self.valid('i32[2][2] grid=[[1,2],[3,4]]; i32[2][2]* pointer=&grid; '
                   'i32[2][2] copied=*pointer; return copied[1][0];')
        self.valid('Point[2] points=[Point { x=7 },Point { x=8 }]; '
                   'Point[2]* pointer=&points; Point[2] copied=*pointer; return copied[1].x;',
                   functions='struct Point { i32 x; } ')

    def test_shared_and_mutable_permissions_apply_to_whole_array(self):
        self.reject('mut i32[2] values=[1,2]; i32[2]* pointer=&values; '
                    '*pointer=[7,8]; return 0;', 'borrow_conflict')
        self.reject('mut i32[2] values=[1,2]; mut i32[2]* pointer=&mut values; '
                    'values[0]=7; i32[2] copied=*pointer; return copied[0];', 'borrow_conflict')

    def test_whole_array_borrow_overlaps_element_borrows(self):
        self.reject('mut i32[2] values=[1,2]; i32[2]* whole=&values; '
                    'mut i32* element=&mut values[0]; i32[2] copied=*whole; return copied[0];', 'borrow_conflict')

    def test_struct_field_borrows_preserve_sibling_disjointness(self):
        self.valid('mut Data data=Data { values=[1,2], tag=3 }; '
                   'mut i32[2]* values=&mut data.values; *values=[7,8]; '
                   'i32* tag=&data.tag; return *tag;')

    def test_struct_pointer_array_field_borrows_preserve_parent_permissions(self):
        self.valid('mut Data data=Data { values=[1,2], tag=3 }; mut Data* root=&mut data; '
                   'mut i32[2]* values=&mut root->values; *values=[7,8]; return data.values[0];')
        self.reject('Data data=Data { values=[1,2], tag=3 }; Data* root=&data; '
                    'mut i32[2]* values=&mut root->values; return 0;', 'borrow_conflict')

    def test_unavailable_whole_array_cannot_be_borrowed_or_copied(self):
        self.reject('mut i32[2] values=[1,2]; i32 taken=move values[0]; '
                    'i32[2]* pointer=&values; return 0;', 'invalid_borrow')

    def test_whole_array_borrow_cannot_escape_local_storage(self):
        doc = compile_text(self.header + 'fn bad():i32[2]* { i32[2] values=[1,2]; return &values; }')
        validate(doc)
        self.assertIn('lifetime_violation', [d['code'] for d in doc['diagnostics']], doc['diagnostics'])

    def test_input_derived_whole_array_borrow_can_be_returned(self):
        functions = 'fn identity(i32[2]* pointer):i32[2]* { return pointer; } '
        self.valid('i32[2] values=[1,2]; i32[2]* pointer=identity(&values); '
                   'i32[2] copied=*pointer; return copied[0];', functions=functions)

    def test_whole_array_pointer_supports_checked_element_reads(self):
        doc=self.valid('i32[2] values=[3,7]; i32[2]* pointer=&values; '
                       'return (*pointer)[1];')
        borrow=self.ops(doc,'indexed_field_borrow')[0]
        self.assertNotIn('field',borrow['attributes'])
        self.assertEqual(borrow['attributes']['target_selection'],'definite')
        self.assertEqual(len(borrow['attributes']['possible_elements']),1)
        self.assertIn('borrow the checked element',render(doc))

    def test_whole_array_pointer_supports_multidimensional_checked_reads(self):
        doc=self.valid('i32[2][2] grid=[[1,2],[3,4]]; i32[2][2]* pointer=&grid; '
                       'return (*pointer)[row][column];',params='i32 row,i32 column')
        borrow=self.ops(doc,'indexed_field_borrow')[0]
        self.assertEqual(len(borrow['attributes']['dimension_bounds_proofs']),2)
        self.assertEqual(len(borrow['attributes']['possible_elements']),4)

    def test_whole_array_pointer_element_borrows_overlap_the_array_capability(self):
        self.reject('mut i32[2] values=[1,2]; i32[2]* whole=&values; '
                    'mut i32* element=&mut (*whole)[0]; return 0;', 'borrow_conflict')

    def test_exclusive_whole_array_pointer_replaces_checked_elements(self):
        doc=self.valid('mut i32[2] values=[1,2]; mut i32[2]* pointer=&mut values; '
                       '(*pointer)[1]=9; return values[1];')
        assignment=self.ops(doc,'deref_assign')[0]
        self.assertEqual(assignment['attributes']['validation'],'valid')

    def test_shared_whole_array_pointer_cannot_replace_an_element(self):
        self.reject('mut i32[2] values=[1,2]; i32[2]* pointer=&values; '
                    '(*pointer)[1]=9; return 0;', 'borrow_conflict')

    def test_dynamic_multidimensional_pointer_assignment_checks_each_index(self):
        doc=self.valid('mut i32[2][2] grid=[[1,2],[3,4]]; mut i32[2][2]* pointer=&mut grid; '
                       '(*pointer)[row][column]=9; return grid[0][0];',
                       params='i32 row,i32 column')
        borrow=next(op for op in self.ops(doc,'indexed_field_borrow')
                    if op['attributes']['access']=='MutableExclusive')
        self.assertEqual(len(borrow['attributes']['dimension_bounds_proofs']),2)
        self.assertEqual(len(borrow['attributes']['possible_elements']),4)

    def test_exclusive_whole_array_pointer_moves_and_restores_element(self):
        doc=self.valid('mut i32[2] values=[3,7]; mut i32[2]* pointer=&mut values; '
                       'i32 taken=move (*pointer)[1]; (*pointer)[1]=9; '
                       'return taken+values[1];')
        move=self.ops(doc,'deref_move')[0]
        self.assertEqual(move['attributes']['target_selection'],'definite')
        self.assertEqual(move['attributes']['validation'],'valid')
        self.assertEqual(self.ops(doc,'deref_assign')[0]['attributes']['validation'],'valid')

    def test_runtime_pointer_element_move_marks_only_possible_candidates(self):
        doc=self.valid('mut i32[2] values=[3,7]; mut i32[2]* pointer=&mut values; '
                       'i32 taken=move (*pointer)[index]; return taken;',params='i32 index')
        move=self.ops(doc,'deref_move')[0]
        self.assertEqual(move['attributes']['target_selection'],'one_of_referents')
        self.assertEqual(len(move['attributes']['referent_states_after']),2)

    def test_shared_whole_array_pointer_cannot_move_an_element(self):
        self.reject('mut i32[2] values=[1,2]; i32[2]* pointer=&values; '
                    'i32 taken=move (*pointer)[0]; return taken;', 'borrow_conflict')

    def test_whole_array_pointer_projects_fields_of_struct_elements(self):
        doc=self.valid('Point[2] points=[Point { x=3 },Point { x=7 }]; '
                       'Point[2]* pointer=&points; return (*pointer)[1].x;',
                       functions='struct Point { i32 x; } ')
        borrow=self.ops(doc,'indexed_field_borrow')[0]
        self.assertEqual(borrow['attributes']['field_suffix'],'x')
        self.assertEqual(borrow['attributes']['target_selection'],'definite')

    def test_exclusive_pointer_can_mutate_and_move_struct_element_fields(self):
        doc=self.valid('mut Point[2] points=[Point { x=3 },Point { x=7 }]; '
                       'mut Point[2]* pointer=&mut points; '
                       'i32 taken=move (*pointer)[1].x; (*pointer)[1].x=9; '
                       'return taken+points[1].x;',functions='struct Point { i32 x; } ')
        moves=self.ops(doc,'deref_move')
        self.assertTrue(any(move['attributes'].get('target_selection')=='definite' for move in moves))
        self.assertEqual(self.ops(doc,'deref_assign')[0]['attributes']['validation'],'valid')


if __name__ == '__main__':
    unittest.main()

import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class MultidimensionalStructArrayTests(unittest.TestCase):
    declaration = 'struct Point { i32 x; i32 y; } '
    values = '[[Point { x=1,y=2 },Point { x=3,y=4 }],[Point { x=5,y=6 },Point { x=7,y=8 }]]'

    def compile(self, body, params=''):
        doc = compile_text('module demo; '+self.declaration+
                           'fn test('+params+'):i32 { '+body+' }')
        validate(doc)
        return doc

    def valid(self, body, params=''):
        doc = self.compile(body, params)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        return doc

    def reject(self, body, code, params=''):
        doc = self.compile(body, params)
        self.assertIn(code, [d['code'] for d in doc['diagnostics']], doc['diagnostics'])
        return doc

    def ops(self, doc, kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind'] == kind]

    def test_literal_nested_construction_and_field_access(self):
        doc = self.valid('Point[2][2] grid='+self.values+'; return grid[1][0].x;')
        self.assertEqual(doc['compilation']['compiler']['support_profile'],
                         'multidimensional-struct-array-milestone')
        self.assertEqual(len(self.ops(doc, 'copy')), 1)
        report = render(doc)
        self.assertIn('multiple fixed-size dimensions', report)
        self.assertIn('struct elements', report)

    def test_partial_field_move_and_restoration(self):
        self.valid('mut Point[2][2] grid='+self.values+'; '
                   'i32 x=move grid[0][0].x; i32 y=grid[0][0].y; '
                   'grid[0][0].x=9; Point restored=grid[0][0]; return x+y+restored.x;')
        self.reject('mut Point[2][2] grid='+self.values+'; '
                    'i32 x=move grid[0][0].x; return grid[0][0].x;', 'use_after_move')

    def test_element_and_row_transfer(self):
        self.valid('mut Point[2][2] grid='+self.values+'; '
                   'Point taken=move grid[0][1]; grid[0][1]=taken; '
                   'Point[2] row=grid[1]; Point copy=row[0]; return copy.x;')
        self.valid('mut Point[2][2] grid='+self.values+'; '
                   'Point[2] row=move grid[0]; grid[0]=row; '
                   'Point[2][2] copy=grid; return copy[0][0].x;')
        self.reject('mut Point[2][2] grid='+self.values+'; '
                    'Point taken=move grid[0][1]; return grid[0][1].x;', 'use_after_move')

    def test_field_borrows_follow_nested_element_disjointness(self):
        self.valid('mut Point[2][2] grid='+self.values+'; '
                   'mut i32* a=&mut grid[0][0].x; mut i32* b=&mut grid[1][0].x; '
                   '*a=10; *b=11; return *a;')
        self.reject('mut Point[2][2] grid='+self.values+'; '
                    'i32* p=&grid[0][0].x; grid[0][0].x=8; return *p;', 'borrow_conflict')

    def test_runtime_whole_struct_candidates(self):
        doc = self.valid('Point[2][2] grid='+self.values+'; '
                         'Point point=grid[row][column]; return point.x;', 'i32 row,i32 column')
        read = self.ops(doc, 'array_read')[0]
        self.assertEqual(len(read['attributes']['dimension_bounds_proofs']), 2)
        self.assertEqual(len(read['attributes']['possible_elements']), 4)

    def test_runtime_field_projection_checks_dimensions_and_candidates(self):
        doc = self.valid('Point[2][2] grid='+self.values+'; return grid[row][column].x;',
                         'i32 row,i32 column')
        read = self.ops(doc, 'array_read')[0]
        self.assertEqual(read['attributes']['projected_field'], 'x')
        self.assertEqual(read['attributes']['dimension_lengths'], [2, 2])
        self.assertEqual(len(read['attributes']['possible_elements']), 4)
        self.valid('mut Point[2][2] grid='+self.values+'; '
                   'grid[row][column].x=9; return grid[0][0].x;', 'i32 row,i32 column')
        self.reject('mut Point[2][2] grid='+self.values+'; '
                    'i32 x=move grid[row][column].x; return grid[0][0].x;',
                    'use_after_move', 'i32 row,i32 column')

    def test_runtime_borrow_and_bounds(self):
        self.valid('mut Point[2][2] grid='+self.values+'; '
                   'mut i32* p=&mut grid[row][column].x; *p=9; return *p;',
                   'i32 row,i32 column')
        doc = self.reject('Point[2][2] grid='+self.values+'; '
                          'return grid[row][2].x;', 'index_out_of_bounds', 'i32 row')
        self.assertEqual(len(self.ops(doc, 'array_bounds')), 2)

    def test_multidimensional_struct_arrays_in_struct_fields(self):
        source = ('module demo; '+self.declaration+
                  'struct Board { Point[2][2] points; i32 tag; } '
                  'fn test():i32 { Board b=Board { points='+self.values+',tag=7 }; '
                  'return b.points[1][1].y; }')
        doc = compile_text(source)
        validate(doc)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])

    def test_report_is_deterministic(self):
        source = 'Point[2][2] grid='+self.values+'; return grid[0][1].y;'
        self.assertEqual(dumps(self.compile(source)), dumps(self.compile(source)))


if __name__ == '__main__':
    unittest.main()

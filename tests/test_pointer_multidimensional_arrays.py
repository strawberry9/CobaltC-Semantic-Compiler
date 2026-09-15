import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class PointerMultidimensionalArrayTests(unittest.TestCase):
    scalar_decl = 'struct Data { i32[2][2] grid; i32 tag; } '
    scalar_init = 'Data { grid=[[1,2],[3,4]],tag=7 }'
    struct_decl = 'struct Point { i32 x; i32 y; } struct Data { Point[2][2] points; i32 tag; } '
    struct_init = ('Data { points=[[Point { x=1,y=2 },Point { x=3,y=4 }],'
                   '[Point { x=5,y=6 },Point { x=7,y=8 }]],tag=7 }')

    def compile(self, body, params='i32 row,i32 column', declaration=None, prefix=None, functions=''):
        declaration=declaration or self.scalar_decl
        prefix=prefix or 'mut Data data='+self.scalar_init+'; mut Data* ptr=&mut data; '
        doc=compile_text('module demo; '+declaration+functions+
                         ' fn test('+params+'):i32 { '+prefix+body+' }')
        validate(doc)
        return doc

    def valid(self, body, **kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc

    def reject(self, body, code, **kwargs):
        doc=self.compile(body,**kwargs)
        self.assertIn(code,[d['code'] for d in doc['diagnostics']],doc['diagnostics'])
        return doc

    def ops(self, doc, kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind']==kind]

    def test_runtime_read_write_and_mixed_known_indices(self):
        doc=self.valid('ptr->grid[row][column]=9; return ptr->grid[0][column];')
        self.assertEqual(len(self.ops(doc,'array_bounds')),4)
        self.assertEqual(len(self.ops(doc,'indexed_field_borrow')),2)
        op=self.ops(doc,'indexed_field_borrow')[0]
        self.assertEqual(op['attributes']['dimension_lengths'],[2,2])
        self.assertEqual(len(op['attributes']['possible_elements']),4)
        self.assertIn('every dimension is bounds checked',render(doc))
        self.valid('i32[2] selected=ptr->grid[row]; return selected[column];')

    def test_mutable_borrows_track_nested_disjointness(self):
        self.valid('mut i32* first=&mut ptr->grid[0][column]; '
                   'mut i32* second=&mut ptr->grid[1][column]; '
                   '*first=8; *second=9; return *first;')
        self.reject('i32* item=&ptr->grid[row][column]; ptr->grid[0][0]=9; return *item;',
                    'borrow_conflict')

    def test_shared_pointer_cannot_write_any_nested_element(self):
        prefix='Data data='+self.scalar_init+'; Data* ptr=&data; '
        self.valid('return ptr->grid[row][column];',prefix=prefix)
        self.reject('ptr->grid[row][column]=9; return 0;','borrow_conflict',prefix=prefix)
        self.reject('mut i32* item=&mut ptr->grid[row][column]; return 0;',
                    'borrow_conflict',prefix=prefix)

    def test_struct_element_copy_and_borrow(self):
        doc=self.valid('Point point=ptr->points[row][column]; return point.x;',
                       declaration=self.struct_decl,prefix='mut Data data='+self.struct_init+'; mut Data* ptr=&mut data; ')
        borrow=self.ops(doc,'indexed_field_borrow')[0]
        self.assertEqual(len(borrow['attributes']['possible_elements']),4)
        self.valid('return ptr->points[row][column].x;',declaration=self.struct_decl,
                   prefix='mut Data data='+self.struct_init+'; mut Data* ptr=&mut data; ')
        doc=self.valid('ptr->points[row][column].x=9; '
                       'mut i32* field=&mut ptr->points[row][column].y; *field=10; '
                       'return ptr->points[row][column].x;',declaration=self.struct_decl,
                       prefix='mut Data data='+self.struct_init+'; mut Data* ptr=&mut data; ')
        field_borrow=next(op for op in self.ops(doc,'indexed_field_borrow')
                          if op['attributes'].get('field_suffix')=='y')
        self.assertEqual(field_borrow['attributes']['field'],'points')
        self.assertEqual(len(field_borrow['attributes']['possible_elements']),4)
        self.assertIn('.y',render(doc))
        self.valid('mut Point* point=&mut ptr->points[row][column]; '
                   'point->x=9; return point->x;',declaration=self.struct_decl,
                   prefix='mut Data data='+self.struct_init+'; mut Data* ptr=&mut data; ')

    def test_nested_struct_field_paths_and_parent_permissions(self):
        decl='struct Inner { i32[2][2] cells; } struct Outer { Inner inner; } '
        prefix='mut Outer outer=Outer { inner=Inner { cells=[[1,2],[3,4]] } }; mut Outer* ptr=&mut outer; '
        self.valid('return ptr->inner.cells[row][column];',declaration=decl,prefix=prefix)
        shared=prefix.replace('mut Outer* ptr=&mut outer','Outer* ptr=&outer')
        self.reject('ptr->inner.cells[0][1]=9; return 0;', 'borrow_conflict',declaration=decl,prefix=shared)

    def test_bounds_fail_at_each_dimension(self):
        for body in ('i32 bad=2; return ptr->grid[bad][column];',
                     'i32 bad=2; return ptr->grid[row][bad];'):
            with self.subTest(body=body):
                doc=self.reject(body,'index_out_of_bounds')
                self.assertEqual(len(self.ops(doc,'array_bounds')),2)

    def test_each_index_evaluates_once_in_order(self):
        helpers='fn first():i32 { return 0; } fn second():i32 { return 1; } '
        doc=self.valid('ptr->grid[first()][second()]=9; return 0;',functions=helpers)
        ops=[op for block in doc['functions'][-1]['blocks'] for op in block['operations']]
        kinds=[op['kind'] for op in ops]
        self.assertEqual([kind for kind in kinds if kind in ('call','array_bounds','deref_assign')],
                         ['call','array_bounds','call','array_bounds','deref_assign'])

    def test_returned_borrow_restricted_and_row_moves_supported(self):
        fn='fn select(mut Data* value,i32 row,i32 column):mut i32* { return &mut value->grid[row][column]; } '
        self.valid('mut i32* item=select(ptr,row,column); *item=9; return *item;',functions=fn)
        self.valid('return move ptr->grid[row][column];')
        self.valid('i32[2] selected=move ptr->grid[row]; ptr->grid[row]=[7,8]; return selected[0];')

    def test_determinism(self):
        body='return ptr->grid[row][column];'
        self.assertEqual(dumps(self.compile(body)),dumps(self.compile(body)))


if __name__=='__main__':
    unittest.main()

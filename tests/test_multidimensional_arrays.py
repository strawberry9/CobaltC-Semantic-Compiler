import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class MultidimensionalArrayTests(unittest.TestCase):
    init='[[1,2,3],[4,5,6]]'
    prefix='mut i32[2][3] grid='+init+'; '
    def compile(self,body,params='',functions='',declaration=None):
        doc=compile_text('module demo; '+(declaration or '')+functions+' fn test('+params+'):i32 { '+body+' }')
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
    def test_nested_construction_shape_and_literal_reads(self):
        doc=self.valid(self.prefix+'return grid[1][2];')
        self.assertEqual(len(self.ops(doc,'copy')),1)
        self.assertEqual(self.ops(doc,'array_read'),[])
        self.assertEqual(doc['compilation']['compiler']['support_profile'],'multidimensional-array-milestone')
        typ=next(t for t in doc['types'] if t['name']=='i32[2][3]')
        inner=next(t for t in doc['types'] if t['id']==typ['args'][0])
        self.assertEqual(inner['name'],'i32[3]')
    def test_nested_initialization_and_shape_mismatch(self):
        self.valid('i32[2][2] grid=[[1,2],[3,4]]; return grid[0][1];')
        self.reject('i32[2][2] grid=[[1],[2,3]]; return 0;','array_length_mismatch')
        self.reject('i32[2][2] grid=[[1,2],[true,4]]; return 0;','type_error')
    def test_nested_partial_initialization_and_whole_copy(self):
        self.valid('mut i32[2][2] grid; grid[0][0]=1; grid[0][1]=2; grid[1][0]=3; grid[1][1]=4; i32[2][2] copy=grid; return copy[1][1];')
        self.reject('mut i32[2][2] grid; grid[0][0]=1; grid[0][1]=2; grid[1][0]=3; i32[2][2] copy=grid; return 0;','uninitialized_read')
        self.reject('mut i32[2][2] grid; grid[0][0]=1; i32[2] row=grid[0]; return 0;','uninitialized_read')
    def test_row_copy_replacement_and_identity(self):
        doc=self.valid(self.prefix+'mut i32[3] row=grid[0]; row[0]=9; grid[1]=row; return grid[0][0]+grid[1][0];')
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],10)
        self.valid('mut i32[2][2] grid; grid[0]=[1,2]; grid[1]=[3,4]; return grid[1][1];')
    def test_element_and_row_moves_restore(self):
        self.valid(self.prefix+'i32 value=move grid[0][0]; i32 sibling=grid[0][1]; grid[0][0]=9; i32[2][3] copy=grid; return value+sibling;')
        self.reject(self.prefix+'i32 value=move grid[0][0]; i32[3] row=grid[0]; return 0;','use_after_move')
        self.reject(self.prefix+'i32[3] row=move grid[0]; return grid[0][0];','use_after_move')
        self.valid(self.prefix+'i32[3] row=move grid[0]; grid[0]=row; i32[2][3] copy=grid; return copy[0][0];')
    def test_borrows_and_nested_disjointness(self):
        self.valid(self.prefix+'mut i32* first=&mut grid[0][0]; mut i32* second=&mut grid[1][0]; *first=9; *second=8; return *first;')
        self.valid(self.prefix+'mut i32* first=&mut grid[0][0]; grid[0][1]=9; return *first;')
        self.reject(self.prefix+'i32* first=&grid[0][1]; grid[0]=[7,8,9]; return *first;','borrow_conflict')
        self.reject(self.prefix+'i32* row=&grid[0][0]; i32[3] taken=move grid[0]; return *row;','borrow_conflict')
    def test_bounds_zero_and_negative(self):
        self.reject(self.prefix+'return grid[2][0];','index_out_of_bounds')
        self.reject(self.prefix+'return grid[0][3];','index_out_of_bounds')
        self.reject(self.prefix+'return grid[-1][0];','index_out_of_bounds')
        self.reject('i32[2][0] grid=[[],[]]; return grid[0][0];','index_out_of_bounds')
        self.reject('i32[0][2] grid=[]; return grid[0][0];','index_out_of_bounds')
    def test_element_types_and_lengths(self):
        self.valid('bool[2][1] flags=[[true],[false]]; if(flags[1][0]) { return 1; } return 0;')
        self.reject('i32[2][257] grid; return 0;','unsupported_array_length')
        self.reject('i32[17][16] grid; return 0;','unsupported_array_size')
        self.valid('Point[2][2] grid; return 0;',declaration='struct Point { i32 x; } ')
    def test_array_in_struct_and_nested_struct_array(self):
        decl='struct Grid { i32[2][2] cells; i32 tag; } '
        self.valid('mut Grid grid=Grid { cells=[[1,2],[3,4]],tag=7 }; grid.cells[0][1]=9; return grid.cells[0][1];',declaration=decl)
        self.valid('mut Grid[1] grids=[Grid { cells=[[1,2],[3,4]],tag=7 }]; grids[0].cells[1][1]=9; return grids[0].cells[1][1];',declaration=decl)
    def test_by_value_calls_returns_and_cleanup(self):
        functions='fn identity(i32[2][3] values):i32[2][3] { return move values; } '
        self.valid(self.prefix+'i32[2][3] copy=identity(grid); i32[2][3] moved=identity(move grid); return moved[0][0]+copy[0][0];',functions=functions)
        doc=self.valid(self.prefix+'return grid[1][2];')
        self.assertEqual(len(self.ops(doc,'destroy')),6)
    def test_defer_branches_and_determinism(self):
        self.reject(self.prefix+'defer { grid[0][0]; }; i32 value=move grid[0][0]; return value;','use_after_move')
        self.reject(self.prefix+'if(flag) { i32 value=move grid[0][0]; } return grid[0][0];','use_after_move',params='bool flag')
        body=self.prefix+'return grid[0][0];'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('Nested fixed-size arrays',render(doc))
    def test_runtime_indices_all_dimension_combinations(self):
        for indices,count in [('row][column',6),('row][1',2),('0][column',3),('0][1',1)]:
            body='mut i32[2][3] grid='+self.init+'; return grid['+indices+'];'
            doc=self.valid(body,params='i32 row,i32 column')
            if count==1:
                self.assertEqual(self.ops(doc,'array_read'),[])
                continue
            read=self.ops(doc,'array_read')[0]
            self.assertEqual(len(read['attributes']['possible_elements']),count)
            self.assertEqual(read['attributes']['dimension_lengths'],[2,3])
            self.assertEqual(len(read['attributes']['dimension_bounds_proofs']),2)
    def test_runtime_assign_and_partial_initialization(self):
        self.valid('mut i32[2][3] grid; grid[0]=[1,2,3]; grid[1]=[4,5,6]; i32[2][3] copy=grid; return copy[1][2];')
        self.reject('mut i32[2][3] grid; grid[row][column]=7; i32 value=grid[0][0]; return 0;','uninitialized_read',params='i32 row,i32 column')
        self.reject('mut i32[2][3] grid; grid[row][column]=7; i32[2][3] copy=grid; return 0;','uninitialized_read',params='i32 row,i32 column')
    def test_runtime_move_and_conservative_restoration(self):
        prefix='mut i32[2][3] grid='+self.init+'; i32 value=move grid[0][column]; '
        self.valid(prefix+'return grid[1][0];',params='i32 row,i32 column')
        self.reject(prefix+'return grid[0][0];','use_after_move',params='i32 row,i32 column')
        self.reject(prefix+'grid[row][column]=9; i32[2][3] copy=grid; return 0;','use_after_move',params='i32 row,i32 column')
        self.valid(prefix+'grid[0]=[7,8,9]; grid[1]=[7,8,9]; i32[2][3] copy=grid; return copy[0][0];',params='i32 row,i32 column')
    def test_inner_borrows_and_candidate_overlap(self):
        self.valid('mut i32[2][3] grid='+self.init+'; mut i32* first=&mut grid[0][column]; mut i32* second=&mut grid[1][column]; *first=7; *second=8; return *first;',params='i32 column')
        self.valid('mut i32[2][3] grid='+self.init+'; mut i32* first=&mut grid[row][0]; mut i32* second=&mut grid[row][1]; *first=7; *second=8; return *first;',params='i32 row')
        self.reject('mut i32[2][3] grid='+self.init+'; mut i32* first=&mut grid[row][column]; grid[0][0]=9; return *first;','borrow_conflict',params='i32 row,i32 column')
    def test_bounds_each_dimension_and_abort_edges(self):
        for body in ('i32 r=2; return grid[r][column];','i32 c=3; return grid[row][c];'):
            doc=self.reject('i32[2][3] grid='+self.init+'; '+body,'index_out_of_bounds',params='i32 row,i32 column')
            self.assertEqual(len(self.ops(doc,'array_bounds')),2)
        self.reject('i32[2][0] grid=[[],[]]; return grid[0][column];','index_out_of_bounds',params='i32 column')
        self.reject('i32[0][3] grid=[]; return grid[row][column];','index_out_of_bounds',params='i32 row,i32 column')
    def test_index_and_rhs_evaluation_order(self):
        functions='fn row():i32 { return 0; } fn column():i32 { return 1; } fn rhs():i32 { return 9; } '
        doc=self.valid('mut i32[2][3] grid='+self.init+'; grid[row()][column()]=rhs(); return 0;',functions=functions)
        ops=[o for b in doc['functions'][-1]['blocks'] for o in b['operations']]
        selected=[o['kind'] for o in ops if o['kind'] in ('call','array_bounds','array_assign')]
        self.assertEqual(selected,['call','array_bounds','call','array_bounds','call','array_assign'])
        assign=self.ops(doc,'array_assign')[0]
        self.assertEqual(assign['operands'][-1],assign['operands'][assign['attributes']['value_operand']])
    def test_nested_by_value_signatures_and_return(self):
        functions='fn identity(i32[2][3] value):i32[2][3] { return move value; } fn cell(i32[2][3] value):i32 { return value[1][2]; } '
        self.valid('i32[2][3] grid='+self.init+'; i32[2][3] copy=identity(grid); return cell(copy);',functions=functions)
    def test_defer_and_branch_state_with_runtime_targets(self):
        self.reject('mut i32[2][2] grid=[[1,2],[3,4]]; defer { grid[0][0]; }; i32 value=move grid[row][column]; return value;','use_after_move',params='i32 row,i32 column')
        self.reject('mut i32[2][2] grid=[[1,2],[3,4]]; if(flag) { i32 value=move grid[row][column]; } return grid[0][0];','use_after_move',params='i32 row,i32 column,bool flag')
    def test_nested_array_fields_support_runtime_each_dimension(self):
        decl='struct Grid { i32[2][2] cells; } '
        self.valid('mut Grid grid=Grid { cells=[[1,2],[3,4]] }; grid.cells[row][column]=9; return grid.cells[row][column];',declaration=decl,params='i32 row,i32 column')
    def test_deterministic_nested_runtime_report(self):
        body='mut i32[2][3] grid='+self.init+'; return grid[row][column];'
        doc=self.valid(body,params='i32 row,i32 column')
        self.assertEqual(dumps(doc),dumps(self.compile(body,params='i32 row,i32 column')))
        self.assertIn('each bounds proof',render(doc))
        self.assertIn('each bounds proof',render(doc))

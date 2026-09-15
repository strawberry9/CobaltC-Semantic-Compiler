import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps,validate
from cobalt.explain import render

class ArrayTests(unittest.TestCase):
    def compile(self,body,functions='',params=''):
        return compile_text('module demo; '+functions+' fn test('+params+'):i32 { '+body+' }')
    def valid(self,body,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics']);validate(doc);return doc
    def reject(self,body,code,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertIn(code,[d['code'] for d in doc['diagnostics']],doc['diagnostics']);validate(doc);return doc
    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def test_construction_index_proof_and_constants(self):
        doc=self.valid('i32[3] values=[1,2,3]; return values[0]+values[2];')
        typ=next(t for t in doc['types'] if t['kind']=='array')
        self.assertEqual(typ['name'],'i32[3]')
        self.assertEqual(len(typ['fields']),3)
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],4)
        indexed=[o for o in self.ops(doc,'read') if 'array_index' in o['attributes']]
        self.assertEqual([o['attributes']['array_index'] for o in indexed],[0,2])
        self.assertTrue(all(o['attributes']['bounds_check']=='proven_in_bounds' for o in indexed))
        self.assertEqual(doc['compilation']['compiler']['support_profile'],'scalar-array-milestone')

    def test_length_type_and_bounds_errors(self):
        self.reject('i32[2] values=[1]; return 0;','array_length_mismatch')
        self.reject('i32[1] values=[1,2]; return 0;','array_length_mismatch')
        self.reject('i32[1] values=[true]; return 0;','type_error')
        self.reject('u8[1] values=[256]; return 0;','literal_range')
        for index in ('2','-1'):
            self.reject('i32[2] values=[1,2]; return values['+index+'];','index_out_of_bounds')
        self.reject('i32 value=1; return value[0];','invalid_index')

    def test_partial_initialization_and_mutability(self):
        self.valid('mut i32[2] values; values[0]=1; values[1]=2; i32[2] copied=values; return copied[1];')
        self.reject('mut i32[2] values; values[0]=1; return values[1];','uninitialized_read')
        self.reject('i32[2] values=[1,2]; values[0]=3; return 0;','immutable_assignment')
        self.reject('mut i32[2] values; if(flag) { values[0]=1; } return values[0];','uninitialized_read',params='bool flag')

    def test_copy_independence_move_and_reinitialization(self):
        doc=self.valid('i32[2] source=[1,2]; mut i32[2] copied=source; copied[0]=9; return source[0]+copied[0];')
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],10)
        self.valid('mut i32[2] source=[1,2]; i32[2] moved=move source; source=[3,4]; return source[0]+moved[0];')
        self.reject('i32[2] source=[1,2]; i32[2] moved=move source; return source[0];','use_after_move')

    def test_element_moves_cleanup_and_restoration(self):
        doc=self.valid('i32[2] values=[1,2]; i32 taken=move values[0]; return values[1];')
        self.assertEqual(sum(not o['attributes']['executes_if_initialized'] for o in self.ops(doc,'destroy')),1)
        self.reject('i32[2] values=[1,2]; i32 taken=move values[0]; i32[2] copied=values; return 0;','use_after_move')
        self.valid('mut i32[2] values=[1,2]; i32 taken=move values[0]; values[0]=3; i32[2] copied=values; return copied[0];')

    def test_disjoint_element_borrows_and_overlap(self):
        self.valid('mut i32[2] values=[1,2]; mut i32* first=&mut values[0]; mut i32* second=&mut values[1]; *first=7; *second=8; return *first+*second;')
        self.reject('mut i32[2] values=[1,2]; i32* first=&values[0]; values[0]=9; return *first;','borrow_conflict')
        self.reject('mut i32[2] values=[1,2]; i32* first=&values[0]; values=[7,8]; return *first;','borrow_conflict')
        self.valid('mut i32[2] values=[1,2]; i32* first=&values[0]; i32 result=*first; values=[7,8]; return result;')

    def test_by_value_parameters_returns_and_zero_length(self):
        self.valid('i32[2] values=identity([1,2]); return values[1];',functions='fn identity(i32[2] values):i32[2] { return move values; }')
        self.valid('i32[0] empty=[]; i32[0] copied=empty; return 0;')
        self.reject('i32[0] empty=[]; return empty[0];','index_out_of_bounds')
        self.reject('i32[2] values=[1,2]; i32[3] copied=values; return 0;','type_error')

    def test_initializer_evaluation_order_and_replacement_rollback(self):
        self.reject('i32 value=1; i32[2] values=[move value,value]; return 0;','use_after_move')
        self.valid('i32 value=1; i32[2] values=[value,move value]; return values[0];')
        doc=self.reject('mut i32[2] values=[1,2]; values=[3]; return values[0];','array_length_mismatch')
        self.assertEqual(self.ops(doc,'assign')[0]['effects'],{})
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],1)

    def test_supported_scalar_element_types(self):
        self.valid('bool[2] flags=[true,false]; char[1] letters=[\'a\']; u8[1] bytes=[255]; if(flags[0]) { return 1; } return 0;')

    def test_defer_and_returned_element_borrow_lifetime(self):
        self.valid('mut i32[2] values=[1,2]; defer { values[1]; }; i32 taken=move values[0]; return taken;')
        self.reject('i32[2] values=[1,2]; defer { values[0]; }; i32 taken=move values[0]; return 0;','use_after_move')
        self.reject('return 0;','lifetime_violation',functions='fn bad(i32[2] values):i32* { return &values[0]; }')

    def test_explicit_boundaries(self):
        self.valid('i32[2] values=[1,2]; i32 index=0; i32 taken=move values[index]; return taken;')
        self.reject('i32[4097] values; return 0;','unsupported_array_length')
        self.valid('i32[2] values=[1,2]; i32[2]* pointer=&values; i32[2] copied=*pointer; return copied[0];')
        self.valid('Point[1] values=[Point { x=7 }]; return values[0].x;',functions='struct Point { i32 x; }')

    def test_deterministic_report(self):
        body='i32[2] values=[1,2]; return values[0];'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('proven in bounds',render(doc))

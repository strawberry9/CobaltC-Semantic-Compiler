import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class NestedRuntimeIndexTests(unittest.TestCase):
    prefix='mut Data[2] data=[Data { values=[1,2],tag=3 },Data { values=[4,5],tag=6 }]; '
    def compile(self,body,params='i32 index,i32 item',functions='',declaration=None):
        doc=compile_text('module demo; '+(declaration or 'struct Data { i32[2] values; i32 tag; } ')+functions+' fn test('+params+'):i32 { '+body+' }')
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
    def test_unknown_and_known_candidate_sets(self):
        for outer,inner,count in [('index','item',4),('index','0',2),('chosen','item',2),('chosen','0',1)]:
            doc=self.valid(self.prefix+f'i32 chosen=0; return data[{outer}].values[{inner}];')
            read=self.ops(doc,'array_read')[0]
            self.assertEqual(len(read['attributes']['possible_elements']),count)
            self.assertIn(read['attributes']['inner_bounds_proof'],read['operands'])
    def test_write_and_singleton_initialization(self):
        doc=self.valid(self.prefix+'i32 chosen=0; data[chosen].values[0]=9; return data[0].values[0];')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],9)
        self.reject('mut Data[2] data; data[index].values[item]=9; return data[0].values[0];','uninitialized_read')
        self.valid('mut Data[1] data; data[index].values[item]=9; return data[0].values[0];',declaration='struct Data { i32[1] values; } ')
    def test_partial_sibling_availability(self):
        self.valid('mut Data[2] data; data[0].values[0]=1; data[1].values[0]=2; return data[index].values[0];')
        self.reject('mut Data[2] data; data[0].values[0]=1; data[1].values[0]=2; return data[index].values[item];','uninitialized_read')
    def test_moves_and_restoration(self):
        prefix=self.prefix+'i32 taken=move data[index].values[item]; '
        self.valid(prefix+'return data[index].tag;')
        self.reject(prefix+'return data[0].values[0];','use_after_move')
        self.reject(prefix+'data[index].values[item]=7; Data[2] copied=data; return 0;','use_after_move')
        self.valid(prefix+'data[0].values=[7,8]; data[1].values=[9,10]; Data[2] copied=data; return copied[0].tag;')
        doc=self.valid(prefix+'return taken;')
        self.assertEqual(len(self.ops(doc,'array_move')[0]['attributes']['possible_elements']),4)
        self.assertEqual(sum('Moved' in o['attributes']['state_before']['initialization'] for o in self.ops(doc,'destroy')),4)
    def test_borrow_overlap_and_disjoint_columns(self):
        self.valid(self.prefix+'mut i32* ptr=&mut data[index].values[0]; data[index].values[1]=9; data[index].tag=7; return *ptr;')
        self.reject(self.prefix+'i32* ptr=&data[index].values[item]; data[0].values[0]=9; return *ptr;','borrow_conflict')
        self.reject(self.prefix+'i32* ptr=&data[index].values[item]; data[index].values=[7,8]; return *ptr;','borrow_conflict')
    def test_bounds_and_index_types(self):
        for body in ('i32 chosen=2; return data[chosen].values[item];','return data[index].values[2];','return data[index].values[-1];'):
            self.reject(self.prefix+body,'index_out_of_bounds')
        self.reject(self.prefix+'return data[index].values[true];','type_error')
        self.reject('Data[1] data=[Data { values=[] }]; return data[index].values[item];','index_out_of_bounds',declaration='struct Data { i32[0] values; } ')
    def test_evaluation_order_and_rhs_rollback(self):
        funcs='fn outer():i32 { return 0; } fn inner():i32 { return 0; } fn rhs():i32 { return 9; } '
        doc=self.valid(self.prefix+'data[outer()].values[inner()]=rhs(); return 0;',functions=funcs)
        ops=[o for b in doc['functions'][-1]['blocks'] for o in b['operations']]
        self.assertEqual([o['kind'] for o in ops if o['kind'] in ('call','array_bounds','array_assign')],['call','array_bounds','call','array_bounds','call','array_assign'])
        doc=self.reject(self.prefix+'data[index].values[item]=true; return 0;','type_error')
        assign=self.ops(doc,'array_assign')[0]
        self.assertEqual(assign['effects'],{})
        self.assertEqual(assign['attributes']['element_states_before'],assign['attributes']['element_states_after'])
    def test_returned_borrow_and_defer(self):
        self.valid(self.prefix+'i32* ptr=identity(&data[index].values[item]); return *ptr;',functions='fn identity(i32* ptr):i32* { return ptr; } ')
        self.reject('return 0;','lifetime_violation',functions='fn bad(Data[2] data,i32 index,i32 item):i32* { return &data[index].values[item]; } ')
        self.reject(self.prefix+'defer { data[0].values[0]; }; return move data[index].values[item];','use_after_move')
    def test_nested_struct_path_and_determinism(self):
        decl='struct Inner { i32[2] values; } struct Data { Inner inner; } '
        body='mut Data[1] data=[Data { inner=Inner { values=[1,2] } }]; return data[index].inner.values[item];'
        doc=self.valid(body,declaration=decl)
        self.assertEqual(dumps(doc),dumps(self.compile(body,declaration=decl)))
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['projected_field'],'inner.values')

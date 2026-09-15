import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate, dumps
from cobalt.explain import render

class PointerArrayFieldTests(unittest.TestCase):
    def compile(self,body,functions='',params='i32 index'):
        doc=compile_text('module demo; struct Data { i32[2] values; i32 tag; } '+functions+' fn test('+params+'):i32 { '+body+' }')
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
    prefix='mut Data data=Data { values=[1,2], tag=3 }; mut Data* ptr=&mut data; '
    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]
    def test_reads_and_writes(self):
        for index in ('0','index'):
            self.valid(self.prefix+f'ptr->values[{index}]=7; return ptr->values[{index}];')
        self.valid(self.prefix+'(*ptr).values[0]=7; return (*ptr).values[0];')
    def test_shared_mutability(self):
        prefix='Data data=Data { values=[1,2], tag=3 }; Data* ptr=&data; '
        self.valid(prefix+'return ptr->values[index];')
        self.reject(prefix+'ptr->values[index]=7; return 0;','borrow_conflict')
        self.reject(prefix+'mut i32* item=&mut ptr->values[index]; return 0;','borrow_conflict')
    def test_disjoint_and_overlapping_borrows(self):
        self.valid(self.prefix+'i32* item=&ptr->values[0]; ptr->values[1]=9; return *item;')
        self.valid(self.prefix+'i32* item=&ptr->values[index]; ptr->tag=9; return *item;')
        self.reject(self.prefix+'i32* item=&ptr->values[index]; ptr->values[0]=9; return *item;','borrow_conflict')
        self.valid(self.prefix+'mut i32* item=&mut ptr->values[index]; *item=9; i32 saved=*item; return ptr->values[0];')
    def test_bounds_and_moves(self):
        self.reject(self.prefix+'return ptr->values[2];','index_out_of_bounds')
        self.reject(self.prefix+'return ptr->values[-1];','index_out_of_bounds')
        self.reject(self.prefix+'return ptr->values[true];','type_error')
        doc=self.valid(self.prefix+'return move ptr->values[index];')
        self.assertEqual(self.ops(doc,'deref_move')[0]['attributes']['validation'],'valid')
    def test_returned_element_borrow(self):
        functions='fn select(Data* value,i32 index):i32* { return &value->values[index]; } '
        self.valid('Data data=Data { values=[1,2], tag=3 }; i32* item=select(&data,index); return *item;',functions=functions)
        doc=self.compile('Data data=Data { values=[1,2], tag=3 }; return 0;',functions='fn bad():i32* { Data data=Data { values=[1,2], tag=3 }; Data* ptr=&data; return &ptr->values[0]; } ')
        self.assertNotEqual(doc['compilation']['result'],'valid')
    def test_conditional_write_constants(self):
        doc=self.valid(self.prefix+'ptr->values[index]=9; return data.values[0];')
        reads=self.ops(doc,'copy')
        self.assertNotIn('constant_value',reads[-1]['attributes'])
    def test_defer_conflict(self):
        self.reject(self.prefix+'i32* item=&ptr->values[index]; defer { *item; }; ptr->values[0]=9; return 0;','borrow_conflict')
    def test_determinism_and_alternatives(self):
        body=self.prefix+'return ptr->values[index];'
        doc=self.valid(body)
        op=self.ops(doc,'indexed_field_borrow')[0]
        self.assertEqual(len(op['attributes']['capability_alternatives']),2)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
    def test_nested_field_and_mutable_return(self):
        doc=compile_text('module demo; struct Inner { i32[2] values; } struct Outer { Inner inner; } fn select(mut Outer* ptr,i32 index):mut i32* { return &mut ptr->inner.values[index]; } fn test(i32 index):i32 { mut Outer outer=Outer { inner=Inner { values=[1,2] } }; mut i32* item=select(&mut outer,index); *item=7; return *item; }')
        validate(doc)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
    def test_index_evaluated_once_and_failure_rollback(self):
        doc=self.valid(self.prefix+'ptr->values[next()]=7; return 0;',functions='fn next():i32 { return 0; } ')
        self.assertEqual(len(self.ops(doc,'call')),1)
        doc=self.reject(self.prefix+'i32* item=&ptr->values[index]; ptr->values[0]=9; return *item;','borrow_conflict')
        failed=[o for o in self.ops(doc,'indexed_field_borrow') if o['attributes'].get('validation')=='invalid']
        self.assertTrue(failed)
        self.assertTrue(all(not o['attributes'].get('created_capabilities') for o in failed))

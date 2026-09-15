import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class PointerArrayValueTests(unittest.TestCase):
    prefix='mut Data data=Data { values=[1,2], tag=3 }; mut Data* ptr=&mut data; '
    def compile(self,body,functions='',params=''):
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
    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]
    def test_copy_independent_and_source_retained(self):
        doc=self.valid(self.prefix+'mut i32[2] values=ptr->values; values[0]=9; return data.values[0];')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],1)
        read=self.ops(doc,'deref_read')[0]
        self.assertEqual(read['attributes']['result_ownership'],'Owned')
        before=read['attributes']['referent_states_before']
        objects={obj for root in before.values() for field in root['fields'].values() for obj in field['object_identities']}
        copied={obj for field in read['attributes']['result_field_states'].values() for obj in field['object_identities']}
        self.assertTrue(objects.isdisjoint(copied))
    def test_replacement_and_self_copy(self):
        doc=self.valid(self.prefix+'ptr->values=[7,8]; ptr->values=ptr->values; return data.values[0];')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],7)
        for op in self.ops(doc,'deref_assign'):
            self.assertEqual(len(op['effects']['destruction']),2)
    def test_shared_parent_permissions(self):
        prefix='Data data=Data { values=[1,2], tag=3 }; Data* ptr=&data; '
        self.valid(prefix+'i32[2] values=ptr->values; return values[1];')
        self.reject(prefix+'ptr->values=[7,8]; return 0;','borrow_conflict')
    def test_element_overlap_and_disjoint_sibling(self):
        self.reject(self.prefix+'i32* item=&ptr->values[0]; ptr->values=[7,8]; return *item;','borrow_conflict')
        self.reject(self.prefix+'mut i32* item=&mut ptr->values[0]; i32[2] values=ptr->values; return *item;','borrow_conflict')
        self.valid(self.prefix+'i32* tag=&ptr->tag; ptr->values=[7,8]; return *tag;')
    def test_failed_rhs_preserves_array(self):
        doc=self.reject(self.prefix+'ptr->values=[true,false]; return data.values[0];','type_error')
        op=self.ops(doc,'deref_assign')[0]
        self.assertEqual(op['effects'],{})
        self.assertEqual(op['attributes']['referent_states_before'],op['attributes']['referent_states_after'])
    def test_calls_and_returns(self):
        functions='fn values(Data* ptr):i32[2] { return ptr->values; } fn first(i32[2] values):i32 { return values[0]; } '
        self.valid(self.prefix+'i32[2] copied=values(ptr); return first(ptr->values);',functions=functions)
    def test_explicit_array_borrow_and_whole_array_move_supported(self):
        self.valid(self.prefix+'i32[2]* values=&ptr->values; i32[2] copied=*values; return copied[0];')
        self.valid(self.prefix+'mut i32[2]* values=&mut ptr->values; *values=[7,8]; return data.values[0];')
        self.valid(self.prefix+'i32[2] values=move ptr->values; return values[0];')
    def test_nested_empty_arrays_and_defer(self):
        doc=compile_text('module demo; struct Inner { i32[0] values; } struct Outer { Inner inner; } fn test():void { mut Outer outer=Outer { inner=Inner { values=[] } }; mut Outer* ptr=&mut outer; ptr->inner.values=[]; i32[0] values=ptr->inner.values; defer { ptr->inner.values=[]; }; }')
        validate(doc)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
    def test_alternative_parent_preserves_possible_old_values(self):
        functions='fn select(bool flag,mut Data* first,mut Data* second):mut Data* { if(flag) { return move first; } return move second; } '
        doc=self.valid('mut Data first=Data { values=[1,2], tag=3 }; mut Data second=Data { values=[4,5], tag=6 }; mut Data* ptr=select(flag,&mut first,&mut second); ptr->values=[7,8]; return first.values[0];',functions=functions,params='bool flag')
        op=self.ops(doc,'deref_assign')[0]
        self.assertEqual(op['attributes']['target_selection'],'one_of_referents')
        self.assertNotIn('constant_value',self.ops(doc,'copy')[-1]['attributes'])
    def test_deterministic_report(self):
        body=self.prefix+'ptr->values=[7,8]; i32[2] values=ptr->values; return values[0];'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('whole array',render(doc))

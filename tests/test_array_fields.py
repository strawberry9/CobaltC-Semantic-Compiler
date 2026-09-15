import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class ArrayFieldTests(unittest.TestCase):
    declaration='struct Data { i32[2] values; i32 tag; } '
    initial='Data { values=[1,2], tag=3 }'

    def compile(self,body,params='i32 index',functions='',declaration=None):
        doc=compile_text('module demo; '+(declaration or self.declaration)+functions+' fn test('+params+'):i32 { '+body+' }')
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

    def test_construction_and_reads(self):
        for index in ('0','index'):
            self.valid('Data data='+self.initial+'; return data.values['+index+'];')

    def test_partial_initialization_and_restoration(self):
        self.valid('mut Data data; data.values[0]=7; data.values[1]=8; data.tag=9; Data copy=data; return copy.values[0];')
        self.reject('mut Data data; data.values[0]=7; data.tag=9; Data copy=data; return 0;','uninitialized_read')

    def test_literal_move_leaves_siblings_available(self):
        self.valid('Data data='+self.initial+'; i32 taken=move data.values[0]; return data.values[1]+data.tag;')
        self.reject('Data data='+self.initial+'; i32 taken=move data.values[0]; Data copy=data; return 0;','use_after_move')

    def test_runtime_move_and_ancestor_restoration(self):
        prefix='mut Data data='+self.initial+'; i32 taken=move data.values[index]; '
        self.valid(prefix+'return data.tag;')
        self.reject(prefix+'Data copy=data; return 0;','use_after_move')
        self.valid(prefix+'data.values=[7,8]; Data copy=data; return copy.values[0];')

    def test_runtime_write_does_not_initialize_every_element(self):
        self.reject('mut Data data; data.values[index]=7; data.tag=9; Data copy=data; return 0;','uninitialized_read')

    def test_borrows_disjoint_and_overlapping(self):
        prefix='mut Data data='+self.initial+'; '
        self.valid(prefix+'mut i32* ptr=&mut data.values[index]; data.tag=7; return *ptr;')
        self.valid(prefix+'i32* ptr=&data.values[0]; data.values[1]=7; return *ptr;')
        self.reject(prefix+'i32* ptr=&data.values[index]; data.values[0]=7; return *ptr;','borrow_conflict')
        self.reject(prefix+'i32* ptr=&data.values[index]; data='+self.initial+'; return *ptr;','borrow_conflict')

    def test_immutable_array_field(self):
        self.reject('Data data='+self.initial+'; data.values[index]=7; return 0;','immutable_assignment')

    def test_nested_struct_and_by_value_calls(self):
        declaration=self.declaration+'struct Outer { Data data; } '
        functions='fn identity(Outer value):Outer { return move value; } '
        self.valid('Outer outer=identity(Outer { data='+self.initial+' }); return outer.data.values[index];',declaration=declaration,functions=functions)

    def test_whole_array_field_copy_and_move(self):
        self.valid('mut Data data='+self.initial+'; i32[2] values=move data.values; data.values=[7,8]; Data copy=data; return values[0]+copy.values[1];')

    def test_cleanup_has_scalar_leaves_only(self):
        doc=self.valid('Data data='+self.initial+'; return data.tag;')
        destroys=self.ops(doc,'destroy')
        # Three owned scalar leaves plus the index parameter.
        self.assertEqual(len(destroys),4)
        self.assertTrue(all(o['attributes']['guard']=='initialized_and_owned' for o in destroys))

    def test_defer_and_branch_joins(self):
        self.reject('Data data='+self.initial+'; defer { data.values[0]; }; return move data.values[index];','use_after_move')
        self.reject('mut Data data; if(flag) { data.values=[1,2]; } data.tag=3; return data.values[0];','uninitialized_read',params='bool flag')

    def test_empty_array_field(self):
        self.valid('Empty data=Empty { values=[], tag=7 }; Empty copy=data; return copy.tag;',declaration='struct Empty { i32[0] values; i32 tag; }')

    def test_pointer_to_containing_struct(self):
        self.valid('Data data='+self.initial+'; Data* ptr=&data; Data copy=*ptr; return copy.values[index];')
        self.valid('Data data='+self.initial+'; Data* ptr=&data; i32[2] copy=ptr->values; return copy[0];')

    def test_invalid_array_field_type_and_length(self):
        for typ,code in [('i32[257]','unsupported_array_length'),('Data[2]','unsupported_recursive_struct')]:
            self.reject('return 0;',code,declaration='struct Data { '+typ+' values; }')

    def test_deterministic_report(self):
        body='Data data='+self.initial+'; return data.values[index];'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('Fixed-size arrays',render(doc))

import unittest

from cobalt.driver import compile_text
from cobalt.esir import validate


class TemporaryBorrowTests(unittest.TestCase):
    def compile(self, body, *, declarations='', factory='', functions='', params=''):
        source='module demo; '+declarations+factory+functions+f'fn test({params}):i32 {{ {body} }}'
        doc=compile_text(source);validate(doc);return doc

    def valid(self, body, **kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc

    def reject(self, body, code, **kwargs):
        doc=self.compile(body,**kwargs)
        self.assertIn(code,[diag['code'] for diag in doc['diagnostics']],doc['diagnostics'])
        return doc

    def ops(self,doc,kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind']==kind]

    def test_shared_borrow_of_temporary_array_element_lives_through_call(self):
        factory='fn make():i32[2] { return [4,7]; } '
        functions='fn get(i32* value):i32 { return *value; } '
        doc=self.valid('return get(&make()[1]);',factory=factory,functions=functions)
        borrow=self.ops(doc,'borrow_shared')[0]
        call=self.ops(doc,'call')[-1]
        end=self.ops(doc,'temporary_end')[0]
        fn=doc['functions'][-1]
        operations=[op for block in fn['blocks'] for op in block['operations']]
        self.assertLess(operations.index(borrow),operations.index(call))
        self.assertLess(operations.index(call),operations.index(end))
        self.assertEqual(end['attributes']['validation'],'valid')
        self.assertIn('destruction',end['effects'])

    def test_mutable_borrow_can_update_temporary_field_before_cleanup(self):
        declarations='struct Point { i32 x; i32 y; } '
        factory='fn make():Point { return Point { x=4,y=7 }; } '
        functions='fn set(mut i32* value) { *value=9; } '
        doc=self.valid('set(&mut make().x); return 0;',declarations=declarations,factory=factory,functions=functions)
        self.assertEqual(self.ops(doc,'borrow_mut')[0]['attributes']['access'],'MutableExclusive')
        self.assertEqual(self.ops(doc,'deref_assign')[0]['attributes']['validation'],'valid')
        self.assertEqual(self.ops(doc,'temporary_end')[0]['attributes']['validation'],'valid')

    def test_temporary_borrow_lifetime_extends_across_nested_call_arguments(self):
        factory='fn make():i32[1] { return [5]; } '
        functions=('fn identity(i32* value):i32* { return value; } '
                   'fn get(i32* value):i32 { return *value; } ')
        doc=self.valid('return get(identity(&make()[0]));',factory=factory,functions=functions)
        calls=self.ops(doc,'call')
        self.assertEqual(len(calls),3) # make, identity, get
        end=self.ops(doc,'temporary_end')[0]
        fn=doc['functions'][-1]
        operations=[op for block in fn['blocks'] for op in block['operations']]
        self.assertGreater(operations.index(end),operations.index(calls[-1]))
        self.assertEqual(end['attributes']['validation'],'valid')

    def test_returning_a_temporary_borrow_is_rejected_at_its_lifetime_end(self):
        factory='fn make():i32[1] { return [5]; } '
        functions='fn identity(i32* value):i32* { return value; } '
        doc=compile_text('module demo; '+factory+functions+
                         'fn bad():i32* { return identity(&make()[0]); }')
        validate(doc)
        self.assertIn('lifetime_violation',[diag['code'] for diag in doc['diagnostics']])
        self.assertEqual(self.ops(doc,'temporary_end')[0]['attributes']['validation'],'invalid')

    def test_borrow_cannot_be_retained_outside_a_call(self):
        factory='fn make():i32[1] { return [5]; } '
        doc=self.reject('i32* pointer=&make()[0]; return 0;','unsupported_temporary_borrow',factory=factory)


if __name__=='__main__':
    unittest.main()

import unittest
from cobalt.source import Source, IDs, Diagnostics, StopCompilation
from cobalt.lexer import lex
from cobalt.syntax import Parser

def parse(s):
    ids=IDs(); d=Diagnostics(ids)
    return Parser(lex(Source('x.cb',s),ids,d),ids,d).parse()

class ParserTests(unittest.TestCase):
    def test_managed_pointer_types_and_borrow_precedence(self):
        n=parse('module demo; fn f(mut i32* pointer) : i32* { i32* shared=&*pointer; return shared; }')
        fn=n.data['functions'][0]
        self.assertEqual(fn.data['params'][0].data['type'], 'mut i32*')
        self.assertFalse(fn.data['params'][0].data['mutable'])
        self.assertEqual(fn.data['result'], 'i32*')
        borrow=fn.data['body'].data['statements'][0].data['value']
        self.assertEqual(borrow.kind, 'borrow')
        self.assertEqual(borrow.data['value'].kind, 'deref')
        for source in ['module demo; fn f(mut mut i32* p) {}',
                       'module demo; fn f() { i32** pointer; }',
                       'module demo; fn f() { i32*? pointer; }']:
            with self.subTest(source=source), self.assertRaises(StopCompilation): parse(source)

    def test_pointer_binding_mutability_is_separate_from_pointer_type(self):
        n=parse('module demo; fn f(i32* mut local, mut i32* mut exclusive) {}')
        first,second=n.data['functions'][0].data['params']
        self.assertEqual(first.data['type'],'i32*')
        self.assertTrue(first.data['mutable'])
        self.assertEqual(second.data['type'],'mut i32*')
        self.assertTrue(second.data['mutable'])
        n=parse('module demo; fn f() { i32* mut local; mut i32* exclusive; }')
        local,exclusive=n.data['functions'][0].data['body'].data['statements']
        self.assertEqual(local.data['type'],'i32*')
        self.assertTrue(local.data['mutable'])
        self.assertEqual(exclusive.data['type'],'mut i32*')
        self.assertFalse(exclusive.data['mutable'])

    def test_precedence(self):
        n=parse('module x; fn f() : i32 { return 1 + 2 * 3; }')
        e=n.data['functions'][0].data['body'].data['statements'][0].data['value']
        self.assertEqual(e.data['operator'],'+')
        self.assertEqual(e.data['right'].data['operator'],'*')

    def test_void_and_if(self):
        n=parse('module a.b; export { f; } fn f(bool b) { if b { return; } else { i32 x; } }')
        self.assertEqual(n.data['functions'][0].data['result'],'void')

    def test_errors(self):
        for s in ['fn f() {}', 'module x; module y;', 'module x; fn f() { i32 true; }','module x; fn f() { while (true); }']:
            with self.subTest(s=s), self.assertRaises(StopCompilation): parse(s)

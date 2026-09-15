import unittest
from cobalt.source import Source, IDs, Diagnostics, StopCompilation
from cobalt.lexer import lex

class LexerTests(unittest.TestCase):
    def run_lex(self, text):
        ids = IDs(); d = Diagnostics(ids)
        return lex(Source('test.cb', text), ids, d)

    def test_nested_comments_and_spans(self):
        t = self.run_lex('/* a /* b */ c */\r\ni32 value = 0xA_B; // x')
        self.assertEqual([x.text for x in t], ['i32','value','=','0xA_B',';',''])
        self.assertEqual(t[0].span['start_line'], 2)
        self.assertEqual(t[3].value, 171)

    def test_literals(self):
        ts = self.run_lex('01 0b10 0o17 123. 123.e-10 \'λ\' "a\\n"')
        self.assertEqual([x.kind for x in ts], ['int','int','int','float','float','char','string','eof'])
        self.assertEqual(ts[0].value, 1)

    def test_protected_whole_tokens(self):
        self.assertEqual([t.kind for t in self.run_lex('return returnValue i32 i32Value let')][:-1], ['keyword','identifier','type','identifier','identifier'])

    def test_negative(self):
        for s in ['/* a', '0x', '1__2', '12_', '123e+', '1.2_3', '0b2', "'ab'", '"oops', '\u200b', 'a\u202e', 'aα']:
            with self.subTest(s=s), self.assertRaises(StopCompilation): self.run_lex(s)

    def test_unicode_identifiers_keep_original_spelling(self):
        spellings = ['é', 'e\u0301', '变量', 'résultat', '日本語abc', 'हिन्दी', 'שלום', 'か\u3099', 'Ѐ']
        self.assertEqual([t.text for t in self.run_lex(' '.join(spellings))][:-1], spellings)

    def test_unicode_17_classification_is_independent_of_host(self):
        from cobalt.unicode_identifiers import identifier_start, moderately_restrictive, skeleton, nfd, nfc
        self.assertTrue(identifier_start('\U0001e6c0'))  # Tai Yo, added in Unicode 17
        self.assertFalse(moderately_restrictive('\U0001e6c0'))  # restricted script
        self.assertEqual(skeleton('modern'), skeleton('rnodern'))
        self.assertEqual(skeleton('é'), skeleton('e\u0301'))
        self.assertNotEqual(skeleton('value'), skeleton('Value'))
        self.assertEqual(nfd([0xAC01]), [0x1100, 0x1161, 0x11A8])
        self.assertEqual(nfc([0x1100, 0x1161, 0x11A8]), [0xAC01])
        self.assertEqual(nfc([0x304B, 0x3099]), [0x304C])
        self.assertEqual(skeleton('か\u3099'), skeleton('が'))

    def test_confusables_are_checked_in_lookup_scope(self):
        from cobalt.driver import compile_text
        for source in ['module demo; fn f() { i32 modern=1; i32 rnodern=2; }',
                       'module demo; fn f() { i32 modern=1; { i32 rnodern=2; } }',
                       'module demo; fn f() { i32 voіd=1; }',
                       'module demo; fn f() { i32 ｖｏｉｄ=1; }',
                       'module demo; fn f() { i32 é=1; i32 e\u0301=2; }']:
            self.assertNotEqual(compile_text(source)['compilation']['result'], 'valid')
        doc = compile_text('module demo; fn f() { { i32 modern=1; } { i32 rnodern=2; } }')
        self.assertEqual(doc['compilation']['result'], 'valid')

if __name__ == '__main__': unittest.main()

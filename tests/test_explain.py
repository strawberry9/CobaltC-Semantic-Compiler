import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from cobalt.driver import compile_text
from cobalt.explain import render


class ExplainTests(unittest.TestCase):
    def test_source_is_embedded_and_escaped_beside_report(self):
        source = 'module demo; // <script>alert(1)</script> &\nfn f() {}\n'
        doc = compile_text(source, 'original/demo.cb')
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'demo.cb').write_text(source, encoding='utf-8')
            html = render(doc, path / 'demo.esir.json')
        self.assertIn('<pre><code>module demo;', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; &amp;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('has changed since compilation', html)
        self.assertLess(html.index('Source code'), html.index('Plain-English interpretation'))

    def test_missing_and_changed_source_do_not_prevent_report(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'demo.cb'
            doc = compile_text('module demo; fn f() {}', str(path))
            self.assertIn('Source file unavailable', render(doc))
            path.write_text('module changed;', encoding='utf-8')
            html = render(doc)
            self.assertIn('has changed since compilation', html)
            self.assertIn('<pre><code>module changed;</code></pre>', html)
            self.assertIn('Plain-English interpretation', html)

    def test_names_move_and_control_links(self):
        doc = compile_text('module demo; fn f(bool b) : i32 { i32 x=1; if b { return move x; } return x; }')
        html = render(doc)
        self.assertIn('move x; the source loses', html)
        self.assertIn('Initialized / Owned', html)
        self.assertIn('Moved / Moved', html)
        for b in doc['functions'][0]['blocks']:
            self.assertIn('id="'+b['id']+'"', html)
        self.assertIn('true: <a', html)
        self.assertIn('false: <a', html)

    def test_invalid_attempt_is_labeled(self):
        doc = compile_text('module demo; fn f() : i32 { i32 x; return x; }')
        html = render(doc)
        self.assertIn('Invalid attempted operation:', html)
        self.assertIn('uninitialized_read', html)

    def test_source_content_is_escaped(self):
        doc = compile_text('module demo; fn f() {}', '<script>alert(1)</script>.cb')
        html = render(doc)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)


class NarrativeTests(unittest.TestCase):
    def test_managed_pointer_narrative(self):
        doc = compile_text('module demo; fn f() : i32 { mut i32 value=1; mut i32* pointer=&mut value; i32* shared=pointer; i32 saved=*shared; *pointer=2; return value; }')
        html = render(doc)
        self.assertIn('a mutable borrow of value', html)
        self.assertIn('a shared reborrow through pointer', html)
        self.assertIn('using exclusive mutable access', html)
        self.assertIn('without owning their referents', html)
        self.assertIn('Borrow no longer needed after this step', html)

    def test_scalar_interpretation_is_program_specific(self):
        import json
        from pathlib import Path
        from cobalt.narrative import interpret
        doc = json.loads(Path('examples/scalars.esir.json').read_text())
        _, functions = interpret(doc)
        text = str(functions)
        self.assertIn('condition is true', text)
        self.assertIn('condition is false', text)
        self.assertIn('Set result to (input + 1).', text)
        self.assertIn('Set result to 0.', text)
        self.assertIn('Copy result into copied.', text)
        self.assertIn('Move copied into transferred.', text)
        self.assertEqual(len(functions[0]['paths']), 2)
        html = render(doc)
        self.assertLess(html.index('Plain-English interpretation'), html.index('Function choose'))

    def test_incomplete_report_does_not_invent_behavior(self):
        doc = compile_text('module counter; import io { print };')
        html = render(doc)
        self.assertIn('could not finish analyzing', html)
        self.assertIn('No function behavior is available', html)
        self.assertNotIn('Every recorded reachable read', html)

    def test_invalid_reads_do_not_get_success_summary(self):
        html = render(compile_text('module demo; fn f() : i32 { i32 x; return x; }'))
        self.assertIn('The compiler found errors.', html)
        self.assertNotIn('Every recorded reachable read', html)

    def test_return_value_is_prepared_before_deferred_mutation(self):
        from cobalt.narrative import interpret
        doc = compile_text('module demo; fn f() : i32 { mut i32 x=1; defer { x=2; }; return x; }')
        _, functions = interpret(doc)
        steps = functions[0]['paths'][0][1]
        prepare = next(i for i, s in enumerate(steps) if 'Prepare x as' in s)
        mutate = steps.index('Set x to 2.')
        self.assertLess(prepare, mutate)
        self.assertEqual(steps[-1], 'Return the prepared value to the caller.')

    def test_path_overview_is_bounded(self):
        from cobalt.narrative import interpret
        body = ' '.join('if b { i32 x=1; } else { i32 y=2; }' for _ in range(5))
        _, functions = interpret(compile_text('module demo; fn f(bool b) {'+body+'}'))
        self.assertTrue(functions[0]['truncated'])
        self.assertEqual(len(functions[0]['paths']), 8)

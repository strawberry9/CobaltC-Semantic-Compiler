import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from cobalt.driver import compile_text, compile_bytes
from cobalt.esir import dumps, validate, ValidationError


def compile_body(body,params='',result='i32',prefix=''):
    return compile_text(f'module test; {prefix} fn test({params}) : {result} {{ {body} }}')

def codes(doc):return {d['code'] for d in doc['diagnostics']}
def ops(doc):return [op for f in doc['functions'] for b in f['blocks'] for op in b['operations']]

class CompilerTests(unittest.TestCase):
    def valid(self,doc):
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics']);validate(doc)

    def test_scalar_example(self):
        self.valid(compile_text(Path('examples/scalars.cb').read_text()))

    def test_self_initializer(self):
        self.assertIn('uninitialized_read',codes(compile_body('i32 x = x; return x;')))

    def test_branch_initialization(self):
        self.valid(compile_body('mut i32 x; if b { x = 1; } else { x = 2; } return x;', 'bool b'))
        self.assertIn('uninitialized_read',codes(compile_body('mut i32 x; if b { x = 1; } return x;', 'bool b')))

    def test_returning_branch_does_not_pollute_merge(self):
        self.valid(compile_body('mut i32 x; if b { return 1; } else { x = 2; } return x;', 'bool b'))

    def test_moves_and_copies(self):
        doc=compile_body('i32 x = 1; i32 y = x; i32 z = move x; return y + z;')
        self.valid(doc)
        move=next(o for o in ops(doc) if o['kind']=='move')
        self.assertEqual(move['attributes']['state_after']['ownership'],['Moved'])
        self.assertEqual(move['attributes']['state_before']['object_identities'],move['attributes']['object_identities'])
        cp=next(o for o in ops(doc) if o['kind']=='copy')
        self.assertNotEqual(cp['attributes']['state_before']['object_identities'],cp['attributes']['object_identities'])
        self.assertIn('use_after_move',codes(compile_body('i32 x = 1; i32 y = move x; return x;')))

    def test_conditional_move(self):
        doc=compile_body('i32 x = 1; if b { i32 y = move x; } return x;', 'bool b')
        self.assertIn('use_after_move',codes(doc))

    def test_move_reinitialization(self):
        self.valid(compile_body('mut i32 x = 1; i32 y = move x; x = 2; return x;'))

    def test_mutability(self):
        self.assertIn('immutable_assignment',codes(compile_body('i32 x=1; x=2; return x;')))
        self.valid(compile_body('mut i32 x=1; x=2; return x;'))

    def test_rhs_before_replacement(self):
        doc=compile_body('mut i32 x=1; x=x+1; return x;');self.valid(doc)
        allops=ops(doc);assign=next(o for o in allops if o['kind']=='assign')
        self.assertEqual(assign['attributes']['state_before']['initialization'],['Initialized'])
        self.assertTrue(assign['effects']['destruction'])

    def test_failed_rhs_does_not_initialize(self):
        doc=compile_body('i32 x=true; return x;')
        init=next(o for o in ops(doc) if o['kind']=='init')
        self.assertEqual(init['facts_established'],[])
        self.assertEqual(init['attributes']['state_after']['initialization'],['Uninitialized'])

    def test_overflow(self):
        self.assertIn('arithmetic_failure',codes(compile_body('i32 x=2147483647; return x+1;')))
        self.assertIn('literal_range',codes(compile_body('return 2147483648;')))
        self.valid(compile_body('i8 x=-128; return x;',result='i8'))

    def test_contextual_literal(self):
        self.valid(compile_body('u128 x=340282366920938463463374607431768211455; return x;',result='u128'))
        self.assertIn('literal_range',codes(compile_body('u8 x=256; return x;',result='u8')))

    def test_call_and_order(self):
        prefix='fn add(i32 a, i32 b) : i32 { return a+b; }'
        self.valid(compile_body('return add(1,2);',prefix=prefix))
        self.assertIn('argument_count',codes(compile_body('return add(1);',prefix=prefix)))
        self.assertIn('use_after_move',codes(compile_body('i32 x=1; return add(move x,x);',prefix=prefix)))
        self.valid(compile_body('i32 x=1; return add(x,move x);',prefix=prefix))

    def test_scopes(self):
        self.valid(compile_body('i32 x=1; { i32 x=2; } return x;'))
        self.assertIn('unresolved_name',codes(compile_body('{ i32 x=2; } return x;')))
        self.assertIn('duplicate_name',codes(compile_body('i32 x=1; i32 x=2; return x;')))

    def test_missing_return(self):
        self.assertIn('missing_return',codes(compile_body('if b { return 1; }','bool b')))
        self.valid(compile_body('if b { return 1; } else { return 2; }','bool b'))

    def test_void(self):
        self.valid(compile_body('return;',result='void'))
        self.assertIn('return_type',codes(compile_body('return 1;',result='void')))

    def test_condition(self):
        self.assertIn('type_error',codes(compile_body('if 1 { return 1; } return 0;')))

    def test_short_circuit(self):
        self.valid(compile_body('bool x; return false && x;',result='bool'))
        self.assertIn('uninitialized_read',codes(compile_body('bool x; return true && x;',result='bool')))
        self.valid(compile_body('bool x; return true || x;',result='bool'))

    def test_cleanup_reverse_order(self):
        doc=compile_body('i32 x=1; i32 y=2; return 0;');self.valid(doc)
        allocated=[o['operands'][0] for o in ops(doc) if o['kind']=='alloca']
        destroyed=[o['operands'][0] for o in ops(doc) if o['kind']=='destroy']
        self.assertEqual(destroyed,list(reversed(allocated)))

    def test_moved_cleanup_is_not_executed(self):
        doc=compile_body('i32 x=1; return move x;');self.valid(doc)
        destroy=next(o for o in ops(doc) if o['kind']=='destroy')
        self.assertFalse(destroy['attributes']['executes_if_initialized'])
        self.assertEqual(destroy['effects'],{})

    def test_defer_uses_exit_state(self):
        self.valid(compile_body('mut i32 x=1; defer { x=x+1; }; x=2; return 0;'))
        self.assertIn('use_after_move',codes(compile_body('i32 x=1; defer { x; }; return move x;')))
        self.valid(compile_body('mut i32 x=1; defer { x; }; i32 y=move x; x=2; return y;'))

    def test_defer_order_and_return_preparation(self):
        doc=compile_body('i32 x=1; defer { x; }; defer { x; }; return x;');self.valid(doc)
        operations=ops(doc)
        registered=[o['operands'][0] for o in operations if o['kind']=='defer_register']
        executed=[o['operands'][0] for o in operations if o['kind']=='defer_execute']
        self.assertEqual(executed,list(reversed(registered)))
        kinds=[o['kind'] for o in operations]
        self.assertLess(kinds.index('return_prepare'),kinds.index('defer_execute'))
        self.assertLess(kinds.index('defer_execute'),kinds.index('destroy'))

    def test_constants(self):
        self.valid(compile_body('const i32 x=1+2; return x;'))
        self.assertIn('constant_required',codes(compile_body('const i32 x=p; return x;','i32 p')))

    def test_unsupported_is_incomplete(self):
        for body in ['String s="hello"; return 0;', 'while (true) { } return 0;', 'return 1/2;']:
            with self.subTest(body=body):self.assertEqual(compile_body(body)['compilation']['result'],'incomplete')

    def test_bad_utf8(self):
        doc=compile_bytes(b'module x;\xff');validate(doc)
        self.assertIn('invalid_utf8',codes(doc))

    def test_determinism(self):
        text=Path('examples/scalars.cb').read_text()
        self.assertEqual(dumps(compile_text(text)),dumps(compile_text(text)))

    def test_schema_and_references_fail_closed(self):
        original=compile_body('return 1;')
        mutations=[lambda d:d.update(extra=True),lambda d:d['functions'][0].update(type='missing'),
                   lambda d:d['summary'].update(operation_count=999),lambda d:d['functions'][0]['blocks'][0]['operations'][0]['rule_refs'].append('FAKE')]
        for change in mutations:
            doc=copy.deepcopy(original);change(doc)
            with self.assertRaises(ValidationError):validate(doc)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'x.cb';out=Path(tmp)/'x.esir.json'
            for body,expected in [('return 1;',0),('i32 x; return x;',1),('return 1/2;',2)]:
                source.write_text(f'module x; fn main() : i32 {{ {body} }}')
                result=subprocess.run([sys.executable,'-m','cobalt',str(source),'-o',str(out)],capture_output=True,text=True)
                self.assertEqual(result.returncode,expected,result.stderr)
                validate(json.loads(out.read_text()))

class AdditionalRegressions(unittest.TestCase):
    def test_unary_negation_overflow(self):
        self.assertIn('arithmetic_failure',codes(compile_body('i8 x=-128; return -x;',result='i8')))
        doc=compile_body('return -x;','i8 x','i8')
        self.assertTrue(any(b['terminator']['kind']=='fail' for f in doc['functions'] for b in f['blocks']))

    def test_bad_syntax_is_invalid(self):
        self.assertEqual(compile_text('module x; fn f( {}')['compilation']['result'],'invalid')

    def test_defer_captures_binding_before_shadow(self):
        doc=compile_body('i32 x=1; { defer { x; }; i32 x=2; } return x;')
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        reads=[o for o in ops(doc) if o['kind']=='copy']
        self.assertEqual(reads[0]['operands'],reads[-1]['operands'])

class GoldenTests(unittest.TestCase):
    def test_reviewed_examples(self):
        for path in sorted(Path('examples').glob('*.cb')):
            with self.subTest(path=path):
                doc=compile_bytes(path.read_bytes(),path.as_posix())
                self.assertEqual(dumps(doc),path.with_suffix('.esir.json').read_text())
                validate(doc)

    def test_success_failure_are_distinct_paths(self):
        doc=compile_body('return x+1;','i32 x')
        fn=doc['functions'][0]
        arithmetic=next(o for o in ops(doc) if o['kind']=='arithmetic_checked')
        block=next(b for b in fn['blocks'] if arithmetic in b['operations'])
        targets=block['terminator']['targets']
        fail=next(b for b in fn['blocks'] if b['id']==targets[1])
        self.assertEqual(fail['terminator']['kind'],'fail')
        self.assertFalse(fail['terminator']['attributes']['produces_value'])
        self.assertEqual(fail['operations'],[])

    def test_defer_capture_survives_checked_arithmetic(self):
        doc=compile_body('mut i32 x=1; defer { x=x+1; }; return 0;')
        region=doc['functions'][0]['cleanup_regions'][0]
        obligation=region['defer_obligations'][0]
        self.assertTrue(obligation['captured_places'])
        self.assertIsNotNone(obligation['body_block'])

class MutabilityRegressions(unittest.TestCase):
    def test_later_initialization_requires_mutable_destination(self):
        self.assertIn('immutable_assignment',codes(compile_body('i32 x; x=1; return x;')))
        doc=compile_body('mut i32 x; x=1; return x;')
        self.assertEqual(doc['compilation']['result'],'valid')

    def test_reinitialization_does_not_waive_mutability(self):
        self.assertIn('immutable_assignment',codes(compile_body('i32 x=1; i32 y=move x; x=2; return y;')))

class ImplementationBoundaryTests(unittest.TestCase):
    def test_assignment_value_is_incomplete(self):
        doc=compile_body('mut i32 x=0; return x=1;')
        self.assertEqual(doc['compilation']['result'],'incomplete')
        self.assertIn('unsupported_assignment_value',codes(doc))

    def test_extreme_nesting_is_diagnosed(self):
        doc=compile_body('return '+'('*1200+'1'+')'*1200+';')
        self.assertEqual(doc['compilation']['result'],'incomplete')
        self.assertIn('unsupported_nesting_depth',codes(doc))

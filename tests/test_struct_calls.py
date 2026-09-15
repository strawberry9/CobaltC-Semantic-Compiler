import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class StructCallTests(unittest.TestCase):
    prefix = 'module demo; struct Point { i32 x; i32 y; } '

    def compile(self, functions, body='return 0;', params=''):
        return compile_text(self.prefix+functions+' fn test('+params+'):i32 { '+body+' }')

    def valid(self, functions, body='return 0;', params=''):
        doc = self.compile(functions, body, params)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        validate(doc)
        return doc

    def rejected(self, functions, body, code, params=''):
        doc = self.compile(functions, body, params)
        self.assertIn(code, [d['code'] for d in doc['diagnostics']], doc['diagnostics'])
        validate(doc)
        return doc

    def ops(self, doc, kind, function=None):
        return [o for f in doc['functions'] if function is None or f['name']==function
                for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def test_parameter_fields_owned_initialized_and_cleaned(self):
        doc = self.valid('fn read(Point p):i32 { return p.x+p.y; }',
                         'Point p=Point{x=1,y=2}; return read(p);')
        parameter = self.ops(doc, 'parameter', 'read')[0]
        self.assertEqual(set(parameter['attributes']['field_states_after']), {'x','y'})
        self.assertTrue(all(s['initialization']==['Initialized'] and s['ownership']==['Owned']
                            for s in parameter['attributes']['field_states_after'].values()))
        destroys = self.ops(doc, 'destroy', 'read')
        self.assertEqual(len(destroys), 2)
        self.assertTrue(all(o['attributes']['executes_if_initialized'] for o in destroys))

    def test_copy_argument_preserves_source_and_independent_identities(self):
        doc = self.valid('fn consume(Point p):void {}',
                         'Point p=Point{x=1,y=2}; consume(p); return p.x;')
        copy = self.ops(doc, 'copy', 'test')[0]
        for name, field in copy['attributes']['result_field_states'].items():
            self.assertNotEqual(field['object_identities'], copy['attributes']['field_states_before'][name]['object_identities'])
        call = self.ops(doc, 'call')[0]
        arg = call['attributes']['struct_arguments'][0]
        self.assertEqual(arg['field_states'], copy['attributes']['result_field_states'])
        self.assertTrue(any('transfer_argument_field' in e for e in call['effects']['ownership']))

    def test_move_argument_consumes_source_and_preserves_transferred_identity(self):
        doc = self.valid('fn consume(Point p):void {}',
                         'Point p=Point{x=1,y=2}; consume(move p); return 0;')
        move = self.ops(doc, 'move', 'test')[0]
        for name, field in move['attributes']['result_field_states'].items():
            self.assertEqual(field['object_identities'], move['attributes']['field_states_before'][name]['object_identities'])
        self.assertTrue(all(not o['attributes']['executes_if_initialized'] for o in self.ops(doc, 'destroy', 'test')))
        self.rejected('fn consume(Point p):void {}', 'Point p=Point{x=1,y=2}; consume(move p); return p.x;', 'use_after_move')

    def test_constructed_arguments_and_left_to_right_evaluation(self):
        self.valid('fn read(Point p):i32 { return p.x; }', 'return read(Point{y=2,x=1});')
        functions = 'fn consume(Point first, Point second):void {}'
        self.valid(functions, 'Point p=Point{x=1,y=2}; consume(p, move p); return 0;')
        self.rejected(functions, 'Point p=Point{x=1,y=2}; consume(move p, p); return 0;', 'use_after_move')

    def test_return_constructed_value_is_complete_but_not_constant_evaluated(self):
        doc = self.valid('fn make():Point { return Point{x=1,y=2}; }', 'Point p=make(); return p.x;')
        call = self.ops(doc, 'call')[0]
        self.assertEqual(set(call['attributes']['result_field_states']), {'x','y'})
        self.assertTrue(all(s['initialization']==['Initialized'] for s in call['attributes']['result_field_states'].values()))
        self.assertNotIn('constant_value', self.ops(doc, 'copy', 'test')[-1]['attributes'])
        returned = self.ops(doc, 'return_prepare', 'make')[0]
        self.assertEqual(set(returned['attributes']['returned_field_states']), {'x','y'})

    def test_return_copy_and_move_cleanup(self):
        for expression, executes in [('p', True), ('move p', False)]:
            with self.subTest(expression=expression):
                doc = self.valid('fn identity(Point p):Point { return '+expression+'; }',
                                 'Point p=identity(Point{x=1,y=2}); return p.y;')
                self.assertTrue(all(o['attributes']['executes_if_initialized']==executes for o in self.ops(doc, 'destroy', 'identity')))
                returned = self.ops(doc, 'return_prepare', 'identity')[0]
                transfer = self.ops(doc, 'copy' if executes else 'move', 'identity')[0]
                self.assertEqual(returned['attributes']['returned_field_states'], transfer['attributes']['result_field_states'])

    def test_return_prepared_before_deferred_mutation(self):
        doc = self.valid('fn make():Point { mut Point p=Point{x=1,y=2}; defer { p.x=9; }; return p; }', 'Point p=make(); return p.x;')
        returned = self.ops(doc, 'return_prepare', 'make')[0]
        copied = self.ops(doc, 'copy', 'make')[0]
        self.assertEqual(returned['attributes']['returned_field_states'], copied['attributes']['result_field_states'])
        operations = [o for f in doc['functions'] if f['name']=='make' for b in f['blocks'] for o in b['operations']]
        assignment = self.ops(doc, 'assign', 'make')[0]
        self.assertLess(operations.index(returned), operations.index(assignment))
        self.rejected('fn make():Point { Point p=Point{x=1,y=2}; defer { p.x; }; return move p; }', 'return 0;', 'use_after_move')

    def test_partial_move_parameter_cleanup_and_restore_via_local(self):
        doc = self.valid('fn take(Point p):i32 { i32 value=move p.x; return value; }', 'return take(Point{x=1,y=2});')
        self.assertEqual([o['attributes']['executes_if_initialized'] for o in self.ops(doc, 'destroy', 'take')], [True, True, False])
        self.valid('fn update(Point p):Point { mut Point local=move p; i32 old=move local.x; local.x=9; return move local; }',
                   'Point p=update(Point{x=1,y=2}); return p.x;')

    def test_partial_uninitialized_arguments_and_returns_rejected(self):
        functions = 'fn consume(Point p):void {}'
        self.rejected(functions, 'Point p=Point{x=1,y=2}; i32 old=move p.x; consume(p); return 0;', 'use_after_move')
        self.rejected(functions, 'mut Point p; p.x=1; consume(move p); return 0;', 'uninitialized_read')
        self.rejected('fn bad(Point p):Point { i32 old=move p.x; return p; }', 'return 0;', 'use_after_move')
        self.rejected('fn bad():Point { mut Point p; p.x=1; return move p; }', 'return 0;', 'uninitialized_read')

    def test_nominal_argument_return_types_and_missing_return(self):
        self.rejected('struct Other { i32 x; i32 y; } fn consume(Point p):void {}',
                      'Other p=Other{x=1,y=2}; consume(p); return 0;', 'type_error')
        doc = self.rejected('struct Other { i32 x; i32 y; } fn bad():Point { return Other{x=1,y=2}; }', 'return 0;', 'type_error')
        returned = self.ops(doc, 'return_prepare', 'bad')[0]
        self.assertEqual(returned['attributes']['validation'], 'invalid')
        self.assertEqual(returned['effects'], {})
        self.assertNotIn('returned_field_states', returned['attributes'])
        self.rejected('fn bad(bool flag):Point { if (flag) { return Point{x=1,y=2}; } }', 'return 0;', 'missing_return')

    def test_branch_returns_and_recursive_interface(self):
        functions = 'fn choose(bool flag, Point p):Point { if (flag) { return p; } return move p; }'
        self.valid(functions, 'Point p=choose(flag, Point{x=1,y=2}); return p.x;', 'bool flag')
        self.valid('fn recurse(bool flag, Point p):Point { if (flag) { return p; } return recurse(true, move p); }',
                   'Point p=recurse(false, Point{x=1,y=2}); return p.x;')

    def test_returned_struct_discard_replacement_and_forwarding(self):
        functions = 'fn make():Point { return Point{x=1,y=2}; } fn wrap():Point { return make(); }'
        doc = self.valid(functions, 'make(); mut Point p=make(); p=wrap(); return p.x;')
        self.assertEqual(len(self.ops(doc, 'discard', 'test')[0]['effects']['destruction']), 2)
        self.assertEqual(len(self.ops(doc, 'assign', 'test')[0]['effects']['destruction']), 2)

    def test_by_value_and_borrowed_arguments_are_distinct(self):
        doc = self.valid('fn combine(Point owned, mut Point* borrowed):Point { borrowed->x=9; return move owned; }',
                         'mut Point p=Point{x=1,y=2}; Point result=combine(p, &mut p); return result.x;')
        call = self.ops(doc, 'call')[0]
        self.assertTrue(any(e.startswith('receive_return_field') for e in call['effects']['ownership']))
        self.assertEqual(len(call['attributes']['struct_arguments']), 1)
        self.rejected('fn combine(Point owned, Point* borrowed):Point { return owned; }',
                      'Point p=Point{x=1,y=2}; Point* ptr=&p; Point result=combine(move p, ptr); return result.x;', 'borrow_conflict')

    def test_cannot_return_pointer_to_owned_parameter(self):
        self.rejected('fn bad(Point p):i32* { return &p.x; }', 'return 0;', 'lifetime_violation')

    def test_empty_struct_parameters_and_returns(self):
        self.valid('struct Empty {} fn identity(Empty value):Empty { return move value; }',
                   'Empty first=Empty{}; Empty second=identity(move first); identity(move second); return 0;')

    def test_report_and_determinism(self):
        functions = 'fn identity(Point p):Point { return move p; }'
        body = 'Point p=identity(Point{x=1,y=2}); return p.x;'
        doc = self.valid(functions, body)
        self.assertEqual(dumps(doc), dumps(self.compile(functions, body)))
        self.assertIn('by value', render(doc))

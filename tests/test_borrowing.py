import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate


class BorrowTests(unittest.TestCase):
    def compile(self, body, result='i32', functions=''):
        return compile_text('module demo; '+functions+' fn test() : '+result+' { '+body+' }')

    def valid(self, body, result='i32', functions=''):
        doc = self.compile(body, result, functions)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        validate(doc)
        return doc

    def invalid(self, body, code, result='i32', functions=''):
        doc = self.compile(body, result, functions)
        self.assertEqual(doc['compilation']['result'], 'invalid', doc['diagnostics'])
        self.assertIn(code, [d['code'] for d in doc['diagnostics']])
        return doc

    def ops(self, doc):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations']]

    def test_shared_copy_has_distinct_capabilities_and_no_referent_ownership(self):
        doc = self.valid('i32 value=7; i32* first=&value; i32* second=first; return *first + *second;')
        fn = doc['functions'][0]
        self.assertEqual(len(fn['capabilities']), 2)
        self.assertEqual(len({c['referent'] for c in fn['capabilities']}), 1)
        self.assertTrue(all(c['access'] == 'SharedRead' for c in fn['capabilities']))
        copy = next(o for o in self.ops(doc) if o['kind'] == 'copy')
        self.assertEqual(copy['attributes']['result_ownership'], 'Unowned')
        self.assertNotIn('ownership', copy['effects'])
        for c in fn['capabilities']:
            life = next(l for l in fn['lifetimes'] if l['id'] == c['lifetime'])
            self.assertIsNotNone(life['parent'])

    def test_last_use_ends_borrow_before_owner_assignment(self):
        doc = self.valid('mut i32 value=7; i32* pointer=&value; i32 saved=*pointer; value=9; return saved;')
        self.assertTrue(any(o['attributes'].get('ended_capabilities') for o in self.ops(doc)))

    def test_conflicting_owner_operations(self):
        for operation in ('value=9;', 'i32 taken=move value;'):
            self.invalid('mut i32 value=7; i32* pointer=&value; '+operation+' return *pointer;', 'borrow_conflict')
        self.invalid('mut i32 value=7; mut i32* pointer=&mut value; i32 saved=value; return *pointer;', 'borrow_conflict')

    def test_invalid_borrow_sources(self):
        self.invalid('i32 value; i32* pointer=&value; return 0;', 'invalid_borrow')
        self.invalid('i32 value=7; i32 taken=move value; i32* pointer=&value; return 0;', 'invalid_borrow')
        self.invalid('i32 value=7; mut i32* pointer=&mut value; return 0;', 'borrow_conflict')

    def test_mutable_dereference_updates_scalar_state(self):
        doc = self.valid('mut i32 value=7; mut i32* pointer=&mut value; *pointer=9; return value;')
        read = next(o for o in reversed(self.ops(doc)) if o['kind'] == 'copy')
        self.assertEqual(read['attributes']['constant_value'], 9)
        self.invalid('i32 value=7; i32* pointer=&value; *pointer=9; return value;', 'borrow_conflict')

    def test_reborrow_suspends_and_resumes_parent(self):
        doc = self.valid('mut i32 value=7; mut i32* pointer=&mut value; i32* shared=pointer; i32 saved=*shared; *pointer=9; return value;')
        self.assertTrue(any('Suspended' in o['attributes'].get('capability_state_after', {}).values() for o in self.ops(doc)))
        assignment = next(o for o in self.ops(doc) if o['kind'] == 'deref_assign')
        self.assertEqual(list(assignment['attributes']['capability_state_before'].values()), ['Active'])
        self.invalid('mut i32 value=7; mut i32* pointer=&mut value; i32* shared=&*pointer; *pointer=9; return *shared;', 'borrow_conflict')
        self.invalid('mut i32 value=7; i32* pointer=&value; mut i32* exclusive=&mut *pointer; return 0;', 'borrow_conflict')

    def test_mutable_pointer_transfer_consumes_source(self):
        self.valid('mut i32 value=7; mut i32* first=&mut value; mut i32* second=first; *second=9; return value;')
        self.invalid('mut i32 value=7; mut i32* first=&mut value; mut i32* second=first; return *first;', 'use_after_move')

    def test_mutable_pointer_binding_can_rebind_to_another_shared_referent(self):
        doc=self.valid('i32 first=1; i32 second=2; i32* mut pointer=&first; '
                       'pointer=&second; return *pointer;')
        assignment=next(o for o in self.ops(doc) if o['kind']=='assign')
        self.assertEqual(assignment['attributes']['validation'],'valid')
        self.assertTrue(assignment['effects'].get('borrows'))
        self.assertEqual(assignment['attributes']['binding_mutability'],'Mutable')
        self.assertNotEqual(assignment['attributes']['pointer_capabilities_before'],
                            assignment['attributes']['pointer_capabilities_after'])
        self.assertTrue(any(o['attributes'].get('ended_capabilities') for o in self.ops(doc)))

    def test_immutable_pointer_binding_cannot_be_rebound(self):
        self.invalid('i32 first=1; i32 second=2; i32* pointer=&first; '
                     'pointer=&second; return *pointer;','immutable_assignment')

    def test_mutable_exclusive_pointer_binding_rebinds_by_transfer(self):
        doc=self.valid('mut i32 first=1; mut i32 second=2; '
                       'mut i32* mut pointer=&mut first; mut i32* source=&mut second; '
                       'pointer=move source; *pointer=9; return first+second;')
        self.assertTrue(any(o['kind']=='move' and o['attributes'].get('result_ownership')=='Unowned'
                            for o in self.ops(doc)))
        self.assertTrue(any(o['kind']=='assign' and o['attributes']['validation']=='valid'
                            for o in self.ops(doc)))

    def test_mutable_shared_pointer_parameter_can_be_reseated_and_returned(self):
        functions=('fn reseat(i32* mut slot, i32* next):i32* { '
                   'slot=next; return slot; } ')
        doc=self.valid('mut i32 first=1; i32 second=2; i32* pointer=reseat(&first,&second); '
                       'first=9; return *pointer;',functions=functions)
        target=next(f for f in doc['functions'] if f['name']=='reseat')
        write=next(o for b in target['blocks'] for o in b['operations'] if o['kind']=='assign')
        self.assertTrue(write['attributes']['pointer_capabilities_after'])
        self.assertTrue(set(write['attributes']['pointer_capabilities_after']) <=
                        {c['id'] for c in target['capabilities']})

    def test_branch_rebinding_preserves_all_possible_targets(self):
        doc=self.valid('i32 first=1; i32 second=2; i32 third=3; bool flag=condition(); '
                       'i32* mut pointer=&first; if flag { pointer=&second; } '
                       'else { pointer=&third; } return *pointer;',
                       functions='fn condition():bool { return true; }')
        read=next(o for o in self.ops(doc) if o['kind']=='deref_read')
        referents={effect.rsplit(',',1)[1].rstrip(')') for effect in read['effects']['borrows']
                   if effect.startswith('read_through(')}
        self.assertEqual(len(referents),2)

    def test_old_exclusive_target_remains_borrowed_through_a_live_alias(self):
        self.invalid('mut i32 first=1; mut i32 second=2; '
                     'mut i32* mut pointer=&mut first; i32* shared=pointer; '
                     'pointer=&mut second; first=9; return *shared+*pointer;', 'borrow_conflict')

    def test_array_and_struct_pointer_bindings_rebind_without_changing_referent_ownership(self):
        array=self.valid('i32[2] first=[1,2]; i32[2] second=[3,4]; '
                         'i32[2]* mut pointer=&first; pointer=&second; '
                         'i32[2] copy=*pointer; return copy[1];')
        self.assertEqual(next(o for o in self.ops(array) if o['kind']=='assign')['attributes']['validation'],'valid')
        struct=self.valid('mut Point first=Point{x=1,y=2}; mut Point second=Point{x=3,y=4}; '
                          'mut i32* mut field=&mut first.x; field=&mut second.x; '
                          'first.x=7; *field=9; return first.x+second.x;',
                          functions='struct Point { i32 x; i32 y; } ')
        self.assertEqual(next(o for o in self.ops(struct) if o['kind']=='assign')['attributes']['validation'],'valid')

    def test_invalid_pointer_rebinding_keeps_the_previous_capability(self):
        doc=self.invalid('i32 first=1; i32* mut pointer=&first; pointer=2; return *pointer;',
                         'type_error')
        write=next(o for o in self.ops(doc) if o['kind']=='assign')
        read=next(o for o in self.ops(doc) if o['kind']=='deref_read')
        self.assertFalse(write['effects'])
        self.assertEqual(read['attributes']['constant_value'],1)

    def test_calls_require_live_borrows_and_forget_mutated_constants(self):
        functions = 'fn set(mut i32* pointer) { *pointer=9; }'
        doc = self.valid('mut i32 value=7; set(&mut value); return value;', functions=functions)
        last_copy = [o for o in self.ops(doc) if o['kind'] == 'copy'][-1]
        self.assertNotIn('constant_value', last_copy['attributes'])
        self.valid('mut i32 value=7; mut i32* pointer=&mut value; set(&mut *pointer); *pointer=8; return value;', functions=functions)
        self.valid('mut i32 value=7; return read(&mut value);', functions='fn read(i32* pointer) : i32 { return *pointer; }')

    def test_call_arguments_conflict_for_duration_of_call(self):
        self.invalid('mut i32 value=7; return both(&mut value, &value);', 'borrow_conflict',
                     functions='fn both(mut i32* first, i32* second) : i32 { return *first + *second; }')

    def test_returned_borrow_provenance(self):
        self.valid('i32 value=7; i32* pointer=identity(&value); return *pointer;',
                   functions='fn identity(i32* pointer) : i32* { return pointer; }')
        self.invalid('i32 value=7; return &value;', 'lifetime_violation', result='i32*')
        self.invalid('i32 value=7; return identity(&value);', 'lifetime_violation', result='i32*',
                     functions='fn identity(i32* pointer) : i32* { return pointer; }')

    def test_returned_shared_capability_cannot_regain_mutability(self):
        functions = 'fn share(mut i32* pointer) : i32* { return pointer; }'
        self.invalid('mut i32 value=7; i32* pointer=share(&mut value); *pointer=9; return value;', 'borrow_conflict', functions=functions)

    def test_recursive_borrow_results_are_explicitly_incomplete(self):
        source = 'module demo; fn rotate(bool flag, i32* first, i32* second, i32* third) : i32* { if flag { return first; } return rotate(flag, second, third, first); }'
        doc = compile_text(source)
        self.assertEqual(doc['compilation']['result'], 'incomplete')
        self.assertIn('unsupported_borrow_return', [d['code'] for d in doc['diagnostics']])

    def test_return_summary_includes_every_branch(self):
        functions = 'fn choose(bool flag, i32* first, i32* second) : i32* { if flag { return first; } return second; }'
        self.invalid('mut i32 value=7; i32 other=8; i32* pointer=choose(true, &other, &value); value=9; return *pointer;', 'borrow_conflict', functions=functions)

    def test_branch_and_defer_liveness(self):
        functions = 'fn read(i32* pointer) : i32 { return *pointer; }'
        self.valid('mut i32 value=7; i32* pointer=&value; if true { read(pointer); } value=9; return value;', functions=functions)
        self.invalid('mut i32 value=7; i32* pointer=&value; defer { read(pointer); }; value=9; return 0;', 'borrow_conflict', functions=functions)
        source = 'module demo; fn f(bool flag) : i32 { mut i32 value=1; i32* pointer=&value; if flag { value=2; } return *pointer; }'
        self.assertIn('borrow_conflict', [d['code'] for d in compile_text(source)['diagnostics']])

    def test_deterministic_pointer_report(self):
        source = 'module demo; fn f(i32* pointer) : i32* { return pointer; }'
        self.assertEqual(dumps(compile_text(source)), dumps(compile_text(source)))

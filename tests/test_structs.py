import unittest

from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class StructTests(unittest.TestCase):
    declaration = 'struct Point { i32 x; i32 y; }'

    def compile(self, body, params='', declaration=None):
        return compile_text('module demo; '+(self.declaration if declaration is None else declaration)+
                            ' fn test('+params+') : i32 { '+body+' }')

    def valid(self, body, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        validate(doc)
        return doc

    def rejected(self, body, code, **kwargs):
        doc = self.compile(body, **kwargs)
        self.assertNotEqual(doc['compilation']['result'], 'valid')
        self.assertIn(code, [d['code'] for d in doc['diagnostics']], doc['diagnostics'])
        return doc

    def ops(self, doc):
        return [op for fn in doc['functions'] for block in fn['blocks'] for op in block['operations']]

    def test_construct_has_nominal_type_and_distinct_field_places(self):
        doc = self.valid('Point point=Point { y=2, x=1 }; return point.x + point.y;')
        typ = next(t for t in doc['types'] if t['kind'] == 'struct')
        self.assertEqual([f['name'] for f in typ['fields']], ['x','y'])
        fields = [p for p in doc['functions'][0]['places'] if p['parent']]
        self.assertEqual([p['field_path'] for p in fields], [['x'], ['y']])
        self.assertEqual(len({p['parent'] for p in fields}), 1)
        arithmetic = next(o for o in self.ops(doc) if o['kind'] == 'arithmetic_checked')
        self.assertEqual(arithmetic['attributes']['constant_value'], 3)

    def test_field_mutation_requires_mutable_binding(self):
        doc = self.valid('mut Point point=Point{x=1,y=2}; point.x=5; return point.x;')
        self.assertEqual(next(o for o in self.ops(doc) if o['kind'] == 'copy')['attributes']['constant_value'], 5)
        self.rejected('Point point=Point{x=1,y=2}; point.x=5; return point.x;', 'immutable_assignment')

    def test_initialization_is_per_field(self):
        doc = self.valid('mut Point point; point.x=1; return point.x;')
        assignment = next(o for o in self.ops(doc) if o['kind'] == 'assign')
        self.assertEqual(assignment['attributes']['aggregate_state_after']['initialization'], ['PartiallyInitialized'])
        self.assertEqual(assignment['attributes']['field_states_after']['y']['initialization'], ['Uninitialized'])
        self.rejected('mut Point point; point.x=1; return point.y;', 'uninitialized_read')
        doc = self.valid('mut Point point; point.x=1; point.y=2; return point.y;')
        assignments = [o for o in self.ops(doc) if o['kind'] == 'assign']
        self.assertEqual(assignments[-1]['attributes']['aggregate_state_after']['initialization'], ['Initialized'])

    def test_branch_joins_require_each_field_on_every_incoming_path(self):
        self.valid('mut Point point; if flag { point.x=1; } else { point.x=2; } return point.x;', params='bool flag')
        self.rejected('mut Point point; if flag { point.x=1; } else { point.y=2; } return point.x;', 'uninitialized_read', params='bool flag')
        self.valid('mut Point point; if true { point.x=1; } return point.x;')

    def test_construction_requires_exactly_the_declared_fields(self):
        self.rejected('Point point=Point{x=1}; return 0;', 'missing_field_initializer')
        self.rejected('Point point=Point{x=1,x=2,y=3}; return 0;', 'duplicate_field_initializer')
        self.rejected('Point point=Point{x=1,y=2,z=3}; return 0;', 'unknown_field')
        self.rejected('Point point=Point{x=true,y=2}; return 0;', 'type_error')
        self.rejected('Point point=Point{x=1,y=2}; return point.z;', 'unknown_field')
        self.rejected('i32 number=1; return number.x;', 'invalid_field_access')

    def test_contextual_field_types_and_nominal_identity(self):
        declaration='struct Sample { i8 small; bool enabled; char letter; }'
        self.valid("Sample s=Sample{small=-128,enabled=true,letter='a'}; return 0;", declaration=declaration)
        self.rejected("Sample s=Sample{small=128,enabled=true,letter='a'}; return 0;", 'literal_range', declaration=declaration)
        self.rejected('Point point=Other{x=1,y=2}; return 0;', 'type_error',
                      declaration=self.declaration+' struct Other { i32 x; i32 y; }')

    def test_bad_initializer_does_not_establish_field_initialization(self):
        doc=self.rejected('i32 missing; Point point=Point{x=missing,y=2}; return point.y;', 'uninitialized_read')
        initialization=next(o for o in self.ops(doc) if o['kind']=='init' and 'field_states_after' in o['attributes'])
        self.assertEqual(initialization['attributes']['validation'], 'invalid')
        self.assertTrue(all(s['initialization']==['Uninitialized'] for s in initialization['attributes']['field_states_after'].values()))

    def test_struct_replacement_evaluates_rhs_before_field_updates(self):
        doc=self.valid('mut Point point=Point{x=1,y=2}; point=Point{x=point.y,y=point.x}; return point.x*10+point.y;')
        ops=self.ops(doc)
        arithmetic=[o for o in ops if o['kind']=='arithmetic_checked']
        self.assertEqual(arithmetic[-1]['attributes']['constant_value'], 21)
        assignment=next(o for o in ops if o['kind']=='assign')
        self.assertEqual(len(assignment['effects']['destruction']), 2)

    def test_named_initializers_evaluate_in_source_order(self):
        self.valid('i32 value=7; Point point=Point{y=value,x=move value}; return point.y;')
        self.rejected('i32 value=7; Point point=Point{y=move value,x=value}; return 0;', 'use_after_move')

    def test_cleanup_only_destroys_initialized_scalar_fields(self):
        doc=self.valid('mut Point point; point.x=1; return point.x;')
        destroys=[o for o in self.ops(doc) if o['kind']=='destroy']
        self.assertEqual([o['attributes']['executes_if_initialized'] for o in destroys], [False, True])
        root=next(p for p in doc['functions'][0]['places'] if not p['parent'])
        self.assertFalse(any(o['operands']==[root['id']] for o in destroys))

    def test_defer_captures_field_storage_and_reads_execution_time_value(self):
        doc=self.valid('mut Point point; defer { point.x; }; point.x=7; return 0;')
        obligation=doc['functions'][0]['cleanup_regions'][0]['defer_obligations'][0]
        field=next(p for p in doc['functions'][0]['places'] if p['field_path']==['x'])
        self.assertIn(field['id'], obligation['captured_places'])
        deferred=next(o for o in self.ops(doc) if o['kind']=='copy')
        self.assertEqual(deferred['attributes']['constant_value'], 7)
        self.rejected('mut Point point; defer { point.y; }; point.x=7; return 0;', 'uninitialized_read')

    def test_unsupported_aggregate_features_are_incomplete(self):
        for field in ('i32* pointer;', 'f64 real;'):
            doc=self.rejected('return 0;', 'unsupported_struct_field', declaration='struct Point { '+field+' }')
            self.assertEqual(doc['compilation']['result'], 'incomplete')

    def test_declaration_errors_exports_and_forward_type_resolution(self):
        self.rejected('return 0;', 'duplicate_field', declaration='struct Point { i32 x; i32 x; }')
        self.rejected('return 0;', 'duplicate_name', declaration=self.declaration+' '+self.declaration)
        source='module demo; export { Point; } fn f():i32 { Point p=Point{x=1,y=2}; return p.x; } '+self.declaration
        self.assertEqual(compile_text(source)['compilation']['result'], 'valid')
        self.rejected('return 0;', 'confusable_identifier', declaration='struct Point { i32 modern; i32 rnodern; }')

    def test_empty_struct_and_determinism(self):
        self.valid('Empty e=Empty{}; return 0;', declaration='struct Empty {}')
        source='module demo; '+self.declaration+' fn f():i32 { Point p=Point{x=1,y=2}; return p.y; }'
        self.assertEqual(dumps(compile_text(source)), dumps(compile_text(source)))

    def test_report_explains_struct_fields(self):
        doc=self.valid('mut Point point=Point{x=1,y=2}; point.x=3; return point.x;')
        html=render(doc)
        self.assertIn('Set point to Point { x = 1, y = 2 }.', html)
        self.assertIn('Set point.x to 3.', html)
        self.assertIn('Struct fields have separate initialization states', html)
        self.assertIn('Fields of point: x = Initialized; y = Initialized', html)

    def test_whole_copy_preserves_source_and_has_independent_field_identities(self):
        doc=self.valid('Point source=Point{x=1,y=2}; mut Point copied=source; copied.x=9; return source.x*10+copied.x;')
        copy=next(o for o in self.ops(doc) if o['kind']=='copy' and 'result_field_states' in o['attributes'])
        self.assertEqual(copy['attributes']['field_states_before'], copy['attributes']['field_states_after'])
        for name in ('x','y'):
            self.assertNotEqual(copy['attributes']['field_states_before'][name]['object_identities'],
                                copy['attributes']['result_field_states'][name]['object_identities'])
        self.assertEqual([o for o in self.ops(doc) if o['kind']=='arithmetic_checked'][-1]['attributes']['constant_value'], 19)

    def test_whole_move_transfers_field_identities_and_skips_source_cleanup(self):
        doc=self.valid('Point source=Point{x=1,y=2}; Point moved=move source; return moved.y;')
        move=next(o for o in self.ops(doc) if o['kind']=='move')
        self.assertEqual(move['attributes']['state_after']['initialization'], ['Moved'])
        for name in ('x','y'):
            self.assertEqual(move['attributes']['field_states_before'][name]['object_identities'],
                             move['attributes']['result_field_states'][name]['object_identities'])
            self.assertEqual(move['attributes']['field_states_after'][name]['initialization'], ['Moved'])
        destroys=[o for o in self.ops(doc) if o['kind']=='destroy']
        self.assertEqual([o['attributes']['executes_if_initialized'] for o in destroys], [True, True, False, False])
        self.assertIn('Move source into moved.', render(doc))

    def test_moved_struct_and_its_fields_are_unavailable(self):
        for use in ('return source.x;', 'Point another=source; return 0;', 'Point another=move source; return 0;'):
            with self.subTest(use=use):
                self.rejected('Point source=Point{x=1,y=2}; Point moved=move source; '+use, 'use_after_move')

    def test_partial_initialization_cannot_be_copied_or_moved(self):
        for transfer in ('source', 'move source'):
            doc=self.rejected('mut Point source; source.x=7; Point target='+transfer+'; return source.x;', 'uninitialized_read')
            op=next(o for o in self.ops(doc) if o['kind'] in ('copy','move') and o['attributes']['validation']=='invalid')
            self.assertEqual(op['attributes']['field_states_before'], op['attributes']['field_states_after'])
            self.assertEqual(op['effects'], {})

    def test_whole_transfer_requires_all_branch_states(self):
        self.rejected('Point source=Point{x=1,y=2}; if flag { Point moved=move source; } Point copied=source; return 0;',
                      'use_after_move', params='bool flag')
        self.valid('mut Point source=Point{x=1,y=2}; if flag { Point moved=move source; } source=Point{x=3,y=4}; Point copied=source; return copied.x;',
                   params='bool flag')

    def test_reinitialization_after_move_restores_fields(self):
        self.valid('mut Point source=Point{x=1,y=2}; Point moved=move source; source=moved; return source.y;')
        doc=self.valid('mut Point source=Point{x=1,y=2}; Point moved=move source; source.x=3; source.y=4; Point again=move source; return again.y;')
        moves=[o for o in self.ops(doc) if o['kind']=='move']
        self.assertNotEqual(moves[0]['attributes']['object_identities'], moves[1]['attributes']['object_identities'])
        self.rejected('mut Point source=Point{x=1,y=2}; Point moved=move source; source.x=3; Point again=source; return 0;', 'use_after_move')

    def test_copy_and_move_assignment_replace_destination_after_rhs(self):
        for rhs in ('source', 'move source'):
            doc=self.valid('Point source=Point{x=1,y=2}; mut Point target=Point{x=3,y=4}; target='+rhs+'; return target.x;')
            assignment=next(o for o in self.ops(doc) if o['kind']=='assign')
            self.assertEqual(len(assignment['effects']['destruction']), 2)
        self.valid('mut Point point=Point{x=1,y=2}; point=point; point=move point; return point.x;')
        self.rejected('Point source=Point{x=1,y=2}; Point target=Point{x=3,y=4}; target=source; return 0;', 'immutable_assignment')

    def test_deferred_whole_value_use_observes_moves_and_reinitialization(self):
        self.rejected('Point source=Point{x=1,y=2}; defer { source; }; Point moved=move source; return 0;', 'use_after_move')
        self.valid('mut Point source=Point{x=1,y=2}; defer { source; }; Point moved=move source; source=Point{x=3,y=4}; return 0;')

    def test_empty_structs_and_piecewise_initialized_structs_transfer(self):
        self.valid('Empty source=Empty{}; Empty copied=source; Empty moved=move source; return 0;', declaration='struct Empty {}')
        self.rejected('Empty source; Empty copied=source; return 0;', 'uninitialized_read', declaration='struct Empty {}')
        self.rejected('Empty source=Empty{}; Empty moved=move source; Empty copied=source; return 0;', 'use_after_move', declaration='struct Empty {}')
        self.valid('mut Point source; source.x=1; source.y=2; Point copied=source; Point moved=move source; return copied.x+moved.y;')

    def test_struct_transfer_is_nominal_and_deterministic(self):
        self.rejected('Other source=Other{x=1,y=2}; Point target=source; return 0;', 'type_error',
                      declaration=self.declaration+' struct Other { i32 x; i32 y; }')
        body='Point source=Point{x=1,y=2}; Point copied=source; Point moved=move source; return copied.x+moved.y;'
        self.assertEqual(dumps(self.compile(body)), dumps(self.compile(body)))

    def test_discarded_move_cleans_up_temporary_fields_only(self):
        doc=self.valid('Point source=Point{x=1,y=2}; move source; return 0;')
        discard=next(o for o in self.ops(doc) if o['kind']=='discard')
        self.assertEqual(len(discard['effects']['destruction']), 2)
        self.assertTrue(all(not o['attributes']['executes_if_initialized'] for o in self.ops(doc) if o['kind']=='destroy'))

    def test_partial_move_keeps_sibling_and_transfers_only_field_identity(self):
        doc=self.valid('Point point=Point{x=1,y=2}; i32 taken=move point.x; return point.y+taken;')
        move=next(o for o in self.ops(doc) if o['kind']=='move')
        self.assertEqual(move['attributes']['aggregate_state_after']['ownership'], ['PartiallyMoved'])
        self.assertEqual(move['attributes']['aggregate_state_after']['initialization'], ['PartiallyInitialized'])
        self.assertEqual(move['attributes']['object_identities'], move['attributes']['state_before']['object_identities'])
        self.assertEqual(move['attributes']['field_states_after']['x']['initialization'], ['Moved'])
        self.assertEqual(move['attributes']['field_states_after']['y'], move['attributes']['field_states_before']['y'])

    def test_partial_move_prevents_field_and_whole_value_use(self):
        for use in ('return point.x;', 'i32 again=move point.x; return 0;',
                    'Point copied=point; return 0;', 'Point transferred=move point; return 0;'):
            with self.subTest(use=use):
                self.rejected('Point point=Point{x=1,y=2}; i32 taken=move point.x; '+use, 'use_after_move')

    def test_field_reinitialization_restores_whole_value(self):
        self.valid('mut Point point=Point{x=1,y=2}; i32 taken=move point.x; point.x=3; Point copied=point; return copied.x;')
        self.rejected('Point point=Point{x=1,y=2}; i32 taken=move point.x; point.x=3; return 0;', 'immutable_assignment')
        self.rejected('mut Point point=Point{x=1,y=2}; i32 taken=move point.x; point.y=3; Point copied=point; return 0;', 'use_after_move')

    def test_partial_move_cleanup_is_guarded_per_field(self):
        doc=self.valid('Point point=Point{x=1,y=2}; i32 taken=move point.x; return point.y;')
        names={s['place']:s['name'] for s in doc['symbols'] if 'place' in s}
        guards={names[o['operands'][0]]:o['attributes']['executes_if_initialized'] for o in self.ops(doc) if o['kind']=='destroy'}
        self.assertEqual(guards, {'taken':True, 'point.x':False, 'point.y':True})

    def test_partial_move_branch_joins(self):
        self.valid('Point point=Point{x=1,y=2}; if flag { i32 taken=move point.x; } return point.y;', params='bool flag')
        self.rejected('Point point=Point{x=1,y=2}; if flag { i32 taken=move point.x; } return point.x;', 'use_after_move', params='bool flag')
        self.valid('mut Point point=Point{x=1,y=2}; if flag { i32 taken=move point.x; } point.x=3; Point copied=point; return copied.y;', params='bool flag')

    def test_disjoint_mutable_field_borrows(self):
        doc=self.valid('mut Point point=Point{x=1,y=2}; mut i32* left=&mut point.x; mut i32* right=&mut point.y; *left=3; *right=4; return point.x+point.y;')
        caps=doc['functions'][0]['capabilities']
        self.assertEqual(len({c['referent'] for c in caps}), 2)
        self.assertTrue(any(not c['overlap'] for o in self.ops(doc) for c in o['attributes'].get('overlap_checks', [])))
        self.assertTrue(any(f.startswith('disjoint(') for o in self.ops(doc) for f in o['facts_established']))
        self.assertEqual(next(o for o in self.ops(doc) if o['kind']=='arithmetic_checked')['attributes']['constant_value'], 7)

    def test_same_field_borrows_conflict(self):
        for second in ('i32* right=&point.x;', 'mut i32* right=&mut point.x;'):
            with self.subTest(second=second):
                self.rejected('mut Point point=Point{x=1,y=2}; mut i32* left=&mut point.x; '+second+' return *left+*right;', 'borrow_conflict')
        self.valid('Point point=Point{x=1,y=2}; i32* left=&point.x; i32* right=&point.x; return *left+*right;')

    def test_field_borrow_requires_available_mutable_storage(self):
        self.rejected('Point point=Point{x=1,y=2}; mut i32* pointer=&mut point.x; return 0;', 'borrow_conflict')
        self.rejected('mut Point point; point.y=2; i32* pointer=&point.x; return 0;', 'invalid_borrow')
        self.rejected('Point point=Point{x=1,y=2}; i32 taken=move point.x; i32* pointer=&point.x; return 0;', 'invalid_borrow')
        self.valid('mut Point point; point.y=2; i32* pointer=&point.y; return *pointer;')

    def test_borrowed_field_allows_disjoint_read_write_and_move(self):
        self.valid('mut Point point=Point{x=1,y=2}; mut i32* pointer=&mut point.x; point.y=3; i32 taken=move point.y; *pointer=4; return *pointer+taken;')
        self.valid('Point point=Point{x=1,y=2}; i32 taken=move point.x; i32* pointer=&point.y; return *pointer;')

    def test_whole_value_overlap_with_live_field_borrow(self):
        for operation in ('Point moved=move point;', 'point=Point{x=3,y=4};', 'i32 taken=move point.x;', 'point.x=3;'):
            with self.subTest(operation=operation):
                doc=self.rejected('mut Point point=Point{x=1,y=2}; i32* pointer=&point.x; '+operation+' return *pointer;', 'borrow_conflict')
                invalid=next(o for o in self.ops(doc) if o['attributes']['validation']=='invalid')
                if 'field_states_before' in invalid['attributes']:
                    self.assertEqual(invalid['attributes']['field_states_before'],invalid['attributes']['field_states_after'])
        self.rejected('mut Point point=Point{x=1,y=2}; mut i32* pointer=&mut point.x; Point copied=point; return *pointer;', 'borrow_conflict')
        self.valid('Point point=Point{x=1,y=2}; i32* pointer=&point.x; Point copied=point; return *pointer+copied.y;')

    def test_last_field_use_releases_whole_value(self):
        self.valid('Point point=Point{x=1,y=2}; i32* pointer=&point.x; i32 saved=*pointer; Point moved=move point; return moved.y+saved;')

    def test_field_reborrow_suspension_and_resumption(self):
        doc=self.valid('mut Point point=Point{x=1,y=2}; mut i32* pointer=&mut point.x; i32* shared=&*pointer; i32 saved=*shared; point.y=3; *pointer=4; return point.x;')
        self.assertTrue(any('Suspended' in o['attributes'].get('capability_state_after',{}).values() for o in self.ops(doc)))
        self.rejected('mut Point point=Point{x=1,y=2}; mut i32* pointer=&mut point.x; i32* shared=&*pointer; *pointer=4; return *shared;', 'borrow_conflict')

    def test_field_borrow_calls_preserve_overlap_and_mutation_checks(self):
        declarations=self.declaration+' fn use(mut i32* first, mut i32* second) { *first=3; *second=4; }'
        self.valid('mut Point point=Point{x=1,y=2}; use(&mut point.x,&mut point.y); return point.x;', declaration=declarations)
        self.rejected('mut Point point=Point{x=1,y=2}; use(&mut point.x,&mut point.x); return 0;', 'borrow_conflict', declaration=declarations)

    def test_field_borrow_lifetime_is_contained_in_aggregate(self):
        doc=self.valid('Point point=Point{x=1,y=2}; i32* pointer=&point.x; return *pointer;')
        fn=doc['functions'][0]; cap=fn['capabilities'][0]
        places={p['id']:p for p in fn['places']}; lives={l['id']:l for l in fn['lifetimes']}
        field=places[cap['referent']]
        self.assertEqual(lives[cap['lifetime']]['parent'],field['lifetime'])
        self.assertEqual(lives[field['lifetime']]['parent'],places[field['parent']]['lifetime'])
        source='module demo; '+self.declaration+' fn escape():i32* { Point point=Point{x=1,y=2}; return &point.x; }'
        self.assertIn('lifetime_violation',[d['code'] for d in compile_text(source)['diagnostics']])

    def test_deferred_field_borrows_and_moves(self):
        self.valid('Point point=Point{x=1,y=2}; defer { point.y; }; i32 taken=move point.x; return 0;')
        self.rejected('Point point=Point{x=1,y=2}; defer { point.x; }; i32 taken=move point.x; return 0;', 'use_after_move')
        self.valid('mut Point point=Point{x=1,y=2}; defer { point.x; }; i32 taken=move point.x; point.x=3; return 0;')
        self.rejected('Point point=Point{x=1,y=2}; i32* pointer=&point.x; defer { *pointer; }; Point moved=move point; return 0;', 'borrow_conflict')

    def test_borrowed_field_aliases_retain_same_overlap(self):
        self.rejected('mut Point point=Point{x=1,y=2}; i32* first=&point.x; i32* copied=first; point.x=3; return *copied;', 'borrow_conflict')
        self.valid('mut Point first=Point{x=1,y=2}; mut Point second=Point{x=3,y=4}; mut i32* left=&mut first.x; mut i32* right=&mut second.x; *left=5; *right=6; return *left+*right;')

    def test_field_borrow_branch_liveness(self):
        self.rejected('mut Point point=Point{x=1,y=2}; i32* pointer=&point.x; if flag { point.x=3; } return *pointer;', 'borrow_conflict', params='bool flag')
        self.valid('mut Point point=Point{x=1,y=2}; i32* pointer=&point.x; if flag { return *pointer; } point.x=3; return point.x;', params='bool flag')

    def test_field_call_return_keeps_original_referent(self):
        declarations=self.declaration+' fn identity(i32* pointer):i32* { return pointer; }'
        self.rejected('mut Point point=Point{x=1,y=2}; i32* pointer=identity(&point.x); point=Point{x=3,y=4}; return *pointer;', 'borrow_conflict', declaration=declarations)
        self.valid('Point point=Point{x=1,y=2}; i32* pointer=identity(&point.x); i32 taken=move point.y; return *pointer+taken;', declaration=declarations)

    def test_partial_field_report_and_determinism(self):
        body='mut Point point=Point{x=1,y=2}; i32 taken=move point.x; point.x=3; mut i32* left=&mut point.x; mut i32* right=&mut point.y; *left=4; return *right;'
        doc=self.valid(body)
        html=render(doc)
        self.assertIn('Move point.x into taken.', html)
        self.assertIn('Moving a field leaves the other fields available', html)
        self.assertIn('Disjoint storage', html)
        self.assertIn('PartiallyMoved', html)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))

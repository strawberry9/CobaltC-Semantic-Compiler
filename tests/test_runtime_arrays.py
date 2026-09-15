import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps,validate
from cobalt.explain import render

class RuntimeArrayTests(unittest.TestCase):
    def compile(self,body,params='i32 index',functions=''):
        return compile_text('module demo; '+functions+' fn test('+params+'):i32 { '+body+' }')
    def valid(self,body,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics']);validate(doc);return doc
    def reject(self,body,code,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertIn(code,[d['code'] for d in doc['diagnostics']],doc['diagnostics']);validate(doc);return doc
    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def test_runtime_bounds_edges_and_read(self):
        doc=self.valid('i32[2] values=[1,2]; return values[index];')
        bounds=self.ops(doc,'array_bounds')[0]
        self.assertTrue(bounds['attributes']['runtime_check'])
        block=next(b for f in doc['functions'] for b in f['blocks'] if bounds in b['operations'])
        self.assertEqual(len(block['terminator']['targets']),2)
        fail=next(b for f in doc['functions'] for b in f['blocks'] if b['id']==block['terminator']['targets'][1])
        self.assertEqual(fail['terminator']['attributes']['failure'],'bounds')
        self.assertFalse(fail['terminator']['attributes']['cleanup_guaranteed'])
        self.assertNotIn('constant_value',self.ops(doc,'array_read')[0]['attributes'])

    def test_known_variable_index_only_needs_selected_element(self):
        doc=self.valid('mut i32[2] values; values[1]=7; i32 selected=1; return values[selected];',params='')
        self.assertFalse(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['constant_value'],7)
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),1)

    def test_equality_true_edge_refines_runtime_index(self):
        doc=self.valid('mut i32[2] values; values[0]=7; if index == 0 { return values[index]; } return 0;')
        bounds=self.ops(doc,'array_bounds')[0]
        read=self.ops(doc,'array_read')[0]
        self.assertFalse(bounds['attributes']['runtime_check'])
        self.assertEqual(read['attributes']['constant_value'],7)
        self.assertEqual(len(read['attributes']['possible_elements']),1)
        terms=[b['terminator'] for f in doc['functions'] for b in f['blocks'] if b['terminator'].get('attributes',{}).get('branch_refinements')]
        self.assertEqual(terms[0]['attributes']['branch_refinements'][0]['value'],0)

    def test_equality_refinement_accepts_constant_on_left(self):
        doc=self.valid('mut i32[2] values; values[1]=8; if 1 == index { return values[index]; } return 0;')
        self.assertFalse(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['constant_value'],8)

    def test_not_equal_false_edge_refines_to_equal_value(self):
        doc=self.valid('mut i32[2] values; values[0]=9; if index != 0 { return 0; } else { return values[index]; }')
        self.assertFalse(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['constant_value'],9)

    def test_opposite_branch_does_not_receive_equality_refinement(self):
        doc=self.valid('i32[2] values=[4,5]; if index == 0 { return 0; } else { return values[index]; }')
        self.assertTrue(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_call_between_load_and_comparison_blocks_stale_refinement(self):
        functions='fn change(mut i32* pointer):i32 { *pointer=1; return 0; }'
        doc=self.valid('i32[2] values=[4,5]; if index == change(&mut index) { return values[index]; } return 0;',params='mut i32 index',functions=functions)
        self.assertTrue(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_nested_equality_refinements_compose(self):
        doc=self.valid('mut i32[2] values; values[0]=6; if index != 1 { if index == 0 { return values[index]; } } return 0;')
        self.assertFalse(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['constant_value'],6)

    def test_equality_refinement_enables_static_out_of_bounds_diagnostic(self):
        doc=self.reject('i32[2] values=[1,2]; if index == 2 { return values[index]; } return 0;','index_out_of_bounds')
        self.assertFalse(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['validation'],'unreachable')

    def test_refined_candidate_set_limits_element_move(self):
        doc=self.valid('mut i32[2] values=[3,4]; if index == 0 { i32 taken=move values[index]; return values[1]+taken; } return 0;')
        move=self.ops(doc,'array_move')[0]
        self.assertEqual(len(move['attributes']['possible_elements']),1)

    def test_refined_candidate_set_allows_disjoint_element_borrow(self):
        self.valid('mut i32[2] values=[3,4]; i32* held=&values[1]; if index == 0 { return values[index]+*held; } return 0;')

    def test_join_does_not_leak_edge_local_refinement(self):
        doc=self.valid('mut i32[2] values=[3,4]; if index == 0 { values[1]=8; } return values[index];')
        self.assertTrue(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_refinement_flows_through_whole_array_pointer_and_report(self):
        body='mut i32[2] values=[3,4]; i32[2]* pointer=&values; if index == 0 { return (*pointer)[index]; } return 0;'
        doc=self.valid(body)
        self.assertFalse(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(len(self.ops(doc,'indexed_field_borrow')[0]['attributes']['possible_elements']),1)
        html=render(doc)
        self.assertIn('Equality tests can refine',html)

    def test_less_than_true_edge_narrows_upper_candidates(self):
        doc=self.valid('i32[3] values=[1,2,3]; if index < 2 { return values[index]; } return 0;')
        self.assertTrue(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(self.ops(doc,'array_bounds')[0]['attributes']['index_range_on_success'],[0,1])
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_less_or_equal_true_edge_narrows_upper_candidates(self):
        doc=self.valid('i32[3] values=[1,2,3]; if index <= 1 { return values[index]; } return 0;')
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_greater_than_true_edge_narrows_lower_candidates(self):
        doc=self.valid('i32[3] values=[1,2,3]; if index > 0 { return values[index]; } return 0;')
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_greater_or_equal_true_edge_narrows_lower_candidates(self):
        doc=self.valid('i32[3] values=[1,2,3]; if index >= 2 { return values[index]; } return 0;')
        bounds=self.ops(doc,'array_bounds')[0]
        self.assertTrue(bounds['attributes']['runtime_check'])
        self.assertEqual(bounds['attributes']['index_range_on_success'],[2,2])
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),1)

    def test_constant_on_left_inverts_relational_operator(self):
        doc=self.valid('i32[3] values=[1,2,3]; if 1 < index { return values[index]; } return 0;')
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),1)

    def test_false_edge_inverts_relational_constraint(self):
        doc=self.valid('i32[3] values=[1,2,3]; if index < 1 { return 0; } else { return values[index]; }')
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_nested_relational_edges_prove_bounds_without_runtime_check(self):
        doc=self.valid('i32[2] values=[1,2]; if index >= 0 { if index < 2 { return values[index]; } } return 0;')
        bounds=self.ops(doc,'array_bounds')[0]
        self.assertFalse(bounds['attributes']['runtime_check'])
        self.assertEqual(bounds['attributes']['index_range_on_success'],[0,1])

    def test_relational_edge_proves_index_out_of_bounds(self):
        doc=self.reject('i32[2] values=[1,2]; if index >= 2 { return values[index]; } return 0;','index_out_of_bounds')
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['validation'],'unreachable')

    def test_range_candidates_preserve_disjoint_element_borrow(self):
        body='mut i32[3] values=[1,2,3]; i32* held=&values[2]; if index >= 0 { if index < 2 { values[index]=9; return *held; } } return 0;'
        doc=self.valid(body)
        write=self.ops(doc,'array_assign')[0]
        self.assertEqual(len(write['attributes']['possible_elements']),2)
        held=self.ops(doc,'borrow_shared')[0]['effects']['borrows'][0].split(',')[1]
        self.assertNotIn(held,write['attributes']['possible_elements'])

    def test_relational_range_flows_through_whole_array_pointer_and_explanation(self):
        body='mut i32[2] values=[1,2]; i32[2]* pointer=&values; if index >= 0 { if index < 2 { return (*pointer)[index]; } } return 0;'
        doc=self.valid(body)
        self.assertFalse(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(len(self.ops(doc,'indexed_field_borrow')[0]['attributes']['possible_elements']),2)
        self.assertIn('inclusive integer ranges',render(doc))

    def test_relational_range_is_not_retained_at_join(self):
        doc=self.valid('i32[2] values=[1,2]; if index < 0 { return 0; } return values[index];')
        self.assertTrue(self.ops(doc,'array_bounds')[0]['attributes']['runtime_check'])
        self.assertEqual(len(self.ops(doc,'array_read')[0]['attributes']['possible_elements']),2)

    def test_provable_failure_and_noninteger_index(self):
        for value in ('-1','2'):
            doc=self.reject('i32[2] values=[1,2]; i32 selected='+value+'; return values[selected];','index_out_of_bounds',params='')
            self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['validation'],'unreachable')
        self.reject('i32[0] values=[]; return values[index];','index_out_of_bounds')
        self.reject('i32[2] values=[1,2]; bool selected=true; return values[selected];','type_error',params='')

    def test_unknown_read_requires_all_possible_elements(self):
        self.reject('mut i32[2] values; values[0]=1; return values[index];','uninitialized_read')
        self.reject('i32[2] values=[1,2]; i32 taken=move values[0]; return values[index];','use_after_move')
        doc=self.valid('i32[2] values=[7,7]; return values[index];')
        self.assertEqual(self.ops(doc,'array_read')[0]['attributes']['constant_value'],7)

    def test_unknown_write_does_not_initialize_every_element(self):
        doc=self.reject('mut i32[2] values; values[index]=9; return values[0];','uninitialized_read')
        write=self.ops(doc,'array_assign')[0]
        self.assertTrue(all(set(s['initialization'])=={'Initialized','Uninitialized'} for s in write['attributes']['element_states_after'].values()))
        self.valid('mut i32[2] values; values[index]=9; return 0;')

    def test_weak_write_constants_and_object_alternatives(self):
        doc=self.valid('mut i32[2] values=[1,2]; values[index]=9; return values[0];')
        write=self.ops(doc,'array_assign')[0]
        self.assertEqual(write['attributes']['target_selection'],'one_of_elements')
        for pid,after in write['attributes']['element_states_after'].items():
            self.assertTrue(set(write['attributes']['element_states_before'][pid]['object_identities']) < set(after['object_identities']))
        self.assertNotIn('constant_value',self.ops(doc,'copy')[-1]['attributes'])

    def test_single_element_narrows_after_bounds(self):
        doc=self.valid('mut i32[1] values; values[index]=9; return values[0];')
        self.assertEqual(self.ops(doc,'array_assign')[0]['attributes']['target_selection'],'definite')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],9)

    def test_write_mutability_type_and_rhs_rollback(self):
        self.reject('i32[2] values=[1,2]; values[index]=9; return 0;','immutable_assignment')
        doc=self.reject('mut i32[2] values=[1,2]; values[index]=true; return values[0];','type_error')
        write=self.ops(doc,'array_assign')[0]
        self.assertEqual(write['effects'],{})
        self.assertEqual(write['attributes']['element_states_before'],write['attributes']['element_states_after'])

    def test_unknown_access_borrow_conflicts_and_known_disjoint_access(self):
        self.reject('mut i32[2] values=[1,2]; i32* ptr=&values[0]; values[index]=9; return *ptr;','borrow_conflict')
        self.reject('mut i32[2] values=[1,2]; mut i32* ptr=&mut values[0]; i32 result=values[index]; return *ptr;','borrow_conflict')
        self.valid('mut i32[2] values=[1,2]; i32* ptr=&values[0]; i32 selected=1; values[selected]=9; return *ptr;',params='')

    def test_index_evaluated_once_before_rhs(self):
        doc=self.valid('mut i32[2] values=[1,2]; values[select()]=rhs(); return values[0];',params='',functions='fn select():i32 { return 0; } fn rhs():i32 { return 9; }')
        ops=[o for f in doc['functions'] if f['name']=='test' for b in f['blocks'] for o in b['operations']]
        calls=[o for o in ops if o['kind']=='call']
        self.assertEqual(len(calls),2)
        bounds=self.ops(doc,'array_bounds')[0]
        self.assertLess(ops.index(calls[0]),ops.index(bounds))
        self.assertLess(ops.index(bounds),ops.index(calls[1]))

    def test_unsigned_and_checked_index_expression(self):
        self.valid('i32[2] values=[1,2]; return values[index];',params='u64 index')
        self.valid('i32[2] values=[1,2]; return values[index+1];')

    def test_defers_and_dynamic_move_borrow_boundaries(self):
        self.valid('mut i32[2] values=[1,2]; defer { values[index]=9; }; return values[0];')
        self.valid('i32[2] values=[1,2]; i32 taken=move values[index]; return taken;')

    def test_dynamic_reinitialization_restores_whole_array_identity(self):
        doc=self.valid('mut i32[1] values=[1]; i32[1] moved=move values; values[index]=9; i32[1] again=move values; return again[0];')
        self.assertTrue(self.ops(doc,'move')[-1]['attributes']['object_identities'])
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],9)

    def test_report_and_determinism(self):
        body='i32[2] values=[1,2]; return values[index];'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        html=render(doc)
        self.assertIn('index is out of bounds',html)
        self.assertIn('index is in bounds',html)

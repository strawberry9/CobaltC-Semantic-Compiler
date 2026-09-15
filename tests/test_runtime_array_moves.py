import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps,validate
from cobalt.explain import render

class RuntimeArrayMoveTests(unittest.TestCase):
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

    def test_unknown_move_preserves_identity_alternatives(self):
        doc=self.valid('i32[2] values=[1,2]; return move values[index];')
        move=self.ops(doc,'array_move')[0]
        before=move['attributes']['element_states_before']
        identities={obj for s in before.values() for obj in s['object_identities']}
        self.assertEqual(set(move['attributes']['object_identities']),identities)
        self.assertEqual(move['attributes']['result_identity_selection'],'selected_element')
        for s in move['attributes']['element_states_after'].values():
            self.assertEqual(set(s['initialization']),{'Initialized','Moved'})
        self.assertEqual(move['attributes']['aggregate_state_after']['ownership'],['PartiallyMoved'])

    def test_known_move_only_consumes_selected_element(self):
        doc=self.valid('i32[2] values=[7,8]; i32 selected=0; i32 taken=move values[selected]; return values[1]+taken;',params='')
        move=self.ops(doc,'array_move')[0]
        self.assertEqual(len(move['attributes']['possible_elements']),1)
        self.assertEqual(next(iter(move['attributes']['element_states_after'].values()))['initialization'],['Moved'])
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],15)
        self.assertEqual(sum(not o['attributes']['executes_if_initialized'] for o in self.ops(doc,'destroy')),1)

    def test_unknown_move_blocks_reads_borrows_and_whole_transfers(self):
        for action in ('return values[0];','return values[index];','i32* ptr=&values[1]; return 0;','i32[2] copied=values; return 0;','i32[2] moved=move values; return 0;'):
            self.reject('i32[2] values=[1,2]; i32 taken=move values[index]; '+action,'invalid_borrow' if '&values[1]' in action else 'use_after_move')

    def test_repeated_unknown_move_rejected(self):
        self.reject('i32[2] values=[1,2]; i32 first=move values[index]; i32 second=move values[index]; return first;','use_after_move')

    def test_reinitialization_known_whole_and_all_elements(self):
        self.valid('mut i32[2] values=[1,2]; i32 selected=0; i32 taken=move values[selected]; values[selected]=9; i32[2] copied=values; return copied[0];',params='')
        self.valid('mut i32[2] values=[1,2]; i32 taken=move values[index]; values=[7,8]; i32[2] copied=values; return copied[0];')
        self.valid('mut i32[2] values=[1,2]; i32 taken=move values[index]; values[0]=7; values[1]=8; i32[2] copied=values; return copied[0];')
        self.reject('mut i32[2] values=[1,2]; i32 taken=move values[index]; values[index]=9; i32[2] copied=values; return 0;','use_after_move')

    def test_single_element_and_equal_constants(self):
        doc=self.valid('i32[1] values=[7]; return move values[index];')
        self.assertEqual(self.ops(doc,'array_move')[0]['attributes']['constant_value'],7)
        move=self.ops(doc,'array_move')[0]
        targets=move['attributes']['possible_elements']
        destroys=[o for o in self.ops(doc,'destroy') if o['operands'][0] in targets]
        self.assertEqual(len(destroys),1)
        self.assertFalse(destroys[0]['attributes']['executes_if_initialized'])
        doc=self.valid('i32[2] values=[7,7]; return move values[index];')
        self.assertEqual(self.ops(doc,'array_move')[0]['attributes']['constant_value'],7)

    def test_permission_conflicts_and_failed_move_rollback(self):
        doc=self.reject('i32[2] values=[1,2]; i32* ptr=&values[0]; i32 taken=move values[index]; return *ptr;','borrow_conflict')
        move=self.ops(doc,'array_move')[0]
        self.assertEqual(move['effects'],{})
        self.assertEqual(move['attributes']['element_states_before'],move['attributes']['element_states_after'])
        self.valid('i32[2] values=[1,2]; i32* ptr=&values[0]; i32 selected=1; i32 taken=move values[selected]; return *ptr+taken;',params='')
        self.valid('i32[2] values=[1,2]; i32* ptr=&values[0]; i32 saved=*ptr; return move values[index];')

    def test_bounds_and_uninitialized_candidates(self):
        doc=self.reject('i32[2] values=[1,2]; i32 selected=2; return move values[selected];','index_out_of_bounds',params='')
        self.assertEqual(self.ops(doc,'array_move')[0]['attributes']['validation'],'unreachable')
        self.reject('i32[0] values=[]; return move values[index];','index_out_of_bounds')
        self.reject('mut i32[2] values; values[0]=1; return move values[index];','uninitialized_read')

    def test_cleanup_is_guarded_for_each_possible_moved_element(self):
        doc=self.valid('i32[2] values=[1,2]; i32 taken=move values[index]; return taken;')
        destroys=[o for o in self.ops(doc,'destroy') if 'Moved' in o['attributes']['state_before']['initialization']]
        self.assertEqual(len(destroys),2)
        self.assertTrue(all(o['attributes']['guard']=='initialized_and_owned' for o in destroys))
        self.assertTrue(all(o['attributes']['executes_if_initialized'] for o in destroys))

    def test_defer_and_branch_move_tracking(self):
        self.reject('i32[2] values=[1,2]; defer { values[0]; }; return move values[index];','use_after_move')
        self.valid('mut i32[2] values=[1,2]; defer { values[0]; }; i32 taken=move values[index]; values=[7,8]; return taken;')
        self.reject('i32[2] values=[1,2]; if(flag) { i32 taken=move values[index]; } return values[0];','use_after_move',params='i32 index,bool flag')

    def test_call_arguments_and_index_evaluated_once(self):
        doc=self.valid('i32[2] values=[1,2]; return consume(move values[select()]);',params='',functions='fn select():i32 { return 0; } fn consume(i32 value):i32 { return value; }')
        self.assertEqual(len(self.ops(doc,'array_move')),1)
        self.assertEqual(len(self.ops(doc,'call')),2)

    def test_deterministic_explanation(self):
        body='i32[2] values=[1,2]; return move values[index];'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('possibly moved',render(doc))

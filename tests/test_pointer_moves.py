import unittest

from cobalt.driver import compile_text
from cobalt.esir import validate


class ManagedPointerMoveTests(unittest.TestCase):
    declaration='struct Point { i32 x; i32 y; } '

    def compile(self,body):
        doc=compile_text('module demo; '+self.declaration+f'fn test():i32 {{ {body} }}')
        validate(doc);return doc

    def valid(self,body):
        doc=self.compile(body)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc

    def ops(self,doc,kind):
        return [op for fn in doc['functions'] for block in fn['blocks']
                for op in block['operations'] if op['kind']==kind]

    def test_scalar_referent_move_and_reinitialization(self):
        doc=self.valid('mut i32 value=7; mut i32* pointer=&mut value; '
                       'i32 taken=move *pointer; *pointer=9; return taken+*pointer;')
        move=self.ops(doc,'deref_move')[0]
        self.assertEqual(move['attributes']['result_ownership'],'Owned')
        self.assertEqual(move['attributes']['target_selection'],'definite')
        self.assertTrue(any('move_referent_if_selected' in effect for effect in move['effects']['initialization']))
        self.assertEqual(self.ops(doc,'deref_assign')[0]['attributes']['validation'],'valid')

    def test_whole_struct_move_preserves_fields_and_replacement_restores_them(self):
        doc=self.valid('mut Point point=Point { x=7,y=8 }; mut Point* pointer=&mut point; '
                       'Point old=move *pointer; *pointer=Point { x=3,y=4 }; return old.x+pointer->x;')
        move=self.ops(doc,'deref_move')[0]
        self.assertEqual(set(move['attributes']['result_field_states']),{'x','y'})
        after=move['attributes']['referent_states_after']
        ref=move['attributes']['struct_referents'][0]
        self.assertTrue(all(state['aggregate']['initialization']==['Moved'] for state in after.values()))
        assignment=self.ops(doc,'deref_assign')[0]
        self.assertEqual(assignment['attributes']['referent_states_after'][ref]['aggregate']['initialization'],['Initialized'])
        self.assertFalse(assignment['effects'].get('destruction'))

    def test_projected_field_move_and_reinitialization(self):
        doc=self.valid('mut Point point=Point { x=7,y=8 }; mut Point* pointer=&mut point; '
                       'i32 taken=move pointer->x; pointer->x=9; return taken+pointer->x;')
        self.assertEqual(self.ops(doc,'deref_move')[0]['attributes']['validation'],'valid')
        field=next(op for op in self.ops(doc,'field_borrow') if op['attributes'].get('allow_moved_for_assignment'))
        self.assertEqual(field['attributes']['validation'],'valid')
        self.assertEqual(self.ops(doc,'deref_assign')[0]['attributes']['validation'],'valid')

    def test_shared_pointer_cannot_move(self):
        doc=self.compile('i32 value=7; i32* pointer=&value; i32 taken=move *pointer; return taken;')
        self.assertIn('borrow_conflict',[diag['code'] for diag in doc['diagnostics']])

    def test_alternative_pointer_targets_record_conditional_moves(self):
        functions=('fn choose(bool flag,mut i32* first,mut i32* second):mut i32* { '
                   'if(flag) { return move first; } return move second; } ')
        source=('module demo; '+functions+
                'fn test(bool flag):i32 { mut i32 first=1; mut i32 second=2; '
                'mut i32* pointer=choose(flag,&mut first,&mut second); '
                'return move *pointer; }')
        doc=compile_text(source);validate(doc)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        move=self.ops(doc,'deref_move')[0]
        self.assertEqual(move['attributes']['target_selection'],'one_of_referents')
        self.assertEqual(len(move['attributes']['referent_states_before']),2)
        self.assertTrue(all(state['initialization']==['Initialized']
                            for state in move['attributes']['referent_states_before'].values()))
        self.assertTrue(all(state['initialization']==['Initialized','Moved']
                            for state in move['attributes']['referent_states_after'].values()))

    def test_unknown_target_move_blocks_every_candidate_owner_read(self):
        functions=('fn choose(bool flag,mut i32* first,mut i32* second):mut i32* { '
                   'if(flag) { return move first; } return move second; } ')
        source=('module demo; '+functions+
                'fn test(bool flag):i32 { mut i32 first=1; mut i32 second=2; '
                'mut i32* pointer=choose(flag,&mut first,&mut second); '
                'i32 taken=move *pointer; return first+second+taken; }')
        doc=compile_text(source);validate(doc)
        self.assertGreaterEqual(sum(diag['code']=='use_after_move' for diag in doc['diagnostics']),2)


if __name__=='__main__':
    unittest.main()

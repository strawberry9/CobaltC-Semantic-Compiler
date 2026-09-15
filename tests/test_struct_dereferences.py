import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class StructDereferenceTests(unittest.TestCase):
    prefix = 'module demo; struct Point { i32 x; i32 y; } '

    def compile(self, body, functions='', params=''):
        return compile_text(self.prefix+functions+' fn test('+params+'):i32 { '+body+' }')

    def valid(self, body, **kwargs):
        doc=self.compile(body, **kwargs)
        self.assertEqual(doc['compilation']['result'], 'valid', doc['diagnostics'])
        validate(doc)
        return doc

    def rejected(self, body, code, **kwargs):
        doc=self.compile(body, **kwargs)
        self.assertIn(code, [d['code'] for d in doc['diagnostics']])
        validate(doc)
        return doc

    def ops(self, doc, kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def test_copy_has_independent_fields_and_preserves_source(self):
        doc=self.valid('mut Point p=Point{x=3,y=5}; Point* ptr=&p; mut Point copied=*ptr; copied.x=9; return p.x+copied.x;')
        read=self.ops(doc, 'deref_read')[0]
        self.assertEqual(read['attributes']['referent_states_before'],read['attributes']['referent_states_after'])
        before=next(iter(read['attributes']['referent_states_before'].values()))['fields']
        for name, field in read['attributes']['result_field_states'].items():
            self.assertNotEqual(field['object_identities'], before[name]['object_identities'])
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],12)

    def test_replace_then_project_and_copy(self):
        doc=self.valid('mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; *ptr=Point{x=7,y=8}; Point copied=*ptr; return copied.x+ptr->y;')
        write=self.ops(doc,'deref_assign')[0]
        self.assertEqual(len(write['effects']['destruction']),2)
        self.assertEqual(write['attributes']['target_selection'],'definite')
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],15)

    def test_self_replacement_copies_before_destruction(self):
        doc=self.valid('mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; *ptr=*ptr; return ptr->x;')
        read=self.ops(doc,'deref_read')[0]
        write=self.ops(doc,'deref_assign')[0]
        after=next(iter(write['attributes']['referent_states_after'].values()))['fields']
        self.assertEqual(after,read['attributes']['result_field_states'])
        self.assertEqual(self.ops(doc,'deref_read')[-1]['attributes']['constant_value'],1)

    def test_move_rhs_transfers_fields_and_source_cleanup_skips(self):
        doc=self.valid('mut Point p=Point{x=1,y=2}; Point source=Point{x=7,y=8}; mut Point* ptr=&mut p; *ptr=move source; return ptr->x;')
        move=self.ops(doc,'move')[0]
        after=next(iter(self.ops(doc,'deref_assign')[0]['attributes']['referent_states_after'].values()))['fields']
        self.assertEqual(after,move['attributes']['result_field_states'])
        self.assertEqual(sum(not o['attributes']['executes_if_initialized'] for o in self.ops(doc,'destroy')),3)

    def test_shared_write_and_live_field_conflicts(self):
        self.rejected('Point p=Point{x=1,y=2}; Point* ptr=&p; *ptr=Point{x=3,y=4}; return 0;', 'borrow_conflict')
        for action in ('*ptr=Point{x=3,y=4};', 'Point copied=*ptr;'):
            self.rejected('mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; mut i32* field=&mut ptr->x; '+action+' return *field;', 'borrow_conflict')
        self.valid('mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; i32* field=&ptr->x; Point copied=*ptr; return *field+copied.y;')

    def test_invalid_rhs_preserves_destination_and_has_no_destruction(self):
        doc=self.rejected('mut Point p=Point{x=1,y=2}; Point source=Point{x=7,y=8}; i32 old=move source.x; mut Point* ptr=&mut p; *ptr=move source; return ptr->x;', 'use_after_move')
        write=self.ops(doc,'deref_assign')[0]
        self.assertEqual(write['effects'],{})
        self.assertEqual(write['attributes']['referent_states_before'],write['attributes']['referent_states_after'])
        self.assertEqual(self.ops(doc,'deref_read')[-1]['attributes']['constant_value'],1)
        self.rejected('mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; *ptr=3; return 0;', 'type_error')

    def test_copy_parameter_return_call_argument_and_discard(self):
        self.valid('mut Point p=Point{x=1,y=2}; Point copied=clone(&p); replace(&mut p, copied); return sum(*(&p));',
                   functions='fn clone(Point* ptr):Point { return *ptr; } fn replace(mut Point* ptr, Point value):void { *ptr=move value; } fn sum(Point value):i32 { return value.x+value.y; }')
        doc=self.valid('Point p=Point{x=1,y=2}; Point* ptr=&p; *ptr; return 0;')
        self.assertEqual(len(self.ops(doc,'discard')[0]['effects']['destruction']),2)

    def test_alternative_referents_weak_updates(self):
        doc=self.valid('mut Point first=Point{x=1,y=2}; mut Point second=Point{x=3,y=2}; mut Point* ptr=select(&mut first,&mut second,flag); *ptr=Point{x=9,y=2}; return first.x+second.y;', params='bool flag',
                       functions='fn select(mut Point* first, mut Point* second, bool flag):mut Point* { if (flag) { return first; } return second; }')
        write=self.ops(doc,'deref_assign')[0]
        self.assertEqual(write['attributes']['target_selection'],'one_of_referents')
        self.assertEqual(len(write['attributes']['referent_states_after']),2)
        for root, after in write['attributes']['referent_states_after'].items():
            before=write['attributes']['referent_states_before'][root]
            for name, field in after['fields'].items():
                self.assertTrue(set(before['fields'][name]['object_identities']) < set(field['object_identities']))
        self.assertNotIn('constant_value',self.ops(doc,'arithmetic_checked')[-1]['attributes'])

    def test_alternative_shared_copy_constants(self):
        doc=self.valid('Point first=Point{x=1,y=2}; Point second=Point{x=3,y=2}; Point* ptr=select(&first,&second,flag); Point copied=*ptr; return copied.y;', params='bool flag',
                       functions='fn select(Point* first, Point* second, bool flag):Point* { if (flag) { return first; } return second; }')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],2)

    def test_defer_and_empty_struct(self):
        self.valid('mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; defer { *ptr=Point{x=3,y=4}; }; return ptr->x;')
        self.valid('mut Empty value=Empty{}; mut Empty* ptr=&mut value; *ptr=*ptr; Empty copied=*ptr; return 0;', functions='struct Empty {}')

    def test_moves_out_transfer_fields_and_report_deterministic(self):
        moved=self.valid('mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; '
                         'Point copied=move *ptr; return copied.x;')
        operation=self.ops(moved,'deref_move')[0]
        self.assertEqual(operation['attributes']['target_selection'],'definite')
        self.assertTrue(all(state['aggregate']['initialization']==['Moved']
                            for state in operation['attributes']['referent_states_after'].values()))
        body='mut Point p=Point{x=1,y=2}; mut Point* ptr=&mut p; *ptr=*ptr; return ptr->x;'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('whole struct', render(doc))

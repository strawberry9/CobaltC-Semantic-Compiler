import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render

class NestedStructTests(unittest.TestCase):
    prefix='module demo; struct Point { i32 x; i32 y; } struct Rect { Point start; Point end; } '
    init='mut Rect rect=Rect{start=Point{x=1,y=2},end=Point{x=3,y=4}}; '

    def compile(self, body, functions='', params=''):
        return compile_text(self.prefix+functions+' fn test('+params+'):i32 { '+body+' }')

    def valid(self, body, **kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        validate(doc)
        return doc

    def reject(self, body, code, **kwargs):
        doc=self.compile(body,**kwargs)
        self.assertIn(code,[d['code'] for d in doc['diagnostics']],doc['diagnostics'])
        validate(doc)
        return doc

    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def test_construct_paths_lifetimes_and_copy_independence(self):
        doc=self.valid(self.init+'mut Rect copied=rect; copied.start.x=9; return rect.start.x+copied.start.x;')
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],10)
        fn=doc['functions'][0]
        leaf=next(p for p in fn['places'] if p['field_path']==['start','x'])
        parent=next(p for p in fn['places'] if p['id']==leaf['parent'])
        life=next(l for l in fn['lifetimes'] if l['id']==leaf['lifetime'])
        self.assertEqual(life['parent'],parent['lifetime'])
        copied=next(o for o in self.ops(doc,'copy') if 'result_field_states' in o['attributes'])
        self.assertEqual(set(copied['attributes']['result_field_states']),{'start','start.x','start.y','end','end.x','end.y'})
        for path,state in copied['attributes']['result_field_states'].items():
            self.assertNotEqual(state['object_identities'],copied['attributes']['field_states_before'][path]['object_identities'])

    def test_forward_definitions_and_cycle_diagnostics(self):
        source='module demo; struct Box { Point point; } struct Point { i32 x; } fn test():i32 { Box box=Box{point=Point{x=7}}; return box.point.x; }'
        self.assertEqual(compile_text(source)['compilation']['result'],'valid')
        for definitions in ('struct Cycle { Cycle child; }','struct First { Second child; } struct Second { First child; }'):
            doc=compile_text('module demo; '+definitions+' fn test():i32 { return 0; }')
            self.assertIn('unsupported_recursive_struct',[d['code'] for d in doc['diagnostics']])
            validate(doc)

    def test_nested_partial_initialization_and_branch_join(self):
        self.valid('mut Rect rect; rect.start.x=1; rect.start.y=2; rect.end=Point{x=3,y=4}; Rect copied=rect; return copied.end.y;')
        self.reject('mut Rect rect; rect.start.x=1; Rect copied=rect; return 0;','uninitialized_read')
        self.reject('mut Rect rect; rect.start=Point{x=1,y=2}; if(flag) { rect.end=Point{x=3,y=4}; } Rect copied=rect; return 0;','uninitialized_read',params='bool flag')

    def test_substruct_move_and_reinitialization(self):
        doc=self.valid(self.init+'Point taken=move rect.start; i32 saved=rect.end.x; rect.start=Point{x=7,y=8}; Rect copied=rect; return copied.start.x+saved;')
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],10)
        self.reject(self.init+'Point taken=move rect.start; Rect copied=rect; return 0;','use_after_move')
        self.reject(self.init+'Point taken=move rect.start; return rect.start.x;','use_after_move')

    def test_deep_leaf_move_propagates_and_cleanup_skips_only_leaf(self):
        doc=self.valid(self.init+'i32 taken=move rect.start.x; return rect.end.y;')
        destroys=self.ops(doc,'destroy')
        self.assertEqual(sum(o['attributes']['executes_if_initialized'] for o in destroys),4)
        self.assertEqual(sum(not o['attributes']['executes_if_initialized'] for o in destroys),1)
        self.reject(self.init+'i32 taken=move rect.start.x; Rect copied=rect; return 0;','use_after_move')
        self.valid(self.init+'i32 taken=move rect.start.x; rect.start.x=9; Rect copied=rect; return copied.start.x;')

    def test_replacement_destroys_leaves_not_intermediate_structs(self):
        doc=self.valid(self.init+'rect=Rect{start=Point{x=5,y=6},end=Point{x=7,y=8}}; return rect.end.y;')
        assign=self.ops(doc,'assign')[0]
        self.assertEqual(len(assign['effects']['destruction']),4)
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],8)

    def test_nested_borrows_disjoint_and_overlapping(self):
        self.valid(self.init+'mut i32* first=&mut rect.start.x; mut i32* second=&mut rect.start.y; *first=7; *second=8; return *first+*second;')
        self.valid(self.init+'mut Point* first=&mut rect.start; mut i32* second=&mut rect.end.x; first->x=7; *second=8; return first->x+*second;')
        self.reject(self.init+'i32* leaf=&rect.start.x; rect.start=Point{x=7,y=8}; return *leaf;','borrow_conflict')
        self.reject(self.init+'mut Point* parent=&mut rect.start; i32 value=rect.start.x; return parent->y;','borrow_conflict')

    def test_nested_pointer_projection(self):
        doc=self.valid(self.init+'mut Rect* ptr=&mut rect; ptr->start.x=8; (*ptr).end.y=9; return ptr->start.x+ptr->end.y;')
        self.assertEqual(self.ops(doc,'arithmetic_checked')[-1]['attributes']['constant_value'],17)
        self.valid(self.init+'mut Rect* ptr=&mut rect; mut i32* first=&mut ptr->start.x; mut i32* second=&mut ptr->start.y; *first=8; *second=9; return *first+*second;')
        self.reject(self.init+'mut Rect* ptr=&mut rect; i32* first=&ptr->start.x; ptr->start=Point{x=7,y=8}; return *first;','borrow_conflict')

    def test_borrowed_parameters_nested_returns_and_mutation(self):
        functions='fn select(Rect* ptr):i32* { return &ptr->start.y; } fn wrap(Rect* ptr):i32* { return select(ptr); }'
        doc=self.valid(self.init+'i32* value=wrap(&rect); return *value;',functions=functions)
        self.assertEqual(self.ops(doc,'deref_read')[-1]['attributes']['constant_value'],2)
        self.valid(self.init+'update(&mut rect); return rect.start.x;',functions='fn update(mut Rect* ptr):void { ptr->start.x=9; }')
        self.reject('return 0;','lifetime_violation',functions='fn bad():i32* { Rect local=Rect{start=Point{x=1,y=2},end=Point{x=3,y=4}}; return &local.start.x; }')

    def test_by_value_call_return_and_pointer_copy_replace(self):
        self.valid(self.init+'Rect copied=identity(rect); mut Rect* ptr=&mut rect; *ptr=move copied; Rect final_value=*ptr; return final_value.start.x;',functions='fn identity(Rect input):Rect { return move input; }')
        doc=self.valid(self.init+'mut Rect* ptr=&mut rect; *ptr=*ptr; return ptr->end.y;')
        self.assertEqual(len(self.ops(doc,'deref_assign')[0]['effects']['destruction']),4)
        self.assertEqual(self.ops(doc,'deref_read')[-1]['attributes']['constant_value'],4)

    def test_deferred_nested_path(self):
        doc=self.valid(self.init+'defer { rect.start.x; }; i32 taken=move rect.end.x; return 0;')
        obligation=doc['functions'][0]['cleanup_regions'][0]['defer_obligations'][0]
        leaf=next(p for p in doc['functions'][0]['places'] if p['field_path']==['start','x'])
        self.assertIn(leaf['id'],obligation['captured_places'])
        self.reject(self.init+'defer { rect.start.x; }; i32 taken=move rect.start.x; return 0;','use_after_move')

    def test_empty_nested_struct_and_three_levels(self):
        self.valid('mut Box box=Box{empty=Empty{},point=Point{x=1,y=2}}; Box copied=move box; return copied.point.x;',functions='struct Empty {} struct Box { Empty empty; Point point; }')
        self.valid('mut Box box=Box{rect=Rect{start=Point{x=1,y=2},end=Point{x=3,y=4}}}; box.rect.start.x=8; return box.rect.start.x;',functions='struct Box { Rect rect; }')

    def test_ancestor_move_state_and_reinitialized_identity(self):
        doc=self.valid(self.init+'i32 taken=move rect.start.x; rect.start.x=9; Rect moved=move rect; return moved.end.x;')
        leaf_move=self.ops(doc,'move')[0]
        ancestors=leaf_move['attributes']['ancestor_states_after']
        self.assertTrue(all(s['ownership']==['PartiallyMoved'] for s in ancestors.values()))
        doc=self.valid('mut Rect rect; rect.start=Point{x=1,y=2}; rect.end=Point{x=3,y=4}; Rect moved=move rect; return moved.start.x;')
        self.assertTrue(self.ops(doc,'move')[0]['attributes']['object_identities'])

    def test_nested_substruct_pointer_and_mutable_call_invalidation(self):
        doc=self.valid(self.init+'mut Rect* ptr=&mut rect; ptr->start=ptr->end; Point copied=ptr->start; return copied.y;')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],4)
        doc=self.valid(self.init+'update(&mut rect); return rect.start.x;',functions='fn update(mut Rect* ptr):void { ptr->start.x=9; }')
        self.assertNotIn('constant_value',self.ops(doc,'copy')[-1]['attributes'])

    def test_report_determinism_and_invalid_nested_constructor(self):
        self.reject('Rect rect=Rect{start=Point{x=1,y=2},end=3}; return 0;','type_error')
        body=self.init+'i32 taken=move rect.start.x; return rect.end.y;'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('rect.start.x',render(doc))

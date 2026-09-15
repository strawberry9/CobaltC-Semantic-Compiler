import unittest
import os
import subprocess
import sys
from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render

class RuntimeArrayBorrowTests(unittest.TestCase):
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

    def test_shared_borrow_records_alternatives_and_contained_lifetimes(self):
        doc=self.valid('i32[2] values=[7,7]; i32* ptr=&values[index]; return *ptr;')
        op=self.ops(doc,'array_borrow')[0]
        self.assertEqual(len(op['attributes']['capability_alternatives']),2)
        fn=doc['functions'][0]; caps={c['id']:c for c in fn['capabilities']}; places={p['id']:p for p in fn['places']}; lives={l['id']:l for l in fn['lifetimes']}
        for cid in op['attributes']['capability_alternatives']:
            cap=caps[cid]
            self.assertEqual(lives[cap['lifetime']]['parent'],places[cap['referent']]['lifetime'])
        self.assertEqual(self.ops(doc,'deref_read')[-1]['attributes']['constant_value'],7)

    def test_mutable_write_keeps_possible_old_values(self):
        doc=self.valid('mut i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; *ptr=9; return values[0];')
        self.assertNotIn('constant_value',self.ops(doc,'copy')[-1]['attributes'])
        self.assertEqual(len(self.ops(doc,'deref_assign')[0]['effects']['initialization']),2)
        self.reject('i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; return *ptr;','borrow_conflict')
        self.reject('i32[2] values=[1,2]; i32* ptr=&values[index]; *ptr=9; return 0;','borrow_conflict')

    def test_known_indices_and_single_element(self):
        self.valid('mut i32[2] values=[1,2]; i32 first_index=0; i32 second_index=1; mut i32* first=&mut values[first_index]; mut i32* second=&mut values[second_index]; *first=7; *second=8; return *first+*second;',params='')
        doc=self.valid('mut i32[1] values=[1]; mut i32* ptr=&mut values[index]; *ptr=9; return values[0];')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],9)

    def test_unknown_indices_cannot_be_assumed_disjoint(self):
        self.reject('mut i32[2] values=[1,2]; mut i32* first=&mut values[index]; mut i32* second=&mut values[other]; *second=9; return *first;','borrow_conflict',params='i32 index, i32 other')
        self.valid('i32[2] values=[1,2]; i32* first=&values[index]; i32* second=&values[other]; return *first+*second;',params='i32 index, i32 other')

    def test_direct_access_and_whole_array_conflicts(self):
        for action in ('values[0]=9;','values=[7,8];','i32[2] moved=move values;'):
            self.reject('mut i32[2] values=[1,2]; i32* ptr=&values[index]; '+action+' return *ptr;','borrow_conflict')
        self.reject('mut i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; i32 read=values[1]; return *ptr;','borrow_conflict')

    def test_all_candidates_available_before_borrow_creation(self):
        for prefix,code in [('mut i32[2] values; values[0]=1;','uninitialized_read'),('i32[2] values=[1,2]; i32 taken=move values[0];','use_after_move')]:
            doc=self.reject(prefix+' i32* ptr=&values[index]; return 0;',code)
            self.assertNotIn('created_capabilities',self.ops(doc,'array_borrow')[0]['attributes'])
        self.valid('mut i32[2] values; values[1]=7; i32 selected=1; i32* ptr=&values[selected]; return *ptr;',params='')

    def test_bounds_failures_create_no_capabilities(self):
        doc=self.reject('i32[2] values=[1,2]; i32 selected=2; i32* ptr=&values[selected]; return 0;','index_out_of_bounds',params='')
        self.assertEqual(self.ops(doc,'array_borrow')[0]['attributes']['validation'],'unreachable')
        self.reject('i32[0] values=[]; i32* ptr=&values[index]; return 0;','index_out_of_bounds')

    def test_last_use_releases_every_alternative(self):
        doc=self.valid('mut i32[2] values=[1,2]; i32* ptr=&values[index]; i32 saved=*ptr; values=[7,8]; return saved;')
        created=set(self.ops(doc,'array_borrow')[0]['attributes']['created_capabilities'])
        ended=set(self.ops(doc,'deref_read')[0]['attributes']['ended_capabilities'])
        self.assertTrue(created <= ended)

    def test_shared_alias_and_mutable_transfer(self):
        self.valid('i32[2] values=[1,2]; i32* ptr=&values[index]; i32* copied=ptr; return *copied;')
        self.reject('mut i32[2] values=[1,2]; i32* ptr=&values[index]; i32* copied=ptr; values[0]=9; return *copied;','borrow_conflict')
        self.valid('mut i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; mut i32* transferred=move ptr; *transferred=9; return *transferred;')
        self.reject('mut i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; mut i32* transferred=move ptr; return *ptr;','use_after_move')

    def test_reborrow_suspend_and_resume(self):
        self.valid('mut i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; i32* shared=&*ptr; i32 saved=*shared; *ptr=9; return saved;')
        self.reject('mut i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; i32* shared=&*ptr; *ptr=9; return *shared;','borrow_conflict')

    def test_calls_and_input_derived_return_preserve_alternatives(self):
        self.valid('mut i32[2] values=[1,2]; mut i32* ptr=identity(&mut values[index]); *ptr=9; return values[0];',functions='fn identity(mut i32* ptr):mut i32* { return ptr; }')
        self.reject('mut i32[2] values=[1,2]; i32* ptr=identity(&values[index]); values[0]=9; return *ptr;','borrow_conflict',functions='fn identity(i32* ptr):i32* { return ptr; }')
        self.valid('mut i32[2] values=[1,2]; update(&mut values[index]); return values[1];',functions='fn update(mut i32* ptr):void { *ptr=9; }')

    def test_local_array_and_owned_parameter_returns_rejected(self):
        self.reject('return 0;','lifetime_violation',functions='fn bad(i32 index):i32* { i32[2] values=[1,2]; return &values[index]; }')
        self.reject('return 0;','lifetime_violation',functions='fn bad(i32[2] values,i32 index):i32* { return &values[index]; }')

    def test_index_snapshot_and_defer_liveness(self):
        doc=self.valid('mut i32[2] values=[1,2]; mut i32 selected=0; i32* ptr=&values[selected]; selected=1; values[1]=9; return *ptr;',params='')
        self.assertEqual(self.ops(doc,'deref_read')[-1]['attributes']['constant_value'],1)
        self.reject('mut i32[2] values=[1,2]; i32* ptr=&values[index]; defer { *ptr; }; values[0]=9; return 0;','borrow_conflict')

    def test_branch_last_use_and_report(self):
        body='mut i32[2] values=[1,2]; if(flag) { i32* ptr=&values[index]; i32 saved=*ptr; } values=[7,8]; return values[0];'
        doc=self.valid(body,params='i32 index,bool flag')
        self.assertEqual(dumps(doc),dumps(self.compile(body,params='i32 index,bool flag')))
        self.assertIn('possible element',render(doc))

    def test_determinism_across_hash_seeds(self):
        source='module demo; fn test(i32 index):i32 { mut i32[2] values=[1,2]; mut i32* ptr=&mut values[index]; i32* shared=&*ptr; i32 saved=*shared; *ptr=9; return saved; }'
        script='from cobalt.driver import compile_text; from cobalt.esir import dumps; import sys; print(dumps(compile_text(sys.argv[1])))'
        outputs=[subprocess.check_output([sys.executable,'-c',script,source],env=dict(os.environ,PYTHONHASHSEED=seed)) for seed in ('1','2')]
        self.assertTrue(outputs[0]==outputs[1], 'ESIR changed across hash seeds')

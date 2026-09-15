import unittest
from cobalt.driver import compile_text
from cobalt.esir import dumps, validate
from cobalt.explain import render


class TemporaryArrayTests(unittest.TestCase):
    def compile(self, expression, result='i32', length=2, values='7,8', params='i32 index'):
        doc=compile_text(f'module demo; fn make():i32[{length}] {{ return [{values}]; }} fn test({params}):{result} {{ {expression} }}')
        validate(doc)
        return doc

    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]

    def valid(self,expression,**kwargs):
        doc=self.compile(expression,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc

    def test_known_and_unknown_indices(self):
        for index,count in [('0',1),('index',2)]:
            doc=self.valid(f'return make()[{index}];')
            extract=self.ops(doc,'array_extract')[0]
            self.assertEqual(len(extract['attributes']['possible_elements']),count)
            self.assertEqual(extract['attributes']['result_ownership'],'Owned')
            call=self.ops(doc,'call')[0]
            self.assertTrue(set(extract['attributes']['object_identities']).isdisjoint(call['attributes']['object_identities']))

    def test_cleanup_after_copy(self):
        doc=self.valid('return make()[index];')
        operations=[o for b in doc['functions'][-1]['blocks'] for o in b['operations']]
        extract=self.ops(doc,'array_extract')[0]
        discard=next(o for o in operations if o['kind']=='discard' and o['operands']==extract['operands'][:1])
        self.assertLess(operations.index(extract),operations.index(discard))
        self.assertEqual(len(discard['effects']['destruction']),2)

    def test_bounds_failures(self):
        for index,length,values in [('2',2,'7,8'),('-1',2,'7,8'),('index',0,'')]:
            doc=self.compile(f'return make()[{index}];',length=length,values=values)
            self.assertIn('index_out_of_bounds',[d['code'] for d in doc['diagnostics']])
            self.assertEqual(self.ops(doc,'array_extract')[0]['attributes']['validation'],'unreachable')

    def test_single_element(self):
        doc=self.valid('return make()[index];',length=1,values='7')
        self.assertEqual(self.ops(doc,'array_extract')[0]['attributes']['target_selection'],'definite')

    def test_invalid_index_type_and_source(self):
        for body in ['return make()[true];','return 7[index];']:
            self.assertEqual(self.compile(body)['compilation']['result'],'invalid')

    def test_source_and_index_evaluated_once(self):
        doc=self.valid('return make()[make()[0]];')
        self.assertEqual(len(self.ops(doc,'call')),2)
        self.assertEqual(len(self.ops(doc,'array_extract')),2)

    def test_storage_and_deferred_evaluation(self):
        self.valid('i32 value=make()[index]; defer { make()[index]; }; return value;')

    def test_temporary_place_operations_rejected(self):
        for body in ['i32* ptr=&make()[index]; return 0;','make()[index]=9; return 0;']:
            self.assertNotEqual(self.compile(body)['compilation']['result'],'valid')

    def test_deterministic_source_inclusive_report(self):
        body='return make()[index];'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('Temporary array indexing',render(doc))

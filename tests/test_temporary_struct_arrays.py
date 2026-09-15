import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class TemporaryStructArrayTests(unittest.TestCase):
    decl='struct Point { i32 x; i32 y; } '
    init='[Point { x=1,y=7 },Point { x=3,y=7 }]'
    def compile(self,body,params='i32 index',functions='',decl=None,make=None):
        make=make or 'fn make():Point[2] { return '+self.init+'; } '
        doc=compile_text('module demo; '+(decl or self.decl)+make+functions+' fn test('+params+'):i32 { '+body+' }')
        validate(doc)
        return doc
    def valid(self,body,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc
    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]
    def test_literal_and_runtime_extraction(self):
        for index,count in [('0',1),('index',2)]:
            doc=self.valid(f'Point point=make()[{index}]; return point.x;')
            extract=self.ops(doc,'array_extract')[0]
            self.assertEqual(len(extract['attributes']['possible_elements']),count)
            self.assertEqual(set(extract['attributes']['result_field_states']),{'x','y'})
    def test_direct_field_and_nested_substruct(self):
        self.valid('return make()[index].x;')
        doc=self.valid('Point point=make()[index].point; return point.y;',decl=self.decl+'struct Outer { Point point; } ',make='fn make():Outer[1] { return [Outer { point=Point { x=1,y=7 } }]; } ')
        self.assertEqual(len(self.ops(doc,'array_extract')),1)
        self.assertEqual(len(self.ops(doc,'struct_extract')),1)
    def test_independent_identities_and_cleanup_order(self):
        doc=self.valid('return make()[index].x;')
        extract=self.ops(doc,'array_extract')[0]
        call=self.ops(doc,'call')[0]
        original={obj for cell in call['attributes']['result_field_states'].values() for obj in cell['object_identities']}
        copied={obj for cell in extract['attributes']['result_field_states'].values() for obj in cell['object_identities']}
        self.assertTrue(original.isdisjoint(copied))
        ops=[o for b in doc['functions'][-1]['blocks'] for o in b['operations']]
        discard=next(o for o in ops if o['kind']=='discard' and o['operands']==[extract['operands'][0]])
        self.assertEqual(len(discard['effects']['destruction']),4)
        self.assertLess(ops.index(extract),ops.index(discard))
    def test_moved_array_source_constants(self):
        doc=self.valid('Point[2] points='+self.init+'; Point point=(move points)[index]; return point.y;')
        self.assertEqual(self.ops(doc,'copy')[-1]['attributes']['constant_value'],7)
        doc=self.compile('Point[2] points='+self.init+'; Point point=(move points)[index]; return points[0].x;')
        self.assertIn('use_after_move',[d['code'] for d in doc['diagnostics']])
    def test_bounds_failure_and_empty_arrays(self):
        for index in ('2','-1'):
            doc=self.compile(f'return make()[{index}].x;')
            self.assertIn('index_out_of_bounds',[d['code'] for d in doc['diagnostics']])
            self.assertEqual(self.ops(doc,'array_extract')[0]['attributes']['validation'],'unreachable')
        doc=self.compile('Point point=make()[index]; return 0;',make='fn make():Point[0] { return []; } ')
        self.assertIn('index_out_of_bounds',[d['code'] for d in doc['diagnostics']])
    def test_empty_struct_elements(self):
        self.valid('Empty value=make()[index]; return 0;',decl='struct Empty {} ',make='fn make():Empty[2] { return [Empty {},Empty {}]; } ')
    def test_single_evaluation_calls_returns_and_defer(self):
        funcs='fn index_value():i32 { return 0; } fn take(Point point):i32 { return point.x; } fn pick(i32 index):Point { return make()[index]; } '
        doc=self.valid('return take(make()[index_value()]);',functions=funcs)
        calls=[o for b in doc['functions'][-1]['blocks'] for o in b['operations'] if o['kind']=='call']
        self.assertEqual(len(calls),3)
        self.valid('defer { make()[index].x; }; return 0;')
    def test_temporary_borrows_and_assignment_rejected(self):
        for body in ('Point* ptr=&make()[index]; return 0;','make()[index]=Point { x=1,y=2 }; return 0;','i32* ptr=&make()[index].x; return 0;','make()[index].x=9; return 0;'):
            doc=self.compile(body)
            self.assertNotEqual(doc['compilation']['result'],'valid')
    def test_deterministic_report(self):
        body='return make()[index].x;'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('temporary',render(doc))

import unittest
from cobalt.driver import compile_text
from cobalt.esir import validate,dumps
from cobalt.explain import render

class StructArrayFieldTests(unittest.TestCase):
    decl='struct Point { i32 x; i32 y; } struct Scene { Point[2] points; i32 tag; } '
    init='Scene { points=[Point { x=1,y=2 },Point { x=3,y=4 }], tag=7 }'
    prefix='mut Scene scene='+init+'; '
    def compile(self,body,params='i32 index',functions='',decl=None):
        doc=compile_text('module demo; '+(decl or self.decl)+functions+' fn test('+params+'):i32 { '+body+' }')
        validate(doc)
        return doc
    def valid(self,body,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertEqual(doc['compilation']['result'],'valid',doc['diagnostics'])
        return doc
    def reject(self,body,code,**kwargs):
        doc=self.compile(body,**kwargs)
        self.assertIn(code,[d['code'] for d in doc['diagnostics']],doc['diagnostics'])
        return doc
    def ops(self,doc,kind):
        return [o for f in doc['functions'] for b in f['blocks'] for o in b['operations'] if o['kind']==kind]
    def test_construction_forward_and_direct_fields(self):
        self.valid(self.prefix+'scene.points[index].x=9; return scene.points[index].x;')
        self.valid(self.prefix+'return scene.points[0].y;',decl='struct Scene { Point[2] points; i32 tag; } struct Point { i32 x; i32 y; } ')
    def test_partial_moves_and_restoration(self):
        prefix=self.prefix+'Point taken=move scene.points[index]; '
        self.valid(prefix+'return scene.tag;')
        self.reject(prefix+'Scene copied=scene; return 0;','use_after_move')
        self.valid(prefix+'scene.points=[Point { x=7,y=8 },Point { x=9,y=10 }]; Scene copied=scene; return copied.tag;')
        self.reject(prefix+'scene.points[index]=Point { x=7,y=8 }; Scene copied=scene; return 0;','use_after_move')
    def test_partial_initialization(self):
        self.valid('mut Scene scene; scene.points[0]=Point { x=1,y=2 }; scene.points[1]=Point { x=3,y=4 }; scene.tag=7; Scene copied=scene; return copied.tag;')
        self.reject('mut Scene scene; scene.points[index]=Point { x=1,y=2 }; scene.tag=7; Scene copied=scene; return 0;','uninitialized_read')
    def test_field_borrow_overlap(self):
        self.valid(self.prefix+'mut Point* ptr=&mut scene.points[index]; scene.tag=9; ptr->x=7; return ptr->x;')
        self.reject(self.prefix+'i32* ptr=&scene.points[index].x; scene='+self.init+'; return *ptr;','borrow_conflict')
        self.valid(self.prefix+'i32* ptr=&scene.points[index].x; scene.points[index].y=9; return *ptr;')
    def test_struct_pointer_array_element_and_whole_array(self):
        self.valid(self.prefix+'mut Scene* ptr=&mut scene; ptr->points[index]=Point { x=7,y=8 }; Point point=ptr->points[index]; return point.x;')
        self.valid(self.prefix+'Scene* ptr=&scene; Point[2] points=ptr->points; return points[0].x;')
        self.valid(self.prefix+'mut Scene* ptr=&mut scene; ptr->points=[Point { x=7,y=8 },Point { x=9,y=10 }]; Point* point=&ptr->points[index]; return point->x;')
        self.reject(self.prefix+'Scene* ptr=&scene; ptr->points[index]=Point { x=7,y=8 }; return 0;','borrow_conflict')
    def test_nested_runtime_aggregate_selection(self):
        prefix='mut Scene[2] scenes=['+self.init+','+self.init+']; '
        self.valid(prefix+'Point taken=move scenes[index].points[item]; return taken.x;',params='i32 index,i32 item')
        doc=self.valid(prefix+'scenes[index].points[item]=Point { x=7,y=8 }; Point point=scenes[index].points[item]; return point.x;',params='i32 index,i32 item')
        assign=self.ops(doc,'array_assign')[0]
        self.assertEqual(len(assign['attributes']['possible_elements']),4)
        self.assertTrue(all(assign['attributes']['inner_bounds_proof'] in effect for effect in assign['effects']['initialization']))
    def test_by_value_transfer_and_returned_borrows(self):
        functions='fn identity(Scene scene):Scene { return move scene; } fn field(Point* point):i32* { return &point->x; } '
        self.valid(self.prefix+'Scene copied=identity(scene); i32* ptr=field(&copied.points[index]); return *ptr;',functions=functions)
        self.reject('return 0;','lifetime_violation',functions='fn bad(Scene scene,i32 index):Point* { return &scene.points[index]; } ')
    def test_cleanup_leaf_count_and_defer(self):
        doc=self.valid(self.prefix+'return scene.tag;')
        self.assertEqual(len(self.ops(doc,'destroy')),6)
        self.reject(self.prefix+'defer { scene.points[0].x; }; return move scene.points[index].x;','use_after_move')
    def test_cycles_including_zero_length(self):
        for decl in ('struct Scene { Scene[1] children; }','struct Scene { Scene[0] children; }','struct First { Second[2] children; } struct Second { First parent; }'):
            self.reject('return 0;','unsupported_recursive_struct',decl=decl)
    def test_empty_arrays_and_bounds(self):
        self.valid('Scene scene=Scene { points=[],tag=7 }; Scene copied=scene; return copied.tag;',decl='struct Point {} struct Scene { Point[0] points; i32 tag; } ')
        self.reject(self.prefix+'i32 selected=2; Point point=scene.points[selected]; return 0;','index_out_of_bounds')
    def test_deterministic_report(self):
        body=self.prefix+'return scene.points[index].x;'
        doc=self.valid(body)
        self.assertEqual(dumps(doc),dumps(self.compile(body)))
        self.assertIn('struct',render(doc))

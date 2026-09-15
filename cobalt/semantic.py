"""Scalar type analysis and lowering to an explicit semantic CFG.

Binding lookup is lexical; cleanup is lowered on each exiting path. State-sensitive
validation is a separate pass in dataflow.py, after the CFG has been constructed.
"""
from dataclasses import dataclass
from .source import StopCompilation
from .unicode_identifiers import skeleton

INTEGERS = {f'{s}{w}' for s in ('i','u') for w in (8,16,32,64,128)}
SUPPORTED = INTEGERS | {'bool','char','void'}


def is_pointer(typ):
    return typ.endswith('*')


def pointee(typ):
    return typ.removeprefix('mut ')[:-1]


def limits(typ):
    bits = int(typ[1:])
    return (-(1 << (bits-1)), (1 << (bits-1))-1) if typ[0]=='i' else (0, (1 << bits)-1)


@dataclass
class Value:
    id: str
    type: str


class Lowerer:
    def __init__(self, ast, ids, diagnostics):
        self.ast, self.ids, self.d = ast, ids, diagnostics
        self.types, self.symbols, self.functions, self.signatures = {}, [], [], {}
        self.structs, self.components = {}, {}
        self.arrays = {}
        self.array_elements = {}
        self.call_temporaries = []
        self.scopes, self.cleanup, self.current = [], [], None
        self.type_id('void')
        self.type_id('error')

    def array_cells(self, name):
        element,length=self.arrays[name]
        return length*(self.array_cells(element) if element in self.arrays else 1)

    def type_id(self, name):
        if name not in self.types:
            if is_pointer(name):
                target = self.type_id(pointee(name))
                self.types[name] = dict(id=self.ids.new('type'), name=name, kind='managed_pointer',
                                       args=[target], copyable=not name.startswith('mut '), destructor=False)
                return self.types[name]['id']
            self.types[name] = dict(id=self.ids.new('type'), name=name,
                kind='error' if name=='error' else 'builtin',
                copyable=None if name=='error' else name!='void', destructor=None if name=='error' else False)
        return self.types[name]['id']

    def error(self, node, code, message, phase='P5', rules=(), entities=()):
        self.d.add(code, message, node.span, phase, rules, entities)

    def check_type(self, name, node, allow_void=False):
        if name.endswith(']'):
            element, dimensions=name.split('[',1)
            length, remainder=dimensions.split(']',1)
            if remainder:
                element = self.check_type(element+remainder,node)
                if element == 'error': return 'error'
            aggregate_element = element in self.structs
            if element not in SUPPORTED - {'void'} and not aggregate_element:
                self.error(node,'unsupported_array_element','Array elements require supported scalars, arrays, or acyclic structs.')
                return 'error'
            length=int(length)
            if length > 256:
                self.error(node,'unsupported_array_length','Each array dimension in this milestone supports lengths up to 256.')
                return 'error'
            total=length*(self.array_cells(element) if element in self.arrays else 1)
            if total>256:
                self.error(node,'unsupported_array_size','This multidimensional array milestone supports at most 256 scalar cells per array value.')
                return 'error'
            if name not in self.arrays:
                self.arrays[name]=(element,length)
                self.structs[name]={'['+str(i)+']':element for i in range(length)}
                self.types[name]=dict(id=self.ids.new('type'),name=name,kind='array',args=[self.type_id(element)],
                    fields=[dict(name=key,type=self.type_id(element)) for key in self.structs[name]],copyable=True,destructor=False)
            return name
        if is_pointer(name):
            if self.check_type(pointee(name), node) == 'error': return 'error'
            self.type_id(name)
            return name
        if name in ('isize','usize','f32','f64','String'):
            self.error(node,'unsupported_type',f'{name} requires a target/library model not implemented in this milestone.')
            return 'error'
        if name not in SUPPORTED and name not in self.structs:
            self.error(node,'unresolved_type',f'Unknown type {name!r}.', 'P4')
            return 'error'
        if name=='void' and not allow_void:
            self.error(node,'invalid_void_type','void is only supported as a function return type.')
            return 'error'
        self.type_id(name)
        return name

    def lower(self):
        self.register_structs()
        for fn in self.ast.data['functions']:
            name=fn.data['name']
            self.check_confusable(fn, name, set(self.signatures) | set(self.structs))
            if name in self.signatures or name in self.structs:
                self.error(fn,'duplicate_name',f'Function {name!r} is already declared.','P4',['TYPE-039'])
                continue
            result=self.check_type(fn.data['result'],fn,True)
            params=[self.check_type(p.data['type'],p) for p in fn.data['params']]
            tid=self.ids.new('type'); sid=self.ids.new('symbol'); fid=self.ids.new('function')
            self.types[f'function:{name}']=dict(id=tid,name=name,kind='function',parameters=[{'type':self.type_id(t)} for t in params],return_type=self.type_id(result),copyable=None,destructor=False,source_span=fn.span)
            self.symbols.append(dict(id=sid,name=name,kind='function',type=tid,source_span=fn.span))
            self.signatures[name]=(sid,fid,tid,params,result,fn)
        for ex in self.ast.data['exports']:
            if ex.text not in self.signatures and ex.text not in self.structs: self.error(ex,'unresolved_name',f'Unknown export {ex.text!r}.','P4')
        for sig in self.signatures.values(): self.function(sig)
        return self

    def register_structs(self):
        for node in self.ast.data.get('structs', []):
            name = node.data['name']
            self.check_confusable(node, name, self.structs)
            if name in self.structs:
                self.error(node,'duplicate_name',f'Struct {name!r} is already declared.','P4'); continue
            self.structs[name] = {}
            tid = self.ids.new('type')
            self.types[name] = dict(id=tid, name=name, kind='struct', fields=[], copyable=True,
                                    destructor=False, source_span=node.span)
            self.symbols.append(dict(id=self.ids.new('symbol'), name=name, kind='type', type=tid, source_span=node.span))
        for node in self.ast.data.get('structs', []):
            name = node.data['name']; fields = self.structs[name]
            # Only populate the first declaration of a duplicated type.
            if self.types[name]['source_span'] != node.span: continue
            for field in node.data['fields']:
                fname, typ = field.data['name'], field.data['type']
                self.check_confusable(field, fname, fields)
                if fname in fields:
                    self.error(field,'duplicate_field',f'Field {fname!r} is already declared.','P4'); continue
                if typ.endswith(']'):
                    typ = self.check_type(typ, field)
                if typ != 'error' and typ not in (SUPPORTED - {'void'}) and typ not in self.structs and not is_pointer(typ):
                    self.error(field,'unsupported_struct_field','Struct fields require supported scalars, fixed-size arrays, acyclic structs, or managed pointers.')
                    typ = 'error'; self.types[name]['copyable'] = None
                if typ == 'error': self.types[name]['copyable'] = None
                fields[fname] = typ
                self.types[name]['fields'].append(dict(name=fname, type=self.type_id(typ), source_span=field.span))

        # Reject cycles before creating any recursive storage paths.
        visiting, done = set(), set()
        def visit(name):
            if name in done: return
            visiting.add(name)
            for field in self.types[name]['fields']:
                target = self.structs[name][field['name']]
                while target in self.arrays: target = self.arrays[target][0]
                if target not in self.structs: continue
                if target in visiting:
                    self.error(next(n for n in self.ast.data['structs'] if n.data['name']==name),
                               'unsupported_recursive_struct', 'Recursive by-value struct definitions are not supported.')
                    self.structs[name][field['name']] = 'error'
                    field['type'] = self.type_id('error')
                    self.types[name]['copyable'] = None
                else: visit(target)
            visiting.remove(name); done.add(name)
        for name in self.structs:
            if name not in self.arrays: visit(name)

    def component_paths(self, root):
        result = {}
        for name, child in self.components.get(root, {}).items():
            result[name] = child
            result.update((name+'.'+path, p) for path,p in self.component_paths(child['id']).items())
        return result

    def type_paths(self, typ):
        result = {}
        for name, child_type in self.structs.get(typ, {}).items():
            result[name] = child_type
            result.update((name+'.'+path, t) for path,t in self.type_paths(child_type).items())
        return result

    def block(self, node):
        b=dict(id=self.ids.new('block'), parameters=[],operations=[],terminator={'kind':'unreachable'},source_span=node.span)
        self.fn['blocks'].append(b)
        return b

    def op(self, kind, node, operands=(), typ=None, rules=(), **attrs):
        if operands and operands[0] in self.array_elements and kind in ('read','copy','move','assign','borrow_shared','borrow_mut'):
            index,length=self.array_elements[operands[0]]
            attrs.update(array_index=index,array_length=length,bounds_check='proven_in_bounds')
            rules=[*rules,'TYPE-036','TYPE-070']
        op=dict(id=self.ids.new('op'),kind=kind,operands=list(operands),results=[],
                preconditions=[],postconditions=[],effects={},rule_refs=list(rules),
                facts_established=[],facts_invalidated=[],source_span=node.span,
                attributes=dict(ast_origin=node.id, **attrs))
        value=None
        if typ is not None:
            value=Value(self.ids.new('value'),typ)
            op['results']=[value.id]
            self.fn['values'].append(dict(id=value.id,type=self.type_id(typ),origin_op=op['id'],source_span=node.span))
        self.current['operations'].append(op)
        return value

    def jump(self, block, node, operands=()):
        self.current['terminator']=dict(kind='jump',targets=[block['id']],operands=list(operands),source_span=node.span)

    def function(self,sig):
        sid,fid,tid,paramtypes,self.result,fn=sig
        self.fn=dict(id=fid,name=fn.data['name'],type=tid,entry_block='',blocks=[],places=[],values=[],capabilities=[],lifetimes=[],cleanup_regions=[],unsafe_regions=[],source_span=fn.span)
        self.functions.append(self.fn); self.scopes=[]; self.cleanup=[]
        self.current=self.block(fn); self.fn['entry_block']=self.current['id']
        self.enter(fn)
        for p,t in zip(fn.data['params'],paramtypes):
            place=self.declare(p,t,'parameter')
            self.op('parameter',p,[place['id']],rules=['STATIC-TYPE-001','TRANS-INIT-001'],parameter_index=fn.data['params'].index(p))
        self.statements(fn.data['body'].data['statements'])
        if self.current is not None:
            self.exit_scope(fn)
            if self.result!='void':
                self.op('missing_return',fn,rules=['TYPE-037'])
                self.current['terminator']={'kind':'unreachable','source_span':fn.span}
            else: self.current['terminator']={'kind':'return','operands':[],'source_span':fn.span}
        self.scopes.pop(); self.cleanup.pop()

    def enter(self,node):
        region=dict(id=self.ids.new('cleanup'),parent=self.cleanup[-1][0]['id'] if self.cleanup else None,
            defer_obligations=[],destruction_places=[],source_span=node.span)
        self.fn['cleanup_regions'].append(region)
        self.scopes.append({}); self.cleanup.append((region,[]))

    def declare(self,node,typ,kind='local'):
        name=node.data['name']
        visible = (set(self.signatures) | set(self.structs)).union(*(set(s) for s in self.scopes))
        self.check_confusable(node, name, visible)
        if name in self.scopes[-1]: self.error(node,'duplicate_name',f'{name!r} already declared in this scope.','P4')
        pid=self.ids.new('place'); lid=self.ids.new('life'); sid=self.ids.new('symbol')
        place=dict(id=pid,type=self.type_id(typ),ownership='Unowned',initialization='Uninitialized',
            mutability='Mutable' if node.data.get('mutable') else 'Immutable',lifetime=lid,
            object_identity=None,parent=None,field_path=[],source_span=node.span)
        self.fn['places'].append(place)
        self.fn['lifetimes'].append(dict(id=lid,referent=pid,status='Live',lower_bound='declaration',upper_bound=self.cleanup[-1][0]['id'],source_span=node.span))
        symbol=dict(id=sid,name=name,kind=kind,type=self.type_id(typ),place=pid,source_span=node.span)
        self.symbols.append(symbol); self.scopes[-1][name]=(place,typ,symbol,node.data.get('const',False))
        self.cleanup[-1][0]['destruction_places'].append(pid)
        self.op('alloca',node,[pid],rules=['TRANS-INIT-001'],lifetime=lid)
        def children(place, typ, name):
            pid, lid = place['id'], place['lifetime']
            if typ not in self.structs: return
            self.components[pid] = {}
            for fname, ftyp in self.structs[typ].items():
                fid, flife = self.ids.new('place'), self.ids.new('life')
                child = dict(place, id=fid, type=self.type_id(ftyp), parent=pid, field_path=place['field_path']+[fname], lifetime=flife)
                self.fn['places'].append(child); self.components[pid][fname] = child
                if typ in self.arrays: self.array_elements[fid]=(int(fname[1:-1]),self.arrays[typ][1])
                self.fn['lifetimes'].append(dict(id=flife, referent=fid, parent=lid, status='Live',
                    lower_bound='declaration', upper_bound=lid, source_span=node.span))
                self.symbols.append(dict(id=self.ids.new('symbol'), name=name+('' if fname.startswith('[') else '.')+fname, kind='field',
                                         type=self.type_id(ftyp), place=fid, source_span=node.span))
                self.op('alloca',node,[fid],rules=['TRANS-INIT-001'],lifetime=flife)
                children(child, ftyp, name+'.'+fname)
        children(place, typ, name)
        return place

    def temporary_storage(self,node,value):
        """Materialize an owned rvalue for a borrow that lasts through a call."""
        pid=self.ids.new('place'); lid=self.ids.new('life')
        place=dict(id=pid,type=self.type_id(value.type),ownership='Unowned',initialization='Uninitialized',
            mutability='Mutable',lifetime=lid,object_identity=None,parent=None,field_path=[],source_span=node.span)
        self.fn['places'].append(place)
        self.fn['lifetimes'].append(dict(id=lid,referent=pid,status='Live',lower_bound='expression',
            upper_bound=self.cleanup[-1][0]['id'],source_span=node.span))
        self.op('alloca',node,[pid],rules=['TRANS-INIT-001'],lifetime=lid,temporary=True)
        def children(parent,typ,path):
            if typ not in self.structs: return
            self.components[parent['id']]={}
            for name,child_type in self.structs[typ].items():
                cid,clife=self.ids.new('place'),self.ids.new('life')
                child=dict(parent,id=cid,type=self.type_id(child_type),parent=parent['id'],field_path=path+[name],lifetime=clife)
                self.fn['places'].append(child);self.components[parent['id']][name]=child
                if typ in self.arrays:self.array_elements[cid]=(int(name[1:-1]),self.arrays[typ][1])
                self.fn['lifetimes'].append(dict(id=clife,referent=cid,parent=parent['lifetime'],status='Live',
                    lower_bound='expression',upper_bound=parent['lifetime'],source_span=node.span))
                self.op('alloca',node,[cid],rules=['TRANS-INIT-001'],lifetime=clife,temporary=True)
                children(child,child_type,path+[name])
        children(place,value.type,[])
        self.op('init',node,[pid,value.id],rules=['TRANS-INIT-001','TYPE-004'],type_valid=True,
                const_binding=False,temporary=True)
        self.call_temporaries[-1].append(pid)
        return place

    def check_confusable(self, node, name, visible):
        for other in sorted(visible):
            if other != name and skeleton(other) == skeleton(name):
                self.error(node, 'confusable_identifier', f'{name!r} is confusable with visible identifier {other!r}.', 'P4', ['PARSE-204','PARSE-205','PARSE-206'])

    def lookup(self,node):
        if node.kind == 'index':
            base=node.data['value']
            if base.kind not in ('name','member','index') or self.temporary_member(base) or self.projected_field(base):
                self.error(node,'unsupported_array_base','Indexing requires a local or parameter array or array field.')
                return None
            entry=self.lookup(base)
            if entry is None: return None
            root,typ,symbol,const=entry
            if typ not in self.arrays:
                self.error(node,'invalid_index','Indexing requires an array.')
                return None
            index=node.data['index']; negative=index.kind=='unary' and index.data['operator']=='-'
            literal=index.data['value'] if negative else index
            if literal.kind!='literal' or literal.data['literal_kind']!='int':
                self.error(node,'unsupported_dynamic_index','This place projection requires an integer literal index.')
                return None
            number=literal.data['value']*(-1 if negative else 1)
            element,length=self.arrays[typ]
            if not 0 <= number < length:
                self.error(node,'index_out_of_bounds',f'Index {number} is outside array length {length}.',rules=['TYPE-036'])
                return None
            return self.components[root['id']]['['+str(number)+']'],element,symbol,const
        if node.kind == 'member':
            base = node.data['value']
            if base.kind not in ('name','member','index'):
                self.error(node,'unsupported_member_base','Field access currently requires a local struct binding.')
                return None
            entry = self.lookup(base)
            if entry is None: return None
            root, typ, symbol, const = entry
            if typ not in self.structs:
                self.error(node,'invalid_field_access',f'{typ} is not a struct.')
                return None
            name = node.data['name']
            if name not in self.structs[typ]:
                self.error(node,'unknown_field',f'{typ} has no field {name!r}.','P4')
                return None
            return self.components[root['id']][name], self.structs[typ][name], symbol, const
        name=node.data['name']
        for scope in reversed(self.scopes):
            if name in scope: return scope[name]
        self.error(node,'unresolved_name',f'Unresolved name {name!r}.','P4')
        return None

    def compatible(self,node,actual,expected):
        if 'error' in (actual,expected): return False
        if actual!=expected:
            self.error(node,'type_error',f'Expected {expected}, found {actual}.',rules=['TYPE-007','STATIC-TYPE-002'])
            return False
        return True

    def expr_type_hint(self,node):
        if node.kind=='construct': return node.data['type']
        if node.kind=='index':
            base=self.expr_type_hint(node.data['value'])
            return self.arrays[base][0] if base in self.arrays else None
        if node.kind=='member':
            base=self.expr_type_hint(node.data['value'])
            return self.structs.get(base, {}).get(node.data['name'])
        if node.kind=='borrow':
            hint=self.expr_type_hint(node.data['value'])
            return ('mut ' if node.data['mutable'] else '')+hint+'*' if hint else None
        if node.kind=='deref':
            hint=self.expr_type_hint(node.data['value'])
            return pointee(hint) if hint and is_pointer(hint) else None
        if node.kind=='name':
            for scope in reversed(self.scopes):
                if node.data['name'] in scope: return scope[node.data['name']][1]
        if node.kind=='call' and node.data['callee'].kind=='name':
            sig=self.signatures.get(node.data['callee'].data['name'])
            if sig: return sig[4]
        return None

    def runtime_array_field(self, node):
        if node.kind == 'index': return self.runtime_array_field(node.data['value'])
        if node.kind != 'member' or self.temporary_member(node): return False
        if self.expr_type_hint(node) not in self.arrays: return False
        while node.kind == 'member': node=node.data['value']
        return self.dynamic_index(node) and not self.pointer_array_index(node)

    def dynamic_struct_projection(self,node):
        if node.kind!='member' or self.temporary_member(node): return None
        names=[]; base=node
        while base.kind=='member':
            names.append(base.data['name']); base=base.data['value']
        if base.kind!='index' or not self.dynamic_index(base): return None
        chain=self.checked_index_chain(base)
        if chain is None: return None
        root,typ,proofs,const,lengths=chain
        path='.'.join(reversed(names))
        fields=self.type_paths(typ) if typ in self.structs else {}
        if path not in fields:
            self.error(node,'unknown_field',f'{typ} has no supported field path {path!r}.','P4')
            return None
        return root,fields[path],proofs,const,lengths,path

    def dynamic_projection_access(self,node,kind,prepared,value=None,mutable=False):
        root,typ,proofs,const,lengths,path=prepared
        operands=[root['id'],*[p.id for p in proofs]]
        attrs=dict(projected_field=path,projected_field_dimension=len(proofs)-1,
                   dimension_bounds_proofs=[p.id for p in proofs],dimension_lengths=lengths)
        if kind=='array_assign':
            operands.append(value.id)
            attrs.update(type_valid=self.compatible(node,value.type,typ),const_binding=const,value_operand=len(operands)-1)
            return self.op(kind,node,operands,rules=['TYPE-066','TYPE-036'],**attrs)
        if kind=='array_borrow':
            attrs['access']='MutableExclusive' if mutable else 'SharedRead'
            typ=('mut ' if mutable else '')+typ+'*'
            return self.op(kind,node,operands,typ,['TRANS-BORROW-001','BORROW-002','BORROW-064','BORROW-042','TYPE-036'],**attrs)
        rules=['STATIC-INIT-001','OWNERSHIP-003','TYPE-036']
        if kind=='array_move': rules=['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005','TYPE-036']
        return self.op(kind,node,operands,typ,rules,**attrs)

    def prepare_array_field(self, node):
        if node.kind=='index':
            prepared=self.prepare_array_field(node.data['value'])
            if prepared is None: return None
            root,typ,outer,const,path=prepared[:5]
            if typ not in self.arrays:
                self.error(node,'invalid_index','Nested indexing requires a scalar-array field.')
                return None
            element,length=self.arrays[typ]
            inner=self.expression(node.data['index'])
            if inner.type not in INTEGERS:
                self.error(node,'type_error','An array index must have a fixed-width integer type.')
                return None
            checked=self.op('array_bounds',node,[inner.id],inner.type,['TYPE-036','TYPE-069','TYPE-070','TRANS-FAIL-001'],array_length=length)
            self.checked_edges(node,checked,failure='bounds')
            return root,element,outer,const,path,checked
        names=[]; base=node
        while base.kind=='member':
            names.append(base.data['name']); base=base.data['value']
        target=self.checked_index(base)
        if target is None: return None
        root,element,index,const=target
        path='.'.join(reversed(names))
        fields=self.type_paths(element)
        if path not in fields:
            self.error(node,'unknown_field',f'{element} has no supported field path {path!r}.','P4')
            return None
        return root,fields[path],index,const,path

    def array_field_access(self, node, kind, prepared, value=None, mutable=False):
        root,typ,index,const,path=prepared[:5]
        args=[root['id'],index.id]
        attrs=dict(projected_field=path)
        inner=[prepared[5].id] if len(prepared)>5 else []
        if inner: attrs['inner_bounds_proof']=inner[0]
        rules=['TYPE-036','STATIC-INIT-001','OWNERSHIP-003']
        if kind=='array_assign':
            args.append(value.id)
            attrs.update(type_valid=self.compatible(node,value.type,typ),const_binding=const)
            rules=['TYPE-066','TYPE-036']
            return self.op(kind,node,args+inner,rules=rules,**attrs)
        if kind=='array_borrow':
            attrs['access']='MutableExclusive' if mutable else 'SharedRead'
            typ=('mut ' if mutable else '')+typ+'*'
            rules=['TRANS-BORROW-001','BORROW-029','BORROW-032','BORROW-064','TYPE-036']
        elif kind=='array_move':
            rules=['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005','TYPE-036']
        return self.op(kind,node,args+inner,typ,rules,**attrs)

    def projected_field(self, node):
        if node.kind != 'member': return False
        base=node.data['value']
        return base.kind == 'deref' or self.projected_field(base)

    def projection_base(self, node):
        while node.kind == 'member': node=node.data['value']
        return node.data['value']

    def field_pointer(self, node, mutable=False, pointer=None, value_projection=False, for_assignment=False):
        pointer = pointer or self.expression(self.projection_base(node))
        root_type = pointee(pointer.type) if is_pointer(pointer.type) else None
        fields = self.type_paths(root_type) if root_type in self.structs else None
        names=[]; current=node
        while current.kind == 'member':
            names.append(current.data['name']); current=current.data['value']
        name='.'.join(reversed(names))
        if fields is None:
            self.error(node, 'invalid_field_access', 'Pointer field access requires a managed pointer to a struct.')
            return self.op('invalid', node, typ='error')
        if name not in fields:
            self.error(node, 'unknown_field', f'{root_type} has no field {name!r}.', 'P4')
            return self.op('invalid', node, typ='error')
        return self.op('field_borrow', node, [pointer.id], ('mut ' if mutable else '')+fields[name]+'*',
                       ['BORROW-029','BORROW-032','BORROW-024'], field=name,
                       access='MutableExclusive' if mutable else 'SharedRead',
                       allow_moved_for_assignment=for_assignment)

    def temporary_member(self, node):
        if node.kind != 'member': return False
        while node.kind in ('member','index'): node = node.data['value']
        return node.kind not in ('name', 'deref')

    def extract_temporary(self, node, moving=False):
        names=[]; base=node
        while base.kind == 'member':
            names.append(base.data['name']); base=base.data['value']
        path='.'.join(reversed(names))
        if moving and base.kind == 'index' and self.temporary_array_access(base):
            value=self.extract_array_temporary(base, moving=True)
        else:
            value=self.expression(base, mode='value')
        fields=self.type_paths(value.type) if value.type in self.structs else None
        if fields is None or path not in fields:
            self.error(node, 'invalid_field_access' if fields is None else 'unknown_field',
                       f'{value.type} has no supported field path {path!r}.')
            return self.op('invalid',node,typ='error')
        kind='struct_move_extract' if moving else 'struct_extract'
        rules=(['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005'] if moving else
               ['OWNERSHIP-003','TRANS-COPY-001','STATIC-INIT-001'])
        result=self.op(kind,node,[value.id],fields[path],rules,field=path)
        cleanup_attrs=dict(moved_field_path=path) if moving else {}
        self.op('discard',node,[value.id],rules=['TRANS-DESTROY-001'],**cleanup_attrs)
        return result

    def pointer_array_index(self, node):
        if node.kind!='index': return False
        base,_=self.index_layers(node)
        if self.projected_field(base): return True
        return base.kind=='deref' and self.expr_type_hint(base) in self.arrays

    def pointer_array_projection(self,node):
        if self.pointer_array_index(node): return True
        if node.kind!='member': return False
        base=node
        while base.kind=='member': base=base.data['value']
        return self.pointer_array_index(base)

    def prepare_pointer_index(self, node):
        suffix=[]; target=node
        while target.kind=='member':
            suffix.append(target.data['name']); target=target.data['value']
        base,layers=self.index_layers(target)
        pointer=self.expression(self.projection_base(base))
        names=[]
        while base.kind=='member':
            names.append(base.data['name']); base=base.data['value']
        path='.'.join(reversed(names))
        root=pointee(pointer.type) if is_pointer(pointer.type) else None
        typ=(self.type_paths(root).get(path) if path and root in self.structs else root if not path else None)
        if typ not in self.arrays:
            self.error(node,'invalid_index','Pointer indexing requires an array field of a struct.')
            return None
        proofs=[]; lengths=[]
        for layer in layers:
            if typ not in self.arrays:
                self.error(layer,'invalid_index','Each pointer array index must select an array.')
                return None
            index=self.expression(layer.data['index'])
            if index.type not in INTEGERS:
                self.error(layer,'type_error','An array index must have a fixed-width integer type.')
                return None
            typ,length=self.arrays[typ]
            checked=self.op('array_bounds',layer,[index.id],index.type,['TYPE-036','TYPE-069','TYPE-070','TRANS-FAIL-001'],array_length=length)
            self.checked_edges(layer,checked,failure='bounds')
            proofs.append(checked); lengths.append(length)
        suffix_path='.'.join(reversed(suffix))
        if suffix_path:
            fields=self.type_paths(typ) if typ in self.structs else {}
            if suffix_path not in fields:
                self.error(node,'unknown_field',f'{typ} has no supported field path {suffix_path!r}.','P4')
                return None
            typ=fields[suffix_path]
        return pointer,typ,proofs,path,lengths,suffix_path

    def borrow_pointer_index(self, node, prepared, mutable=False, for_assignment=False):
        pointer,element,proofs,path,lengths,suffix=prepared
        attrs=dict(array_length=lengths[0],access='MutableExclusive' if mutable else 'SharedRead')
        if path: attrs['field']=path
        if for_assignment: attrs['allow_moved_for_assignment']=True
        if suffix: attrs['field_suffix']=suffix
        if len(proofs)>1:
            attrs.update(dimension_bounds_proofs=[p.id for p in proofs],dimension_lengths=lengths)
        return self.op('indexed_field_borrow',node,[pointer.id,*[p.id for p in proofs]],('mut ' if mutable else '')+element+'*',
                       ['BORROW-029','BORROW-032','BORROW-024','TYPE-036'],**attrs)

    def temporary_array_access(self, node):
        if node.kind != 'index': return False
        base=node
        while base.kind == 'index': base=base.data['value']
        return base.kind not in ('name','member','deref') or self.temporary_member(base)

    def extract_array_temporary(self, node, moving=False):
        base=node.data['value']
        if moving and self.temporary_member(base):
            value=self.extract_temporary(base, moving=True)
        elif moving and base.kind == 'index' and self.temporary_array_access(base):
            value=self.extract_array_temporary(base, moving=True)
        else:
            value=self.expression(base, mode='value')
        if value.type not in self.arrays:
            self.error(node,'invalid_index','Temporary indexing requires an array value.')
            return self.op('invalid',node,typ='error')
        index=self.expression(node.data['index'])
        if index.type not in INTEGERS:
            self.error(node,'type_error','An array index must have a fixed-width integer type.')
            return self.op('invalid',node,typ='error')
        element,length=self.arrays[value.type]
        checked=self.op('array_bounds',node,[index.id],index.type,['TYPE-036','TYPE-069','TYPE-070','TRANS-FAIL-001'],array_length=length)
        self.checked_edges(node,checked,failure='bounds')
        kind='array_move_extract' if moving else 'array_extract'
        rules=(['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005','TYPE-036'] if moving else
               ['OWNERSHIP-003','TRANS-COPY-001','STATIC-INIT-001','TYPE-036'])
        result=self.op(kind,node,[value.id,checked.id],element,rules,array_length=length)
        cleanup_attrs=dict(moved_element_index=checked.id,array_length=length) if moving else {}
        self.op('discard',node,[value.id],rules=['TRANS-DESTROY-001'],**cleanup_attrs)
        return result

    def index_layers(self,node):
        layers=[]
        while node.kind=='index':
            layers.append(node)
            node=node.data['value']
        return node,list(reversed(layers))

    def dynamic_index(self, node):
        if node.kind != 'index': return False
        _,layers=self.index_layers(node)
        for layer in layers:
            index=layer.data['index']
            if index.kind=='unary' and index.data['operator']=='-': index=index.data['value']
            if not (index.kind=='literal' and index.data['literal_kind']=='int'):
                return True
        return False

    def checked_index_chain(self,node):
        base,layers=self.index_layers(node)
        if base.kind not in ('name','member') or self.temporary_member(base) or self.projected_field(base):
            self.error(node,'unsupported_array_base','Indexing requires a local or parameter array or array field.')
            return None
        entry=self.lookup(base)
        if entry is None: return None
        root,typ,_,const=entry
        proofs=[]; lengths=[]
        for layer in layers:
            if typ not in self.arrays:
                self.error(layer,'invalid_index','Each index dimension must select an array.')
                return None
            index=self.expression(layer.data['index'])
            if index.type not in INTEGERS:
                self.error(layer,'type_error','An array index must have a fixed-width integer type.')
                return None
            element,length=self.arrays[typ]
            checked=self.op('array_bounds',layer,[index.id],index.type,['TYPE-036','TYPE-069','TYPE-070','TRANS-FAIL-001'],array_length=length)
            self.checked_edges(layer,checked,failure='bounds')
            proofs.append(checked); lengths.append(length); typ=element
        return root,typ,proofs,const,lengths

    def checked_index(self, node):
        result=self.checked_index_chain(node)
        if result is None: return None
        root,typ,proofs,const,lengths=result
        return root,typ,proofs[-1],const

    def expression(self,node,expected=None,mode='read',allow_assignment=False):
        d=node.data
        if node.kind=='array_literal':
            if expected not in self.arrays:
                self.error(node,'unsupported_array_inference','An array literal requires an expected fixed-size array type.')
                return self.op('invalid',node,typ='error')
            element,length=self.arrays[expected]; args=[]; valid=len(d['values'])==length
            if not valid: self.error(node,'array_length_mismatch',f'Expected {length} initializer elements, found {len(d["values"])}.',rules=['TYPE-035'])
            for child in d['values']:
                value=self.expression(child,element,'value'); args.append(value.id)
                valid=self.compatible(child,value.type,element) and valid
            return self.op('array_construct',node,args,expected,['TYPE-035','STATIC-TYPE-001','SEM-EVAL-001'],
                fields=['['+str(i)+']' for i in range(len(args))],type_valid=valid)
        if node.kind=='construct':
            typ=d['type']; fields=self.structs[typ]; seen=set(); args=[]; names=[]; valid=True
            for initializer in d['fields']:
                name=initializer.data['name']
                if name not in fields:
                    self.error(initializer,'unknown_field',f'{typ} has no field {name!r}.','P5',['TYPE-024']); valid=False
                elif name in seen:
                    self.error(initializer,'duplicate_field_initializer',f'Field {name!r} is initialized more than once.','P5',['TYPE-024']); valid=False
                seen.add(name)
                value=self.expression(initializer.data['value'],fields.get(name),'value')
                if name in fields: valid=self.compatible(initializer,value.type,fields[name]) and valid
                args.append(value.id); names.append(name)
            missing=set(fields)-seen
            if missing:
                self.error(node,'missing_field_initializer','Missing fields: '+', '.join(sorted(missing))+'.','P5',['TYPE-024']); valid=False
            return self.op('struct_construct',node,args,typ,['TYPE-024','STATIC-TYPE-001','SEM-EVAL-001'],fields=names,type_valid=valid)
        hint=self.expr_type_hint(node)
        if expected and is_pointer(expected) and not expected.startswith('mut ') and hint == 'mut '+expected:
            v=self.expression(node, mode='read')
            return self.op('reborrow',node,[v.id],expected,['BORROW-024','BORROW-025','STATIC-BORROW-001'],access='SharedRead')
        if node.kind=='borrow':
            target=d['value']; access='MutableExclusive' if d['mutable'] else 'SharedRead'
            is_temporary=(target.kind=='call' or self.temporary_member(target) or self.temporary_array_access(target))
            if is_temporary:
                if not self.call_temporaries:
                    self.error(node,'unsupported_temporary_borrow','Borrowing a temporary is supported only for the duration of a call; bind the value to a local to retain the borrow.')
                    return self.op('invalid',node,typ='error')
                if self.temporary_array_access(target): value=self.extract_array_temporary(target,moving=True)
                elif self.temporary_member(target): value=self.extract_temporary(target,moving=True)
                else: value=self.expression(target,mode='value')
                if is_pointer(value.type):
                    self.error(node,'unsupported_nested_pointer','Borrows of pointer-valued temporaries are not implemented.')
                    return self.op('invalid',node,typ='error')
                place=self.temporary_storage(node,value)
                rules=['TRANS-BORROW-001','BORROW-002','BORROW-064']
                pointer=self.op('borrow_mut' if d['mutable'] else 'borrow_shared',node,[place['id']],
                    ('mut ' if d['mutable'] else '')+value.type+'*',rules,access=access,temporary=True)
                return pointer
            if self.runtime_array_field(target):
                prepared=self.prepare_array_field(target)
                return self.array_field_access(node,'array_borrow',prepared,mutable=d['mutable']) if prepared else self.op('invalid',node,typ='error')
            if self.pointer_array_projection(target):
                prepared=self.prepare_pointer_index(target)
                return self.borrow_pointer_index(node,prepared,d['mutable']) if prepared else self.op('invalid',node,typ='error')
            projection=self.dynamic_struct_projection(target)
            if projection is not None:
                return self.dynamic_projection_access(node,'array_borrow',projection,mutable=d['mutable'])
            if self.dynamic_index(target):
                chain=self.checked_index_chain(target)
                if chain is None: return self.op('invalid',node,typ='error')
                root,typ,proofs,_,lengths=chain
                if len(proofs)==1:
                    return self.op('array_borrow',node,[root['id'],proofs[0].id],('mut ' if d['mutable'] else '')+typ+'*',
                        ['TRANS-BORROW-001','BORROW-002','BORROW-064','BORROW-042','TYPE-036'],access=access)
                return self.op('array_borrow',node,[root['id'],*[p.id for p in proofs]],('mut ' if d['mutable'] else '')+typ+'*',
                    ['TRANS-BORROW-001','BORROW-002','BORROW-064','BORROW-042','TYPE-036'],access=access,
                    dimension_bounds_proofs=[p.id for p in proofs],dimension_lengths=lengths)
            if self.temporary_member(target):
                self.error(node,'unsupported_temporary_place','Borrowing temporary fields is not implemented; bind the struct to a local first.')
                return self.op('invalid',node,typ='error')
            if self.projected_field(target):
                return self.field_pointer(target, d['mutable'])
            if target.kind in ('name','member','index'):
                entry=self.lookup(target)
                if entry is None:return self.op('invalid',node,typ='error')
                p,typ,_,_=entry
                if is_pointer(typ):
                    self.error(node,'unsupported_nested_pointer','Borrows of pointer storage are not implemented.')
                    return self.op('invalid',node,typ='error')
                rules=['TRANS-BORROW-001','BORROW-002','BORROW-064']
                if target.kind=='member': rules+=['BORROW-029','BORROW-032']
                return self.op('borrow_mut' if d['mutable'] else 'borrow_shared',node,[p['id']],('mut ' if d['mutable'] else '')+typ+'*',
                               rules,access=access)
            if target.kind=='deref':
                v=self.expression(target.data['value'])
                if is_pointer(v.type):
                    return self.op('reborrow',node,[v.id],('mut ' if d['mutable'] else '')+pointee(v.type)+'*',
                                   ['BORROW-021','BORROW-023','BORROW-024'],access=access)
            self.error(node,'invalid_borrow','Borrow requires a local place or a managed dereference.')
            return self.op('invalid',node,typ='error')
        if self.runtime_array_field(node):
            prepared=self.prepare_array_field(node)
            return self.array_field_access(node,'array_read',prepared) if prepared else self.op('invalid',node,typ='error')
        if self.pointer_array_projection(node):
            prepared=self.prepare_pointer_index(node)
            if prepared is None: return self.op('invalid',node,typ='error')
            pointer=self.borrow_pointer_index(node,prepared)
            return self.op('deref_read',node,[pointer.id],prepared[1],['STATIC-INIT-001','BORROW-006'])
        if node.kind=='member':
            projection=self.dynamic_struct_projection(node)
            if projection is not None:
                return self.dynamic_projection_access(node,'array_read',projection)
        if node.kind=='index':
            if self.temporary_array_access(node):
                return self.extract_array_temporary(node)
        if self.dynamic_index(node):
            chain=self.checked_index_chain(node)
            if chain is None: return self.op('invalid',node,typ='error')
            root,typ,proofs,_,lengths=chain
            attrs={}
            if len(proofs)>1: attrs=dict(dimension_bounds_proofs=[p.id for p in proofs],dimension_lengths=lengths)
            return self.op('array_read',node,[root['id'],*[p.id for p in proofs]],typ,['STATIC-INIT-001','OWNERSHIP-003','TYPE-036'],**attrs)
        if self.temporary_member(node):
            return self.extract_temporary(node)
        if self.projected_field(node):
            pointer=self.field_pointer(node, value_projection=True)
            return self.op('deref_read',node,[pointer.id],pointee(pointer.type) if is_pointer(pointer.type) else 'error',['STATIC-INIT-001','BORROW-006'])
        if node.kind=='deref':
            v=self.expression(d['value'])
            if not is_pointer(v.type):
                self.error(node,'type_error','Dereference requires a managed pointer.')
                return self.op('invalid',node,typ='error')
            return self.op('deref_read',node,[v.id],pointee(v.type),['STATIC-INIT-001','BORROW-006'])
        if node.kind=='literal':
            kind=d['literal_kind']; typ={'int':expected if expected in INTEGERS else 'i32','bool':'bool','char':'char'}.get(kind,'error')
            if typ=='error': self.error(node,'unsupported_literal',f'{kind} values are not implemented.')
            return self.op('const',node,typ=typ,rules=['STATIC-TYPE-001','PARSE-019'],constant=d['value'])
        if node.kind in ('name','member','index'):
            entry=self.lookup(node)
            if entry is None: return self.op('invalid',node,typ='error')
            place,typ,symbol,_=entry
            kind='copy' if mode=='value' else 'read'
            if kind=='copy' and typ.startswith('mut ') and is_pointer(typ): kind='move'
            rules=['STATIC-INIT-001','INITIALIZATION-001']
            if kind=='copy': rules+=['TRANS-COPY-001','OWNERSHIP-003']
            if kind=='move': rules+=['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005']
            value=self.op(kind,node,[place['id']],typ,rules,symbol=symbol['id'])
            self.fn['values'][-1]['place']=place['id']
            return value
        if node.kind=='unary':
            op=d['operator']
            if op=='move':
                if self.temporary_array_access(d['value']):
                    return self.extract_array_temporary(d['value'],moving=True)
                if self.temporary_member(d['value']):
                    return self.extract_temporary(d['value'],moving=True)
                if d['value'].kind == 'deref':
                    pointer=self.expression(d['value'].data['value'])
                    if not is_pointer(pointer.type):
                        self.error(node,'type_error','Dereference requires a managed pointer.')
                        return self.op('invalid',node,typ='error')
                    typ=pointee(pointer.type)
                    return self.op('deref_move',node,[pointer.id],typ,
                        ['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005','BORROW-009'])
                if self.runtime_array_field(d['value']):
                    prepared=self.prepare_array_field(d['value'])
                    return self.array_field_access(node,'array_move',prepared) if prepared else self.op('invalid',node,typ='error')
                if self.pointer_array_projection(d['value']):
                    prepared=self.prepare_pointer_index(d['value'])
                    if prepared is None:return self.op('invalid',node,typ='error')
                    pointer=self.borrow_pointer_index(node,prepared,True)
                    return self.op('deref_move',node,[pointer.id],prepared[1],
                        ['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005','BORROW-009','TYPE-036'])
                if d['value'].kind=='member':
                    projection=self.dynamic_struct_projection(d['value'])
                    if projection is not None:
                        return self.dynamic_projection_access(node,'array_move',projection)
                if self.dynamic_index(d['value']):
                    chain=self.checked_index_chain(d['value'])
                    if chain is None: return self.op('invalid',node,typ='error')
                    root,typ,proofs,_,lengths=chain
                    attrs={}
                    if len(proofs)>1: attrs=dict(dimension_bounds_proofs=[p.id for p in proofs],dimension_lengths=lengths)
                    return self.op('array_move',node,[root['id'],*[p.id for p in proofs]],typ,
                        ['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005','OWNERSHIP-007','OWNERSHIP-008','TYPE-036'],**attrs)
                if self.projected_field(d['value']):
                    pointer=self.field_pointer(d['value'],True,value_projection=True)
                    typ=pointee(pointer.type) if is_pointer(pointer.type) else 'error'
                    return self.op('deref_move',node,[pointer.id],typ,
                        ['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005','BORROW-009'])
                if d['value'].kind not in ('name','member','index'):
                    self.error(node,'unsupported_move_operand','Only moves from local/parameter places are implemented.')
                    return self.op('invalid',node,typ='error')
                entry=self.lookup(d['value'])
                if entry is None: return self.op('invalid',node,typ='error')
                p,typ,_,_=entry
                rules=['TRANS-MOVE-001','STATIC-OWN-002','OWNERSHIP-005']
                if d['value'].kind=='member': rules+=['OWNERSHIP-007','OWNERSHIP-008']
                return self.op('move',node,[p['id']],typ,rules)
            # Treat a signed literal as one contextual constant, permitting i8 -128.
            if op=='-' and d['value'].kind=='literal' and d['value'].data['literal_kind']=='int':
                typ=expected if expected in INTEGERS else 'i32'
                return self.op('const',node,typ=typ,rules=['PARSE-019','PARSE-020'],constant=-d['value'].data['value'])
            v=self.expression(d['value'],expected)
            typ='bool' if op=='!' else v.type
            if (op=='!' and v.type!='bool') or (op!='!' and v.type not in INTEGERS):
                self.error(node,'type_error',f'Invalid operand for {op}.',rules=['STATIC-TYPE-001']);typ='error'
            value=self.op('unary' if op=='!' else 'unary_checked',node,[v.id],typ,
                ['STATIC-TYPE-001'] if op=='!' else ['TYPE-055','TYPE-056','TYPE-058'],operator=op)
            if op!='!': self.checked_edges(node,value)
            return value
        if node.kind=='call':
            callee=d['callee']; sig=self.signatures.get(callee.data.get('name')) if callee.kind=='name' else None
            # A local declaration shadows an ordinary function name.
            if callee.kind=='name' and any(callee.data['name'] in s for s in self.scopes): sig=None
            if sig is None:
                self.error(node,'unresolved_function','Call target does not resolve to a supported function.','P4')
                for arg in d['args']: self.expression(arg,mode='value')
                return self.op('invalid',node,typ='error')
            args=[]; valid=len(sig[3])==len(d['args'])
            if not valid: self.error(node,'argument_count','Argument count does not match signature.',rules=['TYPE-051'])
            temporaries=[];self.call_temporaries.append(temporaries)
            for i,arg in enumerate(d['args']):
                wanted=sig[3][i] if i<len(sig[3]) else None
                val=self.expression(arg,wanted,'value');args.append(val.id)
                if wanted is not None: valid=self.compatible(arg,val.type,wanted) and valid
            result=self.op('call',node,[sig[0],*args],sig[4] if valid else 'error',['SEM-EVAL-001','STATIC-TYPE-002'],function=sig[1])
            self.call_temporaries.pop()
            if self.call_temporaries:
                self.call_temporaries[-1].extend(temporaries)
            else:
                for place in temporaries:
                    self.op('temporary_end',node,[place],rules=['TRANS-DESTROY-001','LIFETIME-003'],temporary=True)
            return result
        if node.kind=='binary':
            op=d['operator']
            if op=='=':
                if not allow_assignment:
                    self.error(node,'unsupported_assignment_value','Value-producing assignment expressions are not implemented.')
                    return self.op('invalid',node,typ='error')
                if self.runtime_array_field(d['left']):
                    prepared=self.prepare_array_field(d['left'])
                    if prepared is None: return self.op('invalid',node,typ='error')
                    value=self.expression(d['right'],prepared[1],'value')
                    self.array_field_access(node,'array_assign',prepared,value)
                    return Value(value.id,'void')
                if self.pointer_array_projection(d['left']):
                    prepared=self.prepare_pointer_index(d['left'])
                    if prepared is None: return self.op('invalid',node,typ='error')
                    value=self.expression(d['right'],prepared[1],'value')
                    valid=self.compatible(node,value.type,prepared[1])
                    pointer=self.borrow_pointer_index(d['left'],prepared,True,for_assignment=True)
                    self.op('deref_assign',node,[pointer.id,value.id],rules=['TYPE-066','BORROW-009'],type_valid=valid)
                    return Value(value.id,'void')
                if d['left'].kind=='member':
                    projection=self.dynamic_struct_projection(d['left'])
                    if projection is not None:
                        value=self.expression(d['right'],projection[1],'value')
                        self.dynamic_projection_access(node,'array_assign',projection,value)
                        return Value(value.id,'void')
                if self.dynamic_index(d['left']):
                    chain=self.checked_index_chain(d['left'])
                    if chain is None: return self.op('invalid',node,typ='error')
                    root,typ,proofs,const,lengths=chain
                    value=self.expression(d['right'],typ,'value')
                    valid=self.compatible(node,value.type,typ)
                    attrs=dict(type_valid=valid,const_binding=const)
                    operands=[root['id'],*[p.id for p in proofs],value.id]
                    if len(proofs)>1: attrs.update(dimension_bounds_proofs=[p.id for p in proofs],dimension_lengths=lengths,value_operand=len(operands)-1)
                    self.op('array_assign',node,operands,rules=['TYPE-066','TYPE-036'],**attrs)
                    return Value(value.id,'void')
                if self.temporary_member(d['left']):
                    self.error(node,'unsupported_temporary_place','Assigning temporary fields is not implemented; bind the struct to a local first.')
                    return self.op('invalid',node,typ='error')
                if d['left'].kind=='deref' or self.projected_field(d['left']):
                    projected=self.projected_field(d['left'])
                    pointer=self.expression(self.projection_base(d['left']) if projected else d['left'].data['value'])
                    typ=(self.expr_type_hint(d['left']) or 'error') if projected else (pointee(pointer.type) if is_pointer(pointer.type) else 'error')
                    v=self.expression(d['right'],typ,'value')
                    ok=self.compatible(node,v.type,typ)
                    if projected: pointer=self.field_pointer(d['left'], True, pointer, value_projection=True,for_assignment=True)
                    self.op('deref_assign',node,[pointer.id,v.id],rules=['TYPE-066','BORROW-009'],type_valid=ok)
                    return Value(v.id,'void')
                if d['left'].kind not in ('name','member','index'):
                    self.error(node,'invalid_assignment','Assignment requires a supported place.')
                    return self.op('invalid',node,typ='error')
                entry=self.lookup(d['left'])
                if entry is None: return self.op('invalid',node,typ='error')
                p,typ,_,const=entry
                v=self.expression(d['right'],typ,'value')
                valid=self.compatible(node,v.type,typ)
                # Assignment's value/copy contract is not specified precisely enough for this slice.
                self.op('assign',node,[p['id'],v.id],rules=['TRANS-ASSIGN-001','TYPE-066'],type_valid=valid,const_binding=const)
                return Value(v.id,'void')
            if op in ('&&','||'): return self.short_circuit(node)
            if op not in ('+','-','*','==','!=','<','<=','>','>='):
                self.error(node,'unsupported_operator',f'{op} is not implemented; no foreign-language arithmetic convention is assumed.')
                return self.op('invalid',node,typ='error')
            hint=expected if expected in INTEGERS else self.expr_type_hint(d['left']) or self.expr_type_hint(d['right'])
            left=self.expression(d['left'],hint);right=self.expression(d['right'],left.type)
            ok=self.compatible(node,right.type,left.type)
            comparison=op in ('==','!=','<','<=','>','>=')
            if left.type not in INTEGERS and not (op in ('==','!=') and left.type in ('bool','char')):
                self.error(node,'type_error',f'Operator {op} is not defined for supported operands of type {left.type}.');ok=False
            typ=('bool' if comparison else left.type) if ok else 'error'
            v=self.op('binary' if comparison else 'arithmetic_checked',node,[left.id,right.id],typ,
                ['STATIC-TYPE-001','SEM-EVAL-001'] if comparison else ['TYPE-055','TYPE-056','TYPE-058','TRANS-FAIL-001'],operator=op)
            if not comparison:
                self.checked_edges(node,v)
            return v
        raise AssertionError(node.kind)

    def checked_edges(self,node,value,failure='arithmetic'):
        # Failure profile: abort, no successful value and no guaranteed cleanup.
        success,fail=self.block(node),self.block(node)
        self.current['terminator']=dict(kind='branch',targets=[success['id'],fail['id']],operands=[],attributes={'condition':f'success({value.id})','checked_value':value.id},source_span=node.span)
        fail['terminator']=dict(kind='fail',attributes={'failure':failure,'mechanism':'abort','produces_value':False,'cleanup_guaranteed':False},source_span=node.span)
        self.current=success

    def short_circuit(self,node):
        left=self.expression(node.data['left'],'bool');self.compatible(node,left.type,'bool')
        rhs,skip,join=self.block(node),self.block(node),self.block(node)
        targets=[rhs['id'],skip['id']] if node.data['operator']=='&&' else [skip['id'],rhs['id']]
        self.current['terminator']=dict(kind='branch',targets=targets,operands=[left.id],source_span=node.span)
        self.current=rhs;right=self.expression(node.data['right'],'bool');self.compatible(node,right.type,'bool');self.jump(join,node,[right.id])
        right_block=self.current['id']
        self.current=skip;self.jump(join,node,[left.id]);skip_block=self.current['id']
        self.current=join
        return self.op('phi',node,[right.id,left.id],'bool',['STATIC-CTRL-001'],incoming_blocks=[right_block,skip_block])

    def statements(self,statements):
        for n in statements:
            if self.current is None:
                # Still resolve/type-check unreachable statements; CFG has no incoming edge.
                self.current=self.block(n)
                self.current['operations'].append(dict(id=self.ids.new('op'),kind='unreachable_source',operands=[],results=[],preconditions=[],postconditions=[],effects={},rule_refs=[],facts_established=[],facts_invalidated=[],source_span=n.span,attributes={}))
            self.statement(n)

    def statement(self,node):
        d=node.data
        if node.kind=='decl':
            typ=self.check_type(d['type'],node);p=self.declare(node,typ)
            if typ in self.structs and d['const']:
                self.error(node,'unsupported_struct_constant','Aggregate constant evaluation is not implemented.')
            if d['value']:
                v=self.expression(d['value'],typ,'value');ok=self.compatible(node,v.type,typ)
                self.op('init',node,[p['id'],v.id],rules=['TRANS-INIT-001','TYPE-004'],type_valid=ok,const_binding=d['const'])
        elif node.kind=='expr':
            if d['value'].kind=='binary' and d['value'].data['operator']=='=': self.expression(d['value'],allow_assignment=True)
            else:
                v=self.expression(d['value'],mode='value')
                if v.type!='void': self.op('discard',node,[v.id],rules=['TRANS-DESTROY-001'])
        elif node.kind=='block':
            self.enter(node);self.statements(d['statements'])
            if self.current is not None: self.exit_scope(node)
            self.scopes.pop();self.cleanup.pop()
        elif node.kind=='return':
            return_valid=True
            v=self.expression(d['value'],self.result,'value') if d['value'] else None
            if self.result=='void' and v is not None: self.error(node,'return_type','A void function cannot return a value.',rules=['TYPE-038'])
            elif self.result!='void':
                if v is None: self.error(node,'return_type','A non-void function must return a value.',rules=['TYPE-037'])
                else: return_valid=self.compatible(node,v.type,self.result)
            return_attrs={}
            if self.result in self.structs or (v and v.type in self.structs):
                return_attrs['type_valid']=return_valid and v is not None and self.result in self.structs
            self.op('return_prepare',node,[v.id] if v else [],rules=['TRANS-RET-001'],**return_attrs)
            for index in reversed(range(len(self.cleanup))): self.exit_scope(node,index)
            self.current['terminator']=dict(kind='return',operands=[v.id] if v else [],source_span=node.span)
            self.current=None
        elif node.kind=='if':
            cond=self.expression(d['condition'],'bool');self.compatible(node,cond.type,'bool')
            yes,no,join=self.block(node),self.block(node),self.block(node)
            self.current['terminator']=dict(kind='branch',targets=[yes['id'],no['id']],operands=[cond.id],source_span=node.span)
            self.current=yes;self.statement(d['yes'])
            yes_live=self.current is not None
            if yes_live:self.jump(join,node)
            self.current=no
            if d['no']:self.statement(d['no'])
            no_live=self.current is not None
            if no_live:self.jump(join,node)
            self.current=join if yes_live or no_live else None
        elif node.kind=='defer':
            # Capture lookup environment, not current values (Section 35 / D.26).
            def has_control(n):
                if n.kind in ('return','defer','if'):return True
                return any(has_control(x) for x in n.data.get('statements',[]))
            if has_control(d['body']):
                self.error(node,'unsupported_defer_control','Deferred control transfers and nested defers are not implemented.');return
            region,items=self.cleanup[-1]
            obligation=dict(id=self.ids.new('defer'),registration_order=len(items),body_block=None,captured_places=[],source_span=node.span)
            region['defer_obligations'].append(obligation)
            items.append((node,[dict(s) for s in self.scopes],obligation))
            self.op('defer_register',node,[obligation['id']],rules=['TRANS-DEFER-001'])
        else: raise AssertionError(node.kind)

    def exit_scope(self,node,index=None):
        index=len(self.cleanup)-1 if index is None else index
        region,items=self.cleanup[index]
        for registration,scopes,obligation in reversed(items):
            self.op('defer_execute',registration,[obligation['id']],rules=['TRANS-DEFER-002'])
            old_scopes=self.scopes;self.scopes=[dict(s) for s in scopes]
            existing_ops={op['id'] for b in self.fn['blocks'] for op in b['operations']}
            placeids={entry[0]['id'] for scope in scopes for entry in scope.values()}
            placeids.update(child['id'] for pid in list(placeids) for child in self.component_paths(pid).values())
            obligation['body_block']=obligation['body_block'] or self.current['id']
            self.statement(registration.data['body'])
            # Include operations on all success/failure blocks created during expansion.
            expanded=[op for b in self.fn['blocks'] for op in b['operations'] if op['id'] not in existing_ops]
            used={x for op in expanded for x in op['operands'] if x in placeids}
            for op in expanded:op['attributes']['defer_origin']=obligation['id']
            obligation['captured_places']=sorted(set(obligation['captured_places'])|used)
            self.scopes=old_scopes
        def cleanup_place(pid):
            if pid in self.components:
                for child in reversed(list(self.components[pid].values())):
                    cleanup_place(child['id'])
                self.op('struct_storage_end',node,[pid],rules=['TRANS-DESTROY-001'])
            else:
                self.op('destroy',node,[pid],rules=['TRANS-DESTROY-001','STATIC-INIT-002','DESTRUCTION-015'],guard='initialized_and_owned')
            p=next(p for p in self.fn['places'] if p['id']==pid)
            self.op('lifetime_end',node,[p['lifetime']],rules=['TRANS-DESTROY-001'])
        for pid in reversed(region['destruction_places']): cleanup_place(pid)

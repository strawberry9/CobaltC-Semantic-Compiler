"""ESIR construction, canonical serialization, schema and reference validation."""
import json
from .artifacts import artifact, corpus


def dumps(doc):
    return json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'


def build(source,ids,diagnostics,ast=None,graph=None):
    doc=dict(format={'name':'CobaltC-Explainable-Semantic-IR','version':'1.0.0','language':'CobaltC','language_publication':'1.0.3'},
        compilation={'compiler':{'id':'cobaltc-semantic','version':'0.1.0','support_profile':'scalar-milestone','conformance_claim':False},
                     'result':'incomplete','analysis_model':'CobaltC-1.0.3-formal-semantic-model-v3','source_hashes':{source.path:source.hash}},
        source_files=[dict(id=source.id,path=source.path,encoding='UTF-8',hash=source.hash)],
        modules=[],types=[],symbols=[],functions=[],contracts=[],rules=[],diagnostics=diagnostics.items,summary={})
    if ast:
        doc['modules']=[dict(id=ids.new('module'),name=ast.data['name'],imports=[],exports=[x.text for x in ast.data['exports']],source_span=ast.span)]
    if graph:
        doc.update(types=list(graph.types.values()),symbols=graph.symbols,functions=graph.functions)
    errors=diagnostics.items
    incomplete=any(d['code'].startswith('unsupported_') for d in errors) or (graph is None and not errors)
    result='incomplete' if incomplete else 'invalid' if errors else 'valid'
    doc['compilation']['result']=result
    ops=[op for fn in doc['functions'] for b in fn['blocks'] for op in b['operations']]
    referenced=sorted({r for item in [*ops,*errors] for r in item.get('rule_refs',[])})
    classified,formal=corpus()
    for ref in referenced:
        if ref in formal:doc['rules'].append(dict(id=ref,formal_rule=ref,source_rules=[]))
        elif ref in classified:doc['rules'].append(dict(id=ref,source_rules=[ref],category=classified[ref]['primary_category']))
        else:raise ValueError(f'Unknown rule {ref}')
    checked=['V_type','V_init','V_owner','V_control','V_destroy'] if graph else []
    if graph and any(t['kind'] == 'managed_pointer' for t in doc['types']):
        doc['compilation']['compiler']['support_profile'] = 'managed-scalar-milestone'
        checked += ['V_borrow', 'V_lifetime']
    if graph and any(t['kind'] == 'struct' for t in doc['types']):
        doc['compilation']['compiler']['support_profile'] = 'scalar-field-struct-milestone'
    if graph and any(t['kind'] == 'array' for t in doc['types']):
        doc['compilation']['compiler']['support_profile'] = 'scalar-array-milestone'
    array_types={t['id']:t for t in doc['types'] if t['kind']=='array'}
    multidimensional=graph and any(array_types.get(arg,{}).get('kind')=='array' for t in array_types.values() for arg in t.get('args', []))
    if multidimensional:
        doc['compilation']['compiler']['support_profile'] = 'multidimensional-array-milestone'
    struct_ids = {t['id'] for t in doc['types'] if t['kind']=='struct'}
    struct_arrays=graph and any(t['kind']=='array' and any(arg in struct_ids for arg in t.get('args', [])) for t in doc['types'])
    if struct_arrays:
        doc['compilation']['compiler']['support_profile'] = 'multidimensional-struct-array-milestone' if multidimensional else 'struct-array-milestone'
    doc['summary']=dict(valid=result=='valid',operation_count=len(ops),diagnostic_count=len(errors),
        invariants_checked=checked,invariants_satisfied=checked if result=='valid' else [],invariants_failed=[])
    return doc


class ValidationError(ValueError): pass


def validate_schema(doc):
    """Evaluate every validation keyword used by the supplied schema.

    This is deliberately not a general Draft 2020-12 implementation. Unknown schema
    keywords fail closed so a schema upgrade cannot silently bypass validation.
    """
    schema=artifact('Explainable_Semantic_IR.schema.json')
    known={'$schema','$id','$defs','title','description','$ref','type','properties','additionalProperties','required','items','enum','const','minimum','minLength'}
    types={'object':lambda v:isinstance(v,dict),'array':lambda v:isinstance(v,list),
        'string':lambda v:isinstance(v,str),'integer':lambda v:type(v)is int,
        'boolean':lambda v:type(v)is bool,'null':lambda v:v is None}
    def check(value,rule,path):
        if set(rule)-known:raise ValidationError(f'Unsupported schema keywords: {set(rule)-known}')
        if '$ref' in rule:
            ref=rule['$ref']
            if not ref.startswith('#/$defs/'):raise ValidationError(f'Unsupported reference {ref}')
            check(value,schema['$defs'][ref.split('/')[-1]],path);return
        if 'type' in rule:
            kinds=rule['type'] if isinstance(rule['type'],list) else [rule['type']]
            if not any(types[k](value) for k in kinds):raise ValidationError(f'{path}: expected {kinds}, got {type(value).__name__}')
        if 'const' in rule and value!=rule['const']:raise ValidationError(f'{path}: incorrect constant')
        if 'enum' in rule and value not in rule['enum']:raise ValidationError(f'{path}: not in enum')
        if 'minimum' in rule and value<rule['minimum']:raise ValidationError(f'{path}: below minimum')
        if 'minLength' in rule and len(value)<rule['minLength']:raise ValidationError(f'{path}: too short')
        if isinstance(value,dict):
            missing=set(rule.get('required',[]))-set(value)
            if missing:raise ValidationError(f'{path}: missing {sorted(missing)}')
            props=rule.get('properties',{})
            for k,v in value.items():
                if k in props:check(v,props[k],path+'.'+k)
                elif rule.get('additionalProperties') is False:raise ValidationError(f'{path}: extra field {k}')
                elif isinstance(rule.get('additionalProperties'),dict):check(v,rule['additionalProperties'],path+'.'+k)
        if isinstance(value,list) and 'items' in rule:
            for i,v in enumerate(value):check(v,rule['items'],f'{path}[{i}]')
    check(doc,schema,'$')


def validate_references(doc):
    entities={}
    def collect(v):
        if isinstance(v,dict):
            if 'id' in v and v is not doc['compilation'].get('compiler'):
                if v['id'] in entities:raise ValidationError(f'Duplicate ID {v["id"]}')
                entities[v['id']]=v
            for key,child in v.items():
                # Attributes are implementation metadata, not entity definitions.
                if key!='attributes':collect(child)
        elif isinstance(v,list):
            for child in v:collect(child)
    collect(doc)
    def require(ref,kind=None):
        if ref is not None and ref not in entities:raise ValidationError(f'Unresolved reference {ref}')
        if ref is not None and kind is not None and ref not in kind:raise ValidationError(f'Wrong reference category: {ref}')
    types={t['id'] for t in doc['types']}; rules={r['id'] for r in doc['rules']}
    source_rules,formal=corpus()
    for rule in doc['rules']:
        if rule['id'] not in source_rules and rule['id'] not in formal:raise ValidationError('Unknown rule ID')
        for ref in rule.get('source_rules',[]):
            if ref not in source_rules:raise ValidationError('Unknown source rule')
        if 'formal_rule' in rule and rule['formal_rule'] not in formal:raise ValidationError('Unknown formal rule')
    for t in doc['types']:
        for ref in t.get('args', []): require(ref,types)
        for field in t.get('fields', []): require(field.get('type'),types)
        require(t.get('return_type'),types)
        for p in t.get('parameters',[]):require(p.get('type'),types)
    for s in doc['symbols']:require(s['type'],types);require(s.get('place'))
    for fn in doc['functions']:
        require(fn['type'],types);blocks={b['id'] for b in fn['blocks']};require(fn['entry_block'],blocks)
        local={e['id'] for group in ('places','values','capabilities','lifetimes','cleanup_regions','unsafe_regions','blocks') for e in fn[group]}
        for group in ('places','values'):
            for e in fn[group]:
                require(e['type'],types)
                for key in ('lifetime','parent','place','capability'):require(e.get(key),local)
                require(e.get('origin_op'))
        for cap in fn['capabilities']:
            require(cap['referent'],local);require(cap['lifetime'],local);require(cap.get('derived_from'),local);require(cap.get('origin'))
        for life in fn['lifetimes']:require(life['referent'],local);require(life.get('parent'),local)
        for region in fn['cleanup_regions']:
            require(region['parent'],local)
            for ref in region['destruction_places']:require(ref,local)
            for defer in region['defer_obligations']:
                require(defer.get('body_block'),blocks)
                for ref in defer.get('captured_places',[]):require(ref,local)
        for b in fn['blocks']:
            for ref in b['terminator'].get('targets',[]):require(ref,blocks)
            for ref in b['terminator'].get('operands',[]):require(ref,local)
            for op in b['operations']:
                for ref in op['operands']+op['results']:require(ref)
                for ref in op['rule_refs']:require(ref,rules)
    for diag in doc['diagnostics']:
        for ref in diag.get('related_entities',[]):require(ref)
        for ref in diag.get('rule_refs',[]):require(ref,rules)
    ops=[o for f in doc['functions'] for b in f['blocks'] for o in b['operations']]
    if doc['summary']['operation_count']!=len(ops) or doc['summary']['diagnostic_count']!=len(doc['diagnostics']):raise ValidationError('Summary counts do not match')
    if doc['summary']['valid']!=(doc['compilation']['result']=='valid'):raise ValidationError('Validity mismatch')


def validate(doc):
    validate_schema(doc);validate_references(doc)

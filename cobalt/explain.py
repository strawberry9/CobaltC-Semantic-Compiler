"""Render ESIR as a standalone, offline HTML report: python -m cobalt.explain."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sys

from .esir import validate_schema
from .narrative import interpret


def location(entity):
    span = entity.get('source_span', {})
    if not span:
        return 'No source location'
    return f"{span['file']}:{span['start_line']}:{span['start_col']}"


def source_section(doc, input_path=None):
    parts = ['<section class="source"><h2>Source code</h2>']
    for source in doc['source_files']:
        name = source['path']
        path = Path(name)
        candidates = [path]
        if input_path is not None and not path.is_absolute():
            parent = Path(input_path).resolve().parent
            candidates.extend([parent / path, parent / path.name])
        text = None
        for candidate in candidates:
            try:
                contents = candidate.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                continue
            # Prefer a matching copy if more than one location is available.
            if text is None:
                text = contents
            if hashlib.sha256(contents.encode('utf-8')).hexdigest() == source.get('hash'):
                text = contents
                break
        parts.append('<h3>'+escape(name)+'</h3>')
        if text is None:
            parts.append('<p class="muted">Source file unavailable. Keep the source file alongside the ESIR JSON or at its recorded path to include it.</p>')
        else:
            if source.get('hash') and hashlib.sha256(text.encode('utf-8')).hexdigest() != source['hash']:
                parts.append('<p class="muted">This source file has changed since compilation; the explanation may describe an earlier version.</p>')
            parts.append('<pre><code>'+escape(text)+'</code></pre>')
    parts.append('</section>')
    return '\n'.join(parts)


def render(doc, input_path=None):
    validate_schema(doc)
    types = {t['id']: t['name'] for t in doc['types']}
    names = dict(types)
    names.update({s['id']: s['name'] for s in doc['symbols']})
    names.update({s['place']: s['name'] for s in doc['symbols'] if s.get('place')})
    for fn in doc['functions']:
        for lifetime in fn['lifetimes']:
            names[lifetime['id']] = f"lifetime of {names.get(lifetime['referent'], lifetime['referent'])}"
    # Keep value IDs in the report: a snapshot is not the binding's current value.
    def label(ref):
        return names.get(ref, ref)

    def friendly(text):
        return re.sub(r'\b[A-Za-z_][A-Za-z_0-9]*\b', lambda m: label(m.group()), str(text))

    def code(text):
        return '<code>' + escape(str(text)) + '</code>'

    def table(headers, rows):
        return '<div class="scroll"><table><thead><tr>' + ''.join('<th>'+escape(h)+'</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+c+'</td>' for c in row)+'</tr>' for row in rows) + '</tbody></table></div>'

    def details(title, data):
        return '<details><summary>'+escape(title)+'</summary><pre>'+escape(json.dumps(data, ensure_ascii=False, indent=2))+'</pre></details>'

    def state(s):
        return ' / '.join(', '.join(s.get(k, [])) for k in ('initialization', 'ownership'))

    def description(op):
        args = [label(x) for x in op['operands']]
        result = ', '.join(op['results'])
        a = op.get('attributes', {})
        kind = op['kind']
        x = args[0] if args else '?'
        y = args[1] if len(args) > 1 else '?'
        if a.get('projected_field') and kind in ('array_read','array_move','array_assign','array_borrow'):
            action={'array_read':'Copy','array_move':'Move','array_assign':'Replace','array_borrow':'Borrow'}[kind]
            if a.get('dimension_bounds_proofs'):
                indices=''.join(f'[{label(ref)}]' for ref in a['dimension_bounds_proofs'])
                return f'{action} projected field {a["projected_field"]} of {x}{indices} after checking every array dimension.'
            inner=f' and checked inner index {label(a["inner_bounds_proof"])}' if a.get('inner_bounds_proof') else ''
            return f'{action} projected field {a["projected_field"]} of {x} selected by checked index {y}{inner}.'
        if kind == 'alloca': return f'Reserve storage for {x} (not initialized yet).'
        if kind == 'parameter' and 'field_states_after' in a: return f'Receive {x} by value from the caller, owning its initialized fields.'
        if kind == 'parameter': return f'Initialize parameter {x} from the caller.'
        if kind in ('borrow_shared', 'borrow_mut'):
            if a.get('temporary'): return f'{result} = borrow the materialized temporary {x} for this call expression; its storage ends immediately after the call unless the borrow escapes, which is rejected.'
            return f'{result} = create a {"shared" if kind == "borrow_shared" else "mutable"} borrow of {x}; ownership stays with the referent.'
        if kind == 'temporary_end': return f'End the temporary borrow storage {x} after the call and destroy its remaining owned value.'
        if kind == 'indexed_field_borrow':
            if a.get('dimension_bounds_proofs') or a.get('field_suffix'):
                indices=''.join(f'[{label(ref)}]' for ref in a.get('dimension_bounds_proofs',[args[1]]))
                suffix='.'+a['field_suffix'] if a.get('field_suffix') else ''
                target=f'{x}->{a["field"]}' if a.get('field') else f'*{x}'
                return f'{result} = borrow {target}{indices}{suffix}; every dimension is bounds checked and permissions cover all possible elements.'
            if not a.get('field'):
                return f'{result} = borrow the checked element {y} through *{x} with {a["access"]} access.'
            return f'{result} = borrow the checked element {y} of array field {a["field"]} through {x} with {a["access"]} access.'
        if kind == 'field_borrow': return f'{result} = borrow field {a["field"]} through struct pointer {x} with {a.get("access", "recorded")} access.'
        if kind == 'reborrow': return f'{result} = reborrow through {x} with {a.get("access", "recorded")} access.'
        if kind == 'deref_read' and a.get('array_referents'): return f'{result} = copy the whole array through {x}, creating independent element values.'
        if kind == 'deref_assign' and a.get('array_referents'): return f'Replace the whole array selected by {x} with {y} after successful RHS evaluation; destroy its previous elements.'
        if kind == 'deref_move' and a.get('struct_referents'): return f'{result} = move the whole struct through exclusive capability {x}; its fields become moved and their identities transfer to the result.'
        if kind == 'deref_move': return f'{result} = move the value through exclusive capability {x}; its referent becomes unavailable until reinitialized.'
        if kind == 'deref_read' and a.get('struct_referents'): return f'{result} = copy the whole struct through {x}, creating independent field values.'
        if kind == 'deref_assign' and a.get('struct_referents'): return f'Replace the whole struct selected by {x} with {y} after successful RHS evaluation; destroy its previous fields.'
        if kind == 'deref_read': return f'{result} = read the value through {x}.'
        if kind == 'deref_assign': return f'Store {y} through the mutable capability {x}.'
        if kind == 'const': return f'{result} = literal {json.dumps(a.get("constant"), ensure_ascii=False)}'
        if kind == 'struct_extract': return f'{result} = copy field {a["field"]} from temporary {x}; its cleanup follows the copy.'
        if kind == 'array_extract': return f'{result} = copy the element of temporary {x} selected by checked index {y}; temporary cleanup follows the copy.'
        if kind == 'array_move_extract': return f'{result} = transfer the element of temporary {x} selected by checked index {y}; cleanup destroys unselected elements and preserves the selected element identity.'
        if kind == 'array_borrow' and a.get('dimension_bounds_proofs'):
            indices=''.join(f'[{label(ref)}]' for ref in a['dimension_bounds_proofs'])
            return f'{result} = borrow {x}{indices}; each dimension is bounds checked and permissions cover all possible cells.'
        if kind == 'array_move' and a.get('dimension_bounds_proofs'):
            indices=''.join(f'[{label(ref)}]' for ref in a['dimension_bounds_proofs'])
            return f'{result} = move the element of {x}{indices}; bounds are checked at each dimension.'
        if kind == 'array_move': return f'{result} = move the element of {x} selected by checked index {y}; other possible targets retain their values.'
        if kind == 'array_borrow': return f'{result} = borrow the element of {x} selected by checked index {y} with {a["access"]} access; recorded capabilities cover its possible elements.'
        if kind == 'array_bounds': return f'{result} = check 0 <= {x} < {a["array_length"]}; continue on success, abort on bounds failure.'
        if kind == 'array_read' and a.get('dimension_bounds_proofs'):
            indices=''.join(f'[{label(ref)}]' for ref in a['dimension_bounds_proofs'])
            return f'{result} = copy the element of {x}{indices}; bounds are checked at each dimension.'
        if kind == 'array_read': return f'{result} = copy the element of {x} selected by checked index {y}.'
        if kind == 'array_assign' and a.get('dimension_bounds_proofs'):
            indices=''.join(f'[{label(ref)}]' for ref in a['dimension_bounds_proofs'])
            return f'Write {label(args[a["value_operand"]])} to {x}{indices} after bounds checks at each dimension.'
        if kind == 'array_assign': return f'Write {args[2]} to the element of {x} selected by checked index {y}.'
        if kind == 'array_construct': return f'{result} = construct an array with elements [' + ', '.join(args) + '].'
        if kind == 'struct_construct': return f'{result} = construct a struct with ' + ', '.join(name+' = '+value for name, value in zip(a['fields'], args)) + '.'
        if kind == 'struct_storage_end': return f'Finish cleanup of {x}; its scalar fields have separate guarded cleanup operations.'
        if kind == 'read': return f'{result} = read {x}'
        if kind == 'copy': return f'{result} = copy {x}; the source keeps its value.'
        if kind == 'move': return f'{result} = move {x}; the source loses the transferred value.'
        if kind in ('init', 'assign'): return f'Store {y} in {x}.'
        if kind in ('binary', 'arithmetic_checked'): return f'{result} = {x} {a.get("operator", "?")} {y}' + (' (checked for arithmetic failure)' if kind == 'arithmetic_checked' else '')
        if kind in ('unary', 'unary_checked'): return f'{result} = {a.get("operator", "?")}{x}'
        if kind == 'return_prepare': return f'Prepare return {", ".join(args) or "without a value"}; run cleanup before returning.'
        if kind == 'destroy':
            if a.get('executes_if_initialized') is False: return f'Skip destruction of {x}: it has no initialized owned value.'
            return f'Destroy {x} if initialized and owned.'
        if kind == 'lifetime_end': return f'End {x}.'
        if kind == 'call': return f'{result + " = " if result else ""}call {x}({", ".join(args[1:])})'
        if kind == 'phi': return f'{result} = the value from the incoming branch ({", ".join(args)}).'
        if kind == 'defer_register': return f'Register deferred block {x} for scope exit.'
        if kind == 'defer_execute': return f'Execute deferred block {x} using the current binding values.'
        if kind == 'discard': return f'Discard temporary {x}.'
        return f'{kind}: {", ".join(args)}' + (f' → {result}' if result else '')

    title = ', '.join(m['name'] for m in doc['modules']) or 'Compilation report'
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>'+escape(title)+' · ESIR report</title>', '<style>'+CSS+'</style><main>',
             '<p class="eyebrow">CobaltC · Semantic report</p><h1>'+escape(title)+'</h1>',
             '<p><strong>'+escape(doc['compilation']['result'].upper())+'</strong> · '+str(len(doc['functions']))+' functions · '+str(doc['summary']['operation_count'])+' operations · '+str(len(doc['diagnostics']))+' diagnostics</p>',
             '<p class="muted">This is a static analysis report, not an execution trace. Branches are alternatives. “Valid” reflects the compiler’s implemented checks; it is not a full language conformance certificate.</p>',
             '<nav>'+ ' '.join('<a href="#'+escape(fn['id'], quote=True)+'">'+escape(fn['name'])+'</a>' for fn in doc['functions'])+'</nav>']
    parts.append(source_section(doc, input_path))
    structs = [t for t in doc['types'] if t['kind'] == 'struct']
    if structs: parts.append(details('Struct declarations', structs))
    arrays = [t for t in doc['types'] if t['kind'] == 'array']
    if arrays: parts.append(details('Fixed-size array types', arrays))
    paragraphs, interpretations = interpret(doc)
    parts.append('<section class="interpretation"><h2>Plain-English interpretation</h2>')
    parts.extend('<p>'+escape(p)+'</p>' for p in paragraphs)
    for interpretation in interpretations:
        parts.append('<h3>'+escape(interpretation['name'])+'</h3>')
        parts.extend('<p>'+escape(p)+'</p>' for p in interpretation['paragraphs'])
        if interpretation['paths']:
            parts.append('<p>Paths through the reported branches (not a record of a run). Some combinations of conditions may be impossible:</p>')
        for conditions, steps in interpretation['paths']:
            heading = 'When ' + ' and '.join(conditions) if conditions else 'Steps'
            parts.append('<h4>'+escape(heading)+'</h4><ol>')
            parts.extend('<li>'+escape(step)+'</li>' for step in steps)
            parts.append('</ol>')
        if interpretation['truncated']:
            parts.append('<p>This overview shows at most eight paths. The detailed control flow below contains the rest.</p>')
    parts.append('<p class="muted">Internal labels identify storage, temporary values, and operations. Expand the details below to inspect the evidence behind this interpretation.</p></section>')
    if doc['diagnostics']:
        parts.append('<h2>Diagnostics</h2>')
        for d in doc['diagnostics']:
            parts.append('<article class="diagnostic"><strong>'+escape(d['code'])+'</strong><p>'+escape(d['message'])+'</p><small>'+escape(location(d))+'</small>'+details('Diagnostic details', d)+'</article>')
    for fn in doc['functions']:
        parts.append('<section id="'+escape(fn['id'], quote=True)+'"><h2>Function '+escape(fn['name'])+'</h2><p class="muted">'+escape(location(fn))+'</p>')
        rows = [[code(label(p['id'])), code(types.get(p['type'],p['type'])), escape(p['mutability']), code(p['id'])] for p in fn['places']]
        parts.append(table(['Binding', 'Type', 'Mutability', 'Storage ID'], rows))
        parts.append('<h3>Control flow</h3><p>Start at <a href="#'+escape(fn['entry_block'], quote=True)+'">'+escape(fn['entry_block'])+'</a>. Follow the labeled links; block listing order is not execution order.</p>')
        flow = []
        for b in fn['blocks']:
            t = b['terminator']; a = t.get('attributes', {}); targets = t.get('targets', [])
            condition = ', '.join(label(x) for x in t.get('operands', []))
            if t['kind'] == 'branch':
                condition = friendly(a.get('condition', condition))
                labels = ['success', 'failure'] if a.get('checked_value') else ['true', 'false']
                edges = ' · '.join(escape(labels[i] if i < 2 else str(i))+': <a href="#'+escape(target, quote=True)+'">'+escape(target)+'</a>' for i,target in enumerate(targets))
                text = 'Branch on '+code(condition)+' → '+edges
            elif targets:
                text = escape(t['kind'])+' → '+', '.join('<a href="#'+escape(x, quote=True)+'">'+escape(x)+'</a>' for x in targets)
            elif t['kind'] == 'return': text = 'Return '+code(condition or 'void')
            elif t['kind'] == 'fail': text = 'Failure: '+escape(a.get('mechanism', 'see details'))+'; no successful result.'
            else: text = escape(t['kind'])
            flow.append(['<a href="#'+escape(b['id'], quote=True)+'">'+escape(b['id'])+'</a>',text])
        parts.append(table(['Block', 'Next step'], flow))
        for b in fn['blocks']:
            parts.append('<article class="block" id="'+escape(b['id'], quote=True)+'"><h3>'+escape(b['id'])+'</h3>')
            if not b['operations']: parts.append('<p class="muted">No operations in this block.</p>')
            for op in b['operations']:
                a = op.get('attributes', {}); status = a.get('validation', 'not recorded')
                prefix = 'Unreachable: ' if a.get('reachable') is False else 'Invalid attempted operation: ' if status == 'invalid' else ''
                parts.append('<div class="operation"><div class="op-heading"><span>'+escape(prefix+description(op))+'</span><small>'+escape(location(op))+'</small></div>')
                if a.get('state_before') != a.get('state_after') and a.get('state_after'):
                    parts.append('<p class="transition">'+escape(state(a.get('state_before', {})))+' → <strong>'+escape(state(a['state_after']))+'</strong></p>')
                if a.get('field_states_after') is not None and a.get('field_states_before') != a['field_states_after']:
                    root=label(a['aggregate_place'])
                    parts.append('<p class="muted">Fields of '+escape(root)+': '+escape('; '.join(name+' = '+', '.join(s['initialization']) for name,s in a['field_states_after'].items()))+'</p>')
                if a.get('struct_arguments'):
                    rows = [[str(arg['index']+1), code(label(arg['value'])), code(label(arg['parameter_place'])), ', '.join(arg['field_states']) or '(empty struct)'] for arg in a['struct_arguments']]
                    parts.append(table(['Argument','Owned value','Callee parameter','Transferred fields'], rows))
                if 'returned_field_states' in a:
                    parts.append('<p class="muted">Prepared return fields: '+escape(', '.join(a['returned_field_states']) or '(empty struct)')+'. Their values survive local cleanup.</p>')
                if a.get('bounds_check') and 'array_index' in a:
                    parts.append('<p class="muted">Array index '+str(a['array_index'])+' is proven in bounds for length '+str(a['array_length'])+'.</p>')
                facts = op['facts_established']
                if facts: parts.append('<p class="muted">Established: '+escape('; '.join(friendly(x) for x in facts))+'</p>')
                if a.get('ended_capabilities'):
                    parts.append('<p class="muted">Borrow no longer needed after this step: '+escape(', '.join(a['ended_capabilities']))+'.</p>')
                if a.get('overlap_checks'):
                    rows=[[code(label(c['place'])),code(label(c['referent'])),
                           'Conflicting access' if c['conflicting'] else 'Compatible shared access' if c['overlap'] else 'Disjoint storage'] for c in a['overlap_checks']]
                    parts.append(table(['Accessed storage','Borrowed storage','Overlap check'],rows))
                parts.append(details('Why / effects / exact IDs · '+op['id'], op)+'</div>')
            parts.append(details('Block exit details', b['terminator'])+'</article>')
        for key, heading in [('values','Values and their origins'), ('lifetimes','Lifetimes'), ('capabilities','Borrow capabilities'), ('cleanup_regions','Cleanup regions'), ('unsafe_regions','Unsafe regions')]:
            if fn[key]: parts.append(details(heading, fn[key]))
        parts.append('</section>')
    parts.append(details('Rule references', doc['rules']))
    parts.append(details('Compilation metadata and checked invariants', {'compilation':doc['compilation'],'summary':doc['summary']}))
    if doc['contracts']: parts.append(details('External contracts', doc['contracts']))
    parts.append('</main></html>')
    return '\n'.join(parts)+'\n'


CSS = '''
:root { color-scheme: light; font: 16px/1.55 system-ui,sans-serif; color:#203040; background:#f3f5f7; }
body { margin:0; } main { max-width:1100px; margin:auto; padding:40px 24px 80px; }
h1 { font-size:2.2rem; margin:.2em 0; } h2 { margin-top:2em; } h3 { margin:1em 0 .5em; }
.eyebrow { color:#315eb1; letter-spacing:.1em; text-transform:uppercase; font-size:.8rem; }
.muted,small { color:#586575; } small { font-size:.8rem; } a { color:#1752ad; }
nav { display:flex; gap:16px; flex-wrap:wrap; } .scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; background:white; } td,th { text-align:left; padding:10px 14px; border-bottom:1px solid #dce2e8; } th { background:#e8edf3; }
.block,.diagnostic { background:white; border:1px solid #dce2e8; border-radius:10px; padding:12px 22px; margin:20px 0; scroll-margin-top:16px; }
.interpretation { background:#eef5ff; border:1px solid #c5d8f4; border-radius:10px; padding:8px 24px 20px; margin:24px 0; }
.interpretation h2 { margin-top:.7em; }
.diagnostic { border-left:5px solid #b84839; } .operation { padding:14px 0; border-top:1px solid #e6ebef; }
.op-heading { display:flex; justify-content:space-between; gap:16px; align-items:baseline; flex-wrap:wrap; }
.transition { color:#1b6657; } p { margin:.6em 0; } details { margin:12px 0; } summary { cursor:pointer; color:#31527b; }
pre { background:#f3f5f7; padding:14px; overflow:auto; font-size:.8rem; max-height:500px; }
code { font-size:.87em; background:#eef2f6; padding:2px 4px; border-radius:3px; }
.source pre { background:white; border:1px solid #dce2e8; border-radius:10px; max-height:none; }
.source pre code { font-size:inherit; background:transparent; padding:0; }
@media print { main { padding:0; } .block { break-inside:avoid; } }
'''


def main():
    parser = argparse.ArgumentParser(description='Turn ESIR JSON into a readable offline HTML report.')
    parser.add_argument('input', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.input.with_suffix('.html')
    if output.resolve() == args.input.resolve():
        parser.error('Output must differ from the input JSON.')
    try:
        html = render(json.loads(args.input.read_text(encoding='utf-8')), args.input)
        output.write_text(html, encoding='utf-8')
    except (OSError, ValueError) as error:
        print(f'cobalt.explain: {error}', file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())

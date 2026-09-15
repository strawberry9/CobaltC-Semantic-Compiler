"""Deterministic plain-English descriptions derived only from recorded ESIR."""
import json


def interpret(doc):
    """Return text paragraphs and bounded path descriptions, without executing code."""
    result = doc['compilation']['result']
    intro = {
        'valid': 'The program passed the checks implemented by this compiler. It has not been run.',
        'invalid': 'The compiler found errors. The steps below describe the available analysis, not a program that is safe to execute.',
        'incomplete': 'The compiler could not finish analyzing this program. Unsupported features may be the reason; this does not by itself mean the source program is wrong.',
    }[result]
    paragraphs = [intro]
    allops=[o for fn in doc['functions'] for b in fn['blocks'] for o in b['operations']]
    profile=doc['compilation']['compiler'].get('support_profile')
    if profile in ('multidimensional-array-milestone','multidimensional-struct-array-milestone'):
        selected='struct elements and their fields' if profile == 'multidimensional-struct-array-milestone' else 'scalar cells'
        paragraphs.append(f'Nested fixed-size arrays use an independent length and initialization state at each dimension. Indices evaluate and check in order. Literal or runtime indices can select rows or {selected}; partial moves and borrows apply to the selected candidates while disjoint rows and elements remain independent.')
        if any(o.get('attributes',{}).get('dimension_bounds_proofs') for o in allops):
            paragraphs.append('When multiple dimensions use runtime indices, the report records each bounds proof and tracks the possible cell combinations. Known indices narrow those combinations; unknown-index reads and moves require every candidate cell to be available. Repeating unknown indices does not prove that a moved cell was restored.')
    if profile in ('struct-array-milestone','multidimensional-struct-array-milestone'):
        paragraphs.append('Arrays of structs track each element and its descendant fields separately. Known indices identify disjoint elements. Runtime whole-element access checks bounds and tracks alternative field states. Moving a field or element restricts containing values until restored; cleanup destroys only initialized owned scalar leaves.')
    if profile == 'multidimensional-struct-array-milestone':
        paragraphs.append('Struct elements may be nested through multiple fixed-size dimensions. Each selected struct and its fields retains separate ownership and borrow state. Runtime indexing tracks possible struct candidates at every dimension; indexed field projections apply to the selected structs after all dimension checks.')
    if not doc['functions']:
        paragraphs.append('No function behavior is available to explain because this report contains no analyzed function bodies.')
    for d in doc['diagnostics']:
        if d['severity'] == 'error':
            span = d.get('source_span', {})
            where = f" At line {span['start_line']}: " if span else ' '
            paragraphs.append('The compiler reports:' + where + d['message'])
    functions = []
    types = {t['id']: t['name'] for t in doc['types']}
    for fn in doc['functions']:
        value_types = {v['id']: types[v['type']] for v in fn['values']}
        names = {s.get('place', s['id']): s['name'] for s in doc['symbols']}
        names.update({s['id']: s['name'] for s in doc['symbols']})
        blocks = {b['id']: b for b in fn['blocks']}
        producers = {v: o for b in fn['blocks'] for o in b['operations'] for v in o['results']}

        def expression(ref, seen=frozenset()):
            if ref in names:
                return names[ref]
            if ref in seen or len(seen) > 12:
                return 'an intermediate value'
            op = producers.get(ref)
            if not op:
                return 'an intermediate value'
            a, args, kind = op.get('attributes', {}), op['operands'], op['kind']
            next_seen = seen | {ref}
            if kind == 'const':
                if 'constant' not in a:
                    return 'a literal value'
                return json.dumps(a['constant'], ensure_ascii=False)
            if kind == 'struct_extract':
                return 'field '+a['field']+' of '+expression(args[0], next_seen)
            if a.get('projected_field') and kind in ('array_read','array_move','array_borrow'):
                proofs=a.get('dimension_bounds_proofs')
                target=names.get(args[0],args[0])+''.join('['+expression(ref,next_seen)+']' for ref in proofs) if proofs else names.get(args[0],args[0])+'['+expression(args[1],next_seen)+']'
                target+='.'+a['projected_field']
                if a.get('inner_bounds_proof'): target+='['+expression(a['inner_bounds_proof'],next_seen)+']'
                prefix='a borrow of ' if kind=='array_borrow' else 'the moved field ' if kind=='array_move' else ''
                return prefix+target
            if kind == 'array_borrow':
                return ('a mutable borrow of ' if a['access']=='MutableExclusive' else 'a shared borrow of ')+names.get(args[0],args[0])+'['+expression(args[1],next_seen)+']'
            if kind == 'array_bounds':
                return expression(args[0], next_seen)
            if kind == 'array_move':
                return 'the moved element '+names.get(args[0],args[0])+'['+expression(args[1],next_seen)+']'
            if kind in ('array_extract','array_move_extract'):
                return 'the element at '+expression(args[1],next_seen)+' of temporary '+expression(args[0],next_seen)
            if kind == 'array_read':
                text=names.get(args[0], args[0])+'['+expression(args[1], next_seen)+']'
                for proof in a.get('dimension_bounds_proofs', [])[1:]: text+='['+expression(proof,next_seen)+']'
                return text
            if kind == 'array_construct':
                return '['+', '.join(expression(arg, next_seen) for arg in args)+']'
            if kind == 'struct_construct':
                fields = ', '.join(name+' = '+expression(arg, next_seen) for name, arg in zip(a['fields'], args))
                return value_types.get(ref, 'a struct')+' { '+fields+' }'
            if kind in ('read', 'copy', 'move') and args:
                return names.get(args[0], 'a stored value')
            if kind in ('borrow_shared', 'borrow_mut'):
                return ('a mutable borrow of ' if kind == 'borrow_mut' else 'a shared borrow of ') + names.get(args[0], args[0])
            if kind == 'indexed_field_borrow':
                if a.get('dimension_bounds_proofs') or a.get('field_suffix'):
                    indices=''.join('['+expression(ref,next_seen)+']' for ref in a.get('dimension_bounds_proofs',[args[1]]))
                    suffix='.'+a['field_suffix'] if a.get('field_suffix') else ''
                    target=(names.get(args[0],args[0])+'->'+a['field'] if a.get('field')
                            else '*'+names.get(args[0],args[0]))
                    return ('a mutable borrow of ' if a['access']=='MutableExclusive' else 'a shared borrow of ')+target+indices+suffix
                if not a.get('field'):
                    return ('a mutable borrow of ' if a['access']=='MutableExclusive' else 'a shared borrow of ')+ '*'+names.get(args[0],args[0])+'['+expression(args[1],next_seen)+']'
                return 'a borrow of array field '+a['field']+' at '+expression(args[1],next_seen)+' through '+expression(args[0],next_seen)
            if kind == 'field_borrow':
                return 'field '+a['field']+' through '+expression(args[0], next_seen)
            if kind == 'reborrow':
                return ('a mutable reborrow through ' if a.get('access') == 'MutableExclusive' else 'a shared reborrow through ') + expression(args[0], next_seen)
            if kind == 'deref_read':
                return 'the value accessed through ' + expression(args[0], next_seen)
            if kind in ('binary', 'arithmetic_checked') and len(args) == 2:
                return '(' + expression(args[0], next_seen) + ' ' + a.get('operator', '?') + ' ' + expression(args[1], next_seen) + ')'
            if kind in ('unary', 'unary_checked') and args:
                return a.get('operator', '?') + expression(args[0], next_seen)
            if kind == 'call' and args:
                return names.get(args[0], 'a function') + '(' + ', '.join(expression(x, next_seen) for x in args[1:]) + ')'
            if kind == 'phi':
                return 'the value selected by the preceding branch'
            return 'an intermediate value'

        def explain_op(op):
            a, args, kind = op.get('attributes', {}), op['operands'], op['kind']
            if a.get('reachable') is False:
                return None
            if a.get('validation') == 'invalid':
                return 'An attempted ' + kind.replace('_', ' ') + ' operation failed the compiler’s checks; no successful effect is claimed.'
            # Unknown operation validity must not become an asserted semantic fact.
            if a.get('validation') != 'valid':
                return 'The report records ' + kind.replace('_', ' ') + ', but does not record whether it passed validation.'
            if kind in ('init', 'assign') and len(args) == 2:
                target = names.get(args[0], 'a binding')
                producer = producers.get(args[1], {})
                if producer.get('attributes', {}).get('result_ownership') == 'Unowned' and producer.get('kind') in ('copy','move'):
                    action = 'Copy the shared capability' if producer['kind'] == 'copy' else 'Transfer the capability'
                    return f'{action} from {expression(args[1])} into {target}. Ownership of the referent does not change.'
                if producer.get('kind') == 'copy':
                    return f'Copy {expression(args[1])} into {target}. The source keeps its value.'
                if producer.get('kind') == 'move':
                    return f'Move {expression(args[1])} into {target}. The source no longer holds that value and cannot be read again until it is validly reinitialized.'
                return f'Set {target} to {expression(args[1])}.'
            if kind == 'array_assign':
                value=args[a.get('value_operand',2)]
                proofs=a.get('dimension_bounds_proofs')
                if a.get('projected_field') and proofs:
                    target=names.get(args[0],args[0])+''.join('['+expression(ref)+']' for ref in proofs)+'.'+a['projected_field']
                    return f'Write {expression(value)} to {target} after checking every array dimension.'
                if proofs:
                    target=names.get(args[0],args[0])+''.join('['+expression(ref)+']' for ref in proofs)
                    return f'Write {expression(value)} to {target} after checking every array dimension.'
                return f'Write {expression(value)} to the element of {names.get(args[0], args[0])} selected by checked index {expression(args[1])}.'
            if kind == 'deref_assign':
                return f'Set the value accessed through {expression(args[0])} to {expression(args[1])} using exclusive mutable access.'
            if kind == 'return_prepare':
                if args:
                    return f'Prepare {expression(args[0])} as the return value before running cleanup.'
                return 'Prepare to return without a value, after cleanup.'
            if kind == 'defer_register':
                return 'Schedule a deferred block to run when its enclosing scope is left.'
            if kind == 'defer_execute':
                return 'Run a deferred block now, using the current values of its referenced bindings.'
            if kind == 'call':
                return 'Call ' + (names.get(args[0], 'a function') if args else 'a function') + ' with the evaluated arguments.'
            return None

        params = [names.get(o['operands'][0], 'a parameter') for b in fn['blocks'] for o in b['operations'] if o['kind'] == 'parameter' and o['operands']]
        overview = [f"{fn['name']} takes {', '.join(params)} as input." if params else f"{fn['name']} has no recorded input parameters."]
        allops = [o for b in fn['blocks'] for o in b['operations']]
        if any(b['terminator'].get('attributes', {}).get('branch_refinements') for b in fn['blocks']):
            overview.append('Equality tests can refine a scalar place to a constant on the edge that proves it. Relational integer comparisons can narrow inclusive integer ranges. Bounds checks and candidate selection use these facts along the branch; facts do not leak through a join unless every incoming path supports them.')
        checked = [o for o in allops if o['kind'] in ('arithmetic_checked', 'unary_checked') and o.get('attributes', {}).get('reachable') is not False]
        if checked:
            overview.append('Arithmetic is checked. A failed operation produces no successful result; it cannot silently wrap around and continue as if it succeeded.')
            if any(b['terminator']['kind'] == 'fail' and b['terminator'].get('attributes', {}).get('mechanism') == 'abort' for b in fn['blocks']):
                overview.append('The recorded arithmetic failure path aborts execution. Normal cleanup is not guaranteed on that path.')
        reads = [o for o in allops if o['kind'] in ('read', 'copy', 'move') and o.get('attributes', {}).get('reachable') is not False]
        if reads and all(o.get('attributes', {}).get('validation') == 'valid' for o in reads):
            overview.append('Every recorded reachable read, copy, and move passed initialization checks. Where paths meet, the compiler checks the incoming paths before allowing a value to be used.')
        if any(o['kind'] == 'destroy' for o in allops):
            overview.append('On ordinary scope exit, cleanup releases values that are still initialized and owned. Moved-from bindings are not destroyed as though they still held the transferred value.')
        if any(o.get('attributes', {}).get('struct_arguments') or 'returned_field_states' in o.get('attributes', {})
               or (o['kind']=='parameter' and 'field_states_after' in o.get('attributes', {})) for o in allops):
            overview.append('Structs passed by value give the callee ownership of every field. Ordinary arguments copy the source; explicit moves leave it unavailable. Return values are prepared before deferred cleanup, and moved fields are skipped during local destruction. Call results have initialized fields, but their values are not evaluated at compile time.')
        if any(o.get('attributes', {}).get('bounds_check') for o in allops):
            overview.append('Fixed-size arrays track each element independently. Indices have recorded bounds checks or static proofs. Moving an element leaves the others available; whole-array copies and moves require all elements. Distinct element borrows can coexist, and cleanup skips moved elements.')
        if any(o['kind']=='array_extract' for o in allops):
            overview.append('Temporary array indexing evaluates the source once, checks the index bounds, and copies the selected value and any descendant fields into independent ownership. Cleanup of the temporary follows the copy on the successful path; bounds failure aborts without guaranteed cleanup.')
        if any(o['kind']=='array_move_extract' for o in allops):
            overview.append('Moving from a temporary array transfers the selected element and preserves its identity. For nested indexing, each selected row or element transfers in order; cleanup destroys only unselected values, using conditional destruction when a runtime index has several possible targets.')
        if any(o['kind'] in ('borrow_shared','borrow_mut') and o.get('attributes',{}).get('temporary') for o in allops):
            overview.append('A temporary value borrowed for a call is materialized in owned storage and remains alive through that complete nested call expression. Cleanup follows the outer call; retaining or returning a pointer to that storage is rejected by the lifetime checks.')
        if any(o.get('attributes', {}).get('inner_bounds_proof') for o in allops):
            overview.append('Nested array-field indexing evaluates and checks the outer index, then the inner index, before accessing storage or evaluating an assignment RHS. Candidate scalar targets cover both selections. Known indices narrow the candidates; unknown selections preserve possible old states and do not prove restoration by repeated indexing.')
        if any(o.get('attributes', {}).get('projected_field') for o in allops):
            overview.append('Runtime-index field projection checks the selected descendant path in every possible element. Sibling fields remain independent. Reads and borrows require only the projected targets to be available; moves and replacement update their descendants and ancestor summaries. Unknown-index restoration remains conservative.')
        if any(o.get('attributes', {}).get('element_field_states_before') and not o.get('attributes', {}).get('projected_field') for o in allops):
            overview.append('Runtime struct-array access selects one complete element. Copies create independent descendant values; moves transfer the selected identities and make every possible source field potentially moved. Replacement updates the selected subtree after successful RHS evaluation and preserves possible unselected values. Repeating an unknown index does not prove that a moved element was restored.')
        if any(o['kind']=='array_move' and not o.get('attributes', {}).get('projected_field') for o in allops):
            overview.append('A runtime-index move transfers one selected element and preserves its identity. With an unknown index, each candidate is possibly moved; subsequent reads and whole-array transfers require restoration. Cleanup checks actual initialization and ownership, so it skips the selected moved element while destroying the remaining elements. Repeating an unknown index does not establish that it selects the same element.')
        if any(o['kind']=='array_borrow' and not o.get('attributes', {}).get('projected_field') for o in allops):
            overview.append('A runtime-index borrow refers to one selected element. Its recorded capabilities describe possible element alternatives, not simultaneous borrows chosen at runtime. Permissions and lifetimes conservatively cover every alternative until the last required use. Different unknown indices are not assumed disjoint.')
        if any(o['kind']=='array_bounds' for o in allops):
            overview.append('Runtime array indexing checks both bounds before accessing storage. Bounds failure aborts without a successful value or guaranteed cleanup. Unknown-index reads require every possible element to be available. Unknown-index writes update one element; analysis retains each possible old value and does not assume that every element becomes initialized.')
        if any(o['kind']=='struct_extract' for o in allops):
            overview.append('Field access on a temporary struct evaluates its source once and copies the selected field or substruct. The original temporary is cleaned up after the copy; the selected value remains independently owned.')
        if any(o.get('attributes', {}).get('array_referents') for o in allops):
            overview.append('A whole array field read through a struct pointer makes independent copies of every element. Replacement requires exclusive access to the array and destroys the previous elements only after the complete right-hand side succeeds. If the pointer has alternative referents, analysis preserves each possible unselected array.')
        if any(o.get('attributes', {}).get('struct_referents') and not o.get('attributes', {}).get('array_referents') for o in allops):
            overview.append('Dereferencing a struct pointer copies the whole struct into independent field values. Replacement through a mutable pointer checks the whole referent and replaces its old fields only after the complete right-hand side succeeds. If the pointer has several possible referents, only the selected struct is replaced; analysis retains the other possible values.')
        if any(o['kind']=='deref_move' for o in allops):
            overview.append('Moving through an exclusive managed pointer transfers the referent identity and marks its source moved. A later complete replacement, or assignment to a moved field, restores initialization; shared pointers cannot move values.')
        if any(o['kind'] == 'indexed_field_borrow' for o in allops):
            overview.append('Array-field access through a managed struct pointer checks bounds and derives an element capability from the struct capability. Unknown indices cover every possible element; mutable access requires an exclusive parent. Derived lifetimes remain within the parent and element lifetimes, and last-use analysis releases the alternatives together.')
        if any(o['kind'] == 'field_borrow' for o in allops):
            overview.append('A struct pointer provides access to its scalar fields without transferring ownership. Field projections retain the pointer lifetime and check shared or mutable permissions for the selected field.')
        if fn['capabilities']:
            overview.append('Managed pointers carry access capabilities without owning their referents. Borrow restrictions follow later pointer uses, including deferred uses. Reborrows can temporarily restrict a mutable capability; access resumes after the reborrow ends.')
        if any(len(p.get('field_path', [])) > 1 for p in fn['places']):
            overview.append('Nested structs have separate storage and lifetime paths at every level. Moving a nested field leaves disjoint siblings available but restricts whole-value use of its ancestors until restored. Cleanup visits scalar leaves and then ends the containing struct storage.')
        if any(p.get('field_path') for p in fn['places']):
            overview.append('Struct fields have separate initialization states. Initializing one field does not make the other fields readable. Cleanup applies only to scalar fields that hold initialized, owned values.')
            if any(o['kind']=='move' and o.get('attributes', {}).get('aggregate_place') not in (None, o['operands'][0]) for o in allops):
                overview.append('Moving a field leaves the other fields available. The moved field must be reinitialized before it can be read again or the whole struct can be copied or moved. Cleanup skips fields that remain moved.')
            if fn['capabilities']:
                overview.append('Borrows of distinct scalar fields can coexist. Overlapping mutable access is rejected, and a live field borrow prevents moving or replacing its containing struct.')
        if any(o['kind'] in ('copy','move') and o.get('attributes', {}).get('result_field_states') is not None for o in allops):
            overview.append('A whole-struct copy creates independent field values and leaves the source intact. A whole-struct move transfers every field and leaves the source unavailable until reinitialized. Both require every field on every incoming path.')

        place_types={p['type'] for p in fn['places']}
        if any(t['kind']=='array' and t['id'] in place_types for t in doc['types']) and not any(t['kind']=='struct' and t['id'] in place_types for t in doc['types']):
            overview=[p.replace('Structs','Arrays').replace('struct','array').replace('field','element') for p in overview]
        paths, truncated = [], False

        def walk(bid, steps, conditions, seen):
            nonlocal truncated
            if len(paths) >= 8:
                truncated = True
                return
            if bid in seen or len(seen) >= 128:
                paths.append((conditions, steps + ['Control continues through a repeated or longer path; follow the detailed control-flow links below.']))
                return
            b = blocks.get(bid)
            if b is None:
                paths.append((conditions, steps + ['The next block is not available in this report.']))
                return
            if b['operations'] and all(o.get('attributes', {}).get('reachable') is False for o in b['operations']):
                return
            steps = steps + [text for o in b['operations'] if (text := explain_op(o))]
            term = b['terminator']
            targets = term.get('targets', [])
            attrs = term.get('attributes', {})
            seen = seen | {bid}
            if term['kind'] == 'branch' and attrs.get('checked_value') and len(targets) == 2:
                value_op = producers.get(attrs['checked_value'], {})
                bounds=value_op.get('kind')=='array_bounds'
                if bounds:
                    if value_op.get('attributes', {}).get('validation') == 'invalid':
                        paths.append((conditions, steps + ['Index validation failed; there is no successful array access.']))
                    else:
                        walk(targets[0], steps, conditions + ['index is in bounds'], seen)
                        if value_op.get('attributes', {}).get('runtime_check'):
                            walk(targets[1], steps, conditions + ['index is out of bounds'], seen)
                elif value_op.get('attributes', {}).get('validation') == 'invalid':
                    paths.append((conditions, steps + ['The arithmetic check failed; there is no successful continuation.']))
                else:
                    walk(targets[0], steps, conditions + ['arithmetic succeeds'], seen)
            elif term['kind'] == 'branch' and len(targets) == 2:
                operands = term.get('operands', [])
                condition = expression(operands[0]) if operands else 'the recorded condition'
                const = producers.get(operands[0], {}).get('attributes', {}).get('constant_value') if operands else None
                for i, target in enumerate(targets):
                    if type(const) is bool and const != (i == 0):
                        continue
                    walk(target, steps, conditions + [f'{condition} is {"true" if i == 0 else "false"}'], seen)
            elif term['kind'] == 'jump' and len(targets) == 1:
                walk(targets[0], steps, conditions, seen)
            elif term['kind'] == 'return':
                end = 'Return the prepared value to the caller.' if term.get('operands') else 'Return to the caller without a value.'
                if any('failed the compiler' in step or 'does not record whether' in step for step in steps):
                    end = 'The recorded exit is a return, but this path has errors or unverified operations; a successful return is not established.'
                paths.append((conditions, steps + [end]))
            elif term['kind'] == 'fail':
                paths.append((conditions, steps + ['This path ends in failure, without a successful result.']))
            else:
                paths.append((conditions, steps + ['See the detailed block exit for the remaining control flow.']))

        walk(fn['entry_block'], [], [], frozenset())
        functions.append(dict(name=fn['name'], paragraphs=overview, paths=paths, truncated=truncated))
    return paragraphs, functions

# Implementation inventory and decisions

The handoff is the execution procedure. `Appendix_06(10).html` (publication 1.0.3) remains normative. The formal v3 materials describe semantic judgments; classification and traceability index the source rules; ESIR specification/schema define the external artifact. The supplied files have not been modified.

`inventory.json` records all 13 input files, their hashes, versions, purposes, authority levels, sections or machine-readable structures, and cross-reference integrity. `tools/audit_artifacts.py` regenerates it from the original inputs. `coverage.json` accounts for all 1,230 classified records and 35 formal families.

## Authority and abstraction differences

1. **Historical classification instructions.** `Pasted markdown.md` says not to implement a compiler. The handoff explicitly supplies this as the historical methodology brief. The current user instruction and handoff require implementation; the old task restriction is not a current execution instruction.
2. **Phase order.** The numeric P0–P17 list is not a topological schedule: P7–P10 depend on P11 in the machine-readable contracts. Initialization requires CFG paths under normative Section 36. Construct the typed CFG before dataflow, as the implementation specification's final driver pseudocode does. The inventory includes the derived schedule:
   `P0 → P1 → P2 → P3 → P4 → P5 → P6 → P11 → P7 → P8 → P9 → P10 → P12 → P13 → P14 → P15 → P16 → P17`.
3. **ESIR example versus normative source.** The example's `Int`, `fn()->Int`, and string facts illustrate serialization. They do not introduce an `Int` primitive or waive reference integrity. Generated function types are actual type entities, using the source primitive names.
4. **Formal IR versus ESIR.** The formal specification's older `program` wrapper and dotted operation names are conceptual representations. The supplied ESIR schema governs serialization, including `related_entities` rather than the handoff's recommended `entities` diagnostic field.
5. **Borrow lifetime examples.** Some illustrative borrow-conflict comments appear stricter than normative Sections 44/50 and D.15's last-use rules. Managed scalar borrowing now uses backwards CFG may-use liveness, including deferred uses. It follows the normative liveness requirements rather than copying those comments as unconditional rejection rules.
6. **Unicode.** Appendix B pins Unicode 17.0.0 and expressly forbids substituting a differing host version. The lexer now uses vendored Unicode 17 XID, script-extension, identifier-status, decomposition, combining-class, bidi-class, and confusable tables. Security skeletons are separate from source identity. Visible declarations are checked for confusable conflicts, including ASCII names. See `cobalt/unicode_data/manifest.json` for the pinned upstream hashes.
7. **Arithmetic boundary.** Section 27 permits a documented runtime failure mechanism. The supported integer operations use explicit abort edges. Division/remainder conventions, floating-point model and target-width assumptions have not been imported from Python or C.
8. **Illustrative APIs.** Storage, thread, mutex, and FFI examples do not automatically establish callable builtins. No API is recognized merely by its spelling.

9. **Assignment mutability.** Section 29 says assignment requires a valid mutable destination; several illustrative snippets omit `mut`. This milestone requires mutable bindings for all source assignment statements, including initialization through a later assignment and reinitialization after a move. The general permission to reinitialize does not explicitly waive Section 29. Declaration initializers still permit immutable bindings. Tests and examples make mutability explicit.

## Implemented architecture

| Module | Responsibility |
| --- | --- |
| `cobalt/source.py` | Stable identifiers, source map, diagnostics |
| `cobalt/lexer.py` | Spanned tokens and lexical diagnostics |
| `cobalt/unicode_identifiers.py` | Pinned Unicode 17 identifier classification and security skeletons |
| `cobalt/structs.py` | Scalar-field construction, component initialization and aggregate state summaries |
| `cobalt/borrowing.py` | Managed scalar capabilities, backwards CFG liveness, reborrows and lifetime constraints |
| `cobalt/syntax.py` | AST, precedence parser, normalization boundary |
| `cobalt/semantic.py` | Lexical symbols, scalar typing, places, CFG and cleanup lowering |
| `cobalt/arrays.py` | Runtime array bounds checks, candidate-element access and conditional updates |
| `cobalt/dataflow.py` | CFG joins, initialization/ownership transfer, constant checking, operation annotations |
| `cobalt/artifacts.py` | Versioned rule corpus and cross-reference checks |
| `cobalt/esir.py` | ESIR construction, canonical serialization, schema/reference validation |
| `cobalt/driver.py` | Source-to-ESIR phase orchestration |
| `cobalt/__main__.py` | File CLI and exit statuses |

P4/P5/P6 and CFG lowering share a traversal but maintain distinct symbol, type, place, and value entities. P7/P8 share a state transition pass with independent initialization and ownership meanings. P12 constructs cleanup obligations before dataflow, which validates them in execution order. These are implementation boundaries, not alternate language semantics.

The current CFG admits no loops and is analyzed in topological order. Each reachable predecessor contributes a state; a read requires all contributing states to contain an initialized value. Known constant branch conditions restrict reachable edges. Runtime-checked operations expose failure edges. Deferred blocks expand at each applicable exit using registration-time lexical bindings and execution-time state.

## Dependency map for further implementation

- Resolution establishes declaration identity; type analysis determines scalar compatibility and copy contracts.
- Types and storage paths establish which objects initialization and ownership refer to.
- CFG predecessor states determine initialization and move validity at joins.
- Ownership, paths, CFG liveness and lifetime constraints must precede managed capabilities.
- Initialization, ownership and lifetime facts govern destruction and deferred execution.
- Unsafe modifies permission checks without establishing missing state.
- Concurrency additionally requires access context and explicit synchronization relations.
- FFI requires an explicit target profile plus ownership/lifetime/representation contracts.
- Global validation and ESIR emission consume all applicable established facts.

The audit checks exact rule graph endpoints and the phase DAG. Category edges remain supporting evidence, not automatically executable semantic rules.

## Coverage interpretation

Coverage reports record the tests during which each emitted rule reference was observed. That is exercise evidence, not a claim that every clause of the cited rule was independently asserted. Every exercised rule is marked **partial**; all remaining rules are explicitly marked **not implemented**. Tests include positive and negative cases plus meaningful assertions about ESIR effects and transitions. No full language, library, hosted runtime, ABI or Unicode conformance level is claimed.

## Managed scalar expansion

The next expansion is now implemented as a vertical slice: pinned lexical security data; parsing of `T*`, `mut T*`, `&place`, `&mut place`, `*pointer`, and reborrows; managed scalar places/capabilities; and lifetime constraints. Scalar-only reports retain their existing support profile. Reports using managed pointers identify the `managed-scalar-milestone` profile and include `V_borrow` and `V_lifetime` among the checked invariants.

Backwards CFG liveness tracks pointer bindings and temporary values with assignment kills. Derived capabilities keep their ancestors live. Forward analysis resolves capabilities to scalar referents on incoming paths, checks conflicts, and records capability creation, suspension, resumption, expiration and lifetime containment in operation effects and attributes. Deferred bodies participate at their actual cleanup points. Pointer copies create shared capabilities; mutable pointer transfers consume the source binding without transferring referent ownership. Pointer cleanup never destroys the referent.

Managed parameters refer to explicit caller-owned places, distinct from parameter bindings. Calls retain argument capabilities through the call and conservatively forget constants of mutably accessible referents. Callees are analyzed before callers; returned-borrow summaries include every contributing input parameter. A caller retains all possible input lifetime constraints. Returning an ordinary local borrow is invalid. Recursive borrow-return relationships require a fixed-point summary analysis and currently produce `unsupported_borrow_return`, rather than relying on an incomplete summary.

Top-level capability status describes creation, just as top-level place state describes declaration. `capability_state_before` and `capability_state_after` record path-dependent state; `ended_capabilities` records last-use expiration. No one final capability state is claimed for all branches. Liveness and return summaries are conservative: infeasible future branches or unselected argument-return alternatives may retain a borrow longer than necessary.

In this slice, `mut T* pointer` denotes exclusive referent access and an immutable pointer binding. Independent pointer-binding mutability/rebinding, nested or nullable pointers, moves out of managed dereferences, whole-array pointers, slices, and collection invalidation are not implemented. This does not complete every P6/P9/P10 rule.

The Unicode generator is `python3 tools/generate_unicode.py DIRECTORY`, where DIRECTORY contains the eight official Unicode 17 inputs named in the manifest. Regeneration verifies their SHA-256 hashes. Compiler use is offline and requires no host Unicode library. The security implementation follows UTS #39 revision 32, including LTR bidi skeletons for profile-allowed identifier characters; normalization is used for security profile membership and skeleton comparisons only. The NFC/NFD implementation was also checked against all 20,034 vectors in the official Unicode 17 `NormalizationTest.txt`. Full-language conformance remains unclaimed.

## Scalar-field struct slice

The bounded aggregate milestone now supports nominal struct declarations containing fixed-width integer, `bool`, and `char` fields; exporting struct names; local struct bindings; named construction; field reads/writes; and whole-struct copies, moves, and replacement. Construction uses Section 21's `Type { field = expression, ... }` form. Every declared field must occur exactly once; unknown, duplicate, missing and incompatible field initializers are diagnosed. Initializers evaluate in source order, and destination updates occur only after the complete constructor succeeds. Equal field layouts do not make two nominal struct types interchangeable.

Every local struct has a root place and distinct child places with `parent` and `field_path` links. Each child has a lifetime contained in the root's lifetime. Field cells drive definite initialization over the existing acyclic CFG. The root's `PartiallyInitialized` state is a summary and never grants permission to read an uninitialized child. Operations expose `field_states_before/after` and `aggregate_state_before/after`, and HTML explanations show field names and initialization transitions.

This slice has no aggregate destruction hooks or resource-owning fields. Cleanup emits individually guarded scalar-field destruction operations and then ends aggregate storage, without additionally destroying the root as an independent scalar value. Field cleanup is listed in reverse declaration order as an implementation traversal; scalar fields have no observable destruction hooks in this slice. Deferred field references bind to their field places at registration and read execution-time values.

Reports containing struct declarations use `scalar-field-struct-milestone`. This is a bounded extension, not completion of general aggregate ownership: recursive struct definitions or managed-pointer fields, aggregate constants, associated functions and destruction hooks are explicitly unsupported. Supported field declarations are still recorded as nominal types and owned scalar components; no native layout or ABI is inferred.

Validation includes positive/negative constructor checks, nominal typing, contextual scalar types and range errors, mutation, partial initialization, branch joins, invalid-initializer rollback, replacement evaluation order, deferred field uses, cleanup guards, deterministic ESIR, and HTML explanations. `examples/structs.cb` and `examples/invalid_struct_initialization.cb` provide checked-in ESIR examples; the former also has a standalone source-inclusive HTML report.

### Whole-struct ownership transfers

Local by-value initialization and assignment now copy scalar-field structs implicitly; `move source` transfers the whole value explicitly. Every field must be initialized on every incoming CFG path before a whole-value read/copy/move can succeed. A rejected transfer leaves all source fields unchanged. Copies receive independent root and field object identities; moves preserve their identities and mark the root and every child as `Moved`. Reinitialization through a whole-value assignment or individual scalar-field assignments restores availability when all fields are initialized again.

ESIR copy/move operations include `result_field_states` and per-field ownership effects. Field constants travel with the value snapshot, so destination writes do not change a copied source. Replacement evaluates the complete RHS before destroying old destination fields, including self-copy and self-move assignments. Cleanup skips moved source fields and destroys destination fields or discarded temporary fields as applicable. Empty structs retain explicit root initialization/move state despite having no components. Deferred whole-value uses participate in the same initialization checks at execution time.

Tests cover independent field identities, preserved move identities, use-after-move through both root and fields, branch joins, partial initialization rejection, reinitialization, replacement, self-assignment, deferred uses, empty structs, nominal typing, discarded temporaries, and deterministic output. `examples/struct_transfers.cb` includes a source-inclusive HTML report; `examples/invalid_struct_move.cb` demonstrates rejection.

### Partial field moves and field borrowing

Explicit `move point.x` transfers that field's value identity and leaves siblings available. A partially moved root reports `PartiallyInitialized` initialization and `PartiallyMoved` ownership. Whole-value copies and moves require every field to be available on every incoming path. Ordinary mutable field assignment restores a moved field, and restoring all fields restores whole-value availability. Cleanup skips moved fields and still destroys initialized siblings.

Shared `&point.x` and mutable `&mut point.x` borrows use the scalar capability and last-use analysis. Distinct sibling fields and fields of different local structs are disjoint; a root overlaps all its fields. Live field capabilities therefore prevent conflicting whole-struct moves or replacement as well as conflicting accesses to the same field. Reborrows, calls, input-derived returned pointers and deferred pointer uses retain these relationships. Capability lifetimes are contained in field lifetimes, which are contained in aggregate storage lifetimes. Rejected accesses are stopped before ownership transfers or destination updates execute.

ESIR records overlap comparisons, disjointness facts, partial ownership transitions and field reinitialization. HTML includes the overlap evidence and explains partial moves and field borrowing. Tests cover shared aliases, exclusive conflicts, sibling access, whole-value conflicts, branch joins, reinitialization, last-use release, reborrows, calls, returned pointers, deferred uses and guarded cleanup. `examples/partial_fields.cb` has a source-inclusive HTML report; `invalid_partial_move.cb` and `invalid_field_borrow.cb` demonstrate rejection.

### Whole-struct managed pointers

`Point*` and `mut Point*` now borrow initialized scalar-field structs and can be passed to functions. Section 25's `pointer->field` syntax lowers identically to `(*pointer).field`. Reads, writes and explicit shared/mutable field reborrows project from the incoming capability to the selected child place. Mutable access requires an exclusive capability. Loading a struct pointer for projection does not itself access every field; the projection checks the selected storage against other live capabilities. This permits disjoint field borrows through a common mutable struct pointer while rejecting same-field conflicts. Assignment evaluates its pointer and RHS before establishing the temporary write capability, so `pointer->x = pointer->x + 1` is supported.

Borrowed parameters have caller-owned root and child places with contained lifetimes and no local destruction obligations. A mutable call conservatively forgets constants for every accessible field. Returned-borrow summaries track both input parameter indices and field paths, preserving the correct referent through calls and wrappers. Returning local storage remains invalid. Derived capabilities retain ancestor lifetime constraints; conservative root capabilities may continue restricting direct local access while a returned field pointer remains live.

ESIR records `field_borrow` operations, projected places, overlap checks and containment in both the source capability and field lifetime. HTML explains struct pointer field access. Tests cover both syntaxes, permissions, disjoint and overlapping reborrows, RHS evaluation, parameters, caller constant invalidation, returned roots and fields, branch alternatives, deferred uses, local lifetime rejection and deterministic reports. `examples/struct_pointers.cb` includes a source-inclusive report; `invalid_struct_pointer.cb` demonstrates a shared-write rejection.

Moves out of managed dereferences were unsupported at this earlier struct milestone; later sections add scalar, aggregate, and array moves through exclusive managed pointers. Recursive struct definitions and broader destruction contracts remain separate work. Loops separately require converging dataflow and loop-exit cleanup. Imports, aliases and the rest of the parser remain incremental work.


### By-value struct parameters and returns

Functions now accept and return nominal scalar-field structs by value. Ordinary argument/return expressions copy a local struct; explicit `move` transfers its value and leaves its fields unavailable. Constructors and struct-returning calls can supply owned values directly. All required fields must be initialized on every incoming path. Nominal type compatibility, argument order, partial moves, live borrows, missing returns and deferred uses follow the existing checks.

Each owned struct parameter starts with initialized root and child places. Its field cleanup obligations are local to the callee; moved fields are skipped. Call operations record `struct_arguments`, including argument value snapshots, parameter places and per-field ownership transfer effects. `return_prepare` records `returned_field_states` before deferred cleanup. Returning a copy leaves the local value for cleanup; returning a move leaves no destruction obligation for its moved fields. Returned temporary structs are destroyed field by field when discarded, or transferred into local bindings or onward calls.

Function bodies are analyzed once against their declared interfaces. Parameter and call-result identities are symbolic instances; argument/return effects connect ownership across the call boundary without claiming an additional copy. Calls return fully initialized owned fields with unknown constants, even for a constructor-returning function. This is interface-based analysis, not interprocedural constant evaluation or an ABI/layout implementation. Recursive by-value calls can use the declared interface without returned-borrow inference. Returned pointers to owned parameters remain invalid because those parameters are callee-local storage.

Validation covers copies and explicit moves, field identities and cleanup guards, constructed arguments, left-to-right evaluation, copy/move returns, deferred cleanup ordering, partial-move rejection, nominal mismatches, branch returns, recursion, empty structs, discarded results, replacement, forwarding, and mixed owned/borrowed arguments. HTML explains by-value ownership and shows the callee parameter/field mapping. `examples/struct_calls.cb` includes a source-inclusive report; `invalid_struct_argument.cb` demonstrates rejection.

Field reads on a returned temporary are supported; borrowing, assigning, or explicitly moving its fields still requires a local binding. Resource-owning structs and custom destruction remain outside this slice.


### Whole-value operations through struct pointers

Dereferencing a shared or mutable struct pointer now produces an owned copy of the whole scalar-field struct. Root and field identities are independent of the source; known field constants are retained when all possible referents agree. The resulting value can initialize a local, become a by-value argument or return value, or be discarded with per-field cleanup.

Assignment through a mutable struct pointer replaces the selected referent after complete RHS evaluation and permission checks. It transfers the RHS root and field identities and records destruction of the previous fields. Self-replacement (`*pointer = *pointer`) copies first. Invalid RHS values, shared-write attempts and overlapping live field borrows leave the destination unchanged. Pointer capabilities continue to refer to the same storage after replacement; moving a value out of a managed dereference remains unsupported.

When returned-borrow analysis gives a pointer multiple possible roots, a replacement affects only the selected root. The analysis conservatively retains old and new identities for each possible target, and retains constants only when both alternatives agree. These are alternative targets, not writes to every target. ESIR exposes `struct_referents`, `referent_states_before/after`, `target_selection`, copied result fields and conditional per-field replacement effects. HTML explains whole-value copying and replacement.

Tests cover independent copies, self-replacement, moves into the destination, failed-RHS rollback, shared and overlapping-borrow rejection, function parameters/arguments/returns, discarded copies, alternative referents, defers, empty structs and deterministic reports. `examples/struct_dereferences.cb` has a source-inclusive report; `invalid_struct_replacement.cb` demonstrates a conflict. Nested component paths are covered by the following expansion.


### Nested structs with scalar leaves

Struct fields may now contain other acyclic structs whose leaves are supported scalars. Definitions may reference a later struct declaration. A traversal detects direct and indirect by-value cycles before allocating component paths and diagnoses `unsupported_recursive_struct`. Managed-pointer fields and custom destruction remain unsupported.

Each nested struct and scalar leaf has its own place and lifetime, an immediate `parent` link and a full `field_path`. Component state/value snapshots use dotted paths such as `start.x`; constructors, copies, moves, by-value calls and returns carry all descendant fields. Aggregate summaries refresh from children toward ancestors. Moving a leaf or substruct restricts whole-value access to ancestors, while disjoint siblings remain available. Field or substruct assignment restores availability when every required descendant is initialized. Ancestor state transitions are included in ESIR.

Direct and pointer-based paths support nested reads, writes, shared/mutable borrows, and whole substruct copies or replacement. Overlap follows ancestry; disjoint branches remain independent. Borrowed parameters synthesize complete caller-owned component trees, returned-borrow summaries preserve full paths, and mutable calls invalidate constants throughout the accessible subtree. Whole-value pointer operations retain their conditional-target semantics.

Cleanup recursively visits children in reverse declaration order, destroying initialized owned scalar leaves and ending intermediate aggregate storage without extra scalar destruction. Deferred captures include descendant places. Tests cover three-level nesting, empty nested structs, forward declarations and cycle rejection, partial initialization and moves, ancestor restoration, nested copying and replacement, disjoint/overlapping borrows, pointer projection, by-value signatures, returned field pointers, deferred paths, and deterministic reports. `examples/nested_structs.cb` has a source-inclusive report; `invalid_nested_move.cb` demonstrates rejection.

Arrays of aggregates, pointer/resource-owning fields, custom destruction, and recursive type definitions remain future work. Loops remain a separate expansion requiring converging dataflow and loop-exit cleanup.


### Field reads from aggregate temporaries

Constructed and returned structs now support direct field reads, including nested paths such as `make().point.x` and substruct results such as `make().point`. The source expression evaluates once. A `struct_extract` operation makes an independent copy of the selected scalar or substruct, retaining known constructor constants and rebasing descendant paths for substruct results. Function results still have unknown constants.

The source temporary is discarded after extraction, with cleanup of its original scalar leaves. The copied selection is independently owned and can be stored, passed, returned or discarded. Flattening the complete selected path avoids creating unnecessary intermediate substruct copies. This cleanup placement is scoped to the current structs with scalar leaves and no custom destruction hooks.

Borrowing, assignment and explicit moves targeting temporary fields produce `unsupported_temporary_place`; users can bind the struct to a local to use the existing place and lifetime rules. Tests cover constructor and call sources, nested and empty substructs, single source evaluation, cleanup, by-value use, deferred evaluation, invalid sources/paths, and deterministic HTML. `examples/temporary_fields.cb` includes a source-inclusive report.


### Fixed-size scalar arrays

Section 23's `T[N]` types and `[element, ...]` initializers are now supported for fixed-width integers, `bool`, and `char`. Length is part of type identity and must be a nonnegative integer literal. This explicit per-element milestone supports lengths 0–256; larger lengths are diagnosed as unsupported to bound the size of state snapshots. Initializer counts and element types must match the expected array type. Array literals require an expected type from a declaration, assignment, parameter or return context.

Local and parameter arrays support literal indices, including rejection of negative and out-of-range indices. Accepted accesses record `array_index`, `array_length`, and `bounds_check=proven_in_bounds`, with bounds rule references. Runtime reads, writes, borrows and moves are covered by the following expansions. Arrays of aggregates, whole-array pointers/borrows and slices remain outside this phase.

Arrays use the existing aggregate component analysis: each `[index]` has independent storage, initialization, ownership and lifetime state. Whole-array copies/moves require every element; moving one element leaves siblings available and ordinary mutable assignment restores it. Cleanup is guarded per element. Literal indices establish disjointness for independent element borrows, while whole-array replacement and moves overlap all elements. By-value parameters and returns transfer complete element snapshots. ESIR array types use `kind=array`, their canonical `T[N]` name, the element type argument and indexed components; reports identify `scalar-array-milestone` and show bounds evidence.

Validation covers lengths, scalar element types/ranges, bounds, partial initialization, mutability, branches, copies/moves, cleanup, disjoint and overlapping borrows, deferred uses, by-value signatures, zero-length arrays, evaluation order, invalid replacement rollback and deterministic reports. `examples/arrays.cb` includes source and explanations; `invalid_array_index.cb` demonstrates bounds rejection. Runtime indexing is implemented in the following expansion.


### Runtime array reads and writes

Local and parameter scalar arrays now support fixed-width signed or unsigned integer index expressions. The index evaluates once. An `array_bounds` operation establishes `0 <= index < length` on its success path before an `array_read` or `array_assign` accesses storage. Bounds failure uses the documented abort profile: no successful result or guaranteed cleanup. Provably invalid indices, including every index into a zero-length array, produce a diagnostic and have no reachable successful access. Known valid indices select only their corresponding element.

Unknown-index reads require every possible element to be initialized and available. They preserve a constant only when all candidates agree. Unknown-index writes update one selected element; analysis retains each candidate's possible old state, identity and value. They therefore do not establish that every element is initialized. A single-element array has a definite target on the successful bounds path. Writes check mutability, RHS validity and conflicts against all possible live element borrows before updating state. The index and its bounds check precede RHS evaluation.

ESIR records bounds success/failure edges, candidate elements, target selection, before/after element states and conditional replacement effects. HTML distinguishes bounds failure from arithmetic failure and shows both bounds outcomes when the index is unknown. Tests cover signed/unsigned indices, known and unknown targets, initialization and move checks, conditional updates, single-element narrowing, borrow conflicts, invalid RHS rollback, evaluation order, deferred use, reinitialization and deterministic reports. `examples/runtime_arrays.cb` includes source and explanations; `invalid_runtime_index.cb` demonstrates rejection.

Runtime-index borrowing and moves are covered by the following expansions. At this stage, repeated unknown-index expressions are not assumed to select the same element. Arrays of aggregates, slices and whole-array pointers remain future work.


### Runtime-index element borrowing

`&values[index]` and `&mut values[index]` now use the existing checked-index success path to create shared or exclusive scalar pointers. The index evaluates once. Known indices select one element; unknown indices conservatively cover all in-bounds elements. Every possible referent must be initialized and available, and mutable borrowing requires a mutable array. All permission checks precede capability creation, so a rejected borrow creates no capabilities.

An `array_borrow` operation records `possible_elements`, the bounds proof, and `capability_alternatives`. These describe a single runtime selection: they are analysis alternatives, not simultaneous runtime pointers. Each capability is contained in its element's lifetime. Overlap checks conservatively cover the entire alternative set; unrelated unknown indices are never assumed disjoint. Known distinct indices and elements of different arrays can establish disjointness.

Shared aliases, mutable transfers, reborrows, calls and input-derived returned pointers preserve the candidate referents and their lifetime constraints. Last-use analysis releases every alternative. Reborrow suspension and resumption apply to the corresponding parent capabilities. An unknown-target mutable dereference or call retains conservative element values. Returning a borrow of a local array or an owned by-value array parameter remains invalid. Whole-array pointers are still unsupported; returned pointers in this slice flow through ordinary scalar-pointer parameters.

Tests cover candidate lifetimes, known and unknown indices, single-element arrays, mutability, initialization/move rejection, bounds failures, overlapping access and whole-array conflicts, last-use release, aliases/transfers, reborrows, calls/returns, deferred uses, index snapshots, branches and deterministic HTML. `examples/runtime_array_borrows.cb` has a source-inclusive report; `invalid_runtime_borrow.cb` demonstrates possible overlap.


### Runtime-index element moves

`move values[index]` evaluates its index once and uses the checked bounds success path. Every candidate must be initialized and available, with no conflicting live shared or mutable borrow. A known index or a single-element array consumes one definite element. An unknown index transfers one selected element while conservatively marking every candidate as possibly moved. The result preserves the selected source identity; its recorded identities are alternatives, not multiple owned objects.

ESIR records `array_move`, the bounds proof, candidate states, identity selection and conditional transfer effects. Guarded cleanup destroys only elements that remain initialized and owned. Subsequent element reads, borrows and whole-array transfers require definite availability. Whole-array replacement or restoring every candidate individually restores availability. Repeating an unknown index for assignment does not prove restoration: the analysis does not track correlations between index expressions.

Tests cover known and unknown indices, equal constants, single-element arrays, bounds failures, partial initialization, borrow conflicts and rollback, restoration, repeated moves, branch joins, deferred use, argument evaluation, identity preservation and conditional cleanup. `examples/runtime_array_moves.cb` includes a source-inclusive report; `invalid_runtime_move.cb` demonstrates rejection of a possibly moved element.


### Element reads from temporary scalar arrays

Returned array values now support `make_values()[index]` with literal or runtime integer indices. The array source evaluates once, followed by the index, consistent with the normative left-to-right operand order. Bounds checks use the existing success/abort profile. An `array_extract` copies the selected scalar into a new independently owned identity and records the bounds proof and possible element paths. Source-temporary cleanup follows extraction on the success path; abort does not guarantee cleanup.

Known indices select one element; unknown indices cover all elements, retaining a constant only when all candidates agree. Callee bodies are still not evaluated at call sites. Results can be stored, returned, passed or discarded, and deferred reads evaluate at cleanup time. Borrowing, assigning or moving a temporary element remains unsupported; bind the array first. Array literals still require an expected type and are not inferred from indexing context.

Tests cover bounds rejection, single-element narrowing, invalid source/index types, single evaluation, independent identity, cleanup ordering, deferred evaluation, temporary-place rejection and deterministic reports. `examples/temporary_arrays.cb` includes the source and explanation.


### Fixed-size scalar arrays within structs

Struct fields now accept supported `T[N]` scalar arrays, including empty arrays and the existing 256-element limit. Named constructors provide the expected array type for list initializers. Nested structs retain array component paths, by-value parameter/return snapshots, independent copies and whole-value replacement.

Local and parameter struct bindings support literal and runtime indexing of array fields, including nested paths such as `outer.data.values[index]`. Reads, writes, moves and element borrows reuse checked array operations. Moving an element makes the array and containing structs partially moved; restoring the array field or every affected element restores ancestor availability. Sibling fields remain independent. Borrow overlap includes the containing array and every ancestor struct. Runtime writes still cannot establish initialization of all possible targets.

Cleanup descends through struct and array components and destroys owned initialized scalar leaves once. Deferred uses and CFG joins retain per-element state. Whole containing-struct pointers support the existing whole-value operations, with array projection through pointers covered by the following expansions. Whole-array pointers, arrays of aggregates and multidimensional arrays remain outside this expansion.

Tests cover construction, bounds-aware access, partial initialization, literal/runtime moves, ancestor restoration, mutability, disjoint/overlapping borrows, nested by-value transfers, array-field transfers, empty fields, cleanup, defers, joins, containing-struct pointers, invalid types/lengths and deterministic reports. `examples/array_fields.cb` includes the source and explanation.


### Array-field elements through managed struct pointers

`pointer->values[index]` and `(*pointer).values[index]` support scalar reads, writes and shared/mutable element borrows, including nested struct field paths. The pointer and index evaluate once in operand order; bounds checking precedes access and assignment RHS evaluation. Assignment derives its exclusive element capability after RHS evaluation and uses managed dereference updates.

`indexed_field_borrow` records the field path, checked index, candidate places and alternative capabilities derived from possible parent struct capabilities. Known indices select one element per parent; unknown indices cover every element. Permission checks cover candidate overlap before capabilities are created. Shared parents cannot authorize mutable access. Element lifetimes remain within parent capability and element storage lifetimes. Alias, reborrow, call and returned-pointer analysis preserve candidate paths and last-use constraints. Moves through managed pointers remain unsupported.

Tests cover permissions, bounds, disjointness/overlap, deferred uses, returned pointers, local escape rejection, nested fields, conditional writes, single evaluation, failed projection rollback and deterministic alternatives. `examples/pointer_array_fields.cb` includes source and explanation.

### Multidimensional array fields through managed struct pointers

Managed struct pointers now support checked indexing through every dimension of an array field, for example `pointer->grid[row][column]`. This applies to scalar arrays and acyclic struct arrays, including nested field paths. Each index evaluates once and is bounds checked in source order before access or later index evaluation. Runtime candidate selection forms the possible nested element paths from the per-dimension index facts.

Reads and replacement use the existing managed dereference permissions. Shared pointer capabilities permit reads only; writes and mutable borrows require exclusive access. Element and field borrows retain candidate places, bounds proofs, and the parent struct capability, so distinct cells remain independently borrowable and overlapping possible selections conflict. Struct fields can be projected directly after the indices, such as `pointer->points[row][column].x`. By-value row copies work through the resulting row capability. Moving an element out through a managed pointer remains unsupported, as do explicit whole-array borrows and pointers.

Tests cover mixed known/runtime dimensions, nested struct fields, scalar and struct leaves, direct field projections, disjoint/overlapping borrows, shared-parent rejection, per-dimension bounds, evaluation order, returned element borrows, row copies, and deterministic explanations. `examples/pointer_multidimensional_arrays.cb` includes source and explanation.

### Whole-array field copies and replacement through struct pointers

`i32[2] values = pointer->values` copies every scalar element into independent owned values. `pointer->values = [7,8]` replaces the complete array through an exclusive struct capability. Nested field paths and empty arrays use the same aggregate transfer machinery. The array field is projected internally for the value operation; explicit source-level whole-array pointers and borrows remain unsupported.

Replacement evaluates the entire RHS before deriving exclusive array access and destroying old elements. Shared parents and overlapping live element borrows reject replacement; disjoint sibling fields remain accessible. Failed RHS or permission checks leave the destination unchanged. Self-copy replacement is permitted. If the parent pointer has several possible referents, each array retains its possible old state and identities. By-value calls, returns and deferred operations preserve these rules.

ESIR retains aggregate dereference evidence and adds `array_referents` so explanations identify whole-array copies and replacements. Tests assert independent identities, replacement effects, rollback, shared permissions, element overlap, nested/empty arrays, calls/returns, alternative referents and deterministic reports. `examples/pointer_array_values.cb` includes source and explanation.


### Explicit whole-array borrows

Fixed-size arrays and array fields can now be borrowed as complete places, using pointer types such as `i32[2]*` and `mut i32[2]*`. A shared whole-array borrow permits complete-array reads and copies; an exclusive borrow permits replacement of the complete array. The same rules apply to local arrays, local struct fields, and array fields reached through managed struct pointers.

Whole-array capabilities use the existing place ancestry, so they overlap every element and nested row. A live shared borrow blocks replacement and mutable borrows; a live exclusive borrow blocks conflicting element reads, writes and borrows. Disjoint sibling struct fields remain accessible. Borrowing requires a fully initialized, available array; moved or partially moved arrays are rejected. Whole-array borrows follow existing last-use, reborrow, call/return and lifetime checks. Moves out through managed pointers and slices remain unsupported.

ESIR records whole-array borrowing as an ordinary place borrow or `field_borrow`, retaining the full array type and access mode. Dereference reads and replacements preserve complete descendant snapshots and ownership effects. Tests cover scalar arrays, nested arrays, local and pointer-projected fields, permission conflicts, sibling disjointness, moved-state rejection, returned-borrow lifetimes and deterministic reports. `examples/whole_array_borrows.cb` includes source and explanation.


### Arrays of structs with literal indices

Local and parameter arrays now accept acyclic struct element types, retaining the existing 0–256 element limit. Struct elements may contain supported nested structs and scalar arrays. At this stage of the expansion, array-of-struct fields within other structs and multidimensional arrays were unsupported; later sections record their additions. Struct-array reports identify `struct-array-milestone`; this remains a partial implementation, not a conformance claim.

List construction transfers the complete element field snapshots. Literal indexing selects an element place with its own descendant fields and lifetime. `points[0].x`, whole-element copies/replacement, explicit element or field moves, and shared/mutable element and field borrows use the existing aggregate place analysis. Moving a descendant restricts its element and array ancestors, while sibling fields and elements remain usable. Restoring every missing field or replacing the affected element restores whole-value availability.

Whole-array copies/moves and by-value parameters/returns preserve descendant state and ownership. Copies create independent values; moves retain identities. Cleanup descends to initialized owned scalar leaves, skipping moved leaves and ending intermediate aggregate storage without additional destruction. Borrow overlap follows element/field ancestry; pointers to literal-selected struct elements support the existing projection and returned-field-pointer rules.

Runtime whole-element indexing is covered by the following expansion. Temporary struct-array reads are covered by a later expansion. Tests cover construction, nested fields, identities, partial initialization and moves, restoration, borrow overlap, calls/returns, lifetimes, cleanup, defers, CFG joins, empty arrays/elements, bounds, unsupported boundaries and deterministic reports. `examples/struct_arrays.cb` includes source and explanation.


### Runtime whole-element access for arrays of structs

Struct arrays now support checked runtime whole-element copies, replacement, moves and shared/mutable borrows. Indices evaluate once and use the existing bounds success/abort profile. Known indices narrow to one element; unknown indices select among immediate elements, not flattened descendant paths. Reads, moves and borrows require every possible element and descendant to be initialized and available. Replacement checks mutability, RHS validity and all candidate borrow conflicts before changing state.

Copies construct independent identities for the selected struct and all descendant fields, retaining constants only where all alternatives agree. Moves preserve selected identity alternatives and mark every possible source descendant as moved or possibly moved. Replacement updates one selected subtree, destroying only previously initialized owned scalar leaves; unknown targets retain possible old field states and identities. Empty elements and nested structs/scalar-array fields follow the same rules. ESIR records candidate roots and per-candidate descendant snapshots before and after access.

Struct-element borrows reuse candidate capabilities with existing field projection, alias/reborrow, call and returned-pointer lifetime checks. By-value calls and returns receive complete field snapshots. Cleanup skips the actual moved leaves and remains guarded for possible moves. Whole-array replacement or restoration of every candidate recovers availability; repeated unknown-index assignment does not prove restoration.

Direct field projection such as `points[index].x` is covered by the following expansion. Temporary struct-array reads are covered below; struct-array fields and multidimensional arrays remain outside this phase. Tests cover copies and identity alternatives, known/unknown targets, moves, replacement, partial initialization, overlap, rollback, nested/empty elements, bounds, calls/returns, lifetime escape, deferred use, CFG joins, evaluation count and deterministic reports. `examples/runtime_struct_arrays.cb` includes source and explanation.


### Direct fields of runtime-selected struct elements

`points[index].x` and nested member paths now support reads, replacement, explicit moves, and shared/mutable borrowing. The index evaluates once with the existing checked bounds success path. ESIR array operations record `projected_field` and narrow each candidate element to that descendant place before checking permissions or state. Partial initialization or moves of unrelated siblings do not prevent access to an available selected field.

Scalar, substruct and whole scalar-array field values reuse their existing copy/transfer rules. Unknown selections update only possible target descendants; sibling paths remain independent. Moves invalidate containing aggregate availability, and restoration refreshes ancestor summaries and identities. Borrows cover candidate field paths, with normal last-use, call/return, and lifetime checks. Explicit whole-array field borrowing remains unsupported.

Indexing within a scalar-array field of a runtime-selected element is covered by the following expansion. Temporary struct-array reads are covered below; arrays-of-struct fields remain unsupported. Tests cover partial initialization, identities and restoration, sibling access after moves, substruct and array-field operations, mutability, bounds, borrow overlap, rollback, guarded cleanup, returned-pointer lifetimes, deferred uses, single evaluation and deterministic explanations. `examples/runtime_array_fields.cb` includes source and explanation.


### Nested indexing through runtime-selected struct elements

`data[index].values[item]` and nested member paths such as `data[index].inner.values[item]` now support scalar reads, writes, moves and shared/mutable borrows. The outer index evaluates and passes its bounds check before the inner index evaluates; the inner bounds check precedes assignment RHS evaluation. Both checked indices are operation operands, with the second also recorded as `inner_bounds_proof`.

Candidate places are the scalar elements selected by both indices. Known indices narrow their respective dimension; unknown indices cover the possible combinations. Permission and initialization checks apply only to these scalar targets. Known distinct inner indices remain disjoint even with an unknown outer index. Moves and conditional replacement update target states and containing aggregate summaries. Repeated unknown selections do not prove restoration. Cleanup retains initialized-and-owned guards for possibly moved targets.

This supports scalar-array fields within existing struct arrays, not general multidimensional array types. Temporary struct-array reads are covered by the following expansion; array-of-struct fields remain unsupported. Tests cover narrowing, partial initialization, sibling availability, moves/restoration, conflicts, bounds including empty inner arrays, evaluation order, rollback, returned-borrow lifetimes, defers, nested paths and deterministic reports. `examples/nested_runtime_indices.cb` includes source and explanation.


### Reads from temporary arrays of structs

`make_points()[index]` now copies a selected struct from a temporary array using the existing bounds success/abort profile. The source and index evaluate once, in order. Known indices select one element; unknown indices select among immediate element paths, excluding flattened descendants. The copied result has independent identities for the struct and every descendant field, with constants retained only when candidate fields agree.

Source-array cleanup follows extraction and visits its owned scalar leaves once. Subsequent field reads such as `make_points()[index].x` reuse temporary struct extraction and cleanup of the selected copy. Empty struct elements and nested substructs are supported. By-value arguments and returns receive complete selected field snapshots. Explicitly moving an owned local array into the temporary expression preserves the normal moved-source restriction.

Bounds failure has no successful copy or guaranteed cleanup. Borrowing, assigning or moving a temporary element or field remains unsupported; bind the array first. Array-of-struct fields are covered by the following expansion; multidimensional array types remain future work. Tests cover candidate selection, identities, cleanup ordering, constants, bounds failures, empty arrays/elements, nested fields, single evaluation, calls/returns, defers, rejected temporary-place operations and deterministic reports. `examples/temporary_struct_arrays.cb` includes source and explanation.


### Arrays of structs as struct fields

Struct fields now accept fixed-size arrays of supported acyclic structs, including forward-declared element types. Nested struct and array storage paths retain the existing construction, copies/moves, partial initialization, runtime projection, borrow overlap and cleanup rules. Containing structs support by-value calls and returns. Managed containing-struct pointers support whole-array copies/replacement and checked struct-element copies/replacement/borrows through their array fields.

Nested runtime selections such as `scenes[index].points[item]` select aggregate subtrees and preserve complete descendant snapshots. Effects record both checked indices. Moving a selected subtree restricts containing arrays and structs while leaving disjoint siblings accessible. Restoring every candidate or replacing the containing array restores availability. Cleanup destroys initialized owned scalar leaves without extra destruction of intermediate aggregates.

Cycle detection follows array element type dependencies before allocating storage paths, including zero-length arrays. Direct and indirect recursive by-value definitions are explicitly unsupported, with diagnostics attached to the declaring struct. Multidimensional array types remain unsupported; arrays-of-struct fields do not introduce them.

Tests cover forward declarations, partial state/restoration, runtime projections, borrows, whole-array and element access through pointers, nested aggregate selections, by-value transfer, returned-borrow lifetimes, cleanup, defers, cycle rejection, empty fields, bounds and deterministic reports. `examples/struct_array_fields.cb` includes source and explanation.


### Fixed-size multidimensional scalar arrays with literal indices

Type syntax accepts multiple fixed dimensions, for example `i32[2][3]`, interpreted as two rows of three `i32` elements. Each dimension is part of the type identity, each dimension is at most 256, and a multidimensional value contains at most 256 scalar cells to bound component snapshots. Nested array literals require the matching expected type at every dimension; shape mismatches and scalar element type errors are diagnosed.

Each row and scalar cell has independent storage, initialization, ownership and lifetime state in the existing aggregate tree. Literal indices at each level establish static bounds proofs. Reads and writes affect only the selected row/cell; moves, borrows, reinitialization, copying and cleanup follow existing array and place rules. Disjoint rows and cells can be borrowed independently. Whole nested-array copies/moves and by-value parameters/returns carry all descendant states. Struct fields may contain nested scalar arrays, including within arrays of structs.

ESIR retains nested `array` types, with each outer dimension's element type referring to the next inner array type. Reports identify `multidimensional-array-milestone`. Runtime indexing chains across dimensions evaluate and check each index in order. Multidimensional arrays whose leaf elements are structs are covered in the following phase.

Tests cover asymmetric shapes, nested initialization, shape/type mismatches, partial initialization, row and cell copies/moves, restoration, borrows/disjointness, cleanup, calls/returns, struct fields, zero lengths at either dimension, bounds, defers, CFG joins and deterministic reports. `examples/multidimensional_arrays.cb` includes source and explanation.


### Runtime indexing across multidimensional scalar arrays

Runtime indices may now be used at every dimension, as in `grid[row][column]`. The array base evaluates first; each index expression then evaluates once and its bounds check runs before the next dimension is evaluated. A failure aborts at that dimension. The final access, move, replacement or borrow records all bounds proof values and dimension lengths in ESIR.

Candidate analysis narrows each dimension independently. A known row with an unknown column tracks only cells in that row; unknown indices at both dimensions track their Cartesian candidate set. Reads, moves and borrows require each candidate cell to be initialized and available. Writes update only selected candidates and do not claim that every cell or row was initialized. Repeated unknown-index writes do not prove restoration after a possible move. Literal indices retain the existing static place path.

Array rows and cells preserve independent identities, constants, borrow overlap, and initialized-and-owned cleanup guards. Known distinct cells remain disjoint, including when the other dimension is unknown. By-value nested arrays and struct fields containing nested scalar arrays use the same transitions. Each bounds check is evaluated in source order, before later indices or the assignment RHS.

Tests cover candidate set sizes for mixed known/unknown dimensions, partial initialization, conditional replacement, conservative moves/restoration, per-dimension borrow overlap and disjointness, empty dimensions, bounds aborts, left-to-right single evaluation, calls/returns, defers, branches, array fields and deterministic explanations. `examples/runtime_multidimensional_arrays.cb` includes source and explanation.


### Multidimensional arrays of structs

Fixed-size arrays may now contain acyclic structs at multiple dimensions, such as `Point[2][3]`. The existing 256-element bound counts array cells across dimensions, and each dimension retains its own length and bounds proof. Struct arrays can also appear as fields inside structs, subject to the same acyclic by-value type rules.

Nested construction transfers complete struct snapshots into each selected cell. Literal row, element, and field access uses the aggregate place tree; copies, moves, replacement, partial field restoration, borrowing, by-value calls/returns, and cleanup preserve separate state for each struct and descendant field. Disjoint cells remain independently borrowable.

Runtime indices at each dimension check in source order and retain candidate struct places. Whole-element reads, moves, replacement, and borrows track all possible candidates. Field projections such as `points[row][column].x` are applied after the dimensions are checked, so reads, moves, writes, and borrows account for the selected field in every possible struct. ESIR reports use `multidimensional-struct-array-milestone` and record the dimension proofs, candidate places, ownership state, and field projection.

Tests cover nested construction, field and whole-element transfers, restoration, row copies/moves, known and unknown index candidates, dynamic field moves and borrows, disjointness, bounds failures, struct fields, deterministic reports, and cleanup. `examples/multidimensional_struct_arrays.cb` includes source and explanation.


### Reads from temporary multidimensional struct arrays

Returned nested struct arrays now support chained element reads such as `make_grid()[row][column]`, including direct field reads such as `make_grid()[row][column].x`. Each indexing layer lowers to its own checked temporary extraction, so each index expression is evaluated once and its bounds check runs before the next index expression. Mixed literal/runtime indices narrow the candidate paths at each layer.

Every extraction creates an independent copy of the selected row or struct, then cleanup discards the source temporary's owned leaves before continuing. ESIR records a separate bounds proof, candidate set, result field snapshot, and cleanup operation for each layer. The final selected struct can flow through the existing by-value call, return, field extraction, and cleanup behavior. Arrays retain the multidimensional 256-cell bound.

Borrowing and assignment targeting temporary elements or fields still require first binding the returned array or selected value to a local. Tests cover two- and three-dimensional indexing, known/unknown candidate narrowing, field reads, left-to-right single evaluation, bounds failures, independent identities, cleanup order and amounts, deterministic reports, and rejected temporary-place operations. `examples/multidimensional_temporary_struct_arrays.cb` includes source and explanation.


### Moving selected elements from temporary arrays

`move make_values()[index]` and nested expressions such as `move make_grid()[row][column]` now transfer a selected element from an owned temporary array. Each source expression and index evaluates once in left-to-right order; every dimension performs its bounds check before the next index. Nested moves transfer intermediate rows as well as the final element, preserving the selected element and descendant identities across each extraction.

After a definite selection, cleanup destroys the remaining temporary elements and skips the transferred subtree. For runtime indices, ESIR records the candidate elements and conditional destruction of every element not selected at runtime. The extracted value can be stored, returned, or passed by value. Bounds failure produces no successful transfer and does not guarantee cleanup. Borrowing and assignment targeting temporary elements, and moving temporary fields, remain unsupported.

Tests cover scalar and struct elements, known and runtime selections, nested arrays, identity preservation, conditional and definite cleanup, calls, bounds failure, deterministic ESIR and explanations. `examples/temporary_array_moves.cb` includes source and explanation.


### Moving fields from temporary structs

An owned temporary struct now supports explicit field or substruct transfer, for example `move make_point().x` or `move make_outer().point`. Field-path snapshots are rebased to the result type and retain the source identities. Cleanup skips the transferred subtree and destroys the remaining initialized scalar leaves.

This composes with temporary array extraction: `move make_outer_array()[index].point` first transfers the selected outer element, then transfers its `point` field. Runtime-selected array elements preserve all candidate identities, while field cleanup skips exactly the transferred descendant path. The extracted field may be stored or passed by value. Borrowing or assigning temporary fields remains unsupported.

Tests cover scalar and nested-substruct transfers, fields selected from temporary arrays, field-path rebasing, identity preservation, cleanup, runtime candidate handling and deterministic reports. `tests/test_temporary_field_moves.py` contains the checked cases.


### Call-scoped borrows of temporary values

An owned temporary may be borrowed as a call argument, for example `read(&make_values()[index])`, `set(&mut make_point().x)`, or `inspect(&make_point())`. The compiler materializes the selected value in hidden owned storage, creates the normal managed capability, and keeps that storage alive across nested calls in the same expression. Mutable temporary borrows may update the temporary before it is destroyed.

After the outer call, `temporary_end` checks that no live capability still refers to the temporary, then records destruction and lifetime termination. A call that returns the temporary borrow therefore fails before the temporary is ended; storing a borrow outside a call and pointer-valued temporary borrows remain unsupported. Index extraction keeps its checked bounds and selected-element cleanup behavior.

Tests cover scalar and aggregate borrows, shared and mutable access, nested call forwarding, cleanup ordering, rejected escapes and deterministic explanations. `examples/temporary_borrows.cb` includes source and explanation.


### Moves through exclusive managed pointers

`move *pointer` now transfers a scalar or complete struct from a mutable managed capability. Projected scalar and substruct fields can also be moved through a mutable struct pointer. The operation requires exclusive access and a fully initialized referent; shared capabilities reject moves. ESIR records the referent candidates, transferred identities and moved source states.

The pointer remains associated with its storage after a move. Replacing the whole referent through `*pointer = value` restores a moved scalar or struct and skips destruction of the moved old fields. A moved projected field can be restored through `pointer->field = value`; sibling fields remain available.

Tests cover scalar and struct transfers, field paths, source identity, moved-state reads, shared access rejection, replacement restoration and cleanup. `examples/managed_pointer_moves.cb` includes source and explanation.


### Whole-array moves through managed pointers

An exclusive pointer to a fixed-size array may now transfer the entire array with `move *pointer`; a containing struct pointer may similarly transfer an array field with `move pointer->values`. A pointer-indexed row or element can be moved with the existing dimension and bounds checks. The selected array or row retains descendant identities, while the source storage becomes moved or partially moved.

Whole-array or row replacement through the same mutable pointer restores the moved storage. Runtime-selected rows remain conservative alternatives, and whole-array access still requires every descendant to be available. Shared parents cannot authorize a move. Tests cover complete array and row transfers, scalar and struct descendants, bounds, replacement, cleanup and pointer permissions.

When a managed pointer has several possible referents, a whole-value move records one-of-referents selection and conditionally moves each candidate. The result retains alternatives without treating the operation as a move from every target. Each candidate's before/after state is included in ESIR, and later reads of any candidate are rejected when that candidate may have been selected. Tests cover conditional pointer parameters returned from a branch and conservative owner reads.

### Checked indexing through whole-array pointers

An existing pointer to a complete fixed-size array can now project checked elements with `(*pointer)[index]`, including chained indexing through multidimensional arrays. Each index evaluates once and gets its own bounds check in source order. Reads and shared or mutable element borrows resolve candidates relative to the pointer's referent, so the whole-array capability continues to govern conflicts and element paths remain available in ESIR.

Pointer indexing applies to arrays of supported scalars and structs. Runtime indices preserve the existing conservative candidate semantics, and mutable access requires an exclusive pointer. Tests cover literal and runtime indexing, multidimensional candidate sets, overlap with whole-array borrows, and deterministic report text.

### Element replacement through whole-array pointers

Exclusive whole-array pointers may replace checked selected elements, including a cell selected through multiple dimensions. Index and bounds checks run before the assignment value is evaluated, and the write capability is derived only after the right-hand side succeeds. A shared whole-array pointer cannot authorize element replacement. Runtime selection updates each possible cell conditionally and keeps unselected states intact.

Tests cover definite and unknown-index replacement, multidimensional checks, permission rejection, restoration of moved cells, and reads through the original array after the pointer's last use.


### Element moves through whole-array pointers

`move (*pointer)[index]` transfers the selected scalar, struct, row, or nested aggregate through an exclusive whole-array capability. Every dimension is bounds checked before transfer. A definite move marks the selected storage moved; runtime selection records a conditional move for each candidate. Replacing the selected cell or row through the pointer restores availability, while shared pointers reject the transfer.

Tests cover definite and runtime scalar moves, moved-cell restoration, permission rejection, multidimensional selection, and ownership state evidence.


### Struct field projections through whole-array pointers

When the selected array element is a struct, field paths may follow the checked indices, as in `(*points)[index].x`. Reads, writes, shared/mutable field borrows, and moves reuse the same candidate element and parent capability checks. A field move leaves sibling fields available, and reinitializing it restores whole-element availability; unknown indices retain conditional per-candidate state.

Tests cover direct and multidimensional struct-array projections, field moves and replacement, permission/overlap checks, sibling availability, cleanup, and deterministic explanations.


### Independent pointer-binding mutability and rebinding

Binding mutability is now distinct from managed-pointer access capability. A qualifier immediately before the binding name marks a pointer variable reassignable, for example `i32* mut selected`; `mut i32* selected` remains an immutable binding with an exclusive referent capability. The two qualifiers may be combined as `mut i32* mut selected`.

Assignment to a mutable pointer binding replaces its capability set after the right-hand side has been validated. Shared pointers may be reseated to another shared referent. Exclusive pointers require a valid exclusive capability, normally transferred with `move`. Immutable pointer bindings reject reassignment. ESIR records the old and new capability sets and the rebinding effect.

Rebinding follows ordinary borrow liveness: a discarded target capability ends when no alias still needs it, while derived aliases keep the old referent protected. Branch assignments retain every possible new target, returned pointer summaries follow a reseated parameter to its replacement input, and an invalid rebind leaves the previous capability and referent state unchanged. These rules apply to scalar, array, struct, and projected-field pointers.

Tests cover qualifier parsing and separation, local and parameter rebinding, shared and exclusive capabilities, branch alternatives, aliases of old targets, arrays and struct fields, invalid type changes, returned provenance, and deterministic ESIR.


### Equality-based scalar refinement on branch edges

When a two-way branch tests a place against a known scalar constant with `==` or `!=`, the outgoing edge that proves equality now refines that place to the constant. Both operand orders are supported. This applies to the true edge of `index == 0`, the false edge of `index != 0`, and nested branches. Refinements are edge-local, so joins keep only facts supported by their incoming states.

Array analysis consumes the refined value for bounds checks and candidate selection, including reads, moves, borrows, writes, and access through whole-array pointers. A proven in-range value removes an unnecessary runtime bounds check; a proven out-of-range value reports the existing bounds diagnostic. ESIR stores the edge, place, and constant in `branch_refinements`, and the explanation describes the refinement and its join boundary.

The analysis does not combine relations between different variables, propagate ranges through arithmetic expressions, or retain disjoint ranges as separate alternatives. It also declines to refine a place when a call between its load and the comparison could have changed it through a managed pointer. Tests cover operand order, equality and inequality outcomes, nested edges, bounds, candidate narrowing, moved and borrowed elements, pointer indexing, join behavior, stale-load protection, and explanation output. `examples/branch_index_refinement.cb` includes source and explanation.


### Relational integer ranges on branch edges

The branch refinement pass now handles `<`, `<=`, `>`, and `>=` between an integer place and a known integer constant. It applies the comparison on the true edge and its inverse on the false edge, and it normalizes constant-left comparisons (`0 <= index`) to the corresponding constraint on the place. Each place carries an inclusive lower and upper bound; nested branch edges intersect those bounds. At a join, incoming ranges combine to their conservative interval hull.

Array bounds checks intersect the incoming interval with the legal index range. If all possible values are in bounds, the runtime check is removed; if the intervals cannot overlap, the existing out-of-bounds diagnostic is reported. Otherwise, the success edge carries the intersected range, and array reads, writes, moves, borrows, and pointer projections consider only elements in that range. This also allows the borrow checker to prove a range-selected write disjoint from an element outside the range. ESIR records the incoming and successful bounds in `index_range_before_bounds` and `index_range_on_success`; branch evidence records the refined interval.

Ranges are inclusive and use the source integer type's representable limits for integer parameters. The analysis does not track variable-to-variable relations, arbitrary arithmetic ranges, or disjoint alternatives, and function calls between a place load and its comparison suppress refinement because the call may mutate the place through a pointer. Tests cover all comparison operators and edge outcomes, operand order, range intersections, safe and impossible bounds, candidate narrowing, borrow disjointness, pointer access, joins, and explanation output. `examples/relational_index_ranges.cb` includes source and explanation.

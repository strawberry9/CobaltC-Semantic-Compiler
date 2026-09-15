![Project Logo](images/CobaltC_Cyber_Guardian_Poster_small.png)

# CobaltC Semantic Compiler

Progress toward the first milestone is tracked in the [Core requirements checklist](docs/core-checklist.md), including implementation gaps, acceptance criteria, and explicit deviations from full Core Conformance.

The agreed first milestone is a **single-module core semantic compiler**, including `match`, with import syntax accepted but import resolution explicitly incomplete. FFI, concurrency, threads, and standard-library facilities are outside this milestone. See the [goal and continuation plan](docs/goal.md) for scope, completion criteria, and the next phase.

## Project goals

We are building **a trustworthy CobaltC compiler that explains its reasoning**. The goal is to help programmers understand what their code means under the CobaltC language specification, why an operation is accepted or rejected, and how values are initialized, copied, moved, borrowed, and cleaned up.

The project aims to:

- **Check source code against the specification.** Analyze types, control flow, initialization, ownership, borrowing, lifetimes, and destruction, with diagnostics that identify the relevant source code and language rules.
- **Make compiler decisions inspectable.** Produce Explainable Semantic IR (ESIR), a structured JSON record of semantic operations, established facts, state transitions, and specification references.
- **Explain programs in plain English.** Generate a standalone HTML report containing the original source alongside explanations derived from the recorded analysis, so readers can follow both successful checks and rejected operations.
- **Build trust through evidence.** Expand language support incrementally, testing valid and invalid programs, checking interactions between features, and validating generated artifacts. Clearly distinguish implemented behavior, partial rule coverage, and unsupported features.

Our immediate objective is a reliable semantic analysis and explanation tool for an expanding subset of **CobaltC 1.0.3**. Full language support is a longer-term goal. Native code generation and execution are future work; the current compiler produces ESIR and explanatory reports, and does not yet claim complete language conformance.

---------------------
License

Copyright © 2026 strawberry9.

This repository contains software and other creative content, which are licensed separately.

Source Code

Unless otherwise stated, all source code in this repository is licensed under the BSD 3-Clause License.

See LICENSE for the full license text.

Documentation and Creative Content

Unless otherwise stated, the documentation, language specification, written content, images, graphics, and other original creative content in this repository are licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License (CC BY-NC-ND 4.0).

This means you may share the licensed content for non-commercial purposes, provided that you give appropriate attribution and comply with the license terms. You may not distribute modified versions of the licensed content.

See LICENSE-CC-BY-NC-ND for the complete license text.

Full license:
https://creativecommons.org/licenses/by-nc-nd/4.0/

Third-Party Content

Third-party materials included in this repository may be subject to their own licenses and terms. Such materials are not necessarily covered by either license above. Where applicable, their respective licenses and attribution notices are provided alongside the relevant materials.

------------------

A runnable Python implementation that incrementally analyzes a growing subset of **CobaltC 1.0.3 → Explainable Semantic IR JSON**. No native backend is required or provided. This remains a partial semantic implementation, **not a conforming implementation of the complete language**.

Run from this directory with Python 3.10 or newer; no third-party packages are required:

```sh
python3 -m cobalt examples/scalars.cb
python3 -m cobalt.explain examples/scalars.esir.json

python3 -m unittest discover -s tests -v
python3 tools/audit_artifacts.py
python3 tools/coverage_report.py
```

The default output replaces the source suffix with `.esir.json`. Exit codes are 0 for valid within the implemented profile, 1 for diagnosed language errors, and 2 for unsupported features or invocation/I/O errors. Invalid and incomplete source programs still produce schema-validated diagnostic ESIR. The CLI refuses to overwrite its input.

The compiler validates every output against the **supplied schema** and checks entity/rule references. Its dependency-free validator implements all validation keywords used by that schema, and rejects unknown schema keywords. It is not a general-purpose JSON Schema engine.

## Read ESIR in your browser

![Project Logo](images/Coby_small.png)

Generate a standalone HTML report:

```sh
python3 -m cobalt.explain examples/scalars.esir.json
```

Open `examples/scalars.esir.html` in a browser. The report includes the source code followed by a plain-English interpretation generated from the recorded analysis: function inputs, possible paths, assignments, copies, moves, return preparation, cleanup, and any diagnostics. It does not guess behavior for unsupported code. The overview shows at most eight paths; all blocks remain available in the detailed report.

The report also shows source binding names, initialization/ownership transitions, diagnostics, and clickable control-flow paths. Expand an operation to inspect its exact effects, facts, and rule references. It is a static analysis report, not a runtime trace. No web server, JavaScript, or internet connection is needed.

Source files are loaded from their recorded paths, relative to the working directory or the JSON directory, or by filename alongside the JSON. Missing or changed source files are noted in the report. The source is embedded in the HTML so it remains available when sharing the report.

Use `-o report.html` to choose another output path. The original JSON is preserved.

## Implemented slice

- Explicit module declaration, simple function exports, scalar functions and parameters, lexical scope and name resolution, duplicate and protected-name checks.
- UTF-8 decoding, pinned Unicode 17 identifier and security checks, exact reserved names, nested comments, integer/float/character/string tokenization and source spans.
- Fixed-width signed/unsigned integer types, `bool`, `char`, and function return `void`; contextual integer literals and range checking.
- Typed mutable/immutable locals, local constants, initialization, assignment statements, explicit `move`, implicit scalar copying, calls and returns.
- Integer `+`, `-`, `*`, unary signs, comparisons; Boolean `!`, equality, `&&` and `||`. Checked arithmetic has explicit success/abort control edges.
- Acyclic CFGs for `if`/`else`, lexical blocks, early return, and short-circuit expressions. Initialization and ownership use reachable predecessor states, not a flat AST walk. Equality branches can refine a scalar place to a known constant, and relational integer comparisons can narrow its range on the proving edge; array bounds and candidate analysis use those facts without leaking them across joins.
- Guarded scalar destruction, lifetime-ending operations, and simple `defer` blocks. Deferred names bind at registration and values are read at execution; returns evaluate before cleanup.
- Nominal local structs with fixed-width integer, `bool`, `char`, fixed-size arrays, and nested struct fields; named construction, field reads/writes, whole-struct copies, moves, and replacement, partial field moves and reinitialization, per-field initialization at CFG joins, guarded scalar-field cleanup, and by-value function parameters and returns. Structs may also contain managed scalar pointer fields with lifetime and permission checks.
- Non-null managed pointers to scalars, arrays, and scalar-field structs, independently mutable pointer bindings with safe rebinding, shared and mutable borrows, scalar dereference reads/writes/moves, checked array-element projection through whole-array pointers, struct field projection through pointers, whole-struct and whole-array moves/replacement/copies, mutable capability transfers, reborrows, last-use liveness, input-derived returned borrows, call-scoped borrows of temporary values, and disjoint/overlapping storage checks.
- Fixed-size scalar arrays, including nested dimensions such as `i32[2][3]` and at most 256 scalar cells per value, with nested list initialization, literal-index reads/writes/moves/borrows and independent state per cell and row. Runtime indexing across dimensions checks each index in order and tracks possible cells conservatively. Whole-array copies/replacement, explicit shared/mutable whole-array borrows, selected-element moves from temporary arrays, and by-value parameters/returns are supported. Lengths 0–256 are supported; slices remain unsupported.
- Multidimensional arrays of acyclic structs, including nested construction and struct-array fields, with literal/runtime whole-element and field access. Candidate analysis tracks each dimension; copies, moves, replacement, partial field restoration, borrows, by-value transfers and cleanup preserve per-element state. Each value is bounded to 256 array cells.
- Managed struct pointers support checked multidimensional access to scalar or struct array fields, including direct selected-struct field projections. Permission, bounds, candidate-overlap, returned-borrow lifetime, scalar/struct moves, and whole-array or row moves apply through every dimension.
- Arrays of acyclic structs with literal/runtime field access and checked whole-element copies, replacement, moves and borrows; partial moves and restoration, whole-array copies/moves, and by-value parameters/returns. Nested scalar-array field indexing supports both literal and runtime indices. Temporary struct-array reads copy the selected element and support subsequent field extraction. Structs may themselves contain arrays of acyclic structs.
- Stable IDs, canonical JSON, SHA-256 source hashes, source/formal rule references, operation facts, structured diagnostics and reference validation.

The latest recorded validation has **487 passing tests**, exercising **82 of 1,265 rule IDs**. Exercised rules are marked partial; these counts are evidence of tested behavior, not a percentage of language completion. Regenerate the evidence with `python3 tools/coverage_report.py`.

See [the implementation inventory and decisions](docs/implementation.md), [the complete input inventory](docs/inventory.json), and [rule exercise evidence](docs/coverage.json).

## Current boundaries

Not implemented: imports/multiple translation units, aliases, global constants, recursive struct definitions, custom destruction hooks, enums, generics, associated functions, nested/nullable managed pointers, recursive returned-borrow inference, raw pointers, slices, String/library copy contracts, floating-point semantics, target-sized integer/ABI profiles, loops, match, error propagation, unsafe, concurrency, FFI, and a runtime/library.

`defer` supports the implemented scalar, pointer, struct, and array statements within lexical blocks; nested defers and conditional/control-transfer deferred bodies are unsupported. Assignment expressions are supported only as standalone statements; their value-producing semantics are not assumed. Division, remainder, shifts, bitwise operators and compound assignment are not implemented.

Structs may contain fixed-size scalar or struct arrays, with literal/runtime element access through local and parameter struct bindings. Array-field element borrows overlap the containing struct and array; disjoint sibling fields remain available. Managed pointers support checked access through every array dimension, whole-array copies, replacement and moves, explicit shared/mutable borrows of complete arrays and selected elements, and moves of scalar, struct, array, row, or field referents.

Returned scalar and struct-array temporaries support checked element reads, element moves, field moves, and call-scoped borrows, including chained indexing such as `make_grid()[row][column]` and direct field reads. Each layer evaluates and checks its index once; reads copy the selected value independently, while moves preserve its identity and clean up unselected values. A temporary borrow remains alive through its call expression and cannot escape it. Assigning a temporary element or field still requires a local binding. Array literals still require an expected array type.

Constructed and returned struct temporaries support field reads and explicit field moves such as `make().point.x` and `move make().point.x`. A temporary field may be borrowed for a call expression, but the borrow cannot escape; assignment to temporary fields still requires first storing the struct in a local binding.

The `valid` result is scoped to the reported milestone and its checks, not a complete CobaltC conformance certificate. `compilation.compiler.conformance_claim` is always false. Unsupported constructs are diagnosed where recognized; unrecognized grammar may produce syntax diagnostics. Concurrent and FFI sections remain empty. Managed-pointer reports include explicit capability and lifetime evidence.

## Implementation choices

The struct slice supports acyclic nesting, including paths such as `rectangle.start.x`, and local bindings and construction with `Point { x = 1, y = 2 }`. Direct field assignment requires a mutable containing binding; assignment through a struct pointer requires an exclusive mutable capability. Each field has a separate place and initialization state; partial initialization of a struct does not authorize reading its remaining fields. Local whole-struct copies preserve the source and create independent field values; explicit moves transfer every field and make the source unavailable until reinitialized. Both require all fields on every incoming path. Moving an individual field leaves its siblings available; reinitializing every moved field restores whole-value availability. Shared and mutable field borrows support disjoint sibling access and prevent conflicting access to a borrowed field or its containing struct. Whole-struct pointers support borrowed function parameters and `pointer->field` (equivalently `(*pointer).field`) reads, writes, moves, and field reborrows. Whole-array pointers support checked element reads and shared/mutable element borrows through `(*pointer)[index]`, including each dimension of multidimensional arrays. Input-derived returned pointers retain field paths and lifetime constraints. Struct parameters and return values also support by-value ownership: ordinary local-value arguments and returns copy, while explicit `move` transfers ownership. Constructors and call results supply owned values directly. Calls produce initialized result fields without compile-time evaluation of the callee. Exclusive pointers support whole-value moves and replacement; replacement evaluates the complete right-hand side before destroying the previous initialized leaves.

Source positions use one-based Unicode scalar columns and exclusive end positions; CRLF is one line break. Identifiers are never normalized or case-folded. Vendored Unicode 17 tables provide classification, security profiles and confusable skeletons, including ASCII confusable conflicts; the compiler uses them offline. Security skeletons do not change identifier identity.

Constant initializers must evaluate to a known scalar under the implemented constant analysis. The analysis propagates scalar constants through locals and reachable acyclic joins, but does not evaluate function bodies at call sites. No implicit integer widening is assumed. Assignment statements always require `mut`, including a later first initialization or reinitialization after a move; declaration initializers may initialize immutable bindings.

For the supported checked integer operations, runtime failure is represented as **abort**: no successful value, no continuation through the success edge, and no guaranteed cleanup. This documents the choice permitted by Sections 27 and 54; ESIR consumers must implement that contract. Arithmetic operations are retained even when a constant result is known.

Place entities describe declaration-time storage. Operation `state_before`/`state_after` attributes describe path-dependent states; they must not be read as one global final state. Value-instance identity is distinct from place identity: copies establish independent identities and moves preserve transferred identity. Cleanup has an explicit initialized-and-owned guard. A moved/uninitialized place does not execute destruction.

## Examples

- [relational_index_ranges.cb](examples/relational_index_ranges.cb): nested integer guards prove array bounds and narrow possible elements, with a [standalone report](examples/relational_index_ranges.esir.html).
- [branch_index_refinement.cb](examples/branch_index_refinement.cb): equality branches narrow checked array indices and explain the edge-local fact, with a [standalone report](examples/branch_index_refinement.esir.html).
- [runtime_multidimensional_arrays.cb](examples/runtime_multidimensional_arrays.cb): runtime row and cell indices with checked bounds at each dimension, with a [standalone report](examples/runtime_multidimensional_arrays.esir.html).

- [multidimensional_arrays.cb](examples/multidimensional_arrays.cb): nested scalar arrays with literal-index access, row transfers and partial moves, with a [standalone report](examples/multidimensional_arrays.esir.html).

- [struct_array_fields.cb](examples/struct_array_fields.cb): arrays of structs within structs, with a [standalone report](examples/struct_array_fields.esir.html).

- [temporary_struct_arrays.cb](examples/temporary_struct_arrays.cb): checked copies and field reads from temporary struct arrays, with a [standalone report](examples/temporary_struct_arrays.esir.html).
- [multidimensional_struct_arrays.cb](examples/multidimensional_struct_arrays.cb): runtime selection, field borrowing and updates in a two-dimensional struct array, with a [standalone report](examples/multidimensional_struct_arrays.esir.html).
- [multidimensional_temporary_struct_arrays.cb](examples/multidimensional_temporary_struct_arrays.cb): checked chained reads and cleanup from a returned struct grid, with a [standalone report](examples/multidimensional_temporary_struct_arrays.esir.html).
- [pointer_multidimensional_arrays.cb](examples/pointer_multidimensional_arrays.cb): checked multidimensional access and field borrowing through a managed struct pointer, with a [standalone report](examples/pointer_multidimensional_arrays.esir.html).

- [nested_runtime_indices.cb](examples/nested_runtime_indices.cb): checked scalar-array indexing inside runtime-selected structs, with a [standalone report](examples/nested_runtime_indices.esir.html).

- [runtime_array_fields.cb](examples/runtime_array_fields.cb): direct runtime-selected field access, moves and disjoint borrowing, with a [standalone report](examples/runtime_array_fields.esir.html).

- [runtime_struct_arrays.cb](examples/runtime_struct_arrays.cb): checked struct-element copies, moves, replacement and borrows, with a [standalone report](examples/runtime_struct_arrays.esir.html).

- [struct_arrays.cb](examples/struct_arrays.cb): arrays of structs, partial moves, restoration and element borrowing, with a [standalone report](examples/struct_arrays.esir.html).

- [pointer_array_values.cb](examples/pointer_array_values.cb): whole-array field copies and replacement through struct pointers, with a [standalone report](examples/pointer_array_values.esir.html).
- [whole_array_borrows.cb](examples/whole_array_borrows.cb): whole-array borrows and checked element moves/reinitialization through array pointers, with a [standalone report](examples/whole_array_borrows.esir.html).
- [pointer_rebinding.cb](examples/pointer_rebinding.cb): shared pointer reseating, branch-selected targets, and exclusive capability transfer between mutable pointer bindings, with a [standalone report](examples/pointer_rebinding.esir.html).
- [temporary_array_moves.cb](examples/temporary_array_moves.cb): identity-preserving moves from runtime-selected temporary arrays, including nested struct arrays, with a [standalone report](examples/temporary_array_moves.esir.html).
- [temporary_borrows.cb](examples/temporary_borrows.cb): shared and mutable borrows of temporary elements and fields that last through their call, with a [standalone report](examples/temporary_borrows.esir.html).
- [managed_pointer_moves.cb](examples/managed_pointer_moves.cb): moving and reinitializing scalar and struct values through exclusive pointers, with a [standalone report](examples/managed_pointer_moves.esir.html).
- [pointer_array_fields.cb](examples/pointer_array_fields.cb): checked element access through struct pointers, with a [standalone report](examples/pointer_array_fields.esir.html).
- [pointer_fields.cb](examples/pointer_fields.cb): managed scalar pointer fields with shared reads, exclusive writes, and lifetime checks, with a [standalone report](examples/pointer_fields.esir.html).

- [array_fields.cb](examples/array_fields.cb): scalar arrays inside structs, partial moves and restoration, with a [standalone report](examples/array_fields.esir.html).

- [temporary_arrays.cb](examples/temporary_arrays.cb): checked reads from returned arrays, with a [standalone report](examples/temporary_arrays.esir.html).

- [runtime_array_moves.cb](examples/runtime_array_moves.cb): checked element moves and restoration, with a [standalone report](examples/runtime_array_moves.esir.html).
- [invalid_runtime_move.cb](examples/invalid_runtime_move.cb): reading an element that may have moved.

- [runtime_array_borrows.cb](examples/runtime_array_borrows.cb): runtime-index borrows, reborrows and returned pointers, with a [standalone report](examples/runtime_array_borrows.esir.html).
- [invalid_runtime_borrow.cb](examples/invalid_runtime_borrow.cb): mutable borrows whose unknown indices may overlap.

- [runtime_arrays.cb](examples/runtime_arrays.cb): checked runtime reads and writes, with a [standalone report](examples/runtime_arrays.esir.html).
- [invalid_runtime_index.cb](examples/invalid_runtime_index.cb): an index variable proven to be out of bounds.

- [arrays.cb](examples/arrays.cb): array construction, element moves and borrows, and by-value returns, with a [standalone report](examples/arrays.esir.html).
- [invalid_array_index.cb](examples/invalid_array_index.cb): a literal index outside the array bounds.

- [temporary_fields.cb](examples/temporary_fields.cb): field reads from constructors and returned structs, with a [standalone report](examples/temporary_fields.esir.html).

- [nested_structs.cb](examples/nested_structs.cb): nested construction, partial moves, restoration and disjoint borrowing, with a [standalone report](examples/nested_structs.esir.html).
- [invalid_nested_move.cb](examples/invalid_nested_move.cb): passing a struct whose nested field has been moved.

- [struct_dereferences.cb](examples/struct_dereferences.cb): whole-struct pointer copies and replacement, with a [standalone report](examples/struct_dereferences.esir.html).
- [invalid_struct_replacement.cb](examples/invalid_struct_replacement.cb): whole-struct replacement conflicting with a live field borrow.

- [struct_calls.cb](examples/struct_calls.cb): struct construction, copy/move arguments, returned values and cleanup, with a [standalone report](examples/struct_calls.esir.html).
- [invalid_struct_argument.cb](examples/invalid_struct_argument.cb): passing a partially moved struct by value.

- [struct_pointers.cb](examples/struct_pointers.cb): borrowed struct parameters, field projection and a returned field pointer, with a [standalone report](examples/struct_pointers.esir.html).
- [invalid_struct_pointer.cb](examples/invalid_struct_pointer.cb): mutation through a shared struct pointer.

- [partial_fields.cb](examples/partial_fields.cb): partial moves, restoration, and simultaneous mutable borrows of distinct fields, with a [standalone report](examples/partial_fields.esir.html).
- [invalid_partial_move.cb](examples/invalid_partial_move.cb): whole-value copying after a field move.
- [invalid_field_borrow.cb](examples/invalid_field_borrow.cb): replacing a struct while its field remains borrowed.

- [struct_transfers.cb](examples/struct_transfers.cb): whole-struct copy independence, moves, and guarded cleanup. Generate its report with `python3 -m cobalt.explain examples/struct_transfers.esir.json`.
- [invalid_struct_move.cb](examples/invalid_struct_move.cb): reading a field after moving its containing struct.

- [structs.cb](examples/structs.cb): construction and separate field initialization. Generate its report with `python3 -m cobalt.explain examples/structs.esir.json`.
- [invalid_struct_initialization.cb](examples/invalid_struct_initialization.cb): a field initialized on only one branch.

- [borrows.cb](examples/borrows.cb): shared reborrowing, last-use expiration, and resumed exclusive access. Generate its report with `python3 -m cobalt.explain examples/borrows.esir.json`.
- [invalid_borrow.cb](examples/invalid_borrow.cb): owner assignment while a shared borrow is still needed.
- [invalid_lifetime.cb](examples/invalid_lifetime.cb): an attempted return of a local borrow.
- [scalars.cb](examples/scalars.cb): branches, arithmetic, copy and move.
- [defer.cb](examples/defer.cb): cleanup and return ordering.
- [invalid_move.cb](examples/invalid_move.cb): use after move.
- [invalid_initialization.cb](examples/invalid_initialization.cb): a missing initialization path.
- [invalid_type.cb](examples/invalid_type.cb): incompatible initialization.

Each has a checked-in `.esir.json` output. Golden tests check determinism; semantic assertions separately inspect transitions, diagnostics, and cleanup order.

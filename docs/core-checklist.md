# Single-module core semantic checklist

This is the acceptance checklist for [the agreed goal](goal.md), based on CobaltC 1.0.3 [Section 80](../Appendix_06(10).html#section-80), especially 80.1 and 80.12. It is a requirements-family inventory, not a claim to have independently verified every normative clause. Before implementing each family, enumerate its detailed rules from the specification and connect them to tests. `coverage.json` records exercised rule references, not completed requirements.

**Scope:** Required means necessary for this milestone; deferred means an explicit unresolved or later milestone boundary; excluded means outside the user-agreed scope. **Status:** partial means some implementation and tests exist; missing means no supported implementation was identified; audit means current behavior needs checking against normative rules. No family below is certified complete by this inventory.

Section numbers below refer to the normative [specification](../Appendix_06(10).html). Test paths are relative to `tests/`; implementation paths are relative to `cobalt/`. Evidence was inspected on 2026-09-15; listed tests are evidence locations, not a claim of a fresh full-suite run.

## Section 80.1 obligations

| Core obligation | Milestone coverage |
| --- | --- |
| Required language syntax | C01–C03, C06–C10, C15–C18; imports have the explicit C02 exception |
| Name resolution | C02–C03, C06–C07 |
| Type system | C04–C08, C13, C17 |
| Static semantics | All required rows; especially C05, C09–C10, C19 |
| Initialization | C11 |
| Ownership | C11–C12, C15 |
| Borrowing and capabilities | C12–C13 |
| Lifetimes | C12, C15–C16 |
| Nullability | C13; required, currently missing |
| Bounds and memory safety | C08, C12–C14 |
| Core memory model | C14 retains single-thread access/lifetime/sequencing obligations; concurrency is excluded |
| Other normative Core facilities | C03, C06–C07, C15–C18 and the scope review below; this catch-all is not waived |

## Required implementation and acceptance inventory

| ID | Requirement and source | Current evidence/status | Acceptance gate |
| --- | --- | --- | --- |
| C01 | Source, comments, identifiers, literals (§§3–7; Appendices A/B) | Partial: `lexer.py`, `unicode_identifiers.py`; `test_source_lexer.py`, `test_parser.py` | Cover normative grammar, malformed tokens, Unicode security and literal forms; separate token acceptance from unsupported value semantics. |
| C02 | Single module, import syntax, local exports (§§3,8,20) | Partial: `syntax.py` rejects imports as unsupported declarations; `test_parser.py`, `test_compiler.py` | Parse plain, selective, and grouped imports with normative separators; retain their source evidence, report unresolved import semantics as incomplete, check local declarations without inventing imported symbols. Validate local export targets. Cross-module access remains excluded. |
| C03 | Names, declarations, aliases, constants (§§8–11) | Partial: local names/constants supported; top-level aliases/constants rejected in `syntax.py`; `test_compiler.py` | Resolve local/module scopes, shadowing and duplicates; aliases preserve identity; document constant-expression rules and check module constants and dependency cycles. |
| C04 | Primitive types and inference (§§7,12,17–18,78) | Partial: fixed-width integers/bool/char/void; `semantic.py` rejects floating and target-sized semantics; `test_compiler.py` | Add or explicitly resolve a documented numeric profile for f32/f64/isize/usize and predefined limit constants. Preserve type/capability distinctions; reject ambiguous inference. Tokenization is insufficient. |
| C05 | Expressions, operators, assignments (§§25–30) | Partial: `syntax.py`, `semantic.py`, `dataflow.py`; `test_compiler.py` | Account for every normative operator, evaluation order, compatibility, value-producing assignment, division/remainder/shift/bitwise rules, constant errors and runtime failure edges. Do not import another language's arithmetic conventions. |
| C06 | Functions, associated functions and function types (§§13,24,30,34) | Partial: ordinary calls and returns; associated declarations rejected; `test_compiler.py`, `test_struct_calls.py`, `test_borrowing.py` | Validate signatures, qualified lookup, explicit receivers, all successful return paths, argument order, and ownership/lifetime contracts, including recursive calls. Inspect normative function-value requirements before choosing representation. |
| C07 | Unconstrained generics (§19) | Missing: generic declarations rejected in `syntax.py` | Check parameterized declarations and instantiations, nominal identities and universally permitted operations. Do not invent constraint syntax (outside this edition). |
| C08 | Structs, arrays, component access (§§13,21,23) | Partial: `structs.py`, `arrays.py`; `test_structs.py`, `test_nested_structs.py`, `test_arrays.py`, `test_multidimensional_struct_arrays.py` | Validate component initialization, copies/moves, replacement, temporaries, pointer fields and nesting across all supported paths. Document array resource limits; do not claim they are language limits. |
| C09 | Conditionals and loops (§§31–32) | Partial: acyclic if/else CFG; `test_compiler.py`; loops missing | Support while/loop/for/foreach with converging initialization, ownership, borrow and liveness analysis. Check zero/multiple iterations, break/continue, for increment on continue, loop scope/defer cleanup, and non-returning paths. Array/range iteration does not require Vector. |
| C10 | Enums and match (§§22,33) | Missing: enums rejected, no match lowering | Support nominal variants and payloads, zero-variant types, construction, statement/expression match, first matching arm, wildcard, exhaustiveness, result compatibility and per-arm ownership/borrow joins. |
| C11 | Initialization, ownership, moves, copies, partial moves (§§36–40) | Partial: `dataflow.py`, `structs.py`, `arrays.py`; `test_structs.py`, `test_pointer_moves.py`, `test_runtime_array_moves.py` | Preserve identity and state at joins, calls and temporaries; rejected operations cannot establish ownership or initialization. Recheck copyability recursively by field type and destruction contracts. |
| C12 | Borrowing, capability permissions, lifetimes, aliasing, invalidation (§§14,16–18,41–50) | Partial/audit: `borrowing.py`, `structs.py`; `test_borrowing.py`, `test_structs.py`, `test_temporary_borrows.py` | Preserve capability provenance through aggregate copies/moves, calls/returns and cleanup; reject escapes and conflicting access. Reconcile mutable pointer copy behavior with §14 (non-implicitly-copyable) and §17 (shared reborrow conversion). Library storage relocation is excluded, ordinary replacement/invalidation is not. |
| C13 | Nullable and composed managed pointer types (§§13–14,17–18,55) | Missing for nullability/nested pointers: `syntax.py`, `semantic.py` explicit restrictions | Establish non-nullness before dereference, invalidate refinement on relevant changes, preserve it where permitted, handle branch joins and nullable compatibility without widening permissions. Track composed pointer storage separately from its referents. |
| C14 | Bounds and single-thread memory model (§§23,50,56,66,76) | Partial: checked arrays and object/lifetime evidence; `test_runtime_arrays.py`, `test_whole_array_borrows.py` | Check selected storage, subobjects, sequencing, overlap, lifetime end and failure edges. Unknown bounds require explicit checks. Concurrency exclusion does not remove single-thread memory validity. ESIR checks do not prove a future runtime/backend. |
| C15 | Destruction, defer, scope exits (§§21,35,40,51–54) | Partial: guarded cleanup and simple defer; `test_structs.py`, `test_compiler.py`; custom hooks missing | Implement valid destruction hooks, exactly-once owned cleanup, moved fields, reverse scope cleanup, deferred control rules, return ordering and loop exits. Borrowed fields never destroy referents. Abort must follow its distinct contract. |
| C16 | Unsafe/raw language boundary (§§15,67–69) | Missing | Required for the current broad core-language target, separately from excluded FFI/library APIs: check unsafe contexts/functions and raw-pointer operations, retain unrelated static guarantees, never infer managed validity from a raw address. Detailed supported raw operations and profile require a dedicated phase. |
| C17 | Type compatibility across all included forms (§§13,17–19,24) | Partial: `semantic.py`; `test_struct_calls.py`, `test_borrowing.py` | Compose nominal, generic, array, pointer and function compatibility; no implicit increase in access, removal of nullability, or loss of lifetime constraints. |
| C18 | Language error propagation (§58) | Deferred pending dependency decision; no implementation | Postfix ? is language syntax, but its specified operand depends on Result (§57), excluded with the library baseline. Keep this a named deviation; revisit whether a minimal Result contract belongs in scope before claiming close Core coverage. |
| C19 | Diagnostics, profiles and honest acceptance (§§77–80; Appendix G) | Partial: `source.py`, `driver.py`, `esir.py`; `test_compiler.py` | Distinguish invalid source from unsupported/incomplete analysis; document actual profile choices; unsupported combinations cannot become valid. Audit required diagnostics and rejection/acceptance pairs. Keep conformance_claim false. |
| C20 | ESIR and source-inclusive explanations (project requirement) | Partial: `esir.py`, `explain.py`; `test_explain.py`, golden examples | Deterministic valid references and source hashes; English follows recorded semantics, including branch uncertainty, failed operations and unsupported scope. Every new family needs report evidence as well as verdict tests. |

## Explicit exclusions and unresolved boundaries

- **Excluded by user scope:** module loading/linking and cross-module resolution (§8), external representation checking (§20); FFI/platform ABI facilities; threads/synchronization/data races (§§62–65 and concurrent portions of §66); standard-library baseline (§80.2: Result, String, Vector, Slice, Mutex, standard I/O), hosted runtime, allocation/library APIs and native execution.
- **Retained despite those exclusions:** match, generics, associated functions, destruction hooks, nullable pointers, and single-thread memory rules are language facilities. Raw/unsafe language semantics have not been excluded by the user and remain required here; removing them would need an explicit scope revision.
- **Deferred dependency decision:** §58 error propagation depends on Result. String literal token syntax remains required by §7, but producing String values is outside the selected library scope. These cross-boundary facilities must receive explicit unsupported semantics, not silently disappear from the inventory.
- **Profile decision before C04 completion:** select numeric/target assumptions from permitted specification choices; do not silently exclude floats or target-sized integers because the present compiler lacks them.
- **Conformance limit:** syntax-only imports and deferred language/library dependencies prevent a full Core claim. This milestone verifies semantic analysis and modeled runtime checks, not emitted machine-code memory safety.

## Ordered bounded phases

1. **Next: managed pointer soundness audit and repair.** Inspect §14/§17 copy versus shared reborrow semantics, then field provenance across construction, assignment, copies/moves, temporaries, calls/returns, nesting and cleanup. Deliver regression tests and fixes or explicit unsupported diagnostics for uncovered combinations. Update historical claims that overstate support. Do not expand arrays of pointer-bearing structs before this gate.
2. **Import syntax boundary.** Implement the three §8 forms and incomplete-result handling with local analysis and source/report evidence.
3. **Declarations and numeric/operator gaps.** Split C03–C05 into separate bounded phases; settle documented numeric choices before dependent constant/range work.
4. **Nullable pointers.** Build on repaired capability tracking and branch refinement, including refinement invalidation.
5. **Loop foundation and forms.** Establish fixed-point dataflow first, then individual loop forms and cleanup exits with regression gates.
6. **Enums and match.** Introduce variants/payloads first, then statement/expression matching and exhaustiveness; reuse ownership joins.
7. **Associated functions and destruction hooks.** Add qualified lookup before hooks; test cleanup with partial moves and loop exits.
8. **Generics, composed types and raw/unsafe semantics.** Separate phases, each with detailed normative rule mapping and explicit supported boundaries. Revisit C18 dependency scope.
9. **Milestone acceptance audit.** Expand every required row into clause-level evidence, resolve deferred decisions, exercise feature combinations, audit unsupported paths, and reconcile docs/examples/ESIR. No percentage of completion is inferred from test counts.

The order is dependency guidance, not authorization to run multiple phases. Each phase ends with validation, a handoff update, and a stop for confirmation.

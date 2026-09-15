# CobaltC 1.0.3 — Consolidated Formal Semantic Specification and Semantic IR

**Status:** derived semantic artifact; no compiler implementation.  
**Authority:** CobaltC Programming Language Specification 1.0.3 and the previously produced classification/semantic artifacts.

## 1. Scope and authority

This document consolidates the previously extracted CobaltC rules into a single semantic model. It does not add source syntax, runtime facilities, ownership mechanisms, or compiler requirements that are not supported by the specification. Appendix D defines the sequential semantic foundation; Appendix E extends it to concurrent execution; Appendix F applies semantic and ABI contracts at foreign boundaries; Appendix H composes the models.

The specification explicitly permits different sound analyses, intermediate representations, optimization strategies, and runtime representations provided required acceptance/rejection and observable semantics are preserved.

## 2. Semantic domains

```text
Γ  = static lexical / typing / ownership / capability environment
Σ  = (ρ, μ, Λ, Δ)
ρ  = binding environment
μ  = store of storage and object state
Λ  = lifetime identities and validity intervals
Δ  = active deferred-destruction obligations
l  = semantic storage location
λ  = lifetime identity
κ  = access capability
τ  = CobaltC type
π  = control-flow path / program point

Judgments:
Γ ⊢ e : τ
Γ ⊢ p : Place<τ>
Γ ⊢ κ : Cap(l, mode, λ)
Γ ⊢ e ⇒ v
Γ;Σ ⊢ op ⇒ Σ'
Σ ⊢ invariant
Γ ⊢ program ✓
```

## 3. Semantic state model

The sequential state is the specification-level tuple `Σ = (ρ, μ, Λ, Δ)`. The store distinguishes, where applicable, uninitialized storage, initialized valid values, partially moved aggregates, transferred ownership, and consumed/destroyed storage. These are semantic states; implementations need not encode them identically.

### 3.1 Ownership state

```text
Owned(o,l)          — object o is owned through location l
Moved(l)             — ownership formerly represented by l has moved
PartiallyMoved(l,P)  — aggregate at l has moved paths P
Copyable(τ)          — τ permits copying under its contract
```

### 3.2 Initialization state

```text
Uninit(l)
Init(l,o,τ)
PartInit(l,P)
Consumed(l)
```

### 3.3 Capability state

```text
Shared(κ)
Mutable(κ)
Suspended(κ)
Expired(κ)
Derived(κ,κ0)
```

### 3.4 Lifetime state

```text
λ = lifetime identity
valid(λ,π)
ends(λ,π)
λ_child ⊆ λ_parent
```

### 3.5 Deferred destruction

```text
Δ = ordered set of deferred obligations
Defer(scope, path, body, registration_order)
```

## 4. Core typing and semantic judgments

The following judgment families are the semantic interface between source constructs and the IR. They are semantic judgments, not implementation APIs.

- `type_of`
- `type_compatible`
- `resolve_name`
- `place_of`
- `initialized`
- `owned_by`
- `copyable`
- `movable`
- `borrowable`
- `borrow_compatible`
- `lifetime_ok`
- `destructible`
- `destruction_order`
- `control_effect`
- `const_value`
- `ffi_contract_ok`
- `abi_repr_ok`
- `unsafe_required`
- `concurrency_safe`
- `program_valid`

## 5. Formal inference and transition rules

The normalized formal layer contains **35 rules**. Each is mapped back to the 1,230 classified specification rules in the traceability artifact.

### STATIC-TYPE-001 — Expression typing

**judgment:** `Γ ⊢ e : T`

**semantic requirement:** Every accepted expression has a specification-permitted type.


### STATIC-TYPE-002 — Type compatibility

**judgment:** `Γ ⊢ T1 ≈ T2`

**semantic requirement:** An operation requiring compatible types is valid only when the specified compatibility relation holds.


### STATIC-INIT-001 — Initialized read

**judgment:** `Γ,Σ ⊢ initialized(p)`

**semantic requirement:** A read requires the place to contain a valid initialized value.


### STATIC-INIT-002 — Valid destruction state

**judgment:** `Γ,Σ ⊢ destroyable(p)`

**semantic requirement:** Destruction applies only to the initialized/partial ownership state permitted by the specification.


### STATIC-OWN-001 — Unique ownership

**judgment:** `Γ,Σ ⊢ owns(p)`

**semantic requirement:** An owned value has exactly one responsible owner.


### STATIC-OWN-002 — Move validity

**judgment:** `Γ,Σ ⊢ move_valid(p)`

**semantic requirement:** A move is valid only when the source currently owns an initialized value and no rule forbids invalidating it.


### STATIC-OWN-003 — Copy validity

**judgment:** `Γ,Σ ⊢ copy_valid(p)`

**semantic requirement:** A copy is valid only when the type copy contract permits copying.


### STATIC-BORROW-001 — Shared borrow creation

**judgment:** `Γ,Σ ⊢ borrow_shared(p,λ)`

**semantic requirement:** Shared borrowing is valid only when ownership, mutability, overlap, and lifetime constraints permit it.


### STATIC-BORROW-002 — Mutable borrow creation

**judgment:** `Γ,Σ ⊢ borrow_mut(p,λ)`

**semantic requirement:** A mutable borrow requires exclusive compatible access to the referent.


### STATIC-BORROW-003 — Capability compatibility

**judgment:** `Γ,Σ ⊢ compatible(κ1,κ2)`

**semantic requirement:** Overlapping capabilities must satisfy the applicable shared/mutable compatibility relation.


### STATIC-BORROW-004 — Borrow end

**judgment:** `Γ,Σ ⊢ end(κ)`

**semantic requirement:** A capability may cease to constrain access only when no later semantic use requires it and doing so preserves behavior.


### STATIC-LIFE-001 — Referent containment

**judgment:** `Γ,Σ ⊢ λb ⊆ λr`

**semantic requirement:** A borrow lifetime cannot exceed the referent lifetime.


### STATIC-LIFE-002 — Returned borrow

**judgment:** `Γ,Σ ⊢ return_borrow(κin,κout)`

**semantic requirement:** A returned managed pointer derived from an input borrow cannot outlive that input borrow.


### STATIC-CTRL-001 — Path merge

**judgment:** `Γ,Σ1,Σ2 ⊢ merge(Σ1,Σ2)`

**semantic requirement:** A control-flow join retains only semantic facts established on all applicable incoming paths, subject to specification rules.


### STATIC-CTRL-002 — Exhaustive match

**judgment:** `Γ ⊢ exhaustive(match)`

**semantic requirement:** Finite known cases must be exhaustively covered where the specification requires rejection of non-exhaustive matches.


### SEM-EVAL-001 — Left-to-right evaluation

**judgment:** `Σ,e1;e2 ⇝ Σ1,Σ2`

**semantic requirement:** Operands and function arguments are evaluated in the specified left-to-right order.


### TRANS-INIT-001 — Initialize

**judgment:** `Σ[p↦Uninitialized] ⟶ init(p,v) ⟶ Σ[p↦Initialized(v)]`

**semantic requirement:** Successful initialization changes the semantic state from uninitialized to initialized.


### TRANS-MOVE-001 — Move

**judgment:** `Σ[p↦Owned(v)] ⟶ move(p) ⟶ Σ[p↦Moved], q↦Owned(v)`

**semantic requirement:** A successful move transfers ownership responsibility and invalidates the source ownership state.


### TRANS-COPY-001 — Copy

**judgment:** `Σ[p↦Copyable(v)] ⟶ copy(p) ⟶ Σ[p↦Copyable(v)], q↦Independent(v)`

**semantic requirement:** Copying creates an independent value and does not transfer ownership.


### TRANS-BORROW-001 — Create shared capability

**judgment:** `Σ ⟶ borrow_shared(p) ⟶ Σ,κShared`

**semantic requirement:** A shared capability is created without transferring ownership.


### TRANS-BORROW-002 — Create mutable capability

**judgment:** `Σ ⟶ borrow_mut(p) ⟶ Σ,κMut`

**semantic requirement:** A mutable capability is created only when exclusive mutable access is permitted.


### TRANS-BORROW-003 — Reborrow

**judgment:** `Σ,κ1 ⟶ reborrow(κ1,mode) ⟶ Σ,κ2`

**semantic requirement:** A derived capability does not transfer underlying ownership.


### TRANS-ASSIGN-001 — Assignment success

**judgment:** `Σ ⟶ rhs_eval(v) ⟶ assign(d,v) ⟶ Σ\old(d)+v`

**semantic requirement:** The previous owned destination value is replaced only after successful RHS evaluation.


### TRANS-ASSIGN-002 — Assignment failure

**judgment:** `Σ ⟶ rhs_eval_fail ⟶ Σ`

**semantic requirement:** A failed RHS evaluation does not replace the destination value.


### TRANS-DESTROY-001 — Destroy

**judgment:** `Σ[p↦Owned(v)] ⟶ destroy(p) ⟶ Σ[p↦Consumed]`

**semantic requirement:** Destruction consumes the applicable ownership/destruction responsibility exactly as specified.


### TRANS-DEFER-001 — Register defer

**judgment:** `Σ ⟶ defer_register(S,path) ⟶ Σ,Δ+obligation`

**semantic requirement:** Registration creates a future semantic use bound to the enclosing scope.


### TRANS-DEFER-002 — Execute defer

**judgment:** `Σ,Δ ⟶ scope_exit(S) ⟶ execute(ΔS) ⟶ destroy_remaining(S)`

**semantic requirement:** Deferred obligations execute before automatic destruction of the scope’s owned locals, in the specified order.


### TRANS-RET-001 — Return

**judgment:** `Σ ⟶ eval(return_expr) ⟶ cleanup(exited_scopes) ⟶ return(v)`

**semantic requirement:** Return evaluates its expression before deferred blocks and destruction associated with exited scopes.


### TRANS-FAIL-001 — Failure

**judgment:** `Σ ⟶ fail(f) ⟶ cleanup/failure semantics`

**semantic requirement:** A failed operation produces no successful result and cannot be treated as having completed normally.


### TRANS-THREAD-001 — Thread spawn

**judgment:** `Σ ⟶ spawn(args) ⟶ Σc`

**semantic requirement:** Cross-context ownership transfer creates exactly one destination ownership responsibility.


### TRANS-THREAD-002 — Thread join

**judgment:** `Σc ⟶ join(h) ⟶ Σ`

**semantic requirement:** Successful join establishes the required happens-after relationship.


### TRANS-SYNC-001 — Mutex unlock/lock

**judgment:** `unlock(m) →hb→ subsequent_successful_lock(m)`

**semantic requirement:** The specified synchronization relation establishes ordering and visibility.


### TRANS-FFI-001 — FFI call

**judgment:** `Σ ⟶ ffi_call(contract,args) ⟶ Σ′`

**semantic requirement:** An FFI call is valid only when ABI representation and explicit semantic contract obligations hold.


### TRANS-UNSAFE-001 — Unsafe region

**judgment:** `Σ ⟶ unsafe_enter ⟶ unsafe_op* ⟶ unsafe_exit`

**semantic requirement:** Unsafe context changes the permitted operation set but does not automatically create ownership, initialization, lifetime, or managed capability facts.


### VALID-001 — Semantic IR validity

**judgment:** `IR ⊢ V_type ∧ V_init ∧ V_owner ∧ V_borrow ∧ V_lifetime ∧ V_destroy ∧ V_control ∧ V_concurrent ∧ V_unsafe ∧ V_ffi`

**semantic requirement:** Validated semantic IR preserves the combined language safety model.


## 6. Per-subsystem formal schema

This section gives the formal interface for every primary taxonomy category. It deliberately derives operation names from the traceability artifact; it is not a new source-language design.

### PARSE

- Classified rules: **214**

- Judgment anchors: `parse_ok`

- IR operations: `aggregate.partial_state`, `arith.failure`, `assign.semantic`, `borrow.semantic`, `bounds.check`, `call.semantic`, `control.semantic`, `copy.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `initialization.semantic`, `library.contract`, `lifetime.semantic`, `move.semantic`, `nullability.check`, `parse.lexical`, `parse.node`, `runtime.semantic`, `unsafe.semantic`

- Primary validators: `parser`


### TYPE

- Classified rules: **209**

- Judgment anchors: `type_compatible`, `type_of`

- IR operations: `arith.failure`, `assign.semantic`, `borrow.semantic`, `bounds.check`, `call.semantic`, `concurrency.semantic`, `control.semantic`, `copy.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `generic.instantiate`, `initialization.semantic`, `library.contract`, `lifetime.semantic`, `move.semantic`, `nullability.check`, `parse.lexical`, `runtime.semantic`, `type.assert`, `type.instantiate`, `unsafe.semantic`, `value.convert`

- Primary validators: `type_checker`

- Upstream categories represented by explicit dependencies: PARSE


### OWNERSHIP

- Classified rules: **57**

- Judgment anchors: `move_valid`, `owns`

- IR operations: `aggregate.partial_state`, `assign.semantic`, `borrow.semantic`, `bounds.check`, `call.semantic`, `control.semantic`, `copy.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `generic.instantiate`, `initialization.semantic`, `library.contract`, `lifetime.semantic`, `move.semantic`, `nullability.check`, `ownership.copy`, `ownership.invalidate`, `ownership.transfer`, `runtime.semantic`, `unsafe.semantic`

- Primary validators: `ownership_checker`

- Upstream categories represented by explicit dependencies: INITIALIZATION, TYPE


### BORROW

- Classified rules: **94**

- Judgment anchors: `borrow_compatible`, `capability_valid`

- IR operations: `aggregate.partial_state`, `borrow.create`, `borrow.end`, `borrow.reborrow`, `borrow.semantic`, `bounds.check`, `call.semantic`, `concurrency.semantic`, `control.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `initialization.semantic`, `library.contract`, `lifetime.semantic`, `move.semantic`, `runtime.semantic`, `unsafe.semantic`

- Primary validators: `borrow_checker`

- Upstream categories represented by explicit dependencies: OWNERSHIP, TYPE


### LIFETIME

- Classified rules: **10**

- Judgment anchors: `lifetime_valid`, `outlives`

- IR operations: `borrow.semantic`, `call.semantic`, `control.semantic`, `ffi.abi.semantic`, `lifetime.begin`, `lifetime.constrain`, `lifetime.end`, `lifetime.semantic`, `runtime.semantic`

- Primary validators: `lifetime_checker`

- Upstream categories represented by explicit dependencies: BORROW, OWNERSHIP


### INITIALIZATION

- Classified rules: **24**

- Judgment anchors: `initialized`, `read_valid`

- IR operations: `call.semantic`, `control.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `init.consume`, `init.create`, `init.reinitialize`, `initialization.semantic`, `runtime.semantic`, `unsafe.semantic`

- Primary validators: `initialization_checker`

- Upstream categories represented by explicit dependencies: CONTROL_FLOW, PARSE, TYPE


### DESTRUCTION

- Classified rules: **22**

- Judgment anchors: `cleanup_valid`, `destruction_valid`

- IR operations: `aggregate.partial_state`, `borrow.semantic`, `call.semantic`, `cleanup.enter`, `cleanup.execute`, `control.semantic`, `destroy`, `destruction.semantic`, `initialization.semantic`, `lifetime.semantic`, `move.semantic`, `runtime.semantic`

- Primary validators: `destruction_analysis`

- Upstream categories represented by explicit dependencies: CONTROL_FLOW, INITIALIZATION, OWNERSHIP


### CONTROL FLOW

- Classified rules: **23**

- Judgment anchors: `join_valid`, `path_valid`

- IR operations: `borrow.semantic`, `bounds.check`, `call.semantic`, `cf.branch`, `cf.jump`, `cf.loop`, `cf.return`, `control.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `initialization.semantic`, `lifetime.semantic`, `unsafe.semantic`

- Primary validators: `control_flow_analysis`

- Upstream categories represented by explicit dependencies: PARSE, TYPE


### CONCURRENCY

- Classified rules: **84**

- Judgment anchors: `cross_context_valid`, `happens_before`, `race_free`

- IR operations: `atomic`, `borrow.semantic`, `bounds.check`, `call.semantic`, `concurrency.semantic`, `control.semantic`, `copy.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `initialization.semantic`, `library.contract`, `lifetime.semantic`, `move.semantic`, `runtime.semantic`, `sync.acquire`, `sync.release`, `thread.join`, `thread.spawn`, `unsafe.semantic`

- Primary validators: `concurrency_checker`

- Upstream categories represented by explicit dependencies: BORROW, LIFETIME, OWNERSHIP


### UNSAFE

- Classified rules: **115**

- Judgment anchors: `unsafe_context_valid`, `unsafe_obligation_satisfied`

- IR operations: `arith.failure`, `borrow.semantic`, `bounds.check`, `call.semantic`, `concurrency.semantic`, `control.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `initialization.semantic`, `library.contract`, `lifetime.semantic`, `nullability.check`, `parse.lexical`, `proof.obligation`, `raw.access`, `runtime.semantic`, `unsafe.enter`, `unsafe.exit`, `unsafe.semantic`

- Primary validators: `unsafe_checker`

- Upstream categories represented by explicit dependencies: TYPE


### ABI

- Classified rules: **45**

- Judgment anchors: `abi_valid`, `representation_valid`

- IR operations: `abi.call`, `abi.lower`, `borrow.semantic`, `bounds.check`, `call.semantic`, `concurrency.semantic`, `control.semantic`, `ffi.abi.semantic`, `ffi.declare`, `lifetime.semantic`, `nullability.check`, `runtime.semantic`

- Primary validators: `ffi`

- Upstream categories represented by explicit dependencies: TYPE, UNSAFE


### RUNTIME

- Classified rules: **162**

- Judgment anchors: `failure_semantics_valid`, `runtime_effect_valid`

- IR operations: `arith.failure`, `borrow.semantic`, `bounds.check`, `call.semantic`, `concurrency.semantic`, `control.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `generic.instantiate`, `initialization.semantic`, `library.contract`, `lifetime.semantic`, `move.semantic`, `nullability.check`, `parse.lexical`, `runtime.check`, `runtime.effect`, `runtime.fail`, `runtime.semantic`, `unsafe.semantic`

- Primary validators: `runtime`

- Upstream categories represented by explicit dependencies: TYPE


### LIBRARY

- Classified rules: **171**

- Judgment anchors: `library_contract_valid`

- IR operations: `aggregate.partial_state`, `assign.semantic`, `borrow.semantic`, `bounds.check`, `call.semantic`, `concurrency.semantic`, `control.semantic`, `copy.semantic`, `destruction.semantic`, `ffi.abi.semantic`, `generic.instantiate`, `initialization.semantic`, `library.call`, `library.contract`, `lifetime.semantic`, `move.semantic`, `parse.lexical`, `runtime.semantic`, `unsafe.semantic`

- Primary validators: `library`

- Upstream categories represented by explicit dependencies: TYPE


## 7. Canonical semantic transition families

### Evaluation
- Judgment: ``Γ;Σ ⊢ e ⇓ (v,Σ1)``
- Meaning: Expression evaluation produces a value and a resulting semantic state.

### Move
- Judgment: ``Γ;Σ ⊢ move(p) ⇓ (v,Σ1)``
- Meaning: The destination receives the owned value and the source becomes moved according to ownership/initialization rules.

### Copy
- Judgment: ``Γ;Σ ⊢ copy(v) ⇓ (v1,Σ1)``
- Meaning: An independent value is produced only when the type permits copying.

### Borrow
- Judgment: ``Γ;Σ ⊢ borrow(p,m) ⇓ (κ,Σ1)``
- Meaning: A shared or mutable capability is created subject to ownership, mutability, aliasing, and lifetime constraints.

### Reborrow
- Judgment: ``Γ;Σ ⊢ reborrow(κ,m) ⇓ (κ1,Σ1)``
- Meaning: A derived capability is created without transferring ownership of the underlying referent.

### Assign
- Judgment: ``Γ;Σ ⊢ assign(p,e) ⇓ (·,Σ1)``
- Meaning: Assignment preserves initialization, ownership, borrowing, lifetime, and destruction invariants.

### Destroy
- Judgment: ``Γ;Σ ⊢ destroy(p) ⇓ (·,Σ1)``
- Meaning: Destruction consumes the applicable owned initialized value exactly once.

### ScopeExit
- Judgment: ``Γ;Σ ⊢ exit(scope) ⇓ Σ1``
- Meaning: Deferred blocks and owned local destruction occur according to scope semantics.

### Return
- Judgment: ``Γ;Σ ⊢ return(e) ⇓ result(Σ1)``
- Meaning: Return evaluates the result before exiting scopes and applies ownership/borrow/lifetime rules.

### Failure
- Judgment: ``Γ;Σ ⊢ fail(e) ⇓ failure(Σ1)``
- Meaning: Failure preserves required destruction and semantic-state guarantees.

### Sync
- Judgment: ``Γ;Σ ⊢ sync(op) ⇓ Σ1``
- Meaning: Synchronization adds required ordering/visibility without creating a separate ownership calculus.

### FFI
- Judgment: ``Γ;Σ ⊢ ffi_call(f,args) ⇓ (r,Σ1)``
- Meaning: ABI representation and explicit semantic contract jointly govern the boundary.

### Unsafe
- Judgment: ``Γ;Σ ⊢ unsafe(op) ⇓ Σ1``
- Meaning: Unsafe operations remain outside automatic guarantees except where an explicit contract restores required invariants.

## 8. Global invariants

- An initialized storage position represents a valid value of its type.

- An uninitialized storage position is not readable, borrowable, movable, or destructible as an initialized value.

- An owned value has one ownership responsibility.

- A moved source cannot subsequently be used as the owner of the transferred value.

- A borrow cannot outlive its referent.

- Conflicting mutable and shared access cannot coexist where the specification prohibits the overlap.

- Destruction responsibility is discharged exactly once.

- Relocation cannot silently invalidate a live borrow.

- Synchronization does not itself extend object lifetime.

- Unsafe entry does not implicitly establish ownership, initialization, lifetime, or managed capability.

- ABI compatibility does not itself establish CobaltC ownership or lifetime semantics.

- Subsystem composition preserves existing guarantees unless a more specific normative rule explicitly says otherwise.

## 9. Compiler-independent Semantic IR schema

The semantic IR is a graph of validated semantic entities. It must preserve the information needed to establish or carry the judgments above; it does not encode machine instructions.

### 9.1 Top-level entity

```json
{
  "program": {
    "id": "...",
    "language": "CobaltC",
    "edition": "1.0",
    "publication": "1.0.3",
    "modules": [],
    "types": [],
    "functions": [],
    "contracts": [],
    "semantic_rules": [],
    "diagnostics": []
  }
}
```

### 9.2 Function body

```json
{
  "id": "fn:...",
  "signature": {},
  "entry": "bb0",
  "blocks": [],
  "locals": [],
  "lifetimes": [],
  "capabilities": [],
  "cleanup_scopes": [],
  "contracts": []
}
```

### 9.3 Basic block

```json
{
  "id": "bb0",
  "operations": [],
  "terminator": {}
}
```

### 9.4 Semantic operation

Each operation contains a stable ID, source span, operation kind, operands, semantic effects, preconditions, postconditions, and rule references.

```json
{
  "id": "op42",
  "kind": "borrow.create",
  "operands": [],
  "source_span": {},
  "preconditions": [],
  "postconditions": [],
  "effects": {
    "ownership": [],
    "initialization": [],
    "borrows": [],
    "lifetimes": [],
    "destruction": []
  },
  "rule_refs": ["BORROW-001"]
}
```

## 10. Complete 1,230-rule traceability model

Every classified rule has a stable rule ID and an explicit semantic anchor. The canonical machine-readable mapping is supplied separately as JSON and CSV.

### Category counts

- PARSE: 214

- TYPE: 209

- OWNERSHIP: 57

- BORROW: 94

- LIFETIME: 10

- INITIALIZATION: 24

- DESTRUCTION: 22

- CONTROL_FLOW: 23

- CONCURRENCY: 84

- UNSAFE: 115

- ABI: 45

- RUNTIME: 162

- LIBRARY: 171

- **Total: 1230**

### Status counts

- NORMATIVE: 1171

- INFORMATIVE: 52

- UNSPECIFIED: 7

## 11. Complete dependency graph

The graph contains **1230 nodes** and **1505 explicit dependency edges**.

### Category-level dependency summary

- `BORROW → CONCURRENCY`: 84 rule dependencies

- `BORROW → LIFETIME`: 10 rule dependencies

- `CONTROL_FLOW → DESTRUCTION`: 22 rule dependencies

- `CONTROL_FLOW → INITIALIZATION`: 24 rule dependencies

- `INITIALIZATION → DESTRUCTION`: 22 rule dependencies

- `INITIALIZATION → OWNERSHIP`: 57 rule dependencies

- `LIFETIME → CONCURRENCY`: 84 rule dependencies

- `OWNERSHIP → BORROW`: 94 rule dependencies

- `OWNERSHIP → CONCURRENCY`: 84 rule dependencies

- `OWNERSHIP → DESTRUCTION`: 22 rule dependencies

- `OWNERSHIP → LIFETIME`: 10 rule dependencies

- `PARSE → CONTROL_FLOW`: 23 rule dependencies

- `PARSE → INITIALIZATION`: 24 rule dependencies

- `PARSE → TYPE`: 209 rule dependencies

- `TYPE → ABI`: 45 rule dependencies

- `TYPE → BORROW`: 94 rule dependencies

- `TYPE → CONTROL_FLOW`: 23 rule dependencies

- `TYPE → INITIALIZATION`: 24 rule dependencies

- `TYPE → LIBRARY`: 171 rule dependencies

- `TYPE → OWNERSHIP`: 57 rule dependencies

- `TYPE → RUNTIME`: 162 rule dependencies

- `TYPE → UNSAFE`: 115 rule dependencies

- `UNSAFE → ABI`: 45 rule dependencies

### Exact rule-level graph

The exact edge set is in `CobaltC_1.0.3_Rule_Dependency_Graph.json` and `.dot`.

### Strongly connected components
No multi-node dependency cycles were detected in the explicit `depends_on` graph.

## 12. Subsystem ordering derived from dependencies

- `PARSE → TYPE` (209 explicit rule edges)

- `TYPE → CONTROL_FLOW` (23 explicit rule edges)

- `CONTROL_FLOW → INITIALIZATION` (24 explicit rule edges)

- `INITIALIZATION → OWNERSHIP` (57 explicit rule edges)

- `OWNERSHIP → BORROW` (94 explicit rule edges)

- `BORROW → LIFETIME` (10 explicit rule edges)

- `OWNERSHIP → CONCURRENCY` (84 explicit rule edges)

- `BORROW → CONCURRENCY` (84 explicit rule edges)

- `LIFETIME → CONCURRENCY` (84 explicit rule edges)

- `TYPE → UNSAFE` (115 explicit rule edges)

- `TYPE → ABI` (45 explicit rule edges)

This is dependency evidence, not a mandated compiler-pass sequence.

## 13. Validation model

A semantic program is valid when the required source and semantic judgments are derivable and all applicable invariants hold. An invalid semantic state produces a diagnostic rather than being silently lowered as though it were valid. The exact ordering and presentation of multiple diagnostics remains implementation-defined unless otherwise specified.

## 14. Boundary conditions intentionally preserved

- Illustrative storage APIs remain semantic examples unless separately required by the specification.

- ABI representation and CobaltC semantic contracts remain distinct.

- Unsafe code does not automatically establish missing semantic facts.

- Implementation-defined and unspecified behavior remain explicitly marked rather than normalized into one assumed result.

- Conservative analysis is permitted only where the specification permits it.

## 15. Deliverables

- `CobaltC_1.0.3_Formal_Semantic_Specification_v3.md` — consolidated semantic specification.

- `CobaltC_1.0.3_Formal_Inference_and_Transition_Rules_v3.json` — normalized formal rules.

- `CobaltC_1.0.3_Rule_to_IR_Traceability_v3.json` — all 1,230 rule mappings.

- `CobaltC_1.0.3_Rule_Dependency_Graph.json` — exact rule-level dependency graph.

- `CobaltC_1.0.3_Rule_Dependency_Graph.dot` — Graphviz representation.

# CobaltC 1.0.3 — AI Compiler Implementation Handoff v1

## Purpose

This document is a handoff package for an AI coding agent that will implement the CobaltC semantic compiler.

The requested end product is **not an executable compiler backend**. The compiler's primary externally observable product is an **Explainable Semantic IR (ESIR) JSON file**.

The implementation target is:

```text
CobaltC source
  -> lexer
  -> parser
  -> AST / normalized HIR
  -> name resolution
  -> type analysis
  -> place / storage analysis
  -> definite-initialization analysis
  -> ownership / move / copy analysis
  -> borrow / capability analysis
  -> lifetime analysis
  -> control-flow analysis
  -> destruction / defer analysis
  -> unsafe analysis
  -> concurrency / synchronization analysis
  -> FFI / ABI analysis
  -> global semantic validation
  -> Explainable Semantic IR JSON
```

The AI must implement the language according to the supplied CobaltC 1.0.3 specification. It must not substitute assumptions from C, C++, Rust, LLVM, or another language merely because a concept looks similar.

---

# 1. Instructions to the implementing AI

You are acting as the implementation engineer for the CobaltC 1.0.3 semantic compiler.

Your primary goals, in priority order, are:

1. semantic correctness relative to CobaltC 1.0.3;
2. explainability and traceability;
3. deterministic compiler behavior and ESIR output;
4. precise structured diagnostics;
5. complete semantic coverage;
6. maintainable implementation.

Do **not** optimize for native code generation. No executable backend is required.

You must produce a compiler that can take CobaltC source and emit a machine-readable ESIR JSON file.

Your implementation language may be chosen by you, but **Python is the recommended first implementation language** because the project is currently focused on semantics, traceability, analysis, and explainability rather than native-code performance. If you choose another language, document why before implementation.

---

# 2. Authority rules

Treat the supplied files according to this hierarchy:

1. **CobaltC 1.0.3 specification** — authoritative normative source.
2. **Formal Semantic Specification v3** — derived formalization.
3. **Formal Inference and Transition Rules v3** — derived semantic rule families.
4. **Rule-to-IR Traceability v3** — mapping between source-derived rules and semantic/IR concepts.
5. **Rule Dependency Graph** — dependency information.
6. **ESIR Specification and ESIR JSON Schema** — external output contract.
7. **Compiler Implementation Specification v1** — implementation organization and phase contracts.
8. **This handoff document** — execution instructions for implementing the compiler.

If artifacts disagree, the AI must not silently choose whichever is easier to implement. It must identify the conflict, determine whether it is a genuine contradiction or merely a difference in abstraction, and preserve the CobaltC 1.0.3 semantics.

Derived artifacts must never silently override the 1.0.3 specification.

---

# 3. Files to provide to the implementing AI

## 3.1 Mandatory — provide all of these

### A. CobaltC language specification

**File:**

`Appendix_06(10).html`

Role:

- authoritative CobaltC 1.0.3 language specification;
- grammar;
- normative semantic rules;
- ownership;
- borrowing;
- lifetime;
- initialization;
- destruction;
- control flow;
- concurrency;
- unsafe behavior;
- FFI/ABI;
- standard/library requirements.

This is the most important file.

### B. Formal semantic specification

**File:**

`CobaltC_1.0.3_Formal_Semantic_Specification_v3.md`

Role:

- formal semantic state;
- environments;
- judgments;
- ownership model;
- capability model;
- lifetime model;
- destruction model;
- concurrency model;
- FFI model;
- unsafe model;
- semantic invariants.

Use this as the implementation-oriented formalization of the language specification.

### C. Formal rule families

**File:**

`CobaltC_1.0.3_Formal_Inference_and_Transition_Rules_v3.json`

Role:

- normalized implementation-facing semantic rule families;
- static judgments;
- state-transition rules;
- validation rules.

Important: these are derived rule families, not a replacement for the original specification.

### D. Rule-to-IR traceability

**File:**

`CobaltC_1.0.3_Rule_to_IR_Traceability_v3.json`

Role:

- maps the classified CobaltC rule records to semantic anchors, judgments, state, IR operations, validators, invariants, and dependencies;
- provides the bridge between source-language requirements and ESIR construction.

The current mapping covers **1,230 classified rule records**.

### E. Rule dependency graph

**File:**

`CobaltC_1.0.3_Rule_Dependency_Graph.json`

Role:

- rule dependency relationships;
- ordering/context information;
- semantic dependency analysis.

### F. Explainable Semantic IR specification

**File:**

`CobaltC_1.0.3_Explainable_Semantic_IR_Specification_v1.md`

Role:

- defines what the compiler's semantic output means;
- defines explainability requirements;
- defines ESIR entities, operations, effects, facts, diagnostics, and provenance.

### G. Explainable Semantic IR schema

**File:**

`CobaltC_1.0.3_Explainable_Semantic_IR.schema.json`

Role:

- machine-readable validation contract for the emitted ESIR JSON;
- required fields and structures.

### H. ESIR example

**File:**

`CobaltC_1.0.3_Explainable_Semantic_IR_Example.json`

Role:

- concrete example of expected ESIR structure;
- useful as a serialization and explanation reference.

### I. Compiler implementation specification

**File:**

`CobaltC_1.0.3_ESIR_Compiler_Implementation_Specification_v1.md`

Role:

- phase-by-phase compiler architecture;
- inputs and outputs;
- semantic state;
- diagnostics;
- dependencies;
- ESIR responsibilities;
- acceptance criteria.
\n### J. Machine-readable compiler phase contracts\n\n**File:**\n\n`CobaltC_1.0.3_ESIR_Compiler_Phase_Contracts_v1.json`\n\nRole:\n\n- machine-readable phase order;\n- phase dependencies;\n- required semantic state;\n- produced outputs;\n- ESIR responsibilities.\n\n### K. Source-rule classification\n\n**File:**\n\n`CobaltC_1.0.3_Rule_Classification.json`\n\nRole:\n\n- machine-readable classification of the 1,230 source-derived rule records;\n- category, status, compiler-phase, invariant, dependency, and traceability information.\n\nThe AI should use this as an implementation index, while treating the original 1.0.3 specification as the normative authority.\n\n### L. Classification / authority brief\n\n**File:**\n\n`Pasted markdown.md`\n\nRole:\n\n- project classification and authority instructions used to produce the rule classification;\n- interpretive constraints for the supplied specification.\n\nThis should be supplied because it documents the intended authority and classification methodology behind the machine-readable rule corpus.\n
---

# 4. Optional files

The following can be supplied for convenience but are not strictly required if the mandatory files are present:

`CobaltC_1.0.3_Formal_Inference_and_Transition_Rules_v3.json` — already mandatory; do not omit it.

Older/historical versions of semantic artifacts should **not** be treated as current authority unless specifically requested.

Additional generated artifacts such as CSV exports or visualization files are secondary and should not drive implementation decisions.

---

# 5. First task: inspect before coding

Before writing compiler code, inspect every mandatory input.

Create an internal implementation inventory containing:

```text
file
version
purpose
authority level
major sections
machine-readable structures
semantic domains
rule identifiers
cross-references
```

Do not begin by guessing the grammar or semantic model.

The AI must first establish:

1. what the source specification says;
2. what the formal model represents;
3. what the ESIR schema requires;
4. how rules map to semantic operations;
5. what dependencies exist between analyses.

---

# 6. Do not rewrite the language specification

The AI is implementing CobaltC.

It is not authorized to:

- simplify away difficult rules;
- replace the CobaltC ownership model with Rust ownership;
- replace CobaltC syntax with Rust syntax;
- interpret CobaltC as C/C++;
- assume LLVM semantics;
- invent unspecified language behavior and call it normative;
- silently change the meaning of the specification to make implementation easier.

When the specification is silent, distinguish:

```text
specified
derived from existing specified rules
implementation-defined / environment-dependent
unspecified
not yet determined
```

Never present an implementation choice as a language rule.

---

# 7. Compiler boundary

The compiler stops here:

```text
source -> ESIR JSON
```

There is no requirement to emit:

```text
machine code
assembly
object files
executables
LLVM IR
WASM
JIT code
```

A later consumer may use ESIR for visualization, diagnostics, verification, static analysis, auditing, or another transformation.

---

# 8. Required compiler phases

Implement the phases in this semantic order, subject to justified parallelization:

```text
P0  source/module discovery
P1  lexing
P2  parsing
P3  AST normalization
P4  name resolution
P5  type analysis
P6  place/storage/object analysis
P7  definite initialization
P8  ownership/move/copy
P9  borrow/capability
P10 lifetime
P11 control-flow/path structure
P12 destruction/defer/cleanup
P13 unsafe
P14 concurrency/synchronization
P15 FFI/ABI contracts
P16 global semantic validation
P17 ESIR construction/emission
```

The phase numbers are implementation identifiers, not language syntax.

Independent analyses may run in parallel after their dependencies are satisfied, provided the result remains deterministic and semantically equivalent.

---

# 9. Core semantic state that must survive

The implementation must preserve enough information to reconstruct all required ESIR explanations.

At minimum, preserve:

```text
source spans
symbols
types
places
values
object identity
initialization state
ownership state
capabilities
lifetimes
cleanup/defer regions
unsafe regions
control-flow blocks and edges
concurrency relations
FFI contracts
diagnostics
rule references
semantic facts
semantic operations
```

A semantic fact must not disappear merely because a conventional optimizing compiler would normally consider it redundant.

---

# 10. Formal semantic backbone

Use the formal semantic model as the conceptual backbone:

```text
Σ = (ρ, μ, Λ, Δ)
```

where:

```text
ρ = binding environment
μ = store/storage state
Λ = lifetime environment
Δ = deferred-destruction environment
```

Use the static environment conceptually represented by Γ for:

```text
symbols
types
bindings
places
ownership
capabilities
lifetimes
initialization
mutability
unsafe context
generic substitutions
control context
contracts
```

Do not assume that these exact structures must be Python classes with these exact names. They are semantic requirements, not an imposed programming architecture.

---

# 11. Required semantic distinctions

The implementation must preserve these distinctions:

```text
value != place
ownership != borrowing
move != copy
initialization != ownership
capability != ownership
lifetime != scope
unsafe context != semantic invalidation of all other rules
source syntax != normalized semantic representation
FFI contract != host-platform assumption
```

Any place where these concepts are merged internally must still permit the required distinction to be recovered for validation and ESIR output.

---

# 12. Ownership and move/copy implementation

Implement ownership as explicit semantic state.

At minimum support the conceptual states:

```text
Owned
Moved
PartiallyMoved
Unowned / non-owning
```

For moves:

```text
Γ ⊢ move(p) ⇒ moved(p), v:T
```

For copies:

```text
Γ ⊢ copy(p) ⇒ v1:T, v2:T
```

The implementation must not treat every assignment or value transfer as an ownership move.

The exact ownership conditions must be taken from CobaltC 1.0.3.

Partial moves of aggregates must be represented whenever required.

---

# 13. Initialization implementation

Track initialization per relevant place and path.

At minimum distinguish:

```text
Uninitialized
Initialized
PartiallyInitialized
Consumed
```

Reads must be checked against initialization state.

The compiler must not fabricate initialization facts after parsing or after entering an unsafe region.

---

# 14. Borrow/capability implementation

Represent managed borrowing as capabilities.

A capability conceptually contains:

```text
referent
access mode
lifetime
origin
status
```

Access modes include:

```text
SharedRead
MutableExclusive
```

Implement:

```text
borrow_shared
borrow_mut
reborrow
suspend_capability
resume_capability
end_borrow
```

The implementation must track:

- which place is borrowed;
- which capability caused the borrow;
- whether accesses overlap;
- whether access is shared or exclusive;
- the capability's lifetime;
- capability invalidation/expiration.

Do not import Rust's exact borrow-checker behavior unless the CobaltC specification independently requires the same result.

---

# 15. Lifetime implementation

Lifetimes must be explicit internal semantic entities.

For every managed capability, track a validity interval.

The central invariant is conceptually:

```text
lifetime(capability) is contained within lifetime(referent)
```

subject to the exact CobaltC rules.

Detect and diagnose:

- borrow beyond referent lifetime;
- use after lifetime expiration;
- invalid lifetime extension;
- invalid capability expiration.

---

# 16. Control-flow implementation

Construct a control-flow graph rich enough for path-sensitive semantic checking.

Represent at least:

```text
jump
branch
switch
return
break
continue
fail
unreachable
```

All dataflow analyses that depend on execution paths must operate over the CFG or an equivalent semantic representation.

Do not assume that straight-line AST traversal is sufficient.

---

# 17. Destruction and defer

Represent destruction explicitly.

Represent deferred work explicitly:

```text
defer_register
defer_execute
destroy
```

Preserve registration and execution ordering required by CobaltC.

Cleanup must be represented on all relevant exits, including normal return and failure paths where the language requires it.

Do not encode cleanup only as an implementation side effect invisible to ESIR.

---

# 18. Unsafe analysis

Represent unsafe regions explicitly:

```text
unsafe_enter
unsafe_exit
```

Represent raw operations distinctly:

```text
raw_load
raw_store
```

Entering unsafe context does **not**, merely by itself:

- transfer ownership;
- initialize storage;
- extend a lifetime;
- create a managed capability;
- erase unrelated CobaltC invariants.

Unsafe permissions must be derived from the actual language specification.

---

# 19. Concurrency

Represent concurrency as semantic relations, not simply as function-call names.

The formal conceptual state is:

```text
Σc = (Σ, Ctx, O, HB, Sync)
```

Track, as required:

```text
thread/task identity
ownership transfer
shared access
synchronization
happens-before
mutex/lock state
atomic operations
join relationships
```

The compiler must apply the CobaltC concurrency rules, not a generic language-independent thread model.

---

# 20. FFI and ABI

Represent FFI/ABI contracts explicitly.

Where applicable, preserve:

```text
ABI identity/profile
argument representation
return representation
ownership transfer
borrow requirements
lifetime requirements
nullability
destruction responsibility
failure behavior
concurrency requirements
safety requirements
```

Do not infer platform-specific ABI behavior merely because a host operating system or C compiler commonly uses it.

---

# 21. Explainable Semantic IR

The primary external output is:

```text
program.esir.json
```

The output must conform to:

`CobaltC_1.0.3_Explainable_Semantic_IR.schema.json`

The top-level model includes:

```text
format
compilation
source_files
modules
types
symbols
functions
contracts
rules
diagnostics
summary
```

Every semantically significant operation should make it possible to answer:

1. What happened?
2. Where did it originate?
3. What semantic entities did it read/change?
4. Why was it permitted or required?
5. What semantic facts/invariants resulted?

Operations should carry, where applicable:

```text
id
kind
source_span
operands
results
attributes
preconditions
postconditions
effects
rule_refs
facts_established
facts_invalidated
```

---

# 22. Rule traceability

Use both levels of rule references.

### Formal rule families

Examples:

```text
STATIC-TYPE-001
STATIC-INIT-001
STATIC-OWN-001
STATIC-BORROW-001
STATIC-LIFE-001
TRANS-MOVE-001
TRANS-COPY-001
TRANS-BORROW-001
TRANS-DESTROY-001
TRANS-DEFER-001
TRANS-THREAD-001
TRANS-SYNC-001
TRANS-FFI-001
TRANS-UNSAFE-001
VALID-001
```

### Source-derived specification rules

The current traceability artifact covers 1,230 classified rule records.

Where a source-derived rule maps directly to an operation, prefer including that reference.

It is acceptable and useful to include both:

```text
source rule reference
+
formal semantic rule reference
```

This enables:

```text
ESIR operation
  -> semantic rule
  -> source-derived rule
  -> source location
```

---

# 23. Diagnostics

Diagnostics must be structured.

Recommended information:

```text
diagnostic_id
severity
code
message
source_span
related_spans
phase
rule_refs
entities
notes
```

Examples include:

```text
unresolved_name
type_error
uninitialized_read
use_after_move
invalid_move
borrow_conflict
invalid_reborrow
lifetime_violation
invalid_destruction
unsafe_requirement
concurrency_violation
ffi_contract_violation
```

The actual taxonomy must remain subordinate to CobaltC 1.0.3.

---

# 24. Errors and partial ESIR

The compiler may emit ESIR despite errors when useful.

If it does, it must clearly indicate invalid or unresolved portions.

Never fabricate a valid:

```text
type
ownership
initialization
borrow
lifetime
ABI
```

fact merely to complete an output file.

Unknown information must be represented as unknown/unresolved/error state rather than as a guessed valid fact.

---

# 25. Determinism

The compiler should produce deterministic output.

Given identical:

```text
source
compiler version
language version
semantic configuration
```

the ESIR should be deterministic.

Do not depend on:

- hash-map iteration order;
- memory addresses;
- process IDs;
- random IDs;
- host timestamps in semantic content.

Use stable identifier schemes.

Recommended namespaces:

```text
file_*
module_*
token_*
ast_*
symbol_*
type_*
place_*
value_*
cap_*
life_*
cleanup_*
unsafe_*
contract_*
block_*
op_*
diag_*
```

---

# 26. Implementation process

Do the implementation in these stages.

## Stage 1 — repository and infrastructure

Create the repository/module structure.

Implement:

- source manager;
- diagnostics framework;
- stable ID generator;
- source-span system;
- compiler driver;
- JSON infrastructure;
- test harness.

Do not build the full semantic checker yet.

## Stage 2 — lexer

Implement the CobaltC lexical grammar from the 1.0.3 specification.

Every token must retain source location.

Create positive and negative lexer tests.

## Stage 3 — parser

Implement the grammar.

Create AST node types with source spans.

Create parser recovery where useful without turning invalid syntax into valid semantic constructs.

## Stage 4 — normalization

Create the internal normalized representation used by semantic analysis.

Preserve source provenance.

## Stage 5 — symbol resolution

Implement:

- module symbols;
- lexical scopes;
- declarations;
- references;
- duplicate checking;
- unresolved-name diagnostics.

## Stage 6 — type analysis

Implement the actual CobaltC type system.

Create stable type identities.

Resolve generic/type substitutions as required by the language.

## Stage 7 — places and initialization

Implement:

- place identities;
- field/index paths;
- object identity;
- mutability;
- initialization dataflow.

## Stage 8 — ownership

Implement:

- owner state;
- moves;
- copies;
- partial moves;
- ownership diagnostics.

## Stage 9 — borrowing/lifetimes

Implement:

- capabilities;
- shared/exclusive access;
- reborrows;
- capability status;
- lifetime constraints;
- lifetime expiration.

## Stage 10 — CFG/cleanup

Implement:

- control-flow graph;
- returns/failure;
- destruction;
- defer;
- cleanup paths.

## Stage 11 — unsafe/concurrency/FFI

Implement the remaining semantic subsystems.

## Stage 12 — ESIR

Make the ESIR builder consume the semantic graph rather than merely translating AST nodes.

## Stage 13 — validation

Validate emitted ESIR against the JSON schema.

Add rule-reference integrity checks.

Add internal consistency checks:

```text
every referenced symbol exists
every referenced type exists
every capability refers to valid entities
every lifetime reference resolves
every operation ID is unique
every rule reference exists in the rule corpus
every diagnostic entity reference resolves
```

---

# 27. Testing strategy

Build tests at every stage.

## Lexer tests

```text
source -> tokens
```

## Parser tests

```text
tokens -> AST
```

## Resolution tests

```text
AST -> symbols/references
```

## Type tests

```text
typed valid program
typed invalid program
```

## Semantic state-transition tests

For every important semantic operation:

```text
before
+
operation
=
after
```

At minimum cover:

```text
init
move
copy
borrow
reborrow
assign
destroy
defer
return
fail
thread spawn
thread join
synchronization
FFI call
unsafe operation
```

## Negative tests

Every important normative restriction should have at least one negative test.

## ESIR golden tests

Use:

```text
input.cc
expected.esir.json
```

The expected file must be reviewed semantically, not merely byte-compared blindly.

---

# 28. First working milestone

The first runnable compiler should support:

```text
CobaltC source
 -> lexer
 -> parser
 -> name resolution
 -> type analysis
 -> basic places
 -> basic initialization
 -> basic ownership
 -> ESIR JSON
```

Then extend the semantic core to:

```text
borrow
 -> lifetime
 -> control flow
 -> cleanup/defer
 -> unsafe
 -> concurrency
 -> FFI
 -> global validation
```

Do not wait until the entire language is complete before producing ESIR. Build a vertical slice and expand it.

---

# 29. Required deliverables from the implementing AI

The AI should eventually return:

### Compiler source

A complete source tree that can be built/run from a clean environment.

### Build/run instructions

Exact commands.

### ESIR schema validation

The compiler must emit JSON conforming to the supplied schema.

### Test suite

Automated tests covering all implemented phases.

### Example programs

Small CobaltC source examples for each major semantic subsystem.

### Example ESIR

At least one complete valid ESIR output and several invalid-program examples containing diagnostics.

### Traceability report

A report showing which source-derived rule classes and formal rule families are implemented, tested, partially implemented, or not yet implemented.

### Known limitations

Explicitly list anything not implemented.

Do not claim full CobaltC support until the evidence supports that claim.

---

# 30. Acceptance test for the AI

The implementation is considered successful only when the AI can demonstrate an end-to-end run:

```text
example.cobalt
    |
    v
CobaltC compiler
    |
    v
example.esir.json
```

and the ESIR can be inspected to see:

```text
source locations
symbols
types
places
values
initialization
ownership
borrows/capabilities
lifetimes
control flow
cleanup/defer
unsafe context
concurrency
FFI contracts
rule references
facts established
facts invalidated
diagnostics
```

for the language features actually supported by the implementation.

---

# 31. Important implementation discipline

When a difficult rule is encountered:

1. locate the exact 1.0.3 source rule;
2. locate its classification/traceability record;
3. locate the corresponding formal rule family if one exists;
4. determine the semantic state required;
5. implement the smallest semantic mechanism that faithfully represents the rule;
6. add positive and negative tests;
7. expose the resulting fact/transition in ESIR;
8. document any genuinely unresolved ambiguity.

Do not solve specification problems by silently changing the specification.

---

# 32. What the AI should do when the specification appears ambiguous

Do not immediately ask the user to restate the entire language.

Instead:

1. identify the exact ambiguous passage;
2. identify the dependent rules;
3. determine whether the ambiguity actually affects implementation;
4. check the formal semantic artifacts and traceability;
5. determine whether one interpretation is already constrained elsewhere in the 1.0.3 specification;
6. implement the interpretation best supported by the supplied materials;
7. record the ambiguity explicitly;
8. ask for user clarification only when the ambiguity prevents a defensible implementation.

---

# 33. Recommended project philosophy

Treat the compiler as a **semantic compiler** rather than a conventional optimizing compiler.

Its job is to make the semantics explicit.

The central invariant is:

```text
No semantically significant fact may disappear before ESIR emission
unless it is provably irrelevant to all required CobaltC 1.0.3
acceptance, rejection, explanation, and observable-semantic obligations.
```

The implementation language is secondary.

The internal data structures are secondary.

Optimization is secondary.

The primary product is a correct, inspectable semantic model.

---

# 34. Final instruction to the implementing AI

Start by reading all mandatory files.

Then produce:

1. an implementation inventory;
2. a semantic dependency map;
3. a repository structure;
4. the compiler skeleton;
5. the lexer;
6. the parser;
7. the semantic analysis phases;
8. the ESIR builder and serializer;
9. tests and fixtures;
10. a traceability/coverage report.

Do not stop at a design document.

The objective is to produce an actual runnable compiler implementation whose canonical output is:

```text
*.esir.json
```

The compiler should be built incrementally, with each completed phase tested before the next major semantic layer is added.

---

# 35. File checklist for the human operator

When handing the project to another AI, provide this complete set:

- [ ] `Appendix_06(10).html`
- [ ] `CobaltC_1.0.3_Formal_Semantic_Specification_v3.md`
- [ ] `CobaltC_1.0.3_Formal_Inference_and_Transition_Rules_v3.json`
- [ ] `CobaltC_1.0.3_Rule_to_IR_Traceability_v3.json`
- [ ] `CobaltC_1.0.3_Rule_Dependency_Graph.json`
- [ ] `CobaltC_1.0.3_Explainable_Semantic_IR_Specification_v1.md`
- [ ] `CobaltC_1.0.3_Explainable_Semantic_IR.schema.json`
- [ ] `CobaltC_1.0.3_Explainable_Semantic_IR_Example.json`
- [ ] `CobaltC_1.0.3_ESIR_Compiler_Implementation_Specification_v1.md`
- [ ] `CobaltC_1.0.3_ESIR_Compiler_Phase_Contracts_v1.json`
- [ ] `CobaltC_1.0.3_Rule_Classification.json`
- [ ] `Pasted markdown.md`
- [ ] **this handoff document**

If convenient, provide all of the above together with the implementation package ZIP.

---

# 36. Final expected architecture

```text
                CobaltC 1.0.3 Specification
                         |
                         v
               Formal Semantic Model
                         |
                         v
                    Rule System
                         |
                         v
CobaltC source --> Semantic Compiler
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
     Symbols          Types          Semantic State
                                         |
                  +----------------------+------------------+
                  |          |         |        |           |
                  v          v         v        v           v
               Ownership   Borrow   Lifetime  Cleanup   Concurrency
                  |          |         |        |           |
                  +----------+---------+--------+-----------+
                                         |
                                         v
                                  Global Validation
                                         |
                                         v
                              Explainable Semantic IR
                                         |
                                         v
                              `program.esir.json`
```

The intended result is a compiler that can explain not merely that a program is accepted or rejected, but **why each semantically significant operation is valid, invalid, or conditionally constrained according to CobaltC 1.0.3**.

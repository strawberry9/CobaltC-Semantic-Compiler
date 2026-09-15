# CobaltC 1.0.3 — Explainable Semantic IR Compiler Implementation Specification v1

**Status:** derived implementation artifact  
**Language authority:** CobaltC Programming Language Specification 1.0.3  
**Purpose:** define an implementation blueprint for a compiler whose primary externally observable output is an Explainable Semantic IR (ESIR) JSON file rather than executable code.

---

## 1. Scope

The implementation covered by this specification performs:

```text
CobaltC source
  → source/module discovery
  → lexing
  → parsing
  → AST normalization
  → name resolution
  → type analysis
  → place / storage analysis
  → definite-initialization analysis
  → ownership / move / copy analysis
  → borrow / capability analysis
  → lifetime analysis
  → control-flow analysis
  → destruction / defer analysis
  → unsafe-context analysis
  → concurrency / synchronization analysis
  → FFI / ABI contract analysis
  → semantic validation
  → ESIR construction
  → ESIR JSON emission
```

The implementation does **not** require:

- code generation;
- machine-code lowering;
- LLVM IR;
- native object files;
- register allocation;
- instruction selection;
- executable linking.

The compiler may contain additional internal representations, caches, indexes, or analyses, provided they preserve the semantic information required by the CobaltC specification and the ESIR contract.

---

## 2. Authority hierarchy

The implementation SHALL treat the following hierarchy as authoritative:

1. **CobaltC Programming Language Specification 1.0.3** — normative language authority.
2. **CobaltC 1.0.3 formal semantic model** — derived semantic formalization.
3. **Normalized formal inference / transition rules** — derived implementation-facing rule families.
4. **Rule-to-IR traceability** — mapping between source-derived rule records and ESIR concepts.
5. **ESIR specification** — external output contract.
6. **This document** — implementation organization and phase contracts.

A derived artifact must not silently override the language specification.

The compiler SHALL distinguish:

- source-derived facts;
- derived semantic facts;
- implementation metadata;
- diagnostics.

Implementation convenience SHALL NOT be emitted as though it were a CobaltC semantic requirement.

---

## 3. Design objective

The compiler's central output is an **explainable semantic model of the program**.

For every semantically significant operation, the ESIR should make it possible to answer:

1. What happened?
2. Where did it originate in source?
3. Which semantic entities were read or changed?
4. Which rule(s) justify or constrain it?
5. Which facts and invariants resulted?

The compiler should therefore preserve semantic information even where a conventional optimizing IR would normally discard it.

---

## 4. Implementation architecture

A conforming implementation SHOULD use a layered architecture:

```text
+------------------------------+
| Source / Module Loader        |
+------------------------------+
              |
+------------------------------+
| Lexer                         |
+------------------------------+
              |
+------------------------------+
| Parser                        |
+------------------------------+
              |
+------------------------------+
| AST + Source Map              |
+------------------------------+
              |
+------------------------------+
| Name / Symbol Resolution      |
+------------------------------+
              |
+------------------------------+
| Type + Generic Analysis       |
+------------------------------+
              |
+------------------------------+
| Place / Initialization        |
+------------------------------+
              |
+------------------------------+
| Ownership / Borrow / Lifetime |
+------------------------------+
              |
+------------------------------+
| Control / Cleanup             |
+------------------------------+
              |
+------------------------------+
| Unsafe / Concurrency / FFI    |
+------------------------------+
              |
+------------------------------+
| Global Semantic Validator     |
+------------------------------+
              |
+------------------------------+
| ESIR Builder                  |
+------------------------------+
              |
+------------------------------+
| Deterministic JSON Writer     |
+------------------------------+
```

The architecture may be changed without changing semantics. Phase boundaries in this specification are semantic contracts, not required class names or process boundaries.

---

# 5. Core implementation data model

## 5.1 Stable identifiers

The compiler SHALL assign stable identifiers to semantically significant entities.

Recommended identifier namespaces:

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

Identifiers MUST be unique within an ESIR document.

For deterministic builds, the compiler SHOULD derive IDs from deterministic encounter order or another deterministic scheme rather than process addresses or hash-map iteration order.

---

## 5.2 Source spans

Every source-derived entity and operation SHOULD retain a source span whenever one exists.

Conceptual structure:

```json
{
  "file": "example.cc",
  "start_line": 4,
  "start_col": 9,
  "end_line": 4,
  "end_col": 14
}
```

A source span is explanatory provenance, not semantic identity.

For synthesized constructs, the compiler SHOULD retain an origin span or an explicit `synthetic: true` marker.

---

## 5.3 Internal semantic state

The semantic model is represented conceptually as:

```text
Σ = (ρ, μ, Λ, Δ)
```

where:

```text
ρ = binding environment
μ = store / storage-object state
Λ = lifetime environment
Δ = deferred-destruction obligations
```

Static analysis state SHALL additionally track, as applicable:

```text
Γ = {
  symbols,
  types,
  bindings,
  places,
  ownership,
  capabilities,
  lifetimes,
  initialization,
  mutability,
  unsafe context,
  generic substitutions,
  control context,
  contracts
}
```

The implementation may partition these structures differently, but all information required by the semantic model must remain recoverable.

---

# 6. Phase contracts

Each phase is defined by:

- required inputs;
- produced outputs;
- state consumed;
- state established;
- source information preserved;
- diagnostics;
- ESIR obligations;
- predecessor dependencies.

---

## PHASE P0 — Source and module discovery

### Input

- compiler invocation;
- source files;
- configured module roots;
- implementation-defined file system inputs allowed by the language environment.

### Output

- ordered source-file set;
- module identity map;
- source text buffers;
- source hashes;
- module dependency declarations.

### Must establish

- every source file has a stable file ID;
- every source location can be mapped to a file;
- module identities are unambiguous;
- source ordering is deterministic.

### Must preserve

- complete source text or equivalent offset-addressable representation;
- line/column mapping;
- file identity.

### Diagnostics

- missing source;
- unreadable source;
- duplicate module identity;
- malformed module path metadata where applicable.

### ESIR

Populate:

```text
source_files
modules
compilation.source hashes
```

### Depends on

None.

---

## PHASE P1 — Lexing

### Input

- source text;
- file/source-map metadata.

### Output

- token stream;
- token source spans;
- lexical diagnostics.

### Responsibilities

The lexer SHALL:

- recognize the lexical forms required by the 1.0.3 specification;
- preserve exact source spans;
- distinguish tokens required by the grammar;
- report lexical errors without inventing semantic meaning.

### Must NOT do

- name resolution;
- type inference;
- ownership analysis;
- borrow analysis;
- lifetime analysis.

### ESIR

Normally no semantic operations are emitted solely for tokens, but token provenance SHALL remain available to AST/source mapping.

### Dependencies

P0.

---

## PHASE P2 — Parsing

### Input

- token stream.

### Output

- parsed AST;
- syntax diagnostics;
- source spans for AST nodes.

### Responsibilities

The parser SHALL establish grammatical structure only.

It SHALL NOT treat an otherwise parseable construct as semantically valid merely because grammar permits it.

### Error handling

The implementation SHOULD use recovery sufficient to report multiple syntax errors in one compilation, while preventing recovered placeholder nodes from being mistaken for valid semantic entities.

### ESIR

AST nodes are not required to be emitted as final ESIR operations. Their IDs and spans SHALL remain available as provenance for later entities and operations.

### Dependencies

P1.

---

## PHASE P3 — AST normalization

### Input

- parsed AST.

### Output

- canonical internal AST / HIR suitable for semantic analysis;
- explicit source constructs for syntactic sugar where useful;
- normalized control-flow constructs;
- preserved origin spans.

### Responsibilities

Normalization MAY:

- desugar syntax;
- make implicit syntax explicit;
- canonicalize equivalent syntactic forms.

Normalization MUST NOT change CobaltC semantic meaning.

### Required property

Every normalized construct that corresponds to source syntax SHALL retain an origin mapping back to source AST nodes/spans.

### Dependencies

P2.

---

## PHASE P4 — Name resolution and symbol graph

### Input

- normalized AST;
- module graph.

### Output

- symbol table;
- lexical scopes;
- declaration-to-symbol mapping;
- reference-to-symbol mapping;
- overload/generic candidates where the specification requires them;
- unresolved-name diagnostics.

### Must establish

For each successfully resolved reference:

```text
reference → symbol_id
symbol_id → declaration span
symbol_id → declared type / declaration form
```

### Diagnostics

- unresolved names;
- illegal duplicate declarations;
- invalid scope access;
- ambiguity, where specified.

### ESIR

Populate:

```text
symbols
modules
symbol references in operations
```

### Dependencies

P3.

---

## PHASE P5 — Type and generic analysis

### Input

- resolved AST/HIR;
- symbols;
- type declarations;
- generic declarations/substitutions.

### Output

- canonical type entities;
- expression types;
- type compatibility results;
- generic instantiations;
- type diagnostics.

### Must establish

For accepted expressions:

```text
Γ ⊢ e : T
```

For type-relevant operations, the compiler SHALL retain:

- source type;
- resulting type;
- conversion/coercion where specified;
- generic substitutions where applicable.

### ESIR

Populate:

```text
types
value type facts
operation type attributes
type rule references
```

### Diagnostics

- incompatible types;
- invalid conversions;
- invalid generic use;
- violated type constraints.

### Dependencies

P4.

---

## PHASE P6 — Place / storage / object identity analysis

### Input

- typed HIR.

### Output

- place graph;
- storage categories;
- object identity relations;
- field/index paths;
- mutability classification.

### Purpose

A **place** is a semantic storage position, distinct from a produced value.

Typical relations:

```text
place p
place p.field
place p[index]
place *capability
```

### Must establish

Every operation that reads, writes, initializes, moves, borrows, or destroys storage SHALL be associated with a place where the language semantics require one.

### ESIR

Populate:

```text
places
object_identity facts
field/index path metadata
```

### Dependencies

P5.

---

## PHASE P7 — Definite initialization analysis

### Input

- typed HIR;
- place graph;
- control-flow graph skeleton.

### Output

- initialization state per program point;
- initialization transfer facts;
- uninitialized-use diagnostics;
- partial-initialization state.

### State domain

At minimum:

```text
Uninitialized
Initialized
PartiallyInitialized
Consumed
```

### Required properties

The analysis SHALL respect path sensitivity sufficient to determine whether a place is initialized at each use.

The compiler SHALL distinguish:

```text
uninitialized
initialized
partially initialized
consumed/destroyed
```

### ESIR

Emit or annotate:

```text
init
read
assign
destroy
```

with `preconditions`, `postconditions`, and initialization facts.

### Dependencies

P6.

---

## PHASE P8 — Ownership, move, copy, and partial-move analysis

### Input

- initialization state;
- places;
- types;
- control-flow graph.

### Output

- ownership state;
- move graph;
- copy decisions;
- partial-move paths;
- ownership diagnostics.

### Core states

```text
Owned
Moved
PartiallyMoved
Unowned / non-owning
```

### Required distinctions

The compiler SHALL distinguish:

```text
move != copy
ownership != borrow capability
value production != ownership transfer
```

For a move:

```text
Γ ⊢ move(p) ⇒ moved(p), v:T
```

For a copy:

```text
Γ ⊢ copy(p) ⇒ v1:T, v2:T
```

subject to the type and source rules.

### Partial moves

Aggregate subpaths MAY become independently moved while the remaining paths remain valid, subject to the source specification.

### ESIR

Primary operations:

```text
move
copy
assign
```

Facts:

```text
ownership
object_identity
initialization
```

### Diagnostics

- use after move;
- illegal move;
- illegal copy;
- conflicting partial move;
- ownership violation.

### Dependencies

P7, P5.

---

## PHASE P9 — Borrow / capability analysis

### Input

- ownership state;
- typed places;
- control-flow graph;
- lifetime candidates.

### Output

- capability entities;
- borrow relations;
- shared/exclusive access constraints;
- reborrow relations;
- capability status transitions;
- borrow diagnostics.

### Capability model

A managed capability records:

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

### Required invariants

At minimum:

```text
shared-read capabilities may coexist subject to language rules;
mutable-exclusive access conflicts with incompatible overlapping access;
a capability cannot outlive its referent;
a move cannot invalidate a still-valid managed capability without violating the specification.
```

The last condition MUST be evaluated against the actual 1.0.3 rules, not an imported Rust model.

### Reborrows

Reborrow relationships SHALL record the capability from which the new capability was derived.

### ESIR

Primary operations:

```text
borrow_shared
borrow_mut
reborrow
suspend_capability
resume_capability
end_borrow
```

### Diagnostics

- conflicting borrows;
- invalid reborrow;
- expired capability;
- illegal access through capability;
- lifetime mismatch discoverable here or delegated to P10.

### Dependencies

P8, P6.

---

## PHASE P10 — Lifetime analysis

### Input

- borrow/capability graph;
- control-flow graph;
- object/place lifetime information.

### Output

- lifetime entities;
- capability validity intervals;
- lifetime containment relations;
- expiration points;
- lifetime diagnostics.

### Required invariant

For every managed capability:

```text
lifetime(capability) ⊆ lifetime(referent)
```

unless the CobaltC specification explicitly defines a different mechanism.

### Lifetime identity

Lifetimes SHALL be explicit internal entities even if they are omitted from source syntax.

### ESIR

Populate:

```text
lifetimes
capability lifetime links
lifetime-established/invalidated facts
```

### Diagnostics

- borrow outlives referent;
- use after lifetime end;
- illegal lifetime extension;
- invalid capability expiration.

### Dependencies

P9, P7, P8.

---

## PHASE P11 — Control-flow and path semantics

### Input

- typed HIR;
- semantic constraints from prior phases.

### Output

- canonical control-flow graph;
- basic blocks;
- branch conditions;
- loop structure;
- return/break/continue/failure edges;
- path predicates.

### Responsibilities

The CFG SHALL make all semantically relevant execution paths explicit enough for later dataflow analyses.

Terminators include, as applicable:

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

### ESIR

Populate:

```text
functions.blocks
terminators
control-flow operations
branch predicates
```

### Dependencies

P3, P5.

---

## PHASE P12 — Destruction and deferred-destruction analysis

### Input

- CFG;
- initialization state;
- ownership state;
- lifetime state;
- language destruction rules;
- defer registrations.

### Output

- cleanup regions;
- destruction obligations;
- defer registration/execution order;
- cleanup edges;
- destruction diagnostics.

### Required semantics

The compiler SHALL distinguish:

```text
normal destruction
explicit destruction where specified
deferred destruction
failure/unwinding cleanup where specified
```

Deferred actions SHALL preserve the source-defined registration/execution order.

### ESIR

Primary operations:

```text
defer_register
defer_execute
destroy
```

Cleanup regions SHALL expose:

- registration order;
- execution order;
- guarded cleanup paths;
- affected places.

### Dependencies

P7, P8, P10, P11.

---

## PHASE P13 — Unsafe-region and raw-access analysis

### Input

- typed/ownership/borrow/lifetime state;
- CFG.

### Output

- unsafe-region graph;
- unsafe operation classification;
- unsafe obligations;
- unsafe diagnostics.

### Required property

Entering an unsafe region SHALL NOT by itself:

- transfer ownership;
- initialize storage;
- extend lifetimes;
- create managed capabilities;
- waive unrelated language rules.

Unsafe context changes which operations are permitted, not the meaning of all other invariants.

### ESIR

Primary operations:

```text
unsafe_enter
unsafe_exit
raw_load
raw_store
```

Each unsafe operation SHOULD identify:

- containing unsafe region;
- violated/assumed safety condition where relevant;
- rule references;
- affected place/value/capability.

### Dependencies

P8, P9, P10, P11.

---

## PHASE P14 — Concurrency and synchronization analysis

### Input

- ownership/capability/lifetime state;
- CFG;
- thread/task operations;
- synchronization operations;
- language concurrency rules.

### Output

- concurrency context;
- thread/task relationships;
- synchronization edges;
- happens-before relations;
- concurrency obligations;
- diagnostics.

### Conceptual state

```text
Σc = (Σ, Ctx, O, HB, Sync)
```

where:

```text
Ctx = concurrency context
O   = concurrency ownership/operation relations
HB  = happens-before relations
Sync = synchronization facts
```

### ESIR

Primary operations may include:

```text
thread_spawn
thread_join
mutex_lock
mutex_unlock
atomic
```

The implementation SHALL record semantic synchronization relations rather than merely textual call names.

### Diagnostics

- invalid shared access;
- ownership transfer incompatible with concurrency rules;
- invalid synchronization;
- invalid thread lifetime;
- data-race conditions where the specification makes them statically diagnosable.

### Dependencies

P8, P9, P10, P11.

---

## PHASE P15 — FFI and ABI contract analysis

### Input

- resolved symbols;
- types;
- ownership/capability/lifetime information;
- declared/external contracts;
- target ABI profile only to the extent permitted by the CobaltC specification.

### Output

- ABI/FFI contract entities;
- argument/return contracts;
- representation checks;
- ownership/lifetime obligations;
- FFI diagnostics.

### Contract fields

Where applicable:

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

### Important separation

The compiler SHALL NOT infer that a particular ABI, calling convention, layout, or machine representation exists solely because a host platform commonly uses it. It SHALL use only properties established by the language specification or an explicit implementation ABI contract.

### ESIR

Primary operation:

```text
ffi_call
```

with contract references.

### Dependencies

P5, P8, P9, P10.

---

## PHASE P16 — Global semantic validation and rule closure

### Input

All prior semantic state.

### Output

- final semantic validity;
- cross-subsystem diagnostics;
- invariant validation results;
- complete rule-reference closure;
- finalized ESIR semantic entities and operations.

### Validation layers

At minimum:

```text
V_type
∧ V_init
∧ V_owner
∧ V_borrow
∧ V_lifetime
∧ V_destroy
∧ V_control
∧ V_concurrent
∧ V_unsafe
∧ V_ffi
```

A program is semantically valid only if all required applicable constraints hold.

### Rule closure

For each accepted operation, the compiler SHOULD be able to trace:

```text
operation
 → fact / invariant
 → semantic rule family
 → source-derived rule record(s)
 → source location(s)
```

### Diagnostics

This phase may emit cross-cutting diagnostics whose cause is visible only after multiple analyses are combined.

### Dependencies

P5–P15 as applicable.

---

## PHASE P17 — ESIR construction and emission

### Input

- finalized semantic graph;
- diagnostics;
- source/module metadata;
- rule traceability data.

### Output

A single deterministic JSON ESIR file.

### Required top-level sections

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

### Required semantic coverage

The emitted ESIR SHALL preserve, where applicable:

- source spans;
- resolved symbols;
- types;
- places;
- values;
- object identity;
- initialization;
- ownership;
- capabilities;
- lifetimes;
- cleanup/defer;
- control-flow;
- concurrency;
- unsafe context;
- FFI/ABI contracts;
- rule references;
- semantic facts;
- diagnostics.

### Determinism

Given identical source, compiler configuration, language version, and implementation semantic configuration, emission SHOULD be byte-for-byte deterministic.

If a timestamp or build host is included, it SHALL be clearly classified as non-semantic compilation metadata.

### Dependencies

P0–P16.

---

# 7. Internal representation requirements

The compiler may use AST, HIR, CFG, SSA, dataflow lattices, constraint graphs, or other internal forms. These are implementation choices.

The following semantic objects, however, MUST be reconstructible before final ESIR emission:

```text
SourceSpan
Symbol
Type
Place
Value
ObjectIdentity
OwnershipState
InitializationState
Capability
Lifetime
CleanupRegion
UnsafeRegion
Contract
BasicBlock / ControlEdge
SemanticOperation
Diagnostic
RuleReference
SemanticFact
```

The compiler SHOULD avoid encoding semantic facts only in ephemeral local variables that cannot later be exported to ESIR.

---

# 8. Semantic operation construction

Every ESIR operation SHOULD have the following conceptual shape:

```json
{
  "id": "op_42",
  "kind": "move",
  "source_span": {...},
  "operands": [...],
  "results": [...],
  "attributes": {...},
  "preconditions": [...],
  "postconditions": [...],
  "effects": [...],
  "rule_refs": ["OWN-...", "TRANS-MOVE-001"],
  "facts_established": [...],
  "facts_invalidated": [...]
}
```

The exact schema is governed by the ESIR schema artifact.

### Operation principles

An operation must not:

- silently perform a semantic action that is absent from its effects;
- silently erase an ownership or lifetime transition;
- claim a rule reference unsupported by the traceability data;
- merge distinct semantic actions when doing so makes explanation impossible.

A compound implementation step may be represented by multiple ESIR operations.

---

# 9. Diagnostics model

Diagnostics SHALL be structured rather than free-form only.

Recommended fields:

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

Severity should distinguish at least:

```text
error
warning
note
```

The compiler SHOULD attach both:

- the rule that was violated;
- the semantic entity/state responsible for the violation.

Examples:

```text
use_after_move
uninitialized_read
borrow_conflict
lifetime_violation
invalid_assignment
invalid_destruction
unsafe_requirement
concurrency_violation
ffi_contract_violation
```

The exact diagnostic taxonomy remains subordinate to the CobaltC specification.

---

# 10. Error handling and partial ESIR

A compilation containing semantic errors MAY still emit an ESIR file when doing so is safe and useful.

Such an ESIR SHALL:

- set compilation/summary validity fields accordingly;
- include diagnostics;
- mark unresolved or invalid entities explicitly;
- avoid representing guessed semantic facts as established facts.

The compiler SHALL NOT fabricate a valid ownership, lifetime, type, or ABI fact merely to complete an output file.

Recommended states:

```text
complete_valid
complete_invalid
partial_invalid
syntax_only
```

where only the states actually implemented by the compiler need be exposed.

---

# 11. Rule-reference strategy

The compiler has two complementary rule-reference layers.

## 11.1 Derived semantic rule families

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

These explain the formal semantic mechanism.

## 11.2 Source-derived specification rules

The traceability artifact contains one mapping record for each of the 1,230 classified specification rule records.

ESIR SHALL prefer source-derived rule references when a direct mapping exists.

Formal rule family references MAY be included alongside them.

Conceptually:

```text
rule_refs = [
  "TYPE-001",
  "STATIC-TYPE-001"
]
```

This makes explanation bidirectional:

```text
ESIR operation
 → formal semantic rule
 → source-derived specification rule
```

---

# 12. Dependency ordering

The minimum acyclic phase dependency order is:

```text
P0
 ↓
P1
 ↓
P2
 ↓
P3
 ↓
P4
 ↓
P5
 ↓
P6
 ↓
P7
 ↓
P8
 ↓
P9
 ↓
P10
 ↓
P11
 ↓
P12
 ↓
P13
 ↓
P14
 ↓
P15
 ↓
P16
 ↓
P17
```

Important cross-dependencies:

```text
P5 → P7
P5 → P8
P6 → P7
P6 → P8
P8 → P9
P8 → P10
P9 → P10
P7 → P12
P8 → P12
P10 → P12
P11 → P12
P8 → P13
P9 → P13
P10 → P13
P11 → P13
P8 → P14
P9 → P14
P10 → P14
P11 → P14
P5 → P15
P8 → P15
P9 → P15
P10 → P15
P5–P15 → P16
P0–P16 → P17
```

The implementation may run independent analyses in parallel provided dependency ordering is respected and results are deterministic.

---

# 13. Implementation strategy for the first compiler

The first compiler implementation SHOULD favor:

1. correctness;
2. traceability;
3. deterministic output;
4. clear diagnostics;
5. complete semantic coverage;

over:

- optimization;
- compile-time minimization;
- backend generation;
- aggressive canonicalization.

A practical first implementation can use a conventional host language and ordinary compiler data structures. The language used to implement the compiler is not prescribed by this specification.

---

# 14. Recommended compiler-internal modules

A maintainable first implementation can be divided as:

```text
cobalt/
  source/
  lexer/
  parser/
  ast/
  symbols/
  types/
  places/
  init/
  ownership/
  borrow/
  lifetime/
  control/
  cleanup/
  unsafe/
  concurrency/
  ffi/
  rules/
  diagnostics/
  esir/
  driver/
```

Suggested responsibilities:

```text
source/        file identities and source maps
lexer/         lexical tokenization
parser/        grammar and AST creation
ast/           normalized syntax representation
symbols/       scopes and name resolution
types/         type identity and type checking
places/        storage/place graph
init/          definite initialization
ownership/     move/copy/ownership states
borrow/        capabilities and reborrows
lifetime/      lifetime constraints and expiration
control/       CFG and path-sensitive execution structure
cleanup/       destruction and defer
unsafe/        unsafe regions and raw operations
concurrency/   thread/synchronization semantics
ffi/           FFI/ABI contracts
rules/         source-rule + formal-rule references
diagnostics/   structured errors
esir/          semantic graph and JSON serialization
driver/        phase orchestration
```

The exact package/module names are not normative.

---

# 15. First implementation milestone

A useful first milestone is:

```text
source
 → lexer
 → parser
 → name resolution
 → type analysis
 → place/init/ownership/borrow/lifetime/control analysis
 → ESIR
```

with:

- source spans;
- stable IDs;
- structured diagnostics;
- rule references;
- deterministic JSON.

Then add:

```text
cleanup/defer
unsafe
concurrency
FFI/ABI
```

without changing the existing ESIR identity model.

This sequencing is an implementation recommendation, not a change to language semantics.

---

# 16. Acceptance criteria

An implementation satisfies this specification when, for supported source constructs:

### Syntax

- lexical and parsing behavior follows the 1.0.3 source specification;
- syntax errors are located and represented.

### Resolution

- identifiers resolve to stable symbols;
- symbol provenance is retained.

### Types

- expressions and relevant declarations have semantic types;
- invalid type relationships produce diagnostics.

### Initialization

- reads are checked against initialization state;
- partial initialization is represented where required.

### Ownership

- move and copy are distinguished;
- ownership transitions are explicit;
- partial moves are represented where required.

### Borrowing

- capabilities are explicit;
- access modes are explicit;
- conflicting accesses are diagnosed;
- reborrows are represented.

### Lifetimes

- capability/reference lifetimes are explicit;
- invalid lifetime relationships are diagnosed.

### Control

- all relevant control paths are explicit in the CFG;
- return/failure/break/continue semantics are represented.

### Destruction

- destruction obligations are represented;
- deferred destruction order is preserved.

### Unsafe

- unsafe regions are represented;
- raw operations are distinguishable from managed capabilities.

### Concurrency

- concurrency operations and synchronization are represented;
- required ownership/lifetime/synchronization constraints are validated.

### FFI

- applicable contracts and ABI requirements are represented;
- invalid FFI interactions are diagnosed.

### Explainability

For every accepted semantic operation, the compiler can provide:

```text
source origin
+ semantic entities affected
+ preconditions
+ postconditions
+ effects
+ applicable rule references
+ established facts
+ invalidated facts
```

### Output

- ESIR conforms to the ESIR JSON schema;
- identifiers are internally consistent;
- references are resolvable;
- output is deterministic under deterministic inputs/configuration.

---

# 17. Conformance and testing strategy

The implementation SHOULD maintain tests at each semantic boundary.

## 17.1 Lexer tests

```text
source text → tokens → expected spans
```

## 17.2 Parser tests

```text
tokens → AST → expected structure
```

## 17.3 Resolution tests

```text
AST → symbol graph
```

## 17.4 Type tests

```text
AST/HIR → type facts / diagnostics
```

## 17.5 State-transition tests

For semantic operations:

```text
pre-state
+ operation
→ post-state
```

Test at least:

- initialization;
- move;
- copy;
- borrow;
- reborrow;
- assignment;
- destruction;
- defer;
- return;
- failure;
- thread/synchronization;
- FFI;
- unsafe operations.

## 17.6 ESIR golden tests

For each representative source program:

```text
source.cc
→ expected.esir.json
```

The golden output SHOULD be canonicalized so ordering differences unrelated to semantics do not create false failures.

## 17.7 Negative tests

Every normative restriction SHOULD have at least one negative test where practical.

---

# 18. Semantic preservation rule

An implementation may use any internal algorithm that is more permissive, more restrictive, differently structured, or differently represented than another implementation **only where the resulting accepted/rejected behavior and observable semantics remain those required by CobaltC 1.0.3**.

The implementation SHALL NOT replace a specification rule with an assumption imported from another language merely because the concepts appear similar.

In particular, the implementation SHALL NOT assume that CobaltC is semantically identical to C, C++, Rust, LLVM IR, or any other language/IR.

---

# 19. Minimal compiler-to-ESIR execution contract

The conceptual driver can be expressed as:

```text
compile(source):
    files       = discover_sources(source)
    tokens      = lex(files)
    ast         = parse(tokens)
    hir         = normalize(ast)

    symbols     = resolve_names(hir)
    types       = analyze_types(hir, symbols)

    places      = analyze_places(hir, types)
    cfg         = build_cfg(hir)

    init        = analyze_initialization(hir, places, cfg)
    ownership   = analyze_ownership(hir, types, places, init, cfg)
    borrows     = analyze_borrows(hir, ownership, places, cfg)
    lifetimes   = analyze_lifetimes(hir, borrows, ownership, cfg)

    cleanup     = analyze_cleanup(hir, init, ownership, lifetimes, cfg)
    unsafe      = analyze_unsafe(hir, ownership, borrows, lifetimes, cfg)
    concurrency = analyze_concurrency(hir, ownership, borrows, lifetimes, cfg)
    ffi         = analyze_ffi(hir, types, ownership, borrows, lifetimes)

    semantics   = validate_all(
                    files, symbols, types, places, cfg,
                    init, ownership, borrows, lifetimes,
                    cleanup, unsafe, concurrency, ffi
                  )

    esir        = build_esir(
                    files, symbols, types, places, cfg,
                    init, ownership, borrows, lifetimes,
                    cleanup, unsafe, concurrency, ffi,
                    semantics
                  )

    return write_esir(esir)
```

This pseudocode is an architectural model, not required source code.

---

# 20. Final compiler boundary

The compiler described here ends at:

```text
CobaltC source
        ↓
semantic compiler
        ↓
Explainable Semantic IR JSON
        ↓
consumer / analyzer / visualizer / verifier
```

A later consumer may use ESIR to:

- visualize ownership and lifetime;
- explain diagnostics;
- inspect semantic control flow;
- audit unsafe code;
- inspect concurrency relations;
- verify FFI contracts;
- perform secondary static analyses.

Such consumers are outside the compiler boundary defined here.

---

# 21. Required companion artifacts

The implementation SHOULD be accompanied by:

- the CobaltC 1.0.3 specification;
- the ESIR schema;
- the formal semantic specification;
- the formal rule-family JSON;
- the rule-to-IR traceability JSON;
- the rule dependency graph;
- ESIR golden examples.

Recommended package layout:

```text
CobaltC_Compiler_Implementation/
  specification/
    CobaltC_1.0.3/
  semantic/
    formal_semantic_specification_v3.md
    formal_rules_v3.json
    rule_to_ir_traceability_v3.json
    rule_dependency_graph.json
  esir/
    esir_specification_v1.md
    esir_schema.json
    examples/
  compiler/
    source/
    lexer/
    parser/
    ...
  tests/
    lexer/
    parser/
    semantic/
    esir_golden/
```

---

# 22. Bottom line

This specification is sufficient to define a concrete implementation architecture for the semantic compiler objective, while leaving implementation language, data-structure choices, analysis algorithms, and internal IRs unconstrained except where semantic preservation requires information to survive.

The central implementation invariant is:

```text
No semantically significant fact may disappear before ESIR emission
unless it is provably irrelevant to all required CobaltC 1.0.3
acceptance, rejection, explanation, and observable-semantics obligations.
```

The resulting compiler is therefore best understood as:

```text
a CobaltC semantic analyzer / semantic compiler
whose canonical product is an explainable semantic program model.
```

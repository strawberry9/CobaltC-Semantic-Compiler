# CobaltC 1.0.3 — Explainable Semantic IR Specification v1.0

**Status:** derived implementation artifact  
**Language:** CobaltC  
**Language publication:** 1.0.3  
**Purpose:** define the file emitted by a CobaltC semantic compiler whose primary output is an explainable semantic representation rather than executable machine code.

## 1. Purpose

The compiler targeted by this document transforms CobaltC source into a machine-readable **Explainable Semantic IR (ESIR)** file.

The ESIR is intended to make the compiler's semantic decisions inspectable. It therefore preserves information that a conventional lowering-oriented IR might discard, including:

- source locations;
- resolved symbols and types;
- storage places and object identity;
- initialization state;
- ownership state and ownership transfers;
- borrow capabilities and lifetimes;
- control-flow structure;
- destruction and deferred-destruction obligations;
- concurrency and synchronization relationships;
- unsafe regions and obligations;
- ABI/FFI contracts;
- semantic preconditions and postconditions;
- applicable CobaltC rule references;
- established and invalidated semantic facts;
- diagnostics and their source locations.

The ESIR does **not** prescribe a machine-code backend, optimizer, register allocator, object-file format, or executable runtime.

## 2. Authority and derivation

The authoritative language source remains the **CobaltC Programming Language Specification 1.0.3**.

This document formalizes the semantic representation needed for the explainable-IR objective. It is derived from the previously constructed formal semantic model, formal rule families, and rule-to-IR traceability artifacts.

The CobaltC specification permits implementation techniques and intermediate representations to vary provided the required acceptance/rejection behavior and observable semantics are preserved. Accordingly, this ESIR is an implementation-facing representation, not a replacement for the language specification.

## 3. Design principle

Every semantically significant IR operation should answer five questions:

1. **What happened?**
2. **Where did it come from in the source?**
3. **What semantic entities did it read or change?**
4. **Why was it permitted?**
5. **What semantic facts/invariants resulted?**

An operation therefore has, where applicable:

```text
operation
source_span
operands
results
preconditions
postconditions
effects
rule_refs
facts_established
facts_invalidated
```

## 4. Top-level file

An ESIR file is a JSON document with this conceptual structure:

```text
esir
 ├── format
 ├── compilation
 ├── source_files
 ├── modules
 ├── types
 ├── symbols
 ├── functions
 ├── contracts
 ├── rules
 ├── diagnostics
 └── summary
```

### 4.1 Format metadata

`format` identifies the ESIR format version independently of the CobaltC language version.

Required fields:

- `name`: `CobaltC-Explainable-Semantic-IR`
- `version`: semantic version of the ESIR format
- `language`: `CobaltC`
- `language_publication`: `1.0.3`

### 4.2 Compilation metadata

`compilation` records the provenance of the produced IR.

Recommended fields include:

- compiler identifier/version;
- compilation mode;
- source hashes;
- timestamp;
- whether the result is semantically valid;
- analysis/model version.

The compiler is not required to expose private implementation details.

## 5. Source mapping

Every source-derived semantic entity should have a `source_span` when a meaningful source location exists.

A source span contains:

```json
{
  "file": "example.cc",
  "start_line": 4,
  "start_col": 9,
  "end_line": 4,
  "end_col": 14
}
```

Source spans are explanatory provenance, not semantic identities.

## 6. Semantic entities

### 6.1 Types

A type entity identifies:

- stable type ID;
- CobaltC type;
- kind;
- type arguments where applicable;
- fields/parameters where applicable;
- copyability;
- destruction requirements;
- representation information where specified.

The representation section must not be used to invent ABI properties absent from the CobaltC specification.

### 6.2 Symbols

A symbol identifies a declaration after name resolution.

It should include:

- symbol ID;
- source name;
- kind;
- type;
- visibility/access information where applicable;
- associated place;
- source span.

### 6.3 Places

A **place** represents a semantically addressable storage position.

A place records:

- type;
- ownership state;
- initialization state;
- mutability;
- nullability where applicable;
- lifetime;
- object identity;
- parent place;
- field/index path.

Places are the primary objects for expressing ownership, initialization, borrowing, assignment, movement, and destruction.

### 6.4 Values

A value represents a produced semantic value.

It records:

- type;
- producing operation;
- originating place where applicable;
- capability where applicable;
- source span.

### 6.5 Capabilities

A capability represents managed access to a referent.

The core capability fields are:

- capability ID;
- referent place;
- access mode;
- lifetime;
- origin;
- status;
- derived-from capability where applicable.

The ESIR distinguishes capabilities from ownership.

### 6.6 Lifetimes

A lifetime records:

- lifetime ID;
- referent;
- parent lifetime where applicable;
- lower/upper semantic bounds;
- status.

A borrow lifetime must not exceed the lifetime of its referent.

### 6.7 Cleanup regions

Cleanup regions expose:

- scope nesting;
- deferred obligations;
- destruction responsibilities;
- cleanup ordering.

This allows return and failure paths to be explained without reducing cleanup to opaque backend code.

### 6.8 Unsafe regions

Unsafe regions expose:

- region ID;
- nesting;
- obligations;
- unsafe operations;
- source spans.

Entering an unsafe region does not, by itself, establish ownership, initialization, lifetime, or managed capability facts.

## 7. Control-flow representation

Each function contains basic blocks.

A block has:

```text
id
parameters
operations
terminator
source_span
```

Terminators include the semantic control-flow forms required by the formal model, such as:

- `jump`
- `branch`
- `switch`
- `return`
- `break`
- `continue`
- `fail`
- `unreachable`

The IR is therefore a control-flow graph rather than a flat sequence.

## 8. Semantic operations

An operation has a stable ID and an operation kind.

Core operation families include:

### Values and storage

- `const`
- `bind`
- `alloca`
- `init`
- `read`
- `write`
- `move`
- `copy`
- `assign`

### Places and aggregates

- `field`
- `index`
- `slice`
- `relocate`

### Borrowing and lifetimes

- `borrow_shared`
- `borrow_mut`
- `reborrow`
- `suspend_capability`
- `resume_capability`
- `end_borrow`

### Destruction and cleanup

- `defer_register`
- `defer_execute`
- `destroy`

### Runtime checks and failure

- `bounds_check`
- `null_check`
- `arithmetic_checked`
- `runtime_fail`

### Control and matching

- `match_test`

### Unsafe

- `unsafe_enter`
- `unsafe_exit`
- `raw_load`
- `raw_store`

### Concurrency

- `thread_spawn`
- `thread_join`
- `mutex_lock`
- `mutex_unlock`
- `atomic`

### ABI/FFI

- `ffi_call`

Implementations may introduce additional internal operation kinds provided they do not misrepresent CobaltC semantics.

## 9. Operation explanation contract

A semantically significant operation should use the following fields:

```json
{
  "id": "op17",
  "kind": "move",
  "source_span": {},
  "operands": ["place_x"],
  "results": ["value_y"],
  "preconditions": ["move_valid(place_x)"],
  "postconditions": ["place_x = Moved"],
  "effects": {
    "ownership": ["transfer(place_x,value_y)"],
    "initialization": ["place_x becomes consumed/moved as applicable"],
    "borrows": [],
    "lifetimes": [],
    "destruction": []
  },
  "rule_refs": ["STATIC-OWN-002", "TRANS-MOVE-001"],
  "facts_established": ["ownership(value_y)"],
  "facts_invalidated": ["ownership(place_x)"]
}
```

The exact wording of explanatory strings is not itself a new CobaltC semantic rule. The structured fields are the important machine-readable content.

## 10. Rule references

`rule_refs` connects an IR operation to the formal semantic rules used to justify it.

A rule reference should identify the normalized formal rule family, and may additionally identify one or more source specification rule IDs.

Example:

```json
{
  "formal_rule": "TRANS-MOVE-001",
  "source_rules": ["OWNERSHIP-..."]
}
```

Where a direct source-rule mapping is unavailable or not meaningful, the formal rule reference may stand alone.

The complete 1,230-rule mapping remains external to each IR file and is supplied by the traceability artifact.

## 11. Semantic facts

Facts are explicit statements about the semantic state.

Useful fact kinds include:

- `type`
- `ownership`
- `initialization`
- `mutability`
- `nullability`
- `capability`
- `lifetime`
- `alias`
- `object_identity`
- `unsafe_origin`
- `control`
- `concurrency`
- `destruction`
- `abi`

Facts may be established or invalidated by operations.

This makes the IR suitable for inspection by a human or another analysis system without requiring access to the compiler's private internal data structures.

## 12. Diagnostics

A diagnostic records an accepted or rejected semantic condition.

Recommended fields:

- diagnostic ID;
- severity;
- code;
- message;
- source span;
- phase;
- rule references;
- related entities;
- notes.

A compiler may emit an invalid ESIR containing the successfully established semantic prefix plus diagnostics, or may emit diagnostics without a completed ESIR. The CobaltC specification governs which source constructs are accepted or rejected; this document does not impose a diagnostic ordering unless the language specification does.

## 13. Validity

A completed ESIR is semantically valid when the applicable validity predicates hold:

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

The ESIR should expose the validation result and, where useful, the individual predicate results.

## 14. Canonical invariants exposed by ESIR

The semantic compiler should be able to expose evidence for invariants such as:

- initialized storage represents a valid value of its type;
- uninitialized storage is not read as an initialized value;
- owned values have one ownership responsibility;
- moved sources cannot be used as owners of transferred values;
- borrows cannot outlive referents;
- prohibited shared/mutable overlaps do not coexist;
- destruction responsibility is discharged exactly once;
- relocation does not silently invalidate live borrows;
- synchronization does not itself extend lifetime;
- unsafe entry does not implicitly create missing semantic facts;
- ABI compatibility does not itself establish CobaltC ownership or lifetime semantics.

## 15. What the ESIR deliberately does not contain

The ESIR is not:

- machine code;
- assembly;
- LLVM IR;
- a C/C++ AST;
- a Rust MIR clone;
- a runtime memory layout specification unless the CobaltC specification requires the relevant representation;
- an optimizer-specific internal format.

The compiler may internally use any suitable implementation architecture. The required external artifact is the explainable semantic result.

## 16. Suggested compiler architecture

A compiler implementing this output can be organized as:

```text
Source
  │
  ▼
Lexer
  │
  ▼
Parser
  │
  ▼
AST
  │
  ▼
Name Resolution
  │
  ▼
Type Analysis
  │
  ▼
Initialization Analysis
  │
  ▼
Ownership Analysis
  │
  ▼
Borrow Analysis
  │
  ▼
Lifetime Analysis
  │
  ├────► Control-flow analysis
  ├────► Destruction/defer analysis
  ├────► Concurrency analysis
  ├────► Unsafe analysis
  └────► ABI/FFI analysis
  │
  ▼
ESIR Construction
  │
  ▼
ESIR Validation
  │
  ▼
program.esir.json
```

This is an implementation plan, not a mandated sequence. The existing dependency graph is evidence for semantic dependencies, not a language requirement.

## 17. Minimal useful output

Even a small valid program should produce enough information to reconstruct the important semantic story:

```text
source
→ resolved declaration
→ type
→ place
→ initialization
→ ownership
→ operation
→ resulting state
→ applicable rule
→ invariant
```

For a move, for example:

```text
source expression
    ↓
place_x
    ↓
Owned
    ↓
TRANS-MOVE-001
    ↓
move
    ↓
value_y receives ownership
    ↓
place_x becomes moved
```

For a borrow:

```text
source expression
    ↓
place_x
    ↓
borrow_shared
    ↓
capability κ
    ↓
lifetime λ
    ↓
referent remains owned
    ↓
borrow/lifetime rules
```

## 18. Relationship to the existing CobaltC artifacts

The ESIR is the **output format**.

The other artifacts serve different roles:

```text
CobaltC 1.0.3 Specification
        │
        ▼
Formal Semantic Specification v3
        │
        ├──► Formal Inference and Transition Rules v3
        │
        ├──► Rule → IR Traceability v3
        │
        └──► Rule Dependency Graph
                    │
                    ▼
              Compiler analyses
                    │
                    ▼
             Explainable ESIR
                    │
                    ▼
          program.esir.json
```

Thus the previously generated files are inputs to the compiler-development process; this document and its schema define the principal external product of that compiler.

## 19. Conformance target

A compiler claiming ESIR conformance should:

1. accept/reject CobaltC source according to the CobaltC 1.0.3 specification;
2. construct semantic entities corresponding to accepted source constructs;
3. preserve the semantic relationships required by the formal model;
4. expose source provenance for semantic operations where a source location exists;
5. expose applicable formal rule references;
6. expose semantic effects and resulting facts;
7. report semantic diagnostics for rejected constructs;
8. validate the resulting ESIR against the ESIR schema;
9. avoid presenting implementation-specific assumptions as CobaltC semantic facts.

## 20. Versioning

The ESIR format version is independent of the CobaltC publication version.

For example:

```text
language_publication = 1.0.3
esir_format = 1.0.0
```

A change to the ESIR structure does not imply a change to the CobaltC language specification.

Conversely, a CobaltC language revision may require a new ESIR capability while retaining compatibility with an older format.

## 21. Final objective

The intended end-to-end result is:

```text
CobaltC source
      │
      ▼
semantic compiler
      │
      ▼
CobaltC Explainable Semantic IR
      │
      ▼
human-readable / machine-readable explanation
```

The ESIR file is therefore the primary compilation artifact for this project. An executable is neither required nor implied.

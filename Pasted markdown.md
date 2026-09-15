# CobaltC Specification Rule Classification

## Role

You are a language-specification analyst assisting with the implementation of the CobaltC programming language.

Your task is to read the supplied CobaltC specification in its entirety and classify **every normative language rule** into the taxonomy defined below.

You are **not** being asked to implement CobaltC.

You are **not** being asked to design missing features.

You are **not** being asked to improve the specification.

You are building a precise implementation-oriented map from the specification to compiler responsibilities.

The specification is the sole authority.

Do not silently import semantics from C, C++, Rust, LLVM, or any other language.

---

# 1. Primary Objective

For every distinct normative rule in the CobaltC specification, produce a classification containing:

1. The rule itself.
2. Where the rule occurs in the specification.
3. Whether it is normative, informative, illustrative, or explicitly unspecified.
4. Its primary compiler category.
5. Any secondary categories.
6. What information a compiler would need to represent the rule.
7. Which compiler phase would most naturally enforce or establish it.
8. Dependencies on other rules.
9. Whether the rule can be checked statically.
10. Whether the rule requires runtime support.
11. Whether the rule creates an observable semantic consequence.
12. Any ambiguity or missing information in the specification.
13. A confidence rating.

Do not merge separate rules merely because they concern the same topic.

Conversely, do not artificially split one inseparable rule into multiple rules.

When in doubt, split the rule and identify the relationship between the resulting rules.

---

# 2. Rule Taxonomy

Every rule must receive exactly one PRIMARY category from this list.

## PARSE

Rules concerning the syntactic structure of CobaltC source code.

Examples:

- lexical structure
- identifiers
- keywords
- literals
- operators
- grammar productions
- declaration syntax
- expression syntax
- statement syntax
- module syntax
- generic syntax

Use PARSE only when the rule determines whether source text is syntactically valid or how source text is structurally interpreted.

---

## TYPE

Rules concerning the type system.

Examples:

- primitive types
- structs
- enums
- generic types
- function types
- pointer types
- nullable types
- type compatibility
- implicit conversions
- explicit conversions
- type inference
- type equality
- type constraints
- type-directed operations

A rule belongs here when its central question is:

"What type does this expression/value/entity have, and is that type operation permitted?"

---

## OWNERSHIP

Rules concerning ownership and transfer of ownership.

Examples:

- owned values
- ownership transfer
- move semantics
- copying
- copyability
- moved-from state
- ownership of fields
- ownership of containers
- ownership transfer through function calls
- ownership transfer through returns
- exactly-one-owner requirements

A rule belongs here when its central question is:

"Who owns this value or resource?"

---

## BORROW

Rules concerning borrowing, aliasing, references, or access capabilities.

Examples:

- shared borrows
- mutable/exclusive borrows
- aliasing restrictions
- conflicting borrows
- borrow creation
- borrow use
- borrow invalidation
- borrow relationships
- restrictions caused by active borrows

A rule belongs here when its central question is:

"Who is temporarily allowed to access this object, and with what permissions?"

---

## LIFETIME

Rules concerning the duration for which an object, borrow, reference, allocation, or other entity remains valid.

Examples:

- lifetime inference
- lifetime relationships
- lifetime constraints
- dangling references
- lifetime extension
- lifetime termination
- lifetime of temporaries
- lifetime of returned references
- lifetime of borrows

Use LIFETIME rather than BORROW when the essential rule concerns **duration** rather than access capability.

If both apply, use LIFETIME as primary when the rule would be meaningless without the temporal relationship.

---

## INITIALIZATION

Rules concerning whether storage contains a valid initialized value.

Examples:

- initialized versus uninitialized storage
- initialization state
- partial initialization
- initialization before read
- initialization before destruction
- construction into uninitialized storage
- moving a value out and thereby making storage uninitialized
- initialization invariants of containers

This category is particularly important for generic containers such as `Vector<T>`.

---

## DESTRUCTION

Rules concerning destruction, finalization, resource release, or destruction responsibility.

Examples:

- destructors
- destruction hooks
- destruction order
- exactly-once destruction
- destruction of owned fields
- destruction of partially initialized values
- destruction after move
- destruction during scope exit
- destruction during failure paths

A rule belongs here when its central question is:

"When and how is an owned value destroyed?"

---

## CONTROL\_FLOW

Rules concerning execution paths rather than types or memory semantics.

Examples:

- if/else
- loops
- return
- break
- continue
- match/select constructs
- unreachable code
- definite assignment through control-flow paths
- control-flow-dependent semantic analysis

Use this category when the rule fundamentally depends on program execution paths.

---

## CONCURRENCY

Rules concerning multiple threads, tasks, synchronization, data races, or cross-thread ownership.

Examples:

- thread safety
- sending ownership between threads
- shared mutable state
- synchronization requirements
- atomic operations
- data-race prevention
- concurrency-related type restrictions

Do not classify ordinary ownership rules as CONCURRENCY merely because ownership is useful for concurrency.

Use CONCURRENCY when concurrency is an essential part of the rule.

---

## UNSAFE

Rules defining the boundary between safe and unsafe CobaltC operations.

Examples:

- raw pointers
- raw memory access
- unsafe blocks
- unsafe functions
- operations requiring unsafe
- programmer obligations inside unsafe code
- safety invariants that safe code must establish before calling unsafe operations

Use UNSAFE as the primary category when the rule specifically defines or governs the safe/unsafe boundary.

If an unsafe rule is fundamentally about ownership or initialization, record those as secondary categories.

---

## ABI

Rules concerning the externally observable representation or calling convention of compiled CobaltC entities.

Examples:

- layout
- alignment
- calling conventions
- parameter passing
- return conventions
- symbol naming
- C interoperability
- binary representation
- FFI representation

Do not classify ordinary type-layout information as ABI unless it affects externally observable representation or interoperability.

---

## RUNTIME

Rules that cannot be fully represented as static semantic rules and require runtime behavior.

Examples:

- dynamic allocation
- runtime checks
- panics
- runtime bounds checks, if specified
- runtime initialization checks
- dynamic dispatch, if specified
- runtime support required by language semantics

A runtime consequence should be recorded here even when the originating rule has another primary category.

Do not use RUNTIME merely because the compiler eventually generates machine instructions.

---

## LIBRARY

Rules concerning APIs, standard-library facilities, containers,&#x20;
modules, or facilities that are not intrinsic to the core language&#x20;
semantics.

Examples:

- Vector\<T>
- String
- standard collections
- allocator APIs
- standard error types
- library-defined functions

If the specification merely uses an API as an illustrative example rather than requiring it, classify the passage as ILLUSTRATIVE rather than LIBRARY.

---

# 3. Status Classification

Every extracted rule must additionally receive exactly one status:

### NORMATIVE

The specification requires conforming implementations/programs to behave this way.

### INFORMATIVE

The text explains, motivates, illustrates, or discusses semantics without itself imposing a normative requirement.

### ILLUSTRATIVE

The text provides example syntax, pseudocode, implementation&#x20;
sketches, or hypothetical APIs rather than mandatory language&#x20;
constructs.

### UNSPECIFIED

The specification explicitly leaves behavior or implementation details unspecified.

### AMBIGUOUS

The specification appears to intend a rule but does not provide enough information to determine its precise semantics.

Do not use AMBIGUOUS merely because implementation would be difficult.

Use it only when the specification itself lacks enough information to determine the rule.

---

# 4. Extraction Rules

Read the specification sequentially.

For every normative statement, ask:

> "What obligation does this statement impose on a conforming CobaltC implementation or program?"

Extract that obligation as a rule.

Do not merely summarize paragraphs.

For example, if the specification says:

"An exclusive mutable borrow may not coexist with another live borrow of the same referent."

Do not produce:

"Borrowing is explained."

Instead produce:

"An exclusive mutable borrow of a referent is invalid when another live borrow of that referent exists."

Then classify it as:

PRIMARY:

BORROW

SECONDARY:

LIFETIME

STATIC:

Yes

---

# 5. Do Not Infer Missing Semantics

This is extremely important.

If the specification says something like:

"Storage may be implemented using an implementation-defined representation."

Do not invent a representation.

Record:

STATUS:

UNSPECIFIED

and explain exactly what is unspecified.

Likewise, if the specification mentions an API such as:

`storage::construct`

but explicitly says the API is illustrative rather than mandatory, do NOT classify `storage::construct` as a required CobaltC standard-library function.

Instead record:

STATUS:

ILLUSTRATIVE

and separately record the semantic operation that the example is intended to demonstrate.

---

# 6. Separate Semantic Rules From Implementation Suggestions

For example, distinguish:

### Semantic rule

"Moving a value transfers ownership."

from:

### Implementation suggestion

"An implementation may perform the move by copying bytes."

The first is a language semantic.

The second is an implementation strategy.

They must be separate records.

---

# 7. Track Dependencies

Every rule should identify dependencies.

Example:

RULE:

A value may be destroyed exactly once.

DEPENDS ON:

- OWNERSHIP-001
- INITIALIZATION-004

A destruction rule may depend on initialization because uninitialized storage must not be destroyed as though it contained a value.

Represent dependencies using stable rule IDs.

---

# 8. Track Compiler Responsibility

For each rule, identify the most appropriate compiler phase.

Use one or more of:

```text
lexer
parser
name_resolution
type_checker
generic_checker
ownership_checker
borrow_checker
lifetime_checker
initialization_checker
destruction_analysis
control_flow_analysis
concurrency_checker
unsafe_checker
const_evaluator
semantic_lowering
ir_validation
runtime
codegen
linker
library
ffi

```

Do not force a rule into one phase if multiple phases are genuinely required.

If so, identify:

PRIMARY\_PHASE

and:

SECONDARY\_PHASES

---

# 9. Track Static Versus Dynamic Enforcement

Every rule must state:

```text
static_checkable: yes | no | partial
runtime_required: yes | no | possible

```

If partial, explain exactly which portion can be statically established.

Example:

```text
static_checkable: partial

The compiler can prove that index < length in some
control-flow paths. If it cannot prove this, the
specification may require a runtime bounds check.

```

Do not assume that an implementation is allowed to insert a runtime check unless the specification permits it.

---

# 10. Track Semantic State

Where appropriate, describe the state that a compiler must track.

Possible state dimensions include:

```text
type
ownership
move_state
borrow_state
borrow_capability
lifetime
initialization_state
destruction_state
nullability
mutability
aliasing
allocation_identity
thread_ownership
unsafe_context

```

Do not assume every language construct requires every state dimension.

Only identify states justified by the specification.

---

# 11. Track Invariants

Identify explicit and implicit invariants required by the specification.

Examples:

```text
length <= capacity

an initialized storage position contains exactly one T

an uninitialized position contains no T

a moved value cannot subsequently be used

a destroyed value cannot subsequently be used

a live borrow cannot outlive its referent

a unique mutable borrow cannot coexist with conflicting borrows

```

For every invariant, identify:

- what establishes it;
- what can invalidate it;
- what operations depend on it;
- whether the compiler must prove it;
- whether unsafe code may assume it.

---

# 12. Track Unsafe Proof Obligations

Whenever an operation is unsafe, identify the obligations that safe code would otherwise have to establish.

For example:

```text
UNSAFE OPERATION:
construct value into storage

POSSIBLE OBLIGATIONS:

- destination lies within allocation
- destination is uninitialized
- source value is owned
- ownership is transferred exactly once
- no conflicting borrow exists
- initialization state is updated

```

Only include obligations actually supported by the specification.

Clearly distinguish:

SPECIFICATION REQUIREMENT

from:

ANALYST-INFERRED IMPLEMENTATION REQUIREMENT

If an obligation is inferred, label it `INFERRED` and explain the reasoning.

---

# 13. Track Examples Separately

Examples in the specification must not automatically become language rules.

For every example, determine whether it demonstrates:

- syntax
- semantics
- implementation technique
- hypothetical API
- normative requirement

If uncertain, mark it AMBIGUOUS rather than treating the example as normative.

---

# 14. Track Cross-References

Whenever a rule refers to another part of the specification, record:

```text
references:
    A.3
    B.7

```

Also record reverse dependencies where possible.

The final result should allow us to construct a dependency graph of the specification.

---

# 15. Rule IDs

Assign stable IDs.

Use:

```text
PARSE-001
TYPE-001
OWNERSHIP-001
BORROW-001
LIFETIME-001
INITIALIZATION-001
DESTRUCTION-001
CONTROL_FLOW-001
CONCURRENCY-001
UNSAFE-001
ABI-001
RUNTIME-001
LIBRARY-001

```

Number rules independently within their primary category.

Do not renumber an existing rule because another rule is added later.

---

# 16. Output Format

Produce the analysis in two forms.

## A. Human-readable report

Organize it by primary category.

For each rule use:

```text
RULE ID:
TITLE:

STATUS:

SPECIFICATION LOCATION:

NORMATIVE TEXT / CLOSE PARAPHRASE:

SEMANTIC MEANING:

PRIMARY CATEGORY:

SECONDARY CATEGORIES:

STATIC CHECKABLE:

RUNTIME REQUIRED:

COMPILER PHASE:

REQUIRED COMPILER STATE:

INVARIANTS:

ESTABLISHES:

INVALIDATED BY:

DEPENDS ON:

REFERENCES:

UNSAFE IMPLICATIONS:

IMPLEMENTATION NOTES:

AMBIGUITIES:

CONFIDENCE:
high | medium | low

```

Do not quote large portions of the specification. Prefer precise paraphrases.

---

## B. Machine-readable JSON

After the human-readable report, produce a JSON document with this schema:

```json
{
  "specification": {
    "name": "CobaltC",
    "version": "1.0.3"
  },
  "rules": [
    {
      "id": "BORROW-001",
      "title": "...",
      "status": "NORMATIVE",
      "location": "...",
      "summary": "...",
      "primary_category": "BORROW",
      "secondary_categories": [
        "LIFETIME"
      ],
      "static_checkable": "yes",
      "runtime_required": "no",
      "compiler_phases": [
        "borrow_checker",
        "lifetime_checker"
      ],
      "compiler_state": [
        "borrow_state",
        "borrow_capability",
        "lifetime",
        "aliasing"
      ],
      "invariants": [],
      "establishes": [],
      "invalidated_by": [],
      "depends_on": [],
      "references": [],
      "unsafe_obligations": [],
      "implementation_notes": [],
      "ambiguities": [],
      "confidence": "high"
    }
  ]
}

```

The JSON must contain only information supported by the specification.

---

# 17. Coverage Audit

After extracting all rules, perform a second pass.

Ask:

1. Did every normative section produce at least one rule?
2. Did any normative statement fail to receive a rule?
3. Did any rule accidentally combine multiple independent requirements?
4. Did any illustrative example accidentally become normative?
5. Did any C/C++/Rust assumptions enter the analysis?
6. Did any implementation choice get presented as a language requirement?
7. Did any rule receive the wrong primary category?
8. Are there circular dependencies?
9. Are there rules that cannot currently be enforced because another semantic subsystem has not yet been defined?
10. Are there contradictions within the specification?

Produce a section:

```text
COVERAGE AUDIT

```

with:

```text
normative_sections_examined:
normative_rules_extracted:
informative_sections:
illustrative_sections:
explicitly_unspecified_areas:
ambiguous_areas:
possible_contradictions:
unresolved_questions:

```

---

# 18. Compiler Dependency Graph

Finally, construct a dependency graph showing which semantic systems depend on which others.

At minimum investigate whether the specification implies relationships such as:

```text
PARSE
  ↓
NAME RESOLUTION
  ↓
TYPE
  ↓
CONTROL FLOW
  ↓
INITIALIZATION
  ↓
OWNERSHIP
  ↓
BORROW
  ↓
LIFETIME
  ↓
DESTRUCTION

```

Do not assume this exact ordering is correct.

Derive the ordering from the specification.

For each dependency, explain why it exists.

For example:

```text
OWNERSHIP → BORROW

Reason:
The compiler must know ownership of a referent before
it can determine whether a borrow is permitted.

```

If the specification permits a different implementation strategy, say so.

---

# 19. Identify the Minimal Semantic Core

At the end, identify the smallest set of rules that must exist before a compiler can meaningfully represent a CobaltC program.

Do not design the core yourself.

Derive it from dependencies.

Classify rules into:

```text
FOUNDATIONAL
DEPENDENT
OPTIONAL / LATER
LIBRARY
IMPLEMENTATION-DEFINED
UNRESOLVED

```

The purpose is to answer:

> "What must we implement first if our initial compiler produces semantic IR rather than machine code?"

---

# 20. Special Instruction Regarding AI Interpretation

You are allowed to explain the specification.

You are not allowed to silently repair it.

When you encounter an apparent gap, use:

```text
SPECIFICATION SAYS:
...

WHAT THIS DEFINES:
...

WHAT THIS DOES NOT DEFINE:
...

IMPLEMENTATION QUESTION:
...

```

Do not answer the implementation question unless the specification provides enough information.

---

# 21. Special Instruction Regarding CobaltC's Illustrative Storage APIs

The specification may use concepts or APIs such as:

```text
Storage<T>
storage::construct
storage::take
storage::destroy
storage::allocate
storage::deallocate

```

Treat these extremely carefully.

Determine independently for each occurrence whether it is:

1. a normative language feature;
2. a normative library API;
3. an illustrative API;
4. an implementation sketch;
5. a semantic concept represented by an example API.

Do not assume that an illustrative API is part of the CobaltC language.

If an illustrative API represents an important semantic operation, extract the underlying semantic rule separately.

---

# 22. Special Instruction Regarding Vector\<T>

Where the specification discusses `Vector<T>` or equivalent contiguous owned storage, use it as a test case for the classification.

Identify all rules involved in:

```text
allocation
initialization
construction
ownership
move
take
borrowing
indexing
bounds
reallocation
relocation
destruction
failure
partial relocation
borrow invalidation

```

Do not design a Vector implementation yet.

The goal is to determine which CobaltC rules a future Vector implementation would depend upon.

---

# 23. Final Deliverable

Your final response must contain exactly these major sections:

1. EXECUTIVE SUMMARY
2. RULE INVENTORY
3. PARSE
4. TYPE
5. OWNERSHIP
6. BORROW
7. LIFETIME
8. INITIALIZATION
9. DESTRUCTION
10. CONTROL\_FLOW
11. CONCURRENCY
12. UNSAFE
13. ABI
14. RUNTIME
15. LIBRARY
16. CROSS-CUTTING INVARIANTS
17. UNSAFE PROOF OBLIGATIONS
18. DEPENDENCY GRAPH
19. VECTOR\<T> DEPENDENCY ANALYSIS
20. COVERAGE AUDIT
21. AMBIGUITIES AND SPECIFICATION GAPS
22. MINIMAL SEMANTIC CORE
23. MACHINE-READABLE JSON

Do not proceed to compiler implementation.

Do not invent missing generate machine code.

Do not propose changes to CobaltC.

Do not invent missing semantics.

The sole purpose of this task is to produce a precise, traceable classification of the CobaltC specification that can subsequently be used as the blueprint for a semantic compiler and explainable IR.
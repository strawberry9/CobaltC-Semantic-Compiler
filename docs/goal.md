# Single-module core semantic milestone

## Agreed goal

Build a functional semantic compiler and explanation tool for a single CobaltC module, covering a subset close to the specification's Core Conformance level. Produce trustworthy ESIR and source-inclusive plain-English HTML explanations for supported programs. This milestone does not require native code generation or execution.

This is an agreed project scope, not a Core Conformance claim. Map the normative Core requirements before deciding exactly how close the milestone is to that level. The normative specification and authority decisions in implementation.md govern semantics; this document governs project scope and continuation.

## Scope

- Include core types, expressions, functions, control flow (including loops and `match`), initialization, ownership, copying and moves, borrowing, lifetimes, aggregates, and cleanup, subject to the explicit Core requirement mapping.
- Accept import declarations as valid syntax. Do not load modules or perform cross-module resolution in this milestone. A program containing imports must receive an explicit unsupported-import diagnostic and an overall semantically incomplete result unless other errors require an invalid result. Continue local analysis where possible; imported names must not be assumed resolved or type-correct.
- Exclude foreign functions/FFI, concurrency, threads, and facilities supplied only by the standard library, including standard I/O, `String`, and `Vector`.
- Include the language feature `match`; it is not excluded as a library facility.
- Diagnose unsupported constructs and combinations explicitly. Do not silently certify unchecked behavior as valid.
- Derive explanations from recorded semantic evidence. Source, diagnostics, capabilities, lifetimes, state transitions, and English explanations must agree.

## Procedure for “continue with goal”

1. Read this handoff, implementation.md, and applicable repository instructions. Inspect Git status and current code/tests; preserve existing work and do not infer current support solely from historical conversations or test counts.
2. Select one bounded phase that advances this milestone. Prioritize correctness gaps in existing support over adding features that depend on those gaps.
3. State the phase and its acceptance criteria. Implement it, including explicit unsupported boundaries and tests of interactions with existing features.
4. Validate positive and negative behavior, semantic evidence, and relevant explanation output. Run focused tests, the full suite where appropriate, example checks, and artifact/reference checks. Record actual results; test counts and rule exercise counts are not conformance percentages.
5. Update this handoff, implementation.md, README status where affected, and relevant examples. Record remaining limitations and the next bounded recommendation. Use recoverable Git checkpoints when authorized; never discard existing changes.
6. **Stop after the phase and wait for user confirmation.** Do not begin another phase automatically. “Continue with goal” authorizes the next single phase.

## Initial roadmap

1. The initial [Core requirements checklist](core-checklist.md) maps all twelve Section 80.1 obligation families to scope, implementation evidence, acceptance gates, and an ordered gap inventory. Expand its family-level entries into clause-level evidence as each implementation phase proceeds.
2. Audit the recently added managed pointer fields before expanding their use: capability preservation and permissions across calls/returns, aggregate temporaries, nested aggregates, and cleanup. Reject unsupported combinations where sound analysis is absent.
3. Use the checklist and audit to sequence further bounded phases, including remaining core expression/type semantics, converging loop dataflow and loop-exit cleanup, and `match` semantics. Derive exact rules from the specification before implementation.
4. Perform integration and negative-case validation across the included feature set; verify deterministic ESIR, diagnostic/reference integrity, and faithful explanations.

## Completion criteria

Every required checklist item has an implementation and meaningful validation evidence; unsupported boundaries are explicit; no known soundness gaps remain within the claimed subset; examples and documentation match the implementation. Record remaining differences from normative Core Conformance explicitly before declaring the milestone complete.

## Current handoff

- The goal and one-phase continuation procedure are agreed and recorded.
- The prior phase reported basic managed pointer fields implemented with 487 passing tests. That report is historical evidence, not a substitute for inspecting current state or auditing feature interactions.
- **Completed planning phase (2026-09-15):** established [core-checklist.md](core-checklist.md), based on normative Section 80.1 and the referenced language sections, with current code/test evidence. Nullability, generics, associated functions, destruction hooks, and single-thread memory semantics remain visible requirements. Error propagation's Result dependency is explicitly deferred for a scope decision; library exclusion does not imply all associated syntax is non-language syntax.
- **Next phase:** managed pointer soundness audit and repair. First reconcile implicit mutable-pointer copies with Sections 14 and 17, then verify aggregate capability provenance through calls/returns, temporaries, nesting, and cleanup. Repair soundness gaps or explicitly diagnose unsupported combinations; add regressions and correct documentation claims. Stop after this phase.
- Planning validation: checked local documentation links, complete mapping of the twelve Section 80.1 families, source artifact/reference audit, and diff whitespace. No compiler changes or new full-suite test results are claimed for this documentation phase.

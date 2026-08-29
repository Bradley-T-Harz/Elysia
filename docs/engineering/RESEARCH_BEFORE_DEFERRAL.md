# Research Before Deferral

Status: permanent Elysia engineering rule adopted 2026-08-22.

A failed first implementation is evidence about that implementation, not proof that the capability is unsound.

Before Elysia defers an owned capability:

1. identify the exact observed failure;
2. consult current primary documentation;
3. consult relevant peer-reviewed work and maintained reference implementations where warranted;
4. distinguish implementation, configuration, device, scale, packaging, privacy, and concept failures;
5. test the strongest practical established architecture inside Elysia;
6. record reproducible measurements and the exact remaining blocker;
7. only then promote, keep optional, or defer to its owning pass.

Therefore:

- first approach failed does not mean capability failed;
- embedded implementation failed does not mean server implementation failed;
- one cold or CPU path was slow does not mean the capability is inherently slow;
- “experimental in Elysia” means not yet proven inside Elysia, not that the mechanism lacks scientific or engineering precedent.

No later-pass boundary is weakened by this rule. Research may establish readiness; implementation still occurs only in the pass that owns the capability.

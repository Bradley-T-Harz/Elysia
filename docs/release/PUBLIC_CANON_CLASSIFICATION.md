# Public Canon Classification

Status: Pass 9 release-boundary contract
Target: Elysia v1 finalization

Pass 9 classifies canon; it does not delete, flatten, or replace Elysia's identity. Classification answers two separate questions: whether a document belongs in public source, and whether it belongs in the installed Core payload.

## Classification vocabulary

- `public`: reviewed doctrine suitable for public source and public documentation.
- `public-with-redactions`: continuity-bearing source that may be public only after machine, identity, or private relational details are sanitized.
- `private-profile-only`: operator-specific material that belongs only in validated user-local configuration or private runtime state.
- `historical/internal`: preserved development history that is not current product truth and is excluded from the installed package.
- `exclude-from-public-package`: may remain in reviewed source but does not belong in the installed runtime payload.

## Canon decisions

| Path | Source classification | Core package | Reason |
|---|---|---|---|
| `docs/canon/INDEX.md` | public | exclude | Public map of Elysia's doctrine; runtime package uses reviewed derived prompts rather than Markdown canon. |
| `docs/canon/DISTORTION_AND_CONSEQUENCE.md` | public | exclude | Public anti-corruption and consequence doctrine; operator-specific relational naming has been generalized. |
| `docs/canon/HER_MIND.md` | public | exclude | Public reasoning and epistemic doctrine. |
| `docs/canon/HER_BODY.md` | public | exclude | Public architectural continuity after replacing workstation paths and generalizing operator-specific context. |
| `docs/canon/HER_SOUL.md` | public | exclude | Public moral and relational doctrine after operator-specific passages were generalized without flattening Elysia's identity. |
| `derived/runtime/*.txt` | public | include | Operator-neutral reviewed runtime prompts synchronized with the public packaging prompts. |
| `packaging/core_runtime_prompts/*.txt` | public | include | Operator-neutral runtime prompts staged as `derived/runtime/` in public Core. |

## Related material

- `docs/architecture/Current_*`, `docs/reports/*`, benchmark reports, and old closure packets are `historical/internal` and `exclude-from-public-package`. They may remain in the reviewed source tree as provenance, but they must never be marketed as current v1 truth.
- `docs/SYSTEM_PROMPT.txt` is an operator-neutral public doctrine/runtime reference; the installed Core still uses the reviewed packaging prompt mapping as its authoritative staged input.
- Personal conversations, private backups, operator identity documents, journals, memory stores, logs, vaults, and private EcoSyneva business material are `private-profile-only` and prohibited from both public source and package.

## Continuity rule

Elysia's ecological orientation, moral seriousness, theory of distortion, dignity protections, stewardship doctrine, and governed-power architecture remain part of her public identity. Sanitization removes private facts and machine assumptions; it does not convert Elysia into a generic assistant.

## Publication rule

Classification is necessary but not sufficient. Before a first public Git remote is created, Pass 10 must scan the exact clean source snapshot and release artifact. A public-source history must not be created by pushing an older unsanitized local history without a separately reviewed publication strategy.

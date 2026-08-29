# Elysia Public Release Risk Inventory

Date: 2026-08-17
Rule: path/category evidence only; no private contents or secret values.

| Area | Risk | Severity | Pass 9 treatment |
|---|---|---:|---|
| `config/system/machine_profile.yaml` | formerly contained workstation identity, hardware, storage, and absolute paths | critical | replaced with portable unknown defaults; doctor/local config owns machine truth |
| optional model registries | formerly contained operator model-vault paths | critical | converted to relative public asset identifiers; XDG local override supplies private roots |
| optional worker registries | formerly contained operator environment/model paths and disposable evidence paths | critical | path fields now null; compact retained evidence only; local override required |
| media worker CLIs | formerly contained model-vault constants | critical | paths now arrive through validated internal local override resolution and never through public API truth |
| `data/`, `logs/`, `memory/`, `vault/` | runtime/private state | critical | denylisted; only reviewed templates/readmes may be tracked; no generated state packaged |
| local `.env` and override files | secrets/private machine metadata | critical | ignored and absent from tracked source/package |
| `docs/canon/*` | public Elysia canon | low | operator-specific relational/workstation facts generalized; doctrine preserved; installed Core excludes Markdown canon |
| `derived/runtime/*` | operator-neutral runtime prompts | low | synchronized with reviewed public packaging prompts; personal continuity belongs only in private local state |
| `docs/reports/*` and architecture snapshots | old paths and stale capability claims | medium | historical/internal; package-excluded; exact operator paths sanitized where found |
| former external `Elysia_App/Elysia.desktop` | development-checkout and icon path assumptions | high | exact original preserved in the private operator archive; a generated local convenience entry may point to the same stable installed launcher without re-entering public source |
| Desktop build/cache directories | generated artifacts and possible path-bearing build evidence | high | ignored and package-denied except final reviewed Tauri artifact |
| repository history | pre-hygiene history contained workstation assumptions | resolved | verified private bundles preserve the original history; the canonical publication-bound refs were rewritten without flattening chronology, unreachable originals were pruned locally, and the complete-history scanner reports zero findings |

Private runtime material was classified by path/category, preserved without printing its contents, and moved into the access-restricted private operator archive before publication-bound sanitization. Nothing was deleted.

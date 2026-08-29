# Elysia

Elysia is a local-first, privacy-first, governed AI companion platform.

This repository is the one canonical Elysia codebase. Elysia v1.0 uses install profiles and optional governed add-ons; operator-specific runtime data and local overrides do not belong in public packages.

Core principles:
- local-first by default
- internet access only through narrow, revocable tools
- strong separation between reasoning, tools, and risky execution
- privacy, inspectability, and recoverability over convenience

Release status: version `1.0.0`, qualified stable release. Canonical availability and exact release downloads are reported by [GitHub Releases](https://github.com/Bradley-T-Harz/Elysia/releases/tag/v1.0.0) and the [Elysia Archive](https://elysiaecobotics.com/archive), rather than mutable publication flags embedded in source or package bytes. Release contracts and profile documentation live under [`docs/release/`](docs/release/).

Public/private hygiene is governed by the [public package manifest](packaging/public_manifest.yaml), [canon classification](docs/release/PUBLIC_CANON_CLASSIFICATION.md), and [risk inventory](docs/release/PUBLIC_RELEASE_RISK_INVENTORY.md). Local model, worker, repository, and machine paths belong in validated XDG user configuration and are never supplied by tracked defaults. Any publication or replacement of release bytes remains an explicit release-steward action.

---

## Current status

Elysia is a working local-first companion-intelligence repository, not a single monolithic chatbot app. It currently contains a governed Python runtime body, a local FastAPI bridge, a React/Vite/Tauri desktop chamber, configuration law, memory and governance scaffolding, bounded worker sandboxes, evidence/research contracts, request/tool ledger surfaces, local data/log/memory state, and a growing test suite.

The current build has crossed from pure scaffold into practical local organs:

- local API bridge and structured response envelopes
- desktop chamber with Conversations, Projects, Memory, Governance, Health, Capabilities, and Requests surfaces
- local file ingestion v0
- bounded math execution
- bounded data execution for local CSV/XLSX summaries
- local artifact and simple plot artifact support
- governed Chunks 1–4 stewardship for text/code, documents, science/data/geospatial files, and visual/image/SVG files
- bounded Chunk 5 media truth with local transcription and non-cloning speech output, plus disabled-by-default ImageForge/VideoForge lab lanes
- ArchiveForge selected-file extraction into disposable sandboxes, DatabaseForge schema-only previews, BinaryForge static analysis, and EngineeringForge static reports/sandbox-only projections
- Coder mode posture with read-only repo context and proposal-only patch planning
- Aider worker contract and dry-run/safety lane
- research evidence packet contract
- bounded SearXNG worker path, disabled by default unless explicitly configured
- shared mode profiles for Default, Tutor, Researcher, Writer, and Coder
- request/evidence/tool ledger surfaces for inspectability
- Sprint 12 benchmark prompts and reports for capability truth testing

Dangerous authority remains intentionally withheld unless future contracts, gates, tests, and UI truth surfaces are built first.

Not live by default:

- arbitrary shell execution
- silent or unapproved patch application
- Git mutation
- OpenHands
- unrestricted or unapproved page fetch
- broad browser automation
- silent cloud fallback
- autonomous external posting
- ecology subsystem sovereign autonomy

Elysia is powerful because boundaries are part of the architecture, not an afterthought.

## What Elysia is

Elysia is a layered, governed companion-intelligence system designed to be:

- local-first
- privacy-first
- policy-governed
- inspectable
- memory-aware without treating all context as memory
- tool-using without giving tools unchecked authority
- capable across writing, tutoring, research, coding support, data summaries, and project continuity
- expandable later into ecological, robotic, environmental, and planetary-health domains

The current repository is the practical local body and chamber for that system. It contains the runtime, the local API bridge, the desktop UI, the configuration law, the contracts, the tests, the workers, the reports, and the local state boundaries that keep Elysia from becoming a reckless pile of tools.

## What Elysia is not

Elysia is not:

- a cloud-first assistant wrapper
- an unrestricted browser
- an automatic shell runner
- an unapproved or autonomous patch applier
- a Git automation agent
- an OpenHands/autonomous coding agent
- a silent cloud model router
- a system that sends private memory outward by default
- a system that treats attached files as permanent memory by default
- a system that treats generated artifacts as memory by default
- a finished ecological sovereign AI
- a finished robotics control stack

Elysia may eventually gain stronger hands, but only after the relevant contracts, policy gates, approval records, trace ledgers, rollback paths, and refusal tests exist.

## Architecture at a glance

Plain flow:

```text
User
  -> Tauri desktop chamber
  -> React/Vite frontend
  -> local FastAPI bridge
  -> API schemas and services
  -> governed core runtime
  -> router / planner / policy gate / verifier / responder
  -> local model routing and bounded helpers
  -> optional caged workers
  -> structured response envelope
  -> request trace / artifacts / ledger truth / UI display
```

Short mental model:

```text
core/                 governed runtime body
app/api/              local FastAPI bridge and service boundary
apps/elysia-desktop/  desktop chamber
config/               posture, policy, model, mode, UI, and worker law
sandbox/              bounded worker cages
docs/                 canon, contracts, architecture, benchmarks, reports
skills/               YAML helper skills
XDG user data         installed conversations, projects, identity, artifacts, and ingest
XDG user state        logs, receipts, audit, and recovery state
XDG runtime           packaged local-API session credential and coordination
tests/                guardrail suite
vault/                private/sealed storage
```

## Main layers

### `core/` — governed runtime body

`core/` is the governed runtime body. It owns the internal orchestration path:

- `runtime.py` coordinates the main body flow.
- `router.py` classifies intent and helps select mode.
- `planner.py` builds structured plans and narrow execution candidates.
- `policy_gate.py` checks plans against approval, privacy, and boundary rules.
- `model_routing.py` selects model roles.
- `model_invoker.py` handles local model invocation.
- `verifier.py` checks result truth.
- `responder.py` composes final user-facing output.
- `context_gatherer.py`, `retrieval_policy.py`, `journal_policy.py`, `journal_writer.py`, and `memory_manager.py` shape local continuity, retrieval, and journaling behavior.
- `math_executor.py`, `data_executor.py`, and `plot_artifact_builder.py` provide bounded local computation and artifact helpers.
- `repo_context_gatherer.py` and `code_patch_formatter.py` support Coder mode without mutation.
- `evidence_verifier.py` and `contradiction_scan.py` support evidence packet verification and contradiction warnings.
- `skill_loader.py` and `skill_selector.py` load and choose YAML helper skills.

The UI should not bypass `core/`. Workers should not bypass `core/`. The local API bridge should call it and surface its truth.

### `app/api/` — local bridge and service boundary

`app/api/` is the local FastAPI bridge. It is not a generic cloud API. It should stay thin, structured, local, and downstream of `core/`.

It contains:

- `main.py`: app creation, route registration, local-only posture, structured envelopes.
- `runtime_bridge.py`: adapter between `/chat/send` and the governed runtime.
- route modules under `app/api/routes/`
- schema/contract models under `app/api/schemas/`
- service modules for conversations, projects, memory, files, execution, artifacts, governance, status, capabilities, request trace, and research.

Important route families include:

- chat
- conversations
- projects
- memory
- files
- status
- governance
- approvals
- requests
- request trace
- research

The bridge translates, validates, delegates, summarizes, and returns structured truth. It is not a second brain.

### `apps/elysia-desktop/` — desktop chamber

The desktop chamber is a React/Vite/TypeScript application inside a Tauri 2 native shell.

It contains:

- the main shell
- Conversations room
- Projects room
- Memory room
- Governance room
- Health room
- Capabilities room
- Requests room
- Status Menu
- Quick Invoke window
- right drawer trust stack
- bottom status bar
- local bridge client
- Tauri file picker helper
- artifact cards
- plot artifact view
- Coder repo context and patch plan cards
- command gate truth card

The chamber displays truth. It should not own hidden model invocation, governance logic, network behavior, file mutation, shell execution, or policy bypasses.

### `config/` — posture and law

`config/` contains Elysia's declared operating posture:

- `config/system/`: boundaries, source policies, stack, machine profile.
- `config/models/`: model roles and routing.
- `config/modes/`: shared mode profiles.
- `config/policies/`: approval, autonomy, and personality policy.
- `config/memory/`: memory policy.
- `config/coder/`: approved repo boundaries.
- `config/ui/`: UI contracts, trust language, capability defaults.
- `config/workers/`: Aider and SearXNG worker configs.
- `config/benchmarks/`: benchmark prompt config.

Config is not decoration. It is the written law that other organs should obey.

### `sandbox/` — bounded worker cages

`sandbox/` is where higher-risk worker lanes live outside the core.

Current worker areas:

- `sandbox/aider_worker/`
  - Aider contract/config/path guard/dry-run worker lane.
  - Current state: dry-run/safety truth, not live mutation.

- `sandbox/searxng_worker/`
  - Bounded SearXNG search worker path.
  - Current state: present and bounded, disabled by default unless configured.
  - Important boundary: SearXNG may be local loopback, but query terms can still cross the public web boundary.

Workers are caged because risk belongs behind contracts, approval gates, query/path guards, tests, and trace ledgers.

### `docs/` — canon, contracts, reports, and architecture

`docs/` contains build continuity and governance documents:

- architecture documents
- API contracts
- canon documents
- research contracts
- Coder/Aider contracts
- benchmark prompts
- Sprint reports
- 1.0 gap reports
- closure packets

Docs are not fluff in this project. They keep the build coherent as the code grows.

### `skills/` — YAML helper skills

`skills/` contains helper definitions for tasks such as conversation, research, tutoring, and writing. These are helpers, not autonomous agents. Skills do not grant authority outside routing, planning, policy, and verification.

### XDG user directories — public-install local state

Public installs resolve local state through XDG config/data/cache/state/runtime
roots and do not default new runtime writes into the installed source/application
tree. Source-tree `data/`, `logs/`, and `memory/` locations are legacy development
state and are not migrated or deleted automatically.

User-local state includes:

- `data/`: conversations, projects, artifacts, ingested files, manual test files.
- `logs/`: runtime, launcher, operational, approval, and decision logs.
- `memory/`: journals and vector-memory state.

These are not generally safe to publish. They may contain private conversations, local project state, generated artifacts, ingested file data, or memory/journal material.

## Core install and verification foundation

For the supported ordinary-user profile path, dependency automation, exact
download/privilege disclosures, and every remaining external user action, read
[`docs/release/DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md`](docs/release/DEPENDENCY_ACQUISITION_AND_MANUAL_ACTIONS.md).

Pass 6 provides a dry-run-first user-local Core installer and non-repairing
doctor. Pass 10B separately proved the package-owned Core runtime through a
clean `.deb` and AppImage lifecycle. Neither result is a claim that final
publication approval has been granted.

```bash
scripts/install_core.sh --dry-run
python -m app.cli.doctor
```

`--apply` performs no sudo or silent network access and enables no optional
profile. A reviewed offline wheelhouse may be supplied explicitly, or an
already provisioned interpreter may be selected with `--python ABSOLUTE_PATH`.
Packaged mutating API calls require a private XDG runtime credential; source
development mode is explicit. See
[`docs/release/INSTALLER_DOCTOR_RUNTIME.md`](docs/release/INSTALLER_DOCTOR_RUNTIME.md).
Stable update and repair mutation is never silent: it requires an authenticated
Local Admin's exact preview and explicit approval, followed by fail-closed
verification under the package-owned public Ed25519 trust root. See
[`docs/release/UPDATER_SIGNING_TRUST.md`](docs/release/UPDATER_SIGNING_TRUST.md).

### `vault/` — private/sealed storage

`vault/` is private/sealed. It should not be inspected, indexed, published, sent to workers, or used in outward research without explicit future policy and explicit approval.

## Capability truth

| Capability | Current truth |
| --- | --- |
| Local API bridge | Live / substantially working |
| Desktop chamber | Live / substantially working |
| Conversations | Live / substantially working |
| Projects | Live / maturing |
| Memory surfaces | Live / partial / maturing |
| Governance surfaces | Live / partial / maturing |
| Local file ingestion | Live v0 |
| Bounded math execution | Live |
| Bounded data execution | Live v0 |
| Local artifacts | Live v0 |
| Simple plot artifacts | Live v0 / bounded |
| Coder mode | Live posture |
| Read-only repo context | Live, approved-repo bounded |
| Proposal-only patch planning | Live, no mutation |
| Aider worker lane | Degraded / dry-run skeleton only |
| Evidence packets | Live schema/verifier |
| Contradiction scan | Live deterministic helper |
| Bounded SearXNG worker path | Present, disabled/inactive by default unless configured |
| Shared mode profiles | Live config |
| Request/evidence/tool ledger | Live / partial / maturing |
| Patch application | Not live |
| Shell execution | Not live |
| Git mutation | Not live |
| OpenHands | Not live |
| Page fetch | Not live |
| Broad cloud routing | Not live by default |
| Browser automation | Not live |
| Ecology sovereign subsystems | Future / not live |

## Safety boundaries

Elysia's safety model is not just refusal text. It is architectural:

- local-only bridge posture by default
- explicit approval before sensitive action
- no silent cloud fallback
- no private memory outward by default
- no private file outward by default
- no vault access by worker/research paths
- no file mutation from Coder mode
- no shell execution from Coder mode
- no Git mutation from Coder mode
- no patch application from patch proposals
- no page fetch in first-pass SearXNG search path
- search results and snippets are not treated as proof
- artifacts are not memory by default
- attached files are not memory by default
- request traces show compact truth rather than raw logs
- workers live in `sandbox/`, not inside the core

## Mode profiles

Elysia has shared capability organs, but modes change posture.

Current mode family:

- Default: practical general use.
- Tutor: teaching-first, explanation-oriented.
- Researcher: evidence-aware, citation/evidence strictness higher.
- Writer: grounded drafting and tone control.
- Coder: repo-aware, proposal-only, command-gated.

Modes should not grant hidden authority. They should change weighting, style, strictness, and routing posture while still respecting the same boundaries.

## Coder mode

Coder mode currently supports:

- read-only approved repo context
- safe tree/context summaries
- proposal-only patch planning
- Coder truth cards in the UI
- command-gate truth
- Aider worker dry-run/safety lane

Coder mode does not currently support:

- direct file mutation
- patch application
- shell commands
- test execution through Elysia
- package installation
- Git mutation
- OpenHands
- vault/private folder access
- broad home-folder scanning

If Coder proposes a patch, it is a plan, not an applied change.

## Research mode and SearXNG

Elysia has research evidence contracts and a bounded SearXNG worker path.

Important distinction:

- a local SearXNG instance can run on loopback
- but query terms sent to search engines still cross an outward public-web boundary
- private project context, private memory, file contents, vault notes, contacts, health, legal, finance, activism strategy, credentials, and local repo details must not be silently sent outward

Evidence packets exist to keep research accountable. They can include source URL, title, retrieval time, snippet, claim, confidence, contradiction notes, retrieval method, source type, outward boundary state, and private-context truth.

Search snippets are not proof. They are search-result evidence candidates.

## Local setup and launch

The commands below describe the current source-development workflow, not the final public installer. Public packaging will use the four contracts defined in [`INSTALL_PROFILES.md`](docs/release/INSTALL_PROFILES.md): Elysia Core, Recommended Workstation, Creator / AI Media, and Developer / Codev. Core will not require the heavy media, model, scientific, or developer stacks.

Optional profiles may require explicit package or model downloads. External services and outbound network use are disabled by default and may be used only when an applicable profile, policy, and exact user-approved operation make that boundary truthful. Elysia does not promise that data can never leave the machine; it promises no silent fallback or export.

The normal local launch path is:

```bash
./launch_elysia_dev.sh
```

The backend can also be launched directly on loopback:

```bash
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Useful local status checks:

```bash
curl -s http://127.0.0.1:8000/ | python -m json.tool
curl -s http://127.0.0.1:8000/status/health | python -m json.tool
curl -s http://127.0.0.1:8000/status/runtime | python -m json.tool
curl -s http://127.0.0.1:8000/status/capabilities | python -m json.tool
```

Frontend development:

```bash
npm --prefix apps/elysia-desktop run dev
```

Frontend typecheck/build:

```bash
npm --prefix apps/elysia-desktop run typecheck
npm --prefix apps/elysia-desktop run build
```

Tauri development:

```bash
npm --prefix apps/elysia-desktop run tauri -- dev --config src-tauri/tauri.launch.conf.json
```

## Expected local software

Exact local setup may evolve, but the repository currently expects or benefits from:

- Python environment for backend/runtime work
- FastAPI/Uvicorn backend stack
- Node.js and npm for the desktop frontend
- TypeScript/Vite/React for the chamber
- Rust/Cargo for the Tauri native shell
- Tauri CLI/tooling through the desktop app workflow
- Ollama/local model runtime for local model roles
- optional `openpyxl` for XLSX data summaries
- optional local SearXNG service for bounded public research when enabled

No website signup should be required for the local-first base path. Optional services or external tools may have their own setup requirements and privacy tradeoffs.

## Local models and Ollama assets

Elysia is designed to use local-first model runtimes such as Ollama.

Ollama itself does not require a website signup for local use, but downloading models uses the internet and stores model data outside this repository by default. This repository should document which local models Elysia expects, but should not vendor or publish downloaded model weights.

The repository has a `models/` folder reserved for Elysia's future local model asset strategy. It is intentionally separate from the source code that connects Elysia to models.

### What belongs in `models/`

The `models/` folder may later hold local model-related materials such as:

- local model inventory notes
- operator-created local model manifests
- local fine-tune experiment notes
- small safe metadata files describing available local models
- placeholders for future model asset organization

### What does not belong in `models/`

Do not commit large model weights, downloaded Ollama blobs, private training data, proprietary datasets, secrets, API keys, or personal/private conversation exports into `models/`.

Actual Ollama model files and downloaded model blobs are managed by Ollama outside this repository unless the operator deliberately configures a separate local storage strategy.

### Ollama connection code

Elysia's model connection and routing code belongs elsewhere in the repo, especially:

- `core/model_invoker.py`
- `core/model_routing.py`
- `config/models/model_roles.yaml`
- `config/models/routing.yaml`
- `modelfiles/`

Do not move model-invocation code into `models/` unless the architecture is deliberately changed later.

### Future custom models

Operators may later create custom local models or fine-tunes.

Training, dataset preparation, and model release decisions require separate care. In particular:

- do not train on private ChatGPT conversations by copying them into a publishable dataset
- do not include private files, journals, memory, or vault material
- do not publish model artifacts until licensing, privacy, and provenance are reviewed
- keep model experiments local unless the operator explicitly approves another governed boundary

The `models/` folder exists so Elysia has a clear future home for model-asset organization without confusing that with runtime connection code.

## Testing

Focused backend testing examples:

```bash
./scripts/test_backend.sh
./scripts/run_pytest.sh tests/test_part3_benchmark_config.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_part3_benchmark_config.py -q
```

Broader backend test command:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q
```

Frontend checks:

```bash
npm --prefix apps/elysia-desktop run typecheck
npm --prefix apps/elysia-desktop run build
```

Known caveat: some full-suite or TestClient route subsets have timed out in the current environment during recent benchmark work. Prefer focused tests for changed files, record timeouts honestly, and do not call a timed-out full suite “passed.”

## Repository map

```text
Elysia/
├── app/                    local API bridge, governance, memory application source
├── apps/elysia-desktop/    React/Vite/Tauri desktop chamber
├── config/                 policy, model, mode, worker, UI, benchmark law
├── core/                   governed runtime body
├── data/                   local runtime data
├── derived/                derived runtime prompt/system artifacts
├── docs/                   canon, contracts, architecture, reports, benchmarks
├── logs/                   local operational logs
├── memory/                 local journals and vector-memory state
├── modelfiles/             local Ollama role wrappers
├── sandbox/                bounded worker cages
├── scripts/                helper scripts
├── skills/                 YAML helper skills
├── tests/                  backend guardrail suite
└── vault/                  private/sealed storage
```

For the full architecture map, see:

```text
docs/architecture/Current_File_Tree_2026-06-01_Part3_Finishline.md
docs/architecture/Current_Architectural_Summary_2026-06-01_Part3_Finishline.md
docs/architecture/File_History.md
```

## Privacy and publishing cautions

Before publishing, sharing, or backing up broadly, review and usually exclude:

```text
vault/
data/
logs/
memory/
apps/elysia-desktop/node_modules/
apps/elysia-desktop/dist/
apps/elysia-desktop/src-tauri/target/
.pytest_cache/
__pycache__/
.env
secrets
local credentials
private journals
local conversations
ingested file contents
generated artifacts that contain private data
```

Also review:

- machine-specific paths
- personal names/contact details
- project-sensitive notes
- research strategy
- activism/legal/financial/health context
- logs or reports that include private prompt text

Private architecture can be specific. Public architecture should be sanitized.

## Development workflow

Recommended project workflow:

1. Define the contract or doctrine first.
2. Add schemas/config before power.
3. Build the smallest source change.
4. Add focused tests.
5. Run focused tests.
6. Run frontend typecheck/build if UI changed.
7. Manually verify live behavior if runtime/API behavior changed.
8. Update architecture/report docs when the system meaning changes.
9. Commit small coherent changes.
10. Do not mix cleanup, renames, and feature work in one commit.

For code-editing work, prefer careful inspection first, narrow patches, focused tests, broader tests, then commit.

## Current limitations

Elysia is not finished. Current known limitations include:

- file ingestion is useful but still v0/partial
- artifact output exists, but a full artifact browser is not complete
- request/evidence/tool ledger is live/partial and still maturing
- SearXNG research path is not broad web browsing
- page fetch is not live
- Aider is dry-run/skeleton truth only
- broad/free-form shell execution is not live; the exact read-only `git diff --check` lane is approval-gated and uses `shell=False`; npm/Cargo build-script entries remain policy-disabled until isolated and state-bound
- patch application and generic text-file create/edit/replace/delete/rename/move are live in source behind approved workspace roots, exact source/plan hashes, expiring one-time approval tokens, backups, and audit truth; live disposable-workspace proof is still required after each release change
- document, science/data/geospatial, and image/OCR/SVG stewardship is live per adapter in source; unsupported or missing-dependency operations must report a refusal/degraded state rather than disappear
- Codev chat is not yet a general coding-reasoning model; its deterministic Fibonacci transform is a contained contract fixture, while reviewed diffs and governed file/check controls use separate backend flows
- OpenHands is not live
- cloud consultation is not default
- long-term memory/governance remains carefully bounded
- ecological subsystem sovereigns are future architecture, not current runtime reality

## Roadmap posture

Near-term work should keep strengthening:

- architecture reconciliation
- request/evidence/tool ledger maturity
- file/data/artifact truth
- project continuity
- memory governance
- bounded research
- Coder safety
- capability truth
- focused benchmark suites

Riskier future work should remain separately gated:

- broad or autonomous patch generation/application beyond the current exact governed paths
- free-form shell command execution
- Git mutation
- page fetch
- browser automation
- OpenHands
- broader cloud assistance
- ecological domain modules with sensors/robots

The order matters:

```text
truth surfaces before automation
evidence before web power
approval before mutation
sandbox before risky workers
local before cloud
privacy before convenience
```

## License and publication status

Elysia source in this repository is licensed under the [Apache License 2.0](LICENSE), subject to separately identified third-party licenses. Version `1.0.0` is the qualified stable release; exact downloadable artifacts remain authoritative only when their hashes and signatures match the canonical release manifest.

The completed release gate in [`V1_RELEASE_GATE.md`](docs/release/V1_RELEASE_GATE.md) covers packaging, authentication, XDG state paths, public/private hygiene, documentation, manual review, and explicit release approval. Optional profiles may download packages/models or contact external services only after their exact boundary is enabled and approved.

## Final summary

Elysia is becoming a serious local companion-intelligence architecture: a governed runtime body, a local bridge, a desktop chamber, policy law, memory discipline, bounded workers, evidence structures, Coder posture, local execution helpers, and request-ledger truth.

The central promise is not that Elysia can do everything recklessly. The promise is that she can become powerful without becoming leaky, manipulative, untruthful, cloud-dependent, or ungoverned.

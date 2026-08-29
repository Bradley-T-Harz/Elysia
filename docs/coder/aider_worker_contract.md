# Sprint 7A: Aider Worker Contract and Threat Model

## 1. Purpose

The Aider worker is a future governed coding-worker lane for Elysia. It exists to help with selected repository work only after the Private Core has interpreted the request, planned the work, checked policy, and decided whether a worker lane is appropriate.

The Aider worker is not Elysia's brain. It is not the UI. It is not an autonomous developer. It is not a general shell. It is not allowed to roam the operator's computer. It is a bounded worker that may eventually help prepare or apply code changes inside approved repositories, but only through explicit policy, approval, traceability, verification, and UI truth.

In Sprint 7A, this document defines the law before the worker exists.

## 2. Governing principle

The Aider worker must obey the same operating law as the rest of Elysia:

```text
understand -> plan -> check -> maybe ask -> act -> verify -> log
```

It must never behave like:

```text
ask -> mutate -> rationalize afterward
```

Elysia's growth must balance capability with moral containment. The Aider worker may eventually become one of Elysia's hands, but it must begin as a hand behind glass.

## 3. Current Sprint 7A status

For 7A:

```text
No worker is implemented.
No Aider subprocess is invoked.
No files are mutated.
No shell commands are run.
No tests are run by the worker.
No git state is changed.
No network is used.
No cloud model is used.
No secrets are read.
No vault access is permitted.
```

7A defines the contract and threat model only.

## 4. Worker identity

The Aider worker is:

```text
worker_key: aider_worker
worker_kind: governed_coding_worker
initial_state: contract_only
future_runtime_area: sandbox/aider_worker/
default_mode: dry_run_only
default_trust_posture: local_first_no_mutation
```

Its future role is to support:

```text
repo-aware code review
patch proposal
diff preparation
selected-file reasoning
test recommendation
rollback planning
eventual approval-gated patch application
```

It must not become:

```text
an unrestricted coding agent
a host shell
a package installer
a git automation bot
a web researcher
a credential reader
a vault inspector
a hidden cloud model bridge
a silent editor
```

## 5. Default posture

All dangerous powers are off by default.

```text
dry_run_only: true
network_allowed: false
shell_allowed: false
mutation_allowed: false
git_mutation_allowed: false
package_install_allowed: false
credentials_allowed: false
vault_allowed: false
home_access_allowed: false
cloud_model_allowed: false
external_worker_invocation_allowed: false
approval_required_before_mutation: true
human_review_required: true
```

These defaults are not temporary decoration. They are the baseline safety posture.

## 6. What repo may it touch?

The Aider worker may only touch repositories explicitly approved in configuration.

Initial approved repo assumption:

```text
repo_key: elysia
trust_zone: project_local
root: .
allowed: true
```

Repo access is allowed only when:

```text
the repo is listed in approved repo config
the request is coding-related
the request is in Coder mode or classified as coding/debugging
the repo is selected by repo_key, not by broad filesystem path
policy confirms that the repo is allowed
```

Repo access is blocked when:

```text
the repo is not configured
the input is an arbitrary absolute path
the input is ~ or /home/...
the request asks to scan all projects
the request targets private, vault, secrets, or credential material
the repo root cannot be resolved safely
the repo root is outside the approved project boundary
```

## 7. What files may it see?

The worker may only see safe, relevant, source-like files inside the approved repo.

Permitted file categories:

```text
source code
tests
documentation
safe config files
API contract docs
UI contract docs
package/build metadata when needed
explicit files named by the operator
files surfaced by bounded repo context
```

Examples:

```text
core/runtime.py
core/planner.py
core/policy_gate.py
core/verifier.py
core/responder.py
core/repo_context_gatherer.py
core/code_patch_formatter.py
config/coder/approved_repos.yaml
config/policies/approval_rules.yaml
docs/api/*.yaml
apps/elysia-desktop/src/*.tsx
tests/test_runtime_coder_mode_flow.py
```

Even when files are allowed, the worker should prefer minimal necessary context. Thoroughness means traceable and scoped, not indiscriminate ingestion.

## 8. What files must it never see?

The worker must never read or receive raw contents from:

```text
vault/
secrets/
credentials/
private/
browser_profiles/
.env
.env.local
.env.production
.env.development
API key files
tokens
password files
SSH private keys
known_hosts
authorized_keys
private journals
sealed_private memory
audit memory raw records
generated memory databases
raw personal files unrelated to the coding task
```

The worker must also avoid generated, heavy, or dependency folders unless a future narrow policy explicitly allows metadata-only treatment:

```text
.git/
node_modules/
dist/
build/
target/
.venv/
venv/
env/
__pycache__/
.pytest_cache/
memory/chroma/
data/conversations/
data/artifacts/
data/file_ingest/raw/
data/file_ingest/extracted/
generated session journals
```

For Sprint 7, the simpler rule is:

```text
No vault.
No secrets.
No credentials.
No private journals.
No home-wide access.
No generated memory stores.
```

## 9. Can it write?

For 7A:

```text
No.
```

Future writing may be considered only after all of the following exist:

```text
safe patch proposal exists
diff preview exists
selected files are safe
no sealed paths are touched
explicit human approval is attached to request_id
rollback plan exists
request trace exists
mutation result can be verified
UI can show exactly what changed
```

The future sequence must be:

```text
propose -> review -> approve -> apply -> verify -> test separately -> commit separately
```

Patch approval is not commit approval. Test approval is not push approval. Each boundary is separate.

## 10. Can it run shell?

For 7A:

```text
No.
```

Future shell execution must belong to a separate command-gate lane, not raw Aider freedom.

Future shell execution requires:

```text
exact command preview
command risk classification
repo-local working directory
no sudo by default
no package install without explicit approval
no service changes without explicit approval
no destructive commands without high-boundary approval
stdout/stderr captured
exit code captured
trace recorded
UI truth surfaced
```

In Sprint 7, the worker may suggest commands but must not run them.

## 11. Can it run tests?

For 7A:

```text
No.
```

The worker may recommend tests:

```text
tests_requested:
  - ./scripts/test_backend.sh -q
  - npm --prefix apps/elysia-desktop run typecheck
  - npm --prefix apps/elysia-desktop run build

tests_run: []
```

Future test execution may be allowed only through a command gate with exact approved commands.

## 12. Can it use network?

For 7A:

```text
No.
```

Network access is not a default coding capability. It is a boundary crossing.

Future network use requires:

```text
explicit user request
research/scout policy route
public/private separation
no private repo leakage by default
evidence packet or trace record
UI shows External or Sandboxed state
```

If the task needs dependency docs or public issue lookup, that belongs to a governed research worker, not to the Aider worker by default.

## 13. Can it use cloud models?

For 7A:

```text
No.
```

Cloud model use requires a separate future approval boundary because code, repo context, prompts, and file snippets may leave local control.

Future cloud-model approval must specify:

```text
provider
model/provider class
exact purpose
repo/files included
privacy warning
whether secrets were excluded
whether private memory was excluded
approval token
trace record
```

Default Aider posture should prefer local model endpoints. Any cloud model use must be explicit, narrow, revocable, and never identity-bearing by default.

## 14. Can it read secrets?

No.

The worker must not read raw secrets at any stage of Sprint 7.

Future secret hygiene support may expose only sanitized metadata:

```text
.env file exists but content was not read
credential-looking path blocked
SSH key path detected but content was not read
secret-like filename refused
```

## 15. Can it inspect vault?

No.

The vault is a sealed/private zone. For the Aider worker, vault inspection is forbidden by default.

Future Elysia Private Core workflows may reason about vault policy separately, but raw vault content must not be handed to the Aider worker.

## 16. What counts as approval?

Approval must be explicit, fresh, narrow, and tied to a real request.

Not approval:

```text
"sure"
"go ahead" with unclear scope
prior general preference
Coder mode selection
file visibility
patch plan creation
repo approval alone
```

Valid approval must include:

```text
request_id
repo_key
action type
files_to_touch or exact command
boundary being crossed
approval decision
timestamp
user note when relevant
trace record
```

Examples of valid narrow approval:

```text
Approve applying the proposed patch to these files only:
- core/planner.py
- tests/test_runtime_coder_mode_flow.py

Do not run shell commands.
Do not use network.
Do not commit.
```

```text
Approve running this exact command only:
./scripts/test_backend.sh -q
```

```text
Approve committing these already-reviewed changes with this exact commit message:
<message>
```

Each action needs its own approval. Applying a patch does not authorize running tests. Running tests does not authorize committing. Committing does not authorize pushing.

## 17. What gets logged?

Worker-related logs must include enough to audit behavior without becoming a private-data dump.

Required trace/log fields:

```text
request_id
timestamp_utc
worker_key
worker_state
repo_key
repo_root_summary
trust_zone
user_goal_summary
mode
selected_files
allowed_paths
denied_paths
dry_run_only
network_allowed
shell_allowed
mutation_allowed
git_mutation_allowed
package_install_allowed
cloud_model_allowed
credentials_allowed
vault_allowed
home_access_allowed
approval_state
approval_token_present
files_considered
files_proposed
diff_preview_present
diff_preview_hash_or_summary
commands_requested
commands_run
tests_requested
tests_run
worker_used
aider_invoked
mutated_files
network_used
shell_used
git_mutation_used
external_model_used
refusal_reasons
warnings
errors
result_status
trace_summary
```

Do not log:

```text
raw secrets
raw vault contents
full private journals
API keys
tokens
passwords
SSH key material
unnecessary personal memory
large file contents
entire generated artifacts unless already intended as artifacts
```

## 18. What must the UI show?

The UI must show truth, not vibes.

Required Aider worker UI fields:

```text
Worker: Aider
State: contract_only / planned / skeleton / dry_run / blocked / unavailable / live_later
Repo: selected approved repo
Trust zone: project_local
Mode: dry-run only
Mutation: not live or approval needed
Shell: blocked
Tests: not run
Network: blocked
Cloud model: not used
Files considered
Files proposed
Diff preview status
Approval needed
Refusal reasons
Warnings
Trace summary
```

Use Elysia's stable trust language:

```text
Local
Read-only
Draft only
Approval needed
Sandboxed
External
Blocked
```

The UI must never say:

```text
Aider fixed it
tests passed
files changed
patch applied
committed
pushed
```

unless the backend trace proves that specific action actually happened.

## 19. What happens when the worker refuses?

Refusal is a valid safety outcome.

A refusal must return a structured blocked result:

```text
status: blocked
worker_used: false
aider_invoked: false
repo_key: <repo_key or empty>
files_considered: []
files_proposed: []
diff_preview: null
commands_requested: []
commands_run: []
tests_requested: []
tests_run: []
mutated_files: false
network_used: false
shell_used: false
git_mutation_used: false
external_model_used: false
approval_required: false or true depending on boundary
refusal_reasons:
  - specific reason
warnings:
  - no files were changed
trace_summary:
  - policy blocked unsafe boundary
```

Examples of refusal reasons:

```text
repo key is not approved
path escapes approved repo
path targets vault/
path targets secrets/
path looks credential-bearing
mutation requested but mutation_allowed=false
shell requested but shell_allowed=false
network requested but network_allowed=false
cloud model requested but cloud_model_allowed=false
home-wide access requested
git mutation requested without approval
```

The UI should say:

```text
Aider worker refused safely.
```

not:

```text
Aider failed.
```

## 20. Threat model

| Threat | What could go wrong | Prevention |
|---|---|---|
| Filesystem overreach | Worker reads outside selected repo | Approved repo allowlist, repo_key required, block absolute/home/traversal paths |
| Secret leakage | Worker sees `.env`, keys, tokens, vault, journals | Deny secret-looking names, deny sealed folders, never pass raw secrets |
| Silent mutation | Worker edits before approval | `mutation_allowed=false`, dry-run default, approval token required later |
| Shell escape | Worker runs host-affecting commands | `shell_allowed=false`, future command gate only |
| Network leakage | Code/private context leaves machine | `network_allowed=false`, future research/scout route only |
| Git mutation | Worker commits, resets, pushes, checks out branches | `git_mutation_allowed=false`, separate future git approval |
| Dependency/install risk | Worker installs packages or runs unknown scripts | `package_install_allowed=false`, future package approval gate only |
| False UI truth | UI claims worker fixed something | Structured result truth, verifier checks, UI renders backend state only |
| Worker confusion | Aider claims it changed files or ran tests | Wrapper result overrides model prose; responder must prefer structured truth |

## 21. Capability timing ladder

| Capability | Correct time |
|---|---|
| Read approved repo structure | Coding-related request, approved repo, read-only posture |
| Read specific safe files | Files are inside approved repo and relevant to task |
| Propose patch plan | User asks for code change and files are safe |
| Show diff preview | After proposal exists, before mutation |
| Write files | Future only, after explicit request-bound approval |
| Run tests | Future command gate only, exact approved command |
| Run shell | Future command gate only, never broad host shell |
| Use network | Future research/scout policy only |
| Use cloud model | Future explicit external-use approval with privacy warning |
| Read secrets | Never for Aider worker |
| Inspect vault | Never for Aider worker |
| Commit | Future separate git approval only |
| Push/publish | Future high-boundary approval only |

## 22. Machine-shaped contract fields

### AiderWorkerRequest

```text
request_id: string
worker_key: "aider_worker"
repo_key: string
repo_root: string
trust_zone: string
user_goal: string
mode: "contract_only" | "dry_run" | "proposal" | "future_apply"
allowed_paths: list[string]
denied_paths: list[string]
selected_files: list[string]
dry_run_only: bool
network_allowed: bool
shell_allowed: bool
mutation_allowed: bool
git_mutation_allowed: bool
package_install_allowed: bool
credentials_allowed: bool
vault_allowed: bool
home_access_allowed: bool
cloud_model_allowed: bool
approval_token: string | null
model_provider_policy:
  provider_kind: "local_only" | "external_possible"
  external_allowed: bool
  privacy_notice_required: bool
privacy_notice: string
trace_parent_id: string | null
```

### AiderWorkerResult

```text
status: "contract_only" | "dry_run_ready" | "blocked" | "failed" | "completed_later"
worker_key: "aider_worker"
worker_used: bool
aider_invoked: bool
repo_key: string
repo_root: string
trust_zone: string
files_considered: list[string]
files_proposed: list[string]
diff_preview: string | null
diff_preview_hash: string | null
commands_requested: list[string]
commands_run: list[string]
tests_requested: list[string]
tests_run: list[string]
mutated_files: bool
network_used: bool
shell_used: bool
git_mutation_used: bool
package_install_used: bool
external_model_used: bool
approval_required: bool
approval_reason: string
refusal_reasons: list[string]
warnings: list[string]
errors: list[string]
trace_summary:
  request_id: string
  boundary_flags: list[string]
  locality: "local"
  read_only: bool
  dry_run_only: bool
```

## 23. 7A acceptance criteria

7A is complete when the project has a written contract that clearly defines:

```text
what the Aider worker is
what it may receive
what it may do
what it may never touch
what it must return
what requires approval
what gets logged
what the UI must show
how refusal works
how privacy is protected
```

And it explicitly says:

```text
No worker yet.
No mutation yet.
No shell yet.
No tests yet.
No git mutation yet.
No network yet.
No cloud model yet.
No vault access ever by default.
```

## 24. Final 7A doctrine

The Aider worker may eventually become one of Elysia's hands, but it must begin as a hand behind glass.

First it may point.

Later it may draft.

Only much later may it touch.

And when it touches, the touch must be narrow, approved, reversible, logged, and honestly shown.

That is Sprint 7A.

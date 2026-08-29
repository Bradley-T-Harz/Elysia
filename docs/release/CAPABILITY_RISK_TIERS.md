# Elysia v1.0 Capability Risk Tiers

Capability classification determines default exposure, prerequisites, and proof. It is not a judgment that a powerful capability should never be built.

## Tier 1 — Core v1 default

Criteria:

- local and low-risk by default;
- bounded input/output;
- no silent external boundary;
- no physical actuation;
- no unrestricted host execution;
- useful without giant optional stacks;
- truthful degraded behavior;
- tested receipts where operations occur.

Representative capabilities: conversations, projects, local identity, text/code/file stewardship, bounded common metadata/preview, artifacts, requests/traces, read-only governance/capabilities/health, archive inspection/selected extraction, database schema-only inspection, binary static inspection, and engineering static reports/projections.

## Tier 2 — Optional v1 profile

Criteria:

- deliberate user selection;
- dependency and resource declaration;
- doctor prerequisites;
- clear network/download/private-data truth;
- safe disable/uninstall behavior;
- existing policy and operation approvals still apply.

Representative capabilities: Workstation adapters, bounded public research, Creator media, Developer/Codev, and a manual governed outbound queue.

## Tier 3 — v1 Lab / Developer-gated

Criteria:

- experimental, high-resource, or higher-authority;
- hidden outside its selected advanced profile;
- disabled until doctor passes;
- exact bounded scope and user acknowledgement;
- resource/time/network/mount limits;
- stop, cancel, revoke, or recovery path;
- operation receipt and negative safety tests.

Representative capabilities: Pursue Goal bounded loops, heavy EngineeringForge, VideoForge, Reference Voice Lab, add-on execution inside a proven local sandbox, and advanced governance mutations.

## Tier 4 — Hard-prohibited by default

These actions must never happen silently or as a side effect of selecting an ordinary profile:

- silent cloud fallback;
- unapproved outbound posting or sending;
- unconsented voice cloning or impersonation;
- raw private logs, paths, credentials, prompts, or transcripts in normal UI;
- archive install/execute/import merely because a container was opened;
- arbitrary host shell or package scripts;
- physical control without a hardware-specific profile, exact device binding, and final approval;
- add-on code execution without a proven local sandbox and effective permissions.

Hard-prohibited by default does not remove safe static, explanation, planning, simulation, or future explicitly governed forms.

## Disputed capability placement

| Capability | Tier | Promotion requirements |
|---|---|---|
| Pursue Goal | Tier 3 Developer Lab | Approved repo, goal/budget, checkpoints, stop/recovery, test evidence, mutation approval, no hidden push |
| Heavy EngineeringForge | Tier 3 Creator/Engineering Lab | Local isolation proof, allowlisted mounts, resource limits, doctor, cancellation |
| G-code/ROS static analysis and simulation planning | Tier 1 or 2 by dependency | Non-actuating parser/preview contract and safety labeling |
| Actual controller/machine actuation | Tier 4 default | Future hardware profile, exact device binding, simulation/checklist, final approval, receipt |
| Reference voice | Tier 3 | Consent/provenance, local assets, labeling, impersonation refusal, deletion/revocation |
| Unconsented voice cloning | Tier 4 default | Prohibited |
| ImageForge | Tier 2 Creator target | Model/license/provenance/resource doctor, cancellation, output receipt |
| VideoForge | Tier 3 Creator Lab | Fixed profiles, provenance, resource ceilings, cancellation, durable job truth |
| Governance autonomy/outbound changes | Tier 3 advanced governance | Plan/consequence preview, config hash, final approval, backup/restore, audit |
| Publish queue | Tier 2 optional outbound | Draft, preview, destination bind, final approval, receipt |
| Archive inspection/extraction | Tier 1 | Existing bounded policies and exact extraction approval |
| Archive install/execute/import | Tier 4 default | Future separately governed installer trust system |
| Add-on code execution | Tier 3 | Local sandbox, signing/compatibility, effective permissions, revocation, receipts |
| Silent cloud fallback | Tier 4 default | Must remain off |
| Raw private diagnostics in UI | Tier 4 default | Sanitized summaries only |

## Promotion rule

```text
capability contract
→ profile placement
→ dependency and doctor truth
→ UI consequences
→ policy classification
→ exact approval where required
→ bounded local execution
→ receipt
→ stop/revoke/rollback where possible
→ release tests
```

No feature is promoted merely because its code or dependency is present.

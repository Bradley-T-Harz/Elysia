# Sprint 8: Research Evidence Contract

## Purpose

Sprint 8 creates the research evidence law before Elysia receives live web power.

Goal:

Evidence packets exist before live web power.

Elysia must be able to represent, validate, inspect, and refuse weak research evidence before she can perform live web research.

This sprint is not about making Elysia browse. It is about making Elysia structurally unable to treat unsupported web-like claims as trustworthy evidence.

## Future bounded research path

Future bounded research should eventually follow this path:

planner -> policy gate -> research ticket -> SearXNG worker -> optional fetch worker -> evidence packet -> verifier -> response -> trace ledger

Sprint 8 only builds the contract, schema, verifier, contradiction scan, and tests needed before those workers exist.

## Sprint 8 boundaries

Sprint 8 must not add:

- live web browsing
- SearXNG calls
- page fetching
- HTTP client calls
- network use
- cloud search
- external API calls
- research worker execution
- background research queues
- private context sent outward
- private memory sent outward
- source scraping
- automatic citation generation from live pages
- automatic claim truth verification
- frontend research controls

The Requests page may continue to show evidence packets as planned or empty truth only. It must not imply that evidence packets, live research, citations, or bounded web search are live before they are actually live.

## 8A: Evidence packet contract

An evidence packet is a structured record saying:

- this source said this
- this is when the source was retrieved, recorded, or supplied
- this is the claim it supports, limits, or contradicts
- this is the confidence level
- this is what contradicts or limits it
- this is whether any private context crossed the boundary

An evidence packet is not proof by itself. It is a traceable unit of support, contradiction, or uncertainty.

## Required evidence packet fields

The first schema must include:

- source_url
- title
- retrieved_at_utc
- snippet
- claim
- confidence
- contradiction_notes
- source_type
- retrieval_method
- outward_boundary_state
- private_context_sent

## Recommended optional evidence packet fields

The schema may also include:

- evidence_id
- source_rank
- source_date
- publisher
- authors
- license_or_access_notes
- quote_span
- supports_claim
- warnings
- errors
- network_access_used
- page_fetch_used
- live_web_research_used
- contract_note

## Evidence source types

Initial source type vocabulary:

- primary
- secondary
- reference
- news
- academic
- government
- commercial
- unknown

These labels are descriptive only. They do not prove trustworthiness by themselves.

## Evidence retrieval methods

Initial retrieval method vocabulary:

- not_live
- user_provided
- local_cache
- future_search
- future_fetch

future_search and future_fetch describe planned future behavior only. They do not mean search or fetch is live.

Sprint 8 should default to not_live unless the packet clearly represents user-provided or local-cache evidence.

## Evidence confidence values

Initial confidence vocabulary:

- unknown
- low
- medium
- high

Confidence is about the packet's evidentiary usefulness, not absolute truth.

High confidence should require meaningful source and snippet support. A high-confidence packet with weak source support should be warned or rejected by the verifier.

## Evidence outward boundary states

Initial outward boundary state vocabulary:

- local_contract_only
- external_boundary_planned
- external_boundary_crossed
- unknown

For Sprint 8, evidence packets should normally use local_contract_only.

Future planned tickets may use external_boundary_planned.

Sprint 8 must not produce external_boundary_crossed because no outward research worker is live.

## Evidence private context rule

Default:

private_context_sent: false

Sprint 8 must not send private context outward.

Any future outward research that includes private context must require explicit policy, approval, trace, and UI truth. That is not live in Sprint 8.

## Evidence live-power flags

Evidence packets should include or preserve these safety truths when relevant:

- network_access_used: false
- page_fetch_used: false
- live_web_research_used: false
- private_context_sent: false

For Sprint 8, these must remain false.

## 8B: Research ticket contract

A research ticket is not a search. It is a structured plan or record for a research task.

A research ticket answers:

- what question are we trying to answer?
- what kind of sources are acceptable?
- is live research needed?
- is live research enabled?
- is query execution allowed?
- is retrieval allowed?
- is private context allowed outward?
- was private context sent outward?
- what evidence packets are attached?
- what blocked or failed?

## Required research ticket fields

The first schema should include:

- ticket_id
- question
- status
- research_scope
- allowed_source_types
- disallowed_source_types
- requires_peer_reviewed_sources
- requires_primary_sources
- requires_recent_sources
- evidence_packets
- created_at_utc
- completed_at_utc
- requires_live_research
- live_research_enabled
- query_execution_allowed
- retrieval_allowed
- private_context_allowed
- private_context_sent
- outward_boundary_state
- network_access_used
- page_fetch_used
- live_web_research_used
- approval_required
- notes
- warnings
- errors
- contract_note

## Research ticket statuses

Initial ticket statuses:

- planned
- blocked
- completed
- failed

## Research scopes

Initial scope labels:

- general
- academic
- technical
- legal_policy
- environmental
- medical_health
- financial
- unknown

These are routing and expectation labels only. They do not authorize live research.

## Sprint 8 default ticket posture

For Sprint 8, research tickets must default to:

- status: planned
- live_research_enabled: false
- query_execution_allowed: false
- retrieval_allowed: false
- private_context_allowed: false
- private_context_sent: false
- network_access_used: false
- page_fetch_used: false
- live_web_research_used: false
- outward_boundary_state: local_contract_only

## Approval rule

Sprint 8 does not perform outward research.

Future outward research may require approval, especially when:

- a query would leave the local machine
- a page would be fetched
- private or project-specific context might be included
- a source would require login
- a source would require cloud or API access
- a query could reveal sensitive research direction

In Sprint 8, this should remain planned truth, not live behavior.

## 8C: Evidence verifier contract

The evidence verifier should live outside schemas, likely in:

core/evidence_verifier.py

The verifier must not browse, fetch, call models, call HTTP clients, invoke workers, or use network.

It should only inspect structured evidence packets and research tickets.

## Evidence packet checks

The verifier should check:

- source_url is present and non-empty
- title is present and non-empty
- retrieved_at_utc is present and parseable
- snippet is present and bounded
- claim is present and bounded
- confidence is valid
- contradiction_notes exists, even if empty
- source_type is valid
- retrieval_method is valid
- outward_boundary_state is explicit
- private_context_sent is false
- network_access_used is false
- page_fetch_used is false
- live_web_research_used is false

## Evidence packet failures

The verifier should fail or warn when:

- private_context_sent is true
- network_access_used is true
- page_fetch_used is true
- live_web_research_used is true
- outward_boundary_state is external_boundary_crossed
- source_url is missing for web-like evidence
- claim is empty
- snippet is empty
- snippet is too long
- high confidence lacks meaningful source or snippet support
- retrieval_method suggests live behavior during Sprint 8

## Research ticket checks

The verifier should check:

- ticket_id is present
- question is present
- status is valid
- evidence_packets is a list
- live_research_enabled is false
- query_execution_allowed is false
- retrieval_allowed is false
- private_context_allowed is false
- private_context_sent is false
- network_access_used is false
- page_fetch_used is false
- live_web_research_used is false
- outward_boundary_state is not external_boundary_crossed

## Research ticket failures

The verifier should fail when:

- completed ticket has no evidence packets
- blocked ticket has no errors
- failed ticket has no errors
- live research is enabled
- query execution is allowed
- retrieval is allowed
- private context is allowed outward
- private context was sent outward
- network access was used
- page fetch was used
- live web research was used
- external boundary was crossed

## 8D: Contradiction scan contract

The contradiction scanner should live outside schemas, likely in:

core/contradiction_scan.py

It is a deterministic warning engine, not a truth oracle.

It must not:

- browse
- fetch
- call models
- call HTTP clients
- use network
- decide final truth

## Local contradiction scan signals

The first contradiction scanner may flag:

- possible negation conflict between similar claims
- possible numeric mismatch between similar claims
- possible date mismatch between similar claims
- absolute language with low confidence
- possible contradiction without contradiction_notes

## Negation conflict heuristic

A local-only heuristic may flag a possible contradiction when one claim contains terms such as:

- not
- no
- never
- false
- incorrect
- does not
- cannot

and another claim has overlapping important words but lacks negation.

## Numeric/date mismatch heuristic

A local-only heuristic may flag a possible contradiction when claims share important words but contain different numbers, years, dates, percentages, or quantities.

## Absolute-language heuristic

A local-only heuristic may warn when low-confidence evidence uses language such as:

- proves
- always
- never
- definitely
- certainly
- impossible
- guaranteed

The scanner should not decide that the claim is false. It should surface the need for caution.

## 8E: Tests contract

Sprint 8 tests should prove:

- evidence packet schema serializes safely
- research ticket schema serializes safely
- schemas reject unexpected fields
- required fields are enforced
- default live, network, and private-context flags are false
- valid contract-only evidence passes verifier
- valid contract-only ticket passes verifier
- private_context_sent true fails verification
- network_access_used true fails verification
- page_fetch_used true fails verification
- live_web_research_used true fails verification
- external_boundary_crossed fails verification
- completed ticket with no evidence fails verification
- blocked or failed ticket with no errors fails verification
- high confidence with weak source or snippet support warns or fails
- contradiction without notes is flagged
- contradiction with notes is recorded safely
- full backend tests pass

Preferred test files:

- tests/test_evidence_schemas.py
- tests/test_evidence_verifier.py
- tests/test_contradiction_scan.py

## Preferred Sprint 8 files

Preferred new files:

- app/api/schemas/evidence.py
- app/api/schemas/research.py
- core/evidence_verifier.py
- core/contradiction_scan.py
- tests/test_evidence_schemas.py
- tests/test_evidence_verifier.py
- tests/test_contradiction_scan.py

## Files to avoid touching in the first implementation pass

Avoid modifying unless explicitly approved:

- core/runtime.py
- core/planner.py
- core/policy_gate.py
- app/api/runtime_bridge.py
- app/api/request_trace_service.py
- app/api/routes/requests.py
- app/api/capability_service.py
- app/api/status_service.py
- apps/elysia-desktop/src/RequestsPage.tsx
- frontend files generally

The Requests page already has the correct planned truth posture for evidence packets. Do not make evidence appear live before backend research evidence exists.

## Acceptance criteria

Sprint 8 is complete when:

- evidence packet schema exists
- research ticket schema exists
- evidence verifier exists
- contradiction scan exists
- tests prove JSON-safe schema behavior
- tests prove no live web, network, or private-context defaults
- tests prove malformed or risky packets fail verification
- tests prove contradiction warnings are surfaced
- backend tests pass
- no live web, search, or fetch worker exists
- no SearXNG integration exists
- no private context leaves local control

## Final doctrine

Research power without evidence discipline becomes confident rumor.

Sprint 8 gives Elysia the discipline first.

No live web yet.
No private context outward.
No query execution.
No worker.
No browser.
Evidence law first.

# Sprint 9A: SearXNG Worker Contract and Threat Model

## 1. Purpose

Sprint 9A defines the law for bounded public web research before Elysia receives live web-research authority.

This is the web-research equivalent of the Aider worker contract.

Goal:

Bounded public web research works through a worker, not the core.

The core must not become a browser.

The core may plan, gate, delegate, verify, summarize, and log.

The SearXNG worker is the only component that may perform the narrow outward public-search action, and only under this contract.

## 2. What this contract creates

This contract defines:

- what the SearXNG worker is
- what it may receive
- what it may send outward
- what it may never receive
- what it returns
- what gets logged
- what requires approval
- how refusal works
- what the UI must show

This contract does not create live research by itself.

## 3. What Sprint 9A must not do

Sprint 9A must not add:

- live SearXNG calls
- live web browsing
- page fetching
- HTTP client behavior
- network behavior
- cloud search
- cloud model research
- private context outward
- research route behavior
- runtime chat integration
- frontend research controls
- background autonomous research
- automatic citation generation from live pages

This file is contract and threat model only.

## 4. Future bounded research path

Future bounded research should follow this path:

planner -> policy gate -> research ticket -> SearXNG worker -> optional fetch worker -> evidence packet -> verifier -> response -> trace ledger

Sprint 9A defines the SearXNG worker boundary inside that future path.

## 5. Core doctrine

The SearXNG worker is a narrow public-search limb.

It is not the brain.

It is not a general browser.

It is not a scraper.

It is not a cloud research agent.

It is not allowed to receive private memory, private files, vault contents, credentials, journals, hidden project notes, or unsanitized private context.

It may only receive approved public query text and the minimum metadata needed to perform a bounded search.

## 6. What the SearXNG worker is

The SearXNG worker is a sandboxed research worker that sends bounded public search queries to a configured local SearXNG instance.

Preferred local service posture:

- SearXNG service: local loopback
- Search boundary: external public web
- Core network access: not allowed
- Worker network access: allowed only for bounded public search
- Private context outward: false
- Cloud search: false by default
- Cloud model use: false by default
- Page fetch: false for the first pass

A self-hosted local SearXNG path should not require a website signup.

However, local SearXNG does not mean the research stays fully local. Search query terms may leave local control because SearXNG contacts upstream search engines. The UI and trace ledger must show this.

## 7. What the worker may receive

The worker may receive:

- request_id
- ticket_id
- question
- public queries
- allowed source types
- disallowed source types
- requires recent sources flag
- requires primary sources flag
- requires peer-reviewed sources flag
- max queries per ticket
- max results per query
- timeout seconds
- safe search setting
- language or region preference, if configured
- approval token, if required and granted
- trace context with no private content

The worker may receive only what is necessary for public search.

The worker must prefer sanitized query text over raw user text.

## 8. What the worker may send outward

The worker may send outward only:

- approved public query terms
- bounded SearXNG search parameters
- safe search, category, and language options

The worker must not send outward:

- private files
- private memory
- vault content
- journals
- chat history
- credentials
- API keys
- SSH keys
- tokens
- local file paths
- home directory paths
- project secrets
- user contact details
- private names unless explicitly public and necessary
- medical, legal, or financial personal details without approval
- large copied private text
- hidden project context

## 9. What the worker must never receive

The worker must never receive:

- .env files
- vault contents
- SSH keys
- API keys
- tokens
- passwords
- credentials
- private journals
- raw memory stores
- private embeddings
- full chat history
- private file contents
- local repository contents
- personal contact lists
- home directory contents
- sensitive hidden project notes
- unreviewed private context blocks

If any of these appear in a proposed query or request payload, the worker must refuse or require approval before any outward network action.

## 10. What the worker returns

The worker should return a structured result.

Suggested result fields:

- status
- worker_key
- worker_used
- searxng_used
- request_id
- ticket_id
- queries_requested
- queries_sent
- results_considered
- evidence_packets
- network_access_used
- page_fetch_used
- private_context_sent
- cloud_search_used
- cloud_model_used
- approval_required
- refusal_reasons
- warnings
- errors
- trace_summary

Truth fields must be explicit.

A successful live search result should truthfully say:

- worker_used: true
- searxng_used: true
- network_access_used: true
- private_context_sent: false
- cloud_search_used: false
- cloud_model_used: false
- page_fetch_used: false

A blocked result should truthfully say:

- worker_used: false
- searxng_used: false
- queries_sent: []
- network_access_used: false
- private_context_sent: false
- cloud_search_used: false
- cloud_model_used: false
- page_fetch_used: false

## 11. Evidence packet output

Search results must be converted into evidence packets.

Search-result evidence packets should normally use:

- source_url: result URL
- title: result title
- retrieved_at_utc: current UTC timestamp
- snippet: result snippet or content returned by SearXNG
- claim: cautious claim derived from the query/result relationship
- confidence: low or unknown by default
- contradiction_notes: []
- source_type: unknown unless safely inferred
- retrieval_method: searxng_search once schema supports it
- outward_boundary_state: external_boundary_crossed
- private_context_sent: false
- network_access_used: true
- page_fetch_used: false
- live_web_research_used: true

Search snippets are not primary evidence.

Search snippets must not be treated as final truth.

The evidence verifier and contradiction scan must run after packet creation.

## 12. Contract defaults

Default posture:

- live_research_enabled: false
- searxng_base_url: http://127.0.0.1:<port>
- public_query_only: true
- private_context_allowed: false
- private_context_sent: false
- cloud_search_allowed: false
- cloud_model_allowed: false
- page_fetch_allowed: false
- network_access_allowed: true
- network_access_scope: worker_public_search_only
- core_network_access_allowed: false
- search_results_first: true
- max_queries_per_ticket: 3
- max_results_per_query: 5
- all_queries_logged: true

Important:

The worker may use network only for the specific approved public search action.

The core must still not receive general network behavior.

## 13. Search-results-first rule

Sprint 9 should use search results first.

The worker should not fetch pages during the first pass.

Page fetching adds additional risks:

- SSRF
- localhost access
- private-network access
- metadata-service access
- tracking
- large page bodies
- HTML/script content
- prompt injection from webpages
- copyright issues
- login-gated content
- malware-like content

If page fetching is ever added, it must be a separate fetch worker or a separate guarded mode with its own threat model.

## 14. Approval rules

Approval is required before outward action when a proposed query appears to contain or reveal:

- private memory
- private file contents
- vault references
- credentials
- API keys
- tokens
- SSH keys
- .env content
- local paths
- repo paths
- home directory paths
- private journals
- email addresses
- phone numbers
- home addresses
- medical personal details
- legal personal details
- financial personal details
- activism or organizing strategy
- security vulnerability details
- business strategy
- private person investigation
- hidden project details
- large copied private text

Approval may also be required for research-direction leakage, even when no private file content is sent.

A sensitive query must not be sent outward until approval is granted.

## 15. Refusal rules

The worker must refuse before network use when:

- query contains credentials or secrets
- query contains .env content
- query contains vault paths or vault-like content
- query contains private file paths
- query contains raw private memory
- query contains private journal text
- query requests upload or outward use of private files
- cloud search is requested while cloud_search_allowed is false
- page fetch is requested while page_fetch_allowed is false
- base_url is not approved local loopback
- configured query count exceeds maximum
- configured result count exceeds maximum

A refusal result must include:

- status: blocked
- queries_sent: []
- network_access_used: false
- private_context_sent: false
- refusal_reasons
- warnings
- trace_summary

The worker must not try anyway.

## 16. What gets logged

All attempted research tickets should be locally logged or traceable.

The trace ledger should record:

- request_id
- ticket_id
- worker_key
- status
- queries_requested
- queries_sent
- query_count
- result_count
- evidence_packet_count
- outward_boundary_state
- network_access_used
- private_context_sent
- cloud_search_used
- cloud_model_used
- page_fetch_used
- approval_required
- approval_state
- refusal_reasons
- warnings
- errors
- timestamp_utc

If a query is blocked before network use, the trace must still record that refusal.

The trace must not dump private files, raw private memory, vault contents, credentials, or full private context.

## 17. What the UI must show

The UI must never say merely:

local research

when query terms crossed the external boundary.

The UI must show:

- SearXNG service: local loopback
- Boundary: external public web for query terms
- Query terms left local control: yes or no
- Private context sent: false
- Cloud search used: false
- Cloud model used: false
- Page fetch used: false
- Evidence packets produced: count
- Search results verified: yes or no
- Contradictions flagged: count
- Approval required: yes or no
- Refusal reasons, if blocked

Honest wording examples:

- Bounded public web research through local SearXNG worker.
- External boundary crossed for query terms.
- Private context was not sent.
- Search snippets are evidence candidates, not final proof.

Bad wording examples:

- Fully local research completed.
- Elysia browsed safely.
- Evidence proved.
- Sources verified true.
- No external boundary crossed.

## 18. Main threat categories

### 18.1 Private query leakage

The user asks a question using private memory, private files, hidden project details, personal contacts, or sensitive notes, and those details get sent to a search engine.

Mitigation:

- query guard
- private-context blocking
- secret/path detection
- approval requirement
- queries_sent remains empty until allowed
- trace refusal before network

### 18.2 Research-direction leakage

Even if no private file is sent, the query itself can reveal sensitive direction, such as legal strategy, activism, health, finance, business plans, or personal investigation.

Mitigation:

- sensitive-topic detection
- approval gate
- query preview
- outward-boundary UI truth
- local trace

### 18.3 Silent outward boundary crossing

The system searches the web without making clear that query terms left local control.

Mitigation:

- outward_boundary_state
- network_access_used
- queries_sent
- UI boundary card
- request trace ledger
- capability truth

### 18.4 Over-trusting search snippets

Search snippets are not primary evidence. They are compressed, ranked, and sometimes misleading.

Mitigation:

- confidence low or unknown by default
- evidence verifier
- contradiction scan
- source type labeling
- response caveats
- fetch only later if needed and gated

### 18.5 Source laundering

Bad sources get wrapped in clean evidence packets and treated as credible just because they are structured.

Mitigation:

- source_type is descriptive only
- confidence remains modest
- verifier checks structure, not absolute truth
- response must not overclaim
- source ranking is not credibility

### 18.6 Contradiction blindness

One search result says one thing, another says the opposite, and the response ignores the conflict.

Mitigation:

- contradiction_scan
- contradiction_notes
- response warnings
- evidence packet grouping
- do not collapse conflict into false certainty

### 18.7 Fetch escalation

The worker moves from search results into page fetching without need, approval, or SSRF protections.

Mitigation:

- page_fetch_allowed false by default
- search_results_first true
- no fetch client in first pass
- separate fetch contract later
- approval required for fetch

### 18.8 SSRF and local-network risk

A fetch worker follows URLs that hit localhost, private network ranges, file URLs, metadata services, or internal devices.

Mitigation:

- no fetch in first pass
- future fetch guard
- block localhost
- block private IP ranges
- block file, data, javascript, and mailto schemes
- block redirects to private networks
- hard timeout and max bytes

### 18.9 Cloud/API drift

Someone later swaps local SearXNG for hosted search APIs or cloud research without clear UI truth.

Mitigation:

- cloud_search_allowed false
- cloud_model_allowed false
- config validation
- capability truth
- UI boundary disclosure
- approval required for cloud search

### 18.10 False UI truth

The UI says local research when query terms actually crossed the external boundary.

Mitigation:

- never label research as fully local when queries were sent outward
- show local worker versus external search boundary separately
- show private_context_sent
- show cloud_search_used
- show page_fetch_used
- show queries_sent count

## 19. Local SearXNG setup privacy note

A self-hosted local SearXNG path should not require a website signup by default.

However, once a query is sent through SearXNG, the query may still go to upstream public search engines. That means the query terms and network metadata may leave local control.

This must be visible in:

- worker result
- request trace
- capability surface
- UI boundary/evidence surface

## 20. Capability truth

The capability surface should eventually distinguish:

- planned
- configured
- unavailable
- degraded
- live
- blocked

Suggested capability wording:

Bounded public web research: live through local SearXNG worker.

SearXNG service: local loopback.

External boundary: crossed for query terms.

Private context sent: false.

Cloud search: false.

Page fetch: false.

If SearXNG is not reachable:

Bounded public web research: unavailable.

Reason: local SearXNG service not reachable.

No query was sent.

External boundary not crossed.

## 21. Acceptance criteria for Sprint 9A

Sprint 9A is complete when:

- docs/research/searxng_worker_contract.md exists
- the worker boundary is defined
- allowed inputs are defined
- forbidden inputs are defined
- outward boundary truth is defined
- approval rules are defined
- refusal rules are defined
- logging and trace requirements are defined
- UI truth requirements are defined
- threat categories are named with mitigations
- no live web behavior was added
- no network code was added
- no SearXNG client was added
- no runtime integration was added
- no frontend behavior was changed

## 22. Final doctrine

Local worker does not mean local-only research.

A local SearXNG worker may still send query terms to the public web.

Elysia must tell the truth:

- what was searched
- what crossed the boundary
- what did not cross
- what evidence was produced
- what remains uncertain
- what was refused
- what would require approval

No silent outward boundary crossing.

No private context outward by default.

No cloud search by default.

No page fetch in the first pass.

Search results first.

Evidence law always.

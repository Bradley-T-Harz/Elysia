# Bounded Fetch Worker Contract

## Purpose

The bounded fetch worker retrieves one explicitly approved public HTTP(S) page
for evidence support. It is not a browser, crawler, scraper, login agent, or
chat-autonomous web tool.

## Boundary Truth

- Worker: `bounded_fetch_worker`
- Network boundary: external public web for the approved URL
- Private context sent: false
- Cloud search used: false
- Cloud model used: false
- Browser automation used: false
- Crawling used: false

## Required Guards

- Explicit request-specific approval before network access
- HTTP or HTTPS URLs only
- Public DNS/host targets only
- Localhost, loopback, private, link-local, multicast, and unspecified IPs blocked
- Credentials in URLs blocked
- Fragment stripped before request
- Redirects either disabled or revalidated before following
- Hard timeout
- Hard byte limit
- No cookies, authentication, or login-gated content
- No private files, vault contents, memory, journals, secrets, or hidden context sent outward

## Output

The worker may return compact evidence-packet support:

- source URL
- title when safely available
- retrieval timestamp
- short sanitized snippet
- content type
- byte count
- boundary flags
- warnings and errors

It must not return raw full page HTML, raw page text dumps, credentials, hidden
reasoning, private context, or large nested payloads.

## Non-goals

- No page crawling
- No browser automation
- No Playwright/Selenium
- No login scraping
- No form submission
- No private network fetching
- No file/data/javascript/mailto schemes
- No automatic chat browsing

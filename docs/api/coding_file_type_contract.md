# Coding File Type API Contract

The local coding bridge exposes file type policy through:

- `GET /coding/file-types`
- `POST /coding/file/inspect-type`
- `POST /coding/file/read-preview`

`GET /coding/file-types` returns the supported registry descriptors.

`POST /coding/file/inspect-type` accepts `workspace_root` and `file_path`, then
returns a descriptor and path-guard result without dumping file contents.

`POST /coding/file/read-preview` returns an enriched approved preview:

- file type id/label/category
- adapter and language id
- encoding and line-ending metadata
- raw byte hash and decoded content hash
- line/byte counts and truncation truth
- parse status and adapter summary
- capability flags
- risk flags
- redactions and secret-scan findings

Routes are local-only bridge routes. They must not expose vault material,
private runtime files, hidden reasoning, source paths outside the workspace,
Marketplace sessions, cloud credentials, or service-role keys.

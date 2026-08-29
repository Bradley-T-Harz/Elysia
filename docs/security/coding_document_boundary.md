# Coding Document Boundary

Document stewardship is a governed local capability.

Blocked by default:

- macro-enabled Office documents: `.docm`, `.xlsm`, `.pptm`, `.dotm`, `.xltm`, `.potm`
- legacy Office formats: `.doc`, `.xls`, `.ppt`
- encrypted or corrupted documents
- zip containers with path traversal
- oversized documents beyond policy bounds
- unstable edits that could damage document fidelity

Never allowed:

- macro execution
- formula execution
- embedded script/media/link execution
- shell, package-manager, git, or cloud behavior
- full raw document text in audit records by default

Allowed with approval:

- bounded metadata/text/table/outline extraction
- Markdown/text export to a derived local file
- PDF-native derived-copy workflows, including page extraction, safe
  rotate/reorder/merge, metadata update, annotation/stamp/highlight, and
  coordinate-based redaction where the adapter can validate the operation
- PDF form-field inspection and filling for writable fields where field names,
  field types, read-only status, and select/list options can be validated locally;
  results must report per-field success/failure and write a derived PDF copy
- stable DOCX/XLSX/PPTX edits where the operation is explicitly supported,
  workspace-scoped, hash-checked, and audited

PDF source files are not destructively rewritten for unstable inline text edits.
When a request asks to directly rewrite prose inside an existing PDF, Elysia must
return the nearest safe alternative: edited Markdown/text export, corrected
DOCX/Markdown source copy, annotation/overlay on a derived PDF, redaction plus
replacement overlay with approved coordinates, or a rebuilt derived PDF from
approved content.

# Coding Document API Contract

Elysia document stewardship is local-only, bounded, approval-gated, and owned by
the Elysia core coding spine. Codev is only an interface to these routes.

Routes:

- `GET /coding/document-types`
- `POST /coding/document/inspect`
- `POST /coding/document/extract-preview`
- `POST /coding/document/export-plan`
- `POST /coding/document/export-approved`
- `POST /coding/document/edit-plan`
- `POST /coding/document/apply-approved`

Supported formats are `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, and
`.odp`. Macro-enabled variants and legacy Office formats are refused.

Document extraction returns metadata, bounded text previews, table previews,
outline items, provenance labels, warnings, and redaction counts. It does not
execute macros, formulas, embedded content, scripts, links, or media. Audit
records store result metadata, hashes, and approval truth rather than full
extracted document text.

Stable edits are deliberately narrow. PDFs support extraction/export plus
approved PDF-native derived-copy operations such as page extraction, safe page
rotation/reordering, PDF merge, metadata update, text stamp, highlight,
coordinate-based redaction, and governed PDF form-field filling for writable text,
checkbox/radio, and select/list fields where the local adapter can validate field
names, types, and options. These write a derived PDF copy rather than
destructively rewriting the source PDF. Arbitrary inline sentence editing inside
a PDF remains unstable and is redirected to safer alternatives such as edited
Markdown/text export, a corrected DOCX/Markdown source copy, annotation/overlay,
redaction plus replacement overlay when coordinates are approved, or rebuilding a
derived PDF from approved content. Unsupported/read-only PDF field subtypes are
reported per field with a safe refusal and nearest derived-copy fallback. ODF formats remain extraction/export oriented
unless a stable adapter operation is explicitly surfaced. DOCX, XLSX, and PPTX
support only explicit stable edit operations after approval and source-hash
verification.

Parser/runtime dependencies recorded for this capability:

- `pypdf`
- `pdfplumber`
- `pymupdf`
- `python-docx`
- `openpyxl`
- `python-pptx`
- `odfpy`
- `defusedxml`
- `lxml`

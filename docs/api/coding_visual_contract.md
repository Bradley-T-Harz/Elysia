# Coding Visual API Contract

The visual API lives under `/coding` and returns the shared Elysia envelope shape.

Routes:

- `GET /coding/visual-types`
- `POST /coding/visual/inspect`
- `POST /coding/visual/preview`
- `POST /coding/visual/ocr`
- `POST /coding/visual/analysis`
- `POST /coding/visual/export-plan`
- `POST /coding/visual/export-approved`
- `POST /coding/visual/edit-plan`
- `POST /coding/visual/apply-approved`

Inspection is metadata-first. Preview, OCR, analysis, export, and edit operations
require explicit approval where raw content or derived writes are involved.

Approved writes are derived-copy operations. They do not mutate the source image or
SVG. Source hash mismatch blocks execution. Audit payloads store hashes, relative
targets, operation names, and compact result details, not raw pixels, full OCR text,
or precise GPS coordinates.

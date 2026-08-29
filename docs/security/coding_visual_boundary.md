# Coding Visual Stewardship Boundary

Elysia visual stewardship is local-first and approval-gated. Supported image and
SVG files can be inspected, previewed, analyzed, OCR-scanned, exported, and edited
through derived-copy workflows without granting shell, package-manager, cloud, or
autonomous authority.

Supported formats: PNG, JPG/JPEG, WebP, GIF, BMP, TIFF/TIF, and SVG.

Safety rules:

- No cloud OCR or vision by default.
- No external image upload.
- No raw pixel payloads in audit records.
- No full OCR text in audit records by default.
- No precise EXIF GPS coordinates in audit records or UI summaries.
- SVG is parsed with safe XML handling and rendered only after sanitization.
- Source visual files are preserved; approved edits write derived copies.
- Every derived write requires path guard, source hash validation, operator
  approval, and an audit/result record.

PDF, document, and science/geospatial data stewardship remain separate surfaces;
ordinary TIFFs may use visual stewardship while GeoTIFF science workflows remain
available through the governed data routes.

# Coding Media Boundary

Chunk 5A adds a narrow media lane owned by Elysia core. Codev and Desktop are governed clients. They do not run ffprobe/ffmpeg themselves and do not acquire filesystem authority from file extensions or UI state.

Supported metadata formats are WAV, MP3, FLAC, OGG, M4A, MP4, MOV, MKV, and WebM. Recognition permits only explicit-approval, path-guarded local metadata inspection. Supported video containers may also request one fixed-argument derived PNG thumbnail. Audio thumbnails, arbitrary ffmpeg arguments, mutation, and transcoding are unavailable.

Speech-to-text and non-cloning TTS are separate local worker lanes. Saved transcript/WAV outputs require exact, expiring, one-time approvals bound to root, files, source/text hash, plan hash, and artifact-generation class. STT additionally requires a processing-rights and consent attestation. Raw audio, transcript text, TTS input text, and generated WAV bytes are excluded from central audit/request trace. Voice cloning and reference-voice input are unavailable by design. ImageForge provides one cancellable, exact-approved FLUX Creator-profile lane; CommonCanvas and Mitsua remain blocked. VideoForge has a fixed-profile, cancellable, exact-approved Wan lab route that remains disabled by default.

The authoritative gate vocabulary and five production gates live in `config/policies/governed_media_gates.yaml`. Runtime and model license/provenance evidence live in the media runtime and per-forge model registries. Unresolved licensing, provenance, resource-stability, safety, or consent truth cannot be silently promoted.

The adapter:

- accepts only files under an approved workspace root;
- rejects symlinks, remote inputs, blocked/private paths, unsupported extensions, content/extension mismatches, malformed inputs, excessive size/duration/stream counts, timeouts, and excessive tool output;
- invokes tools with fixed argv, `shell=False`, closed stdin, bounded stdout/stderr, and a timeout;
- allows only local `file`/`pipe` protocols and never accepts a URL;
- returns compact stream fields rather than raw ffprobe JSON;
- exposes only the presence of title/artist/comment/date/device/location/GPS-like tags, never their values;
- never stores raw media, raw tag values, or thumbnail bytes in coding audit or central request trace;
- records compact request/session/operation IDs, relative path, hashes, format/family, bounds, thumbnail status, approval state, and audit persistence truth.

Thumbnails are ephemeral inline derived outputs. Temporary files are isolated and removed after the response; no persistent artifact path or source mutation is created in this slice.

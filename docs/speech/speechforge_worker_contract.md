# SpeechForge worker contract

Status: governed local STT and synthetic reading-voice route wiring is live; voice cloning and identity-bearing voice generation remain unavailable.

SpeechForge is Elysia's separately governed local speech organ rather than an ambient audio reader inside the core API process. The dedicated runtime is the `elysia_speechforge` conda environment. Whisper.cpp `base.en` and Kokoro ONNX v1 assets are present locally; `faster-whisper` is installed but remains disabled until a separately reviewed local CTranslate2 model exists. This contract does not authorize a model download.

## Boundary and authority

- Inputs are explicit local files under a server-approved workspace root.
- URLs, streams, devices, microphones, network shares, cloud transcription, external upload, and outward private context are denied by default.
- The existing coding workspace-root/path guard is authoritative before a worker ticket may be issued.
- Transcription planning requires explicit operator posture; saving a transcript consumes an exact, expiring, one-time approval bound to root, source/output files, source hash, plan hash, and mutation class.
- Recordings that may contain other people require the operator to attest that transcription is consensual and lawful for the context.
- Size and duration limits are checked before decode. Current defaults are 512 MiB and 30 minutes; malformed, encrypted, huge, or unsupported inputs fail closed.
- The worker receives only the selected file, a bounded task ticket, model identifier, language/options allowlist, and output limits. It receives no home, vault, journal, identity, account, credential, or unrelated workspace access.
- Subprocesses use fixed arguments with `shell=false`, a timeout, bounded stdout/stderr, and no network protocols.

## Retention and trace

- Raw audio remains at its operator-selected source. It is never copied into the central ledger, request trace, logs, journals, memory, or model cache.
- Disposable decode fragments, if a future implementation requires them, live only in an isolated temporary directory and are removed after the request unless the operator explicitly approves a retained artifact.
- Full transcripts are request-scoped outputs or separately approved local artifacts. They are not central-ledger payloads and are not promoted to memory by default.
- Transcript previews are bounded and pass through secret/PII redaction before UI display or chat use.
- Central request/audit truth is compact: request/session/operation/approval IDs, relative path, root/source/model/output hashes, model provenance ID, consent posture, duration/size bounds, language, status, timestamps, artifact reference, retention outcome, and locality/network/cloud flags.
- Raw audio, full transcripts, absolute private paths, model prompts, decoder logs, and large subtitle bodies are excluded from central trace.

## Provenance and models

Every enabled model entry must declare:

- stable model ID and local path alias (never a credential-bearing cache path);
- provider/author and upstream source;
- exact revision and file hashes;
- model and code licenses;
- documented training-data/provenance summary;
- supported languages and known limitations;
- acquisition date and verifier;
- whether commercial, redistribution, and derived-output use are permitted;
- an explicit ethical-risk note when provenance is incomplete.

Unverified or unclear licenses/provenance keep a model disabled and surface `provenance_verification_required`. Model downloads, Hugging Face login, and cloud inference are outside this worker contract.

## Output artifacts

Transcription may produce separately approved local plain-text, JSON, SRT, or VTT artifacts. Subtitle timing and output size are bounded; exports use source/output hashes and never overwrite existing files. A provenance sidecar marks each transcript as machine-generated and not a source-of-truth record.

Machine transcripts can omit, substitute, or hallucinate words. UI and artifact provenance must tell operators to verify important content against the source recording. TXT, JSON, SRT, and VTT are implemented output formats; support for a container is not a guarantee of transcription accuracy.

## TTS separation

Text-to-speech remains separate from STT:

1. Reading voice: a clearly synthetic catalog-only local voice for accessibility and ordinary reading. Current Kokoro licensing/provenance is not fully verified, so this lane is lab-local rather than production-enabled.
2. Identity-bearing voice generation: a high-risk lane requiring explicit subject consent, provenance, purpose limitation, labeling, and additional approval.

Default voice cloning is forbidden. Deceptive impersonation, evasion of consent, covert identity mimicry, reference-voice input, or removal of provenance labeling must be refused. Kokoro accepts only catalog voice IDs and creates synthetic-audio artifacts with provenance sidecars.

## Refusal behavior

The worker refuses with compact truthful reasons when approval or consent is missing; the path/root is blocked; the input is remote, too large, too long, malformed, or unsupported; the model is absent; output bounds cannot be honored; or the request implies deceptive impersonation or non-consensual processing. Refusal must not echo raw content, generated speech, tag values, credentials, or private absolute paths.

## Enablement gates

SpeechForge remains limited to the current STT and synthetic reading-voice lane. Any expansion requires:

- externally verified model/license provenance;
- continued isolated-process and exact-approval tests;
- consent and retention UI truth;
- disposable-media live proof for every new engine/model;
- explicit operator approval before any capture, identity, cloning, cloud, or streaming capability.

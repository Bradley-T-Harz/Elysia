# VideoForge worker contract

Status: governed Wan route is live as `lab_only` and remains disabled by default. No VideoForge model is production-enabled.

VideoForge is a separate `elysia_videoforge` process. Elysia core owns approval, policy, paths, model truth, artifact registration, audit, and request trace; it must never import Torch or Diffusers. The first registered model is local `Wan2.1-T2V-1.3B-Diffusers`.

## Live lab lane

- Explicitly approved local text-to-video only through preview, apply, job-status, and cancel routes.
- Output only under an approved artifact/workspace root.
- Exactly one fixed resource profile: 416×256, 9 frames, 8 fps, four steps, one concurrent job, and a 300-second process timeout.
- Harmless synthetic-media purposes with mandatory provenance sidecars.
- Compact ledger truth: prompt hash/length, purpose category, model/revision, settings, output artifact/hash, synthetic label, resource profile, operation/approval IDs, duration, and locality flags.

Full prompts, frame bytes, private paths, model logs, and generated videos never belong in central audit or request trace.

## Prohibited lane

Image-to-video, video-to-video, real-person likeness generation, voice-driven avatars, face replacement, deepfakes, identity-bearing content, political persuasion, deceptive depiction of real events, commercial/public posting automation, cloud prompt extension, network model loading, and unlabeled output are unavailable.

Every output sidecar must state `synthetic_media: true`, `local_only: true`, `cloud_used: false`, and `not_a_recording_of_real_events: true`.

The route is enabled only when `ELYSIA_VIDEOFORGE_LAB_ENABLED=1`, the operator explicitly acknowledges lab status, and an exact expiring one-time approval matches the prompt hash, plan hash, root, output MP4 and sidecar, and artifact-generation mutation class. Worker subprocesses use fixed argv, `shell=False`, local model files only, bounded output, timeout, and process-group cancellation. Partial output remains isolated in worker temporary storage and is not copied after cancellation or failure.

## Production enablement gates

Exact approval-token consumption, prompt policy, approved-output path handling, cancellation/timeouts, resource limits, compact artifact/audit/trace integration, UI truth, and focused regression tests are implemented. Production remains blocked by external license/provenance verification and sustained resource/thermal/cancellation soak evidence. Cancellation is supported and unit-proven, but a long-running production-grade job controller with durable cross-restart recovery is intentionally not claimed.

The August 11, 2026 smoke passed at 416×256, 9 frames, 8 fps and four steps in 11.273 seconds with 10,872.6 MiB peak PyTorch allocation. This proves local runtime compatibility only; it is not production enablement.

The August 12 governed route proof completed the same fixed profile in 13.416 seconds, wrote an exact-approved synthetic MP4/artifact/audit/provenance receipt under `/tmp/elysia-chunk5-final-video-XFjhh0/`, and kept the prompt out of central records. A separate immediate cancel proof reached `cancelled` and retained neither a partial MP4 nor sidecar. These are bounded lab proofs, not sustained production evidence.

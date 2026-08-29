# ImageForge worker contract

Status: FLUX.1-schnell is a functional optional Creator-profile capability; other registered models remain blocked.

ImageForge runs only in `elysia_imageforge`. Elysia core owns model registry truth, prompt policy, exact approval, approved output paths, artifact receipts, audit, and request trace; it never imports Torch or Diffusers.

The worker accepts only registry model IDs, bounded dimensions/steps, one image, a numeric seed, an approved purpose category, and a local output ticket. It uses local files only, `trust_remote_code=false`, no network/cloud, no shell, one concurrent job, bounded output and timeout, and mandatory synthetic provenance.

Central truth stores prompt hash/length rather than prompt text, plus model ID, settings, artifact/output hashes, approval/operation IDs, resource result, synthetic label, and locality flags. It never stores image bytes, full prompts, negative prompts, model logs, or absolute private paths.

## Model gates

- FLUX.1-schnell: `profile_gated` for one 256×256, one-step sequential-CPU-offload profile. The publisher's official model and inference repositories identify the model and weights as Apache-2.0. The bounded governed route passed in 6.927 seconds with 262.1 MiB peak PyTorch allocation. Jobs are asynchronous and cancellable. Creator-profile model assets and the isolated runtime must pass doctor before use.
- Mitsua Diffusion One: disabled despite a successful smoke because local loading fell back to pickle `.bin` weights.
- CommonCanvas-XL-C: `lab_only`; generation requires an explicit lab acknowledgement and environment enablement. Local README/license metadata conflict blocks release use.

The governed CommonCanvas route/worker boundary passed a disposable local 256×256, one-step smoke in 6.68 seconds with 5,073.5 MiB peak PyTorch allocation. The disposable output was not retained. This proves the isolated route, exact approval, artifact receipt, and audit path—not release suitability.

The August 12 finalization re-proved CommonCanvas and proved the FLUX sequential-offload profile through the governed route. FLUX completed in 6.927 seconds with 262.1 MiB peak PyTorch allocation. Disposable smoke outputs were not retained. Raw prompts were absent from central audit/artifact records. These results justify only the bounded FLUX Creator-profile lane; they do not promote CommonCanvas.

ImageForge exposes an asynchronous in-process job controller with status polling and operator cancellation. Timeout and process-group termination remain enforced. FLUX does not require the lab override; CommonCanvas remains lab-gated. All saved outputs consume an exact, expiring, one-time approval.

Only the bounded FLUX lane is release-eligible when its optional profile prerequisites are present. Real-person likeness, impersonation, political persuasion, deceptive media, sexual content, graphic violence, copyrighted-character requests, or unlabeled generated outputs remain outside this lane.

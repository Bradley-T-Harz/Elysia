# BlendForge capability truth

BlendForge live support is metadata-only. It validates the `.blend` header and reports pointer size, endianness, encoded Blender version, file size/hash, and bounded indicators for linked `.blend` data. Every report warns that Blender files can contain scripts, drivers, add-ons, handlers, and linked libraries.

The system Blender executable is presence evidence only. Live EngineeringForge routes do not launch Blender, open a GUI, load the selected scene, follow linked libraries, load add-ons, run embedded Python, enable auto-run, or render a preview. The standalone `bpy` experiment was rejected during environment preparation and is not relied upon.

A future Blender preview would require a locked background/factory-startup worker, script auto-run disabled, no network/home/devices, disposable configuration/cache, no arbitrary add-ons, sandbox-only output, fixed arguments, timeout, and exact approval. Until that complete boundary is implemented and verified, preview is `future_sandbox_required` and conversion/repair/simulation are unavailable by design.

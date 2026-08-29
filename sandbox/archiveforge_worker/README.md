# ArchiveForge worker boundary

This worker exposes one operation: fixed-argument, noninteractive listing of a
path-guarded local `7z` or `rar` file. It uses `shell=False`, closes stdin,
enforces runtime and output caps, and never extracts, installs, imports, mounts,
or executes archive contents. Raw worker output is parsed locally and is never
written to central audit or request trace.

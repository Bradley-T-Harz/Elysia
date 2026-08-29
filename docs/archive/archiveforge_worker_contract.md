# ArchiveForge Worker Contract

Status: enabled for bounded 7Z/RAR listing only. Extraction is implemented inside Elysia core only for ZIP, TAR, and TAR.GZ; the external worker cannot extract anything.

The worker runs in `elysia_archiveforge` with one accepted operation (`list`) and two accepted format values (`7z`, `rar`). Elysia builds every argument. The worker resolves only `7zz` or `7z`, invokes `l -slt -ba -bd -y -- <source>`, closes stdin, uses `shell=False`, bounds both output streams, and kills on timeout or output overflow. Parsed output is reduced to member path/type/size/encryption summaries. Stderr and raw tool output do not enter central logs.

The worker cannot receive an extraction destination, password, arbitrary switch, creation command, install command, executable path, shell fragment, or network option. Its environment exposes only a minimal local `PATH` and C UTF-8 locale. Network and cloud access are outside the contract.

RAR listing depends on locally present tooling with mixed multiverse/nonfree/license-sensitive provenance. Presence is reported honestly and does not authorize redistribution, creation, or extraction. If the listing tool is absent, times out, overflows output bounds, requests a password, or rejects a container, the result is blocked.

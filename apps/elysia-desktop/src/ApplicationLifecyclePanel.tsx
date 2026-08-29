import { useEffect, useState, type CSSProperties } from "react";
import { readEnvelopeError } from "./accountPresentation";
import {
  applyApplicationLifecycle,
  fetchAccountState,
  fetchApplicationLifecycleState,
  previewApplicationLifecycle,
  type ApplicationLifecycleEnvelope
} from "./api/bridgeClient";

type Operation = "update" | "repair" | "rollback" | "uninstall_preserve" | "export_then_remove" | "purge_local_data";

const exportPhrase = "EXPORT THEN REMOVE ALL LOCAL ELYSIA DATA";
const purgePhrase = "PURGE ALL LOCAL ELYSIA DATA";

export default function ApplicationLifecyclePanel() {
  const [state, setState] = useState<ApplicationLifecycleEnvelope["data"] | null>(null);
  const [operation, setOperation] = useState<Operation>("update");
  const [artifact, setArtifact] = useState("");
  const [manifest, setManifest] = useState("");
  const [signature, setSignature] = useState("");
  const [releaseId, setReleaseId] = useState("");
  const [exportPath, setExportPath] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [preview, setPreview] = useState<ApplicationLifecycleEnvelope["data"] | null>(null);
  const [result, setResult] = useState<ApplicationLifecycleEnvelope["data"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeRole, setActiveRole] = useState<"installation_owner" | "admin" | "user" | null>(null);
  const localAdminAuthorized = activeRole === "installation_owner" || activeRole === "admin";

  async function refresh() {
    const [lifecycleResponse, accountResponse] = await Promise.all([
      fetchApplicationLifecycleState(),
      fetchAccountState()
    ]);
    if (lifecycleResponse.ok && lifecycleResponse.payload.status === "ok") setState(lifecycleResponse.payload.data ?? null);
    if (accountResponse.ok && accountResponse.payload.status === "ok") {
      setActiveRole(accountResponse.payload.data?.active_role ?? null);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function createPreview() {
    setBusy(true); setError(null); setPreview(null); setResult(null);
    try {
      const response = await previewApplicationLifecycle({
        operation,
        artifact_path: ["update", "repair"].includes(operation) ? artifact || null : null,
        manifest_path: ["update", "repair"].includes(operation) ? manifest || null : null,
        signature_path: ["update", "repair"].includes(operation) ? signature || null : null,
        target_release_id: operation === "rollback" ? releaseId || null : null,
        export_path: operation === "export_then_remove" ? exportPath || null : null,
        destructive_confirmation: ["export_then_remove", "purge_local_data"].includes(operation) ? confirmation || null : null
      });
      if (!response.ok || response.payload.status !== "ok") setError(readEnvelopeError(response.payload));
      else setPreview(response.payload.data ?? null);
    } finally { setBusy(false); }
  }

  async function applyPreview() {
    if (!preview?.preview_id || !preview.approval_token) return;
    setBusy(true); setError(null);
    try {
      const response = await applyApplicationLifecycle({
        preview_id: preview.preview_id,
        approval_token: preview.approval_token,
        operator_approved: true
      });
      if (!response.ok || response.payload.status !== "ok") setError(readEnvelopeError(response.payload));
      else {
        setResult(response.payload.data ?? null);
        setPreview(null);
        await refresh();
      }
    } finally { setBusy(false); }
  }

  const phrase = operation === "export_then_remove" ? exportPhrase : operation === "purge_local_data" ? purgePhrase : null;

  return <section aria-label="Application lifecycle" style={panelStyle}>
    <div>
      <div style={eyebrowStyle}>Managed Core runtime lifecycle</div>
      <p style={mutedStyle}>Signed update, bounded repair, schema-safe rollback, and three distinct removal choices for Elysia's versioned managed Core runtime. Every mutation must be initiated and explicitly approved by the Local Admin through an exact preview. Elysia never silently auto-updates. System .deb and AppImage lifecycle stays with the package/file owner rather than being impersonated by this panel.</p>
    </div>
    {!localAdminAuthorized && <div role="alert" style={dangerStyle}>Installation-wide update, repair, rollback, and removal require an authenticated Local Admin or Installation Owner. This profile may inspect lifecycle status but cannot initiate mutation.</div>}
    <div className="elysia-summary-grid-2" style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".75rem" }}>
      <div style={insetStyle}><strong>Installed:</strong> {state?.installed ? "yes" : "no"}<br /><strong>Current release:</strong> {state?.current_release_id ?? "none"}</div>
      <div style={insetStyle}><strong>Interrupted operation:</strong> {state?.incomplete_operation_detected ? "detected — an exact update/repair may recover the preserved prior release" : "none"}<br /><strong>User data preserved by default:</strong> yes</div>
    </div>
    <label>Lifecycle operation
      <select disabled={!localAdminAuthorized} value={operation} onChange={(event) => { setOperation(event.target.value as Operation); setPreview(null); setConfirmation(""); }} style={inputStyle}>
        <option value="update">Verified update</option><option value="repair">Repair package-owned bytes</option><option value="rollback">Rollback to compatible release</option><option value="uninstall_preserve">Remove application, preserve profiles and memory</option><option value="export_then_remove">Private export, then remove all local data</option><option value="purge_local_data">Permanently purge all local Elysia data</option>
      </select>
    </label>
    {["update", "repair"].includes(operation) && <div style={insetStyle}>
      <label>Exact local release archive<input value={artifact} onChange={(event) => setArtifact(event.target.value)} style={inputStyle} /></label>
      <label>Signed manifest<input value={manifest} onChange={(event) => setManifest(event.target.value)} style={inputStyle} /></label>
      <label>Detached Ed25519 signature<input value={signature} onChange={(event) => setSignature(event.target.value)} style={inputStyle} /></label>
    </div>}
    {operation === "rollback" && <label>Exact prior release identifier<input value={releaseId} onChange={(event) => setReleaseId(event.target.value)} style={inputStyle} /></label>}
    {operation === "export_then_remove" && <label>New private .tar.gz export path (outside Elysia roots)<input value={exportPath} onChange={(event) => setExportPath(event.target.value)} style={inputStyle} /></label>}
    {phrase && <div role="alert" style={dangerStyle}>
      <strong>Destructive local-data removal.</strong> This removes local accounts, conversations, projects, memory, settings, and Elysia-owned local model data. External vaults remain untouched. {operation === "export_then_remove" ? "A private 0600 export is verified first; protect it because it can contain credentials and private lives." : "No recovery archive is created."}
      <label style={{ display: "block", marginTop: ".7rem" }}>Type exactly: <code>{phrase}</code><input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} style={inputStyle} /></label>
    </div>}
    <button type="button" disabled={busy || !localAdminAuthorized || Boolean(phrase && confirmation !== phrase)} onClick={() => void createPreview()} style={buttonStyle}>Local Admin: preview exact lifecycle effects</button>
    {preview && <div style={insetStyle} aria-label="Exact lifecycle preview">
      <p><strong>Operation:</strong> {preview.operation}</p><p><strong>Current → target:</strong> {preview.current_release_id ?? "none"} → {preview.target_release_id ?? "none"}</p>
      {preview.artifact_sha256 && <p><strong>Verified artifact:</strong> {preview.artifact_sha256} · {preview.artifact_size_bytes} bytes</p>}
      {preview.current_memory_schema !== undefined && <p><strong>Memory schema:</strong> {preview.current_memory_schema} → {preview.target_memory_schema}; migrations: {(preview.memory_migration_ids ?? []).join(", ") || "none"}.</p>}
      {!!preview.component_changes?.length && <p><strong>Signed component changes:</strong> {preview.component_changes.join(", ")}</p>}
      {preview.local_data_inventory && <p><strong>Destructive inventory:</strong> {preview.local_data_inventory.file_count} files · {preview.local_data_inventory.exact_bytes} bytes across {preview.local_data_inventory.root_count} roots.</p>}
      <p><strong>User-data preservation:</strong> {preview.user_data_preserved ? "yes" : preview.private_export_created_before_removal ? "private export first" : "no — explicit purge"}</p>
      <p><strong>Mutation authority:</strong> authenticated Local Admin, explicit approval only; silent update unavailable.</p>
      <button type="button" disabled={busy || !localAdminAuthorized} onClick={() => void applyPreview()} style={buttonStyle}>Local Admin: approve this exact preview</button>
    </div>}
    {result && <div role="status" style={insetStyle}><strong>Lifecycle result:</strong> {result.applied ? "applied" : "no mutation"}. {result.current_release_id ? `Current release ${result.current_release_id}.` : ""}</div>}
    {error && <div role="alert" style={dangerStyle}>{error}</div>}
  </section>;
}

const panelStyle: CSSProperties = { display: "grid", gap: ".82rem", padding: "1rem", borderRadius: 20, border: "1px solid rgba(184,162,123,.28)", background: "linear-gradient(180deg,rgba(55,43,30,.20),rgba(11,14,18,.78))" };
const insetStyle: CSSProperties = { display: "grid", gap: ".55rem", padding: ".78rem", borderRadius: 13, border: "1px solid rgba(199,210,218,.16)", background: "rgba(11,14,18,.48)" };
const inputStyle: CSSProperties = { width: "100%", boxSizing: "border-box", marginTop: ".32rem", padding: ".7rem", borderRadius: 11, border: "1px solid rgba(199,210,218,.22)", background: "rgba(11,14,18,.72)", color: "#C7D2DA", font: "inherit" };
const buttonStyle: CSSProperties = { padding: ".76rem .9rem", borderRadius: 11, border: "1px solid rgba(126,215,209,.36)", background: "rgba(16,71,75,.68)", color: "#C7D2DA", fontWeight: 800, cursor: "pointer" };
const dangerStyle: CSSProperties = { padding: ".78rem", borderRadius: 12, border: "1px solid rgba(216,165,165,.35)", background: "rgba(216,165,165,.09)", color: "#E3B4B4", lineHeight: 1.5 };
const mutedStyle: CSSProperties = { color: "rgba(199,210,218,.72)", lineHeight: 1.55, margin: ".28rem 0 0" };
const eyebrowStyle: CSSProperties = { fontSize: ".82rem", letterSpacing: ".08em", textTransform: "uppercase", color: "#B8A27B" };

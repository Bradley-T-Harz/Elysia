import { useEffect, useState, type CSSProperties } from "react";
import { accountPalette, readEnvelopeError } from "./accountPresentation";
import {
  applyComponentInstall,
  applySystemPrerequisites,
  applySetup,
  cancelComponentJob,
  fetchComponentJob,
  previewComponentInstall,
  previewSetup,
  previewSystemPrerequisites,
  runSetupDoctor,
  type ComponentInstallEnvelope,
  type SetupStateEnvelope,
  type SystemPrerequisiteEnvelope
} from "./api/bridgeClient";

const profiles = [
  ["core", "Core"],
  ["workstation_research", "Workstation / Research"],
  ["creator_perception", "Creator / Perception"],
  ["developer_codev", "Developer / Codev"],
  ["scientific_engineering_mega", "Scientific / Engineering MEGA"],
  ["complete_v1_mega", "Complete Elysia v1 MEGA"],
  ["custom", "Custom"]
] as const;

const customComponents = [
  ["workstation_adapters", "Workstation adapters"],
  ["governed_research", "Governed research / SearXNG"],
  ["semantic_retrieval", "Semantic retrieval"],
  ["local_connectors", "Local connectors"],
  ["creator_perception", "Creator / perception"],
  ["codev_companion", "Developer / Codev"],
  ["scientific_engineering", "Scientific / Engineering"],
  ["local_model_provider", "Local model provider"]
] as const;

const creatorModels = [
  ["whisper_cpp_base_en", "Whisper.cpp base.en · local speech-to-text"],
  ["kokoro_onnx_v1", "Kokoro ONNX v1 · catalog-only reading voices"],
  ["flux1_schnell", "FLUX.1-schnell · gated local image pipeline (~31.41 GiB)"]
] as const;

function bytes(value?: number) {
  if (!value) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
  return `${amount.toFixed(unit === 0 ? 0 : 2)} ${units[unit]}`;
}

export default function ElysiaSetupPage({ error: initialError, initialState, onConfigured }: { error?: string | null; initialState?: SetupStateEnvelope["data"] | null; onConfigured: () => Promise<void> }) {
  const [profileId, setProfileId] = useState("core");
  const [distribution, setDistribution] = useState<"deb" | "appimage" | "user_local_desktop" | "onefile_core" | "source">(
    initialState?.detected_distribution_form ?? "deb"
  );
  const [installRoot, setInstallRoot] = useState("");
  const [internetAvailable, setInternetAvailable] = useState(false);
  const [selectedCustom, setSelectedCustom] = useState<string[]>([]);
  const [codevPath, setCodevPath] = useState("");
  const [creatorModelIds, setCreatorModelIds] = useState<string[]>([]);
  const [localModelRoot, setLocalModelRoot] = useState("");
  const [modelTermsAccepted, setModelTermsAccepted] = useState(false);
  const [preview, setPreview] = useState<SetupStateEnvelope["data"] | null>(null);
  const [componentPreview, setComponentPreview] = useState<ComponentInstallEnvelope["data"] | null>(null);
  const [prerequisitePreview, setPrerequisitePreview] = useState<SystemPrerequisiteEnvelope["data"] | null>(null);
  const [activeComponent, setActiveComponent] = useState<string | null>(null);
  const [job, setJob] = useState<ComponentInstallEnvelope["data"] | null>(null);
  const [error, setError] = useState<string | null>(initialError ?? null);
  const [busy, setBusy] = useState(false);

  const componentsPending = Boolean(initialState?.configured && initialState.pending_component_ids?.length);
  const doctorPending = Boolean(initialState?.configured && !componentsPending && initialState.doctor_required);

  useEffect(() => {
    const jobId = job?.job_id;
    if (!jobId || !["queued", "running"].includes(String(job.status))) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void (async () => {
        const result = await fetchComponentJob(jobId);
        if (cancelled) return;
        if (!result.ok || result.payload.status === "blocked") {
          setError(readEnvelopeError(result.payload));
          window.clearInterval(timer);
          return;
        }
        const state = result.payload.data ?? null;
        setJob(state);
        if (state?.status && !["queued", "running"].includes(state.status)) {
          window.clearInterval(timer);
          if (state.status === "succeeded") {
            setComponentPreview(null);
            setActiveComponent(null);
            await onConfigured();
          } else {
            setError(state.error_summary ?? `Component operation ended as ${state.status}.`);
          }
        }
      })();
    }, 500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [job?.job_id, job?.status, onConfigured]);

  async function createPreview() {
    setBusy(true);
    setError(null);
    try {
      const result = await previewSetup({
        profile_id: profileId,
        distribution_form: distribution,
        install_root: installRoot || null,
        custom_components: profileId === "custom" ? selectedCustom : [],
        internet_available: internetAvailable
      });
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        setPreview(null);
        return;
      }
      setPreview(result.payload.data ?? null);
    } finally {
      setBusy(false);
    }
  }

  async function createComponentPreview(componentId: string) {
    setBusy(true);
    setError(null);
    setJob(null);
    try {
      const result = await previewComponentInstall({
        component_id: componentId,
        operation: "install",
        metadata_network_approved: internetAvailable,
        local_artifact_path: componentId === "codev_companion" ? codevPath || null : null,
        selected_model_ids: componentId === "creator_perception" ? creatorModelIds : [],
        local_model_root: componentId === "creator_perception" ? localModelRoot || null : null,
        model_terms_accepted: componentId === "creator_perception" && modelTermsAccepted
      });
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      setActiveComponent(componentId);
      setComponentPreview(result.payload.data ?? null);
    } finally {
      setBusy(false);
    }
  }

  async function createPrerequisitePreview() {
    setBusy(true);
    setError(null);
    try {
      const result = await previewSystemPrerequisites(initialState?.component_ids ?? []);
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      setPrerequisitePreview(result.payload.data ?? null);
    } finally {
      setBusy(false);
    }
  }

  async function applyPrerequisites() {
    if (!prerequisitePreview?.preview_id || !prerequisitePreview.approval_token) return;
    setBusy(true);
    setError(null);
    try {
      const result = await applySystemPrerequisites({
        preview_id: prerequisitePreview.preview_id,
        approval_token: prerequisitePreview.approval_token,
        operator_approved: true
      });
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      setPrerequisitePreview(result.payload.data ?? null);
      await onConfigured();
    } finally {
      setBusy(false);
    }
  }

  async function applyExactComponentPreview() {
    if (!componentPreview?.preview_id || !componentPreview.approval_token) return;
    setBusy(true);
    setError(null);
    try {
      const result = await applyComponentInstall({
        preview_id: componentPreview.preview_id,
        approval_token: componentPreview.approval_token,
        operator_approved: true
      });
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      setJob(result.payload.data ?? null);
    } finally {
      setBusy(false);
    }
  }

  async function cancelJob() {
    if (!job?.job_id) return;
    const result = await cancelComponentJob(job.job_id);
    if (!result.ok || result.payload.status !== "ok") setError(readEnvelopeError(result.payload));
    else setJob(result.payload.data ?? null);
  }

  async function applyExactPreview() {
    if (!preview?.preview_id || !preview.approval_token) return;
    setBusy(true);
    setError(null);
    try {
      const result = await applySetup({
        preview_id: preview.preview_id,
        approval_token: preview.approval_token,
        operator_approved: true
      });
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      await onConfigured();
    } finally {
      setBusy(false);
    }
  }

  async function runFinalDoctor() {
    setBusy(true);
    setError(null);
    try {
      const result = await runSetupDoctor();
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      await onConfigured();
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={pageStyle} data-testid="elysia-setup-page">
      <div style={shellStyle}>
        <header>
          <div style={eyebrowStyle}>Stage A · machine installation</div>
          <h1 style={{ margin: 0 }}>Elysia Setup</h1>
          <p><strong>Elysia 1.0 Setup</strong> · EcoSyneva Commons LLC · Ubuntu 24.04 x86-64. Exact package identity and signed updater material are verified through the governed lifecycle.</p>
          <p style={mutedStyle}>Choose components from the authoritative graph. Setup previews downloads, disk, hardware, network, and privilege effects before any configuration. It does not create a person, biography, Website account, or memory.</p>
          <p style={mutedStyle}>Local Elysia works without a public Commons account. Optional Internet research and selected public exports cross local control only after their own explicit consent.</p>
        </header>
        {!componentsPending && !doctorPending && <section style={sectionStyle}>
          <label>Install profile
            <select value={profileId} onChange={(event) => { setProfileId(event.target.value); setPreview(null); }} style={inputStyle}>
              {profiles.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          {profileId === "custom" && <fieldset style={fieldsetStyle}>
            <legend>Custom components</legend>
            {customComponents.map(([id, label]) => <label key={id} style={{ display: "flex", gap: ".55rem", alignItems: "center" }}>
              <input type="checkbox" checked={selectedCustom.includes(id)} onChange={(event) => {
                setSelectedCustom((current) => event.target.checked ? [...current, id] : current.filter((item) => item !== id));
                setPreview(null);
              }} />
              {label}
            </label>)}
          </fieldset>}
          <label>Distribution form
            <select value={distribution} disabled={Boolean(initialState?.distribution_form_locked)} onChange={(event) => { setDistribution(event.target.value as typeof distribution); setPreview(null); }} style={inputStyle}>
              <option value="deb">Installed .deb</option>
              <option value="appimage">AppImage</option>
              <option value="user_local_desktop">User-local desktop</option>
              <option value="onefile_core">One-file Core</option>
              <option value="source">Source install</option>
            </select>
          </label>
          {initialState?.distribution_form_locked && <p style={mutedStyle}>Detected from the running package and locked into the Setup receipt.</p>}
          <label>Optional managed-component runtime root (optional)
            <input value={installRoot} onChange={(event) => { setInstallRoot(event.target.value); setPreview(null); }} placeholder="Use the safe XDG user-data default" style={inputStyle} />
          </label>
          <p style={mutedStyle}>This choice relocates only Setup-managed optional runtimes. The application package follows its distribution form, while accounts, Memory, settings, caches, and runtime authority remain in their stable XDG locations.</p>
          <label style={{ display: "flex", gap: ".55rem", alignItems: "center" }}>
            <input type="checkbox" checked={internetAvailable} onChange={(event) => { setInternetAvailable(event.target.checked); setPreview(null); }} />
            Internet is currently available for separately approved acquisitions
          </label>
          <button type="button" disabled={busy} onClick={() => void createPreview()} style={primaryButtonStyle}>Preview exact setup plan</button>
        </section>}
        {!componentsPending && !doctorPending && preview && (
          <section style={sectionStyle} aria-label="Setup effect preview">
            <h2 style={{ margin: 0 }}>Review effects</h2>
            <p><strong>Components:</strong> {(preview.component_ids ?? []).join(", ")}</p>
            <p><strong>Hardware decision:</strong> {String(preview.hardware?.neurofabric_variant ?? "CPU")}; external fingerprinting: no.</p>
            <p><strong>Network:</strong> runtime disabled by default; external acquisition requires separate exact confirmation; personal data egress: no.</p>
            <p><strong>Privilege:</strong> silent sudo: no; package-manager privilege required: {String(preview.privilege_preview?.package_manager_privilege_required ?? false)}.</p>
            {!!(preview.privilege_preview?.exact_system_package_operations as string[] | undefined)?.length && <p><strong>Exact reviewed Ubuntu operations:</strong> {(preview.privilege_preview?.exact_system_package_operations as string[]).join(", ")}. The full Setup process never runs as root; applying these opens graphical polkit authorization.</p>}
            <p><strong>Initial size estimate:</strong> download {bytes(preview.estimated_download_bytes)}; installed {bytes(preview.estimated_installed_bytes)}. Every external transfer receives a separate exact-byte preview.</p>
            {preview.dependency_install_dispositions && <div role="region" style={nestedStyle} aria-label="Selected profile dependency dispositions">
              <h3 style={{ margin: 0 }}>Selected-profile dependency coverage</h3>
              <p><strong>{preview.dependency_install_dispositions.dependency_count ?? 0}</strong> release-supported dependencies are mapped through one authoritative installation disposition.</p>
              <p style={mutedStyle}>A bundled: {preview.dependency_install_dispositions.category_counts?.A ?? 0} · B Setup-acquired: {preview.dependency_install_dispositions.category_counts?.B ?? 0} · C Ubuntu/polkit: {preview.dependency_install_dispositions.category_counts?.C ?? 0} · D reused: {preview.dependency_install_dispositions.category_counts?.D ?? 0} · E user action: {preview.dependency_install_dispositions.category_counts?.E ?? 0}</p>
              <p><strong>{preview.dependency_install_dispositions.system_dependency_count ?? 0}</strong> selected system/runtime prerequisites are independently classified.</p>
              <p style={mutedStyle}>System A bundled: {preview.dependency_install_dispositions.system_category_counts?.A ?? 0} · B Setup-acquired: {preview.dependency_install_dispositions.system_category_counts?.B ?? 0} · C Ubuntu/polkit: {preview.dependency_install_dispositions.system_category_counts?.C ?? 0} · D detected/reused: {preview.dependency_install_dispositions.system_category_counts?.D ?? 0} · E user action: {preview.dependency_install_dispositions.system_category_counts?.E ?? 0}</p>
              {(preview.dependency_install_dispositions.category_e_actions ?? []).map((item) => <div key={item.dependency_id} style={nestedStyle}>
                <p><strong>{item.guidance?.title ?? item.label ?? item.dependency_id}</strong> · user action required</p>
                <p>{item.guidance?.why ?? item.purpose}</p>
                <p><strong>Signup:</strong> {item.guidance?.signup_required}; <strong>boundary:</strong> {item.guidance?.data_leaving_local_control}</p>
                <p>{item.guidance?.license_privacy_security}</p>
                <ol>{(item.guidance?.supported_steps ?? []).map((step) => <li key={step}>{step}</li>)}</ol>
                {item.guidance?.official_source && <a href={item.guidance.official_source} target="_blank" rel="noreferrer">Official installation source</a>}
                <p style={mutedStyle}><strong>Doctor:</strong> {item.guidance?.doctor_detection} <strong>Retry/repair:</strong> {item.guidance?.retry_repair}</p>
              </div>)}
              {(preview.dependency_install_dispositions.system_category_e_actions ?? []).map((item) => <div key={`system-${item.dependency_id}`} style={nestedStyle}>
                <p><strong>{item.guidance?.title ?? item.dependency_id}</strong> · system action required</p>
                {!!item.dependency_ids?.length && <p style={mutedStyle}><strong>Applies to:</strong> {item.dependency_ids.join(", ")}</p>}
                <p>{item.guidance?.why ?? item.purposes?.join(" ")}</p>
                <p><strong>Signup:</strong> {item.guidance?.signup_required}; <strong>boundary:</strong> {item.guidance?.data_leaving_local_control}</p>
                <p>{item.guidance?.license_privacy_security}</p>
                <ol>{(item.guidance?.supported_steps ?? []).map((step) => <li key={step}>{step}</li>)}</ol>
                {item.guidance?.official_source && <a href={item.guidance.official_source} target="_blank" rel="noreferrer">Official system-prerequisite source</a>}
                <p style={mutedStyle}><strong>Doctor:</strong> {item.guidance?.doctor_detection} <strong>Retry/repair:</strong> {item.guidance?.retry_repair}</p>
              </div>)}
            </div>}
            {(preview.component_license_preview ?? []).map((item) => <p key={item.component_id}><strong>{item.component_id}:</strong> {item.license}; {item.redistribution}</p>)}
            {(preview.warnings ?? []).map((warning) => <div key={warning} role="status" style={warningStyle}>{warning}</div>)}
            {(preview.blockers ?? []).map((blocker) => <div key={blocker} role="alert" style={errorStyle}>{blocker}</div>)}
            <button type="button" disabled={busy || !preview.ready_to_apply} onClick={() => void applyExactPreview()} style={primaryButtonStyle}>Approve and configure this exact plan</button>
          </section>
        )}
        {componentsPending && <section style={sectionStyle} aria-label="Selected component installation">
          <h2 style={{ margin: 0 }}>Install selected components</h2>
          <p style={mutedStyle}>Profile selection did not approve downloads. Resolve and review each exact source, identity, license, transfer size, storage estimate, network effect, and privilege effect before installation.</p>
          <button type="button" disabled={busy} onClick={() => void createPrerequisitePreview()} style={secondaryButtonStyle}>Inspect exact system prerequisites</button>
          {prerequisitePreview && <div style={nestedStyle} aria-label="Exact system prerequisite preview">
            <p><strong>Silent sudo:</strong> no. Full Setup as root: no. Authorization: {prerequisitePreview.authorization_mechanism ?? "none"}.</p>
            <p><strong>Exact package operations:</strong> {(prerequisitePreview.exact_package_operations ?? []).join(", ") || "none"}.</p>
            {!!prerequisitePreview.external_missing_dependency_ids?.length && <p><strong>Separately governed prerequisites still absent:</strong> {prerequisitePreview.external_missing_dependency_ids.join(", ")}.</p>}
            {(prerequisitePreview.external_missing_guidance ?? []).map((item) => <div key={item.dependency_id} style={nestedStyle}>
              <p><strong>{item.title ?? item.dependency_id}</strong></p>
              <p>{item.why}</p>
              <p><strong>Signup:</strong> {item.signup_required}; <strong>boundary:</strong> {item.data_leaving_local_control}</p>
              <p>{item.license_privacy_security}</p>
              <ol>{(item.supported_steps ?? []).map((step) => <li key={step}>{step}</li>)}</ol>
              {item.official_source && <a href={item.official_source} target="_blank" rel="noreferrer">Official installation source</a>}
              <p style={mutedStyle}><strong>Doctor:</strong> {item.doctor_detection} <strong>Retry/repair:</strong> {item.retry_repair}</p>
            </div>)}
            {!!prerequisitePreview.exact_package_operations?.length && <button type="button" disabled={busy} onClick={() => void applyPrerequisites()} style={primaryButtonStyle}>Authorize only these exact Ubuntu package operations</button>}
          </div>}
          <label style={{ display: "flex", gap: ".55rem", alignItems: "center" }}>
            <input type="checkbox" checked={internetAvailable} onChange={(event) => setInternetAvailable(event.target.checked)} />
            Permit metadata-only package/registry resolution for this preview
          </label>
          {initialState?.pending_component_ids?.includes("codev_companion") && <label>Existing exact Codev v1.0.0 VSIX (optional)
            <input value={codevPath} onChange={(event) => setCodevPath(event.target.value)} placeholder="Leave blank for the exact official GitHub release download" style={inputStyle} />
            <span style={mutedStyle}>Setup verifies a selected local copy byte-for-byte, or acquires the exact first-party VSIX from its canonical v1.0.0 release URL after network approval.</span>
          </label>}
          {initialState?.pending_component_ids?.includes("creator_perception") && <fieldset style={fieldsetStyle}>
            <legend>Creator model assets (optional; capabilities remain visibly gated when omitted)</legend>
            {creatorModels.map(([id, label]) => <label key={id} style={{ display: "flex", gap: ".55rem", alignItems: "center" }}>
              <input type="checkbox" checked={creatorModelIds.includes(id)} onChange={(event) => {
                setCreatorModelIds((current) => event.target.checked ? [...current, id] : current.filter((item) => item !== id));
                setComponentPreview(null);
              }} />
              {label}
            </label>)}
            <label>Existing local model vault (optional; every selected artifact is verified before adoption)
              <input value={localModelRoot} onChange={(event) => { setLocalModelRoot(event.target.value); setComponentPreview(null); }} placeholder="Absolute local vault path; never shown in public diagnostics" style={inputStyle} />
            </label>
            <label style={{ display: "flex", gap: ".55rem", alignItems: "flex-start" }}>
              <input type="checkbox" checked={modelTermsAccepted} onChange={(event) => { setModelTermsAccepted(event.target.checked); setComponentPreview(null); }} />
              I reviewed the displayed upstream identities, licenses, resource costs, gated access terms, and local-only safety boundaries for the selected models.
            </label>
            <p style={mutedStyle}>Profile selection never approves a model transfer. A gated FLUX download uses a session-only HF_TOKEN after upstream terms are accepted; Elysia never stores that token or authenticated download state.</p>
          </fieldset>}
          <div style={{ display: "grid", gap: ".55rem" }}>
            {(initialState?.pending_component_ids ?? []).map((componentId) => <button key={componentId} type="button" disabled={busy || ["queued", "running"].includes(String(job?.status))} onClick={() => void createComponentPreview(componentId)} style={secondaryButtonStyle}>
              Resolve exact plan · {componentId.replaceAll("_", " ")}
            </button>)}
          </div>
          {componentPreview && <div style={nestedStyle} aria-label="Exact component effect preview">
            <h3 style={{ margin: 0 }}>{activeComponent?.replaceAll("_", " ")}</h3>
            <p><strong>Source:</strong> {componentPreview.source}</p>
            <p><strong>Identity:</strong> {componentPreview.identity}</p>
            <p><strong>License:</strong> {componentPreview.license}</p>
            <p><strong>Transfer:</strong> exactly {bytes(componentPreview.exact_download_bytes)} across {componentPreview.artifact_count ?? 0} artifact(s).</p>
            <p><strong>Installed-size estimate:</strong> {bytes(componentPreview.estimated_installed_bytes)}</p>
            <p><strong>Network:</strong> {componentPreview.network}; private data egress: no.</p>
            <p><strong>Privilege:</strong> {componentPreview.privilege}; silent privilege: no.</p>
            {componentPreview.model_plan && <div style={nestedStyle}>
              <p><strong>Creator models:</strong> {(componentPreview.model_plan.selected_model_ids ?? []).join(", ") || "none selected; model-specific powers remain gated"}</p>
              {(componentPreview.model_plan.models ?? []).map((model: any) => <p key={model.model_id}><strong>{model.display_name}:</strong> {model.license}; {model.redistribution}; exact transfer {bytes(model.exact_download_bytes)}.</p>)}
              <p><strong>Local vault adoption:</strong> {componentPreview.model_plan.local_model_vault_adoption ? "exact local assets verified; no transfer" : "no"}.</p>
            </div>}
            <button type="button" disabled={busy || ["queued", "running"].includes(String(job?.status))} onClick={() => void applyExactComponentPreview()} style={primaryButtonStyle}>Approve exact transfer and installation</button>
          </div>}
          {job && <div style={nestedStyle} role="status">
            <p><strong>Job:</strong> {job.status} · {job.phase ?? "queued"}</p>
            {["queued", "running"].includes(String(job.status)) && <button type="button" onClick={() => void cancelJob()} style={secondaryButtonStyle}>Cancel and clean up safely</button>}
          </div>}
        </section>}
        {doctorPending && <section style={sectionStyle} aria-label="Final Setup Doctor gate">
          <h2 style={{ margin: 0 }}>Verify the installed profile</h2>
          <p style={mutedStyle}>All selected component operations have finished. Doctor will now verify Core, the exact component receipts, XDG permissions, Identity and blank Memory readiness, workers, models, hardware, update trust, and resource state. It performs no repair or download.</p>
          <button type="button" disabled={busy} onClick={() => void runFinalDoctor()} style={primaryButtonStyle}>Run final non-repairing Doctor</button>
        </section>}
        {error && <div role="alert" style={errorStyle}>{error}</div>}
      </div>
    </main>
  );
}

const pageStyle: CSSProperties = { height: "100vh", minHeight: 0, maxHeight: "100vh", overflowX: "hidden", overflowY: "auto", scrollbarGutter: "stable", padding: "2rem 1rem", boxSizing: "border-box", background: "linear-gradient(180deg,#111726,#0B0E12)", color: accountPalette.silver, fontFamily: "Inter,ui-sans-serif,system-ui,sans-serif" };
const shellStyle: CSSProperties = { width: "min(860px,100%)", margin: "0 auto", display: "grid", gap: "1rem" };
const sectionStyle: CSSProperties = { display: "grid", gap: ".9rem", padding: "1rem", borderRadius: 18, border: `1px solid ${accountPalette.lineSilver}`, background: accountPalette.panel };
const inputStyle: CSSProperties = { width: "100%", boxSizing: "border-box", marginTop: ".35rem", padding: ".72rem", borderRadius: 12, border: `1px solid ${accountPalette.lineSilver}`, background: "rgba(11,14,18,.55)", color: accountPalette.silver, font: "inherit" };
const primaryButtonStyle: CSSProperties = { padding: ".78rem .95rem", borderRadius: 12, border: "1px solid rgba(126,215,209,.42)", background: "rgba(16,71,75,.78)", color: accountPalette.silver, fontWeight: 800, cursor: "pointer" };
const secondaryButtonStyle: CSSProperties = { ...primaryButtonStyle, background: "rgba(80,92,112,.35)", textAlign: "left" };
const fieldsetStyle: CSSProperties = { display: "grid", gap: ".5rem", border: `1px solid ${accountPalette.lineSilver}`, borderRadius: 12, padding: ".8rem" };
const nestedStyle: CSSProperties = { display: "grid", gap: ".45rem", padding: ".8rem", borderRadius: 12, border: `1px solid ${accountPalette.lineSilver}`, background: "rgba(11,14,18,.4)" };
const mutedStyle: CSSProperties = { color: accountPalette.silverMuted, lineHeight: 1.58 };
const eyebrowStyle: CSSProperties = { fontSize: ".72rem", letterSpacing: ".12em", textTransform: "uppercase", color: accountPalette.sandstone, marginBottom: ".42rem" };
const warningStyle: CSSProperties = { padding: ".7rem", borderRadius: 10, background: "rgba(184,162,123,.12)", color: accountPalette.sandstone };
const errorStyle: CSSProperties = { padding: ".75rem", borderRadius: 12, border: "1px solid rgba(216,165,165,.3)", color: accountPalette.danger, background: "rgba(216,165,165,.08)" };

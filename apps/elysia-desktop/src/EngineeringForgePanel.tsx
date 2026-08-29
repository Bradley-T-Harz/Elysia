import type { EngineeringInspection, EngineeringPreviewPlan, EngineeringPreviewResult } from "./api/bridgeClient";

type Props = {
  inspection: EngineeringInspection | null;
  previewPlan: EngineeringPreviewPlan | null;
  previewResult: EngineeringPreviewResult | null;
  busy: boolean;
  onInspect: () => void;
  onPlanPreview: () => void;
  onApplyPreview: () => void;
};

const colors = {
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  muted: "rgba(199, 210, 218, 0.72)",
  line: "rgba(199, 210, 218, 0.16)",
  warning: "#D6B994",
  blocked: "#D69494"
} as const;

function humanize(value?: string | null): string {
  return (value ?? "unknown").replace(/[_-]/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function shortHash(value?: string | null): string {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "not returned";
}

function familyLabel(family?: string): string {
  const labels: Record<string, string> = {
    geometry: "Geometry",
    cad: "CAD",
    robot_model: "Robot Model",
    cam: "CAM / G-code",
    blend: "Blend",
    fusion: "Fusion limited"
  };
  return labels[family ?? ""] ?? humanize(family);
}

const engineeringFamilies = ["geometry", "cad", "robot_model", "cam", "blend", "fusion"] as const;

export default function EngineeringForgePanel({ inspection, previewPlan, previewResult, busy, onInspect, onPlanPreview, onApplyPreview }: Props) {
  const previewAvailable = inspection?.descriptor.preview_state === "approval_required" && Boolean(inspection.preview_plan_hash);
  const risks = inspection?.risk_flags ?? [];
  const references = inspection?.external_references ?? [];
  return (
    <section style={{ border: `1px solid ${colors.line}`, borderRadius: "14px", padding: "0.8rem", background: "rgba(0,0,0,0.18)", display: "grid", gap: "0.7rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", alignItems: "flex-start" }}>
        <div>
          <div style={{ color: colors.silver, fontWeight: 750 }}>EngineeringForge stewardship</div>
          <div style={{ color: colors.muted, fontSize: "0.8rem", marginTop: "0.25rem" }}>
            {inspection ? `${familyLabel(inspection.descriptor.family)} · ${inspection.descriptor.label}` : "Identify and inspect a selected engineering file safely."}
          </div>
        </div>
        <span style={{ color: colors.teal, border: `1px solid ${colors.teal}`, borderRadius: "999px", padding: "0.2rem 0.45rem", fontSize: "0.68rem" }}>
          local · no actuation
        </span>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" onClick={onInspect} disabled={busy}>Inspect engineering file</button>
        <button type="button" onClick={onPlanPreview} disabled={busy || !previewAvailable}>Plan safe local preview</button>
        <button type="button" onClick={onApplyPreview} disabled={busy || previewPlan?.status !== "planned"}>Create exact-approved preview</button>
      </div>

      <div aria-label="EngineeringForge subpanels" style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
        {engineeringFamilies.map((family) => {
          const active = inspection?.descriptor.family === family;
          return <span key={family} style={{ color: active ? colors.teal : colors.muted, border: `1px solid ${active ? colors.teal : colors.line}`, borderRadius: "999px", padding: "0.16rem 0.4rem", fontSize: "0.68rem" }}>{familyLabel(family)}</span>;
        })}
      </div>

      {inspection ? (
        <>
          <div style={{ color: colors.muted, fontSize: "0.8rem", lineHeight: 1.55, overflowWrap: "anywhere" }}>
            Detected: {humanize(inspection.detected_type)} · {inspection.magic_summary} · {inspection.size_bytes} bytes<br />
            SHA-256: {shortHash(inspection.source_sha256)} · extension/content {inspection.extension_content_match ? "match" : "mismatch or extension-led metadata"}<br />
            Live level: 0–{inspection.descriptor.maximum_live_level} · Static report: {humanize(inspection.descriptor.report_state)} · Preview: {humanize(inspection.descriptor.preview_state)}<br />
            Conversion: {humanize(inspection.descriptor.conversion_state)} · Repair: {humanize(inspection.descriptor.repair_state)} · Simulation: {humanize(inspection.descriptor.simulation_state)}<br />
            Physical output: {humanize(inspection.descriptor.physical_output_state)} · Generation/source modification: {humanize(inspection.descriptor.generation_state)}
          </div>

          <div style={{ color: risks.some((item) => item.severity === "high" || item.severity === "blocked") ? colors.warning : colors.muted, fontSize: "0.8rem", lineHeight: 1.5 }}>
            Risk summary: {risks.map((item) => `${humanize(item.code)} (${item.count}, ${item.severity})`).join(" · ") || "No named static flags; this is not a safety verdict."}
          </div>

          <details>
            <summary style={{ color: colors.teal, cursor: "pointer", fontWeight: 700 }}>Static engineering report</summary>
            <pre style={{ color: colors.muted, fontSize: "0.72rem", whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: "18rem", overflow: "auto" }}>{JSON.stringify(inspection.report, null, 2)}</pre>
          </details>

          <details>
            <summary style={{ color: colors.teal, cursor: "pointer", fontWeight: 700 }}>External references ({inspection.external_reference_count})</summary>
            <div style={{ color: colors.muted, fontSize: "0.76rem", lineHeight: 1.55, marginTop: "0.5rem" }}>
              {references.length ? references.map((reference) => (
                <div key={`${reference.reference_kind}-${reference.reference_hash}`} style={{ overflowWrap: "anywhere" }}>
                  {humanize(reference.reference_kind)} · {reference.display_reference} · {humanize(reference.resolution_state)}
                </div>
              )) : "No external references reported."}
            </div>
          </details>

          <details>
            <summary style={{ color: colors.teal, cursor: "pointer", fontWeight: 700 }}>Capability, worker, artifact, and audit truth</summary>
            <div style={{ color: colors.muted, fontSize: "0.76rem", lineHeight: 1.55, marginTop: "0.5rem", overflowWrap: "anywhere" }}>
              {Object.entries(inspection.capability_truth).map(([level, state]) => `${humanize(level)}: ${humanize(state)}`).join(" · ")}<br />
              Worker boundary: {inspection.worker_key} · {humanize(inspection.worker_state)} · policy {inspection.worker_policy_version}<br />
              Artifacts: {inspection.artifacts.map((artifact) => `${artifact.file_name} (${artifact.artifact_id})`).join(" · ") || "none"}<br />
              Operation: {inspection.operation_id} · request {inspection.request_id ?? "not returned"} · audit {inspection.audit_written ? "persisted" : "not persisted"}<br />
              Proof: source mutation no · network no · scripts no · plugins no · physical output no
            </div>
          </details>
        </>
      ) : null}

      {previewPlan ? (
        <div style={{ color: previewPlan.status === "planned" ? colors.teal : colors.blocked, fontSize: "0.8rem", lineHeight: 1.5 }}>
          Preview plan {humanize(previewPlan.status)} · {humanize(previewPlan.preview_kind)} · source {shortHash(previewPlan.source_sha256)}
          {previewPlan.blocked_reason ? ` · Blocked: ${humanize(previewPlan.blocked_reason)}` : " · fresh exact one-time approval required"}
        </div>
      ) : null}

      {previewResult ? (
        <div style={{ color: previewResult.status === "completed" ? colors.teal : colors.blocked, fontSize: "0.8rem", lineHeight: 1.5 }}>
          Preview {humanize(previewResult.status)} · local artifact {previewResult.artifact?.artifact_id ?? "not created"} · receipt {previewResult.receipt_artifact?.artifact_id ?? "not created"}<br />
          Source/project mutation no/no · network/scripts/plugins/physical output no/no/no/no · audit {previewResult.audit_written ? "persisted" : "not persisted"}
          {previewResult.blocked_reason ? <><br />Blocked: {humanize(previewResult.blocked_reason)}</> : null}
        </div>
      ) : null}

      <div style={{ color: colors.warning, fontSize: "0.76rem", lineHeight: 1.5 }}>
        Reports and projections are descriptive aids, not engineering, structural, manufacturing, robot, machine, printability, or safety certification. There are no Run, Print, Machine, Send, Execute, ROS/Gazebo launch, Fusion upload, patch, overwrite, or “trust as safe” actions here.
      </div>
    </section>
  );
}

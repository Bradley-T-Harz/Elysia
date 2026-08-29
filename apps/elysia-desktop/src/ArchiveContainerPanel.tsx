import { useEffect, useMemo, useState } from "react";
import type {
  ArchiveContainerPreview,
  ArchiveExtractionPlan,
  ArchiveExtractionResult
} from "./api/bridgeClient";

type Props = {
  preview: ArchiveContainerPreview | null;
  plan: ArchiveExtractionPlan | null;
  result: ArchiveExtractionResult | null;
  busy: boolean;
  onInspect: () => void;
  onPlan: (selectedIndexes: number[]) => void;
  onApply: () => void;
};

const colors = {
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  muted: "rgba(199, 210, 218, 0.72)",
  line: "rgba(199, 210, 218, 0.16)",
  blocked: "#D69494"
} as const;

function humanize(value: string): string {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

export default function ArchiveContainerPanel({ preview, plan, result, busy, onInspect, onPlan, onApply }: Props) {
  const [selected, setSelected] = useState<number[]>([]);

  useEffect(() => {
    setSelected([]);
  }, [preview?.operation_id]);

  const selectable = useMemo(
    () => preview?.members.filter((member) => member.extractable && member.is_regular_file) ?? [],
    [preview]
  );
  const blockingRisk = preview?.risk_flags.some((risk) => risk.blocks_extraction) ?? false;
  const canPlan = Boolean(
    preview?.status === "completed" &&
    preview.descriptor.selected_sandbox_extraction_supported &&
    !blockingRisk &&
    selected.length > 0
  );

  function toggle(index: number) {
    setSelected((current) => current.includes(index) ? current.filter((entry) => entry !== index) : [...current, index].sort((a, b) => a - b));
  }

  return (
    <section style={{ border: `1px solid ${colors.line}`, borderRadius: "14px", padding: "0.8rem", background: "rgba(0,0,0,0.18)", display: "grid", gap: "0.7rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", alignItems: "flex-start" }}>
        <div>
          <div style={{ color: colors.silver, fontWeight: 750 }}>ArchiveForge container stewardship</div>
          <div style={{ color: colors.muted, fontSize: "0.8rem", marginTop: "0.25rem" }}>
            {preview ? `${preview.descriptor.label} · ${humanize(preview.status)}` : "Inspect a selected archive or package container."}
          </div>
        </div>
        <span style={{ color: colors.teal, border: `1px solid ${colors.teal}`, borderRadius: "999px", padding: "0.2rem 0.45rem", fontSize: "0.68rem" }}>
          sandbox only
        </span>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" onClick={onInspect} disabled={busy}>List contents & risk</button>
        <button type="button" onClick={() => onPlan(selected)} disabled={busy || !canPlan}>Plan selected sandbox extraction</button>
        <button type="button" onClick={onApply} disabled={busy || plan?.status !== "planned"}>Extract selected to sandbox</button>
      </div>

      {preview && (
        <>
          <div style={{ color: colors.muted, fontSize: "0.8rem", lineHeight: 1.55 }}>
            Type: {humanize(preview.detected_type)} · Members: {preview.member_count} · Projected: {bytes(preview.projected_uncompressed_bytes)} · Ratio: {preview.compression_ratio.toFixed(1)}:1
            <br />
            Extension/content: {preview.extension_content_match ? "match" : "mismatch blocked"} · Encrypted: {preview.encrypted ? "blocked" : "no"} · Nested: {preview.nested_archive_count}
            <br />
            Install: unavailable by design · Execute/import/open: unavailable by design
          </div>

          {preview.risk_flags.length > 0 && (
            <div style={{ color: blockingRisk ? colors.blocked : colors.muted, fontSize: "0.8rem" }}>
              Risk summary: {preview.risk_flags.map((risk) => `${humanize(risk.code)} (${risk.count})`).join(" · ")}
            </div>
          )}

          {selectable.length > 0 ? (
            <details>
              <summary style={{ color: colors.teal, cursor: "pointer", fontWeight: 700 }}>Select regular files ({selected.length} selected)</summary>
              <div style={{ display: "grid", gap: "0.4rem", marginTop: "0.55rem", maxHeight: "14rem", overflow: "auto" }}>
                {selectable.slice(0, 200).map((member) => (
                  <label key={`${member.index}-${member.path_hash}`} style={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", gap: "0.5rem", color: colors.muted, fontSize: "0.78rem" }}>
                    <input type="checkbox" checked={selected.includes(member.index)} onChange={() => toggle(member.index)} />
                    <span style={{ overflowWrap: "anywhere" }}>{member.display_path} · {bytes(member.uncompressed_size)}</span>
                  </label>
                ))}
              </div>
            </details>
          ) : (
            <div style={{ color: colors.muted, fontSize: "0.8rem" }}>No member is eligible for extraction under this format/risk policy.</div>
          )}

          <details>
            <summary style={{ color: colors.teal, cursor: "pointer", fontWeight: 700 }}>Advanced ArchiveForge truth</summary>
            <div style={{ color: colors.muted, fontSize: "0.78rem", lineHeight: 1.55, marginTop: "0.55rem", overflowWrap: "anywhere" }}>
              Manifest: {preview.manifest_digest ?? "not returned"}<br />
              Policy: {preview.policy_version} · Tool: {preview.tool_used}<br />
              Operation: {preview.operation_id} · Request: {preview.request_id ?? "not returned"} · Audit: {preview.audit_written ? "persisted" : "not persisted"}<br />
              Capability: inspect {preview.descriptor.inspection_state} · extraction {preview.descriptor.extraction_state} · license {preview.descriptor.tool_license_status}<br />
              Autonomy: inspection and extraction are user-initiated; extraction always requires fresh exact approval.
              {preview.package_metadata ? <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(preview.package_metadata, null, 2)}</pre> : null}
            </div>
          </details>
        </>
      )}

      {plan && (
        <div style={{ color: plan.status === "planned" ? colors.teal : colors.blocked, fontSize: "0.8rem", lineHeight: 1.5 }}>
          Plan {humanize(plan.status)} · {plan.selected_file_count} selected · {bytes(plan.projected_write_bytes)} · sandbox hash {plan.sandbox_destination_hash}
          {plan.blocked_reason ? ` · Blocked: ${humanize(plan.blocked_reason)}` : " · Fresh exact approval required"}
        </div>
      )}
      {result && (
        <div style={{ color: result.status === "completed" ? colors.teal : colors.blocked, fontSize: "0.8rem", lineHeight: 1.5 }}>
          Result {humanize(result.status)} · {result.extracted_file_count} files · {bytes(result.extracted_bytes)} · audit {result.audit_written ? "persisted" : "not persisted"}
          <br />Source mutated: no · Project root written: no · Installed/executed: no/no
          {result.blocked_reason ? <><br />Blocked: {humanize(result.blocked_reason)}</> : null}
        </div>
      )}
    </section>
  );
}

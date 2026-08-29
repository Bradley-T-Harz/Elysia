import type { BinaryInspection, DatabaseInspection, DatabaseSchemaPreview } from "./api/bridgeClient";

type Props = {
  kind: "database" | "binary";
  database: DatabaseInspection | null;
  schema: DatabaseSchemaPreview | null;
  binary: BinaryInspection | null;
  busy: boolean;
  onInspectDatabase: () => void;
  onPreviewSchema: () => void;
  onInspectBinary: () => void;
};

const colors = {
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  muted: "rgba(199, 210, 218, 0.72)",
  line: "rgba(199, 210, 218, 0.16)",
  warning: "#D6B994"
} as const;

function humanize(value?: string | null): string {
  return (value ?? "unknown").replace(/[_-]/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function shortHash(value?: string | null): string {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : "not returned";
}

export default function DataBinaryForgePanel({ kind, database, schema, binary, busy, onInspectDatabase, onPreviewSchema, onInspectBinary }: Props) {
  const title = kind === "database" ? "DatabaseForge stewardship" : "BinaryForge stewardship";
  return (
    <section style={{ border: `1px solid ${colors.line}`, borderRadius: "14px", padding: "0.8rem", background: "rgba(0,0,0,0.18)", display: "grid", gap: "0.7rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", alignItems: "flex-start" }}>
        <div>
          <div style={{ color: colors.silver, fontWeight: 750 }}>{title}</div>
          <div style={{ color: colors.muted, fontSize: "0.8rem", marginTop: "0.25rem" }}>
            {kind === "database" ? "Static metadata; schema preview requires exact approval." : "Static metadata only; risk indicators are not a malware verdict."}
          </div>
        </div>
        <span style={{ color: colors.teal, border: `1px solid ${colors.teal}`, borderRadius: "999px", padding: "0.2rem 0.45rem", fontSize: "0.68rem" }}>local static only</span>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        {kind === "database" ? (
          <>
            <button type="button" onClick={onInspectDatabase} disabled={busy}>Identify database</button>
            <button type="button" onClick={onPreviewSchema} disabled={busy || database?.status !== "completed" || !database.schema_preview_plan_hash}>Preview schema with approval</button>
          </>
        ) : (
          <button type="button" onClick={onInspectBinary} disabled={busy}>Inspect static metadata</button>
        )}
      </div>

      {kind === "database" && database ? (
        <div style={{ color: colors.muted, fontSize: "0.8rem", lineHeight: 1.55, overflowWrap: "anywhere" }}>
          Type: {humanize(database.detected_engine)} · {database.extension_content_match ? "extension/content match" : "extension/content mismatch"}<br />
          SHA-256: {shortHash(database.source_sha256)} · Size: {database.size_bytes} bytes<br />
          Schema: {humanize(database.descriptor.schema_preview_state)} · Rows: {humanize(database.descriptor.row_preview_state)} · Mutation: {humanize(database.descriptor.mutation_state)}<br />
          Artifact: {database.artifact?.artifact_id ?? "not created"} · Audit: {database.audit_written ? "persisted" : "not persisted"}<br />
          Request: {database.request_id ?? "not returned"} · Operation: {database.operation_id}
          {database.blocked_reason ? <><br /><span style={{ color: colors.warning }}>Blocked: {humanize(database.blocked_reason)}</span></> : null}
        </div>
      ) : null}

      {kind === "database" && schema ? (
        <div style={{ color: schema.status === "completed" ? colors.teal : colors.warning, fontSize: "0.8rem", lineHeight: 1.55, overflowWrap: "anywhere" }}>
          Schema {humanize(schema.status)} · Tables {schema.table_count} · Views {schema.view_count} · Indexes {schema.index_count} · Triggers {schema.trigger_count}<br />
          Snapshot: {humanize(schema.snapshot_strategy)} · {shortHash(schema.snapshot_sha256)}<br />
          Local artifact: {schema.artifact?.artifact_id ?? "not created"} · Rows returned: no · SQL surface: none · Source mutated: no<br />
          Approval: {schema.approval_id ?? "not returned"} · Operation: {schema.operation_id} · Audit: {schema.audit_written ? "persisted" : "not persisted"}
          {schema.blocked_reason ? <><br />Blocked: {humanize(schema.blocked_reason)}</> : null}
        </div>
      ) : null}

      {kind === "binary" && binary ? (
        <div style={{ color: colors.muted, fontSize: "0.8rem", lineHeight: 1.55, overflowWrap: "anywhere" }}>
          Type: {humanize(binary.detected_format)} · Architecture: {binary.architecture ?? "unknown"}{binary.bitness ? ` ${binary.bitness}-bit` : ""}<br />
          SHA-256: {shortHash(binary.source_sha256)} · Entropy: {binary.entropy ?? "unknown"}<br />
          Sections {binary.section_count} · Imports {binary.import_count} · Exports {binary.export_count} · Symbols {binary.symbol_count} · Strings {binary.string_count}<br />
          Risk: {binary.risk_flags.map((flag) => `${humanize(flag.code)} (${flag.count})`).join(" · ") || "no indicators returned"}<br />
          Artifact: {binary.artifact?.artifact_id ?? "not created"} · Audit: {binary.audit_written ? "persisted" : "not persisted"}<br />
          Request: {binary.request_id ?? "not returned"} · Operation: {binary.operation_id}<br />
          Execution unavailable by design · Load/import/install/link unavailable by design · Mutation/patch unavailable by design
          {binary.blocked_reason ? <><br /><span style={{ color: colors.warning }}>Blocked: {humanize(binary.blocked_reason)}</span></> : null}
        </div>
      ) : null}

      <details>
        <summary style={{ color: colors.teal, cursor: "pointer", fontWeight: 700 }}>Advanced policy and receipt truth</summary>
        <div style={{ color: colors.muted, fontSize: "0.78rem", lineHeight: 1.55, marginTop: "0.55rem", overflowWrap: "anywhere" }}>
          {kind === "database" ? (
            <>Policy: {database?.policy_version ?? "database-types-0.1"} · Worker: {database?.worker_policy_version ?? "database-inspection-limits-0.1"}<br />Exact approval binds source hash, sidecar state, plan, path, root, and one-time token. Unknown .db is metadata-only. Future read-only SQL and mutation remain separate gates.</>
          ) : (
            <>Policy: {binary?.policy_version ?? "binary-types-0.1"} · Worker: {binary?.worker_policy_version ?? "binary-inspection-limits-0.1"}<br />Toolchain: {binary?.toolchain.join(", ") || "not run"}. Detailed headers, imports, exports, symbols, and strings remain in the private local artifact. Deeper analysis requires a future sandbox and rights review.</>
          )}
        </div>
      </details>
    </section>
  );
}

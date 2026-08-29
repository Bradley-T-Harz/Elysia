import { useEffect, useMemo, useState } from "react";
import {
  fetchRequestTrace,
  fetchRecentRequestTraces,
  fetchMemoryReceipts,
  fetchMemoryJobs,
  fetchContextReceipts,
  fetchResearchEgressApprovals,
  resolveResearchEgressApproval,
  type RequestTraceData,
  type RequestTraceArtifactSummary,
  type RequestTraceEntry,
  type RequestTraceEnvelope,
  type RequestTraceFileSummary,
  type RequestTraceSnapshot,
  type RequestTraceListItem,
  type RequestTraceToolEntry
} from "./api/bridgeClient";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";

type RequestsPageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
};

type LoadState = "idle" | "loading" | "loaded" | "error";

type BadgeTone =
  | "live"
  | "partial"
  | "planned"
  | "inactive"
  | "unavailable"
  | "degraded"
  | "blocked"
  | "unknown";

const palette = {
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  lineTeal: "rgba(126, 215, 209, 0.24)"
} as const;

function normalize(value?: string | null): string {
  return value?.trim().toLowerCase() ?? "";
}

function humanize(value?: string | null): string {
  if (!value?.trim()) {
    return "Not surfaced";
  }

  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatBoolean(value?: boolean | null): string {
  if (value === true) {
    return "Yes";
  }

  if (value === false) {
    return "No";
  }

  return "Not surfaced";
}

function formatCount(value?: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "0";
  }

  return String(Math.max(0, Math.trunc(value)));
}

function compactListPreview(
  values?: string[] | null,
  emptyLabel = "None surfaced"
): string {
  const compactValues = (values ?? [])
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, 4);

  if (compactValues.length === 0) {
    return emptyLabel;
  }

  const suffix = (values?.length ?? 0) > compactValues.length ? "..." : "";
  return `${compactValues.join(", ")}${suffix}`;
}

function fileSummaryPreview(
  files?: RequestTraceFileSummary[] | null
): string {
  const compactFiles = (files ?? []).slice(0, 4).map((file) => {
    const name = file.file_name || file.file_id || "file";
    const status = file.status ? ` (${humanize(file.status)})` : "";
    const parser = file.parser_used ? ` via ${humanize(file.parser_used)}` : "";
    const chunks = file.chunks_used_count ? `, ${file.chunks_used_count} chunks` : "";
    return `${name}${status}${parser}${chunks}`;
  });

  if (compactFiles.length === 0) {
    return "None surfaced";
  }

  const suffix = (files?.length ?? 0) > compactFiles.length ? "..." : "";
  return `${compactFiles.join(", ")}${suffix}`;
}

function toolSummaryPreview(
  tools?: RequestTraceToolEntry[] | null
): string {
  const compactTools = (tools ?? []).slice(0, 4).map((tool) => {
    const label = tool.tool_label || tool.tool_key || "tool";
    const state = tool.state ? ` (${humanize(tool.state)})` : "";
    return `${label}${state}`;
  });

  if (compactTools.length === 0) {
    return "None surfaced";
  }

  const suffix = (tools?.length ?? 0) > compactTools.length ? "..." : "";
  return `${compactTools.join(", ")}${suffix}`;
}

function artifactSummaryPreview(
  artifacts?: RequestTraceArtifactSummary[] | null
): string {
  const compactArtifacts = (artifacts ?? []).slice(0, 4).map((artifact) => {
    const title = artifact.title || artifact.artifact_id || "artifact";
    const kind = artifact.kind ? ` (${humanize(artifact.kind)})` : "";
    return `${title}${kind}`;
  });

  if (compactArtifacts.length === 0) {
    return "None surfaced";
  }

  const suffix = (artifacts?.length ?? 0) > compactArtifacts.length ? "..." : "";
  return `${compactArtifacts.join(", ")}${suffix}`;
}

function researchEvidenceValue(snapshot?: RequestTraceSnapshot | null): string {
  if (!snapshot?.research_status) {
    return "Planned / none loaded";
  }

  return String(snapshot.evidence_packet_count ?? 0);
}

function researchBoundaryValue(snapshot?: RequestTraceSnapshot | null): string {
  if (!snapshot?.research_status) {
    return "Not crossed in loaded trace";
  }

  if (snapshot.network_access_used) {
    return "External public web crossed for query terms";
  }

  return "Not crossed";
}

function formatDateTime(value?: string | null): string {
  if (!value?.trim()) {
    return "Not surfaced";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function toneForStatus(value?: string | null): BadgeTone {
  const state = normalize(value);

  if (
    state === "live" ||
    state === "partial" ||
    state === "planned" ||
    state === "inactive" ||
    state === "unavailable" ||
    state === "degraded" ||
    state === "blocked"
  ) {
    return state;
  }

  if (state === "ok" || state === "completed" || state === "running") {
    return "live";
  }

  if (state === "pending_startup" || state === "unknown") {
    return "partial";
  }

  if (state === "error") {
    return "unavailable";
  }

  return "unknown";
}

function drawerStateForTrace(
  loadState: LoadState,
  trace?: RequestTraceData | null
): DrawerSection["state"] {
  if (loadState === "loading") {
    return "partial";
  }

  if (loadState === "error") {
    return "unavailable";
  }

  const status = normalize(trace?.request_status);

  if (status === "completed" || status === "running") {
    return "live";
  }

  if (status === "degraded") {
    return "degraded";
  }

  if (status === "blocked") {
    return "degraded";
  }

  if (status === "error") {
    return "unavailable";
  }

  if (status === "pending_startup" || status === "unknown") {
    return "partial";
  }

  return loadState === "loaded" ? "partial" : "inactive";
}

function badgeColors(tone: BadgeTone) {
  switch (tone) {
    case "live":
      return {
        label: "Live",
        color: palette.teal,
        border: "rgba(126, 215, 209, 0.32)",
        background: "rgba(126, 215, 209, 0.08)"
      };
    case "partial":
      return {
        label: "Partial",
        color: palette.sandstone,
        border: "rgba(184, 162, 123, 0.34)",
        background: "rgba(184, 162, 123, 0.10)"
      };
    case "planned":
      return {
        label: "Planned",
        color: palette.bronze,
        border: "rgba(138, 106, 60, 0.36)",
        background: "rgba(138, 106, 60, 0.10)"
      };
    case "inactive":
      return {
        label: "Inactive",
        color: palette.silverMuted,
        border: "rgba(199, 210, 218, 0.18)",
        background: "rgba(199, 210, 218, 0.05)"
      };
    case "unavailable":
      return {
        label: "Unavailable",
        color: "#D8A5A5",
        border: "rgba(216, 165, 165, 0.34)",
        background: "rgba(216, 165, 165, 0.08)"
      };
    case "degraded":
      return {
        label: "Degraded",
        color: "#D7A97E",
        border: "rgba(215, 169, 126, 0.34)",
        background: "rgba(215, 169, 126, 0.09)"
      };
    case "blocked":
      return {
        label: "Blocked",
        color: "#E0A0A0",
        border: "rgba(224, 160, 160, 0.38)",
        background: "rgba(224, 160, 160, 0.09)"
      };
    case "unknown":
    default:
      return {
        label: "Unknown",
        color: palette.silverMuted,
        border: "rgba(199, 210, 218, 0.20)",
        background: "rgba(199, 210, 218, 0.06)"
      };
  }
}

function PillBadge({
  value,
  tone
}: {
  value?: string | null;
  tone?: BadgeTone;
}) {
  const resolvedTone = tone ?? toneForStatus(value);
  const colors = badgeColors(resolvedTone);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "max-content",
        padding: "0.22rem 0.56rem",
        borderRadius: "999px",
        border: `1px solid ${colors.border}`,
        background: colors.background,
        color: colors.color,
        fontSize: "0.68rem",
        fontWeight: 700,
        letterSpacing: "0.055em",
        textTransform: "uppercase",
        whiteSpace: "nowrap"
      }}
    >
      {value?.trim() ? humanize(value) : colors.label}
    </span>
  );
}

function SummaryCard({
  title,
  value,
  detail,
  tone
}: {
  title: string;
  value: string;
  detail: string;
  tone: BadgeTone;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: "0.48rem",
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.62) 0%, rgba(18, 25, 37, 0.74) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.75rem",
          alignItems: "flex-start"
        }}
      >
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.sandstone
          }}
        >
          {title}
        </div>
        <PillBadge value={tone} tone={tone} />
      </div>

      <div
        style={{
          color: palette.silver,
          fontWeight: 750,
          fontSize: "1.06rem",
          lineHeight: 1.32
        }}
      >
        {value}
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.5,
          fontSize: "0.88rem"
        }}
      >
        {detail}
      </div>
    </div>
  );
}

function FieldRow({
  label,
  value
}: {
  label: string;
  value: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "150px minmax(0, 1fr)",
        gap: "0.75rem",
        alignItems: "baseline",
        padding: "0.48rem 0",
        borderBottom: `1px solid rgba(199, 210, 218, 0.08)`
      }}
    >
      <div
        style={{
          color: palette.sandstone,
          fontSize: "0.74rem",
          letterSpacing: "0.07em",
          textTransform: "uppercase"
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: value === "Not surfaced" ? palette.silverMuted : palette.silver,
          lineHeight: 1.45,
          minWidth: 0,
          overflowWrap: "anywhere"
        }}
      >
        {value}
      </div>
    </div>
  );
}

function EmptyState({
  title,
  detail,
  compact = false
}: {
  title: string;
  detail: string;
  compact?: boolean;
}) {
  return (
    <section
      style={{
        display: "grid",
        alignContent: "center",
        minHeight: compact ? "150px" : "260px",
        padding: "1rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.78) 100%)"
      }}
    >
      <div
        style={{
          display: "grid",
          gap: "0.45rem",
          maxWidth: "70ch"
        }}
      >
        <strong style={{ color: palette.silver, fontSize: "1.05rem" }}>
          {title}
        </strong>
        <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
          {detail}
        </div>
      </div>
    </section>
  );
}

function StatusPanel({
  title,
  badge,
  detail,
  tone = "partial"
}: {
  title: string;
  badge: string;
  detail: string;
  tone?: BadgeTone;
}) {
  return (
    <section
      style={{
        display: "grid",
        gap: "0.7rem",
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineBronze}`,
        background:
          "linear-gradient(180deg, rgba(43, 31, 21, 0.34) 0%, rgba(18, 25, 37, 0.72) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.75rem",
          alignItems: "flex-start"
        }}
      >
        <div
          style={{
            fontSize: "0.82rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.bronze
          }}
        >
          {title}
        </div>
        <PillBadge value={badge} tone={tone} />
      </div>

      <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
        {detail}
      </div>
    </section>
  );
}

function TraceOverview({ trace }: { trace?: RequestTraceData | null }) {
  if (!trace) {
    return (
      <EmptyState
        title="No request trace is loaded."
        detail="Paste a request ID to inspect whatever request-trace truth is available from the local bridge."
        compact
      />
    );
  }

  return (
    <section
      style={{
        display: "grid",
        gap: "0.72rem",
        padding: "1rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.74) 0%, rgba(11, 14, 18, 0.82) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "1rem",
          alignItems: "flex-start"
        }}
      >
        <div>
          <div
            style={{
              fontSize: "0.76rem",
              letterSpacing: "0.11em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.22rem"
            }}
          >
            Loaded trace
          </div>
          <h2
            style={{
              margin: 0,
              color: palette.silver,
              fontSize: "1.24rem",
              lineHeight: 1.2,
              overflowWrap: "anywhere"
            }}
          >
            {trace.request_id || "Unknown request"}
          </h2>
        </div>

        <PillBadge value={trace.request_status} />
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.58
        }}
      >
        <strong style={{ color: palette.silver }}>
          {trace.current_phase_label || "No current phase label surfaced."}
        </strong>
        {trace.current_phase_detail ? ` ${trace.current_phase_detail}` : ""}
      </div>

      <div style={{ display: "grid" }}>
        <FieldRow label="Phase" value={trace.current_phase || "Not surfaced"} />
        <FieldRow
          label="Created"
          value={formatDateTime(trace.created_at_utc)}
        />
        <FieldRow
          label="Updated"
          value={formatDateTime(trace.updated_at_utc)}
        />
        <FieldRow
          label="Completed"
          value={formatDateTime(trace.completed_at_utc)}
        />
      </div>
    </section>
  );
}

function SnapshotPanel({
  snapshot
}: {
  snapshot?: RequestTraceSnapshot | null;
}) {
  const warnings = snapshot?.warnings ?? [];
  const errors = snapshot?.errors ?? [];
  const memoryClasses = snapshot?.memory_classes ?? [];
  const codingTool = (snapshot?.tools_used ?? []).find(
    (tool) => tool.tool_kind === "coding_operation"
  );

  return (
    <section
      style={{
        display: "grid",
        gap: "0.72rem",
        padding: "1rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.74) 0%, rgba(11, 14, 18, 0.82) 100%)"
      }}
    >
      <div
        style={{
          fontSize: "0.76rem",
          letterSpacing: "0.11em",
          textTransform: "uppercase",
          color: palette.sandstone
        }}
      >
        Snapshot truth
      </div>

      <div style={{ display: "grid" }}>
        <FieldRow label="Route" value={snapshot?.route_used || "Not surfaced"} />
        <FieldRow label="UI surface" value={snapshot?.ui_surface || "Not surfaced"} />
        <FieldRow label="Mode" value={snapshot?.selected_mode || "Not surfaced"} />
        <FieldRow label="Role" value={snapshot?.selected_role || "Not surfaced"} />
        <FieldRow
          label="Runtime"
          value={snapshot?.selected_runtime || "Not surfaced"}
        />
        <FieldRow
          label="Model tag"
          value={snapshot?.selected_model_runtime_tag || "Not surfaced"}
        />
        <FieldRow
          label="Locality"
          value={snapshot?.locality_state || "Not surfaced"}
        />
        <FieldRow
          label="Approval"
          value={snapshot?.approval_state || "Not surfaced"}
        />
        <FieldRow
          label="Approval needed"
          value={formatBoolean(snapshot?.approval_needed)}
        />
        <FieldRow
          label="Fallback"
          value={formatBoolean(snapshot?.used_fallback)}
        />
        <FieldRow
          label="Mode profile"
          value={snapshot?.mode_profile_label || snapshot?.mode_profile_key || "Not surfaced"}
        />
        <FieldRow
          label="Mode authority"
          value={formatBoolean(snapshot?.authority_granted_by_mode)}
        />
        <FieldRow
          label="Mode posture"
          value={compactListPreview(snapshot?.mode_profile_effects)}
        />
        <FieldRow
          label="Memory classes"
          value={memoryClasses.length > 0 ? memoryClasses.join(", ") : "Not surfaced"}
        />
        <FieldRow label="Skill" value={snapshot?.skill_name || "Not surfaced"} />
        <FieldRow label="Tool" value={snapshot?.tool_name || "Not surfaced"} />
        <FieldRow label="App" value={snapshot?.app_name || "Not surfaced"} />
        <FieldRow label="Worker" value={snapshot?.worker_name || "Not surfaced"} />
        <FieldRow
          label="Execution tool"
          value={snapshot?.execution_tool_kind || "Not surfaced"}
        />
        <FieldRow
          label="Execution status"
          value={snapshot?.execution_status || "Not surfaced"}
        />
        <FieldRow
          label="Execution operation"
          value={snapshot?.execution_operation || "Not surfaced"}
        />
        <FieldRow
          label="Execution summary"
          value={snapshot?.execution_summary || "Not surfaced"}
        />
        <FieldRow
          label="Files attached"
          value={formatCount(snapshot?.files_attached_count)}
        />
        <FieldRow
          label="File summaries"
          value={fileSummaryPreview(snapshot?.files_attached)}
        />
        <FieldRow
          label="Files used"
          value={formatCount(snapshot?.files_used_count)}
        />
        <FieldRow
          label="File chunks used"
          value={formatCount(snapshot?.file_chunks_used_count)}
        />
        <FieldRow
          label="File parsers"
          value={compactListPreview(snapshot?.file_parsers_used)}
        />
        <FieldRow
          label="File memory"
          value={formatBoolean(snapshot?.file_memory_promotion)}
        />
        <FieldRow
          label="File outward"
          value={formatBoolean(snapshot?.file_outward_sharing)}
        />
        <FieldRow
          label="Tools available"
          value={formatCount(snapshot?.tools_available_count)}
        />
        <FieldRow
          label="Tools used"
          value={formatCount(snapshot?.tools_used_count)}
        />
        <FieldRow
          label="Used tools"
          value={toolSummaryPreview(snapshot?.tools_used)}
        />
        {codingTool ? (
          <>
            <FieldRow label="Operation ID" value={codingTool.operation_id || "Not surfaced"} />
            <FieldRow label="Approval ID" value={codingTool.approval_id || "Not surfaced"} />
            <FieldRow label="Relative paths" value={compactListPreview(codingTool.relative_paths)} />
            <FieldRow label="Source / plan / result hashes" value={[codingTool.source_hash, codingTool.plan_hash, codingTool.result_hash].filter(Boolean).join(" · ") || "Not surfaced"} />
            <FieldRow label="Mutation class" value={codingTool.mutation_class || "Not surfaced"} />
            <FieldRow label="Backup / rollback" value={codingTool.backup_summary || snapshot?.rollback_note || "Not surfaced"} />
            <FieldRow label="Durable coding audit" value={formatBoolean(codingTool.audit_persisted)} />
          </>
        ) : null}
        <FieldRow
          label="Artifacts"
          value={formatCount(snapshot?.artifact_count)}
        />
        <FieldRow
          label="Artifact summaries"
          value={artifactSummaryPreview(snapshot?.artifacts)}
        />
        <FieldRow
          label="Repo context"
          value={snapshot?.repo_context_status || "Not surfaced"}
        />
        <FieldRow
          label="Repo files"
          value={compactListPreview(snapshot?.repo_context_files)}
        />
        <FieldRow
          label="Patch plan"
          value={snapshot?.patch_plan_status || "Not surfaced"}
        />
        <FieldRow
          label="Patch files"
          value={compactListPreview(snapshot?.patch_plan_files)}
        />
        <FieldRow label="Patch id" value={snapshot?.patch_id || "Not surfaced"} />
        <FieldRow
          label="Patch hash"
          value={snapshot?.patch_hash || "Not surfaced"}
        />
        <FieldRow
          label="Diff preview"
          value={snapshot?.patch_diff_preview || "Not surfaced"}
        />
        <FieldRow
          label="Rollback"
          value={snapshot?.rollback_note || "Not surfaced"}
        />
        <FieldRow
          label="Command"
          value={snapshot?.command_key || "Not surfaced"}
        />
        <FieldRow
          label="Command argv"
          value={compactListPreview(snapshot?.command_argv)}
        />
        <FieldRow
          label="Command exit"
          value={
            snapshot?.command_exit_code === null ||
            snapshot?.command_exit_code === undefined
              ? "Not surfaced"
              : String(snapshot.command_exit_code)
          }
        />
        <FieldRow
          label="Command output"
          value={snapshot?.command_output_preview || "Not surfaced"}
        />
        <FieldRow
          label="Mutation"
          value={formatBoolean(snapshot?.mutated_files)}
        />
        <FieldRow label="Shell" value={formatBoolean(snapshot?.shell_used)} />
        <FieldRow
          label="Git mutation"
          value={formatBoolean(snapshot?.git_mutation_used)}
        />
        <FieldRow
          label="External worker"
          value={formatBoolean(snapshot?.external_worker_used)}
        />
        <FieldRow
          label="Conversation"
          value={snapshot?.related_conversation_id || "Not surfaced"}
        />
        <FieldRow
          label="Project"
          value={snapshot?.related_project_id || "Not surfaced"}
        />
        <FieldRow
          label="Warnings"
          value={warnings.length > 0 ? warnings.join(" | ") : "None surfaced"}
        />
        <FieldRow
          label="Errors"
          value={errors.length > 0 ? errors.join(" | ") : "None surfaced"}
        />
      </div>
    </section>
  );
}

function TimelineEntryCard({
  entry,
  index
}: {
  entry: RequestTraceEntry;
  index: number;
}) {
  const metaItems = [
    entry.selected_mode ? `Mode ${entry.selected_mode}` : null,
    entry.selected_role ? `Role ${entry.selected_role}` : null,
    entry.selected_runtime ? `Runtime ${entry.selected_runtime}` : null,
    entry.selected_model_runtime_tag,
    entry.locality_state ? `Locality ${entry.locality_state}` : null,
    entry.approval_state ? `Approval ${entry.approval_state}` : null,
    entry.used_fallback === true
      ? "Fallback used"
      : entry.used_fallback === false
        ? "No fallback"
        : null,
    entry.skill_name ? `Skill ${entry.skill_name}` : null,
    entry.tool_name ? `Tool ${entry.tool_name}` : null,
    entry.app_name ? `App ${entry.app_name}` : null,
    entry.worker_name ? `Worker ${entry.worker_name}` : null,
    entry.execution_tool_kind ? `Execution ${entry.execution_tool_kind}` : null,
    entry.execution_status ? `Status ${entry.execution_status}` : null,
    entry.execution_operation ? `Operation ${entry.execution_operation}` : null
  ].filter((value): value is string => Boolean(value));

  const memoryClasses = entry.memory_classes ?? [];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "34px minmax(0, 1fr)",
        gap: "0.75rem"
      }}
    >
      <div
        aria-hidden="true"
        style={{
          display: "grid",
          justifyItems: "center"
        }}
      >
        <div
          style={{
            width: "1.55rem",
            height: "1.55rem",
            borderRadius: "999px",
            display: "grid",
            placeItems: "center",
            border: `1px solid ${palette.lineTeal}`,
            background: "rgba(16, 41, 43, 0.72)",
            color: palette.teal,
            fontWeight: 750,
            fontSize: "0.78rem"
          }}
        >
          {index + 1}
        </div>
      </div>

      <article
        style={{
          display: "grid",
          gap: "0.56rem",
          padding: "0.88rem",
          borderRadius: "17px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.78) 100%)"
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "0.75rem",
            alignItems: "flex-start"
          }}
        >
          <div style={{ minWidth: 0 }}>
            <strong style={{ color: palette.silver }}>
              {entry.label || "Request activity"}
            </strong>
            <div
              style={{
                color: palette.silverMuted,
                fontSize: "0.78rem",
                marginTop: "0.18rem",
                overflowWrap: "anywhere"
              }}
            >
              {entry.phase || "unknown phase"} · {formatDateTime(entry.timestamp_utc)}
            </div>
          </div>

          <PillBadge value={entry.approval_state ?? entry.locality_state} />
        </div>

        {entry.detail && (
          <div style={{ color: palette.silverMuted, lineHeight: 1.5 }}>
            {entry.detail}
          </div>
        )}

        {entry.execution_summary && (
          <div style={{ color: palette.silverMuted, lineHeight: 1.5 }}>
            <strong style={{ color: palette.silver }}>Execution summary:</strong>{" "}
            {entry.execution_summary}
          </div>
        )}

        {memoryClasses.length > 0 && (
          <div style={{ color: palette.silverMuted, lineHeight: 1.45 }}>
            Memory classes: {memoryClasses.join(", ")}
          </div>
        )}

        {metaItems.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {metaItems.map((item) => (
              <span
                key={item}
                style={{
                  padding: "0.25rem 0.52rem",
                  borderRadius: "999px",
                  border: `1px solid ${palette.lineSilver}`,
                  background: "rgba(11, 14, 18, 0.32)",
                  color: palette.silverMuted,
                  fontSize: "0.76rem"
                }}
              >
                {item}
              </span>
            ))}
          </div>
        )}
      </article>
    </div>
  );
}

function TimelinePanel({
  entries
}: {
  entries: RequestTraceEntry[];
}) {
  return (
    <section
      style={{
        display: "grid",
        gap: "0.8rem",
        padding: "1rem",
        borderRadius: "20px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.74) 0%, rgba(11, 14, 18, 0.82) 100%)"
      }}
    >
      <div>
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.11em",
            textTransform: "uppercase",
            color: palette.sandstone,
            marginBottom: "0.2rem"
          }}
        >
          Timeline
        </div>
        <div style={{ color: palette.silverMuted, lineHeight: 1.48 }}>
          Compact trace entries only. Raw logs and journals are not dumped here.
        </div>
      </div>

      {entries.length > 0 ? (
        <div style={{ display: "grid", gap: "0.75rem" }}>
          {entries.map((entry, index) => (
            <TimelineEntryCard
              key={entry.entry_id ?? `${entry.phase}-${index}`}
              entry={entry}
              index={index}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No trace entries are available for this request."
          detail="The request trace route may still return a snapshot or fallback status even when no phase entries have been appended."
          compact
        />
      )}
    </section>
  );
}

export default function RequestsPage({
  startupReady,
  onRightDrawerSectionsChange
}: RequestsPageProps) {
  const [requestIdInput, setRequestIdInput] = useState("");
  const [activeRequestId, setActiveRequestId] = useState("");
  const [traceEnvelope, setTraceEnvelope] =
    useState<RequestTraceEnvelope | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [recentTraces, setRecentTraces] = useState<RequestTraceListItem[]>([]);
  const [recentLoadError, setRecentLoadError] = useState<string | null>(null);
  const [memoryReceipts, setMemoryReceipts] = useState<Array<Record<string, any>>>([]);
  const [memoryJobs, setMemoryJobs] = useState<Array<Record<string, any>>>([]);
  const [contextReceipts, setContextReceipts] = useState<Array<Record<string, any>>>([]);
  const [researchApprovals, setResearchApprovals] = useState<Array<Record<string, any>>>([]);
  const [requestActionNotice, setRequestActionNotice] = useState<string | null>(null);
  const [requestRefresh, setRequestRefresh] = useState(0);

  const traceData = traceEnvelope?.data ?? null;
  const snapshot = traceData?.snapshot ?? null;
  const traceEntries = traceData?.trace_entries ?? [];

  async function loadTrace(requestIdOverride?: string) {
    const requestId = (requestIdOverride ?? requestIdInput).trim();

    if (!requestId) {
      setLoadState("error");
      setLoadError("Enter a request ID before loading a trace.");
      return;
    }

    setLoadState("loading");
    setLoadError(null);
    setActiveRequestId(requestId);

    const result = await fetchRequestTrace(requestId);

    setTraceEnvelope(result.payload);

    const firstError =
      result.payload.errors?.find((value) => value.trim()) ?? null;

    if (!result.ok || result.payload.status === "error") {
      setLoadState("error");
      setLoadError(
        firstError ??
          "Request trace endpoint did not return usable request truth."
      );
      return;
    }

    setLoadState("loaded");
    setLoadError(null);
  }

  useEffect(() => {
    if (!startupReady) return;
    let cancelled = false;
    void fetchRecentRequestTraces(50).then((result) => {
      if (cancelled) return;
      if (!result.ok) {
        setRecentLoadError(result.payload.errors?.[0] ?? "Recent request history is unavailable.");
        return;
      }
      setRecentTraces(result.payload.data?.request_traces ?? []);
      setRecentLoadError(null);
    });
    void fetchMemoryReceipts().then((result) => {
      if (cancelled) return;
      setMemoryReceipts(
        result.ok && Array.isArray(result.payload.data?.receipts)
          ? result.payload.data.receipts
          : []
      );
    });
    void fetchMemoryJobs().then((result) => {
      if (cancelled) return;
      setMemoryJobs(
        result.ok && Array.isArray(result.payload.data?.jobs)
          ? result.payload.data.jobs as Array<Record<string, any>>
          : []
      );
    });
    void fetchContextReceipts(50).then((result) => {
      if (cancelled) return;
      setContextReceipts(
        result.ok && Array.isArray(result.payload.data?.context_receipts)
          ? result.payload.data.context_receipts as Array<Record<string, any>>
          : []
      );
    });
    void fetchResearchEgressApprovals().then((result) => {
      if (cancelled) return;
      setResearchApprovals(
        result.ok && Array.isArray(result.payload.data?.approvals)
          ? result.payload.data.approvals as Array<Record<string, any>>
          : []
      );
    });
    return () => {
      cancelled = true;
    };
  }, [startupReady, requestRefresh]);

  async function resolveResearchApproval(approvalId: string, approve: boolean) {
    const result = await resolveResearchEgressApproval(approvalId, approve, approve);
    setRequestActionNotice(
      result.ok
        ? approve
          ? "The exact bound research request executed once; its approval token was consumed server-side."
          : "The research egress request was denied; no query was sent."
        : result.payload.errors?.[0] ?? "The research approval could not be resolved."
    );
    if (result.ok) setRequestRefresh((value) => value + 1);
  }

  const traceDrawerState = drawerStateForTrace(loadState, traceData);

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    return [
      {
        key: "active_context",
        title: "Active Context",
        state: traceDrawerState,
        accent: "warm",
        rows: [
          { label: "Room", value: "Requests" },
          { label: "Surface", value: "Inspectable request ledger" },
          { label: "Source", value: "/request-trace/{request_id}" }
        ]
      },
      {
        key: "request_ledger",
        title: "Request Ledger",
        state: snapshot ? traceDrawerState : "planned",
        rows: [
          { label: "Recent history", value: `${recentTraces.length} bounded in-memory traces` },
          { label: "Per-request lookup", value: "Live when request ID is known" },
          {
            label: "Mode profile",
            value: snapshot?.mode_profile_label || snapshot?.mode_profile_key || "Not loaded"
          },
          { label: "Files attached", value: formatCount(snapshot?.files_attached_count) },
          { label: "Files used", value: formatCount(snapshot?.files_used_count) },
          { label: "File chunks", value: formatCount(snapshot?.file_chunks_used_count) },
          { label: "Tools available", value: formatCount(snapshot?.tools_available_count) },
          { label: "Tools used", value: formatCount(snapshot?.tools_used_count) },
          { label: "Artifacts", value: formatCount(snapshot?.artifact_count) },
          { label: "Raw logs", value: "Not dumped in UI" }
        ]
      },
      {
        key: "current_trace",
        title: "Current Trace",
        state: traceDrawerState,
        rows: [
          { label: "Request ID", value: traceData?.request_id ?? (activeRequestId || "None loaded") },
          { label: "Status", value: humanize(traceData?.request_status) },
          { label: "Phase", value: humanize(traceData?.current_phase) },
          { label: "Entries", value: String(traceEntries.length) },
          {
            label: "Execution",
            value: humanize(snapshot?.execution_status)
          },
          {
            label: "Executor",
            value: humanize(snapshot?.execution_tool_kind)
          },
          {
            label: "Operation",
            value: humanize(snapshot?.execution_operation)
          }
        ]
      },
      {
        key: "tools_artifacts",
        title: "Tools / Artifacts",
        state: traceDrawerState,
        rows: [
          { label: "Used tools", value: toolSummaryPreview(snapshot?.tools_used) },
          { label: "Artifacts", value: artifactSummaryPreview(snapshot?.artifacts) },
          { label: "Repo context", value: humanize(snapshot?.repo_context_status) },
          { label: "Patch plan", value: humanize(snapshot?.patch_plan_status) },
          { label: "Patch hash", value: snapshot?.patch_hash || "Not surfaced" },
          { label: "Command", value: snapshot?.command_key || "Not surfaced" },
          {
            label: "Command exit",
            value:
              snapshot?.command_exit_code === null ||
              snapshot?.command_exit_code === undefined
                ? "Not surfaced"
                : String(snapshot.command_exit_code)
          },
          { label: "Mutation", value: formatBoolean(snapshot?.mutated_files) },
          { label: "Shell", value: formatBoolean(snapshot?.shell_used) },
          { label: "Git mutation", value: formatBoolean(snapshot?.git_mutation_used) },
          { label: "External worker", value: formatBoolean(snapshot?.external_worker_used) }
        ]
      },
      {
        key: "boundary_evidence",
        title: "Boundary / Evidence",
        state: snapshot?.research_status ? "partial" : "planned",
        rows: [
          { label: "Evidence packets", value: researchEvidenceValue(snapshot) },
          { label: "Worker", value: humanize(snapshot?.research_worker_name) },
          { label: "Boundary", value: researchBoundaryValue(snapshot) },
          { label: "Queries sent", value: String(snapshot?.research_query_count ?? 0) },
          { label: "Private context outward", value: formatBoolean(snapshot?.private_context_sent) },
          { label: "Page fetch", value: formatBoolean(snapshot?.page_fetch_used) },
          { label: "Cloud search", value: formatBoolean(snapshot?.cloud_search_used) },
          { label: "Cloud model", value: formatBoolean(snapshot?.cloud_model_used) }
        ]
      }
    ];
  }, [
    activeRequestId,
    loadState,
    snapshot,
    traceData,
    traceDrawerState,
    traceEntries.length,
    recentTraces.length
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);

    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  const loadedStatusText =
    loadState === "idle"
      ? "No request loaded"
      : loadState === "loading"
        ? "Loading trace"
        : loadState === "error"
          ? "Trace unavailable"
          : humanize(traceData?.request_status);

  const lookupDetail =
    loadState === "error"
      ? loadError ?? "Trace lookup failed."
      : activeRequestId
        ? `Inspecting request ${activeRequestId}.`
        : "Paste a known request ID from a drawer, conversation message, or bridge response.";

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        minHeight: 0,
        height: "100%",
        overflow: "hidden"
      }}
    >
      <div>
        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: palette.sandstone,
            marginBottom: "0.4rem"
          }}
        >
          Requests
        </div>
        <h1
          style={{
            margin: 0,
            fontSize: "2.1rem",
            lineHeight: 1.1,
            color: palette.silver
          }}
        >
          Inspectable request ledger.
        </h1>
        <div
          style={{
            marginTop: "0.65rem",
            color: palette.silverMuted,
            lineHeight: 1.6,
            maxWidth: "84ch"
          }}
        >
          This room shows request truth currently available from the local
          request-trace surface, including governed coding operations. Recent
          history is bounded and in-memory, not a durable raw-log browser. Evidence packet truth is shown when a loaded request trace
          includes bounded research evidence. Raw logs, raw journals, replay
          controls, and mutation controls are intentionally not exposed here.
        </div>
      </div>

      <div
        className="elysia-summary-grid-4"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
          gap: "0.82rem"
        }}
      >
        <SummaryCard
          title="History"
          value={recentLoadError ? "Unavailable" : `${recentTraces.length} recent`}
          detail={recentLoadError ?? "Bounded in-memory summaries include chat, research, and governed coding operations."}
          tone={recentLoadError ? "unavailable" : "live"}
        />
        <SummaryCard
          title="Per-request lookup"
          value="Live"
          detail="A known request ID can be inspected through /request-trace/{request_id}."
          tone="live"
        />
        <SummaryCard
          title="Loaded trace"
          value={loadedStatusText}
          detail={lookupDetail}
          tone={toneForStatus(traceData?.request_status)}
        />
        <SummaryCard
          title="Evidence packets"
          value={researchEvidenceValue(snapshot)}
          detail={
            snapshot?.research_status
              ? "Bounded research trace truth is loaded. Search snippets remain evidence candidates, not proof."
              : "No bounded research evidence is loaded for the current trace."
          }
          tone={snapshot?.research_status ? "partial" : "planned"}
        />
      </div>

      <section
        style={{
          display: "grid",
          gap: "0.75rem",
          padding: "0.9rem",
          borderRadius: "18px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.76) 100%)"
        }}
      >
        <div
          className="elysia-toolbar-grid-2"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(280px, 1fr) auto",
            gap: "0.7rem",
            alignItems: "center"
          }}
        >
          <input
            aria-label="Request ID"
            value={requestIdInput}
            onChange={(event) => setRequestIdInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void loadTrace();
              }
            }}
            placeholder="Paste request ID, for example req_..."
            style={{
              minWidth: 0,
              padding: "0.66rem 0.78rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.72)",
              color: palette.silver,
              outline: "none"
            }}
          />

          <button
            type="button"
            onClick={() => void loadTrace()}
            disabled={loadState === "loading"}
            style={{
              padding: "0.66rem 0.9rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineTeal}`,
              background:
                "linear-gradient(180deg, rgba(16, 41, 43, 0.58) 0%, rgba(18, 25, 37, 0.76) 100%)",
              color: palette.teal,
              cursor: loadState === "loading" ? "wait" : "pointer",
              fontWeight: 700,
              whiteSpace: "nowrap"
            }}
          >
            {loadState === "loading" ? "Loading trace..." : "Load trace"}
          </button>
        </div>

        {loadError && (
          <div style={{ color: "#D8A5A5", lineHeight: 1.5 }}>{loadError}</div>
        )}
      </section>

      <div
        className="elysia-responsive-split"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(340px, 0.95fr) minmax(420px, 1.05fr)",
          gap: "1rem",
          minHeight: 0,
          flex: 1,
          overflow: "hidden"
        }}
      >
        <div
          className="elysia-stacked-pane"
          style={{
            display: "grid",
            gap: "1rem",
            alignContent: "start",
            minHeight: 0,
            overflowY: "auto",
            paddingRight: "0.1rem"
          }}
        >
          <TraceOverview trace={traceData} />
          <section
            style={{
              display: "grid",
              gap: "0.65rem",
              padding: "1rem",
              borderRadius: "18px",
              border: `1px solid ${palette.lineTeal}`,
              background: "rgba(11, 25, 29, 0.58)"
            }}
          >
            <div style={{ color: palette.teal, fontWeight: 700 }}>Recent request and operation ledger</div>
            <div style={{ color: palette.silverMuted, lineHeight: 1.5 }}>
              Bounded in-memory summaries. Coding entries expose route, locality, approval state, and IDs; select one for compact trace detail.
            </div>
            {recentTraces.slice(0, 12).map((trace) => (
              <button
                key={trace.request_id}
                type="button"
                onClick={() => {
                  setRequestIdInput(trace.request_id);
                  void loadTrace(trace.request_id);
                }}
                style={{
                  display: "grid",
                  gap: "0.2rem",
                  textAlign: "left",
                  padding: "0.65rem 0.72rem",
                  borderRadius: "12px",
                  border: `1px solid ${palette.lineSilver}`,
                  background: "rgba(18, 25, 37, 0.7)",
                  color: palette.silver,
                  cursor: "pointer"
                }}
              >
                <strong style={{ overflowWrap: "anywhere" }}>{trace.request_id}</strong>
                <span style={{ color: palette.silverMuted }}>{humanize(trace.selected_mode)} · {humanize(trace.route_used)} · {humanize(trace.request_status)} · approval {humanize(trace.approval_state)}</span>
              </button>
            ))}
            {!recentTraces.length ? <div style={{ color: palette.silverMuted }}>{recentLoadError ?? "No retained request traces are currently available."}</div> : null}
          </section>
          <StatusPanel
            title="Request summary"
            badge="partial"
            tone="partial"
            detail="The backend has a compact request-summary route, but this first page uses request trace only until the frontend summary helper is deliberately wired."
          />
          <section style={{ display: "grid", gap: "0.55rem", padding: "1rem", borderRadius: "18px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43, 31, 21, 0.24)" }}>
            <div style={{ color: palette.sandstone, fontWeight: 700 }}>Durable Memory Fabric outcomes</div>
            <div style={{ color: palette.silverMuted }}>Sanitized mutation receipts are durable and account-scoped. Content and keys never appear here.</div>
            {memoryReceipts.slice(0, 8).map((receipt) => (
              <div key={String(receipt.mutation_id)} style={{ padding: "0.58rem", borderRadius: "10px", border: `1px solid ${palette.lineSilver}`, color: palette.silverMuted }}>
                <strong style={{ color: palette.silver }}>{humanize(String(receipt.action ?? "memory mutation"))}</strong>
                {receipt.request_id ? ` · request ${String(receipt.request_id)}` : " · direct operator action"}
                {receipt.completion_status ? ` · ${humanize(String(receipt.completion_status))}` : ""}
              </div>
            ))}
            {!memoryReceipts.length ? <div style={{ color: palette.silverMuted }}>No memory mutation receipts are available yet.</div> : null}
          </section>
          <section style={{ display: "grid", gap: "0.55rem", padding: "1rem", borderRadius: "18px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43, 31, 21, 0.24)" }}>
            <div style={{ color: palette.sandstone, fontWeight: 700 }}>Governed memory maintenance</div>
            <div style={{ color: palette.silverMuted }}>Account-owned consolidation, backup, restore support, graph, integrity, tier, and homeostasis work is visible here without exposing memory content.</div>
            {memoryJobs.slice(0, 12).map((job) => (
              <div key={String(job.job_id)} style={{ padding: "0.58rem", borderRadius: "10px", border: `1px solid ${palette.lineSilver}`, color: palette.silverMuted }}>
                <strong style={{ color: palette.silver }}>{humanize(String(job.job_kind ?? "memory job"))}</strong>
                {` · ${humanize(String(job.state ?? "unknown"))}`}
                {job.result_code ? ` · ${humanize(String(job.result_code))}` : ""}
              </div>
            ))}
            {!memoryJobs.length ? <div style={{ color: palette.silverMuted }}>No owned memory-maintenance jobs are recorded.</div> : null}
          </section>
          <section style={{ display: "grid", gap: "0.55rem", padding: "1rem", borderRadius: "18px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43, 31, 21, 0.24)" }}>
            <div style={{ color: palette.sandstone, fontWeight: 700 }}>Durable cognition receipts</div>
            <div style={{ color: palette.silverMuted }}>Content-free account-scoped receipts show what was considered, admitted, excluded, budgeted, and versioned across restart.</div>
            {contextReceipts.slice(0, 8).map((receipt) => (
              <div key={String(receipt.receipt_id)} style={{ padding: "0.58rem", borderRadius: "10px", border: `1px solid ${palette.lineSilver}`, color: palette.silverMuted }}>
                <strong style={{ color: palette.silver }}>{String(receipt.request_id ?? "Request")}</strong>
                {` · ${String(receipt.reasoning_gear ?? "unknown gear")} · admitted ${Array.isArray(receipt.admitted) ? receipt.admitted.length : 0} · excluded ${Array.isArray(receipt.excluded) ? receipt.excluded.length : 0}`}
                {receipt.governor ? ` · autonomy ${String(receipt.governor.effective_autonomy_level ?? "unknown")} · verification ${humanize(String(receipt.governor.verification_depth ?? "unknown"))}` : ""}
                {receipt.compute ? ` · device ${String(receipt.compute.selected_device ?? "unknown")} · ${humanize(String(receipt.compute.decision ?? "unknown"))}` : ""}
              </div>
            ))}
            {!contextReceipts.length ? <div style={{ color: palette.silverMuted }}>No durable cognition receipts are available yet.</div> : null}
          </section>
          <section style={{ display: "grid", gap: "0.55rem", padding: "1rem", borderRadius: "18px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43, 31, 21, 0.24)" }}>
            <div style={{ color: palette.sandstone, fontWeight: 700 }}>Pending research egress</div>
            <div style={{ color: palette.silverMuted }}>Only sensitive public queries appear here. Sealed egress is denied before approval exists.</div>
            {researchApprovals.map((approval) => (
              <div key={String(approval.approval_id)} style={{ display: "grid", gap: "0.4rem", padding: "0.58rem", borderRadius: "10px", border: `1px solid ${palette.lineSilver}`, color: palette.silverMuted }}>
                <strong style={{ color: palette.silver }}>{humanize(String(approval.operation ?? "research egress"))}</strong>
                <span>{humanize(String(approval.destination_class ?? "public search"))} · expires {String(approval.expires_at ?? "soon")}</span>
                <div style={{ display: "flex", gap: "0.4rem" }}>
                  <button type="button" onClick={() => void resolveResearchApproval(String(approval.approval_id), true)}>Approve and run once</button>
                  <button type="button" onClick={() => void resolveResearchApproval(String(approval.approval_id), false)}>Deny</button>
                </div>
              </div>
            ))}
            {!researchApprovals.length ? <div style={{ color: palette.silverMuted }}>No sensitive research approvals are pending.</div> : null}
            {requestActionNotice ? <div style={{ color: palette.teal }}>{requestActionNotice}</div> : null}
          </section>
          <StatusPanel
            title="Tool ledger"
            badge={snapshot?.tools_used_count ? "partial" : "planned"}
            tone={snapshot?.tools_used_count ? "partial" : "planned"}
            detail={`Available: ${formatCount(snapshot?.tools_available_count)}. Used: ${formatCount(snapshot?.tools_used_count)}. Used tools: ${toolSummaryPreview(snapshot?.tools_used)}.`}
          />
          <StatusPanel
            title="Files / artifacts"
            badge={
              snapshot?.files_attached_count || snapshot?.artifact_count
                ? "partial"
                : "planned"
            }
            tone={
              snapshot?.files_attached_count || snapshot?.artifact_count
                ? "partial"
                : "planned"
            }
            detail={`Files attached: ${formatCount(snapshot?.files_attached_count)}. Artifacts: ${formatCount(snapshot?.artifact_count)}. Artifact summaries: ${artifactSummaryPreview(snapshot?.artifacts)}.`}
          />
          <StatusPanel
            title="Coder ledger"
            badge={
              snapshot?.repo_context_status || snapshot?.patch_plan_status
                ? "partial"
                : "planned"
            }
            tone={
              snapshot?.repo_context_status || snapshot?.patch_plan_status
                ? "partial"
                : "planned"
            }
            detail={`Repo context: ${humanize(snapshot?.repo_context_status)} (${formatCount(snapshot?.repo_context_file_count)} files). Patch plan: ${humanize(snapshot?.patch_plan_status)} (${formatCount(snapshot?.patch_plan_file_count)} files). Mutation: ${formatBoolean(snapshot?.mutated_files)}. Shell: ${formatBoolean(snapshot?.shell_used)}. Git mutation: ${formatBoolean(snapshot?.git_mutation_used)}. External worker: ${formatBoolean(snapshot?.external_worker_used)}.`}
          />
          <StatusPanel
            title="Evidence packets"
            badge={snapshot?.research_status ? "partial" : "planned"}
            tone={snapshot?.research_status ? "partial" : "planned"}
            detail={
              snapshot?.research_status
                ? `Worker ${humanize(snapshot.research_worker_name)} recorded ${snapshot.evidence_packet_count ?? 0} evidence packets. Boundary: ${researchBoundaryValue(snapshot)}. Private context outward: ${formatBoolean(snapshot.private_context_sent)}. Page fetch: ${formatBoolean(snapshot.page_fetch_used)}.`
                : "No bounded research evidence is loaded for the current trace. Evidence must not be invented."
            }
          />
        </div>

        <div
          className="elysia-stacked-pane"
          style={{
            display: "grid",
            gap: "1rem",
            minHeight: 0,
            overflowY: "auto",
            paddingRight: "0.1rem"
          }}
        >
          <SnapshotPanel snapshot={snapshot} />
          <TimelinePanel entries={traceEntries} />
        </div>
      </div>

      <section
        style={{
          padding: "1rem",
          borderRadius: "18px",
          border: `1px dashed ${palette.lineBronze}`,
          background: "rgba(11, 14, 18, 0.42)",
          color: palette.silverMuted,
          lineHeight: 1.58
        }}
      >
        <strong style={{ color: palette.sandstone }}>Operator boundary:</strong>{" "}
        this room intentionally does not expose raw logs, raw journals, general
        replay controls, deletion controls, or autonomous execution controls.
        It does expose exact pending research-egress decisions because those
        are real governed user actions, not diagnostics.
        {!startupReady &&
          " Startup truth is not ready, so request inspection may be incomplete."}
      </section>
    </div>
  );
}

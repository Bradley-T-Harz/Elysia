import type { CSSProperties } from "react";
import type { ArtifactSummaryData } from "./api/bridgeClient";

export type ArtifactCardProps = {
  artifact: ArtifactSummaryData;
  compact?: boolean;
};

const palette = {
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  panel: "rgba(18, 25, 37, 0.92)",
  panelInset: "rgba(11, 14, 18, 0.64)",
  warning: "rgba(184, 162, 123, 0.16)",
  error: "rgba(139, 78, 47, 0.20)"
} as const;

function safeString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function safeNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function humanize(value: string | null | undefined): string {
  const text = safeString(value);

  if (!text) {
    return "Not surfaced";
  }

  return text
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatCount(value: number | null): string | null {
  if (value === null) {
    return null;
  }

  return String(Math.trunc(value)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function formatRowsColumns(
  rowCount: number | null,
  columnCount: number | null
): string {
  const rows = formatCount(rowCount);
  const columns = formatCount(columnCount);

  if (rows && columns) {
    return `${rows} rows · ${columns} columns`;
  }

  if (rows) {
    return `${rows} rows · columns not surfaced`;
  }

  if (columns) {
    return `rows not surfaced · ${columns} columns`;
  }

  return "Row/column count not surfaced";
}

function compactList(values: string[], limit = 3): string[] {
  const cleanValues = values
    .map((value) => safeString(value))
    .filter((value): value is string => Boolean(value));

  if (cleanValues.length <= limit) {
    return cleanValues;
  }

  return [
    ...cleanValues.slice(0, limit),
    `${cleanValues.length - limit} more`
  ];
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry) => safeString(entry))
    .filter((entry): entry is string => Boolean(entry));
}

function DetailRow({
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
        gridTemplateColumns: "minmax(88px, 0.42fr) minmax(0, 1fr)",
        gap: "0.65rem",
        alignItems: "start",
        padding: "0.42rem 0",
        borderTop: `1px solid ${palette.lineSilver}`
      }}
    >
      <div
        style={{
          color: palette.sandstone,
          fontSize: "0.74rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase"
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: palette.silver,
          minWidth: 0,
          overflowWrap: "anywhere",
          lineHeight: 1.45
        }}
      >
        {value}
      </div>
    </div>
  );
}

function NoticeList({
  title,
  items,
  tone
}: {
  title: string;
  items: string[];
  tone: "warning" | "error";
}) {
  if (items.length === 0) {
    return null;
  }

  const background = tone === "error" ? palette.error : palette.warning;
  const border =
    tone === "error"
      ? "rgba(139, 78, 47, 0.36)"
      : "rgba(184, 162, 123, 0.30)";

  return (
    <div
      style={{
        marginTop: "0.65rem",
        padding: "0.7rem 0.8rem",
        borderRadius: "14px",
        border: `1px solid ${border}`,
        background,
        color: palette.silverMuted,
        lineHeight: 1.5
      }}
    >
      <div
        style={{
          color: tone === "error" ? palette.sandstone : palette.teal,
          fontSize: "0.74rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginBottom: "0.35rem"
        }}
      >
        {title}
      </div>
      <ul
        style={{
          margin: 0,
          paddingLeft: "1.1rem"
        }}
      >
        {compactList(items, 4).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ArtifactCard({
  artifact,
  compact = false
}: ArtifactCardProps) {
  const artifactId = safeString(artifact.artifact_id) ?? "artifact_unknown";
  const kind = safeString(artifact.kind) ?? "data_summary";
  const title =
    safeString(artifact.title) ??
    safeString(artifact.summary) ??
    "Data summary artifact";
  const summary =
    safeString(artifact.summary) ??
    "Saved local artifact summary.";
  const sourceFileName = safeString(artifact.source_file_name);
  const sourceFileId = safeString(artifact.source_file_id);
  const sourceFileKind = safeString(artifact.source_file_kind);
  const sourceLabel = sourceFileName ?? sourceFileId ?? "Source not surfaced";
  const rowCount = safeNumber(artifact.row_count);
  const columnCount = safeNumber(artifact.column_count);
  const isPlotArtifact = kind === "plot_image";
  const isMediaArtifact = ["transcript", "speech_audio", "generated_image", "generated_video"].includes(kind);
  const plotKind = safeString(artifact.plot_kind);
  const metric = safeString(artifact.metric);
  const modelId = safeString(artifact.model_id);
  const mimeType = safeString(artifact.mime_type);
  const outputHash = safeString(artifact.output_sha256);
  const outputBytes = safeNumber(artifact.output_bytes);
  const syntheticMedia = artifact.synthetic_media === true;
  const locality = safeString(artifact.locality) ?? "local";
  const memoryPosture = safeString(artifact.memory_posture) ?? "not_memory";
  const producerToolKind =
    safeString(artifact.producer_tool_kind) ??
    (isPlotArtifact ? "plot_artifact_builder" : "data_executor");
  const producerOperation =
    safeString(artifact.producer_operation) ??
    (isPlotArtifact ? "build_numeric_summary_bar_svg" : "summarize_csv");
  const boundaryNote = isMediaArtifact
    ? `Governed local worker artifact. ${syntheticMedia ? "Synthetic media is explicitly labeled." : "Machine-generated transcript is not source-of-truth."} Raw text, prompts, transcripts, and media bytes are excluded from central trace.`
    : isPlotArtifact
    ? "Local generated plot preview only. Not memory. No notebook, arbitrary Python, shell, web, source-file mutation, or local-path fetch."
    : "Local generated result only. Not memory. No notebook, arbitrary Python, shell, web, or source-file mutation.";
  const warnings = asStringArray(artifact.warnings);
  const errors = asStringArray(artifact.errors);

  const cardStyle: CSSProperties = {
    padding: compact ? "0.8rem 0.85rem" : "0.95rem 1rem",
    borderRadius: "18px",
    border: `1px solid ${errors.length > 0 ? "rgba(139, 78, 47, 0.42)" : palette.lineTeal}`,
    background:
      "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.84) 100%)",
    boxShadow:
      "inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 24px rgba(0,0,0,0.16)",
    color: palette.silver,
    minWidth: 0
  };

  return (
    <article
      aria-label={`${humanize(kind)} artifact`}
      style={cardStyle}
      data-artifact-id={artifactId}
      data-artifact-kind={kind}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.75rem",
          alignItems: "flex-start",
          flexWrap: "wrap"
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              color: palette.sandstone,
              fontSize: "0.72rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              marginBottom: "0.32rem"
            }}
          >
            {humanize(kind)} Artifact
          </div>
          <h3
            style={{
              margin: 0,
              color: palette.silver,
              fontSize: compact ? "0.98rem" : "1.08rem",
              lineHeight: 1.25,
              overflowWrap: "anywhere"
            }}
          >
            {title}
          </h3>
        </div>

        <div
          style={{
            display: "flex",
            gap: "0.35rem",
            flexWrap: "wrap",
            justifyContent: "flex-end"
          }}
        >
          <span
            style={{
              padding: "0.28rem 0.48rem",
              borderRadius: "999px",
              border: `1px solid ${palette.lineTeal}`,
              color: palette.teal,
              background: "rgba(16, 41, 43, 0.44)",
              fontSize: "0.7rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase"
            }}
          >
            {humanize(locality)}
          </span>
          <span
            style={{
              padding: "0.28rem 0.48rem",
              borderRadius: "999px",
              border: `1px solid ${palette.lineBronze}`,
              color: palette.sandstone,
              background: "rgba(43, 31, 21, 0.38)",
              fontSize: "0.7rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase"
            }}
          >
            {humanize(memoryPosture)}
          </span>
        </div>
      </div>

      {!compact && (
        <p
          style={{
            margin: "0.7rem 0 0",
            color: palette.silverMuted,
            lineHeight: 1.55,
            overflowWrap: "anywhere"
          }}
        >
          {summary}
        </p>
      )}

      <div
        style={{
          marginTop: "0.8rem",
          padding: "0.15rem 0"
        }}
      >
        <DetailRow label="Source" value={sourceLabel} />
        <DetailRow label="Kind" value={humanize(kind)} />
        {isPlotArtifact && plotKind && (
          <DetailRow label="Plot" value={humanize(plotKind)} />
        )}
        {isPlotArtifact && metric && (
          <DetailRow label="Metric" value={humanize(metric)} />
        )}
        {sourceFileKind && (
          <DetailRow label="Source type" value={humanize(sourceFileKind)} />
        )}
        {!isMediaArtifact && (
          <DetailRow
            label="Rows/columns"
            value={formatRowsColumns(rowCount, columnCount)}
          />
        )}
        {isMediaArtifact && modelId && <DetailRow label="Model" value={modelId} />}
        {isMediaArtifact && mimeType && <DetailRow label="Format" value={mimeType} />}
        {isMediaArtifact && outputHash && <DetailRow label="Output hash" value={outputHash} />}
        {isMediaArtifact && outputBytes !== null && <DetailRow label="Output bytes" value={String(outputBytes)} />}
        <DetailRow
          label="Produced by"
          value={`${humanize(producerToolKind)} · ${humanize(producerOperation)}`}
        />
      </div>

      <div
        style={{
          marginTop: "0.75rem",
          padding: "0.72rem 0.8rem",
          borderRadius: "14px",
          border: `1px solid ${palette.lineSilver}`,
          background: palette.panelInset,
          color: palette.silverMuted,
          lineHeight: 1.5
        }}
      >
{boundaryNote}
      </div>

      <NoticeList title="Warnings" items={warnings} tone="warning" />
      <NoticeList title="Errors" items={errors} tone="error" />
    </article>
  );
}

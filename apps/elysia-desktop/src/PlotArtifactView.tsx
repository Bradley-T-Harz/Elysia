import type { CSSProperties } from "react";
import type { ArtifactSummaryData } from "./api/bridgeClient";

export type PlotArtifactViewProps = {
  artifact?: ArtifactSummaryData | null;
  svgText?: string | null;
  title?: string | null;
  summary?: string | null;
  compact?: boolean;
};

const MAX_INLINE_SVG_LENGTH = 240_000;

const palette = {
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
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

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry) => safeString(entry))
    .filter((entry): entry is string => Boolean(entry));
}

export function isSafeSvgPreview(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }

  const trimmed = value.trim();
  const lowered = trimmed.toLowerCase();

  if (!trimmed.startsWith("<svg")) {
    return false;
  }

  if (trimmed.length > MAX_INLINE_SVG_LENGTH) {
    return false;
  }

  if (
    lowered.includes("<script") ||
    lowered.includes("foreignobject") ||
    lowered.includes("javascript:") ||
    /\son[a-z]+\s*=/.test(lowered) ||
    /\b(?:href|src)\s*=\s*["']https?:/i.test(trimmed) ||
    /url\(\s*https?:/i.test(trimmed)
  ) {
    return false;
  }

  return true;
}

export function svgToDataUri(svgText: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgText)}`;
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
        gridTemplateColumns: "minmax(92px, 0.42fr) minmax(0, 1fr)",
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
        {items.slice(0, 4).map((item, index) => (
          <li key={`${item}-${index}`}>{item}</li>
        ))}
        {items.length > 4 && <li>{items.length - 4} more</li>}
      </ul>
    </div>
  );
}

export default function PlotArtifactView({
  artifact = null,
  svgText = null,
  title = null,
  summary = null,
  compact = false
}: PlotArtifactViewProps) {
  const artifactId = safeString(artifact?.artifact_id) ?? "plot_artifact_preview";
  const artifactKind = safeString(artifact?.kind) ?? "plot_image";
  const resolvedTitle =
    safeString(title) ??
    safeString(artifact?.title) ??
    "Plot artifact";
  const resolvedSummary =
    safeString(summary) ??
    safeString(artifact?.summary) ??
    "Local plot artifact preview.";
  const sourceFileName = safeString(artifact?.source_file_name);
  const sourceFileId = safeString(artifact?.source_file_id);
  const sourceLabel = sourceFileName ?? sourceFileId ?? "Source not surfaced";
  const rowCount = safeNumber(artifact?.row_count);
  const columnCount = safeNumber(artifact?.column_count);
  const locality = safeString(artifact?.locality) ?? "local";
  const memoryPosture = safeString(artifact?.memory_posture) ?? "not_memory";
  const producerToolKind =
    safeString(artifact?.producer_tool_kind) ?? "plot_artifact_builder";
  const producerOperation =
    safeString(artifact?.producer_operation) ?? "build_numeric_summary_bar_svg";
  const warnings = asStringArray(artifact?.warnings);
  const errors = asStringArray(artifact?.errors);
  const safeSvg = isSafeSvgPreview(svgText) ? svgText.trim() : null;
  const hadUnsafeSvg = Boolean(svgText && !safeSvg);

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
      aria-label={`${humanize(artifactKind)} preview`}
      style={cardStyle}
      data-artifact-id={artifactId}
      data-artifact-kind={artifactKind}
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
            {humanize(artifactKind)} Artifact
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
            {resolvedTitle}
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
          {resolvedSummary}
        </p>
      )}

      <div
        style={{
          marginTop: "0.85rem",
          borderRadius: "16px",
          border: `1px solid ${palette.lineSilver}`,
          background: palette.panelInset,
          minHeight: compact ? "160px" : "220px",
          display: "grid",
          placeItems: "center",
          overflow: "hidden"
        }}
      >
        {safeSvg ? (
          <img
            src={svgToDataUri(safeSvg)}
            alt={resolvedTitle}
            style={{
              display: "block",
              width: "100%",
              height: "auto",
              maxHeight: compact ? "220px" : "360px",
              objectFit: "contain"
            }}
          />
        ) : (
          <div
            style={{
              padding: "1rem",
              color: palette.silverMuted,
              lineHeight: 1.55,
              textAlign: "center"
            }}
          >
            <strong style={{ color: palette.silver }}>
              Plot preview is not surfaced yet.
            </strong>
            <br />
            {hadUnsafeSvg
              ? "The SVG preview was withheld because it failed safe preview checks."
              : "The artifact may be saved locally, but this view does not read local paths directly."}
          </div>
        )}
      </div>

      <div style={{ marginTop: "0.8rem", padding: "0.15rem 0" }}>
        <DetailRow label="Kind" value={humanize(artifactKind)} />
        <DetailRow label="Source" value={sourceLabel} />
        <DetailRow
          label="Rows/columns"
          value={formatRowsColumns(rowCount, columnCount)}
        />
        <DetailRow label="Locality" value={humanize(locality)} />
        <DetailRow label="Memory" value={humanize(memoryPosture)} />
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
        Display-only local artifact view. Does not fetch local paths, open
        files, mutate data, or promote content into memory.
      </div>

      <NoticeList title="Warnings" items={warnings} tone="warning" />
      <NoticeList title="Errors" items={errors} tone="error" />
    </article>
  );
}

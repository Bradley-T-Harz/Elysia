import type { ProjectSummary } from "./api/bridgeClient";

type ProjectSummaryCardProps = {
  project: ProjectSummary;
  isActive?: boolean;
  isDeleting?: boolean;
  onSelect?: (projectId: string) => void;
  onDelete?: (projectId: string) => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.28)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  glowTeal: "rgba(126, 215, 209, 0.14)",
  glowBronze: "rgba(138, 106, 60, 0.12)"
} as const;

function formatCount(value: number | null | undefined, label: string): string {
  const safeValue = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return `${safeValue} ${label}`;
}

function formatTimestamp(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric"
  });
}

export default function ProjectSummaryCard({
  project,
  isActive = false,
  isDeleting = false,
  onSelect,
  onDelete
}: ProjectSummaryCardProps) {
  const projectId = project.project_id;
  const displayName = project.name || "Untitled project";
  const status = project.status || "active";
  const body =
    project.description ||
    project.state_summary ||
    project.notes_summary ||
    "No description, notes summary, or state summary yet.";

  const createdLabel = formatTimestamp(project.created_at_utc);
  const updatedLabel = formatTimestamp(project.updated_at_utc);

  const content = (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.85rem",
          alignItems: "start"
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: "0.8rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.35rem"
            }}
          >
            {isActive ? "Active project" : "Project"}
          </div>
          <div
            style={{
              fontSize: "1rem",
              fontWeight: 600,
              lineHeight: 1.3,
              color: palette.silver,
              overflowWrap: "anywhere"
            }}
          >
            {displayName}
          </div>
        </div>

        <div
          style={{
            fontSize: "0.76rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: isActive ? palette.teal : palette.silverMuted,
            whiteSpace: "nowrap"
          }}
        >
          {status}
        </div>
      </div>

      <div
        style={{
          color: palette.silverMuted,
          lineHeight: 1.55
        }}
      >
        {body}
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.55rem"
        }}
      >
        {[
          formatCount(project.conversation_count, "conversations"),
          project.notes_summary ? "notes summary present" : "notes summary empty",
          project.state_summary ? "state summary present" : "state summary empty"
        ].map((chip) => (
          <div
            key={chip}
            style={{
              padding: "0.34rem 0.55rem",
              borderRadius: "999px",
              border: `1px solid ${isActive ? palette.lineTeal : palette.lineSilver}`,
              color: palette.silverMuted,
              fontSize: "0.76rem",
              lineHeight: 1.2
            }}
          >
            {chip}
          </div>
        ))}
      </div>

      {(createdLabel || updatedLabel) && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.85rem",
            color: palette.silverMuted,
            fontSize: "0.76rem",
            lineHeight: 1.3
          }}
        >
          {createdLabel && <div>Created {createdLabel}</div>}
          {updatedLabel && <div>Updated {updatedLabel}</div>}
        </div>
      )}
    </>
  );

  return (
    <div
      style={{
        display: "grid",
        gap: "0.7rem",
        width: "100%",
        minWidth: 0,
        alignSelf: "start",
        boxSizing: "border-box",
        textAlign: "left",
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${isActive ? palette.lineTeal : palette.lineSilver}`,
        background: isActive
          ? "linear-gradient(180deg, rgba(16, 41, 43, 0.58) 0%, rgba(18, 25, 37, 0.80) 100%)"
          : "linear-gradient(180deg, rgba(24, 33, 48, 0.52) 0%, rgba(18, 25, 37, 0.66) 100%)",
        boxShadow: isActive ? `0 0 20px ${palette.glowTeal}` : "none"
      }}
    >
      {onDelete && (
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end"
          }}
        >
          <button
            type="button"
            disabled={isDeleting}
            onClick={() => onDelete(projectId)}
            style={{
              padding: "0.46rem 0.7rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineBronze}`,
              background: "rgba(42, 25, 21, 0.40)",
              color: palette.silver,
              cursor: isDeleting ? "progress" : "pointer",
              opacity: isDeleting ? 0.82 : 1,
              fontSize: "0.76rem",
              fontWeight: 600
            }}
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      )}

      {onSelect ? (
        <button
          type="button"
          onClick={() => onSelect(projectId)}
          style={{
            display: "grid",
            gap: "0.7rem",
            width: "100%",
            minWidth: 0,
            boxSizing: "border-box",
            textAlign: "left",
            background: "transparent",
            border: "none",
            padding: 0,
            cursor: "pointer"
          }}
        >
          {content}
        </button>
      ) : (
        <div
          style={{
            display: "grid",
            gap: "0.7rem"
          }}
        >
          {content}
        </div>
      )}
    </div>
  );
}

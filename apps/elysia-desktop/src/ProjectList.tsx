import type { ProjectSummary } from "./api/bridgeClient";
import ProjectSummaryCard from "./ProjectSummaryCard";

type ProjectListProps = {
  projects: ProjectSummary[];
  activeProjectId?: string | null;
  deletingProjectId?: string | null;
  isLoading?: boolean;
  errorMessage?: string | null;
  startupReady: boolean;
  onSelectProject?: (projectId: string) => void;
  onCreateProject?: () => void;
  onDeleteProject?: (projectId: string) => void;
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
  glowBronze: "rgba(138, 106, 60, 0.12)",
  glowTeal: "rgba(126, 215, 209, 0.14)"
} as const;

export default function ProjectList({
  projects,
  activeProjectId = null,
  deletingProjectId = null,
  isLoading = false,
  errorMessage = null,
  startupReady,
  onSelectProject,
  onCreateProject,
  onDeleteProject
}: ProjectListProps) {
  if (isLoading) {
    return (
      <div
        style={{
          display: "grid",
          gap: "0.85rem",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.58) 0%, rgba(18, 25, 37, 0.72) 100%)"
        }}
      >
        <div
          style={{
            fontSize: "0.8rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.sandstone
          }}
        >
          Projects
        </div>
        <div style={{ color: palette.silverMuted, lineHeight: 1.6 }}>
          Loading project continuity from the local bridge.
        </div>
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div
        style={{
          display: "grid",
          gap: "0.85rem",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineBronze}`,
          background:
            "linear-gradient(180deg, rgba(42, 25, 21, 0.50) 0%, rgba(18, 25, 37, 0.74) 100%)"
        }}
      >
        <div
          style={{
            fontSize: "0.8rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: palette.sandstone
          }}
        >
          Projects unavailable
        </div>
        <div style={{ color: palette.silverMuted, lineHeight: 1.6 }}>
          {errorMessage}
        </div>
        {onCreateProject && (
          <button
            type="button"
            onClick={onCreateProject}
            style={{
              justifySelf: "start",
              padding: "0.68rem 0.92rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineBronze}`,
              background:
                "linear-gradient(180deg, rgba(43, 31, 21, 0.56) 0%, rgba(18, 25, 37, 0.72) 100%)",
              color: palette.silver,
              boxShadow: `0 0 18px ${palette.glowBronze}`,
              cursor: "pointer",
              fontSize: "0.84rem",
              fontWeight: 600
            }}
          >
            + Create project
          </button>
        )}
      </div>
    );
  }

  if (!projects.length) {
    return (
      <div
        style={{
          display: "grid",
          gap: "0.95rem",
          placeItems: "center",
          textAlign: "center",
          padding: "1.4rem",
          borderRadius: "22px",
          border: `1px dashed ${startupReady ? palette.lineTeal : palette.lineBronze}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.66) 0%, rgba(11, 14, 18, 0.78) 100%)"
        }}
      >
        <div
          aria-hidden="true"
          style={{
            width: "3.8rem",
            height: "3.8rem",
            borderRadius: "999px",
            border: `1px solid ${palette.lineBronze}`,
            background:
              "radial-gradient(circle at 50% 40%, rgba(126, 215, 209, 0.18), rgba(18, 25, 37, 0.94))",
            boxShadow: `0 0 22px ${palette.glowTeal}`
          }}
        />
        <div>
          <div
            style={{
              fontSize: "0.8rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.4rem"
            }}
          >
            Empty project list
          </div>
          <div
            style={{
              fontSize: "1.12rem",
              color: palette.silver,
              lineHeight: 1.3,
              marginBottom: "0.45rem"
            }}
          >
            No projects are visible yet.
          </div>
          <div
            style={{
              color: palette.silverMuted,
              lineHeight: 1.6,
              maxWidth: "54ch"
            }}
          >
            This is correct for Phase 1. Projects should appear only when you create
            them, not because the shell invents demo clutter.
          </div>
        </div>
        {onCreateProject && (
          <button
            type="button"
            onClick={onCreateProject}
            style={{
              padding: "0.72rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineBronze}`,
              background:
                "linear-gradient(180deg, rgba(43, 31, 21, 0.56) 0%, rgba(18, 25, 37, 0.72) 100%)",
              color: palette.silver,
              boxShadow: `0 0 18px ${palette.glowBronze}`,
              cursor: "pointer",
              fontSize: "0.84rem",
              fontWeight: 600
            }}
          >
            + Create project
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gap: "0.85rem",
        minHeight: 0,
        alignContent: "start",
        alignItems: "start",
        gridAutoRows: "max-content"
      }}
    >
      {projects.map((project) => (
        <ProjectSummaryCard
          key={project.project_id}
          project={project}
          isActive={activeProjectId === project.project_id}
          isDeleting={deletingProjectId === project.project_id}
          onSelect={onSelectProject}
          onDelete={onDeleteProject}
        />
      ))}
    </div>
  );
}

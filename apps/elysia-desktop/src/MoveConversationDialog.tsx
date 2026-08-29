import { useEffect, useState } from "react";
import type { ProjectSummary } from "./api/bridgeClient";

export type MoveProjectListState = "loading" | "ready" | "error";

type MoveConversationDialogProps = {
  open: boolean;
  currentProjectId: string;
  projects: ProjectSummary[];
  projectListState: MoveProjectListState;
  projectListError?: string | null;
  moveError?: string | null;
  busy?: boolean;
  onClose: () => void;
  onSubmit: (nextProjectId: string) => void;
  onRetryProjects: () => void;
  onOpenProjects?: () => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  lineTeal: "rgba(126, 215, 209, 0.24)"
} as const;

export default function MoveConversationDialog({
  open,
  currentProjectId,
  projects,
  projectListState,
  projectListError = null,
  moveError = null,
  busy = false,
  onClose,
  onSubmit,
  onRetryProjects,
  onOpenProjects
}: MoveConversationDialogProps) {
  const [selectedProjectId, setSelectedProjectId] = useState(currentProjectId);

  useEffect(() => {
    if (open) {
      const normalizedCurrentProjectId = currentProjectId.trim();
      const currentProjectIsAvailable = projects.some(
        (project) => project.project_id === normalizedCurrentProjectId
      );

      setSelectedProjectId(
        currentProjectIsAvailable
          ? normalizedCurrentProjectId
          : projects[0]?.project_id ?? ""
      );
    }
  }, [open, currentProjectId, projects]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) {
        onClose();
      }
    }

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [busy, onClose, open]);

  if (!open) {
    return null;
  }

  const trimmedProjectId = selectedProjectId.trim();
  const currentTrimmed = currentProjectId.trim();
  const canSubmit =
    !busy &&
    projectListState === "ready" &&
    projects.some((project) => project.project_id === trimmedProjectId) &&
    trimmedProjectId !== currentTrimmed;

  function handleSubmit() {
    if (!canSubmit) {
      return;
    }

    onSubmit(trimmedProjectId);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Move conversation to project"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 120,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.25rem",
        background: "rgba(5, 8, 12, 0.58)",
        backdropFilter: "blur(4px)"
      }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) {
          onClose();
        }
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "30rem",
          display: "grid",
          gap: "1rem",
          padding: "1.15rem",
          borderRadius: "22px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.96) 0%, rgba(18, 25, 37, 0.98) 100%)",
          boxShadow: "0 18px 42px rgba(0,0,0,0.32)"
        }}
      >
        <div>
          <div
            style={{
              fontSize: "0.76rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.35rem"
            }}
          >
            Move to project
          </div>
          <h2
            style={{
              margin: 0,
              fontSize: "1.35rem",
              lineHeight: 1.15,
              color: palette.silver
            }}
          >
            Move conversation
          </h2>
          <div
            style={{
              marginTop: "0.45rem",
              color: palette.silverMuted,
              lineHeight: 1.55
            }}
          >
            Choose one of your existing local projects. Elysia will keep the conversation
            intact and update only its project linkage.
          </div>
        </div>

        {projectListState === "loading" ? (
          <div
            style={{
              padding: "0.9rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.42)",
              color: palette.silverMuted,
              lineHeight: 1.5
            }}
          >
            Loading local projects…
          </div>
        ) : projectListState === "error" ? (
          <div
            role="alert"
            style={{
              display: "grid",
              gap: "0.75rem",
              padding: "0.9rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineBronze}`,
              background: "rgba(72, 31, 24, 0.28)",
              color: palette.silverMuted,
              lineHeight: 1.5
            }}
          >
            <span>{projectListError ?? "Projects could not be loaded from the local bridge."}</span>
            <button
              type="button"
              onClick={onRetryProjects}
              disabled={busy}
              style={{
                justifySelf: "start",
                padding: "0.55rem 0.75rem",
                borderRadius: "12px",
                border: `1px solid ${palette.lineBronze}`,
                background: "rgba(18, 25, 37, 0.72)",
                color: palette.sandstone,
                cursor: busy ? "default" : "pointer"
              }}
            >
              Try again
            </button>
          </div>
        ) : projects.length === 0 ? (
          <div
            style={{
              display: "grid",
              gap: "0.75rem",
              padding: "0.9rem",
              borderRadius: "14px",
              border: `1px dashed ${palette.lineBronze}`,
              background: "rgba(11, 14, 18, 0.42)",
              color: palette.silverMuted,
              lineHeight: 1.5
            }}
          >
            <span>No projects are available yet. Create one in the Projects room, then return here to move this conversation.</span>
            {onOpenProjects && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenProjects();
                }}
                disabled={busy}
                style={{
                  justifySelf: "start",
                  padding: "0.55rem 0.75rem",
                  borderRadius: "12px",
                  border: `1px solid ${palette.lineTeal}`,
                  background: "rgba(16, 41, 43, 0.58)",
                  color: palette.teal,
                  cursor: busy ? "default" : "pointer"
                }}
              >
                Create a project
              </button>
            )}
          </div>
        ) : (
          <div style={{ display: "grid", gap: "0.5rem" }}>
            <label
              htmlFor="move-conversation-project-select"
              style={{
                fontSize: "0.82rem",
                color: palette.silverMuted
              }}
            >
              Project
            </label>

            <select
              id="move-conversation-project-select"
              value={selectedProjectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
              disabled={busy}
              autoFocus
              style={{
                width: "100%",
                padding: "0.85rem 0.95rem",
                borderRadius: "14px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(11, 14, 18, 0.88)",
                color: palette.silver,
                boxSizing: "border-box"
              }}
            >
              {projects.map((project) => {
                const projectName = project.name?.trim() || project.project_id;
                const current = project.project_id === currentTrimmed;

                return (
                  <option key={project.project_id} value={project.project_id}>
                    {projectName}{current ? " (current)" : ""}
                  </option>
                );
              })}
            </select>

            <div style={{ color: palette.silverMuted, fontSize: "0.76rem" }}>
              Local project ID: {selectedProjectId}
            </div>
          </div>
        )}

        {moveError && (
          <div
            role="alert"
            style={{
              padding: "0.8rem 0.9rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineBronze}`,
              background: "rgba(72, 31, 24, 0.28)",
              color: "#E7B4A4",
              lineHeight: 1.5
            }}
          >
            {moveError}
          </div>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.7rem",
            flexWrap: "wrap"
          }}
        >
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            style={{
              padding: "0.7rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${palette.lineBronze}`,
              background:
                "linear-gradient(180deg, rgba(43, 31, 21, 0.46) 0%, rgba(18, 25, 37, 0.70) 100%)",
              color: palette.silverMuted,
              cursor: busy ? "default" : "pointer",
              opacity: busy ? 0.72 : 1
            }}
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              padding: "0.7rem 0.95rem",
              borderRadius: "14px",
              border: `1px solid ${canSubmit ? palette.lineTeal : palette.lineBronze}`,
              background: canSubmit
                ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.80) 100%)"
                : "linear-gradient(180deg, rgba(43, 31, 21, 0.46) 0%, rgba(18, 25, 37, 0.70) 100%)",
              color: canSubmit ? palette.teal : palette.silverMuted,
              cursor: canSubmit ? "pointer" : "default",
              opacity: canSubmit ? 1 : 0.72
            }}
          >
            {busy ? "Moving…" : "Move"}
          </button>
        </div>
      </div>
    </div>
  );
}

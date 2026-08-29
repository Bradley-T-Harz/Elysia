import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createProject,
  deleteProject,
  fetchProjectList,
  type BridgeEnvelope,
  type ProjectCreateRequest,
  type ProjectCreateEnvelope,
  type ProjectDeleteEnvelope,
  type ProjectListEnvelope,
  type ProjectSummary
} from "./api/bridgeClient";
import CreateProjectDialog from "./CreateProjectDialog";
import ProjectList from "./ProjectList";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";

type ProjectsPageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
  onOpenProject?: (projectId: string) => void;
};

type LoadProjectsOptions = {
  showLoading?: boolean;
  preferredActiveProjectId?: string | null;
};

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
  lineTeal: "rgba(126, 215, 209, 0.24)",
  glowTeal: "rgba(126, 215, 209, 0.14)",
  glowBronze: "rgba(138, 106, 60, 0.12)"
} as const;

function isEnvelopeFailureStatus(status?: string): boolean {
  return (
    status === "error" ||
    status === "blocked" ||
    status === "unavailable"
  );
}

function getEnvelopeMessage(
  envelope:
    | Partial<BridgeEnvelope<Record<string, unknown>>>
    | undefined,
  fallback: string
): string {
  const errors = envelope?.errors;
  if (Array.isArray(errors)) {
    const first = errors.find((value) => typeof value === "string" && value.trim());
    if (first) {
      return first;
    }
  }

  if (typeof envelope?.message === "string" && envelope.message.trim()) {
    return envelope.message.trim();
  }

  return fallback;
}

export default function ProjectsPage({
  startupReady,
  onRightDrawerSectionsChange,
  onOpenProject
}: ProjectsPageProps) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

  const [isProjectListLoading, setIsProjectListLoading] = useState(true);
  const [projectListError, setProjectListError] = useState<string | null>(null);

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isCreatingProject, setIsCreatingProject] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [createProjectError, setCreateProjectError] = useState<string | null>(null);
  const [createNotice, setCreateNotice] = useState<string | null>(null);

  const activeProject = useMemo<ProjectSummary | null>(() => {
    return (
      projects.find((project) => project.project_id === activeProjectId) ?? null
    );
  }, [projects, activeProjectId]);

  const loadProjects = useCallback(
    async ({
      showLoading = true,
      preferredActiveProjectId = null
    }: LoadProjectsOptions = {}) => {
      if (showLoading) {
        setIsProjectListLoading(true);
      }

      setProjectListError(null);

      const result = await fetchProjectList();
      const payload: ProjectListEnvelope | undefined = result.payload;
      const payloadStatus = payload?.status;

      if (!result.ok || isEnvelopeFailureStatus(payloadStatus)) {
        setProjectListError(
          getEnvelopeMessage(
            payload,
            "Projects could not be loaded from the local bridge."
          )
        );

        if (showLoading) {
          setProjects([]);
          setActiveProjectId(null);
        }

        setIsProjectListLoading(false);
        return;
      }

      const nextProjects = Array.isArray(payload?.data?.projects)
        ? payload.data.projects
        : [];

      const returnedActiveProjectId =
        typeof payload?.data?.active_project_id === "string"
          ? payload.data.active_project_id
          : null;

      setProjects(nextProjects);
      setActiveProjectId((current) => {
        const candidate =
          returnedActiveProjectId ??
          preferredActiveProjectId ??
          current;

        if (candidate && nextProjects.some((project) => project.project_id === candidate)) {
          return candidate;
        }

        if (nextProjects.length === 1) {
          return nextProjects[0].project_id;
        }

        return null;
      });

      setIsProjectListLoading(false);
    },
    []
  );

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    const currentProjectSelection = activeProject
      ? activeProject.name || activeProject.project_id
      : isProjectListLoading
        ? "Loading project list"
        : "No current project selected";

    const currentProjectStatus = activeProject
      ? activeProject.status || "active"
      : projectListError
        ? "Project list unavailable"
        : projects.length > 0
          ? "Project selected locally only"
          : "Project detail room not opened yet";

    const projectMemoryValue = activeProject
      ? activeProject.name || activeProject.project_id
      : isProjectListLoading
        ? "Loading local project continuity"
        : "No active project selected yet";

    const planStep = deletingProjectId
      ? "Deleting project through the local bridge"
      : isCreatingProject
        ? "Creating project through the local bridge"
        : isProjectListLoading
        ? "Loading project list from /projects"
        : projectListError
          ? "Project bridge returned an error"
          : "Project list and create flow are live through /projects";

    const requestTraceDetail = deletingProjectId
      ? "Project delete request in progress"
      : isCreatingProject
        ? "Project create request in progress"
        : isProjectListLoading
          ? "Project list request in progress"
          : projectListError
            ? "Project bridge returned an error"
            : "Projects index is idle";

    const projectRequestActive =
      Boolean(deletingProjectId) || isCreatingProject || isProjectListLoading;

    const projectRequestTraceState: DrawerSection["state"] = projectListError
      ? "degraded"
      : projectRequestActive
        ? "live"
        : "partial";

    const projectRequestTraceLabel = projectListError
      ? "Project request degraded"
      : projectRequestActive
        ? "Project request active"
        : "No active request trace";

    return [
      {
        key: "active_context",
        title: "Active Context",
        state: "live",
        accent: "warm",
        rows: [
          { label: "Room", value: "Projects" },
          { label: "Surface", value: "Project index" },
          {
            label: "Context source",
            value: "Projects room + local bridge state"
          }
        ]
      },
      {
        key: "memory_classes",
        title: "Memory Classes",
        state: "partial",
        rows: [
          { label: "Working", value: "Idle" },
          { label: "Conversation", value: "No project-scoped thread selected" },
          { label: "Project", value: projectMemoryValue },
          { label: "Sealed private", value: "Not touched in current room state" }
        ]
      },
      {
        key: "current_project",
        title: "Current Project",
        state: activeProject ? "live" : "partial",
        rows: [
          { label: "Selection", value: currentProjectSelection },
          { label: "Status", value: currentProjectStatus },
          {
            label: "Project count",
            value: `${projects.length} visible project${projects.length === 1 ? "" : "s"}`
          }
        ]
      },
      {
        key: "files_in_use",
        title: "Files in Use",
        state: "planned",
        rows: [
          { label: "Attachments", value: "No project files in use" },
          { label: "Status", value: "Project file surfaces are not yet live" }
        ]
      },
      {
        key: "plan_preview",
        title: "Plan Preview",
        state: projectListError ? "degraded" : "partial",
        rows: [
          { label: "Current step", value: planStep },
          {
            label: "Next step",
            value: "Open project detail for continuity and linked conversation routing"
          },
          {
            label: "Action posture",
            value: "Project create, delete, selection, and detail routes are live"
          }
        ]
      },
      {
        key: "boundary_flags",
        title: "Boundary Flags",
        state: "live",
        accent: "teal",
        rows: [
          { label: "Locality", value: startupReady ? "local" : "startup pending" },
          { label: "Boundary", value: "No outward project action is active" },
          { label: "Fallback", value: "No project request fallback is surfaced" }
        ]
      },
      {
        key: "approval_needed",
        title: "Approval Needed",
        state: "inactive",
        rows: [
          { label: "Current state", value: "No approval required" },
          { label: "Blocked state", value: "No approval gate active" }
        ]
      },
      {
        key: "journal_summary",
        title: "Journal Summary",
        state: "partial",
        rows: [
          { label: "Journaling", value: "Room visible" },
          {
            label: "Idle state",
            value: deletingProjectId
              ? "Project delete request has not finished yet"
              : isCreatingProject
                ? "Project create request has not finished yet"
                : "No additional project action is in progress"
          },
          { label: "Status", value: "Compact drawer summary still maturing" }
        ]
      },
      {
        key: "request_trace",
        title: "Request Trace",
        state: projectRequestTraceState,
        rows: [
          { label: "Current trace", value: projectRequestTraceLabel },
          { label: "Detail", value: requestTraceDetail },
          {
            label: "Status",
            value: projectListError
              ? "Project route degraded"
              : projectRequestActive
                ? "Request active"
                : "No active trace"
          }
        ]
      }
    ];
  }, [
    activeProject,
    deletingProjectId,
    isCreatingProject,
    isProjectListLoading,
    projectListError,
    projects.length,
    startupReady
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);

    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  async function handleCreateProject(request: ProjectCreateRequest) {
    if (isCreatingProject) {
      return;
    }

    setCreateProjectError(null);
    setCreateNotice(null);
    setIsCreatingProject(true);

    const result = await createProject(request);
    const payload: ProjectCreateEnvelope | undefined = result.payload;
    const payloadStatus = payload?.status;

    if (!result.ok || isEnvelopeFailureStatus(payloadStatus)) {
      setCreateProjectError(
        getEnvelopeMessage(
          payload,
          `Project "${request.name}" could not be created through the local bridge.`
        )
      );
      setIsCreatingProject(false);
      return;
    }

    const createdProject =
      payload?.data?.project && typeof payload.data.project === "object"
        ? payload.data.project
        : null;

    const createdProjectName = createdProject?.name || request.name;
    const createdProjectId =
      typeof createdProject?.project_id === "string"
        ? createdProject.project_id
        : typeof payload?.data?.project_id === "string"
          ? payload.data.project_id
          : null;

    setIsCreateDialogOpen(false);
    setCreateProjectError(null);
    setCreateNotice(
      `Project "${createdProjectName}" was created locally and the project list has been refreshed.`
    );

    await loadProjects({
      showLoading: false,
      preferredActiveProjectId: createdProjectId
    });

    setIsCreatingProject(false);
  }

  async function handleDeleteProject(projectId: string) {
    const targetProject =
      projects.find((project) => project.project_id === projectId) ?? null;
    const displayName = targetProject?.name || projectId;

    const confirmed = window.confirm(
      `Delete project "${displayName}"?\n\nThis removes the local project record.`
    );

    if (!confirmed) {
      return;
    }

    setCreateNotice(null);
    setProjectListError(null);
    setDeletingProjectId(projectId);

    const result = await deleteProject(projectId);
    const payload: ProjectDeleteEnvelope | undefined = result.payload;
    const payloadStatus = payload?.status;

    if (!result.ok || isEnvelopeFailureStatus(payloadStatus)) {
      setProjectListError(
        getEnvelopeMessage(
          payload,
          `Project "${displayName}" could not be deleted through the local bridge.`
        )
      );
      setDeletingProjectId(null);
      return;
    }

    const nextActiveProjectId =
      typeof payload?.data?.active_project_id === "string"
        ? payload.data.active_project_id
        : null;

    setCreateNotice(
      `Project "${displayName}" was deleted locally and the project list has been refreshed.`
    );

    await loadProjects({
      showLoading: false,
      preferredActiveProjectId: nextActiveProjectId
    });

    setDeletingProjectId(null);
  }

  return (
    <>
      <div
        className="elysia-room-scroll-at-narrow"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          minHeight: 0,
          flex: 1
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
            Projects
          </div>
          <h1
            style={{
              margin: 0,
              fontSize: "2.15rem",
              lineHeight: 1.1
            }}
          >
            Project chambers and continuity begin here.
          </h1>
          <div
            style={{
              marginTop: "0.55rem",
              color: palette.silverMuted,
              lineHeight: 1.6,
              maxWidth: "78ch"
            }}
          >
            Create and remove local project records, open project continuity, and route
            linked conversations back into their live governed thread.
          </div>
        </div>

        <div
          style={{
            padding: "1rem 1.05rem",
            borderRadius: "18px",
            border: `1px dashed ${startupReady ? "rgba(126, 215, 209, 0.26)" : palette.lineBronze}`,
            background: "rgba(11, 14, 18, 0.42)",
            color: palette.silverMuted,
            lineHeight: 1.6
          }}
        >
          {startupReady
            ? "Startup truth is ready. Project creation, deletion, detail, and linked-conversation routing use the local bridge."
            : "Startup truth is not yet ready. The Projects room is visible, but live backend-backed project work should remain explicit and restrained."}
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "0.85rem",
            alignItems: "center",
            flexWrap: "wrap",
            padding: "1rem",
            borderRadius: "20px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.74) 100%)"
          }}
        >
          <div>
            <div
              style={{
                fontSize: "0.82rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: palette.sandstone,
                marginBottom: "0.35rem"
              }}
            >
              Project index
            </div>
            <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
              Creation and deletion operate on real local project records. Opening a
              project loads its persisted continuity and linked conversations.
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setCreateProjectError(null);
              setCreateNotice(null);
              setIsCreateDialogOpen(true);
            }}
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
              fontWeight: 600,
              whiteSpace: "nowrap"
            }}
          >
            + Create project
          </button>
        </div>

        {createNotice && (
          <div
            style={{
              padding: "0.95rem 1rem",
              borderRadius: "18px",
              border: `1px solid ${palette.lineTeal}`,
              background:
                "linear-gradient(180deg, rgba(16, 41, 43, 0.52) 0%, rgba(18, 25, 37, 0.78) 100%)",
              color: palette.silverMuted,
              lineHeight: 1.58
            }}
          >
            {createNotice}
          </div>
        )}

        <div
          style={{
            flex: 1,
            minHeight: 0,
            display: "grid"
          }}
        >
          <ProjectList
            projects={projects}
            activeProjectId={activeProjectId}
            deletingProjectId={deletingProjectId}
            isLoading={isProjectListLoading}
            errorMessage={projectListError}
            startupReady={startupReady}
            onSelectProject={(projectId) => {
              setActiveProjectId(projectId);
              setCreateNotice(null);
              onOpenProject?.(projectId);
            }}
            onCreateProject={() => {
              setCreateProjectError(null);
              setCreateNotice(null);
              setIsCreateDialogOpen(true);
            }}
            onDeleteProject={handleDeleteProject}
          />
        </div>
      </div>

      <CreateProjectDialog
        isOpen={isCreateDialogOpen}
        startupReady={startupReady}
        isSubmitting={isCreatingProject}
        errorMessage={createProjectError}
        onClose={() => {
          if (isCreatingProject) {
            return;
          }

          setCreateProjectError(null);
          setIsCreateDialogOpen(false);
        }}
        onSubmit={handleCreateProject}
      />
    </>
  );
}

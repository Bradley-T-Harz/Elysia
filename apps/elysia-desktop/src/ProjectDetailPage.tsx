import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import RoomActionMenu, { type RoomActionMenuItem } from "./RoomActionMenu";
import ProjectWorkbenchPanel, { type ProjectWorkbenchTool } from "./ProjectWorkbenchPanel";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";
import {
  fetchProjectDetail,
  fetchMemoryItems,
  selectProject,
  updateProject,
  type BridgeEnvelope,
  type ProjectDetailConversationSummary,
  type ProjectDetailEnvelope,
  type ProjectContinuitySummary,
  type ProjectContinuityItem,
  type ProjectSelectionEnvelope,
  type MemoryItemSummary,
  type ProjectSummary
} from "./api/bridgeClient";

type ProjectDetailPageProps = {
  projectId: string;
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
  project?: ProjectSummary | null;
  relatedConversations?: ProjectDetailConversationSummary[];
  notesSummary?: string | null;
  stateSummary?: string | null;
  sourceCount?: number | null;
  onBackToProjects?: () => void;
  onSelectConversation?: (conversationId: string) => void;
};

type DetailTab = "conversations" | "sources" | "workbench";

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
  panel: "rgba(18, 25, 37, 0.92)",
  panelInset: "rgba(11, 14, 18, 0.64)",
  panelRaised: "rgba(24, 33, 48, 0.88)",
  glowTeal: "rgba(126, 215, 209, 0.14)",
  glowBronze: "rgba(138, 106, 60, 0.12)",
  glowEmerald: "rgba(47, 138, 104, 0.14)"
} as const;

function isEnvelopeFailureStatus(status?: string): boolean {
  return status === "error" || status === "blocked" || status === "unavailable";
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

function safeString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function truncate(value: string | null | undefined, limit: number): string | null {
  const text = safeString(value);
  if (!text) {
    return null;
  }

  if (text.length <= limit) {
    return text;
  }

  return `${text.slice(0, Math.max(1, limit - 1)).trimEnd()}…`;
}

function formatTimestamp(value: string | null | undefined): string | null {
  const text = safeString(value);
  if (!text) {
    return null;
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }

  return date.toLocaleString();
}

function formatCount(value: number | null | undefined, noun: string): string {
  const safeValue = typeof value === "number" && Number.isFinite(value) ? value : 0;
  return `${safeValue} ${noun}`;
}

function continuityItemsToText(items: ProjectContinuityItem[] | undefined): string {
  return (Array.isArray(items) ? items : [])
    .map((item) => safeString(item.label) ?? safeString(item.summary))
    .filter((value): value is string => Boolean(value))
    .join("\n");
}

function textToContinuityItems(value: string, status: string): ProjectContinuityItem[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 24)
    .map((label) => ({ label, status }));
}

function getConversationDisplayTitle(
  title: string | null | undefined,
  preview: string | null | undefined
): string {
  const cleanTitle = safeString(title);
  if (cleanTitle && cleanTitle !== "New conversation") {
    return cleanTitle;
  }

  return truncate(preview, 56) ?? cleanTitle ?? "New conversation";
}

function getProjectDisplayName(
  project: ProjectSummary | null | undefined,
  projectId: string
): string {
  return project?.name || projectId;
}

function getProjectStatus(project: ProjectSummary | null | undefined): string {
  return project?.status || "active";
}

export default function ProjectDetailPage({
  projectId,
  startupReady,
  onRightDrawerSectionsChange,
  project = null,
  relatedConversations = [],
  notesSummary = null,
  stateSummary = null,
  sourceCount = 0,
  onBackToProjects,
  onSelectConversation
}: ProjectDetailPageProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>("conversations");
  const [workbenchTool, setWorkbenchTool] = useState<ProjectWorkbenchTool>("sources");
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(
    relatedConversations[0]?.conversation_id ?? null
  );
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const launcherButtonRef = useRef<HTMLButtonElement | null>(null);
  const moreButtonRef = useRef<HTMLButtonElement | null>(null);

  const [liveProject, setLiveProject] = useState<ProjectSummary | null>(project);
  const [liveRelatedConversations, setLiveRelatedConversations] =
    useState<ProjectDetailConversationSummary[]>(relatedConversations);
  const [liveNotesSummary, setLiveNotesSummary] = useState<string | null>(notesSummary);
  const [liveStateSummary, setLiveStateSummary] = useState<string | null>(stateSummary);
  const [liveSourceCount, setLiveSourceCount] = useState<number | null>(sourceCount);
  const [liveContinuitySummary, setLiveContinuitySummary] =
    useState<ProjectContinuitySummary | null>(null);
  const [linkedMemory, setLinkedMemory] = useState<MemoryItemSummary[]>([]);
  const [continuityDraft, setContinuityDraft] = useState({
    currentState: "",
    latestChunk: "",
    projectNotes: "",
    milestones: "",
    decisions: "",
    blockers: "",
    nextActions: "",
    unresolvedQuestions: "",
    corrections: ""
  });
  const [isContinuitySaving, setIsContinuitySaving] = useState(false);

  const [isDetailLoading, setIsDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [launcherMenuOpen, setLauncherMenuOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadProjectRoom() {
      setIsDetailLoading(true);
      setDetailError(null);

      const selectionPromise = selectProject({ project_id: projectId });
      const memoryPromise = fetchMemoryItems({ projectId, limit: 100 });
      const detailResult = await fetchProjectDetail(projectId);
      const selectionResult = await selectionPromise;
      const memoryResult = await memoryPromise;

      if (cancelled) {
        return;
      }

      const detailPayload: ProjectDetailEnvelope | undefined = detailResult.payload;
      const detailStatus = detailPayload?.status;

      if (!detailResult.ok || isEnvelopeFailureStatus(detailStatus)) {
        setDetailError(
          getEnvelopeMessage(
            detailPayload,
            `Project "${projectId}" could not be loaded from the local bridge.`
          )
        );
        setIsDetailLoading(false);

        const selectionPayload: ProjectSelectionEnvelope | undefined = selectionResult.payload;
        const selectionStatus = selectionPayload?.status;
        if (!selectionResult.ok || isEnvelopeFailureStatus(selectionStatus)) {
          setActionNotice(
            getEnvelopeMessage(
              selectionPayload,
              `Project "${projectId}" could not be marked as the active project.`
            )
          );
        }

        return;
      }

      const detailData = detailPayload?.data;
      setLiveProject(detailData?.metadata ?? null);
      setLiveRelatedConversations(
        Array.isArray(detailData?.related_conversations)
          ? detailData.related_conversations
          : []
      );
      setLiveNotesSummary(
        typeof detailData?.notes_summary === "string" ? detailData.notes_summary : null
      );
      setLiveStateSummary(
        typeof detailData?.state_summary === "string" ? detailData.state_summary : null
      );
      setLiveSourceCount(
        typeof detailData?.source_count === "number" && Number.isFinite(detailData.source_count)
          ? detailData.source_count
          : 0
      );
      setLiveContinuitySummary(detailData?.continuity_summary ?? null);
      setLinkedMemory(
        memoryResult.ok && Array.isArray(memoryResult.payload.data?.items)
          ? memoryResult.payload.data.items
          : []
      );
      const loadedContinuity = detailData?.continuity_summary;
      setContinuityDraft({
        currentState: safeString(loadedContinuity?.current_state) ?? "",
        latestChunk: safeString(loadedContinuity?.latest_chunk) ?? "",
        projectNotes: safeString(loadedContinuity?.project_notes) ?? "",
        milestones: continuityItemsToText(loadedContinuity?.recent_milestones),
        decisions: continuityItemsToText(loadedContinuity?.decisions),
        blockers: continuityItemsToText(loadedContinuity?.open_blockers),
        nextActions: continuityItemsToText(loadedContinuity?.next_suggested_actions),
        unresolvedQuestions: continuityItemsToText(loadedContinuity?.unresolved_questions),
        corrections: continuityItemsToText(loadedContinuity?.corrections)
      });

      const selectionPayload: ProjectSelectionEnvelope | undefined = selectionResult.payload;
      const selectionStatus = selectionPayload?.status;
      if (!selectionResult.ok || isEnvelopeFailureStatus(selectionStatus)) {
        setActionNotice(
          getEnvelopeMessage(
            selectionPayload,
            `Project detail loaded, but "${projectId}" could not be persisted as the active project.`
          )
        );
      } else {
        setActionNotice(null);
      }

      setIsDetailLoading(false);
    }

    void loadProjectRoom();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const effectiveProject = liveProject ?? project ?? null;
  const effectiveRelatedConversations = liveRelatedConversations;
  const effectiveNotesSummary =
    safeString(liveNotesSummary) ?? safeString(effectiveProject?.notes_summary) ?? null;
  const effectiveStateSummary =
    safeString(liveStateSummary) ?? safeString(effectiveProject?.state_summary) ?? null;
  const effectiveSourceCount =
    typeof liveSourceCount === "number" && Number.isFinite(liveSourceCount)
      ? liveSourceCount
      : 0;
  const continuity = liveContinuitySummary;
  const continuityMilestones = Array.isArray(continuity?.recent_milestones)
    ? continuity.recent_milestones
    : [];
  const continuityDecisions = Array.isArray(continuity?.decisions)
    ? continuity.decisions
    : [];
  const continuityBlockers = Array.isArray(continuity?.open_blockers)
    ? continuity.open_blockers
    : [];
  const continuityNextActions = Array.isArray(continuity?.next_suggested_actions)
    ? continuity.next_suggested_actions
    : [];
  const continuityQuestions = Array.isArray(continuity?.unresolved_questions)
    ? continuity.unresolved_questions
    : [];
  const continuityCorrections = Array.isArray(continuity?.corrections)
    ? continuity.corrections
    : [];
  const linkedArtifacts = Array.isArray(continuity?.linked_artifacts)
    ? continuity.linked_artifacts
    : [];
  const continuityEditorFields: Array<{
    key: keyof typeof continuityDraft;
    label: string;
    placeholder: string;
  }> = [
    { key: "currentState", label: "Current state", placeholder: "What is true now?" },
    { key: "latestChunk", label: "Latest work", placeholder: "What was completed most recently?" },
    { key: "projectNotes", label: "Project notes", placeholder: "Durable project-only notes" },
    { key: "decisions", label: "Decisions", placeholder: "One durable decision per line" },
    { key: "milestones", label: "Milestones", placeholder: "One milestone per line" },
    { key: "blockers", label: "Blockers", placeholder: "One blocker per line" },
    { key: "nextActions", label: "Next actions", placeholder: "One next action per line" },
    { key: "unresolvedQuestions", label: "Unresolved questions", placeholder: "One open question per line" },
    { key: "corrections", label: "Corrections / supersessions", placeholder: "One correction per line" }
  ];

  const handleSaveContinuity = useCallback(async () => {
    setIsContinuitySaving(true);
    setActionNotice(null);
    const milestones = textToContinuityItems(continuityDraft.milestones, "complete");
    const decisions = textToContinuityItems(continuityDraft.decisions, "decided");
    const blockers = textToContinuityItems(continuityDraft.blockers, "blocked");
    const nextActions = textToContinuityItems(continuityDraft.nextActions, "planned");
    const unresolvedQuestions = textToContinuityItems(
      continuityDraft.unresolvedQuestions,
      "open"
    );
    const corrections = textToContinuityItems(continuityDraft.corrections, "corrective");
    const result = await updateProject(projectId, {
      current_state: continuityDraft.currentState,
      latest_chunk: continuityDraft.latestChunk,
      project_notes: continuityDraft.projectNotes,
      milestones,
      decisions,
      blockers,
      next_actions: nextActions,
      unresolved_questions: unresolvedQuestions,
      corrections
    });
    if (!result.ok || isEnvelopeFailureStatus(result.payload.status)) {
      setActionNotice(
        getEnvelopeMessage(result.payload, "Project continuity could not be saved.")
      );
      setIsContinuitySaving(false);
      return;
    }
    const updatedProject = result.payload.data?.project ?? null;
    if (updatedProject) {
      setLiveProject(updatedProject);
    }
    setLiveContinuitySummary((previous) => ({
      ...(previous ?? {}),
      project_id: projectId,
      current_state: continuityDraft.currentState || null,
      latest_chunk: continuityDraft.latestChunk || null,
      project_notes: continuityDraft.projectNotes || null,
      recent_milestones: milestones,
      decisions,
      open_blockers: blockers,
      next_suggested_actions: nextActions,
      unresolved_questions: unresolvedQuestions,
      corrections
    }));
    setActionNotice("Project continuity saved to the canonical project record.");
    setIsContinuitySaving(false);
  }, [continuityDraft, projectId]);

  useEffect(() => {
    if (!effectiveRelatedConversations.length) {
      setSelectedConversationId(null);
      return;
    }

    if (
      selectedConversationId &&
      effectiveRelatedConversations.some(
        (conversation) => conversation.conversation_id === selectedConversationId
      )
    ) {
      return;
    }

    setSelectedConversationId(effectiveRelatedConversations[0]?.conversation_id ?? null);
  }, [effectiveRelatedConversations, selectedConversationId]);

  const displayProjectName = useMemo(
    () => getProjectDisplayName(effectiveProject, projectId),
    [effectiveProject, projectId]
  );

  const selectedConversation = useMemo(() => {
    return (
      effectiveRelatedConversations.find(
        (conversation) => conversation.conversation_id === selectedConversationId
      ) ?? null
    );
  }, [effectiveRelatedConversations, selectedConversationId]);

  const openWorkbench = useCallback((tool: ProjectWorkbenchTool) => {
    setWorkbenchTool(tool);
    setActiveTab("workbench");
    setActionNotice(null);
    setLauncherMenuOpen(false);
    setMoreMenuOpen(false);
  }, []);

  const launcherMenuItems = useMemo<RoomActionMenuItem[]>(
    () => [
      {
        key: "open-conversation-file-tools",
        label: "Open conversation file tools",
        detail: selectedConversation
          ? "Use the live governed attachment lane in Conversations."
          : "Link and select a project conversation first.",
        stateLabel: selectedConversation ? "Live route" : "Unavailable",
        disabled: !selectedConversation || !onSelectConversation,
        onSelect: selectedConversation
          ? () => onSelectConversation?.(selectedConversation.conversation_id)
          : undefined
      },
      {
        key: "recent-files",
        label: "Project sources",
        detail: "Open the governed local source library for this Project.",
        stateLabel: "Local",
        onSelect: () => openWorkbench("sources")
      },
      { key: "launcher-divider", kind: "divider" },
      {
        key: "create-image",
        label: "Create image",
        detail: "Generate a bounded local synthetic image through ImageForge.",
        stateLabel: "Creator profile",
        onSelect: () => openWorkbench("image")
      },
      {
        key: "deep-research",
        label: "Deep research",
        detail: "Open the evidence-grounded Researcher workflow.",
        stateLabel: "Governed web",
        onSelect: () => openWorkbench("research")
      },
      {
        key: "web-search",
        label: "Web search",
        detail: "Run public-safe searches through the local SearXNG boundary.",
        stateLabel: "Internet controlled",
        onSelect: () => openWorkbench("research")
      }
    ],
    [onSelectConversation, openWorkbench, selectedConversation]
  );

  const moreMenuItems = useMemo<RoomActionMenuItem[]>(
    () => [
      {
        key: "study-learn",
        label: "Study and learn",
        detail: "Create a grounded study plan from source material.",
        stateLabel: "Local",
        onSelect: () => openWorkbench("study")
      },
      {
        key: "agent-mode",
        label: "Pursue goal",
        detail: "Plan bounded checkpoints with budgets, pause, stop, and receipts.",
        stateLabel: "Bounded",
        onSelect: () => openWorkbench("goals")
      },
      { key: "more-divider", kind: "divider" },
      {
        key: "add-source",
        label: "Add project source",
        detail: "Select and attach a source through the governed local ingestion lane.",
        stateLabel: "Local",
        onSelect: () => openWorkbench("sources")
      },
      {
        key: "canvas",
        label: "Canvas",
        detail: "Open Elysia's local Project Canvas.",
        stateLabel: "Local",
        onSelect: () => openWorkbench("canvas")
      },
      {
        key: "image-editing",
        label: "Image editing",
        detail: "Open a private working copy in the installed local GIMP application.",
        stateLabel: "Optional local tool",
        onSelect: () => openWorkbench("image_editing")
      },
      {
        key: "soundcloud",
        label: "SoundCloud",
        detail: "Configure the optional user-owned SoundCloud connector with Internet control and local credential revocation.",
        stateLabel: "Optional connector",
        onSelect: () => openWorkbench("soundcloud")
      },
      {
        key: "quizzes",
        label: "Quizzes",
        detail: "Generate, answer, grade, and review an evidence-grounded quiz.",
        stateLabel: "Local",
        onSelect: () => openWorkbench("quizzes")
      }
    ],
    [openWorkbench]
  );

  const projectConversationCount =
    typeof effectiveProject?.conversation_count === "number"
      ? effectiveProject.conversation_count
      : effectiveRelatedConversations.length;

  const currentProjectStatus =
    detailError && !effectiveProject
      ? "detail unavailable"
      : isDetailLoading && !effectiveProject
        ? "loading"
        : getProjectStatus(effectiveProject);

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    const selectedConversationLabel = selectedConversation
      ? getConversationDisplayTitle(
          selectedConversation.title ?? null,
          selectedConversation.last_message_preview ?? null
        )
      : isDetailLoading
        ? "Loading project conversation state"
        : "No project conversation selected";

    const sourceStateLabel =
      effectiveSourceCount > 0
        ? `${effectiveSourceCount} source${effectiveSourceCount === 1 ? "" : "s"} attached`
        : isDetailLoading
          ? "Loading source state"
          : "No project sources attached";

    const selectedApprovalState =
      safeString(selectedConversation?.approval_state) ?? "not_needed";

    const projectApprovalNeeded =
      selectedApprovalState === "needed" ||
      selectedApprovalState === "approval_needed" ||
      selectedApprovalState === "required";

    const projectRequestTraceState: DrawerSection["state"] = detailError
      ? "degraded"
      : isDetailLoading
        ? "live"
        : "partial";

    const projectRequestTraceLabel = detailError
      ? "Project detail load failed"
      : isDetailLoading
        ? "Project detail load in progress"
        : "No active trace";

    const projectRequestTraceStatus = detailError
      ? "Project detail route degraded"
      : isDetailLoading
        ? "Request active"
        : "No active trace";

    const sections: DrawerSection[] = [
      {
        key: "active_context",
        title: "Active Context",
        state: "live",
        accent: "warm",
        rows: [
          { label: "Room", value: "Project detail" },
          {
            label: "Surface",
            value:
              activeTab === "conversations"
                ? "Project conversations"
                : activeTab === "workbench"
                  ? "Project workbench"
                  : "Project sources"
          },
          { label: "Project", value: displayProjectName }
        ]
      },
      {
        key: "memory_classes",
        title: "Memory Classes",
        state: "partial",
        rows: [
          { label: "Working", value: "Idle" },
          { label: "Conversation", value: selectedConversationLabel },
          { label: "Project", value: displayProjectName },
          { label: "Sealed private", value: "Not touched in current room state" }
        ]
      },
      {
        key: "current_project",
        title: "Current Project",
        state: detailError ? "degraded" : "live",
        rows: [
          { label: "Selection", value: displayProjectName },
          { label: "Status", value: currentProjectStatus },
          {
            label: "Conversation count",
            value: `${projectConversationCount} visible conversation${projectConversationCount === 1 ? "" : "s"}`
          },
          {
            label: "Artifacts",
            value: `${linkedArtifacts.length} linked artifact${linkedArtifacts.length === 1 ? "" : "s"}`
          }
        ]
      },
      {
        key: "files_in_use",
        title: "Files in Use",
        state: activeTab === "sources" || activeTab === "workbench" ? "live" : "partial",
        rows: [
          { label: "Sources", value: sourceStateLabel },
          {
            label: "Status",
            value:
              effectiveSourceCount > 0
                ? "Project sources are available in the governed local workbench"
                : isDetailLoading
                  ? "Loading project source posture"
                  : "No project sources are attached yet"
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
          { label: "Boundary", value: "Local by default; web requires the Internet control" },
          { label: "Fallback", value: "No silent network or execution fallback" }
        ]
      },
      {
        key: "approval_needed",
        title: "Approval Needed",
        state: projectApprovalNeeded ? "live" : "inactive",
        rows: [
          {
            label: "Current state",
            value: projectApprovalNeeded ? "Approval required" : "No approval required"
          },
          {
            label: "Blocked state",
            value: projectApprovalNeeded
              ? "Awaiting approval before project-scoped action"
              : "No project-level approval gate active"
          }
        ]
      },
      {
        key: "journal_summary",
        title: "Journal Summary",
        state: "partial",
        rows: [
          { label: "Journaling", value: "Project room visible" },
          {
            label: "Notes summary",
            value: effectiveNotesSummary ?? "No notes summary recorded yet"
          },
          {
            label: "State summary",
            value: effectiveStateSummary ?? "No state summary recorded yet"
          }
        ]
      },
      {
        key: "request_trace",
        title: "Request Trace",
        state: projectRequestTraceState,
        rows: [
          { label: "Current trace", value: projectRequestTraceLabel },
          {
            label: "Detail",
            value:
              detailError
                ? "Project detail load failed"
                : isDetailLoading
                  ? "Project detail is loading from the local bridge"
                  : activeTab === "conversations"
                    ? "Project detail and linked conversations are bridge-backed"
                    : activeTab === "workbench"
                      ? "Project workbench actions use account-scoped governed local contracts"
                      : "Project source posture is bridge-backed"
          },
          { label: "Status", value: projectRequestTraceStatus }
        ]
      }
    ];

    return sections.filter((section) => {
      if (section.key === "files_in_use") {
        return activeTab === "sources" || activeTab === "workbench" || effectiveSourceCount > 0;
      }
      if (section.key === "memory_classes") {
        return Boolean(selectedConversation);
      }
      if (section.key === "journal_summary") {
        return Boolean(effectiveNotesSummary || effectiveStateSummary);
      }
      return true;
    });
  }, [
    activeTab,
    currentProjectStatus,
    detailError,
    displayProjectName,
    effectiveNotesSummary,
    effectiveSourceCount,
    effectiveStateSummary,
    isDetailLoading,
    projectConversationCount,
    selectedConversation,
    startupReady
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);

    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  async function handleBackToProjectsClick() {
    await selectProject({ project_id: null });
    onBackToProjects?.();
  }

  function handleLauncherClick() {
    setMoreMenuOpen(false);
    setActionNotice(null);
    setLauncherMenuOpen((current) => !current);
  }

  function handleMoreClick() {
    setLauncherMenuOpen(false);
    setActionNotice(null);
    setMoreMenuOpen((current) => !current);
  }

  function handleSelectConversation(conversationId: string) {
    setSelectedConversationId(conversationId);
    setActionNotice(null);
    setLauncherMenuOpen(false);
    setMoreMenuOpen(false);
    onSelectConversation?.(conversationId);
  }

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        minHeight: 0,
        flex: 1,
        overflow: "hidden"
      }}
    >
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "0.85rem",
            alignItems: "flex-start",
            flexWrap: "wrap"
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
              Project detail
            </div>

            <h1
              style={{
                margin: 0,
                fontSize: "2.15rem",
                lineHeight: 1.1
              }}
            >
              {displayProjectName}
            </h1>

            <div
              style={{
                marginTop: "0.55rem",
                color: palette.silverMuted,
                lineHeight: 1.6,
                maxWidth: "78ch"
              }}
            >
              Project continuity, grounded learning, bounded goals, research, creative tools,
              sources, and linked conversations stay together behind governed local contracts.
            </div>
          </div>

          {onBackToProjects && (
            <button
              type="button"
              onClick={() => {
                void handleBackToProjectsClick();
              }}
              style={{
                padding: "0.68rem 0.9rem",
                borderRadius: "14px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(11, 14, 18, 0.34)",
                color: palette.silver,
                cursor: "pointer",
                fontSize: "0.82rem",
                fontWeight: 600,
                whiteSpace: "nowrap"
              }}
            >
              Back to Projects
            </button>
          )}
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
          ? "Startup truth is ready. Project continuity and the functional Project workbench are loaded through the authenticated local bridge."
          : "Startup truth is not yet ready. This project room is visible, but anything that would act through the local body should remain explicitly staged."}
      </div>

      {isDetailLoading && (
        <div
          style={{
            padding: "0.95rem 1rem",
            borderRadius: "18px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(24, 33, 48, 0.52) 0%, rgba(18, 25, 37, 0.78) 100%)",
            color: palette.silverMuted,
            lineHeight: 1.58
          }}
        >
          Loading project detail from the local bridge.
        </div>
      )}

      {detailError && (
        <div
          style={{
            padding: "0.95rem 1rem",
            borderRadius: "18px",
            border: `1px solid ${palette.lineBronze}`,
            background:
              "linear-gradient(180deg, rgba(42, 25, 21, 0.48) 0%, rgba(18, 25, 37, 0.78) 100%)",
            color: palette.silverMuted,
            lineHeight: 1.58
          }}
        >
          {detailError}
        </div>
      )}

      {actionNotice && (
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
          {actionNotice}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gap: "0.85rem",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.74) 100%)"
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "1rem",
            alignItems: "center",
            flexWrap: "wrap"
          }}
        >
          <div
            style={{
              display: "flex",
              gap: "0.6rem",
              flexWrap: "wrap",
              alignItems: "center"
            }}
          >
            {[
              {
                label: "Status",
                value: currentProjectStatus
              },
              {
                label: "Conversations",
                value: String(projectConversationCount)
              },
              {
                label: "Sources",
                value: String(effectiveSourceCount)
              }
            ].map((chip) => (
              <div
                key={`${chip.label}-${chip.value}`}
                style={{
                  padding: "0.42rem 0.62rem",
                  borderRadius: "999px",
                  border: `1px solid ${palette.lineSilver}`,
                  color: palette.silverMuted,
                  fontSize: "0.76rem",
                  lineHeight: 1.2
                }}
              >
                {chip.label}: {chip.value}
              </div>
            ))}
          </div>

          <div
            style={{
              display: "flex",
              gap: "0.6rem",
              flexWrap: "wrap",
              alignItems: "center",
              overflow: "visible"
            }}
          >
            <div
              style={{
                position: "relative",
                overflow: "visible"
              }}
            >
              <button
                ref={launcherButtonRef}
                type="button"
                aria-haspopup="menu"
                aria-expanded={launcherMenuOpen}
                onClick={handleLauncherClick}
                style={{
                  padding: "0.68rem 0.88rem",
                  borderRadius: "14px",
                  border: `1px solid ${palette.lineBronze}`,
                  background:
                    "linear-gradient(180deg, rgba(43, 31, 21, 0.56) 0%, rgba(18, 25, 37, 0.72) 100%)",
                  color: palette.silver,
                  boxShadow: `0 0 18px ${palette.glowBronze}`,
                  cursor: "pointer",
                  fontSize: "0.82rem",
                  fontWeight: 600
                }}
              >
                +
              </button>

              <RoomActionMenu
                open={launcherMenuOpen}
                onClose={() => setLauncherMenuOpen(false)}
                items={launcherMenuItems}
                anchorRef={launcherButtonRef}
                align="end"
              />
            </div>

            <button
              type="button"
              title="Create a local synthetic reading-voice artifact through SpeechForge."
              onClick={() => openWorkbench("speak")}
              style={{
                padding: "0.68rem 0.88rem",
                borderRadius: "14px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(11, 14, 18, 0.34)",
                color: palette.silver,
                cursor: "pointer",
                fontSize: "0.82rem",
                fontWeight: 600
              }}
            >
              Speak
            </button>

            <div
              style={{
                position: "relative",
                overflow: "visible"
              }}
            >
              <button
                ref={moreButtonRef}
                type="button"
                aria-haspopup="menu"
                aria-expanded={moreMenuOpen}
                onClick={handleMoreClick}
                style={{
                  padding: "0.68rem 0.88rem",
                  borderRadius: "14px",
                  border: `1px solid ${palette.lineSilver}`,
                  background: "rgba(11, 14, 18, 0.34)",
                  color: palette.silver,
                  cursor: "pointer",
                  fontSize: "0.82rem",
                  fontWeight: 600
                }}
              >
                ⋮
              </button>

              <RoomActionMenu
                open={moreMenuOpen}
                onClose={() => setMoreMenuOpen(false)}
                items={moreMenuItems}
                anchorRef={moreButtonRef}
                align="end"
              />
            </div>
          </div>
        </div>

        {effectiveProject?.description && (
          <div
            style={{
              color: palette.silverMuted,
              lineHeight: 1.58
            }}
          >
            {effectiveProject.description}
          </div>
        )}
      </div>

      <div
        style={{
          display: "flex",
          gap: "0.65rem",
          flexWrap: "wrap"
        }}
      >
        {[
          { value: "conversations", label: "Conversations" },
          { value: "sources", label: "Sources" },
          { value: "workbench", label: "Workbench" }
        ].map((tab) => {
          const selected = activeTab === tab.value;

          return (
            <button
              key={tab.value}
              type="button"
              onClick={() => {
                setActiveTab(tab.value as DetailTab);
                setActionNotice(null);
                setLauncherMenuOpen(false);
                setMoreMenuOpen(false);
              }}
              style={{
                padding: "0.56rem 0.82rem",
                borderRadius: "999px",
                border: selected
                  ? `1px solid ${palette.lineTeal}`
                  : `1px solid ${palette.lineSilver}`,
                background: selected
                  ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.76) 100%)"
                  : "linear-gradient(180deg, rgba(24, 33, 48, 0.54) 0%, rgba(18, 25, 37, 0.56) 100%)",
                boxShadow: selected ? `0 0 18px ${palette.glowTeal}` : "none",
                color: selected ? palette.teal : palette.silverMuted,
                cursor: "pointer",
                fontSize: "0.8rem",
                letterSpacing: "0.05em",
                textTransform: "uppercase"
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === "workbench" || activeTab === "sources" ? (
        <ProjectWorkbenchPanel
          projectId={projectId}
          initialTool={activeTab === "sources" ? "sources" : workbenchTool}
          onSourceCountChange={setLiveSourceCount}
        />
      ) : (
      <div
        className="elysia-responsive-split"
        style={{
          display: "grid",
          gridTemplateColumns: "320px minmax(0, 1fr)",
          gap: "1rem",
          minHeight: 0,
          flex: 1,
          overflow: "hidden"
        }}
      >
        <aside
          className="elysia-stacked-pane"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.9rem",
            minHeight: 0,
            overflow: "hidden",
            padding: "1rem",
            borderRadius: "22px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.92) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 28px rgba(0,0,0,0.18)"
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
              {activeTab === "conversations" ? "Project conversations" : "Project context"}
            </div>

            <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
              {activeTab === "conversations"
                ? "This list is scoped to the current project."
                : "Project notes, state, and source posture live here."}
            </div>
          </div>

          {activeTab === "conversations" ? (
            <div
              style={{
                display: "grid",
                gap: "0.6rem",
                flex: 1,
                minHeight: 0,
                alignContent: "start",
                overflowY: "auto",
                overflowX: "hidden",
                paddingRight: "0.35rem"
              }}
            >
              {isDetailLoading ? (
                <div
                  style={{
                    padding: "1rem",
                    borderRadius: "16px",
                    border: `1px solid ${palette.lineSilver}`,
                    background: "rgba(11, 14, 18, 0.42)",
                    color: palette.silverMuted,
                    lineHeight: 1.55
                  }}
                >
                  Loading project conversations from the local bridge.
                </div>
              ) : effectiveRelatedConversations.length === 0 ? (
                <div
                  style={{
                    padding: "1rem",
                    borderRadius: "16px",
                    border: `1px dashed ${palette.lineBronze}`,
                    background: "rgba(11, 14, 18, 0.42)",
                    color: palette.silverMuted,
                    lineHeight: 1.55
                  }}
                >
                  No conversations are linked to this project yet. Move one from the
                  Conversations room to see it here.
                </div>
              ) : (
                effectiveRelatedConversations.map((conversation) => {
                  const selected =
                    conversation.conversation_id === selectedConversationId;

                  const conversationTitle = getConversationDisplayTitle(
                    conversation.title ?? null,
                    conversation.last_message_preview ?? null
                  );

                  return (
                    <button
                      key={conversation.conversation_id}
                      type="button"
                      onClick={() => handleSelectConversation(conversation.conversation_id)}
                      style={{
                        display: "grid",
                        gap: "0.45rem",
                        width: "100%",
                        padding: "0.9rem",
                        borderRadius: "16px",
                        border: selected
                          ? `1px solid ${palette.lineTeal}`
                          : `1px solid rgba(199, 210, 218, 0.08)`,
                        background: selected
                          ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.76) 100%)"
                          : "linear-gradient(180deg, rgba(24, 33, 48, 0.54) 0%, rgba(18, 25, 37, 0.56) 100%)",
                        boxShadow: selected ? `0 0 20px ${palette.glowTeal}` : "none",
                        textAlign: "left",
                        cursor: "pointer"
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
                            fontWeight: selected ? 700 : 600,
                            color: selected ? palette.teal : palette.silver,
                            minWidth: 0,
                            overflowWrap: "anywhere"
                          }}
                        >
                          {conversationTitle}
                        </div>

                        {conversation.current_mode && (
                          <span
                            style={{
                              fontSize: "0.72rem",
                              letterSpacing: "0.06em",
                              textTransform: "uppercase",
                              color: palette.silverMuted,
                              whiteSpace: "nowrap"
                            }}
                          >
                            {conversation.current_mode}
                          </span>
                        )}
                      </div>

                      {conversation.last_message_preview && (
                        <div
                          style={{
                            color: palette.silverMuted,
                            lineHeight: 1.45,
                            fontSize: "0.9rem"
                          }}
                        >
                          {truncate(conversation.last_message_preview, 120)}
                        </div>
                      )}

                      <div
                        style={{
                          display: "flex",
                          gap: "0.65rem",
                          flexWrap: "wrap",
                          fontSize: "0.76rem",
                          color: palette.silverMuted
                        }}
                      >
                        <span>{formatCount(conversation.message_count, "messages")}</span>
                        {conversation.pinned && <span>Pinned</span>}
                        {conversation.updated_at_utc && (
                          <span>{formatTimestamp(conversation.updated_at_utc)}</span>
                        )}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gap: "0.85rem",
                alignContent: "start"
              }}
            >
              <details
                style={{
                  padding: "0.9rem",
                  borderRadius: "18px",
                  border: `1px solid ${palette.lineTeal}`,
                  background: "rgba(16, 41, 43, 0.34)"
                }}
              >
                <summary style={{ cursor: "pointer", color: palette.teal, fontWeight: 700 }}>
                  Edit canonical project continuity
                </summary>
                <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.9rem" }}>
                  {continuityEditorFields.map((field) => (
                    <label key={field.key} style={{ display: "grid", gap: "0.3rem" }}>
                      <span style={{ color: palette.sandstone, fontSize: "0.78rem" }}>
                        {field.label}
                      </span>
                      <textarea
                        value={continuityDraft[field.key]}
                        placeholder={field.placeholder}
                        rows={field.key === "currentState" || field.key === "latestChunk" ? 2 : 3}
                        onChange={(event) =>
                          setContinuityDraft((current) => ({
                            ...current,
                            [field.key]: event.target.value
                          }))
                        }
                        style={{
                          resize: "vertical",
                          borderRadius: "10px",
                          border: `1px solid ${palette.lineSilver}`,
                          background: "rgba(11, 14, 18, 0.78)",
                          color: palette.silver,
                          padding: "0.65rem",
                          font: "inherit"
                        }}
                      />
                    </label>
                  ))}
                  <button
                    type="button"
                    disabled={isContinuitySaving}
                    onClick={() => void handleSaveContinuity()}
                    style={{
                      borderRadius: "12px",
                      border: `1px solid ${palette.lineTeal}`,
                      background: "rgba(47, 138, 104, 0.28)",
                      color: palette.teal,
                      padding: "0.7rem 0.9rem",
                      cursor: isContinuitySaving ? "wait" : "pointer"
                    }}
                  >
                    {isContinuitySaving ? "Saving…" : "Save project continuity"}
                  </button>
                  <div style={{ color: palette.silverMuted, fontSize: "0.78rem", lineHeight: 1.45 }}>
                    This updates the canonical Project JSON. It does not create a competing memory record.
                  </div>
                </div>
              </details>
              {[
                {
                  title: "Notes summary",
                  body:
                    effectiveNotesSummary ??
                    "No notes summary recorded for this project yet."
                },
                {
                  title: "State summary",
                  body:
                    effectiveStateSummary ??
                    "No state summary recorded for this project yet."
                },
                {
                  title: "Source posture",
                  body:
                    effectiveSourceCount > 0
                      ? `${effectiveSourceCount} source${effectiveSourceCount === 1 ? "" : "s"} are currently counted for this project.`
                      : isDetailLoading
                        ? "Loading project source posture."
                        : "No project sources are attached yet."
                },
                {
                  title: "Continuity",
                  body:
                    safeString(continuity?.current_state) ??
                    effectiveStateSummary ??
                    "No continuity current-state summary is stored yet."
                },
                {
                  title: "Milestones",
                  body:
                    continuityMilestones.length > 0
                      ? continuityMilestones
                          .slice(0, 3)
                          .map((item) => safeString(item.label) ?? "Milestone")
                          .join(" · ")
                      : "No recent milestones are stored yet."
                },
                {
                  title: "Decisions",
                  body:
                    continuityDecisions.length > 0
                      ? continuityDecisions
                          .slice(0, 3)
                          .map((item) => safeString(item.label) ?? "Decision")
                          .join(" · ")
                      : "No durable project decisions are stored yet."
                },
                {
                  title: "Blockers",
                  body:
                    continuityBlockers.length > 0
                      ? continuityBlockers
                          .slice(0, 3)
                          .map((item) => safeString(item.label) ?? "Blocker")
                          .join(" · ")
                      : "No open blockers are stored yet."
                },
                {
                  title: "Next actions",
                  body:
                    continuityNextActions.length > 0
                      ? continuityNextActions
                          .slice(0, 3)
                          .map((item) => safeString(item.label) ?? "Next action")
                          .join(" · ")
                      : "No next actions are stored yet."
                },
                {
                  title: "Unresolved questions",
                  body:
                    continuityQuestions.length > 0
                      ? continuityQuestions
                          .slice(0, 3)
                          .map((item) => safeString(item.label) ?? "Open question")
                          .join(" · ")
                      : "No unresolved project questions are stored yet."
                },
                {
                  title: "Corrections / supersessions",
                  body:
                    continuityCorrections.length > 0
                      ? continuityCorrections
                          .slice(0, 3)
                          .map((item) => safeString(item.label) ?? "Correction")
                          .join(" · ")
                      : "No project corrections or supersessions are stored yet."
                },
                {
                  title: "Linked artifacts",
                  body:
                    linkedArtifacts.length > 0
                      ? linkedArtifacts
                          .slice(0, 3)
                          .map((item) => safeString(item.title) ?? safeString(item.artifact_id) ?? "Artifact")
                          .join(" · ")
                      : "No linked artifacts are visible yet."
                },
                {
                  title: "Canonical project memory",
                  body:
                    linkedMemory.length > 0
                      ? `${linkedMemory.length} authorized Memory record${linkedMemory.length === 1 ? "" : "s"} link to this canonical Project authority.`
                      : "No canonical Memory records currently link to this project. Project continuity remains authoritative here."
                },
                {
                  title: "Prospective memory",
                  body:
                    linkedMemory.some((item) => item.form === "prospective")
                      ? linkedMemory
                          .filter((item) => item.form === "prospective")
                          .slice(0, 3)
                          .map((item) => item.title ?? item.summary ?? item.memory_id)
                          .join(" · ")
                      : "No owned project-linked prospective items are due or stored."
                },
                {
                  title: "Project memory corrections",
                  body:
                    linkedMemory.some((item) => item.form === "corrective" || item.status === "superseded")
                      ? linkedMemory
                          .filter((item) => item.form === "corrective" || item.status === "superseded")
                          .slice(0, 3)
                          .map((item) => item.title ?? item.summary ?? item.memory_id)
                          .join(" · ")
                      : "No linked corrective or superseded memory is visible under current authorization."
                }
              ].map((card) => (
                <div
                  key={card.title}
                  style={{
                    padding: "1rem",
                    borderRadius: "18px",
                    border: `1px solid ${palette.lineSilver}`,
                    background:
                      "linear-gradient(180deg, rgba(24, 33, 48, 0.50) 0%, rgba(18, 25, 37, 0.62) 100%)"
                  }}
                >
                  <div
                    style={{
                      fontSize: "0.82rem",
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      color: palette.sandstone,
                      marginBottom: "0.45rem"
                    }}
                  >
                    {card.title}
                  </div>
                  <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
                    {card.body}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>

        <section
          className="elysia-stacked-pane"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "1rem",
            minHeight: 0,
            padding: "1rem",
            borderRadius: "22px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.94) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 28px rgba(0,0,0,0.18)"
          }}
        >
          {activeTab === "conversations" ? (
            isDetailLoading ? (
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  display: "grid",
                  placeItems: "center",
                  padding: "1.2rem",
                  borderRadius: "24px",
                  border: `1px dashed ${palette.lineSilver}`,
                  background:
                    "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.82) 100%)",
                  textAlign: "center"
                }}
              >
                <div
                  style={{
                    maxWidth: "56ch",
                    display: "grid",
                    gap: "0.8rem"
                  }}
                >
                  <div
                    style={{
                      fontSize: "0.82rem",
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      color: palette.sandstone
                    }}
                  >
                    Loading project detail
                  </div>
                  <div
                    style={{
                      fontSize: "1.18rem",
                      lineHeight: 1.3,
                      color: palette.silver
                    }}
                  >
                    Loading this project’s conversation surface from the local bridge.
                  </div>
                </div>
              </div>
            ) : (
              <>
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
                    Active project conversation
                  </div>

                  <h2
                    style={{
                      margin: 0,
                      fontSize: "1.45rem",
                      lineHeight: 1.15
                    }}
                  >
                    {selectedConversation
                      ? getConversationDisplayTitle(
                          selectedConversation.title ?? null,
                          selectedConversation.last_message_preview ?? null
                        )
                      : "No project conversation selected"}
                  </h2>
                </div>

                {selectedConversation ? (
                  <>
                    <div
                      style={{
                        padding: "1rem",
                        borderRadius: "18px",
                        border: `1px solid ${palette.lineSilver}`,
                        background:
                          "linear-gradient(180deg, rgba(24, 33, 48, 0.52) 0%, rgba(18, 25, 37, 0.66) 100%)"
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          gap: "0.6rem",
                          flexWrap: "wrap",
                          marginBottom: "0.7rem"
                        }}
                      >
                        {[
                          selectedConversation.current_role
                            ? `Role ${selectedConversation.current_role}`
                            : null,
                          selectedConversation.locality
                            ? `Locality ${selectedConversation.locality}`
                            : null,
                          selectedConversation.approval_state
                            ? `Approval ${selectedConversation.approval_state}`
                            : null,
                          selectedConversation.capability_state
                            ? `Capability ${selectedConversation.capability_state}`
                            : null
                        ]
                          .filter((value): value is string => Boolean(value))
                          .map((chip) => (
                            <div
                              key={chip}
                              style={{
                                padding: "0.38rem 0.58rem",
                                borderRadius: "999px",
                                border: `1px solid ${palette.lineSilver}`,
                                color: palette.silverMuted,
                                fontSize: "0.76rem",
                                lineHeight: 1.2
                              }}
                            >
                              {chip}
                            </div>
                          ))}
                      </div>

                      <div
                        style={{
                          color: palette.silverMuted,
                          lineHeight: 1.6
                        }}
                      >
                        {selectedConversation.last_message_preview
                          ? truncate(selectedConversation.last_message_preview, 320)
                          : "No last-message preview is available for this project conversation yet."}
                      </div>
                    </div>

                    <div
                      style={{
                        padding: "1rem",
                        borderRadius: "18px",
                        border: `1px dashed ${palette.lineTeal}`,
                        background: "rgba(11, 14, 18, 0.42)",
                        color: palette.silverMuted,
                        lineHeight: 1.6
                      }}
                    >
                      Select this conversation from the project list to open its real thread and
                      governed send path in Conversations. Project detail remains a continuity view.
                    </div>

                  </>
                ) : (
                  <div
                    style={{
                      flex: 1,
                      minHeight: 0,
                      display: "grid",
                      placeItems: "center",
                      padding: "1.2rem",
                      borderRadius: "24px",
                      border: `1px dashed ${palette.lineBronze}`,
                      background:
                        "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.82) 100%)",
                      textAlign: "center"
                    }}
                  >
                    <div
                      style={{
                        maxWidth: "56ch",
                        display: "grid",
                        gap: "0.8rem"
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
                        Empty conversation surface
                      </div>
                      <div
                        style={{
                          fontSize: "1.18rem",
                          lineHeight: 1.3,
                          color: palette.silver
                        }}
                      >
                        No project conversation is selected yet.
                      </div>
                      <div
                        style={{
                          color: palette.silverMuted,
                          lineHeight: 1.6
                        }}
                      >
                        Link or move a conversation into this project from Conversations to work
                        with it here.
                      </div>
                    </div>
                  </div>
                )}
              </>
            )
          ) : (
            <div
              style={{
                flex: 1,
                minHeight: 0,
                display: "grid",
                placeItems: "center",
                padding: "1.2rem",
                borderRadius: "24px",
                border: `1px dashed ${palette.lineBronze}`,
                background:
                  "linear-gradient(180deg, rgba(18, 25, 37, 0.72) 0%, rgba(11, 14, 18, 0.82) 100%)",
                textAlign: "center"
              }}
            >
              <div
                style={{
                  maxWidth: "60ch",
                  display: "grid",
                  gap: "0.9rem"
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
                  Sources
                </div>
                <div
                  style={{
                    fontSize: "1.22rem",
                    lineHeight: 1.3,
                    color: palette.silver
                  }}
                >
                  {effectiveSourceCount > 0
                    ? `${effectiveSourceCount} project source${effectiveSourceCount === 1 ? "" : "s"} are counted here.`
                    : isDetailLoading
                      ? "Loading project source posture."
                      : "No sources are attached to this project yet."}
                </div>
                <div
                  style={{
                    color: palette.silverMuted,
                    lineHeight: 1.6
                  }}
                >
                  This is a read-only source posture. Add files through a linked conversation’s
                  governed attachment lane until a project-source contract exists.
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
      )}
    </div>
  );
}

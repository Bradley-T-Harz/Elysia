import { useEffect, useMemo, useState } from "react";
import TopBar from "./TopBar";
import HomePage from "./HomePage";
import LeftRail, { type LeftRailRoom } from "./LeftRail";
import RightDrawer, { type DrawerSection } from "./RightDrawer";
import BottomStatusBar from "./BottomStatusBar";
import ConversationsPage from "./ConversationsPage";
import ProjectsPage from "./ProjectsPage";
import ProjectDetailPage from "./ProjectDetailPage";
import MemoryPage from "./MemoryPage";
import GovernancePage from "./GovernancePage";
import StatusMenuPage from "./StatusMenuPage";
import HealthPage from "./HealthPage";
import CapabilitiesPage from "./CapabilitiesPage";
import RequestsPage from "./RequestsPage";
import ArtifactsPage from "./ArtifactsPage";
import UserProfilePage from "./UserProfilePage";
import AddonsPage from "./AddonsPage";
import AdminPage from "./AdminPage";
import type { AccountStateData } from "./api/bridgeClient";
import { PhysicalPosition } from "@tauri-apps/api/dpi";
import { WebviewWindow, getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import { useStartupTruth } from "./hooks/useStartupTruth";
import type {
  BridgeStartupState,
  InvokerStatusEnvelope,
  RuntimeStatusEnvelope
} from "./api/bridgeClient";
import type { TrustBadge } from "./themeTokens";
import {
  readDesktopPreferences,
  type DesktopPreferences
} from "./desktopPreferences";

type AppRoom = LeftRailRoom | "status_menu" | "project_detail";

const palette = {
  obsidian: "#0B0E12",
  midnight: "#121925",
  basalt: "#2A3138",
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.36)"
} as const;

function mapStartupTruthToSurfaceState(
  startupTruthState: BridgeStartupState
): DrawerSection["state"] {
  switch (startupTruthState) {
    case "ok":
      return "live";
    case "degraded":
      return "degraded";
    case "unavailable":
    case "error":
      return "unavailable";
    case "checking":
    default:
      return "partial";
  }
}

function buildBoundaryFlagsSection(
  startupTruthState: BridgeStartupState
): DrawerSection {
  switch (startupTruthState) {
    case "degraded":
      return {
        key: "boundary_flags",
        title: "Boundary Flags",
        state: "degraded",
        accent: "teal",
        rows: [
          { label: "Local / external", value: "Current chamber state remains local" },
          {
            label: "Blocked / degraded",
            value: "Degraded startup truth is active for the current chamber state"
          },
          { label: "Posture", value: "Downstream of body truth only" }
        ]
      };
    case "unavailable":
    case "error":
      return {
        key: "boundary_flags",
        title: "Boundary Flags",
        state: "unavailable",
        accent: "teal",
        rows: [
          { label: "Local / external", value: "Current chamber state remains local" },
          {
            label: "Blocked / degraded",
            value: "Required startup truth is unavailable for the current chamber state"
          },
          { label: "Posture", value: "Downstream of body truth only" }
        ]
      };
    case "checking":
      return {
        key: "boundary_flags",
        title: "Boundary Flags",
        state: "partial",
        accent: "teal",
        rows: [
          { label: "Local / external", value: "Current chamber state remains local" },
          {
            label: "Blocked / degraded",
            value: "Startup truth is still being established for the current chamber state"
          },
          { label: "Posture", value: "Downstream of body truth only" }
        ]
      };
    case "ok":
    default:
      return {
        key: "boundary_flags",
        title: "Boundary Flags",
        state: "live",
        accent: "teal",
        rows: [
          { label: "Local / external", value: "Current chamber state remains local" },
          { label: "Blocked / degraded", value: "No blocked or degraded path is active" },
          { label: "Posture", value: "Downstream of body truth only" }
        ]
      };
  }
}

function buildIdleDrawerSections(
  view: "home" | "status_menu" | "user_profile" | "addons",
  startupTruthState: BridgeStartupState
): DrawerSection[] {
  const viewingStatusMenu = view === "status_menu";
  const viewingUserProfile = view === "user_profile";
  const viewingAddons = view === "addons";

  const sections: DrawerSection[] = [
    {
      key: "active_context",
      title: "Active Context",
      state: "partial",
      accent: "warm",
      rows: [
        {
          label: "Mode",
          value: viewingStatusMenu
            ? "Status Menu is open for chamber inspection"
            : viewingUserProfile
              ? "Personal Identity is open inside the sealed local identity boundary"
            : viewingAddons
              ? "Add-ons room is open; external catalog remains link-gated"
            : "No active working mode is surfaced in idle chamber state"
        },
        { label: "Conversation", value: "No active conversation is loaded" },
        {
          label: "Context source",
          value: viewingStatusMenu
            ? "Current chamber state plus startup truth"
            : viewingUserProfile
              ? "Authenticated local identity route only"
            : viewingAddons
              ? "Optional Marketplace truth plus local staged-package registry truth"
            : "Idle chamber state only"
        }
      ]
    },
    {
      key: "memory_classes",
      title: "Memory Classes",
      state: "partial",
      rows: [
        { label: "Working", value: "No active request is using working memory" },
        { label: "Conversation", value: "No active thread is loaded" },
        { label: "Project", value: "No project memory is currently linked" },
        {
          label: "Sealed private",
          value: viewingUserProfile
            ? "Visible only to the authenticated user profile page"
            : "Not touched in idle chamber state"
        }
      ]
    },
    {
      key: "current_project",
      title: "Current Project",
      state: "partial",
      rows: [
        { label: "Selection", value: "No active project selected" },
        { label: "Status", value: "No project linkage is currently visible here" }
      ]
    },
    {
      key: "files_in_use",
      title: "Files in Use",
      state: "planned",
      rows: [
        { label: "Attachments", value: "No files attached" },
        { label: "Status", value: "Drawer file feed not yet live" }
      ]
    },
    {
      key: "plan_preview",
      title: "Plan Preview",
      state: "partial",
      rows: [
        {
          label: "Intent",
          value: viewingStatusMenu
            ? "Status inspection only"
            : viewingUserProfile
              ? "Account profile inspection/editing only"
            : viewingAddons
              ? "Marketplace add-on manifest inspection and preview only"
            : "No active governed request"
        },
        { label: "Summary", value: "No plan preview while the chamber is idle" },
        {
          label: "Idle state",
          value: viewingUserProfile
            ? "No runtime request is using private account fields"
            : viewingAddons
              ? "No local add-on execution is live"
            : "No active request in progress"
        }
      ]
    },
    buildBoundaryFlagsSection(startupTruthState),
    {
      key: "approval_needed",
      title: "Approval Needed",
      state: "inactive",
      rows: [
        { label: "Current state", value: "No approval required" },
        {
          label: "Blocked state",
          value: viewingAddons
            ? "Future add-on execution will require local operator approval"
            : "Approval is shown only when a request is gated"
        }
      ]
    },
    {
      key: "journal_summary",
      title: "Journal Summary",
      state: "partial",
      rows: [
        { label: "Journaling", value: "Policy-governed when a request completes" },
        { label: "Idle state", value: "No journal entry for current idle state" },
        {
          label: "Status",
          value: "Idle summary only; richer journal surfacing is still maturing"
        }
      ]
    },
    {
      key: "request_trace",
      title: "Request Trace",
      state: "partial",
      rows: [
        { label: "Current trace", value: "No active trace" },
        {
          label: "Status",
          value: "Idle summary only; richer trace surfacing is still maturing"
        }
      ]
    }
  ];

  return sections.filter((section) =>
    ["active_context", "boundary_flags", "approval_needed", "request_trace"].includes(section.key)
  );
}

function buildBottomStatusSummaryText(
  activeRoom: AppRoom,
  startupTruthState: BridgeStartupState,
  runtimeTruth: RuntimeStatusEnvelope["data"] | null | undefined,
  invokerTruth: InvokerStatusEnvelope["data"] | null | undefined
): string {
  switch (startupTruthState) {
    case "ok":
      if (runtimeTruth?.approval_needed || invokerTruth?.approval_needed) {
        return "The latest governed runtime state is waiting for approval.";
      }

      if (runtimeTruth?.runtime_state === "blocked" || invokerTruth?.invoker_state === "blocked") {
        return "The latest governed runtime path is blocked; no continuation is implied.";
      }

      if (runtimeTruth?.used_fallback || invokerTruth?.used_fallback) {
        return "The latest governed runtime used a surfaced fallback path.";
      }

      if (runtimeTruth?.stayed_local === false || invokerTruth?.stayed_local === false) {
        return "The latest governed runtime reports an explicit external boundary crossing.";
      }

      if (activeRoom === "home") {
        return "Current chamber session verified inside the local boundary.";
      }

      if (activeRoom === "status_menu") {
        return "Status Menu is showing the current chamber condition.";
      }

      return "Current room remains inside the governed local path.";
    case "degraded":
      return "Current chamber session is available, but startup truth is degraded.";
    case "unavailable":
    case "error":
      return "Current chamber session is visible, but required local startup truth is unavailable.";
    case "checking":
    default:
      return "Startup truth is still being established for the current chamber session.";
  }
}

function buildBottomStatusBadges(
  startupTruthState: BridgeStartupState,
  runtimeTruth: RuntimeStatusEnvelope["data"] | null | undefined,
  invokerTruth: InvokerStatusEnvelope["data"] | null | undefined
): TrustBadge[] {
  const stayedLocal = runtimeTruth?.stayed_local ?? invokerTruth?.stayed_local;
  const approvalNeeded = runtimeTruth?.approval_needed || invokerTruth?.approval_needed;
  const usedFallback = runtimeTruth?.used_fallback || invokerTruth?.used_fallback;

  switch (startupTruthState) {
    case "ok":
      return [
        stayedLocal === false
          ? { label: "External used", tone: "external" as const }
          : stayedLocal === true
            ? { label: "Local", tone: "local" as const }
            : { label: "Local default", tone: "local" as const },
        ...(approvalNeeded
          ? [{ label: "Approval needed", tone: "blocked" as const }]
          : []),
        ...(usedFallback
          ? [{ label: "Fallback used", tone: "degraded" as const }]
          : []),
        stayedLocal === false
          ? { label: "Boundary surfaced", tone: "external" as const }
          : { label: "External sealed", tone: "external" as const }
      ];
    case "degraded":
      return [
        { label: "Local", tone: "local" },
        { label: "Degraded", tone: "degraded" },
        { label: "External sealed", tone: "external" }
      ];
    case "unavailable":
    case "error":
      return [
        { label: "Unavailable", tone: "blocked" },
        { label: "External sealed", tone: "external" }
      ];
    case "checking":
    default:
      return [
        { label: "Checking", tone: "inactive" },
        { label: "External sealed", tone: "external" }
      ];
  }
}

export default function AppShell({ accountState = null }: { accountState?: AccountStateData | null }) {
  const showAdmin = accountState?.active_role === "installation_owner" || accountState?.active_role === "admin";
  const [desktopPreferences, setDesktopPreferences] =
    useState<DesktopPreferences>(readDesktopPreferences);
  const [activeRoom, setActiveRoom] = useState<AppRoom>(
    () => desktopPreferences.startupRoom
  );
  const [lastRailRoom, setLastRailRoom] = useState<LeftRailRoom>(
    () => desktopPreferences.startupRoom
  );
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [conversationToOpenId, setConversationToOpenId] = useState<string | null>(null);
  const [rightDrawerSections, setRightDrawerSections] =
    useState<DrawerSection[]>(() => buildIdleDrawerSections("home", "checking"));

  const {
    startupTruthState,
    startupTruthMessage,
    startupTruthDetail,
    startupReady,
    bridgeApiVersion,
    bridgeContractVersion,
    runtimeContractVersion,
    capabilityContractVersion,
    runtimeTruth = null,
    invokerTruth = null
  } = useStartupTruth();

  const isStatusMenu = activeRoom === "status_menu";
  const leftRailActiveRoom: LeftRailRoom =
    activeRoom === "project_detail"
      ? "projects"
      : activeRoom === "status_menu"
        ? lastRailRoom
        : activeRoom;

  const currentStatusMenuState = mapStartupTruthToSurfaceState(startupTruthState);

  useEffect(() => {
    if (activeRoom === "home" || activeRoom === "user_profile" || activeRoom === "addons") {
      setRightDrawerSections(
        buildIdleDrawerSections(
          activeRoom === "user_profile"
            ? "user_profile"
            : activeRoom === "addons"
              ? "addons"
              : "home",
          startupTruthState
        )
      );
      return;
    }

    if (activeRoom === "status_menu") {
      setRightDrawerSections(buildIdleDrawerSections("status_menu", startupTruthState));
    }
  }, [activeRoom, startupTruthState]);

  const bottomStatusSummaryText = useMemo(
    () => buildBottomStatusSummaryText(activeRoom, startupTruthState, runtimeTruth, invokerTruth),
    [activeRoom, invokerTruth, runtimeTruth, startupTruthState]
  );

  const bottomStatusBadges = useMemo(
    () => buildBottomStatusBadges(startupTruthState, runtimeTruth, invokerTruth),
    [invokerTruth, runtimeTruth, startupTruthState]
  );

  function handleSelectRoom(room: LeftRailRoom) {
    setActiveRoom(room);
    setLastRailRoom(room);
    setConversationToOpenId(null);

    if (room !== "projects") {
      setSelectedProjectId(null);
    }
  }

  function handleReturnToProjects() {
    setSelectedProjectId(null);
    setConversationToOpenId(null);
    setActiveRoom("projects");
    setLastRailRoom("projects");
  }

  async function handleOpenQuickInvoke(initialQuery = "") {
    try {
      const QUICK_INVOKE_WIDTH = 700;
      const QUICK_INVOKE_HEIGHT = 500;

      let quickInvokeX: number | null = null;
      let quickInvokeY: number | null = null;

      try {
        const SHELL_PADDING = 16;
        const SHELL_GAP = 16;
        const LEFT_RAIL_WIDTH = 260;
        const TOP_BAR_HEIGHT = 88;

        const CHAMBER_LEFT_INSET = 10;
        const CHAMBER_TOP_INSET = 14;

        const mainWindow = getCurrentWebviewWindow();
        const mainPosition = await mainWindow.outerPosition();

        quickInvokeX = Math.round(
          mainPosition.x
          + SHELL_PADDING
          + LEFT_RAIL_WIDTH
          + SHELL_GAP
          + CHAMBER_LEFT_INSET
        );

        quickInvokeY = Math.round(
          mainPosition.y
          + TOP_BAR_HEIGHT
          + SHELL_PADDING
          + CHAMBER_TOP_INSET
        );
      } catch (positionError) {
        console.warn(
          "[quickInvoke] parent-window positioning unavailable; falling back to default placement",
          positionError
        );
      }

      const existingWindow = await WebviewWindow.getByLabel("quick_invoke");
      if (existingWindow) {
        if (quickInvokeX !== null && quickInvokeY !== null) {
          try {
            await existingWindow.setPosition(
              new PhysicalPosition(quickInvokeX, quickInvokeY)
            );
          } catch (repositionError) {
            console.warn(
              "[quickInvoke] failed to reposition existing child window; continuing with show/focus",
              repositionError
            );
          }
        }

        await existingWindow.show();
        await existingWindow.setFocus();
        return;
      }

      const encodedInitialQuery = initialQuery.trim()
        ? `&initial_query=${encodeURIComponent(initialQuery)}`
        : "";

      const quickInvokeWindowOptions: ConstructorParameters<typeof WebviewWindow>[1] = {
        url: `/?window=quick_invoke${encodedInitialQuery}`,
        title: "Quick Invoke",
        width: QUICK_INVOKE_WIDTH,
        height: QUICK_INVOKE_HEIGHT,
        minWidth: 560,
        minHeight: 380,
        resizable: true,
        decorations: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        focus: true
      };

      if (quickInvokeX !== null && quickInvokeY !== null) {
        quickInvokeWindowOptions.x = quickInvokeX;
        quickInvokeWindowOptions.y = quickInvokeY;
      } else {
        quickInvokeWindowOptions.center = true;
      }

      const quickInvokeWindow = new WebviewWindow(
        "quick_invoke",
        quickInvokeWindowOptions
      );

      quickInvokeWindow.once("tauri://created", async () => {
        await quickInvokeWindow.show();
        await quickInvokeWindow.setFocus();
      });

      quickInvokeWindow.once("tauri://error", (event) => {
        console.error("[quickInvoke] failed to create child window", event);
      });
    } catch (error) {
      console.error("[quickInvoke] failed to open or focus child window", error);
    }
  }

  return (
    <div
      className={`elysia-app-shell elysia-density-${desktopPreferences.density} elysia-motion-${desktopPreferences.motionPreference}`}
      data-density={desktopPreferences.density}
      data-motion={desktopPreferences.motionPreference}
      style={{
        height: "100%",
        minHeight: 0,
        background:
          "radial-gradient(circle at 18% 12%, rgba(126, 215, 209, 0.08), transparent 18%), radial-gradient(circle at 84% 9%, rgba(138, 106, 60, 0.08), transparent 20%), linear-gradient(180deg, #111726 0%, #0B0E12 100%)",
        color: palette.silver,
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        overflow: "hidden"
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          opacity: 0.34,
          backgroundImage:
            "linear-gradient(90deg, rgba(126, 215, 209, 0.05) 0, rgba(126, 215, 209, 0.05) 1px, transparent 1px, transparent 120px), linear-gradient(180deg, rgba(138, 106, 60, 0.035) 0, rgba(138, 106, 60, 0.035) 1px, transparent 1px, transparent 120px)",
          backgroundSize: "120px 120px"
        }}
      />

      <div
        className="elysia-shell-grid"
        style={{
          position: "relative",
          display: "grid",
          gridTemplateRows: "88px minmax(0, 1fr) 46px",
          height: "100%",
          minHeight: 0
        }}
      >
        <TopBar
          onOpenRoom={handleSelectRoom}
          desktopPreferences={desktopPreferences}
          onDesktopPreferencesChange={setDesktopPreferences}
        />

        <main
          className="elysia-shell-main"
          style={{
            display: "grid",
            gridTemplateColumns:
              "clamp(210px, 16vw, 250px) minmax(0, 1fr) clamp(260px, 22vw, 340px)",
            gap: "clamp(0.75rem, 1vw, 1rem)",
            padding: "clamp(0.75rem, 1vw, 1rem)",
            alignItems: isStatusMenu ? "start" : "stretch",
            minHeight: 0,
            overflowX: "hidden",
            overflowY: isStatusMenu ? "auto" : "hidden"
          }}
        >
          <LeftRail
            activeRoom={leftRailActiveRoom}
            onSelectRoom={handleSelectRoom}
            defaultGroupBehavior={desktopPreferences.leftRailDefaultBehavior}
            showAdmin={showAdmin}
          />

          <section
            className="elysia-workspace-surface"
            style={{
              position: "relative",
              display: "grid",
              gridTemplateRows: "minmax(0, 1fr)",
              padding: "clamp(0.8rem, 1.2vw, 1.2rem)",
              borderRadius: "26px",
              border: `1px solid ${palette.lineSilver}`,
              background:
                "radial-gradient(circle at 16% 12%, rgba(126, 215, 209, 0.09), transparent 19%), radial-gradient(circle at 84% 18%, rgba(138, 106, 60, 0.08), transparent 18%), linear-gradient(180deg, rgba(18, 25, 37, 0.98) 0%, rgba(11, 14, 18, 0.98) 100%)",
              boxShadow:
                "inset 0 1px 0 rgba(255,255,255,0.03), 0 14px 38px rgba(0,0,0,0.24)",
              alignSelf: isStatusMenu ? "start" : "stretch",
              minWidth: 0,
              minHeight: 0,
              overflow: "hidden"
            }}
          >
            <div
              aria-hidden="true"
              style={{
                position: "absolute",
                inset: "1rem",
                borderRadius: "22px",
                pointerEvents: "none",
                border: `1px solid rgba(138, 106, 60, 0.08)`
              }}
            />

            <div
              className="elysia-workspace-viewport"
              style={{
                minWidth: 0,
                minHeight: 0,
                height: "100%",
                overflow: "hidden"
              }}
            >
              {activeRoom === "home" ? (
                <HomePage
                  startupTruthState={startupTruthState}
                  startupTruthMessage={startupTruthMessage}
                  startupTruthDetail={startupTruthDetail}
                  startupReady={startupReady}
                  bridgeApiVersion={bridgeApiVersion}
                  bridgeContractVersion={bridgeContractVersion}
                  runtimeContractVersion={runtimeContractVersion}
                  capabilityContractVersion={capabilityContractVersion}
                />
              ) : activeRoom === "conversations" ? (
                <ConversationsPage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                  onOpenProjects={handleReturnToProjects}
                  initialConversationId={conversationToOpenId}
                />
              ) : activeRoom === "project_detail" && selectedProjectId ? (
                <ProjectDetailPage
                  projectId={selectedProjectId}
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                  onBackToProjects={handleReturnToProjects}
                  onSelectConversation={(conversationId) => {
                    setConversationToOpenId(conversationId);
                    setSelectedProjectId(null);
                    setLastRailRoom("conversations");
                    setActiveRoom("conversations");
                  }}
                />
              ) : activeRoom === "projects" ? (
                <ProjectsPage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                  onOpenProject={(projectId) => {
                    setSelectedProjectId(projectId);
                    setLastRailRoom("projects");
                    setActiveRoom("project_detail");
                  }}
                />
              ) : activeRoom === "memory" ? (
                <MemoryPage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                />
              ) : activeRoom === "governance" ? (
                <GovernancePage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                />
              ) : activeRoom === "health" ? (
                <HealthPage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                />
              ) : activeRoom === "capabilities" ? (
                <CapabilitiesPage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                />
              ) : activeRoom === "requests" ? (
                <RequestsPage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                />
              ) : activeRoom === "artifacts" ? (
                <ArtifactsPage
                  startupReady={startupReady}
                  onRightDrawerSectionsChange={setRightDrawerSections}
                />
              ) : activeRoom === "addons" ? (
                <AddonsPage onOpenUserProfile={() => {
                  setLastRailRoom("user_profile");
                  setActiveRoom("user_profile");
                }} />
              ) : activeRoom === "user_profile" ? (
                <UserProfilePage />
              ) : activeRoom === "admin" && showAdmin ? (
                <AdminPage onRightDrawerSectionsChange={setRightDrawerSections} />
              ) : activeRoom === "status_menu" ? (
                <StatusMenuPage
                  startupTruthState={startupTruthState}
                  startupTruthMessage={startupTruthMessage}
                  startupTruthDetail={startupTruthDetail}
                  startupReady={startupReady}
                  bridgeApiVersion={bridgeApiVersion}
                  bridgeContractVersion={bridgeContractVersion}
                  runtimeContractVersion={runtimeContractVersion}
                  capabilityContractVersion={capabilityContractVersion}
                  localCoreState={currentStatusMenuState}
                  localCoreValue={
                    startupReady
                      ? "Local core verified for current chamber session."
                      : startupTruthMessage
                  }
                  approvalNeededState={
                    runtimeTruth?.approval_needed || invokerTruth?.approval_needed
                      ? "live"
                      : "inactive"
                  }
                  approvalNeededValue={
                    runtimeTruth?.approval_needed || invokerTruth?.approval_needed
                      ? "The latest runtime or invoker state requires approval."
                      : "No approval-needed state is surfaced by the latest runtime truth."
                  }
                  blockedPathsState={
                    runtimeTruth?.runtime_state === "blocked" || invokerTruth?.invoker_state === "blocked"
                      ? "blocked"
                      : "inactive"
                  }
                  blockedPathsValue={
                    runtimeTruth?.runtime_state === "blocked" || invokerTruth?.invoker_state === "blocked"
                      ? "The latest governed runtime path reports blocked."
                      : "No blocked path is surfaced by the latest runtime truth."
                  }
                  externalBoundaryState="live"
                  externalBoundaryValue={
                    runtimeTruth?.stayed_local === false || invokerTruth?.stayed_local === false
                      ? "The latest governed runtime reports an explicit external boundary crossing."
                      : runtimeTruth?.stayed_local === true || invokerTruth?.stayed_local === true
                        ? "The latest governed runtime stayed local."
                        : "Local-first law is live; no latest locality result is surfaced."
                  }
                  activeRoleState={runtimeTruth?.selected_role || invokerTruth?.selected_role ? "live" : "inactive"}
                  activeRoleValue={
                    runtimeTruth?.selected_role || invokerTruth?.selected_role
                      ? `Current or recent governed role: ${runtimeTruth?.selected_role ?? invokerTruth?.selected_role}.`
                      : "No current or recent request role is surfaced."
                  }
                  runtimeTagState={
                    runtimeTruth?.selected_model_runtime_tag || invokerTruth?.selected_model_runtime_tag || runtimeTruth?.selected_runtime || invokerTruth?.selected_runtime
                      ? "live"
                      : "inactive"
                  }
                  runtimeTagValue={
                    runtimeTruth?.selected_model_runtime_tag || invokerTruth?.selected_model_runtime_tag
                      ? `Current or recent model tag: ${runtimeTruth?.selected_model_runtime_tag ?? invokerTruth?.selected_model_runtime_tag}.`
                      : runtimeTruth?.selected_runtime || invokerTruth?.selected_runtime
                        ? `Current or recent runtime: ${runtimeTruth?.selected_runtime ?? invokerTruth?.selected_runtime}.`
                        : "No current or recent runtime/model tag is surfaced."
                  }
                  fallbackState={runtimeTruth?.used_fallback || invokerTruth?.used_fallback ? "degraded" : "inactive"}
                  fallbackValue={
                    runtimeTruth?.used_fallback || invokerTruth?.used_fallback
                      ? `Latest fallback: ${runtimeTruth?.fallback_from ?? invokerTruth?.fallback_from ?? "preferred runtime"} → ${runtimeTruth?.fallback_to ?? invokerTruth?.fallback_to ?? "fallback runtime"}.`
                      : "No fallback use is surfaced by the latest runtime truth."
                  }
                  sandboxState="planned"
                  sandboxValue="Local sandbox doctrine exists; no general sandbox is enabled until later profile and doctor proof."
                  outwardBoundaryState="live"
                  outwardBoundaryValue={
                    runtimeTruth?.stayed_local === false || invokerTruth?.stayed_local === false
                      ? "Latest runtime locality reports a surfaced boundary crossing."
                      : "Silent cloud fallback is prohibited; no outward action is enabled by this page."
                  }
                />
              ) : null}
            </div>
          </section>

          <div
            style={{
              display: "flex",
              minWidth: 0,
              minHeight: 0,
              height: isStatusMenu ? "auto" : "100%",
              overflow: "hidden",
              alignSelf: isStatusMenu ? "start" : "stretch"
            }}
          >
            <RightDrawer
              sections={rightDrawerSections}
              layoutMode={isStatusMenu ? "content" : "fill"}
              onOpenQuickInvoke={() => handleOpenQuickInvoke()}
            />
          </div>
        </main>

        <BottomStatusBar
          onOpenStatusMenu={() => setActiveRoom("status_menu")}
          statusSummaryText={bottomStatusSummaryText}
          statusBadges={bottomStatusBadges}
        />
        {accountState?.active_profile_managed && (
          <div role="status" style={{ position: "fixed", left: "50%", bottom: "3.2rem", transform: "translateX(-50%)", zIndex: 80, padding: "0.48rem 0.75rem", borderRadius: "999px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43,31,21,0.94)", color: palette.sandstone, fontSize: "0.72rem" }}>
            Managed local profile — visible supervision ceilings are active; your private content remains yours.
          </div>
        )}
      </div>
    </div>
  );
}

import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const startupTruthMock = vi.hoisted(() => ({
  startupTruthState: "ok" as const,
  startupTruthMessage: "Startup truth verified",
  startupTruthDetail:
    "API bridge healthy • Local runtime available • Governed invoker available • Capability manifest loaded",
  startupReady: true,
  bridgeApiVersion: "1.0.0",
  bridgeContractVersion: "bridge-contract-v1",
  runtimeContractVersion: "runtime-contract-v1",
  capabilityContractVersion: "capability-contract-v1",
  invokerContractVersion: "invoker-contract-v1",
  runtimeTruth: {
    runtime_state: "idle",
    stayed_local: true,
    used_fallback: false,
    approval_needed: false
  },
  invokerTruth: {
    invoker_state: "available",
    stayed_local: true,
    used_fallback: false,
    approval_needed: false
  }
}));

const drawerFixtures = vi.hoisted(() => ({
  conversations: [
    {
      key: "active_context",
      title: "Active Context",
      state: "live",
      rows: [
        { label: "Room", value: "Conversation room active" },
        { label: "Conversation", value: "Thread Alpha" }
      ]
    },
    {
      key: "memory_classes",
      title: "Memory Classes",
      state: "partial",
      rows: [
        { label: "Working", value: "Conversation working set live" },
        { label: "Project", value: "No project memory linked" }
      ]
    },
    {
      key: "current_project",
      title: "Current Project",
      state: "partial",
      rows: [
        { label: "Selection", value: "No current project selected" },
        { label: "Status", value: "Conversation-linked only" }
      ]
    },
    {
      key: "files_in_use",
      title: "Files in Use",
      state: "planned",
      rows: [
        { label: "Attachments", value: "No files attached" },
        { label: "Status", value: "File lane not yet live" }
      ]
    },
    {
      key: "plan_preview",
      title: "Plan Preview",
      state: "live",
      rows: [
        { label: "Phase", value: "Responding inside governed thread" },
        { label: "Latest step", value: "Trace running for conversation room" }
      ]
    },
    {
      key: "boundary_flags",
      title: "Boundary Flags",
      state: "blocked",
      rows: [
        { label: "Locality", value: "local" },
        { label: "Boundary", value: "blocked" }
      ]
    },
    {
      key: "approval_needed",
      title: "Approval Needed",
      state: "blocked",
      rows: [
        { label: "Current state", value: "Approval required" },
        { label: "Blocked state", value: "Approval required before continuation" }
      ]
    },
    {
      key: "journal_summary",
      title: "Journal Summary",
      state: "partial",
      rows: [
        { label: "Journaling", value: "Conversation turn completed" },
        { label: "Status", value: "Compact journal summary still maturing" }
      ]
    },
    {
      key: "request_trace",
      title: "Request Trace",
      state: "live",
      rows: [
        { label: "Current trace", value: "req_conversation_alpha" },
        { label: "Status", value: "Live room trace active" }
      ]
    }
  ],
  projects: [
    {
      key: "active_context",
      title: "Active Context",
      state: "live",
      rows: [
        { label: "Room", value: "Projects room active" },
        { label: "Surface", value: "Project index" }
      ]
    },
    {
      key: "memory_classes",
      title: "Memory Classes",
      state: "partial",
      rows: [
        { label: "Project", value: "Project memory summary visible" },
        { label: "Sealed private", value: "Not touched in current room state" }
      ]
    },
    {
      key: "current_project",
      title: "Current Project",
      state: "live",
      rows: [
        { label: "Selection", value: "Project Cedar" },
        { label: "Project count", value: "3 visible projects" }
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
      state: "partial",
      rows: [
        { label: "Current step", value: "Project list and create flow are live" },
        { label: "Next step", value: "Open project detail room" }
      ]
    },
    {
      key: "boundary_flags",
      title: "Boundary Flags",
      state: "live",
      rows: [
        { label: "Locality", value: "local" },
        { label: "Boundary", value: "clear" }
      ]
    },
    {
      key: "approval_needed",
      title: "Approval Needed",
      state: "live",
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
        { label: "Journaling", value: "Projects room visible" },
        { label: "Idle state", value: "No additional project action is in progress" }
      ]
    },
    {
      key: "request_trace",
      title: "Request Trace",
      state: "live",
      rows: [
        { label: "Current trace", value: "No active request trace" },
        { label: "Status", value: "Projects index is idle" }
      ]
    }
  ],
  projectDetail: [
    {
      key: "active_context",
      title: "Active Context",
      state: "live",
      rows: [
        { label: "Room", value: "Project detail room active" },
        { label: "Project", value: "Project Cedar" }
      ]
    },
    {
      key: "memory_classes",
      title: "Memory Classes",
      state: "partial",
      rows: [
        { label: "Conversation", value: "Selected project conversation visible" },
        { label: "Project", value: "Project Cedar continuity loaded" }
      ]
    },
    {
      key: "current_project",
      title: "Current Project",
      state: "degraded",
      rows: [
        { label: "Selection", value: "Project Cedar" },
        { label: "Status", value: "detail unavailable" }
      ]
    },
    {
      key: "files_in_use",
      title: "Files in Use",
      state: "partial",
      rows: [
        { label: "Sources", value: "2 sources attached" },
        { label: "Status", value: "Sources partially surfaced" }
      ]
    },
    {
      key: "plan_preview",
      title: "Plan Preview",
      state: "degraded",
      rows: [
        { label: "Current step", value: "Project detail mounted from bridge-backed truth" },
        { label: "Next step", value: "Wire project-scoped governed send" }
      ]
    },
    {
      key: "boundary_flags",
      title: "Boundary Flags",
      state: "degraded",
      rows: [
        { label: "Locality", value: "local" },
        { label: "Boundary", value: "degraded" }
      ]
    },
    {
      key: "approval_needed",
      title: "Approval Needed",
      state: "live",
      rows: [
        { label: "Current state", value: "No approval required" },
        { label: "Blocked state", value: "No project-level approval gate active" }
      ]
    },
    {
      key: "journal_summary",
      title: "Journal Summary",
      state: "partial",
      rows: [
        { label: "Notes summary", value: "Project notes summary visible" },
        { label: "State summary", value: "Project state summary visible" }
      ]
    },
    {
      key: "request_trace",
      title: "Request Trace",
      state: "degraded",
      rows: [
        { label: "Current trace", value: "No active trace" },
        { label: "Detail", value: "Project detail load failed" }
      ]
    }
  ]
}));

vi.mock("../src/AccountGate", () => ({
  useAccountSession: () => ({
    state: null,
    colors: [],
    refreshAccountState: vi.fn(),
    logout: vi.fn()
  })
}));

vi.mock("../src/hooks/useStartupTruth", () => ({
  useStartupTruth: () => startupTruthMock
}));

vi.mock("@tauri-apps/api/dpi", () => ({
  PhysicalPosition: class PhysicalPosition {
    x: number;

    y: number;

    constructor(x: number, y: number) {
      this.x = x;
      this.y = y;
    }
  }
}));

vi.mock("@tauri-apps/api/webviewWindow", () => ({
  WebviewWindow: class WebviewWindow {
    static async getByLabel() {
      return null;
    }

    constructor(_label: string, _options: unknown) {}

    once(_eventName: string, _handler: unknown) {}

    async show() {}

    async setFocus() {}

    async setPosition(_position: unknown) {}
  },
  getCurrentWebviewWindow: () => ({
    label: "main",
    outerPosition: async () => ({ x: 0, y: 0 })
  })
}));

vi.mock("../src/ElysiaPortraitCard", () => ({
  default: ({
    title = "Elysia",
    subtitle = "Present in chamber",
    onOpenQuickInvoke
  }: {
    sticky?: boolean;
    title?: string;
    subtitle?: string;
    onOpenQuickInvoke?: () => void;
  }) =>
    React.createElement(
      "section",
      {
        "data-testid": "elysia-portrait-card",
        "aria-label": "Elysia portrait"
      },
      React.createElement("div", null, "Portrait"),
      React.createElement("div", null, title),
      React.createElement("div", null, subtitle),
      onOpenQuickInvoke
        ? React.createElement(
            "button",
            {
              type: "button",
              onClick: onOpenQuickInvoke
            },
            "Quick Invoke"
          )
        : null
    )
}));

vi.mock("../src/TopBar", () => ({
  default: () => React.createElement("div", { "data-testid": "top-bar" }, "Top bar")
}));

vi.mock("../src/LeftRail", () => ({
  default: ({
    activeRoom,
    onSelectRoom
  }: {
    activeRoom: string;
    onSelectRoom: (room: string) => void;
  }) =>
    React.createElement(
      "div",
      { "data-testid": "left-rail" },
      React.createElement("div", null, `Active rail room: ${activeRoom}`),
      React.createElement(
        "button",
        { type: "button", onClick: () => onSelectRoom("home") },
        "Go Home"
      ),
      React.createElement(
        "button",
        { type: "button", onClick: () => onSelectRoom("conversations") },
        "Go Conversations"
      ),
      React.createElement(
        "button",
        { type: "button", onClick: () => onSelectRoom("projects") },
        "Go Projects"
      )
    )
}));

vi.mock("../src/ConversationsPage", () => ({
  default: ({
    onRightDrawerSectionsChange,
    initialConversationId
  }: {
    startupReady: boolean;
    onRightDrawerSectionsChange: (sections: unknown[]) => void;
    initialConversationId?: string | null;
  }) => {
    React.useEffect(() => {
      onRightDrawerSectionsChange(drawerFixtures.conversations);
    }, [onRightDrawerSectionsChange]);

    return React.createElement(
      "div",
      { "data-testid": "conversations-page" },
      `Conversations page${initialConversationId ? ` · ${initialConversationId}` : ""}`
    );
  }
}));

vi.mock("../src/ProjectsPage", () => ({
  default: ({
    onRightDrawerSectionsChange,
    onOpenProject
  }: {
    startupReady: boolean;
    onRightDrawerSectionsChange: (sections: unknown[]) => void;
    onOpenProject?: (projectId: string) => void;
  }) => {
    React.useEffect(() => {
      onRightDrawerSectionsChange(drawerFixtures.projects);
    }, [onRightDrawerSectionsChange]);

    return React.createElement(
      "div",
      { "data-testid": "projects-page" },
      React.createElement("div", null, "Projects page"),
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => onOpenProject?.("project_cedar")
        },
        "Open project detail"
      )
    );
  }
}));

vi.mock("../src/ProjectDetailPage", () => ({
  default: ({
    onRightDrawerSectionsChange,
    onSelectConversation
  }: {
    projectId: string;
    startupReady: boolean;
    onRightDrawerSectionsChange: (sections: unknown[]) => void;
    onBackToProjects?: () => void;
    onSelectConversation?: (conversationId: string) => void;
  }) => {
    React.useEffect(() => {
      onRightDrawerSectionsChange(drawerFixtures.projectDetail);
    }, [onRightDrawerSectionsChange]);

    return React.createElement(
      "div",
      { "data-testid": "project-detail-page" },
      React.createElement("div", null, "Project detail page"),
      React.createElement(
        "button",
        { type: "button", onClick: () => onSelectConversation?.("conv_project") },
        "Open linked conversation"
      )
    );
  }
}));

vi.mock("../src/MemoryPage", () => ({
  default: () =>
    React.createElement("div", { "data-testid": "memory-page" }, "Memory page")
}));

vi.mock("../src/GovernancePage", () => ({
  default: () =>
    React.createElement(
      "div",
      { "data-testid": "governance-page" },
      "Governance page"
    )
}));

import AppShell from "../src/AppShell";
import RightDrawer, {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "../src/RightDrawer";

function resetStartupTruthMock() {
  Object.assign(startupTruthMock, {
    startupTruthState: "ok" as const,
    startupTruthMessage: "Startup truth verified",
    startupTruthDetail:
      "API bridge healthy • Local runtime available • Governed invoker available • Capability manifest loaded",
    startupReady: true,
    bridgeApiVersion: "1.0.0",
    bridgeContractVersion: "bridge-contract-v1",
    runtimeContractVersion: "runtime-contract-v1",
    capabilityContractVersion: "capability-contract-v1",
    invokerContractVersion: "invoker-contract-v1",
    runtimeTruth: {
      runtime_state: "idle",
      stayed_local: true,
      used_fallback: false,
      approval_needed: false
    },
    invokerTruth: {
      invoker_state: "available",
      stayed_local: true,
      used_fallback: false,
      approval_needed: false
    }
  });
}

function renderDrawer(
  overrides: Partial<React.ComponentProps<typeof RightDrawer>> = {}
) {
  const props: React.ComponentProps<typeof RightDrawer> = {
    sections: DEFAULT_RIGHT_DRAWER_SECTIONS,
    layoutMode: "fill",
    onOpenQuickInvoke: vi.fn(),
    ...overrides
  };

  return {
    ...render(React.createElement(RightDrawer, props)),
    onOpenQuickInvoke: props.onOpenQuickInvoke
  };
}

function expectTextOrder(containerText: string, orderedTexts: string[]) {
  let previousIndex = -1;

  for (const text of orderedTexts) {
    const index = containerText.indexOf(text);
    expect(index).toBeGreaterThan(previousIndex);
    previousIndex = index;
  }
}

describe("RightDrawer standalone structural truth", () => {
  beforeEach(() => {
    resetStartupTruthMock();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the portrait first and preserves the canonical default section order", () => {
    const { container } = renderDrawer();

    expect(screen.getByTestId("elysia-portrait-card")).toBeInTheDocument();
    expect(screen.getByText("Portrait")).toBeInTheDocument();
    expect(screen.getByText("Elysia")).toBeInTheDocument();
    expect(screen.getByText("Present in chamber")).toBeInTheDocument();

    const drawerText = container.textContent ?? "";

    expectTextOrder(drawerText, [
      "Portrait",
      "Active Context",
      "Boundary Flags",
      "Approval Needed",
      "Request Trace"
    ]);

    expect(screen.queryByText("Memory Classes")).not.toBeInTheDocument();
    expect(screen.queryByText("Files in Use")).not.toBeInTheDocument();
    expect(screen.queryByText("Plan Preview")).not.toBeInTheDocument();
  });

  it("renders mixed default section maturity honestly instead of flattening everything to live", () => {
    renderDrawer();

    expect(screen.getAllByText("partial").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("live").length).toBeGreaterThanOrEqual(1);

    expect(screen.getByText("No approval required")).toBeInTheDocument();
    expect(screen.getByText("No active trace")).toBeInTheDocument();
  });

  it("collapses planned detail by default while keeping current truth expanded", () => {
    const sections: DrawerSection[] = [
      {
        key: "current",
        title: "Current truth",
        state: "live",
        rows: [{ label: "State", value: "Current value" }]
      },
      {
        key: "future",
        title: "Future truth",
        state: "planned",
        rows: [{ label: "State", value: "Planned value" }]
      }
    ];

    const { container } = renderDrawer({ sections });
    const current = container.querySelector('details[data-drawer-state="live"]');
    const planned = container.querySelector('details[data-drawer-state="planned"]');

    expect(current).toHaveAttribute("open");
    expect(planned).not.toHaveAttribute("open");
  });

  it("passes Quick Invoke through the portrait surface", () => {
    const onOpenQuickInvoke = vi.fn();
    renderDrawer({ onOpenQuickInvoke });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Quick Invoke"
      })
    );

    expect(onOpenQuickInvoke).toHaveBeenCalledTimes(1);
  });

  it("supports custom section truth including inactive, unavailable, degraded, and blocked states", () => {
    const customSections: DrawerSection[] = [
      {
        key: "active_context",
        title: "Active Context",
        state: "inactive",
        rows: [{ label: "Room", value: "No active room truth yet" }]
      },
      {
        key: "memory_classes",
        title: "Memory Classes",
        state: "unavailable",
        rows: [{ label: "Status", value: "Memory summary unavailable" }]
      },
      {
        key: "current_project",
        title: "Current Project",
        state: "degraded",
        rows: [{ label: "Status", value: "Project linkage degraded" }]
      },
      {
        key: "files_in_use",
        title: "Files in Use",
        state: "blocked",
        rows: [{ label: "Status", value: "Attachment lane blocked" }]
      }
    ];

    renderDrawer({ sections: customSections });

    expect(screen.getByText("inactive")).toBeInTheDocument();
    expect(screen.getByText("unavailable")).toBeInTheDocument();
    expect(screen.getByText("degraded")).toBeInTheDocument();
    expect(screen.getByText("blocked")).toBeInTheDocument();

    expect(screen.getByText("No active room truth yet")).toBeInTheDocument();
    expect(screen.getByText("Memory summary unavailable")).toBeInTheDocument();
    expect(screen.getByText("Project linkage degraded")).toBeInTheDocument();
    expect(screen.getByText("Attachment lane blocked")).toBeInTheDocument();
  });
});

describe("RightDrawer shell-fed truth", () => {
  beforeEach(() => {
    resetStartupTruthMock();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("starts with default drawer truth inside AppShell", () => {
    render(React.createElement(AppShell));

    expect(
      screen.getByText("No active working mode is surfaced in idle chamber state")
    ).toBeInTheDocument();
    expect(screen.getByText("No approval required")).toBeInTheDocument();
    expect(screen.getByText("No active trace")).toBeInTheDocument();
    expect(screen.queryByText("No active project selected")).not.toBeInTheDocument();
    expect(screen.queryByText("Drawer file feed not yet live")).not.toBeInTheDocument();
  });

  it("switches from default drawer truth to room-fed conversation truth", () => {
    render(React.createElement(AppShell));

    fireEvent.click(
      screen.getByRole("button", {
        name: "Go Conversations"
      })
    );

    expect(screen.getByTestId("conversations-page")).toBeInTheDocument();
    expect(screen.getByText("Conversation room active")).toBeInTheDocument();
    expect(screen.getByText("Thread Alpha")).toBeInTheDocument();
    expect(screen.getByText("Trace running for conversation room")).toBeInTheDocument();

    expect(
      screen.queryByText("No active working mode is surfaced in idle chamber state")
    ).not.toBeInTheDocument();
  });

  it("switches from project index truth to project-detail truth without breaking drawer structure", () => {
    render(React.createElement(AppShell));

    fireEvent.click(
      screen.getByRole("button", {
        name: "Go Projects"
      })
    );

    expect(screen.getByTestId("projects-page")).toBeInTheDocument();
    expect(screen.getByText("Projects room active")).toBeInTheDocument();
    expect(screen.getByText("3 visible projects")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Open project detail"
      })
    );

    expect(screen.getByTestId("project-detail-page")).toBeInTheDocument();
    expect(screen.getByText("Project detail room active")).toBeInTheDocument();
    expect(screen.getByText("2 sources attached")).toBeInTheDocument();
    expect(screen.getByText("Project detail load failed")).toBeInTheDocument();

    expect(screen.getByText("Active Context")).toBeInTheDocument();
    expect(screen.getByText("Memory Classes")).toBeInTheDocument();
    expect(screen.getByText("Current Project")).toBeInTheDocument();
    expect(screen.getByText("Files in Use")).toBeInTheDocument();
    expect(screen.getByText("Plan Preview")).toBeInTheDocument();
    expect(screen.getByText("Boundary Flags")).toBeInTheDocument();
    expect(screen.getByText("Approval Needed")).toBeInTheDocument();
    expect(screen.getByText("Journal Summary")).toBeInTheDocument();
    expect(screen.getByText("Request Trace")).toBeInTheDocument();
  });

  it("opens a linked project conversation in the real conversations room", () => {
    render(React.createElement(AppShell));

    fireEvent.click(screen.getByRole("button", { name: "Go Projects" }));
    fireEvent.click(screen.getByRole("button", { name: "Open project detail" }));
    fireEvent.click(screen.getByRole("button", { name: "Open linked conversation" }));

    expect(screen.getByTestId("conversations-page")).toHaveTextContent(
      "Conversations page · conv_project"
    );
  });

  it("uses content layout for Status Menu while preserving portrait and section visibility", () => {
    const { container } = render(React.createElement(AppShell));
    const initialDrawerAside = container.querySelector("aside");

    expect(initialDrawerAside).not.toBeNull();
    expect(initialDrawerAside?.style.height).toBe("100%");

    fireEvent.click(
      screen.getByRole("button", {
        name: /status menu/i
      })
    );

    const contentModeDrawerAside = container.querySelector("aside");
    expect(contentModeDrawerAside).not.toBeNull();
    expect(contentModeDrawerAside?.style.height).toBe("auto");

    expect(screen.getByTestId("elysia-portrait-card")).toBeInTheDocument();
    expect(screen.getByText("Active Context")).toBeInTheDocument();
    expect(
      screen.getByText("Expanded trust surfaces for the current chamber state.")
    ).toBeInTheDocument();
  });
});

import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  within
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BridgeStartupState } from "../src/api/bridgeClient";
import AppShell from "../src/AppShell";
import HomePage from "../src/HomePage";
import StatusMenuPage from "../src/StatusMenuPage";
import { useStartupTruth } from "../src/hooks/useStartupTruth";

type BridgeHealthMock = {
  bridgeStartupState: BridgeStartupState;
  bridgeStatusMessage: string;
  bridgeStatusDetail: string;
  bridgeApiVersion: string;
  bridgeContractVersion: string;
};

type RuntimeStatusMock = {
  runtimeStartupState: BridgeStartupState;
  runtimeStatusMessage: string;
  runtimeStatusDetail: string;
  runtimeContractVersion: string;
  runtimeStateLabel: string;
  runtimeTruth: Record<string, unknown> | null;
};

type InvokerStatusMock = {
  invokerStartupState: BridgeStartupState;
  invokerStatusMessage: string;
  invokerStatusDetail: string;
  invokerContractVersion: string;
  invokerStateLabel: string;
  invokerTruth: Record<string, unknown> | null;
};

type CapabilityManifestMock = {
  capabilityStartupState: BridgeStartupState;
  capabilityStatusMessage: string;
  capabilityStatusDetail: string;
  capabilityContractVersion: string;
};

const startupHookMocks = vi.hoisted(() => ({
  bridge: {
    bridgeStartupState: "ok" as BridgeStartupState,
    bridgeStatusMessage: "API bridge healthy",
    bridgeStatusDetail: "Bridge detail",
    bridgeApiVersion: "1.0.0",
    bridgeContractVersion: "bridge-contract-v1"
  },
  runtime: {
    runtimeStartupState: "ok" as BridgeStartupState,
    runtimeStatusMessage: "Local runtime available",
    runtimeStatusDetail: "Runtime detail",
    runtimeContractVersion: "runtime-contract-v1",
    runtimeStateLabel: "idle",
    runtimeTruth: {
      runtime_state: "idle",
      stayed_local: true,
      used_fallback: false,
      approval_needed: false
    }
  },
  invoker: {
    invokerStartupState: "ok" as BridgeStartupState,
    invokerStatusMessage: "Governed invoker available",
    invokerStatusDetail: "Invoker detail",
    invokerContractVersion: "invoker-contract-v1",
    invokerStateLabel: "idle",
    invokerTruth: {
      invoker_state: "available",
      stayed_local: true,
      used_fallback: false,
      approval_needed: false
    }
  },
  capability: {
    capabilityStartupState: "ok" as BridgeStartupState,
    capabilityStatusMessage: "Capability manifest loaded",
    capabilityStatusDetail: "Capability detail",
    capabilityContractVersion: "capability-contract-v1"
  }
}));

vi.mock("../src/hooks/useBridgeHealth", () => ({
  useBridgeHealth: () => startupHookMocks.bridge
}));

vi.mock("../src/hooks/useRuntimeStatus", () => ({
  useRuntimeStatus: () => startupHookMocks.runtime
}));

vi.mock("../src/hooks/useInvokerStatus", () => ({
  useInvokerStatus: () => startupHookMocks.invoker
}));

vi.mock("../src/hooks/useCapabilityManifest", () => ({
  useCapabilityManifest: () => startupHookMocks.capability
}));

vi.mock("../src/AccountGate", () => ({
  useAccountSession: () => ({
    state: null,
    colors: [],
    refreshAccountState: vi.fn(),
    logout: vi.fn()
  })
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

vi.mock("../src/LeftRail", () => ({
  default: () =>
    React.createElement("div", { "data-testid": "left-rail" }, "Left rail")
}));

vi.mock("../src/RightDrawer", () => ({
  DEFAULT_RIGHT_DRAWER_SECTIONS: [],
  default: () =>
    React.createElement("div", { "data-testid": "right-drawer" }, "Right drawer")
}));

vi.mock("../src/ConversationsPage", () => ({
  default: () =>
    React.createElement(
      "div",
      { "data-testid": "conversations-page" },
      "Conversations page"
    )
}));

vi.mock("../src/ProjectsPage", () => ({
  default: () =>
    React.createElement("div", { "data-testid": "projects-page" }, "Projects page")
}));

vi.mock("../src/ProjectDetailPage", () => ({
  default: () =>
    React.createElement(
      "div",
      { "data-testid": "project-detail-page" },
      "Project detail page"
    )
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

function resetStartupHookMocks() {
  Object.assign(startupHookMocks.bridge, {
    bridgeStartupState: "ok" as BridgeStartupState,
    bridgeStatusMessage: "API bridge healthy",
    bridgeStatusDetail: "Bridge detail",
    bridgeApiVersion: "1.0.0",
    bridgeContractVersion: "bridge-contract-v1"
  });

  Object.assign(startupHookMocks.runtime, {
    runtimeStartupState: "ok" as BridgeStartupState,
    runtimeStatusMessage: "Local runtime available",
    runtimeStatusDetail: "Runtime detail",
    runtimeContractVersion: "runtime-contract-v1",
    runtimeStateLabel: "idle",
    runtimeTruth: {
      runtime_state: "idle",
      stayed_local: true,
      used_fallback: false,
      approval_needed: false
    }
  });

  Object.assign(startupHookMocks.invoker, {
    invokerStartupState: "ok" as BridgeStartupState,
    invokerStatusMessage: "Governed invoker available",
    invokerStatusDetail: "Invoker detail",
    invokerContractVersion: "invoker-contract-v1",
    invokerStateLabel: "idle",
    invokerTruth: {
      invoker_state: "available",
      stayed_local: true,
      used_fallback: false,
      approval_needed: false
    }
  });

  Object.assign(startupHookMocks.capability, {
    capabilityStartupState: "ok" as BridgeStartupState,
    capabilityStatusMessage: "Capability manifest loaded",
    capabilityStatusDetail: "Capability detail",
    capabilityContractVersion: "capability-contract-v1"
  });
}

function getStartupTruthCard(): HTMLElement {
  const label = screen.getByText("Startup truth");
  let current: HTMLElement | null = label as HTMLElement;

  while (current && current.getAttribute("aria-live") !== "polite") {
    current = current.parentElement;
  }

  if (!current) {
    throw new Error("Startup truth card was not found.");
  }

  return current;
}

function renderHomePage(
  overrides: Partial<React.ComponentProps<typeof HomePage>> = {}
) {
  const props: React.ComponentProps<typeof HomePage> = {
    startupTruthState: "ok",
    startupTruthMessage: "Startup truth verified",
    startupTruthDetail: "Bridge healthy • Runtime available • Invoker available • Capability manifest loaded",
    startupReady: true,
    bridgeApiVersion: "1.0.0",
    bridgeContractVersion: "bridge-contract-v1",
    runtimeContractVersion: "runtime-contract-v1",
    capabilityContractVersion: "capability-contract-v1",
    ...overrides
  };

  render(React.createElement(HomePage, props));
}

function renderStatusMenuPage(
  startupTruthState: BridgeStartupState,
  overrides: Partial<React.ComponentProps<typeof StatusMenuPage>> = {}
) {
  const props: React.ComponentProps<typeof StatusMenuPage> = {
    startupTruthState,
    startupTruthMessage: `Startup state ${startupTruthState}`,
    startupTruthDetail: `Detail for ${startupTruthState}`,
    startupReady: startupTruthState === "ok",
    bridgeApiVersion: "1.0.0",
    bridgeContractVersion: "bridge-contract-v1",
    runtimeContractVersion: "runtime-contract-v1",
    capabilityContractVersion: "capability-contract-v1",
    localCoreState: "planned",
    localCoreValue: "Local core placeholder",
    approvalNeededState: "planned",
    approvalNeededValue: "Approval placeholder",
    blockedPathsState: "planned",
    blockedPathsValue: "Blocked placeholder",
    externalBoundaryState: "planned",
    externalBoundaryValue: "External placeholder",
    activeRoleState: "planned",
    activeRoleValue: "Role placeholder",
    runtimeTagState: "planned",
    runtimeTagValue: "Runtime placeholder",
    fallbackState: "planned",
    fallbackValue: "Fallback placeholder",
    memoryState: "planned",
    memoryValue: "Memory placeholder",
    sandboxState: "planned",
    sandboxValue: "Sandbox placeholder",
    outwardBoundaryState: "planned",
    outwardBoundaryValue: "Outward placeholder",
    ...overrides
  };

  render(React.createElement(StatusMenuPage, props));
}

describe("useStartupTruth", () => {
  beforeEach(() => {
    resetStartupHookMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("returns verified startup truth and strict readiness only when all startup surfaces are ok", () => {
    const { result } = renderHook(() => useStartupTruth());

    expect(result.current.startupTruthState).toBe("ok");
    expect(result.current.startupTruthMessage).toBe("Startup truth verified");
    expect(result.current.startupTruthDetail).toBe(
      "API bridge healthy • Local runtime available • Governed invoker available • Capability manifest loaded"
    );
    expect(result.current.startupReady).toBe(true);

    expect(result.current.bridgeApiVersion).toBe("1.0.0");
    expect(result.current.bridgeContractVersion).toBe("bridge-contract-v1");
    expect(result.current.runtimeContractVersion).toBe("runtime-contract-v1");
    expect(result.current.invokerContractVersion).toBe("invoker-contract-v1");
    expect(result.current.capabilityContractVersion).toBe(
      "capability-contract-v1"
    );
    expect(result.current.runtimeTruth).toEqual(startupHookMocks.runtime.runtimeTruth);
    expect(result.current.invokerTruth).toEqual(startupHookMocks.invoker.invokerTruth);
  });

  it("keeps startup in checking when no worse startup state is present", () => {
    startupHookMocks.bridge.bridgeStartupState = "checking";

    const { result } = renderHook(() => useStartupTruth());

    expect(result.current.startupTruthState).toBe("checking");
    expect(result.current.startupTruthMessage).toBe("Checking startup truth...");
    expect(result.current.startupReady).toBe(false);
  });

  it("prioritizes degraded over checking", () => {
    startupHookMocks.bridge.bridgeStartupState = "checking";
    startupHookMocks.runtime.runtimeStartupState = "degraded";

    const { result } = renderHook(() => useStartupTruth());

    expect(result.current.startupTruthState).toBe("degraded");
    expect(result.current.startupTruthMessage).toBe(
      "Startup truth loaded with degraded surfaces"
    );
    expect(result.current.startupReady).toBe(false);
  });

  it("prioritizes unavailable over degraded", () => {
    startupHookMocks.bridge.bridgeStartupState = "degraded";
    startupHookMocks.capability.capabilityStartupState = "unavailable";

    const { result } = renderHook(() => useStartupTruth());

    expect(result.current.startupTruthState).toBe("unavailable");
    expect(result.current.startupTruthMessage).toBe(
      "Startup truth incomplete: required surfaces unavailable"
    );
    expect(result.current.startupReady).toBe(false);
  });

  it("prioritizes error over unavailable", () => {
    startupHookMocks.runtime.runtimeStartupState = "unavailable";
    startupHookMocks.invoker.invokerStartupState = "error";

    const { result } = renderHook(() => useStartupTruth());

    expect(result.current.startupTruthState).toBe("error");
    expect(result.current.startupTruthMessage).toBe("Startup truth query failed");
    expect(result.current.startupReady).toBe(false);
  });

  it("joins startup surface messages in bridge, runtime, invoker, capability order", () => {
    startupHookMocks.bridge.bridgeStatusMessage = "Bridge first";
    startupHookMocks.runtime.runtimeStatusMessage = "Runtime second";
    startupHookMocks.invoker.invokerStatusMessage = "Invoker third";
    startupHookMocks.capability.capabilityStatusMessage = "Capability fourth";

    const { result } = renderHook(() => useStartupTruth());

    expect(result.current.startupTruthDetail).toBe(
      "Bridge first • Runtime second • Invoker third • Capability fourth"
    );
  });

  it("allows an approval-bound invoker to remain startup-ok when all startup surfaces are otherwise ok", () => {
    startupHookMocks.invoker.invokerStartupState = "ok";
    startupHookMocks.invoker.invokerStatusMessage =
      "Governed invoker available but approval-bound";

    const { result } = renderHook(() => useStartupTruth());

    expect(result.current.startupTruthState).toBe("ok");
    expect(result.current.startupReady).toBe(true);
    expect(result.current.startupTruthDetail).toContain(
      "Governed invoker available but approval-bound"
    );
  });
});

describe("HomePage startup truth rendering", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders mapped startup truth, versions, and ready-state wording for an ok startup", () => {
    renderHomePage();

    expect(screen.getByTestId("home-page-scroll")).toHaveClass("elysia-room-scroll-at-narrow");
    const startupCard = within(getStartupTruthCard());

    expect(startupCard.getByText("Startup truth verified")).toBeInTheDocument();
    expect(
      startupCard.getByText(
        "Bridge healthy • Runtime available • Invoker available • Capability manifest loaded"
      )
    ).toBeInTheDocument();
    expect(startupCard.getByText("live")).toBeInTheDocument();

    expect(startupCard.getByText("API 1.0.0")).toBeInTheDocument();
    expect(
      startupCard.getByText("Bridge contract bridge-contract-v1")
    ).toBeInTheDocument();
    expect(
      startupCard.getByText("Runtime contract runtime-contract-v1")
    ).toBeInTheDocument();
    expect(
      startupCard.getByText("Capability contract capability-contract-v1")
    ).toBeInTheDocument();

    expect(startupCard.getByText("Not falsely waiting")).toBeInTheDocument();

    expect(
      screen.getByText(
        "The chamber is ready. Working rooms can now be entered honestly through the left rail."
      )
    ).toBeInTheDocument();
  });

  it("renders not-ready wording for a non-ok startup and omits absent version fields", () => {
    renderHomePage({
      startupTruthState: "degraded",
      startupTruthMessage: "Startup truth loaded with degraded surfaces",
      startupTruthDetail: "Bridge healthy • Runtime degraded • Invoker available • Capability manifest loaded",
      startupReady: false,
      bridgeApiVersion: "",
      bridgeContractVersion: "",
      runtimeContractVersion: "",
      capabilityContractVersion: ""
    });

    const startupCard = within(getStartupTruthCard());

    expect(
      startupCard.getByText("Startup truth loaded with degraded surfaces")
    ).toBeInTheDocument();
    expect(startupCard.getByText("degraded")).toBeInTheDocument();
    expect(
      startupCard.getByText("Not ready until truth is known")
    ).toBeInTheDocument();

    expect(screen.queryByText(/^API /)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/^Bridge contract /)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/^Runtime contract /)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/^Capability contract /)
    ).not.toBeInTheDocument();

    expect(
      screen.getByText(
        "The chamber is visible, but readiness is not yet confirmed. Enter working rooms with that truth kept explicit."
      )
    ).toBeInTheDocument();
  });
});

describe("StatusMenuPage startup truth rendering", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it.each([
    {
      startupTruthState: "ok" as BridgeStartupState,
      expectedMappedBadge: "live",
      expectedReadyText: "Not falsely waiting"
    },
    {
      startupTruthState: "checking" as BridgeStartupState,
      expectedMappedBadge: "partial",
      expectedReadyText: "Not ready until truth is known"
    },
    {
      startupTruthState: "degraded" as BridgeStartupState,
      expectedMappedBadge: "degraded",
      expectedReadyText: "Not ready until truth is known"
    },
    {
      startupTruthState: "unavailable" as BridgeStartupState,
      expectedMappedBadge: "unavailable",
      expectedReadyText: "Not ready until truth is known"
    },
    {
      startupTruthState: "error" as BridgeStartupState,
      expectedMappedBadge: "unavailable",
      expectedReadyText: "Not ready until truth is known"
    }
  ])(
    "maps startup truth state $startupTruthState into startup status badge $expectedMappedBadge",
    ({ startupTruthState, expectedMappedBadge, expectedReadyText }) => {
      renderStatusMenuPage(startupTruthState);

      const startupCard = within(getStartupTruthCard());

      expect(
        startupCard.getByText(`Startup state ${startupTruthState}`)
      ).toBeInTheDocument();
      expect(
        startupCard.getByText(`Detail for ${startupTruthState}`)
      ).toBeInTheDocument();
      expect(startupCard.getByText(expectedMappedBadge)).toBeInTheDocument();
      expect(startupCard.getByText(expectedReadyText)).toBeInTheDocument();

      if (startupTruthState !== expectedMappedBadge) {
        expect(
          startupCard.queryByText(startupTruthState, {
            selector: "span"
          })
        ).not.toBeInTheDocument();
      }
    }
  );
});

describe("AppShell startup truth wiring", () => {
  beforeEach(() => {
    resetStartupHookMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("passes startup truth into the Home page on initial render", () => {
    startupHookMocks.bridge.bridgeStatusMessage = "Bridge healthy";
    startupHookMocks.runtime.runtimeStatusMessage = "Runtime available";
    startupHookMocks.invoker.invokerStatusMessage = "Invoker available";
    startupHookMocks.capability.capabilityStatusMessage =
      "Capability manifest loaded";

    render(React.createElement(AppShell));

    expect(
      screen.getByText("The home page should open in stillness, not clutter.")
    ).toBeInTheDocument();
    expect(screen.getByText("Startup truth verified")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Bridge healthy • Runtime available • Invoker available • Capability manifest loaded"
      )
    ).toBeInTheDocument();
    expect(within(getStartupTruthCard()).getByText("live")).toBeInTheDocument();
  });

  it("preserves startup truth when opening the Status Menu from the shell", () => {
    startupHookMocks.bridge.bridgeStartupState = "degraded";
    startupHookMocks.bridge.bridgeStatusMessage = "API bridge reachable but degraded";
    startupHookMocks.runtime.runtimeStatusMessage = "Local runtime available";
    startupHookMocks.invoker.invokerStatusMessage = "Governed invoker available";
    startupHookMocks.capability.capabilityStatusMessage =
      "Capability manifest loaded";

    render(React.createElement(AppShell));

    fireEvent.click(
      screen.getByRole("button", {
        name: /status menu/i
      })
    );

    expect(
      screen.getByText("Expanded trust surfaces for the current chamber state.")
    ).toBeInTheDocument();
    const startupCard = within(getStartupTruthCard());
    expect(
      startupCard.getByText("Startup truth loaded with degraded surfaces")
    ).toBeInTheDocument();
    expect(startupCard.getByText("degraded")).toBeInTheDocument();
    expect(
      startupCard.getByText("Not ready until truth is known")
    ).toBeInTheDocument();
  });
});

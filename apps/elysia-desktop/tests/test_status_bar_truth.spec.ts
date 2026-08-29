import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppShell from "../src/AppShell";
import BottomStatusBar from "../src/BottomStatusBar";

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

vi.mock("../src/hooks/useStartupTruth", () => ({
  useStartupTruth: () => startupTruthMock
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

function renderBottomStatusBar(overrides?: {
  onOpenStatusMenu?: () => void;
}) {
  const onOpenStatusMenu = overrides?.onOpenStatusMenu ?? vi.fn();

  render(
    React.createElement(BottomStatusBar, {
      onOpenStatusMenu
    })
  );

  return { onOpenStatusMenu };
}

describe("BottomStatusBar current trust posture", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the compact trust-posture sentence, launcher, and fixed trust badges", () => {
    renderBottomStatusBar();

    expect(
      screen.getByText(
        "Current trust posture for this chamber session."
      )
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: /status menu/i
      })
    ).toBeInTheDocument();

    expect(screen.getByText("Status Menu")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Open trust center with chamber status & orientation surfaces"
      )
    ).toBeInTheDocument();

    expect(screen.getByText("Local")).toBeInTheDocument();
    expect(screen.getByText("External sealed")).toBeInTheDocument();
  });

  it("does not pretend to render live runtime-body fields that are not yet wired into the bar", () => {
    renderBottomStatusBar();

    expect(screen.queryByText(/Role active/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Runtime active/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Fallback used/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Memory status/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sandbox state/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Outward boundary/i)).not.toBeInTheDocument();
  });

  it("keeps badge language aligned with compact trust posture rather than decorative filler", () => {
    renderBottomStatusBar();

    expect(screen.getByText("Local")).toBeInTheDocument();
    expect(screen.getByText("External sealed")).toBeInTheDocument();
    expect(screen.queryByText("Approval needed")).not.toBeInTheDocument();
    expect(screen.queryByText("Blocked paths visible")).not.toBeInTheDocument();

    expect(screen.queryByText(/All systems go/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Fully autonomous/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Magic/i)).not.toBeInTheDocument();
  });
});

describe("BottomStatusBar interaction", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("calls onOpenStatusMenu when the Status Menu launcher is clicked", () => {
    const { onOpenStatusMenu } = renderBottomStatusBar({
      onOpenStatusMenu: vi.fn()
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: /status menu/i
      })
    );

    expect(onOpenStatusMenu).toHaveBeenCalledTimes(1);
  });
});

describe("AppShell integration with BottomStatusBar", () => {
  beforeEach(() => {
    resetStartupTruthMock();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the bottom status bar as a visible trust surface in the shell", () => {
    render(React.createElement(AppShell));

    expect(
      screen.getByText(
        "Current chamber session verified inside the local boundary."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /status menu/i
      })
    ).toBeInTheDocument();
  });

  it("opens the expanded Status Menu surface when the bottom-bar launcher is clicked", () => {
    render(React.createElement(AppShell));

    expect(
      screen.queryByText("Expanded trust surfaces for the current chamber state.")
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /status menu/i
      })
    );

    expect(
      screen.getByText("Expanded trust surfaces for the current chamber state.")
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "The bottom bar gives the short version. This page gives the expanded version: current trust posture, runtime condition, and the meaning of the chamber’s compact status language without bloating the shell."
      )
    ).toBeInTheDocument();

    expect(screen.getByText("Startup truth verified")).toBeInTheDocument();
  });

  it("keeps the bottom bar modest while delegating expanded runtime trust explanation to Status Menu", () => {
    render(React.createElement(AppShell));

    expect(screen.queryByText(/Role active/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Runtime active/i)).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /status menu/i
      })
    );

    expect(screen.getByText("Current / recent role")).toBeInTheDocument();
    expect(screen.getByText("Current / recent runtime")).toBeInTheDocument();
  });

  it("surfaces approval, fallback, and external use from current runtime truth", () => {
    startupTruthMock.runtimeTruth = {
      runtime_state: "waiting_approval",
      stayed_local: false,
      used_fallback: true,
      approval_needed: true
    };

    render(React.createElement(AppShell));

    expect(screen.getByText("External used")).toBeInTheDocument();
    expect(screen.getByText("Approval needed")).toBeInTheDocument();
    expect(screen.getByText("Fallback used")).toBeInTheDocument();
    expect(screen.getByText("Boundary surfaced")).toBeInTheDocument();
    expect(screen.queryByText("Local")).not.toBeInTheDocument();
  });
});

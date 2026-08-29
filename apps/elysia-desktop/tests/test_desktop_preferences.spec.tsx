import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AppShell from "../src/AppShell";
import {
  DEFAULT_DESKTOP_PREFERENCES,
  DESKTOP_PREFERENCES_STORAGE_KEY,
  normalizeDesktopPreferences,
  readDesktopPreferences,
  type DesktopPreferences
} from "../src/desktopPreferences";

const settingsTruthMocks = vi.hoisted(() => ({
  fetchBridgeHealth: vi.fn(),
  fetchRuntimeStatus: vi.fn(),
  fetchInvokerStatus: vi.fn(),
  fetchCapabilityManifest: vi.fn(),
  fetchInstallProfileStatus: vi.fn(),
  fetchGovernanceState: vi.fn(),
  fetchMemorySummary: vi.fn(),
  fetchMemorySettings: vi.fn().mockResolvedValue({
    ok: false,
    payload: { status: "unavailable", errors: ["Account settings are unavailable in this isolated test."] }
  }),
  updateMemorySettings: vi.fn()
}));

vi.mock("../src/api/bridgeClient", () => settingsTruthMocks);

vi.mock("../src/hooks/useStartupTruth", () => ({
  useStartupTruth: () => ({
    startupTruthState: "ok",
    startupTruthMessage: "Startup truth verified",
    startupTruthDetail: "Local startup truth is ready",
    startupReady: true,
    bridgeApiVersion: "1.0.0",
    bridgeContractVersion: "bridge-contract-v1",
    runtimeContractVersion: "runtime-contract-v1",
    capabilityContractVersion: "capability-contract-v1"
  })
}));

vi.mock("@tauri-apps/api/dpi", () => ({
  PhysicalPosition: class PhysicalPosition {
    constructor(
      public x: number,
      public y: number
    ) {}
  }
}));

vi.mock("@tauri-apps/api/webviewWindow", () => ({
  WebviewWindow: class WebviewWindow {
    static async getByLabel() {
      return null;
    }

    once() {}

    async show() {}

    async setFocus() {}

    async setPosition() {}
  },
  getCurrentWebviewWindow: () => ({
    label: "main",
    outerPosition: async () => ({ x: 0, y: 0 })
  })
}));

vi.mock("../src/RightDrawer", () => ({
  DEFAULT_RIGHT_DRAWER_SECTIONS: [],
  default: () => <div data-testid="right-drawer">Right drawer</div>
}));

vi.mock("../src/HomePage", () => ({
  default: () => <div data-testid="home-page">Chamber page</div>
}));

vi.mock("../src/ConversationsPage", () => ({
  default: () => <div data-testid="conversations-page">Conversations page</div>
}));

vi.mock("../src/ProjectsPage", () => ({
  default: ({ onOpenProject }: { onOpenProject: (projectId: string) => void }) => (
    <div data-testid="projects-page">
      Projects page
      <button type="button" onClick={() => onOpenProject("project-1")}>
        Open project detail
      </button>
    </div>
  )
}));

vi.mock("../src/ProjectDetailPage", () => ({
  default: () => <div data-testid="project-detail-page">Project detail page</div>
}));

vi.mock("../src/MemoryPage", () => ({
  default: () => <div data-testid="memory-page">Memory page</div>
}));

vi.mock("../src/GovernancePage", () => ({
  default: () => <div data-testid="governance-page">Governance page</div>
}));

vi.mock("../src/HealthPage", () => ({
  default: () => <div data-testid="health-page">Health page</div>
}));

vi.mock("../src/CapabilitiesPage", () => ({
  default: () => <div data-testid="capabilities-page">Capabilities page</div>
}));

vi.mock("../src/RequestsPage", () => ({
  default: () => <div data-testid="requests-page">Requests page</div>
}));

vi.mock("../src/ArtifactsPage", () => ({
  default: () => <div data-testid="artifacts-page">Artifacts page</div>
}));

vi.mock("../src/AddonsPage", () => ({
  default: () => <div data-testid="addons-page">Add-ons page</div>
}));

vi.mock("../src/UserProfilePage", () => ({
  default: () => <div data-testid="user-profile-page">Personal Identity page</div>
}));

vi.mock("../src/StatusMenuPage", () => ({
  default: () => <div data-testid="status-menu-page">Status Menu page</div>
}));

const okTruth = {
  ok: true,
  payload: {
    status: "ok",
    capability_state: "live",
    data: {}
  }
};

function resetSettingsTruthMocks() {
  Object.values(settingsTruthMocks).forEach((reader) => {
    reader.mockResolvedValue(okTruth);
  });
}

function storePreferences(value: DesktopPreferences | Record<string, unknown>) {
  window.localStorage.setItem(
    DESKTOP_PREFERENCES_STORAGE_KEY,
    JSON.stringify(value)
  );
}

function getShell(): HTMLElement {
  const shell = document.querySelector<HTMLElement>(".elysia-app-shell");

  if (!shell) {
    throw new Error("Elysia app shell was not rendered.");
  }

  return shell;
}

describe("desktop preference integration", () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetSettingsTruthMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("uses a valid saved startup room and keeps its active rail group open", () => {
    storePreferences({
      density: "compact",
      startupRoom: "memory",
      leftRailDefaultBehavior: "collapsed"
    });

    render(<AppShell />);

    expect(screen.getByTestId("memory-page")).toBeInTheDocument();
    expect(getShell()).toHaveAttribute("data-density", "compact");
    expect(getShell()).toHaveAttribute("data-motion", "system");
    expect(getShell()).toHaveClass("elysia-density-compact");
    expect(
      screen.getByRole("button", { name: "Memory & Identity" })
    ).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Memory" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(screen.getByRole("button", { name: "Workrooms" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });

  it("falls back to Chamber for an invalid saved startup room", () => {
    storePreferences({
      density: "compact",
      startupRoom: "not_a_room",
      leftRailDefaultBehavior: "expanded"
    });

    render(<AppShell />);

    expect(screen.getByTestId("home-page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chamber" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(getShell()).toHaveAttribute("data-density", "compact");
    expect(getShell()).toHaveAttribute("data-motion", "system");
  });

  it("falls back safely when the saved preference payload is malformed", () => {
    window.localStorage.setItem(
      DESKTOP_PREFERENCES_STORAGE_KEY,
      "not valid JSON"
    );

    expect(readDesktopPreferences()).toEqual(DEFAULT_DESKTOP_PREFERENCES);

    render(<AppShell />);

    expect(screen.getByTestId("home-page")).toBeInTheDocument();
    expect(getShell()).toHaveAttribute("data-density", "comfortable");
    expect(getShell()).toHaveAttribute("data-motion", "system");
    expect(screen.getByRole("button", { name: "Workrooms" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });

  it("keeps a changed startup room for the next mount without navigating now", () => {
    const firstMount = render(<AppShell />);

    expect(screen.getByTestId("home-page")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Startup room" }), {
      target: { value: "projects" }
    });

    expect(screen.getByTestId("home-page")).toBeInTheDocument();
    expect(screen.queryByTestId("projects-page")).not.toBeInTheDocument();

    firstMount.unmount();
    render(<AppShell />);

    expect(screen.getByTestId("projects-page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Projects" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("applies density immediately, persists it, and restores it on remount", () => {
    const firstMount = render(<AppShell />);

    expect(getShell()).toHaveAttribute("data-density", "comfortable");
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    fireEvent.change(screen.getByRole("combobox", { name: "UI density" }), {
      target: { value: "compact" }
    });

    expect(getShell()).toHaveAttribute("data-density", "compact");
    expect(getShell()).toHaveClass("elysia-density-compact");
    expect(
      JSON.parse(
        window.localStorage.getItem(DESKTOP_PREFERENCES_STORAGE_KEY) ?? "{}"
      )
    ).toMatchObject({ density: "compact" });

    firstMount.unmount();
    render(<AppShell />);

    expect(getShell()).toHaveAttribute("data-density", "compact");
    expect(screen.getByTestId("home-page")).toBeInTheDocument();
  });

  it("applies reduced motion immediately, persists it, and restores it", () => {
    const firstMount = render(<AppShell />);

    expect(getShell()).toHaveAttribute("data-motion", "system");
    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    fireEvent.change(
      screen.getByRole("combobox", { name: "Motion preference" }),
      { target: { value: "reduced" } }
    );

    expect(getShell()).toHaveAttribute("data-motion", "reduced");
    expect(getShell()).toHaveClass("elysia-motion-reduced");
    expect(
      JSON.parse(
        window.localStorage.getItem(DESKTOP_PREFERENCES_STORAGE_KEY) ?? "{}"
      )
    ).toMatchObject({ motionPreference: "reduced" });

    firstMount.unmount();
    render(<AppShell />);

    expect(getShell()).toHaveAttribute("data-motion", "reduced");
    expect(getShell()).toHaveClass("elysia-motion-reduced");
  });

  it("rejects invalid preference values without rejecting valid siblings", () => {
    expect(
      normalizeDesktopPreferences({
        density: "tiny",
        startupRoom: "memory",
        leftRailDefaultBehavior: "floating",
        motionPreference: "animated"
      })
    ).toEqual({
      density: "comfortable",
      startupRoom: "memory",
      leftRailDefaultBehavior: "collapsed",
      motionPreference: "system"
    });
  });

  it("applies and persists the expanded left-rail default", () => {
    const firstMount = render(<AppShell />);

    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Left rail default group behavior"
      }),
      { target: { value: "expanded" } }
    );

    ["Workrooms", "Memory & Identity", "Control & System"].forEach(
      (group) => {
        expect(screen.getByRole("button", { name: group })).toHaveAttribute(
          "aria-expanded",
          "true"
        );
      }
    );

    firstMount.unmount();
    render(<AppShell />);

    ["Workrooms", "Memory & Identity", "Control & System"].forEach(
      (group) => {
        expect(screen.getByRole("button", { name: group })).toHaveAttribute(
          "aria-expanded",
          "true"
        );
      }
    );
  });

  it("does not change the current room when Settings opens or closes", () => {
    render(<AppShell />);

    fireEvent.click(screen.getByRole("button", { name: "Workrooms" }));
    fireEvent.click(screen.getByRole("button", { name: "Projects" }));
    expect(screen.getByTestId("projects-page")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
    expect(screen.getByTestId("projects-page")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));

    expect(screen.getByTestId("projects-page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Projects" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("preserves every AppShell room mapping and keeps group headers non-navigating", () => {
    render(<AppShell />);

    expect(screen.getByTestId("home-page")).toBeInTheDocument();

    ["Workrooms", "Memory & Identity", "Control & System"].forEach(
      (group) => {
        fireEvent.click(screen.getByRole("button", { name: group }));
        expect(screen.getByTestId("home-page")).toBeInTheDocument();
      }
    );

    const mappedRooms = [
      ["Conversations", "conversations-page"],
      ["Projects", "projects-page"],
      ["Artifacts", "artifacts-page"],
      ["Requests", "requests-page"],
      ["Memory", "memory-page"],
      ["Personal Identity", "user-profile-page"],
      ["Governance", "governance-page"],
      ["Capabilities", "capabilities-page"],
      ["Add-ons", "addons-page"],
      ["Health", "health-page"],
      ["Chamber", "home-page"]
    ] as const;

    mappedRooms.forEach(([room, testId]) => {
      fireEvent.click(screen.getByRole("button", { name: room }));
      expect(screen.getByTestId(testId)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Projects" }));
    fireEvent.click(screen.getByRole("button", { name: "Open project detail" }));
    expect(screen.getByTestId("project-detail-page")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /status menu/i }));
    expect(screen.getByTestId("status-menu-page")).toBeInTheDocument();
  });
});

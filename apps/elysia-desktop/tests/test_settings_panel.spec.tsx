import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TopBar from "../src/TopBar";
import {
  DESKTOP_PREFERENCES_STORAGE_KEY,
  type DesktopPreferences
} from "../src/desktopPreferences";

const bridgeClientMocks = vi.hoisted(() => ({
  fetchBridgeHealth: vi.fn(),
  fetchRuntimeStatus: vi.fn(),
  fetchInvokerStatus: vi.fn(),
  fetchCapabilityManifest: vi.fn(),
  fetchInstallProfileStatus: vi.fn(),
  fetchGovernanceState: vi.fn(),
  fetchMemorySummary: vi.fn(),
  fetchMemorySettings: vi.fn(),
  updateMemorySettings: vi.fn()
}));

vi.mock("../src/api/bridgeClient", () => bridgeClientMocks);

function source(label: string) {
  return {
    kind: "service_summary",
    label,
    authority_level: "derived"
  };
}

function resetTruthMocks() {
  bridgeClientMocks.fetchMemorySettings.mockResolvedValue({
    ok: false,
    payload: { status: "unavailable", errors: ["Account settings are unavailable in this isolated test."] }
  });
  bridgeClientMocks.updateMemorySettings.mockResolvedValue({
    ok: false,
    payload: { status: "unavailable", errors: ["Account settings are unavailable in this isolated test."] }
  });
  bridgeClientMocks.fetchBridgeHealth.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      api_version: "1.0.0",
      contract_version: "bridge-contract-v1",
      capability_state: "live",
      data: {
        health_state: "healthy",
        healthy: true,
        runtime_reachable: true,
        ollama_reachable: true
      }
    }
  });

  bridgeClientMocks.fetchRuntimeStatus.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      contract_version: "runtime-contract-v1",
      capability_state: "live",
      locality: "local",
      data: {
        runtime_state: "ready",
        runtime_available: true,
        active_mode: "idle",
        stayed_local: true
      }
    }
  });

  bridgeClientMocks.fetchInvokerStatus.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      contract_version: "invoker-contract-v1",
      capability_state: "live",
      data: {
        invoker_state: "ready",
        invoker_available: true,
        selected_runtime: "ollama",
        selected_model_runtime_tag: "local-model"
      }
    }
  });

  bridgeClientMocks.fetchCapabilityManifest.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      contract_version: "capability-contract-v1",
      capability_state: "live",
      data: {
        capability_catalog_state: "live",
        capability_count: 12
      }
    }
  });

  bridgeClientMocks.fetchInstallProfileStatus.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      contract_version: "elysia-install-profile-runtime-1.0",
      capability_state: "live",
      data: {
        resolution_state: "resolved",
        active_profile_id: "core",
        active_profile_label: "Elysia Core",
        selected_profile_ids: ["core"],
        resolved_profile_ids: ["core"],
        available_profiles: [
          {
            profile_id: "core",
            display_name: "Elysia Core",
            selected: true,
            included: true,
            readiness: "ready"
          },
          { profile_id: "workstation", display_name: "Recommended Workstation" },
          { profile_id: "creator", display_name: "Creator / AI Media" },
          { profile_id: "developer", display_name: "Developer / Codev" }
        ],
        dependency_summary: {
          present: 12,
          missing: 0,
          optional_missing: 3,
          profile_gated: 2,
          lab_gated: 2
        },
        missing_core_dependency_ids: [],
        local_overrides: {
          state: "not_configured",
          configured_count: 0,
          raw_values_exposed: false,
          authority_granted: false
        },
        provider_summary: {
          provider_id: "ollama",
          command_status: "present",
          network_check_performed: false,
          model_loaded: false,
          selection_authority_available: false
        },
        worker_summaries: [
          { worker_id: "speechforge", status: "profile_gated", enabled: false },
          { worker_id: "imageforge", status: "profile_gated", enabled: false },
          { worker_id: "videoforge", status: "lab_gated", enabled: false },
          { worker_id: "engineeringforge", status: "lab_gated", enabled: false },
          { worker_id: "codev", status: "profile_gated", enabled: false }
        ],
        doctor_executed: false,
        install_authority_available: false,
        download_authority_available: false,
        worker_start_authority_available: false
      }
    }
  });

  bridgeClientMocks.fetchGovernanceState.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      contract_version: "governance-contract-v1",
      capability_state: "live",
      data: {
        locality_summary: {
          local_only_by_default: true,
          outbound_networking_posture: "narrow / approval-gated",
          state: "display_only",
          source: source("Locality authority")
        },
        trust_zones: [
          {
            zone_id: "sealed_private",
            label: "Sealed private",
            access_state: "sealed",
            sealed: true,
            state: "display_only",
            source: source("Trust-zone authority")
          }
        ],
        memory_summary: {
          autonomous_updates_enabled: false,
          review_required_for_sensitive_mutations: true,
          sealed_memory_posture: "sealed by default",
          state: "display_only",
          source: source("Memory policy authority"),
          detail: "Memory writes remain policy-governed."
        },
        approval_summary: {
          approval_mode: "approval-governed",
          outbound_actions_allowed: false,
          state: "display_only",
          source: source("Approval authority")
        },
        journaling_summary: {
          journaling_enabled: true,
          journal_mode: "policy-governed",
          request_trace_enabled: false,
          state: "display_only",
          source: source("Journal authority")
        },
        control_states: [
          {
            control_id: "external_helper_web",
            label: "External web helper",
            value: false,
            state: "inactive",
            source: source("External helper authority")
          },
          {
            control_id: "future_density_control",
            label: "Density control",
            value: null,
            state: "planned",
            source: source("Planned UI surface")
          }
        ]
      }
    }
  });

  bridgeClientMocks.fetchMemorySummary.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      capability_state: "live",
      data: {
        summary: {
          total_items: 3,
          class_summaries: [
            {
              memory_class: "preference",
              total_count: 3,
              active_count: 2
            }
          ]
        },
        store_posture: {
          write_actions_live: false
        }
      }
    }
  });
}

function openSettings() {
  fireEvent.click(screen.getByRole("button", { name: "Open settings" }));
  return screen.getByRole("dialog", { name: "Settings" });
}

function getSettingsRow(label: string): HTMLElement {
  const labelElement = screen.getByText(label, { selector: "strong" });
  const row = labelElement.parentElement;

  if (!row) {
    throw new Error(`Settings row ${label} was not found.`);
  }

  return row;
}

function readStoredPreferences(): DesktopPreferences {
  const storedValue = window.localStorage.getItem(
    DESKTOP_PREFERENCES_STORAGE_KEY
  );

  if (!storedValue) {
    throw new Error("Desktop preferences were not persisted.");
  }

  return JSON.parse(storedValue) as DesktopPreferences;
}

describe("global Settings control", () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetTruthMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders a quiet, accessible gear in the persistent internal header", () => {
    render(React.createElement(TopBar));

    const gear = screen.getByRole("button", { name: "Open settings" });

    expect(gear).toHaveAttribute("title", "Settings");
    expect(gear).toHaveAttribute("aria-haspopup", "dialog");
    expect(gear).toHaveAttribute("aria-expanded", "false");
    expect(gear.closest("header")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("opens Settings with real controls and relocates status truth to its owning rooms", async () => {
    render(React.createElement(TopBar, { onOpenRoom: vi.fn() }));

    const dialog = openSettings();

    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open settings" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    expect(screen.getByRole("heading", { name: "Chamber behavior" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Runtime" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Release & Boundaries" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Governance" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Developer / Diagnostics" })).not.toBeInTheDocument();

    expect(screen.getAllByRole("combobox")).toHaveLength(4);
    expect(screen.getByRole("combobox", { name: "UI density" })).toHaveValue(
      "comfortable"
    );
    expect(
      screen.getByRole("combobox", {
        name: "Left rail default group behavior"
      })
    ).toHaveValue("collapsed");
    expect(
      screen.getByRole("combobox", { name: "Startup room" })
    ).toHaveValue("home");
    expect(
      screen.getByRole("combobox", { name: "Motion preference" })
    ).toHaveValue("system");

    expect(screen.getByRole("button", { name: "Open Governance" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Open Health" })).toBeEnabled();
    expect(bridgeClientMocks.fetchMemorySettings).toHaveBeenCalledTimes(1);
    expect(bridgeClientMocks.fetchBridgeHealth).not.toHaveBeenCalled();
    expect(bridgeClientMocks.fetchRuntimeStatus).not.toHaveBeenCalled();
    expect(bridgeClientMocks.fetchInvokerStatus).not.toHaveBeenCalled();
    expect(bridgeClientMocks.fetchCapabilityManifest).not.toHaveBeenCalled();
    expect(bridgeClientMocks.fetchInstallProfileStatus).not.toHaveBeenCalled();
    expect(bridgeClientMocks.fetchGovernanceState).not.toHaveBeenCalled();
    expect(bridgeClientMocks.fetchMemorySummary).not.toHaveBeenCalled();
  });

  it("closes on Escape and returns keyboard focus to the gear", () => {
    render(React.createElement(TopBar));

    openSettings();
    expect(screen.getByRole("button", { name: "Close settings" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog", { name: "Settings" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open settings" })).toHaveFocus();
  });

  it("closes on an outside click or the explicit close button", () => {
    render(React.createElement(TopBar));

    openSettings();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("dialog", { name: "Settings" })).not.toBeInTheDocument();

    openSettings();
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));
    expect(screen.queryByRole("dialog", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("does not change or call room navigation when Settings opens and closes", () => {
    const onOpenRoom = vi.fn();

    render(
      React.createElement(
        React.Fragment,
        null,
        React.createElement("output", null, "Current room: Projects"),
        React.createElement(TopBar, { onOpenRoom })
      )
    );

    openSettings();
    expect(screen.getByText("Current room: Projects")).toBeInTheDocument();
    expect(onOpenRoom).not.toHaveBeenCalled();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByText("Current room: Projects")).toBeInTheDocument();
    expect(onOpenRoom).not.toHaveBeenCalled();
  });

  it("contains no status-dashboard rows or active-looking no-op controls", async () => {
    render(React.createElement(TopBar));

    openSettings();
    await screen.findByText("Account settings are unavailable in this isolated test.");
    expect(screen.queryByText("Display-only")).not.toBeInTheDocument();
    expect(screen.queryByText("Inactive")).not.toBeInTheDocument();
    expect(screen.queryByText("Blocked")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("combobox")).toHaveLength(4);

    [
      "Appearance",
      "API bridge",
      "Runtime",
      "Provider / model",
      "Install profile",
      "Release channel / target",
      "External boundary",
      "Local sandbox / workers",
      "Local-only mode",
      "External tools",
      "Autonomy level",
      "Trust zones",
      "Memory write preferences",
      "Journal policy",
      "Loaded memory classes",
      "Memory writes",
      "Capability manifest",
      "Request traces",
      "Raw diagnostics"
    ].forEach((label) => {
      expect(screen.queryByText(label, { selector: "strong" })).not.toBeInTheDocument();
    });
  });

  it("preserves and persists the canonical Memory Foundation controls when the account contract is available", async () => {
    const foundationalSettings = {
      memory_recording_enabled: true,
      storage_resource_profile: "core_local",
      default_privacy: "private",
      candidate_behavior: "review_personal_inference",
      autonomy_level: 3,
      internet_master_enabled: false,
      retrieval_breadth: "balanced",
      research_initiative: "manual",
      safe_search_level: "strict",
      preferred_reasoning_gear: "automatic",
      autonomy_domain_overrides: {},
      compute_preference: "automatic",
      model_performance_preference: "balanced",
      background_cognition_enabled: false,
      cpu_percent_ceiling: 85,
      ram_mb_ceiling: 16384,
      vram_mb_ceiling: 12288,
      max_background_jobs: 2,
      memory_storage_profile: "balanced",
      storage_budget_mode: "absolute_mb",
      storage_budget_value: 8192,
      emergency_free_space_reserve_mb: 2048,
      consolidation_enabled: true,
      consolidation_schedule: "daily",
      consolidation_resource_percent: 25,
      backup_enabled: false,
      backup_schedule: "weekly",
      backup_retention_count: 3,
      retention_policy: "balanced",
      hot_retention_days: 14,
      cold_after_days: 180,
      prospective_notifications_enabled: true
    } as const;
    bridgeClientMocks.fetchMemorySettings.mockResolvedValueOnce({
      ok: true,
      payload: {
        status: "ok",
        data: { settings: foundationalSettings }
      }
    });
    bridgeClientMocks.updateMemorySettings.mockImplementation(async (settings) => ({
      ok: true,
      payload: {
        status: "ok",
        data: { settings }
      }
    }));

    render(React.createElement(TopBar));
    openSettings();

    expect(
      await screen.findByRole("heading", { name: "Memory, privacy, and authority" })
    ).toBeInTheDocument();
    await screen.findByText("Authoritative per-account controls loaded.");

    expect(screen.getAllByRole("combobox")).toHaveLength(26);
    expect(screen.getByRole("combobox", { name: "Preferred reasoning gear" })).toHaveValue("automatic");
    expect(screen.getByRole("combobox", { name: "Compute preference" })).toHaveValue("automatic");
    expect(screen.getByRole("combobox", { name: "Memory storage profile" })).toHaveValue(
      "core_local"
    );
    expect(screen.getByRole("combobox", { name: "Default memory privacy" })).toHaveValue(
      "private"
    );
    expect(screen.getByRole("combobox", { name: "Candidate review posture" })).toHaveValue(
      "review_personal_inference"
    );
    expect(screen.getByRole("combobox", { name: "Autonomy level" })).toHaveValue("3");
    expect(screen.getByRole("combobox", { name: "Memory retrieval breadth" })).toHaveValue(
      "balanced"
    );
    expect(screen.getByRole("combobox", { name: "Research initiative" })).toHaveValue(
      "manual"
    );
    expect(screen.getByRole("combobox", { name: "Public research safe search" })).toHaveValue(
      "strict"
    );
    expect(within(getSettingsRow("Memory recording")).getByRole("checkbox")).toBeChecked();
    expect(within(getSettingsRow("Internet master switch")).getByRole("checkbox")).not.toBeChecked();

    fireEvent.change(screen.getByRole("combobox", { name: "Autonomy level" }), {
      target: { value: "4" }
    });
    expect(screen.getByLabelText("Autonomy consequence preview")).toHaveTextContent(
      "Level 3 → Level 4"
    );
    expect(bridgeClientMocks.updateMemorySettings).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply reviewed autonomy change" }));
    await waitFor(() => {
      expect(bridgeClientMocks.updateMemorySettings).toHaveBeenLastCalledWith({
        ...foundationalSettings,
        autonomy_level: 4
      });
    });
    fireEvent.click(
      within(getSettingsRow("Internet master switch")).getByRole("checkbox")
    );

    await waitFor(() => {
      expect(bridgeClientMocks.updateMemorySettings).toHaveBeenLastCalledWith({
        ...foundationalSettings,
        autonomy_level: 4,
        internet_master_enabled: true
      });
    });
    await screen.findByText(
      "Saved. Runtime readers now use this persisted account policy."
    );
    fireEvent.change(
      screen.getByRole("combobox", { name: "Memory retrieval breadth" }),
      { target: { value: "focused" } }
    );
    await waitFor(() => {
      expect(bridgeClientMocks.updateMemorySettings).toHaveBeenLastCalledWith({
        ...foundationalSettings,
        autonomy_level: 4,
        internet_master_enabled: true,
        retrieval_breadth: "focused"
      });
    });
  });

  it("does not duplicate governance status or mutability metadata in Settings", async () => {
    bridgeClientMocks.fetchGovernanceState.mockResolvedValueOnce({
      ok: true,
      payload: {
        status: "ok",
        contract_version: "governance-contract-v1",
        capability_state: "live",
        data: {
          locality_summary: {
            local_only_by_default: true,
            state: "live_editable",
            source: source("Locality authority")
          }
        }
      }
    });

    render(React.createElement(TopBar, { onOpenRoom: vi.fn() }));
    openSettings();
    await screen.findByText("Account settings are unavailable in this isolated test.");
    expect(screen.queryByText("Local-only mode", { selector: "strong" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Governance" })).toBeEnabled();
    expect(screen.getAllByRole("combobox")).toHaveLength(4);
    expect(bridgeClientMocks.fetchGovernanceState).not.toHaveBeenCalled();
  });

  it("persists each live local preference and restores it on a new mount", () => {
    const firstMount = render(React.createElement(TopBar));

    openSettings();
    fireEvent.change(screen.getByRole("combobox", { name: "UI density" }), {
      target: { value: "compact" }
    });
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Left rail default group behavior"
      }),
      { target: { value: "expanded" } }
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Startup room" }), {
      target: { value: "projects" }
    });
    fireEvent.change(
      screen.getByRole("combobox", { name: "Motion preference" }),
      { target: { value: "reduced" } }
    );

    expect(readStoredPreferences()).toEqual({
      density: "compact",
      startupRoom: "projects",
      leftRailDefaultBehavior: "expanded",
      motionPreference: "reduced"
    });

    firstMount.unmount();
    render(React.createElement(TopBar));
    openSettings();

    expect(screen.getByRole("combobox", { name: "UI density" })).toHaveValue(
      "compact"
    );
    expect(
      screen.getByRole("combobox", {
        name: "Left rail default group behavior"
      })
    ).toHaveValue("expanded");
    expect(
      screen.getByRole("combobox", { name: "Startup room" })
    ).toHaveValue("projects");
    expect(
      screen.getByRole("combobox", { name: "Motion preference" })
    ).toHaveValue("reduced");
  });

  it("resets only local chamber preferences and leaves unrelated local state alone", () => {
    window.localStorage.setItem("elysia.unrelated.runtime-marker", "retain-me");
    render(React.createElement(TopBar));

    openSettings();
    fireEvent.change(screen.getByRole("combobox", { name: "UI density" }), {
      target: { value: "compact" }
    });
    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Left rail default group behavior"
      }),
      { target: { value: "expanded" } }
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Startup room" }), {
      target: { value: "projects" }
    });
    fireEvent.change(
      screen.getByRole("combobox", { name: "Motion preference" }),
      { target: { value: "reduced" } }
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Reset chamber preferences" })
    );

    expect(
      window.localStorage.getItem(DESKTOP_PREFERENCES_STORAGE_KEY)
    ).toBeNull();
    expect(
      window.localStorage.getItem("elysia.unrelated.runtime-marker")
    ).toBe("retain-me");
    expect(screen.getByRole("combobox", { name: "UI density" })).toHaveValue(
      "comfortable"
    );
    expect(
      screen.getByRole("combobox", { name: "Motion preference" })
    ).toHaveValue("system");
    expect(
      screen.getByRole("combobox", {
        name: "Left rail default group behavior"
      })
    ).toHaveValue("collapsed");
    expect(
      screen.getByRole("combobox", { name: "Startup room" })
    ).toHaveValue("home");
    expect(
      screen.getByText(
        "Chamber preferences reset; no user or body data changed."
      )
    ).toBeInTheDocument();
  });

  it("keeps diagnostics out of Settings and provides real navigation to Health", async () => {
    render(React.createElement(TopBar, { onOpenRoom: vi.fn() }));

    openSettings();
    await screen.findByText("Account settings are unavailable in this isolated test.");
    expect(screen.queryByText("Developer / Diagnostics")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Sanitized settings summary")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Health" })).toBeEnabled();
  });

  it("navigates only when a user explicitly chooses an existing deep-truth room", async () => {
    const onOpenRoom = vi.fn();

    render(React.createElement(TopBar, { onOpenRoom }));

    const destinations = [
      ["Open Governance", "governance"],
      ["Open Memory", "memory"],
      ["Open Health", "health"],
      ["Open Capabilities", "capabilities"]
    ] as const;

    destinations.forEach(([buttonName]) => {
      openSettings();
      fireEvent.click(screen.getByRole("button", { name: buttonName }));
      expect(
        screen.queryByRole("dialog", { name: "Settings" })
      ).not.toBeInTheDocument();
    });

    await waitFor(() => {
      expect(onOpenRoom.mock.calls.map(([room]) => room)).toEqual(
        destinations.map(([, room]) => room)
      );
    });
  });
});

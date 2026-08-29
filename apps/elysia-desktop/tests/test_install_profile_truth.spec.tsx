import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HealthPage from "../src/HealthPage";
import CapabilitiesPage from "../src/CapabilitiesPage";

const bridgeClientMocks = vi.hoisted(() => ({
  fetchAccountState: vi.fn(),
  fetchBridgeHealth: vi.fn(),
  fetchInstallProfileStatus: vi.fn(),
  fetchInstallDoctorStatus: vi.fn(),
  fetchCapabilityManifest: vi.fn(),
  fetchMemoryHealth: vi.fn(),
  fetchCognitionStatus: vi.fn(),
  fetchApplicationLifecycleState: vi.fn(),
  previewApplicationLifecycle: vi.fn(),
  applyApplicationLifecycle: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>(
    "../src/api/bridgeClient"
  );
  return { ...actual, ...bridgeClientMocks };
});

function profilePayload() {
  return {
    status: "ok",
    capability_state: "live",
    data: {
      resolution_state: "resolved",
      active_profile_id: "core",
      active_profile_label: "Elysia Core",
      available_profiles: [
        {
          profile_id: "core",
          display_name: "Elysia Core",
          selected: true,
          included: true,
          readiness: "ready"
        }
      ],
      dependency_summary: {
        present: 12,
        missing: 0,
        optional_missing: 2,
        profile_gated: 4,
        lab_gated: 3
      },
      missing_core_dependency_ids: [],
      local_overrides: {
        state: "loaded",
        configured_count: 2,
        raw_values_exposed: false,
        authority_granted: false,
        raw_path: "/home/private-operator/PROFILE_PATH_MARKER"
      },
      worker_summaries: [
        { worker_id: "imageforge", status: "profile_gated", enabled: false },
        { worker_id: "videoforge", status: "lab_gated", enabled: false }
      ],
      capability_tiers: {
        core_v1_default: ["conversations_projects_and_identity"],
        optional_v1_profile: ["imageforge_creator_target"],
        v1_lab_or_developer_gated: ["videoforge"],
        hard_prohibited_by_default: ["silent_cloud_fallback"]
      },
      doctor_executed: false,
      install_authority_available: false,
      download_authority_available: false,
      worker_start_authority_available: false
    }
  };
}

describe("install profile runtime truth", () => {
  beforeEach(() => {
    bridgeClientMocks.fetchAccountState.mockResolvedValue({
      ok: true,
      payload: { status: "ok", data: { active_role: "user" } }
    });
    bridgeClientMocks.fetchMemoryHealth.mockResolvedValue({
      ok: true,
      payload: { status: "ok", data: { health: { state: "ready" } } }
    });
    bridgeClientMocks.fetchCognitionStatus.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        data: { effective_controls: {}, compute: {}, model_registry: { models: [] } }
      }
    });
    bridgeClientMocks.fetchApplicationLifecycleState.mockResolvedValue({
      ok: true,
      payload: { status: "ok", data: { installed: true, current_release_id: "candidate-a", incomplete_operation_detected: false } }
    });
    bridgeClientMocks.fetchBridgeHealth.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        data: {
          health_state: "healthy",
          healthy: true,
          startup_state: "ready",
          api_reachable: true,
          runtime_reachable: true,
          ollama_reachable: false,
          searxng_reachable: false,
          config_loadable: true,
          logging_writable: true,
          journaling_writable: true,
          memory_path_available: true,
          health_notes: [],
          subsystems: {}
        }
      }
    });
    bridgeClientMocks.fetchInstallProfileStatus.mockResolvedValue({
      ok: true,
      payload: profilePayload()
    });
    bridgeClientMocks.fetchInstallDoctorStatus.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        capability_state: "live",
        data: {
          overall_status: "present",
          runtime_mode: "packaged",
          active_profile_id: "core",
          core_ready: true,
          local_api_reachable: true,
          local_auth: {
            required_for_mutations: true,
            initialized: true,
            credential_exposed: false,
            raw_credential: "PRIVATE_CREDENTIAL_MARKER"
          },
          path_contract: {
            config: "XDG user config",
            data: "XDG user data",
            raw_paths_exposed: false,
            raw_path: "/home/private-operator/DOCTOR_PATH_MARKER"
          },
          first_run: {
            state: "ready",
            required_directories_ready: true,
            authentication_ready: true,
            raw_paths_exposed: false
          },
          worker_execution_enabled: false,
          install_authority_available: false,
          repair_authority_available: false,
          raw_paths_exposed: false
        }
      }
    });
    bridgeClientMocks.fetchCapabilityManifest.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        capability_state: "live",
        contract_version: "phase1-ui-contract-1.0",
        data: {
          capability_catalog_state: "live",
          capability_count: 1,
          capability_groups: ["status_surfaces"],
          capabilities: [
            {
              capability_key: "install_profile_manifests",
              display_name: "Install profile runtime truth",
              group: "status_surfaces",
              state: "live",
              summary: "Read-only profile readiness.",
              locality: "local",
              approval_state: "not_needed",
              read_only: true,
              ui_surfaces: ["settings_panel", "health_room", "capabilities_room"],
              supporting_endpoint: "/status/profiles",
              notes: ["Installs and enables nothing."]
            }
          ]
        }
      }
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows bounded profile and dependency truth without activation controls", async () => {
    const onDrawer = vi.fn();
    render(
      <HealthPage startupReady={true} onRightDrawerSectionsChange={onDrawer} />
    );

    await screen.findByRole("region", { name: "Install profile readiness" });
    expect(screen.getByRole("region", { name: "Core install doctor" })).toBeInTheDocument();
    expect(screen.getAllByText("Elysia Core").length).toBeGreaterThan(0);
    expect(screen.getByText("12 present")).toBeInTheDocument();
    expect(screen.getByText("Doctor not executed")).toBeInTheDocument();
    expect(
      screen.getByText(/no install, download, profile-enable, model-load, or worker-start authority/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/PROFILE_PATH_MARKER/)).not.toBeInTheDocument();
    expect(screen.queryByText(/DOCTOR_PATH_MARKER/)).not.toBeInTheDocument();
    expect(screen.queryByText(/PRIVATE_CREDENTIAL_MARKER/)).not.toBeInTheDocument();
    expect(screen.getByText("Packaged")).toBeInTheDocument();
    expect(screen.getByText("Initialized")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /install/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /enable/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Refresh health" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Local Admin: preview exact lifecycle effects" })).toBeDisabled();
    expect(bridgeClientMocks.fetchBridgeHealth).toHaveBeenCalledTimes(1);
    expect(bridgeClientMocks.fetchInstallProfileStatus).toHaveBeenCalledTimes(1);
    expect(bridgeClientMocks.fetchInstallDoctorStatus).toHaveBeenCalledTimes(1);

    await waitFor(() => expect(onDrawer).toHaveBeenCalled());
    const latestSections = onDrawer.mock.calls.at(-1)?.[0] ?? [];
    expect(JSON.stringify(latestSections)).not.toContain("PROFILE_PATH_MARKER");
    expect(JSON.stringify(latestSections)).toContain("Profile Readiness");
  });

  it("shows all four capability tiers without profile mutation authority", async () => {
    render(
      <CapabilitiesPage
        startupReady={true}
        onRightDrawerSectionsChange={vi.fn()}
      />
    );

    await screen.findByText(/Install profile capability tiers · Elysia Core/);
    expect(screen.getByText(/Core V1 Default/i)).toBeInTheDocument();
    expect(screen.getByText(/Optional V1 Profile/i)).toBeInTheDocument();
    expect(screen.getByText(/V1 Lab \/ Developer Gated/i)).toBeInTheDocument();
    expect(screen.getByText(/Hard Prohibited By Default/i)).toBeInTheDocument();
    expect(screen.getByText("Silent Cloud Fallback")).toBeInTheDocument();
    expect(
      screen.getByText(/Profile selection installs nothing, starts no worker, grants no approval/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enable profile" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Install profile" })).not.toBeInTheDocument();
    expect(bridgeClientMocks.fetchCapabilityManifest).toHaveBeenCalledTimes(1);
    expect(bridgeClientMocks.fetchInstallProfileStatus).toHaveBeenCalledTimes(1);
  });
});

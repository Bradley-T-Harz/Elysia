import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const bridgeMocks = vi.hoisted(() => ({
  previewSetup: vi.fn(),
  applySetup: vi.fn(),
  previewComponentInstall: vi.fn(),
  applyComponentInstall: vi.fn(),
  fetchComponentJob: vi.fn(),
  cancelComponentJob: vi.fn(),
  previewSystemPrerequisites: vi.fn(),
  applySystemPrerequisites: vi.fn(),
  runSetupDoctor: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>("../src/api/bridgeClient");
  return { ...actual, ...bridgeMocks };
});

import ElysiaSetupPage from "../src/ElysiaSetupPage";

const ok = (data: Record<string, unknown>) => ({
  ok: true,
  payload: { status: "ok", errors: [], warnings: [], data }
});

describe("Elysia Setup machine-install authority", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("truthfully separates optional managed runtimes from package and XDG state", async () => {
    bridgeMocks.previewSetup.mockResolvedValue(ok({
      preview_id: "setup_aaaaaaaaaaaaaaaaaaaaaaaa",
      approval_token: "x".repeat(40),
      ready_to_apply: true,
      component_ids: ["core_runtime", "memory_fabric"],
      hardware: { neurofabric_variant: "cpu" },
      privilege_preview: { package_manager_privilege_required: false, exact_system_package_operations: [] },
      estimated_download_bytes: 0,
      estimated_installed_bytes: 1024,
      dependency_install_dispositions: {
        dependency_count: 15,
        category_counts: { A: 14, B: 0, C: 0, D: 0, E: 1 },
        system_dependency_count: 9,
        system_category_counts: { A: 0, B: 0, C: 9, D: 0, E: 0 },
        system_category_e_actions: [],
        category_e_actions: [{
          dependency_id: "ollama_local_provider",
          label: "Ollama",
          purpose: "Local model provider",
          guidance: {
            title: "Ollama local model provider",
            why: "Optional local conversation and embedding roles use it.",
            official_source: "https://docs.ollama.com/linux",
            signup_required: "no account for installation",
            data_leaving_local_control: "download network metadata only",
            license_privacy_security: "Ollama and each selected model have separate terms.",
            supported_steps: ["Install from the official publisher instructions."],
            doctor_detection: "Doctor checks the loopback service.",
            retry_repair: "Repair through the official lifecycle and rerun Doctor."
          }
        }]
      },
      component_license_preview: [],
      warnings: [],
      blockers: []
    }));
    const configured = vi.fn().mockResolvedValue(undefined);
    render(<ElysiaSetupPage initialState={null} onConfigured={configured} />);

    expect(screen.getByTestId("elysia-setup-page")).toHaveStyle({
      height: "100vh",
      maxHeight: "100vh",
      overflowY: "auto"
    });
    expect(screen.getByText(/does not create a person, biography, Website account, or memory/i)).toBeVisible();
    expect(screen.getByText(/accounts, Memory, settings, caches, and runtime authority remain in their stable XDG locations/i)).toBeVisible();
    fireEvent.change(screen.getByLabelText("Optional managed-component runtime root (optional)"), {
      target: { value: "/tmp/Install Roots/Elysia Ω" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview exact setup plan" }));
    await waitFor(() => expect(bridgeMocks.previewSetup).toHaveBeenCalledWith(expect.objectContaining({
      install_root: "/tmp/Install Roots/Elysia Ω",
      distribution_form: "deb",
      profile_id: "core"
    })));
    expect(await screen.findByRole("region", { name: "Setup effect preview" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Selected profile dependency dispositions" })).toBeVisible();
    expect(screen.getByText(/A bundled: 14/)).toBeVisible();
    expect(screen.getByText(/System A bundled: 0/)).toBeVisible();
    expect(screen.getByText("Ollama local model provider")).toBeVisible();
    expect(screen.getByRole("link", { name: "Official installation source" })).toHaveAttribute(
      "href", "https://docs.ollama.com/linux"
    );
  });

  it("renders one operator action for aliased system prerequisites", async () => {
    bridgeMocks.previewSetup.mockResolvedValue(ok({
      preview_id: "setup_cccccccccccccccccccccccc",
      approval_token: "x".repeat(40),
      ready_to_apply: true,
      component_ids: ["local_model_provider", "semantic_retrieval"],
      hardware: { neurofabric_variant: "cpu" },
      privilege_preview: { package_manager_privilege_required: false, exact_system_package_operations: [] },
      estimated_download_bytes: 0,
      estimated_installed_bytes: 0,
      dependency_install_dispositions: {
        dependency_count: 2,
        category_counts: { A: 0, B: 0, C: 0, D: 2, E: 0 },
        category_e_actions: [],
        system_dependency_count: 2,
        system_category_counts: { A: 0, B: 0, C: 0, D: 0, E: 2 },
        system_category_e_actions: [{
          dependency_id: "ollama_local_provider",
          dependency_ids: ["ollama", "ollama_optional"],
          purposes: ["Required provider", "Optional provider"],
          guidance: {
            title: "Ollama local model provider",
            why: "Local model roles need a compatible loopback provider.",
            official_source: "https://docs.ollama.com/linux",
            signup_required: "No account required.",
            data_leaving_local_control: "Download metadata only.",
            license_privacy_security: "Separate provider and model licenses apply.",
            supported_steps: ["Install from the official source."],
            doctor_detection: "Doctor checks the loopback provider.",
            retry_repair: "Repair the provider and rerun Doctor."
          }
        }]
      },
      component_license_preview: [],
      warnings: [],
      blockers: []
    }));
    render(<ElysiaSetupPage initialState={null} onConfigured={vi.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(screen.getByRole("button", { name: "Preview exact setup plan" }));
    expect(await screen.findByText("Ollama local model provider")).toBeVisible();
    expect(screen.getByText(/ollama, ollama_optional/)).toBeVisible();
    expect(screen.getAllByText("Ollama local model provider")).toHaveLength(1);
  });

  it("locks Setup to the distribution form detected from the running package", async () => {
    bridgeMocks.previewSetup.mockResolvedValue(ok({
      preview_id: "setup_bbbbbbbbbbbbbbbbbbbbbbbb",
      approval_token: "x".repeat(40),
      ready_to_apply: true,
      component_ids: ["core_runtime", "memory_fabric"],
      privilege_preview: { package_manager_privilege_required: false, exact_system_package_operations: [] },
      component_license_preview: [], warnings: [], blockers: []
    }));
    render(<ElysiaSetupPage initialState={{
      configured: false,
      detected_distribution_form: "appimage",
      distribution_form_locked: true,
      pending_component_ids: []
    }} onConfigured={vi.fn().mockResolvedValue(undefined)} />);

    const selector = screen.getByLabelText("Distribution form") as HTMLSelectElement;
    expect(selector).toBeDisabled();
    expect(selector.value).toBe("appimage");
    expect(screen.getByText(/Detected from the running package/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Preview exact setup plan" }));
    await waitFor(() => expect(bridgeMocks.previewSetup).toHaveBeenCalledWith(expect.objectContaining({
      distribution_form: "appimage"
    })));
  });

  it("requires exact component and privilege previews before selected-profile completion", async () => {
    bridgeMocks.previewSystemPrerequisites.mockResolvedValue(ok({
      preview_id: "prereq_aaaaaaaaaaaaaaaaaaaaaaaa",
      approval_token: "y".repeat(40),
      authorization_mechanism: "graphical_polkit_pkexec",
      exact_package_operations: ["install ffmpeg"],
      external_missing_dependency_ids: []
    }));
    render(<ElysiaSetupPage initialState={{
      configured: true,
      setup_required: true,
      doctor_required: true,
      profile_id: "creator_perception",
      component_ids: ["creator_perception"],
      pending_component_ids: ["creator_perception"]
    }} onConfigured={vi.fn().mockResolvedValue(undefined)} />);

    expect(screen.getByRole("region", { name: "Selected component installation" })).toBeVisible();
    expect(screen.getByText(/Profile selection did not approve downloads/i)).toBeVisible();
    expect(screen.getByText(/capabilities remain visibly gated when omitted/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Inspect exact system prerequisites" }));
    expect(await screen.findByText(/graphical_polkit_pkexec/)).toBeVisible();
    expect(screen.getByRole("button", { name: /Authorize only these exact Ubuntu package operations/i })).toBeVisible();
  });

  it("offers exact Codev acquisition while preserving editor-choice authority", () => {
    render(<ElysiaSetupPage initialState={{
      configured: true,
      setup_required: true,
      doctor_required: true,
      profile_id: "developer_codev",
      component_ids: ["codev_companion"],
      pending_component_ids: ["codev_companion"]
    }} onConfigured={vi.fn().mockResolvedValue(undefined)} />);

    expect(screen.getByLabelText(/Existing exact Codev v1\.0\.0 VSIX/)).toBeVisible();
    expect(screen.getByPlaceholderText(/exact official GitHub release download/i)).toBeVisible();
    expect(screen.getByText(/acquires the exact first-party VSIX/i)).toBeVisible();
  });

  it("runs a non-repairing Doctor as the final machine-install gate", async () => {
    bridgeMocks.runSetupDoctor.mockResolvedValue(ok({ doctor_passed: true }));
    const configured = vi.fn().mockResolvedValue(undefined);
    render(<ElysiaSetupPage initialState={{
      configured: true,
      setup_required: true,
      doctor_required: true,
      profile_id: "core",
      component_ids: ["core_runtime", "memory_fabric"],
      pending_component_ids: []
    }} onConfigured={configured} />);

    expect(screen.getByRole("region", { name: "Final Setup Doctor gate" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Run final non-repairing Doctor" }));
    await waitFor(() => expect(bridgeMocks.runSetupDoctor).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(configured).toHaveBeenCalledTimes(1));
  });
});

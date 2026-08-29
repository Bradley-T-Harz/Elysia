import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const bridgeMocks = vi.hoisted(() => ({
  fetchAccountState: vi.fn(),
  fetchApplicationLifecycleState: vi.fn(),
  previewApplicationLifecycle: vi.fn(),
  applyApplicationLifecycle: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>("../src/api/bridgeClient");
  return { ...actual, ...bridgeMocks };
});

import ApplicationLifecyclePanel from "../src/ApplicationLifecyclePanel";

const ok = (data: Record<string, unknown>) => ({ ok: true, payload: { status: "ok", errors: [], warnings: [], data } });

describe("governed application lifecycle", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("distinguishes preserved uninstall, export-remove, and explicit purge", async () => {
    bridgeMocks.fetchAccountState.mockResolvedValue(ok({ active_role: "installation_owner" }));
    bridgeMocks.fetchApplicationLifecycleState.mockResolvedValue(ok({ installed: true, current_release_id: "candidate-a", incomplete_operation_detected: false }));
    bridgeMocks.previewApplicationLifecycle.mockResolvedValue(ok({
      operation: "purge_local_data", preview_id: "lifecycle_aaaaaaaaaaaaaaaaaaaaaaaa",
      approval_token: "x".repeat(40), local_data_inventory: { root_count: 5, file_count: 17, exact_bytes: 2048 },
    }));
    render(<ApplicationLifecyclePanel />);
    expect(await screen.findByText(/Current release:/)).toBeVisible();
    const selector = screen.getByLabelText("Lifecycle operation");
    expect(screen.getByRole("option", { name: "Remove application, preserve profiles and memory" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Private export, then remove all local data" })).toBeInTheDocument();
    fireEvent.change(selector, { target: { value: "purge_local_data" } });
    const previewButton = screen.getByRole("button", { name: "Local Admin: preview exact lifecycle effects" });
    expect(previewButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Type exactly:/), { target: { value: "PURGE ALL LOCAL ELYSIA DATA" } });
    expect(previewButton).toBeEnabled();
    fireEvent.click(previewButton);
    await waitFor(() => expect(bridgeMocks.previewApplicationLifecycle).toHaveBeenCalledWith(expect.objectContaining({
      operation: "purge_local_data", destructive_confirmation: "PURGE ALL LOCAL ELYSIA DATA",
    })));
    expect(await screen.findByText(/17 files/)).toBeVisible();
  });

  it("exposes status but refuses lifecycle mutation to an ordinary user", async () => {
    bridgeMocks.fetchAccountState.mockResolvedValue(ok({ active_role: "user" }));
    bridgeMocks.fetchApplicationLifecycleState.mockResolvedValue(ok({
      installed: true,
      current_release_id: "candidate-a",
      incomplete_operation_detected: false
    }));
    render(<ApplicationLifecyclePanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/require an authenticated Local Admin/);
    expect(screen.getByLabelText("Lifecycle operation")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Local Admin: preview exact lifecycle effects" })).toBeDisabled();
    expect(bridgeMocks.previewApplicationLifecycle).not.toHaveBeenCalled();
  });
});

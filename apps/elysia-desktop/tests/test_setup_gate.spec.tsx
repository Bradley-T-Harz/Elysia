import React from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const bridgeMocks = vi.hoisted(() => ({
  fetchSetupState: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>("../src/api/bridgeClient");
  return { ...actual, ...bridgeMocks };
});

import SetupGate from "../src/SetupGate";

const blocked = {
  ok: false,
  payload: {
    status: "blocked",
    errors: ["The fixed Core launcher did not become ready."],
    warnings: [],
    data: {}
  }
};

const ready = {
  ok: true,
  payload: {
    status: "ok",
    errors: [],
    warnings: [],
    data: {
      setup_required: false,
      configured: true,
      machine_ready: true,
      detected_distribution_form: "appimage"
    }
  }
};

describe("machine-installation startup reconciliation", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("retries a cold packaged launcher before deciding whether Setup is required", async () => {
    vi.useFakeTimers();
    bridgeMocks.fetchSetupState.mockResolvedValueOnce(blocked).mockResolvedValueOnce(ready);

    render(<SetupGate><div>Existing configured chamber</div></SetupGate>);
    await act(async () => { await Promise.resolve(); });
    expect(bridgeMocks.fetchSetupState).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Checking machine installation truth…")).toBeVisible();

    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
    expect(screen.getByText("Existing configured chamber")).toBeVisible();
    expect(bridgeMocks.fetchSetupState).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Elysia Setup")).not.toBeInTheDocument();
  });

  it("never invents a default Setup/distribution state when machine truth stays unavailable", async () => {
    vi.useFakeTimers();
    bridgeMocks.fetchSetupState.mockResolvedValue(blocked);

    render(<SetupGate><div>Existing configured chamber</div></SetupGate>);
    await act(async () => { await Promise.resolve(); });
    expect(bridgeMocks.fetchSetupState).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });

    expect(screen.getByRole("alert")).toHaveTextContent("Machine installation truth is temporarily unavailable");
    expect(screen.getByRole("button", { name: "Retry machine check" })).toBeVisible();
    expect(screen.queryByText("Elysia Setup")).not.toBeInTheDocument();
    expect(screen.queryByText("Installed .deb")).not.toBeInTheDocument();
  });
});

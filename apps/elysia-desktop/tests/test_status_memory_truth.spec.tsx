import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StatusMenuPage from "../src/StatusMenuPage";

const bridgeClientMocks = vi.hoisted(() => ({
  fetchCognitionStatus: vi.fn(),
  fetchMemoryHealth: vi.fn(),
  fetchDueProspectiveMemory: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>(
    "../src/api/bridgeClient"
  );
  return { ...actual, ...bridgeClientMocks };
});

describe("Status memory lifecycle and prospective notification truth", () => {
  beforeEach(() => {
    bridgeClientMocks.fetchCognitionStatus.mockResolvedValue({
      ok: true,
      payload: { data: { effective_controls: {}, compute: {}, emergency: { active: false } } }
    });
    bridgeClientMocks.fetchMemoryHealth.mockResolvedValue({
      ok: true,
      payload: {
        data: {
          health: {
            release_closure: {
              canonical_writer_count: 1,
              object_store: { state: "ready" },
              graph: { state: "ready" }
            }
          }
        }
      }
    });
    bridgeClientMocks.fetchDueProspectiveMemory.mockResolvedValue({
      ok: true,
      payload: {
        data: {
          prospective: {
            enabled: true,
            due_count: 2,
            due: [{ overdue: true }, { overdue: false }],
            sealed_excluded: true
          }
        }
      }
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows endpoint-backed lifecycle and content-free reminder counts", async () => {
    render(
      <StatusMenuPage
        startupTruthState="ok"
        startupTruthMessage="Ready"
        startupTruthDetail="Ready"
        startupReady={true}
      />
    );

    expect(await screen.findByText("2 due in the next 7 days · 1 overdue · Sealed excluded")).toBeInTheDocument();
    expect(
      screen.getByText("Canonical writers 1 · object store ready · graph ready")
    ).toBeInTheDocument();
    expect(bridgeClientMocks.fetchDueProspectiveMemory).toHaveBeenCalledWith(168);
  });
});

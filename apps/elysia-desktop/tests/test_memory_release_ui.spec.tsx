import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const bridge = vi.hoisted(() => ({
  fetchMemorySummary: vi.fn(),
  fetchMemoryItems: vi.fn(),
  fetchMemoryReceipts: vi.fn(),
  fetchMemorySpaces: vi.fn(),
  fetchMemorySpaceInvitations: vi.fn(),
  fetchMemoryHealth: vi.fn(),
  fetchMemoryMigrationStatus: vi.fn(),
  fetchMemoryBackupStatus: vi.fn(),
  fetchMemoryHomeostasis: vi.fn(),
  fetchMemoryJobs: vi.fn(),
  fetchDueProspectiveMemory: vi.fn(),
  fetchMemorySettings: vi.fn(),
  previewMemoryConsequence: vi.fn(),
  applyMemoryConsequence: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>(
    "../src/api/bridgeClient"
  );
  return { ...actual, ...bridge };
});

import MemoryPage from "../src/MemoryPage";

const ok = (data: Record<string, unknown>) => ({
  ok: true,
  payload: { status: "ok", errors: [], data }
});

describe("Part 2E Memory stewardship", () => {
  beforeEach(() => {
    bridge.fetchMemorySummary.mockResolvedValue(ok({
      summary: { total_items: 1, class_summaries: [] },
      store_posture: { write_actions_live: true }
    }));
    bridge.fetchMemoryItems.mockImplementation((options?: { status?: string }) =>
      Promise.resolve(ok({
        items: options?.status
          ? [{
              memory_id: "candidate_synthetic",
              title: "Synthetic candidate",
              status: "candidate",
              candidate_kind: "conversation_extraction",
              candidate_proposed_wording: "Synthetic proposed wording",
              candidate_evidence_summary: "Synthetic source evidence",
              why_stored: "Continuity candidate",
              form: "prospective",
              scope: "conversation",
              privacy: "normal",
              confidence: 0.84,
              activation_tier: "warm",
              sources: [{ source_type: "conversation" }]
            }]
          : [{
              memory_id: "memory_synthetic",
              title: "Synthetic durable memory",
              body_excerpt: "Synthetic nonprivate body",
              why_stored: "Part 2E UI proof",
              memory_class: "preference",
              sensitivity: "internal",
              mutability: "live_editable",
              status: "active",
              source_label: "Synthetic user declaration",
              updated_at_utc: "2026-08-22T00:00:00Z",
              actions: {
                can_pin: true,
                can_move: true,
                can_edit: true,
                can_forget: true
              }
            }],
        total: 1
      }))
    );
    bridge.fetchMemoryReceipts.mockResolvedValue(ok({ receipts: [] }));
    bridge.fetchMemorySpaces.mockResolvedValue(ok({ spaces: [] }));
    bridge.fetchMemorySpaceInvitations.mockResolvedValue(ok({
      invitations: [{
        invitation_id: "spaceinvite_synthetic",
        space_label: "Synthetic collaborators",
        role: "reader",
        state: "pending",
        direction: "incoming"
      }]
    }));
    bridge.fetchMemoryHealth.mockResolvedValue(ok({
      health: {
        lexical_projection: { state: "ready" },
        semantic_projection: { state: "optional_not_configured" },
        research_evidence: { state: "ready" }
      }
    }));
    bridge.fetchMemoryMigrationStatus.mockResolvedValue(ok({ migration: { state: "not_needed" } }));
    bridge.fetchMemoryBackupStatus.mockResolvedValue(ok({ backup: { automatic_pre_migration_backup: true } }));
    bridge.fetchMemoryHomeostasis.mockResolvedValue(ok({
      homeostasis: { state: "ready", tier_counts: { warm: 1 }, objects: { object_count: 0 } }
    }));
    bridge.fetchMemoryJobs.mockResolvedValue(ok({ jobs: [] }));
    bridge.fetchDueProspectiveMemory.mockResolvedValue(ok({ prospective: { due_count: 0 } }));
    bridge.fetchMemorySettings.mockResolvedValue(ok({ settings: { memory_recording_enabled: true } }));
    bridge.previewMemoryConsequence.mockResolvedValue(ok({
      approval: {
        approval_id: "approval_synthetic",
        approval_token: "one-time-synthetic-token",
        expires_at_utc: "2026-08-22T23:59:59Z",
        consequence: {
          deletion_plan: {
            canonical_revisions: 2,
            object_references: 1,
            managed_backups: 1,
            managed_state_fingerprint: "content-free-fingerprint"
          }
        }
      }
    }));
    bridge.applyMemoryConsequence.mockResolvedValue(ok({
      applied: true,
      absence_verification: { absent: true }
    }));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows all forms and requires an in-room exact deletion-plan decision", async () => {
    render(
      <MemoryPage startupReady onRightDrawerSectionsChange={vi.fn()} />
    );

    const form = await screen.findByLabelText("Memory form");
    expect(form.querySelectorAll("option")).toHaveLength(9);
    expect(screen.getByText("Memory stewardship")).toBeInTheDocument();
    expect(screen.getByLabelText("Memory form action")).toBeInTheDocument();
    expect(screen.getByLabelText("Local password for sealed unlock or migration")).toHaveAttribute(
      "type",
      "password"
    );
    expect(screen.getByText(/Form: prospective · Scope: conversation · Privacy: normal/)).toBeInTheDocument();
    expect(screen.getByText(/Confidence: 0.84 · Suggested tier: warm · Sources: 1/)).toBeInTheDocument();
    expect(screen.getByText("Pending Shared Space invitations")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Invite or govern shared-space member" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Memory title" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Memory body" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Memory storage reason" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Memory privacy" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Forget" }));
    const plan = await screen.findByRole("dialog", {
      name: "Exact hard-delete consequence plan"
    });
    expect(plan).toHaveTextContent("managed state fingerprint");
    expect(plan).toHaveTextContent(/cannot erase disconnected or user-exported offline copies/i);
    expect(bridge.applyMemoryConsequence).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "Apply this exact permanent deletion" })
    );
    await waitFor(() => {
      expect(bridge.applyMemoryConsequence).toHaveBeenCalledWith(
        "memory_synthetic",
        "approval_synthetic",
        "one-time-synthetic-token"
      );
    });
  }, 15_000);
});

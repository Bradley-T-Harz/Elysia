import React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import GovernancePage from "../src/GovernancePage";

const bridgeClientMocks = vi.hoisted(() => ({
  fetchGovernanceState: vi.fn(),
  fetchCognitionStatus: vi.fn(),
  planGovernanceChange: vi.fn(),
  applyGovernanceChange: vi.fn(),
  restoreGovernanceChange: vi.fn(),
  resolveGovernanceApproval: vi.fn(),
  fetchMemoryPendingApprovals: vi.fn(),
  fetchResearchEgressApprovals: vi.fn(),
  resolveResearchEgressApproval: vi.fn()
}));

vi.mock("../src/api/bridgeClient", () => bridgeClientMocks);

function source(label: string) {
  return {
    kind: "policy_file",
    label,
    authority_level: "authoritative"
  };
}

describe("Governance mutation truth", () => {
  beforeEach(() => {
    bridgeClientMocks.fetchGovernanceState.mockReset();
    bridgeClientMocks.fetchCognitionStatus.mockReset();
    bridgeClientMocks.planGovernanceChange.mockReset();
    bridgeClientMocks.applyGovernanceChange.mockReset();
    bridgeClientMocks.restoreGovernanceChange.mockReset();
    bridgeClientMocks.resolveGovernanceApproval.mockReset();
    bridgeClientMocks.fetchMemoryPendingApprovals.mockReset();
    bridgeClientMocks.fetchResearchEgressApprovals.mockReset();
    bridgeClientMocks.resolveResearchEgressApproval.mockReset();
    bridgeClientMocks.fetchMemoryPendingApprovals.mockResolvedValue({
      ok: true,
      payload: { status: "ok", data: { approvals: [] } }
    });
    bridgeClientMocks.fetchResearchEgressApprovals.mockResolvedValue({
      ok: true,
      payload: { status: "ok", data: { approvals: [] } }
    });
    bridgeClientMocks.fetchCognitionStatus.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        data: {
          governor_contract: "adaptive-cognition-governor-v1",
          reasoning_gears: ["reflex", "quick", "standard", "deep", "deliberative", "research_engineering"],
          effective_controls: {
            autonomy_level: 3,
            preferred_reasoning_gear: "automatic",
            compute_preference: "automatic",
            cpu_percent_ceiling: 85,
            ram_mb_ceiling: 16384,
            vram_mb_ceiling: 12288
          },
          compute: { active_job_count: 0 },
          active_gpu_leases: [],
          emergency: { active: false },
          private_content_included: false
        }
      }
    });

    bridgeClientMocks.fetchGovernanceState.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        data: {
          mutation_contract_version: "governance-mutation-contract-1.0",
          governance_config_hash: "1".repeat(64),
          mutation_summary: {
            "safe-live-editable-now": 0,
            "read-only-constitutional": 1,
            "hard-prohibited-by-default": 2
          },
          locality_summary: {
            local_only_by_default: true,
            state: "display_only",
            source: source("Locality authority"),
            detail: "Local-only is constitutional law."
          },
          role_authority: {
            default_role: "primary_general",
            authority_label: "Role authority"
          },
          routing_summary: {
            routing_mode: "local_only",
            source: source("Routing authority")
          },
          memory_summary: {
            retention_posture: "policy-governed",
            source: source("Memory authority")
          },
          approval_summary: {
            approval_mode: "approval-governed",
            source: source("Approval authority")
          },
          journaling_summary: {
            journal_mode: "append_only",
            source: source("Audit authority")
          },
          trust_zones: [
            {
              zone_id: "sealed_private",
              label: "Sealed private / Vault",
              description: "Private material remains sealed by default.",
              access_state: "sealed",
              sealed: true,
              state: "inactive",
              source: source("Trust-zone authority")
            }
          ],
          control_sources: [],
          control_states: [
            {
              control_id: "bridge_local_only_default",
              label: "Local-only by default",
              value: true,
              state: "display_only",
              source: source("Locality authority"),
              category: "locality",
              mutation_classification: "read-only-constitutional",
              mutation_risk: "critical",
              mutation_allowed: false,
              approval_required: false,
              mutation_reason: "The local bridge boundary is constitutional law."
            },
            {
              control_id: "routing_silent_cloud_fallback",
              label: "Silent cloud fallback",
              value: false,
              state: "display_only",
              source: source("Routing authority"),
              category: "routing_posture",
              mutation_classification: "hard-prohibited-by-default",
              mutation_risk: "critical",
              mutation_allowed: false,
              approval_required: false,
              mutation_reason: "Silent cloud fallback is prohibited."
            },
            {
              control_id: "trust_zone_sealed_private",
              label: "Trust zone: Sealed private / Vault",
              value: "sealed",
              state: "inactive",
              source: source("Trust-zone authority"),
              category: "trust_zones",
              mutation_classification: "hard-prohibited-by-default",
              mutation_risk: "critical",
              mutation_allowed: false,
              approval_required: false,
              mutation_reason: "Governance mutation never grants ordinary vault access."
            }
          ]
        }
      }
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("shows exact mutability truth without presenting cosmetic authority", async () => {
    const onRightDrawerSectionsChange = vi.fn();
    render(
      <GovernancePage
        startupReady
        onRightDrawerSectionsChange={onRightDrawerSectionsChange}
      />
    );

    expect(
      await screen.findByText("No current production Governance control is live-editable.")
    ).toBeInTheDocument();
    expect(screen.getAllByText("Read-only").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Hard-prohibited by default").length).toBeGreaterThan(0);
    expect(screen.getByText("The local bridge boundary is constitutional law.")).toBeInTheDocument();
    expect(screen.getByText("Silent cloud fallback is prohibited.")).toBeInTheDocument();
    expect(
      screen.getByText("Governance mutation never grants ordinary vault access.")
    ).toBeInTheDocument();
    expect(screen.getByText("State version: 111111111111")).toBeInTheDocument();
    expect(screen.getByText("Adaptive cognition policy in force")).toBeInTheDocument();
    expect(screen.getByText("6 available · Automatic")).toBeInTheDocument();

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(bridgeClientMocks.planGovernanceChange).not.toHaveBeenCalled();
    expect(bridgeClientMocks.applyGovernanceChange).not.toHaveBeenCalled();
    expect(bridgeClientMocks.restoreGovernanceChange).not.toHaveBeenCalled();
    expect(bridgeClientMocks.resolveGovernanceApproval).not.toHaveBeenCalled();

    await waitFor(() => {
      const calls = onRightDrawerSectionsChange.mock.calls;
      const latestSections = calls[calls.length - 1]?.[0] ?? [];
      const serialized = JSON.stringify(latestSections);
      expect(serialized).toContain("Live-editable controls");
      expect(serialized).toContain("governance-mutation-contract-1.0");
    });
  });
});

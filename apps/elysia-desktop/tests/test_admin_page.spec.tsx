import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminPage from "../src/AdminPage";

const bridgeMocks = vi.hoisted(() => ({
  fetchAdminSummary: vi.fn(),
  previewAdminChange: vi.fn(),
  applyAdminChange: vi.fn(),
  createAccount: vi.fn()
}));

vi.mock("../src/api/bridgeClient", () => bridgeMocks);

describe("content-blind local Admin authority", () => {
  beforeEach(() => {
    for (const value of Object.values(bridgeMocks)) value.mockReset();
    bridgeMocks.fetchAdminSummary.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        data: {
          roster: [
            {
              user_id: "owner-synthetic",
              username: "owner",
              role: "installation_owner",
              managed: false,
              enabled: true,
              active_session_count: 1,
              policy_version: 1,
              created_at_utc: "2026-08-22T00:00:00Z"
            },
            {
              user_id: "managed-synthetic",
              username: "managed",
              role: "user",
              managed: true,
              enabled: true,
              active_session_count: 0,
              policy_version: 2,
              created_at_utc: "2026-08-22T00:01:00Z",
              managed_policy: {
                autonomy_maximum: 2,
                internet_allowed: false,
                addons_allowed: false,
                connectors_allowed: false,
                coding_execution_allowed: false,
                project_agent_limit: 0,
                external_mutations_allowed: false,
                background_cognition_allowed: false,
                cpu_percent_ceiling: 40,
                ram_mb_ceiling: 2048,
                vram_mb_ceiling: 1024,
                network_filter_level: "strict"
              }
            }
          ],
          events: [{
            event_id: "event-synthetic",
            event_type: "managed_policy_operation_blocked",
            safe_summary: "managed policy operation blocked",
            created_at_utc: "2026-08-22T00:02:00Z"
          }],
          content_authorities_queried: [],
          admin_content_access_granted: false,
          local_online_identity_federated: false
        }
      }
    });
    bridgeMocks.previewAdminChange.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        data: {
          preview_id: "preview-synthetic",
          approval_token: "synthetic-one-time-token",
          before: { enabled: true },
          after: { enabled: false }
        }
      }
    });
    bridgeMocks.applyAdminChange.mockResolvedValue({
      ok: true, payload: { status: "ok", data: { applied: true } }
    });
    bridgeMocks.createAccount.mockResolvedValue({
      ok: true, payload: { status: "ok", data: {} }
    });
  });

  afterEach(cleanup);

  it("shows installation truth, disclosed supervision, and exact preview/apply controls", async () => {
    const onDrawer = vi.fn();
    const view = render(<AdminPage onRightDrawerSectionsChange={onDrawer} />);

    expect(await screen.findByText("owner")).toBeInTheDocument();
    expect(screen.getByText("managed")).toBeInTheDocument();
    expect(screen.getByText("Managed / visibly supervised")).toBeInTheDocument();
    expect(screen.getByText(/not a content-superuser/i)).toBeInTheDocument();
    expect(screen.getByText(/never creates, federates, or elevates/i)).toBeInTheDocument();
    expect(screen.queryByText(/memory body|conversation body|prompt text/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Managed storage ceiling MiB"), {
      target: { value: "8192" }
    });
    // A parent render must not replace the editor's in-progress draft with a
    // newly allocated policy object before the explicit preview action.
    view.rerender(<AdminPage onRightDrawerSectionsChange={onDrawer} />);
    await waitFor(() => expect(
      screen.getByLabelText("Managed storage ceiling MiB")
    ).toHaveValue(8192));
    fireEvent.click(screen.getByRole("button", { name: "Preview managed memory ceilings" }));
    expect(bridgeMocks.previewAdminChange).toHaveBeenCalledWith(expect.objectContaining({
      target_user_id: "managed-synthetic",
      change_kind: "set_managed_policy",
      managed: true,
      managed_policy: expect.objectContaining({ storage_budget_mb_ceiling: 8192 })
    }));
    await screen.findByText("Exact change preview");
    await waitFor(() => expect(
      screen.getByRole("button", { name: "Preview disable" })
    ).not.toBeDisabled());

    fireEvent.click(screen.getByRole("button", { name: "Preview disable" }));
    await waitFor(() => expect(bridgeMocks.previewAdminChange).toHaveBeenCalledWith(
      expect.objectContaining({
        target_user_id: "managed-synthetic",
        change_kind: "set_account_enabled",
        enabled: false
      })
    ));
    fireEvent.click(screen.getByRole("button", { name: "Apply reviewed change" }));
    await waitFor(() => expect(bridgeMocks.applyAdminChange).toHaveBeenCalledWith(
      "preview-synthetic", "synthetic-one-time-token"
    ));

    const drawer = JSON.stringify(onDrawer.mock.calls.at(-1)?.[0] ?? []);
    expect(drawer).toContain("Installation governance only");
    expect(drawer).toContain("Separate authority; no federation");
  });
});

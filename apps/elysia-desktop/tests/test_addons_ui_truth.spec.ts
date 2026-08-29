import React from "react";
import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildSafeAddonAuditRows,
  buildSafeAddonResultFacts,
  LocalInstallerPanel,
  sanitizeAddonUiMessage
} from "../src/AddonsPage";

describe("Add-ons UI truth", () => {
  afterEach(() => {
    cleanup();
  });

  it("builds result facts from an explicit allowlist without exposing raw paths or private fields", () => {
    const facts = buildSafeAddonResultFacts({
      addon_id: "example.addon",
      version: "1.0.0",
      status: "enabled_limited",
      execution_enabled: false,
      package_path: "/home/private/addons/example.elysia-addon",
      token: "do-not-render",
      inspection: {
        manifest: {
          manifest_hash: "sha256-safe",
          credential: "do-not-render"
        }
      }
    });

    expect(facts).toEqual(expect.arrayContaining([
      { label: "Add-on", value: "example.addon" },
      { label: "Version", value: "1.0.0" },
      { label: "Registry state", value: "enabled_limited" },
      { label: "Execution enabled", value: "No" },
      { label: "Manifest hash", value: "sha256-safe" }
    ]));

    const rendered = JSON.stringify(facts);
    expect(rendered).not.toContain("/home/private");
    expect(rendered).not.toContain("do-not-render");
    expect(rendered).not.toContain("package_path");
    expect(rendered).not.toContain("token");
    expect(rendered).not.toContain("credential");
  });

  it("summarizes audit rows without serializing details or raw local paths", () => {
    const rows = buildSafeAddonAuditRows([
      {
        timestamp_utc: "2026-08-14T12:00:00Z",
        action: "enable",
        addon_id: "example.addon",
        result: "recorded",
        reason_code: "exact_local_transition",
        details: {
          path: "/tmp/private-package",
          secret: "do-not-render"
        }
      }
    ]);

    expect(rows).toEqual([
      {
        timestamp: "2026-08-14T12:00:00Z",
        action: "enable",
        addon: "example.addon",
        result: "recorded",
        reason: "exact_local_transition"
      }
    ]);
    expect(JSON.stringify(rows)).not.toContain("/tmp/private-package");
    expect(JSON.stringify(rows)).not.toContain("do-not-render");
  });

  it("sanitizes path and secret-shaped error details before displaying them", () => {
    const message = sanitizeAddonUiMessage(
      "Failed at /home/example/private/file token=abc123 password:letmein"
    );

    expect(message).toContain("[local path hidden]");
    expect(message).toContain("token=[private value hidden]");
    expect(message).toContain("password=[private value hidden]");
    expect(message).not.toContain("/home/example");
    expect(message).not.toContain("abc123");
    expect(message).not.toContain("letmein");

    expect(sanitizeAddonUiMessage("Failed at /etc/elysia/config.yaml")).toBe(
      "Failed at [local path hidden]"
    );
  });

  it("labels local add-on controls as planned governed transitions, never direct execution", () => {
    render(
      React.createElement(LocalInstallerPanel, {
        packagePath: "",
        setPackagePath: vi.fn(),
        status: {
          installed_count: 1,
          enabled_count: 1,
          sandbox_mode: "validation_only",
          addons_root: "/home/private/addons"
        },
        installed: [
          {
            addon_id: "example.addon",
            name: "Example add-on",
            version: "1.0.0",
            status: "installed_disabled",
            package_path: "/home/private/addons/example.addon"
          }
        ],
        audit: [],
        result: null,
        officialCandidates: [
          {
            addon_id: "org.ecosyneva.codev",
            name: "Codev",
            listing_state: "official_v1_release",
            required_profile: "developer",
            version: "1.0.0",
            install_action_live: true,
            public_distribution_supported: true,
            in_app_install_control_live: false
          }
        ],
        onRefresh: vi.fn(),
        onPackageAction: vi.fn(),
        onInstalledAction: vi.fn()
      })
    );

    expect(screen.getByText("Local package staging")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Plan disabled staging" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Plan limited enable · no execution" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Plan registry removal · retain files" })).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(screen.getByText(/Installed does not mean enabled/)).toBeInTheDocument();
    expect(screen.getByText(/Codev is the official stable v1.0.0 Developer-profile add-on/)).toBeInTheDocument();
    expect(screen.getByText("Reviewed VSIX CLI contract live")).toBeInTheDocument();
    expect(screen.getByText("Public distribution")).toBeInTheDocument();
    expect(screen.getByText(/No upload action is available/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enable" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /install codev/i })).not.toBeInTheDocument();
    expect(screen.queryByText("/home/private/addons")).not.toBeInTheDocument();
  });

  it("renders only allowlisted exact-plan facts and applies through the approval callback", () => {
    const apply = vi.fn();
    render(
      React.createElement(LocalInstallerPanel, {
        packagePath: "",
        setPackagePath: vi.fn(),
        status: { installed_count: 0, enabled_count: 0 },
        installed: [],
        audit: [],
        result: null,
        pendingPlan: {
          plan_id: "plan-safe",
          plan_hash: "sha256-safe",
          plan_state: "ready_for_exact_approval",
          action: "install_disabled",
          addon_id: "example.addon",
          current_state: "packaged",
          proposed_state: "installed_disabled",
          package_hash: "package-safe",
          execution_enabled: false,
          bridge_enabled: false,
          files_retained: true,
          approval_token: "do-not-render",
          package_path: "/home/private/package.elysia-addon"
        },
        onRefresh: vi.fn(),
        onPackageAction: vi.fn(),
        onInstalledAction: vi.fn(),
        onApplyPending: apply
      })
    );

    expect(screen.getByText("Exact non-executing change")).toBeInTheDocument();
    expect(screen.getByText("installed_disabled")).toBeInTheDocument();
    screen.getByRole("button", { name: "Approve and apply exact non-executing change" }).click();
    expect(apply).toHaveBeenCalledOnce();
    expect(screen.queryByText("do-not-render")).not.toBeInTheDocument();
    expect(screen.queryByText("/home/private/package.elysia-addon")).not.toBeInTheDocument();
  });

  it("keeps direct legacy mutations and raw manifest serialization out of the chamber", () => {
    const source = readFileSync("src/AddonsPage.tsx", "utf-8");
    expect(source).toContain("approveAndApplyLocalAddonTransition");
    expect(source).toContain("planLocalAddonLifecycleAction");
    expect(source).not.toContain("installLocalAddonDisabled");
    expect(source).not.toContain("enableLocalAddon");
    expect(source).not.toContain("disableLocalAddon");
    expect(source).not.toContain("removeLocalAddon");
    expect(source).not.toContain("rollbackLocalAddon");
    expect(source).not.toContain("JSON.stringify(preview.addon");
  });
});

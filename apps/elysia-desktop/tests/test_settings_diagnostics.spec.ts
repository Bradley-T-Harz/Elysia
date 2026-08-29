import { describe, expect, it } from "vitest";

import { DEFAULT_DESKTOP_PREFERENCES } from "../src/desktopPreferences";
import type { DesktopPreferences } from "../src/desktopPreferences";
import {
  buildSanitizedSettingsSummary,
  sanitizeSettingsDisplayValue,
  sanitizeSettingsIdentifier
} from "../src/settingsDiagnostics";

describe("Settings diagnostics sanitization", () => {
  it("allows bounded status text and local model identifiers", () => {
    expect(sanitizeSettingsDisplayValue("narrow / approval-gated")).toBe(
      "narrow / approval-gated"
    );
    expect(sanitizeSettingsIdentifier("qwen2.5-coder:7b")).toBe(
      "qwen2.5-coder:7b"
    );
  });

  it("rejects paths, URLs, control characters, secret assignments, and secret-like identifiers", () => {
    [
      "/home/operator/private/settings.yaml",
      "../vault/model.bin",
      "file:///tmp/private.log",
      "https://example.invalid/status",
      "token=TOKEN_MARKER",
      "password: PASSWORD_MARKER",
      "line one\nline two",
      "-----BEGIN PRIVATE KEY-----"
    ].forEach((value) => {
      expect(sanitizeSettingsDisplayValue(value)).toBeNull();
    });

    ["vault-model", "private_key", "credential-cache", "secret-token"].forEach(
      (value) => {
        expect(sanitizeSettingsIdentifier(value)).toBeNull();
      }
    );
  });

  it("builds summaries from an allowlist and drops hostile backend values", () => {
    const summary = buildSanitizedSettingsSummary({
      preferences: {
        ...DEFAULT_DESKTOP_PREFERENCES,
        density: "secret=LOCAL_PREFERENCE_MARKER",
        startupRoom: "/home/operator/PREFERENCE_PATH_MARKER"
      } as unknown as DesktopPreferences,
      desktopVersion: "password=DESKTOP_SECRET_MARKER",
      apiVersion: "/home/operator/API_PATH_MARKER",
      bridgeState: "/var/log/BRIDGE_LOG_MARKER",
      runtimeState: "token=RUNTIME_TOKEN_MARKER",
      capabilityState: "credential=CAPABILITY_CREDENTIAL_MARKER",
      invokerState: "secret=INVOKER_SECRET_MARKER",
      ollamaReachable: true,
      selectedRole: "logs/ROLE_LOG_MARKER/private.log",
      selectedRuntime: "/home/operator/RUNTIME_PATH_MARKER",
      selectedModelRuntimeTag: "vault/MODEL_TOKEN_MARKER/credentials.json",
      activeProfileLabel: "/home/operator/PROFILE_PATH_MARKER",
      profileResolutionState: "secret=PROFILE_SECRET_MARKER",
      profileReadiness: "credentials/PROFILE_CREDENTIAL_MARKER/private.json",
      localOverrideState: "/var/log/OVERRIDE_LOG_MARKER",
      missingCoreDependencyCount: -1,
      doctorExecuted: false
    });

    expect(summary).toContain("Elysia sanitized settings summary");
    expect(summary).toContain("Components: Desktop unavailable • API unavailable");
    expect(summary).toContain(
      "Local body: bridge unavailable • runtime unavailable • capabilities unavailable"
    );
    expect(summary).toContain("Provider: Ollama reachable");
    expect(summary).toContain(
      "Install profile: unavailable • resolution unavailable • readiness unavailable"
    );
    expect(summary).toContain(
      "Profile checks: Core missing unavailable • overrides unavailable • doctor not executed"
    );
    expect(summary).toContain(
      "Preferences: density comfortable • rail collapsed • startup home • motion system"
    );

    [
      "/home/",
      "/var/log/",
      "DESKTOP_SECRET_MARKER",
      "API_PATH_MARKER",
      "BRIDGE_LOG_MARKER",
      "RUNTIME_TOKEN_MARKER",
      "CAPABILITY_CREDENTIAL_MARKER",
      "INVOKER_SECRET_MARKER",
      "ROLE_LOG_MARKER",
      "RUNTIME_PATH_MARKER",
      "MODEL_TOKEN_MARKER",
      "LOCAL_PREFERENCE_MARKER",
      "PREFERENCE_PATH_MARKER",
      "credentials.json",
      "PROFILE_PATH_MARKER",
      "PROFILE_SECRET_MARKER",
      "PROFILE_CREDENTIAL_MARKER",
      "OVERRIDE_LOG_MARKER"
    ].forEach((privateMarker) => {
      expect(summary).not.toContain(privateMarker);
    });
  });
});

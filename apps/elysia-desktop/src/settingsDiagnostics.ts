import {
  normalizeDesktopPreferences,
  type DesktopPreferences
} from "./desktopPreferences";

export const ELYSIA_V1_RELEASE_TRUTH = {
  targetVersion: "1.0.0",
  currentChannel: "stable"
} as const;

const CONTROL_CHARACTER_PATTERN = /[\u0000-\u001f\u007f]/;
const PATH_LIKE_PATTERN =
  /(?:^|[\s("'=])(?:~[\\/]|\/(?:[^/\s]+\/)+[^/\s]*|[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|\.{1,2}[\\/]|[^\s/]+\/(?:[^\s/]+\/)+[^\s/]*)/;
const URL_PATTERN = /\b(?:file|https?):\/\//i;
const SECRET_ASSIGNMENT_PATTERN =
  /\b(?:api[_ -]?key|secret|token|credential|password|authorization|bearer)\b\s*[:=]\s*\S+/i;
const SECRET_MARKER_PATTERN = /-----BEGIN [A-Z ]*PRIVATE KEY-----/i;
const SENSITIVE_IDENTIFIER_PATTERN =
  /(?:secret|token|credential|password|private[_-]?key|vault)/i;

const SAFE_SUMMARY_STATES = new Set([
  "Live",
  "Display-only",
  "Planned",
  "Inactive",
  "Unavailable",
  "Degraded",
  "Blocked"
]);

export function sanitizeSettingsDisplayValue(value: unknown): string | null {
  if (
    typeof value !== "string" &&
    typeof value !== "number" &&
    typeof value !== "boolean"
  ) {
    return null;
  }

  const text = String(value).trim();

  if (
    !text ||
    text.length > 160 ||
    CONTROL_CHARACTER_PATTERN.test(text) ||
    PATH_LIKE_PATTERN.test(text) ||
    URL_PATTERN.test(text) ||
    SECRET_ASSIGNMENT_PATTERN.test(text) ||
    SECRET_MARKER_PATTERN.test(text)
  ) {
    return null;
  }

  return text;
}

export function sanitizeSettingsIdentifier(value: unknown): string | null {
  const text = sanitizeSettingsDisplayValue(value);

  if (
    !text ||
    text.length > 80 ||
    SENSITIVE_IDENTIFIER_PATTERN.test(text) ||
    !/^[A-Za-z0-9][A-Za-z0-9._:@+ ()-]*$/.test(text)
  ) {
    return null;
  }

  return text;
}

function safeSummaryState(value: unknown): string {
  return typeof value === "string" && SAFE_SUMMARY_STATES.has(value)
    ? value.toLowerCase()
    : "unavailable";
}

export type SanitizedSettingsSummaryInput = {
  preferences: DesktopPreferences;
  desktopVersion: unknown;
  apiVersion?: unknown;
  bridgeState: unknown;
  runtimeState: unknown;
  capabilityState: unknown;
  invokerState: unknown;
  ollamaReachable?: boolean | null;
  selectedRole?: unknown;
  selectedRuntime?: unknown;
  selectedModelRuntimeTag?: unknown;
  activeProfileLabel?: unknown;
  profileResolutionState?: unknown;
  profileReadiness?: unknown;
  localOverrideState?: unknown;
  missingCoreDependencyCount?: unknown;
  doctorExecuted?: boolean | null;
};

export function buildSanitizedSettingsSummary(
  input: SanitizedSettingsSummaryInput
): string {
  const preferences = normalizeDesktopPreferences(input.preferences);
  const desktopVersion = sanitizeSettingsIdentifier(input.desktopVersion) ?? "unavailable";
  const apiVersion = sanitizeSettingsIdentifier(input.apiVersion) ?? "unavailable";
  const selectedRole = sanitizeSettingsIdentifier(input.selectedRole);
  const selectedRuntime = sanitizeSettingsIdentifier(input.selectedRuntime);
  const selectedModel = sanitizeSettingsIdentifier(input.selectedModelRuntimeTag);
  const activeProfile = sanitizeSettingsDisplayValue(input.activeProfileLabel);
  const profileResolution = sanitizeSettingsIdentifier(input.profileResolutionState);
  const profileReadiness = sanitizeSettingsIdentifier(input.profileReadiness);
  const localOverrideState = sanitizeSettingsIdentifier(input.localOverrideState);
  const missingCoreDependencyCount =
    typeof input.missingCoreDependencyCount === "number" &&
    Number.isSafeInteger(input.missingCoreDependencyCount) &&
    input.missingCoreDependencyCount >= 0
      ? input.missingCoreDependencyCount
      : null;
  const providerState =
    input.ollamaReachable === true
      ? "Ollama reachable"
      : input.ollamaReachable === false
        ? "Ollama unavailable"
        : "Ollama status not surfaced";
  const invokerParts = [
    safeSummaryState(input.invokerState),
    selectedRuntime ? `runtime ${selectedRuntime}` : "",
    selectedRole ? `role ${selectedRole}` : "",
    selectedModel ? `model ${selectedModel}` : ""
  ].filter(Boolean);

  return [
    "Elysia sanitized settings summary",
    `Release: ${ELYSIA_V1_RELEASE_TRUTH.currentChannel} • target ${ELYSIA_V1_RELEASE_TRUTH.targetVersion}`,
    `Components: Desktop ${desktopVersion} • API ${apiVersion}`,
    `Install profile: ${activeProfile ?? "unavailable"} • resolution ${profileResolution ?? "unavailable"} • readiness ${profileReadiness ?? "unavailable"}`,
    `Profile checks: Core missing ${missingCoreDependencyCount ?? "unavailable"} • overrides ${localOverrideState ?? "unavailable"} • doctor ${input.doctorExecuted === true ? "executed" : "not executed"}`,
    `Preferences: density ${preferences.density} • rail ${preferences.leftRailDefaultBehavior} • startup ${preferences.startupRoom} • motion ${preferences.motionPreference}`,
    `Local body: bridge ${safeSummaryState(input.bridgeState)} • runtime ${safeSummaryState(input.runtimeState)} • capabilities ${safeSummaryState(input.capabilityState)}`,
    `Provider: ${providerState}`,
    `Invoker / model: ${invokerParts.join(" • ")}`,
    "External boundary: local-first default • profile and approval gated • silent cloud fallback prohibited",
    "Sandbox / workers: read-only profile truth only • local doctor proof required • none enabled here • no cloud sandbox required",
    "Content boundary: bounded status fields only; private content is not included"
  ].join("\n");
}

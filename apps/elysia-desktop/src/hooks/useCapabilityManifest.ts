import { useEffect, useState } from "react";
import {
  fetchCapabilityManifest,
  type BridgeStartupState
} from "../api/bridgeClient";

export type CapabilitySurfaceState =
  | "live"
  | "partial"
  | "planned"
  | "inactive"
  | "unavailable"
  | "degraded"
  | "blocked"
  | string;

export type CapabilityManifestEntry = {
  capabilityKey: string;
  displayName: string;
  group: string;
  state: CapabilitySurfaceState;
  summary: string;
  locality: string;
  approvalState: string;
  readOnly: boolean;
  uiSurfaces: string[];
  supportingEndpoint: string;
  notes: string[];
};

type CapabilityManifestData = {
  capability_catalog_state?: unknown;
  capability_count?: unknown;
  capability_groups?: unknown;
  capabilities?: unknown;
};

type CapabilityManifestEnvelope = {
  contract_version?: string;
  status?: string;
  capability_state?: string;
  warnings?: unknown;
  errors?: unknown;
  data?: CapabilityManifestData;
};

type UseCapabilityManifestResult = {
  capabilityStartupState: BridgeStartupState;
  capabilityStatusMessage: string;
  capabilityStatusDetail: string;
  capabilityContractVersion: string;
  capabilityCatalogState: string;
  capabilityCount: number;
  capabilityGroups: string[];
  capabilityWarnings: string[];
  capabilities: CapabilityManifestEntry[];
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  return null;
}

function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => asString(item))
    .filter((item) => item.trim().length > 0);
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();

    if (normalized === "true") {
      return true;
    }

    if (normalized === "false") {
      return false;
    }
  }

  return fallback;
}

function normalizeCapabilityEntry(
  value: unknown
): CapabilityManifestEntry | null {
  const record = asRecord(value);

  if (!record) {
    return null;
  }

  const capabilityKey = asString(record.capability_key).trim();

  if (!capabilityKey) {
    return null;
  }

  return {
    capabilityKey,
    displayName: asString(record.display_name, capabilityKey),
    group: asString(record.group, "uncategorized"),
    state: asString(record.state, "unknown"),
    summary: asString(record.summary),
    locality: asString(record.locality, "unknown"),
    approvalState: asString(record.approval_state, "unknown"),
    readOnly: asBoolean(record.read_only, false),
    uiSurfaces: asStringArray(record.ui_surfaces),
    supportingEndpoint: asString(record.supporting_endpoint),
    notes: asStringArray(record.notes)
  };
}

export function useCapabilityManifest(): UseCapabilityManifestResult {
  const [capabilityStartupState, setCapabilityStartupState] =
    useState<BridgeStartupState>("checking");
  const [capabilityStatusMessage, setCapabilityStatusMessage] = useState(
    "Checking capability manifest..."
  );
  const [capabilityStatusDetail, setCapabilityStatusDetail] = useState(
    "No verified capability manifest yet."
  );
  const [capabilityContractVersion, setCapabilityContractVersion] = useState("");
  const [capabilityCatalogState, setCapabilityCatalogState] = useState("");
  const [capabilityCount, setCapabilityCount] = useState(0);
  const [capabilityGroups, setCapabilityGroups] = useState<string[]>([]);
  const [capabilityWarnings, setCapabilityWarnings] = useState<string[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityManifestEntry[]>(
    []
  );

  useEffect(() => {
    let cancelled = false;

    async function queryCapabilityManifest() {
      setCapabilityStartupState("checking");
      setCapabilityStatusMessage("Checking capability manifest...");
      setCapabilityStatusDetail(
        "Waiting for /status/capabilities response from the local bridge."
      );
      setCapabilityCatalogState("");
      setCapabilityCount(0);
      setCapabilityGroups([]);
      setCapabilityWarnings([]);
      setCapabilities([]);

      try {
        const { ok, payload } = await fetchCapabilityManifest();

        if (cancelled) {
          return;
        }

        const envelope = payload as CapabilityManifestEnvelope;
        const envelopeStatus = envelope.status ?? "unknown";
        const capabilityState = envelope.capability_state ?? "unknown";
        const warnings = asStringArray(envelope.warnings);
        const errors = asStringArray(envelope.errors);
        const manifestData = envelope.data ?? {};
        const rawCapabilities = Array.isArray(manifestData.capabilities)
          ? manifestData.capabilities
          : [];
        const normalizedCapabilities = rawCapabilities
          .map(normalizeCapabilityEntry)
          .filter(
            (entry): entry is CapabilityManifestEntry => entry !== null
          );

        setCapabilityContractVersion(envelope.contract_version ?? "");
        setCapabilityCatalogState(
          asString(manifestData.capability_catalog_state, capabilityState)
        );
        setCapabilityCount(
          asNumber(manifestData.capability_count, normalizedCapabilities.length)
        );
        setCapabilityGroups(asStringArray(manifestData.capability_groups));
        setCapabilityWarnings(warnings);
        setCapabilities(normalizedCapabilities);

        const errorText =
          errors.length > 0
            ? errors.join(" ")
            : "No additional capability-manifest error details were returned.";

        if (
          !ok ||
          envelopeStatus === "unavailable" ||
          capabilityState === "unavailable"
        ) {
          setCapabilityStartupState("unavailable");
          setCapabilityStatusMessage("Capability manifest unavailable");
          setCapabilityStatusDetail(errorText);
          return;
        }

        if (
          envelopeStatus === "degraded" ||
          capabilityState === "degraded"
        ) {
          setCapabilityStartupState("degraded");
          setCapabilityStatusMessage("Capability manifest reachable but degraded");
          setCapabilityStatusDetail(
            `Envelope status: ${envelopeStatus}. Capability state: ${capabilityState}.`
          );
          return;
        }

        if (envelopeStatus === "ok") {
          setCapabilityStartupState("ok");
          setCapabilityStatusMessage("Capability manifest loaded");
          setCapabilityStatusDetail(
            warnings.length > 0
              ? warnings.join(" ")
              : "Capability truth was retrieved from the local API bridge."
          );
          return;
        }

        setCapabilityStartupState("error");
        setCapabilityStatusMessage(
          "Capability manifest returned an unexpected status"
        );
        setCapabilityStatusDetail(
          `Envelope status: ${envelopeStatus}. Capability state: ${capabilityState}.`
        );
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message =
          error instanceof Error
            ? error.message
            : "Unknown capability-manifest query failure.";

        setCapabilityStartupState("error");
        setCapabilityStatusMessage("Capability manifest query failed");
        setCapabilityStatusDetail(message);
        setCapabilityCatalogState("");
        setCapabilityCount(0);
        setCapabilityGroups([]);
        setCapabilityWarnings([]);
        setCapabilities([]);
      }
    }

    void queryCapabilityManifest();

    return () => {
      cancelled = true;
    };
  }, []);

  return {
    capabilityStartupState,
    capabilityStatusMessage,
    capabilityStatusDetail,
    capabilityContractVersion,
    capabilityCatalogState,
    capabilityCount,
    capabilityGroups,
    capabilityWarnings,
    capabilities
  };
}

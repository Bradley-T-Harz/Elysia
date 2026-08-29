import { useEffect, useState } from "react";
import {
  fetchBridgeHealth,
  type BridgeStartupState
} from "../api/bridgeClient";

type UseBridgeHealthResult = {
  bridgeStartupState: BridgeStartupState;
  bridgeStatusMessage: string;
  bridgeStatusDetail: string;
  bridgeApiVersion: string;
  bridgeContractVersion: string;
};

export function useBridgeHealth(): UseBridgeHealthResult {
  const [bridgeStartupState, setBridgeStartupState] =
    useState<BridgeStartupState>("checking");
  const [bridgeStatusMessage, setBridgeStatusMessage] = useState(
    "Checking local API bridge truth..."
  );
  const [bridgeStatusDetail, setBridgeStatusDetail] = useState(
    "No verified startup truth yet."
  );
  const [bridgeApiVersion, setBridgeApiVersion] = useState("");
  const [bridgeContractVersion, setBridgeContractVersion] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function queryApiBridgeStatus() {
      setBridgeStartupState("checking");
      setBridgeStatusMessage("Checking local API bridge truth...");
      setBridgeStatusDetail(
        "Waiting for /status/health response from the local bridge."
      );

      try {
        const { ok, payload } = await fetchBridgeHealth();

        if (cancelled) {
          return;
        }

        setBridgeApiVersion(payload.api_version ?? "");
        setBridgeContractVersion(payload.contract_version ?? "");

        const envelopeStatus = payload.status ?? "unknown";
        const capabilityState = payload.capability_state ?? "unknown";
        const healthState = payload.data?.health_state ?? "unknown";
        const healthy = payload.data?.healthy;
        const errorText =
          payload.errors && payload.errors.length > 0
            ? payload.errors.join(" ")
            : "No additional bridge error details were returned.";

        if (!ok || envelopeStatus === "unavailable" || capabilityState === "unavailable") {
          setBridgeStartupState("unavailable");
          setBridgeStatusMessage("API bridge unavailable");
          setBridgeStatusDetail(errorText);
          return;
        }

        if (
          envelopeStatus === "degraded" ||
          capabilityState === "degraded" ||
          healthState === "degraded" ||
          healthy === false
        ) {
          setBridgeStartupState("degraded");
          setBridgeStatusMessage("API bridge reachable but degraded");
          setBridgeStatusDetail(
            `Health state: ${healthState}. Runtime reachable: ${String(
              payload.data?.runtime_reachable ?? "unknown"
            )}. Ollama reachable: ${String(
              payload.data?.ollama_reachable ?? "unknown"
            )}.`
          );
          return;
        }

        if (envelopeStatus === "ok" && healthState === "healthy") {
          setBridgeStartupState("ok");
          setBridgeStatusMessage("API bridge healthy");
          setBridgeStatusDetail(
            `Health state: ${healthState}. Runtime reachable: ${String(
              payload.data?.runtime_reachable ?? "unknown"
            )}. Ollama reachable: ${String(
              payload.data?.ollama_reachable ?? "unknown"
            )}.`
          );
          return;
        }

        setBridgeStartupState("error");
        setBridgeStatusMessage("API bridge returned an unexpected status");
        setBridgeStatusDetail(
          `Envelope status: ${envelopeStatus}. Capability state: ${capabilityState}. Health state: ${healthState}.`
        );
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message =
          error instanceof Error ? error.message : "Unknown bridge query failure.";

        setBridgeStartupState("error");
        setBridgeStatusMessage("API bridge query failed");
        setBridgeStatusDetail(message);
      }
    }

    void queryApiBridgeStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  return {
    bridgeStartupState,
    bridgeStatusMessage,
    bridgeStatusDetail,
    bridgeApiVersion,
    bridgeContractVersion
  };
}

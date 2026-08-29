import { useMemo } from "react";
import type { BridgeStartupState } from "../api/bridgeClient";
import { useBridgeHealth } from "./useBridgeHealth";
import { useRuntimeStatus } from "./useRuntimeStatus";
import { useInvokerStatus } from "./useInvokerStatus";
import type { RuntimeTruthSnapshot } from "./useRuntimeStatus";
import type { InvokerTruthSnapshot } from "./useInvokerStatus";
import { useCapabilityManifest } from "./useCapabilityManifest";

type UseStartupTruthResult = {
  startupTruthState: BridgeStartupState;
  startupTruthMessage: string;
  startupTruthDetail: string;
  startupReady: boolean;
  bridgeApiVersion: string;
  bridgeContractVersion: string;
  runtimeContractVersion: string;
  invokerContractVersion: string;
  capabilityContractVersion: string;
  runtimeTruth: RuntimeTruthSnapshot | null;
  invokerTruth: InvokerTruthSnapshot | null;
};

export function useStartupTruth(): UseStartupTruthResult {
  const bridge = useBridgeHealth();
  const runtime = useRuntimeStatus();
  const invoker = useInvokerStatus();
  const capabilities = useCapabilityManifest();

  const startupTruthState = useMemo<BridgeStartupState>(() => {
    const states: BridgeStartupState[] = [
      bridge.bridgeStartupState,
      runtime.runtimeStartupState,
      invoker.invokerStartupState,
      capabilities.capabilityStartupState
    ];

    if (states.includes("error")) {
      return "error";
    }

    if (states.includes("unavailable")) {
      return "unavailable";
    }

    if (states.includes("degraded")) {
      return "degraded";
    }

    if (states.includes("checking")) {
      return "checking";
    }

    return "ok";
  }, [
    bridge.bridgeStartupState,
    runtime.runtimeStartupState,
    invoker.invokerStartupState,
    capabilities.capabilityStartupState
  ]);

  const startupTruthMessage = useMemo(() => {
    switch (startupTruthState) {
      case "ok":
        return "Startup truth verified";
      case "degraded":
        return "Startup truth loaded with degraded surfaces";
      case "unavailable":
        return "Startup truth incomplete: required surfaces unavailable";
      case "error":
        return "Startup truth query failed";
      case "checking":
      default:
        return "Checking startup truth...";
    }
  }, [startupTruthState]);

  const startupTruthDetail = useMemo(() => {
    return [
      bridge.bridgeStatusMessage,
      runtime.runtimeStatusMessage,
      invoker.invokerStatusMessage,
      capabilities.capabilityStatusMessage
    ].join(" • ");
  }, [
    bridge.bridgeStatusMessage,
    runtime.runtimeStatusMessage,
    invoker.invokerStatusMessage,
    capabilities.capabilityStatusMessage
  ]);

  return {
    startupTruthState,
    startupTruthMessage,
    startupTruthDetail,
    startupReady: startupTruthState === "ok",
    bridgeApiVersion: bridge.bridgeApiVersion,
    bridgeContractVersion: bridge.bridgeContractVersion,
    runtimeContractVersion: runtime.runtimeContractVersion,
    invokerContractVersion: invoker.invokerContractVersion,
    capabilityContractVersion: capabilities.capabilityContractVersion,
    runtimeTruth: runtime.runtimeTruth,
    invokerTruth: invoker.invokerTruth
  };
}

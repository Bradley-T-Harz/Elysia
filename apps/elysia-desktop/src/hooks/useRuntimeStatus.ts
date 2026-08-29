import { useEffect, useState } from "react";
import {
  fetchRuntimeStatus,
  type BridgeStartupState,
  type RuntimeStatusEnvelope
} from "../api/bridgeClient";

export type RuntimeTruthSnapshot = NonNullable<RuntimeStatusEnvelope["data"]>;

type UseRuntimeStatusResult = {
  runtimeStartupState: BridgeStartupState;
  runtimeStatusMessage: string;
  runtimeStatusDetail: string;
  runtimeContractVersion: string;
  runtimeStateLabel: string;
  runtimeTruth: RuntimeTruthSnapshot | null;
};

export function useRuntimeStatus(): UseRuntimeStatusResult {
  const [runtimeStartupState, setRuntimeStartupState] =
    useState<BridgeStartupState>("checking");
  const [runtimeStatusMessage, setRuntimeStatusMessage] = useState(
    "Checking local runtime truth..."
  );
  const [runtimeStatusDetail, setRuntimeStatusDetail] = useState(
    "No verified runtime status yet."
  );
  const [runtimeContractVersion, setRuntimeContractVersion] = useState("");
  const [runtimeStateLabel, setRuntimeStateLabel] = useState("unknown");
  const [runtimeTruth, setRuntimeTruth] = useState<RuntimeTruthSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function queryRuntimeStatus() {
      setRuntimeStartupState("checking");
      setRuntimeStatusMessage("Checking local runtime truth...");
      setRuntimeStatusDetail(
        "Waiting for /status/runtime response from the local bridge."
      );

      try {
        const { ok, payload } = await fetchRuntimeStatus();

        if (cancelled) {
          return;
        }

        setRuntimeContractVersion(payload.contract_version ?? "");
        setRuntimeTruth(payload.data ?? null);

        const envelopeStatus = payload.status ?? "unknown";
        const capabilityState = payload.capability_state ?? "unknown";
        const runtimeState = payload.data?.runtime_state ?? "unknown";
        const runtimeAvailable = payload.data?.runtime_available;
        const lastInvocationStatus =
          payload.data?.last_invocation_status ?? "unknown";
        const selectedRole = payload.data?.selected_role ?? "unknown";
        const selectedRuntime = payload.data?.selected_runtime ?? "unknown";
        const selectedModel =
          payload.data?.selected_model_runtime_tag ?? "unknown";
        const errorText =
          payload.errors && payload.errors.length > 0
            ? payload.errors.join(" ")
            : "No additional runtime error details were returned.";

        setRuntimeStateLabel(runtimeState);

        if (
          !ok ||
          envelopeStatus === "unavailable" ||
          capabilityState === "unavailable"
        ) {
          setRuntimeStartupState("unavailable");
          setRuntimeStatusMessage("Local runtime unavailable");
          setRuntimeStatusDetail(errorText);
          return;
        }

        if (
          envelopeStatus === "degraded" ||
          capabilityState === "degraded" ||
          runtimeAvailable === false
        ) {
          setRuntimeStartupState("degraded");
          setRuntimeStatusMessage("Local runtime reachable but degraded");
          setRuntimeStatusDetail(
            `Runtime state: ${runtimeState}. Last invocation: ${lastInvocationStatus}. Role: ${selectedRole}. Runtime: ${selectedRuntime}. Model: ${selectedModel}.`
          );
          return;
        }

        if (envelopeStatus === "ok" && runtimeAvailable === true) {
          setRuntimeStartupState("ok");
          setRuntimeStatusMessage("Local runtime available");
          setRuntimeStatusDetail(
            `Runtime state: ${runtimeState}. Last invocation: ${lastInvocationStatus}. Role: ${selectedRole}. Runtime: ${selectedRuntime}. Model: ${selectedModel}.`
          );
          return;
        }

        setRuntimeStartupState("error");
        setRuntimeStatusMessage("Runtime returned an unexpected status");
        setRuntimeStatusDetail(
          `Envelope status: ${envelopeStatus}. Capability state: ${capabilityState}. Runtime state: ${runtimeState}.`
        );
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message =
          error instanceof Error ? error.message : "Unknown runtime query failure.";

        setRuntimeStartupState("error");
        setRuntimeStatusMessage("Runtime query failed");
        setRuntimeStatusDetail(message);
        setRuntimeTruth(null);
      }
    }

    void queryRuntimeStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  return {
    runtimeStartupState,
    runtimeStatusMessage,
    runtimeStatusDetail,
    runtimeContractVersion,
    runtimeStateLabel,
    runtimeTruth
  };
}

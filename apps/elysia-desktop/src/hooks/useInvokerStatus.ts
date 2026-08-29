import { useEffect, useState } from "react";
import {
  fetchInvokerStatus,
  type BridgeStartupState,
  type InvokerStatusEnvelope
} from "../api/bridgeClient";

export type InvokerTruthSnapshot = NonNullable<InvokerStatusEnvelope["data"]>;

type UseInvokerStatusResult = {
  invokerStartupState: BridgeStartupState;
  invokerStatusMessage: string;
  invokerStatusDetail: string;
  invokerContractVersion: string;
  invokerStateLabel: string;
  invokerTruth: InvokerTruthSnapshot | null;
};

export function useInvokerStatus(): UseInvokerStatusResult {
  const [invokerStartupState, setInvokerStartupState] =
    useState<BridgeStartupState>("checking");
  const [invokerStatusMessage, setInvokerStatusMessage] = useState(
    "Checking governed invoker truth..."
  );
  const [invokerStatusDetail, setInvokerStatusDetail] = useState(
    "No verified invoker status yet."
  );
  const [invokerContractVersion, setInvokerContractVersion] = useState("");
  const [invokerStateLabel, setInvokerStateLabel] = useState("unknown");
  const [invokerTruth, setInvokerTruth] = useState<InvokerTruthSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function queryInvokerStatus() {
      setInvokerStartupState("checking");
      setInvokerStatusMessage("Checking governed invoker truth...");
      setInvokerStatusDetail(
        "Waiting for /status/invoker response from the local bridge."
      );

      try {
        const { ok, payload } = await fetchInvokerStatus();

        if (cancelled) {
          return;
        }

        setInvokerContractVersion(payload.contract_version ?? "");
        setInvokerTruth(payload.data ?? null);

        const envelopeStatus = payload.status ?? "unknown";
        const capabilityState = payload.capability_state ?? "unknown";
        const invokerState = payload.data?.invoker_state ?? "unknown";
        const invokerAvailable = payload.data?.invoker_available;
        const lastInvocationStatus =
          payload.data?.last_invocation_status ?? "unknown";
        const selectedRole = payload.data?.selected_role ?? "unknown";
        const selectedRuntime = payload.data?.selected_runtime ?? "unknown";
        const selectedModel =
          payload.data?.selected_model_runtime_tag ?? "unknown";
        const errorText =
          payload.errors && payload.errors.length > 0
            ? payload.errors.join(" ")
            : "No additional invoker error details were returned.";

        setInvokerStateLabel(invokerState);

        if (
          !ok ||
          envelopeStatus === "unavailable" ||
          capabilityState === "unavailable" ||
          (invokerAvailable === false && invokerState === "unavailable")
        ) {
          setInvokerStartupState("unavailable");
          setInvokerStatusMessage("Governed invoker unavailable");
          setInvokerStatusDetail(errorText);
          return;
        }

        if (
          envelopeStatus === "degraded" ||
          capabilityState === "degraded" ||
          invokerState === "degraded"
        ) {
          setInvokerStartupState("degraded");
          setInvokerStatusMessage("Governed invoker reachable but degraded");
          setInvokerStatusDetail(
            `Invoker state: ${invokerState}. Last invocation: ${lastInvocationStatus}. Role: ${selectedRole}. Runtime: ${selectedRuntime}. Model: ${selectedModel}.`
          );
          return;
        }

        if (envelopeStatus === "ok" && invokerAvailable === true) {
          if (invokerState === "blocked") {
            setInvokerStartupState("ok");
            setInvokerStatusMessage("Governed invoker available but approval-bound");
            setInvokerStatusDetail(
              `Invoker state: ${invokerState}. Last invocation: ${lastInvocationStatus}. Role: ${selectedRole}. Runtime: ${selectedRuntime}. Model: ${selectedModel}.`
            );
            return;
          }

          setInvokerStartupState("ok");
          setInvokerStatusMessage("Governed invoker available");
          setInvokerStatusDetail(
            `Invoker state: ${invokerState}. Last invocation: ${lastInvocationStatus}. Role: ${selectedRole}. Runtime: ${selectedRuntime}. Model: ${selectedModel}.`
          );
          return;
        }

        setInvokerStartupState("error");
        setInvokerStatusMessage("Invoker returned an unexpected status");
        setInvokerStatusDetail(
          `Envelope status: ${envelopeStatus}. Capability state: ${capabilityState}. Invoker state: ${invokerState}.`
        );
      } catch (error) {
        if (cancelled) {
          return;
        }

        const message =
          error instanceof Error ? error.message : "Unknown invoker query failure.";

        setInvokerStartupState("error");
        setInvokerStatusMessage("Invoker query failed");
        setInvokerStatusDetail(message);
        setInvokerTruth(null);
      }
    }

    void queryInvokerStatus();

    return () => {
      cancelled = true;
    };
  }, []);

  return {
    invokerStartupState,
    invokerStatusMessage,
    invokerStatusDetail,
    invokerContractVersion,
    invokerStateLabel,
    invokerTruth
  };
}

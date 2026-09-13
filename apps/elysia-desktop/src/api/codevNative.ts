import { requestEnvelope } from "./bridgeClient";
import { CODEV_CONTRACT, type Installation, type OperationReceipt } from "./codevContracts";

export type CodevHandoff = { conversationId: string | null; requestId: string | null; instruction: string };
export type CommandCatalog = { entries: Array<{ command_id: string; label: string; purpose: string; command: string[]; execution_enabled: boolean; disabled_reason: string | null }> };
export type CommandResult = { state: { run_id: string; status: string }; result: { stdout_preview: string; stderr_preview: string; exit_code: number | null; status: string } | null; receipt: OperationReceipt | null };
export type ChatResult = { response_text: string; model_role: string | null; model_tag: string | null; invocation_status: string; receipt: OperationReceipt; context_receipt: unknown; governor: unknown };

type Envelope<T> = { status: string; contract_version: string; data: T; detail?: string; errors?: string[] };
export async function codevRequest<T>(path: string, body?: object): Promise<T> {
  const result = await requestEnvelope<Envelope<T>>(`/codev/${path}`, body === undefined
    ? { method: "GET", cache: "no-store" }
    : { method: "POST", body: JSON.stringify(body) });
  if (!result.ok || result.payload.status !== "ok" || result.payload.contract_version !== CODEV_CONTRACT) {
    const detail = result.payload.detail;
    throw new Error(typeof detail === "string" ? detail.replaceAll("_", " ") : "Codev could not complete this request. Recheck the local connection and permissions.");
  }
  return result.payload.data;
}
export async function getCodevInstallation(): Promise<Installation> {
  return (await codevRequest<{ codev_installation: Installation }>("installation")).codev_installation;
}

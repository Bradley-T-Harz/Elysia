import { fetchMemorySettings } from "./bridgeClient";

export const INTERNET_MASTER_BLOCKED_MESSAGE =
  "Internet access is OFF in Elysia Settings. Enable the governed Internet master before using this external capability.";

export async function requireInternetMasterEnabled(): Promise<void> {
  const result = await fetchMemorySettings();
  const enabled =
    result.ok &&
    result.payload.status === "ok" &&
    result.payload.data?.settings?.internet_master_enabled === true;

  if (!enabled) {
    throw new Error(INTERNET_MASTER_BLOCKED_MESSAGE);
  }
}

export async function governedExternalFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  await requireInternetMasterEnabled();
  return fetch(input, init);
}

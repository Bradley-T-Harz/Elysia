import { invoke } from "@tauri-apps/api/core";

export type EmergencyPayload = {
  status?: string;
  errors?: string[];
  data?: { active?: boolean; resume_required?: boolean };
};

type NativeResponse = { statusCode: number; body: string; contentType: string };
type Result = { ok: boolean; payload: EmergencyPayload };

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function request(path: string, method: "GET" | "POST", body?: object): Promise<Result> {
  try {
    if (isTauri()) {
      const response = await invoke<NativeResponse>("local_api_request", {
        method,
        path,
        body: body ? JSON.stringify(body) : null
      });
      const payload = JSON.parse(response.body) as EmergencyPayload;
      return { ok: response.statusCode >= 200 && response.statusCode < 300 && payload.status === "ok", payload };
    }
    const response = await fetch(`http://127.0.0.1:8000${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store"
    });
    const payload = await response.json() as EmergencyPayload;
    return { ok: response.ok && payload.status === "ok", payload };
  } catch {
    return { ok: false, payload: { status: "error", errors: ["Emergency control bridge unavailable."] } };
  }
}

export function fetchEmergencyState(): Promise<Result> {
  return request("/emergency/status", "GET");
}

export async function activateEmergencyStop(reason: string): Promise<Result> {
  if (isTauri()) {
    try {
      const response = await invoke<NativeResponse>("emergency_stop_owned", { reason });
      const payload = JSON.parse(response.body) as EmergencyPayload;
      return { ok: response.statusCode >= 200 && response.statusCode < 300, payload };
    } catch {
      return { ok: false, payload: { status: "error", errors: ["Native emergency control did not return; inspect the owned process state."] } };
    }
  }
  return request("/emergency/stop", "POST", { reason });
}

export function resetEmergencyStop(): Promise<Result> {
  return request("/emergency/reset", "POST", { acknowledge_safe_restart: true });
}

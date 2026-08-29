import { beforeEach, describe, expect, it, vi } from "vitest";

const invokeMock = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/api/core", () => ({ invoke: invokeMock }));

import {
  createAccount,
  fetchAccountState,
  probeLocalApiAuthentication
} from "../src/api/bridgeClient";

describe("packaged local API client authentication", () => {
  beforeEach(() => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      configurable: true,
      value: {}
    });
    invokeMock.mockResolvedValue({
      statusCode: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        result_type: "local_client_auth_probe",
        data: { credential_exposed: false, mutation_performed: false }
      })
    });
  });

  it("keeps the packaged credential inside the native bridge", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const result = await probeLocalApiAuthentication();

    expect(result.ok).toBe(true);
    expect(invokeMock).toHaveBeenCalledWith("local_api_request", {
      method: "POST",
      path: "/install/auth/probe",
      body: "{}"
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(JSON.stringify(invokeMock.mock.calls)).not.toContain("Authorization");
  });

  it("sends Personal Identity creation through the native request bridge", async () => {
    invokeMock.mockResolvedValueOnce({
      statusCode: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", result_type: "account_create", data: {} })
    });

    const result = await createAccount({
      username: "synthetic-user",
      password: "synthetic account password"
    });

    expect(result.ok).toBe(true);
    expect(invokeMock).toHaveBeenCalledWith("local_api_request", {
      method: "POST",
      path: "/account/create",
      body: JSON.stringify({
        username: "synthetic-user",
        password: "synthetic account password"
      })
    });
  });

  it("surfaces an unowned loopback listener as a port conflict rather than a generic launcher failure", async () => {
    invokeMock
      .mockRejectedValueOnce(new Error("The packaged local API did not become ready."))
      .mockResolvedValueOnce({
        runtimeMode: "packaged",
        lifecycleState: "port_conflict",
        baseUrl: "http://127.0.0.1:49152",
        authenticationRequired: true,
        authenticationState: "missing",
        rawPathExposed: false
      });

    const result = await fetchAccountState();

    expect(result.ok).toBe(false);
    expect(result.payload.errors?.[0]).toContain("refused an unowned loopback listener");
    expect(result.payload.errors?.[0]).not.toContain("fixed Core launcher did not become ready");
  });
});

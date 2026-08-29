import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMemorySettingsMock = vi.hoisted(() => vi.fn());

vi.mock("../src/api/bridgeClient", () => ({
  fetchMemorySettings: fetchMemorySettingsMock
}));

import {
  governedExternalFetch,
  INTERNET_MASTER_BLOCKED_MESSAGE,
  requireInternetMasterEnabled
} from "../src/api/internetMaster";

function settingsResult(enabled: boolean) {
  return {
    ok: true,
    payload: {
      status: "ok",
      data: {
        settings: {
          internet_master_enabled: enabled
        }
      }
    }
  };
}

describe("Desktop Internet master egress boundary", () => {
  beforeEach(() => {
    fetchMemorySettingsMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("fails closed when the authoritative setting cannot be read", async () => {
    fetchMemorySettingsMock.mockResolvedValue({
      ok: false,
      payload: { status: "error", errors: ["local API unavailable"] }
    });

    await expect(requireInternetMasterEnabled()).rejects.toThrow(
      INTERNET_MASTER_BLOCKED_MESSAGE
    );
  });

  it("performs no external fetch while Internet is OFF", async () => {
    fetchMemorySettingsMock.mockResolvedValue(settingsResult(false));
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(governedExternalFetch("https://example.invalid/private"))
      .rejects.toThrow(INTERNET_MASTER_BLOCKED_MESSAGE);

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows exactly the requested external fetch while Internet is ON", async () => {
    fetchMemorySettingsMock.mockResolvedValue(settingsResult(true));
    const response = new Response("ok", { status: 200 });
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);

    await expect(governedExternalFetch("https://example.invalid/public", {
      method: "GET"
    })).resolves.toBe(response);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("https://example.invalid/public", {
      method: "GET"
    });
  });

  it("keeps Marketplace fetches and external openers behind the shared gate", () => {
    const addonsClient = readFileSync("src/api/addonsClient.ts", "utf-8");
    const marketplaceClient = readFileSync("src/api/marketplaceClient.ts", "utf-8");
    const addonsPage = readFileSync("src/AddonsPage.tsx", "utf-8");
    const workbench = readFileSync("src/ProjectWorkbenchPanel.tsx", "utf-8");

    expect(addonsClient).not.toMatch(/\bfetch\s*\(/);
    expect(marketplaceClient).not.toMatch(/\bfetch\s*\(/);
    expect(addonsClient).toContain("governedExternalFetch");
    expect(marketplaceClient).toContain("governedExternalFetch");
    expect(addonsPage).toContain(
      "await requireInternetMasterEnabled();\n      await openUrl(marketplaceUrl);"
    );
    expect(workbench).toContain(
      "await requireInternetMasterEnabled();\n    await openUrl(authorizationUrl);"
    );
  });
});

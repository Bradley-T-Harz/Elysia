import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Actor, Installation, WorkspaceDescriptor } from "../src/api/codevContracts";
const mocks = vi.hoisted(() => ({ request: vi.fn(), open: vi.fn(), installation: vi.fn() }));
vi.mock("../src/api/codevNative", () => ({ codevRequest: mocks.request, getCodevInstallation: mocks.installation }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open }));
import CodevWorkroom from "../src/CodevWorkroom";
import LeftRail from "../src/LeftRail";
import { useCodevInstallation } from "../src/hooks/useCodevInstallation";

const actor: Actor = { client_id: "native_fixture_client", local_profile_id: "profile-fixture", client_kind: "native", surface: "local" };
const installed: Installation = { state: "installed_ready", usable: true, version: "1.0.0", note: "Fixture" };
const base: WorkspaceDescriptor = { workspace_id: "workspace_fixture_id", workspace_type: "local_repository", label: "example-addon", owner: actor,
  current_revision: 0, base_revision: 0, content_hash: "a".repeat(64), base_hash: "a".repeat(64), grant_epoch: 0, files: [] };
let current: WorkspaceDescriptor;
beforeEach(() => {
  current = structuredClone(base);
  mocks.open.mockResolvedValue("/fixture/example-addon");
  mocks.request.mockImplementation(async (path: string, body: Record<string, unknown>) => {
    if (path === "session") return { actor };
    if (path === "commands/catalog") return { catalog: { entries: [] } };
    if (path === "workspaces/select") return { workspace: current };
    if (path === "workspaces/tree") return { files: [{ path: "main.py", size_bytes: 11 }], truncated: false };
    if (path === "grants/issue") {
      const scopes = body.scopes as string[];
      current = { ...current, grant_epoch: (current.grant_epoch ?? 0) + 1, allowed_operations: scopes,
        files: scopes.includes("read") ? [{ path: "main.py", content_hash: "a".repeat(64), size_bytes: 11, text: "answer = 1\n", availability: "text", provenance: "local_file" }] : [] };
      return { workspace: current, grant: { grant_id: "grant_fixture", scopes, files: body.files, epoch: current.grant_epoch, expires_at: new Date(Date.now() + 3600000).toISOString() } };
    }
    if (path === "workspaces/snapshot") return { workspace: current };
    if (path === "grants/revoke") return { grant_epoch: 3 };
    throw new Error(`Unexpected fixture request ${path}`);
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const renderRoom = () => render(<CodevWorkroom installation={installed} active handoff={null} onRightDrawerSectionsChange={vi.fn()} />);
async function shareFile() {
  fireEvent.click(await screen.findByRole("button", { name: "Choose repository" }));
  fireEvent.click(await screen.findByRole("button", { name: "Inspect file list" }));
  fireEvent.click(await screen.findByLabelText("main.py"));
  fireEvent.click(screen.getByRole("button", { name: "Share selected files (1)" }));
  await screen.findByText(/1 selected file shared/);
  fireEvent.click(screen.getByRole("tab", { name: "File" }));
}

describe("Codev installation gating and workspace authority", () => {
  it("renders the exact existing rail with Codev absent", () => {
    const props = { activeRoom: "home" as const, onSelectRoom: vi.fn(), defaultGroupBehavior: "expanded" as const };
    const view = render(<LeftRail {...props} />);
    const original = view.container.innerHTML;
    view.rerender(<LeftRail {...props} showCodev={false} />);
    expect(view.container.innerHTML).toBe(original);
    expect(screen.queryByText("Codev")).toBeNull();
    view.rerender(<LeftRail {...props} showCodev />);
    fireEvent.click(screen.getByRole("button", { name: "Codev" }));
    expect(props.onSelectRoom).toHaveBeenCalledWith("codev");
  });
  it.each(["absent", "incompatible", "degraded", "installed_unavailable"])("does not expose a route for %s", async state => {
    mocks.installation.mockResolvedValue({ ...installed, state, usable: state === "incompatible" });
    function Gate() { const result = useCodevInstallation(); return <LeftRail activeRoom="home" defaultGroupBehavior="expanded" onSelectRoom={vi.fn()} showCodev={!!result}/>; }
    render(<Gate/>);
    await waitFor(() => expect(mocks.installation).toHaveBeenCalled());
    expect(screen.queryByText("Codev")).toBeNull();
  });
  it("selects without access and grants file names separately from content", async () => {
    renderRoom();
    await waitFor(() => expect(screen.getByRole("button", { name: "Choose repository" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Choose repository" }));
    await screen.findByText(/Repository selected. No file list/);
    expect(mocks.request.mock.calls.some(([path]) => path === "grants/issue")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Inspect file list" }));
    await screen.findByLabelText("main.py");
    expect(mocks.request).toHaveBeenCalledWith("grants/issue", expect.objectContaining({ scopes: ["metadata"], files: [], explicitly_approved: true }));
    expect(screen.queryByLabelText("Edit main.py")).toBeNull();
  });
  it("preserves edits when source changes and requires an explicit fresh review", async () => {
    renderRoom();
    await waitFor(() => expect(screen.getByRole("button", { name: "Choose repository" })).toBeEnabled());
    await shareFile();
    fireEvent.change(await screen.findByLabelText("Edit main.py"), { target: { value: "answer = 2\n" } });
    current = { ...current, current_revision: 2, content_hash: "c".repeat(64), files: [{ ...current.files![0], text: "answer = 3\n", content_hash: "c".repeat(64) }] };
    fireEvent.click(screen.getByRole("button", { name: "Refresh files" }));
    await screen.findByText(/Source changed while your edits were open/);
    expect(screen.getByLabelText("Edit main.py")).toHaveValue("answer = 2\n");
    expect(screen.getByRole("button", { name: "Review 1 edit" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Review against the refreshed source" }));
    expect(screen.getByRole("button", { name: "Review 1 edit" })).toBeEnabled();
  });
  it("revokes authority while preserving unsaved local buffers", async () => {
    renderRoom();
    await waitFor(() => expect(screen.getByRole("button", { name: "Choose repository" })).toBeEnabled());
    await shareFile();
    fireEvent.change(await screen.findByLabelText("Edit main.py"), { target: { value: "answer = 2\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Revoke access" }));
    await screen.findByText(/Workspace access revoked/);
    expect(screen.getByLabelText("Edit main.py")).toHaveValue("answer = 2\n");
    expect(screen.getByLabelText("Edit main.py")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Review 1 edit" })).toBeDisabled();
  });
});

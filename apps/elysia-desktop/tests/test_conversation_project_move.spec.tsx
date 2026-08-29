import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const bridgeState = vi.hoisted(() => ({
  projectId: null as string | null
}));

const bridgeMocks = vi.hoisted(() => ({
  fetchConversationList: vi.fn(),
  fetchConversationThread: vi.fn(),
  fetchMemoryItems: vi.fn(),
  fetchMediaWorkerTruth: vi.fn(),
  fetchProjectList: vi.fn(),
  fetchTtsVoices: vi.fn(),
  updateConversation: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>(
    "../src/api/bridgeClient"
  );

  return {
    ...actual,
    fetchConversationList: bridgeMocks.fetchConversationList,
    fetchConversationThread: bridgeMocks.fetchConversationThread,
    fetchMemoryItems: bridgeMocks.fetchMemoryItems,
    fetchMediaWorkerTruth: bridgeMocks.fetchMediaWorkerTruth,
    fetchProjectList: bridgeMocks.fetchProjectList,
    fetchTtsVoices: bridgeMocks.fetchTtsVoices,
    updateConversation: bridgeMocks.updateConversation
  };
});

import ConversationsPage from "../src/ConversationsPage";

function conversationSummary() {
  return {
    conversation_id: "conv_move_test",
    title: "Conversation for project move",
    last_message_preview: "Move this existing conversation.",
    updated_at_utc: "2026-08-13T12:00:00Z",
    message_count: 1,
    current_mode: "default",
    current_role: "assistant",
    last_message_role: "user",
    project_id: bridgeState.projectId,
    archived: false,
    pinned: false,
    capability_state: "live",
    locality: "local",
    approval_state: "not_needed"
  };
}

function configureBridgeMocks() {
  bridgeMocks.fetchConversationList.mockImplementation(async () => ({
    ok: true,
    payload: {
      status: "ok",
      errors: [],
      data: {
        conversations: [conversationSummary()],
        active_conversation_id: "conv_move_test",
        total: 1
      }
    }
  }));
  bridgeMocks.fetchConversationThread.mockImplementation(async () => ({
    ok: true,
    payload: {
      status: "ok",
      errors: [],
      data: {
        conversation_id: "conv_move_test",
        metadata: conversationSummary(),
        messages: [
          {
            message_id: "msg_move_test",
            conversation_id: "conv_move_test",
            role: "user",
            content: "Move this existing conversation.",
            created_at_utc: "2026-08-13T12:00:00Z"
          }
        ],
        message_count: 1,
        last_message_role: "user"
      }
    }
  }));
  bridgeMocks.fetchMemoryItems.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      errors: [],
      data: {
        items: [
          {
            memory_id: "memory_conv_move_test",
            form: "episodic",
            scope: "conversation",
            privacy: "normal"
          }
        ],
        total: 1
      }
    }
  });
  bridgeMocks.fetchProjectList.mockResolvedValue({
    ok: true,
    payload: {
      status: "ok",
      errors: [],
      data: {
        projects: [{ project_id: "proj_test", name: "Test" }],
        total: 1
      }
    }
  });
  bridgeMocks.fetchMediaWorkerTruth.mockResolvedValue({
    ok: true,
    payload: { status: "ok", errors: [], data: { media_workers: null } }
  });
  bridgeMocks.fetchTtsVoices.mockResolvedValue({
    ok: true,
    payload: { status: "ok", errors: [], data: { voices: [] } }
  });
  bridgeMocks.updateConversation.mockImplementation(
    async (_conversationId: string, patch: { project_id?: string | null }) => {
      bridgeState.projectId = patch.project_id ?? null;
      return {
        ok: true,
        payload: {
          status: "ok",
          errors: [],
          data: {
            conversation_id: "conv_move_test",
            metadata: conversationSummary(),
            updated_fields: ["project_id"]
          }
        }
      };
    }
  );
}

async function openMoveDialog() {
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Conversation actions for Conversation for project move"
    })
  );
  fireEvent.click(
    await screen.findByRole("menuitem", { name: "Move to project" })
  );
  return screen.findByRole("dialog", { name: "Move conversation to project" });
}

describe("Conversations project move workflow", () => {
  beforeEach(() => {
    bridgeState.projectId = null;
    vi.clearAllMocks();
    configureBridgeMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("loads local projects for the dialog, moves by stable ID, and refreshes project truth", async () => {
    const onRightDrawerSectionsChange = vi.fn();
    render(
      <ConversationsPage
        startupReady
        onRightDrawerSectionsChange={onRightDrawerSectionsChange}
      />
    );

    const dialog = await openMoveDialog();
    const picker = within(dialog).getByRole("combobox", { name: "Project" });
    expect(within(picker).getByRole("option", { name: "Test" })).toHaveValue(
      "proj_test"
    );

    fireEvent.change(picker, { target: { value: "proj_test" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Move" }));

    await waitFor(() => {
      expect(bridgeMocks.updateConversation).toHaveBeenCalledWith(
        "conv_move_test",
        { project_id: "proj_test" }
      );
    });
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "Move conversation to project" })
      ).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(onRightDrawerSectionsChange).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            key: "current_project",
            rows: expect.arrayContaining([
              expect.objectContaining({ label: "Selection", value: "Test" })
            ])
          })
        ])
      );
    });
    await waitFor(() => {
      expect(onRightDrawerSectionsChange).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({
            key: "memory_classes",
            state: "live",
            rows: expect.arrayContaining([
              expect.objectContaining({
                label: "Canonical linked Memory",
                value: "1 authorized record · episodic"
              }),
              expect.objectContaining({ label: "Archive / deletion" })
            ])
          })
        ])
      );
    });
  });

  it("keeps a real bridge failure visible in the open move dialog", async () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    bridgeMocks.updateConversation.mockResolvedValueOnce({
      ok: false,
      payload: {
        status: "error",
        errors: ["Project 'proj_test' was not found."],
        data: {}
      }
    });
    render(
      <ConversationsPage
        startupReady
        onRightDrawerSectionsChange={vi.fn()}
      />
    );

    const dialog = await openMoveDialog();
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Project" }), {
      target: { value: "proj_test" }
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Move" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Move to project failed. Project 'proj_test' was not found."
    );
    expect(
      screen.getByRole("dialog", { name: "Move conversation to project" })
    ).toBeInTheDocument();
    expect(errorLog).toHaveBeenCalled();
  });
});

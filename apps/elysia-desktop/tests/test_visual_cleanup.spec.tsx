import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Composer from "../src/Composer";
import ConversationActionsMenu from "../src/ConversationActionsMenu";
import MessageBubble, { type MessageBubbleMessage } from "../src/MessageBubble";

function message(content: string): MessageBubbleMessage {
  return {
    messageId: "msg_visual_cleanup",
    conversationId: "conversation_visual_cleanup",
    role: "assistant",
    content,
    createdAtUtc: null,
    requestId: null,
    invocationStatus: null,
    responseSource: null,
    selectedRole: null,
    selectedRuntime: null,
    selectedModelRuntimeTag: null,
    usedFallback: null,
    fallbackFrom: null,
    fallbackTo: null,
    approvalNeeded: null,
    approvalState: null,
    localityState: null,
    capabilityState: null,
    blocked: null,
    degraded: null,
    error: null,
    warnings: [],
    caveats: []
  };
}

describe("desktop visual cleanup behaviors", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("keeps a long message in the document while offering collapse and expand", () => {
    const content = Array.from(
      { length: 18 },
      (_, index) => `Truthful message line ${index + 1}`
    ).join("\n");

    render(<MessageBubble message={message(content)} />);

    const toggle = screen.getByRole("button", { name: "Show full message" });
    const contentElement = document.getElementById(
      toggle.getAttribute("aria-controls") ?? ""
    );

    expect(contentElement).toHaveTextContent("Truthful message line 18");
    expect(contentElement).toHaveStyle({ maxHeight: "16rem", overflow: "hidden" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: "Collapse message" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    expect(contentElement).toHaveStyle({ maxHeight: "none", overflow: "visible" });
  });

  it("keeps optional local-file controls available behind a compact disclosure", () => {
    render(
      <Composer
        value=""
        onChange={vi.fn()}
        onSend={vi.fn()}
        onFilePathChange={vi.fn()}
        onAttachFilePath={vi.fn()}
        onBrowseForFile={vi.fn()}
      />
    );

    const disclosure = screen.getByText("Attach a local file").closest("details");
    expect(disclosure).not.toHaveAttribute("open");
    expect(
      screen.getByPlaceholderText(/notes\.md/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByText("Attach a local file"));
    expect(disclosure).toHaveAttribute("open");
  });

  it("returns focus to the conversation action trigger after Escape", () => {
    render(
      <ConversationActionsMenu
        conversationId="conversation_visual_cleanup"
        conversationTitle="Visual cleanup"
        onShare={vi.fn()}
        onRename={vi.fn()}
        onMoveToProject={vi.fn()}
        onTogglePinned={vi.fn()}
        onToggleArchived={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    const trigger = screen.getByRole("button", {
      name: "Conversation actions for Visual cleanup"
    });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("menu", { name: "Actions for Visual cleanup" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("menu", { name: "Actions for Visual cleanup" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});

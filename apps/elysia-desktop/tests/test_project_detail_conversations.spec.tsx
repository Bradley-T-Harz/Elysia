import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const bridgeMocks = vi.hoisted(() => ({
  fetchProjectDetail: vi.fn(),
  fetchMemoryItems: vi.fn(),
  selectProject: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>(
    "../src/api/bridgeClient"
  );

  return {
    ...actual,
    fetchProjectDetail: bridgeMocks.fetchProjectDetail,
    fetchMemoryItems: bridgeMocks.fetchMemoryItems,
    selectProject: bridgeMocks.selectProject
  };
});

import ProjectDetailPage from "../src/ProjectDetailPage";

describe("ProjectDetailPage conversations", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  beforeEach(() => {
    bridgeMocks.fetchMemoryItems.mockResolvedValue({
      ok: true,
      payload: { status: "ok", errors: [], data: { items: [], total: 0 } }
    });
  });

  it("renders conversations returned by the persisted project-detail linkage", async () => {
    bridgeMocks.fetchProjectDetail.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        errors: [],
        data: {
          project_id: "proj_test",
          metadata: {
            project_id: "proj_test",
            name: "Test",
            status: "active",
            conversation_count: 1
          },
          related_conversations: [
            {
              conversation_id: "conv_linked",
              title: "Moved conversation",
              last_message_preview: "This conversation now belongs to Test.",
              message_count: 2,
              project_id: "proj_test"
            }
          ],
          conversation_count: 1,
          source_count: 0
        }
      }
    });
    bridgeMocks.selectProject.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        errors: [],
        data: { active_project_id: "proj_test" }
      }
    });
    const onSelectConversation = vi.fn();

    render(
      <ProjectDetailPage
        projectId="proj_test"
        startupReady
        onRightDrawerSectionsChange={vi.fn()}
        onSelectConversation={onSelectConversation}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText("Moved conversation").length).toBeGreaterThan(0);
    });
    expect(bridgeMocks.fetchProjectDetail).toHaveBeenCalledWith("proj_test");
    expect(
      screen.queryByText(/No conversations are linked to this project yet/i)
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /Moved conversation/i })
    );
    expect(onSelectConversation).toHaveBeenCalledWith("conv_linked");
  });

  it("keeps the empty project state explicit when the bridge returns no linkage", async () => {
    bridgeMocks.fetchProjectDetail.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        errors: [],
        data: {
          project_id: "proj_empty",
          metadata: {
            project_id: "proj_empty",
            name: "Empty project",
            status: "active",
            conversation_count: 0
          },
          related_conversations: [],
          conversation_count: 0,
          source_count: 0
        }
      }
    });
    bridgeMocks.selectProject.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        errors: [],
        data: { active_project_id: "proj_empty" }
      }
    });

    render(
      <ProjectDetailPage
        projectId="proj_empty"
        startupReady
        onRightDrawerSectionsChange={vi.fn()}
      />
    );

    expect(
      await screen.findByText(/No conversations are linked to this project yet/i)
    ).toBeInTheDocument();
  });

  it("routes real conversation work and exposes restored project capabilities as live actions", async () => {
    bridgeMocks.fetchProjectDetail.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        errors: [],
        data: {
          project_id: "proj_truth",
          metadata: {
            project_id: "proj_truth",
            name: "Truth project",
            status: "active",
            conversation_count: 1
          },
          related_conversations: [
            {
              conversation_id: "conv_truth",
              title: "Governed thread",
              message_count: 3,
              project_id: "proj_truth"
            }
          ],
          conversation_count: 1,
          source_count: 0
        }
      }
    });
    bridgeMocks.selectProject.mockResolvedValue({
      ok: true,
      payload: {
        status: "ok",
        errors: [],
        data: { active_project_id: "proj_truth" }
      }
    });
    const onSelectConversation = vi.fn();

    render(
      <ProjectDetailPage
        projectId="proj_truth"
        startupReady
        onRightDrawerSectionsChange={vi.fn()}
        onSelectConversation={onSelectConversation}
      />
    );

    await screen.findByText("Governed thread");
    expect(screen.queryByRole("button", { name: "Tutor" })).not.toBeInTheDocument();

    const speak = screen.getByRole("button", { name: "Speak" });
    expect(speak).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "+" }));
    const fileTools = await screen.findByRole("button", {
      name: /Open conversation file tools/i
    });
    expect(fileTools).toBeEnabled();
    expect(screen.getByRole("button", { name: /Project sources/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Create image/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Deep research/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Web search/i })).toBeEnabled();

    fireEvent.click(fileTools);
    expect(onSelectConversation).toHaveBeenCalledWith("conv_truth");

    fireEvent.click(screen.getByRole("button", { name: "⋮" }));
    expect(await screen.findByRole("button", { name: /Study and learn/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Pursue goal/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Canvas/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Image editing/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Quizzes/i })).toBeEnabled();
  });
});

import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const bridgeMocks = vi.hoisted(() => ({
  fetchOnboardingState: vi.fn(),
  saveOnboardingDraft: vi.fn(),
  finalizeOnboarding: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>("../src/api/bridgeClient");
  return { ...actual, ...bridgeMocks };
});

import PersonalOnboardingPage from "../src/PersonalOnboardingPage";

const ok = (data: Record<string, unknown>) => ({
  ok: true,
  payload: { status: "ok", errors: [], warnings: [], data }
});

describe("voluntary personal onboarding", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("offers skip, encrypted resume, per-answer privacy, and exact packet review", async () => {
    bridgeMocks.fetchOnboardingState.mockResolvedValue(ok({
      status: "not_started",
      sections: [{
        section_id: "relationship_communication",
        title: "Relationship and communication",
        questions: [{ question_id: "q01", prompt: "What would make Elysia genuinely useful in your life?" }]
      }],
      answers: []
    }));
    bridgeMocks.saveOnboardingDraft.mockResolvedValue(ok({ status: "in_progress" }));
    bridgeMocks.finalizeOnboarding.mockResolvedValue(ok({ status: "completed" }));
    const onDone = vi.fn();
    render(<PersonalOnboardingPage offeredAfterAccountCreation onDone={onDone} />);

    expect(await screen.findByText("Personal onboarding")).toBeVisible();
    expect(screen.getByTestId("personal-onboarding-page")).toHaveStyle({
      height: "100vh",
      maxHeight: "100vh",
      overflowY: "auto"
    });
    expect(screen.getByRole("button", { name: "Skip entire questionnaire" })).toBeEnabled();
    const answer = screen.getByLabelText("What would make Elysia genuinely useful in your life?");
    fireEvent.change(answer, { target: { value: "Help me finish careful work." } });
    expect(screen.getByLabelText("Memory privacy")).toHaveValue("private");
    expect(screen.getByLabelText("Retention")).toHaveValue("persistent");

    fireEvent.click(screen.getByRole("button", { name: "Review proposed memory packet" }));
    expect(screen.getByRole("region", { name: "Exact proposed onboarding memory packet" })).toBeVisible();
    expect(screen.getByLabelText("Exact proposed wording")).toHaveValue("Help me finish careful work.");
    fireEvent.click(screen.getByRole("button", { name: "Import selected reviewed answers" }));
    await waitFor(() => expect(bridgeMocks.saveOnboardingDraft).toHaveBeenCalled());
    await waitFor(() => expect(bridgeMocks.finalizeOnboarding).toHaveBeenCalledWith(expect.objectContaining({ action: "import_selected", selected_question_ids: ["q01"] })));
    expect(onDone).toHaveBeenCalled();
  });

  it("keeps an untouched optional questionnaire available after restart until the user resolves it", async () => {
    bridgeMocks.fetchOnboardingState.mockResolvedValue(ok({
      status: "not_started",
      sections: [{
        section_id: "relationship_communication",
        title: "Relationship and communication",
        questions: [{ question_id: "q01", prompt: "What would make Elysia genuinely useful in your life?" }]
      }],
      answers: []
    }));
    const onDone = vi.fn();
    render(<PersonalOnboardingPage offeredAfterAccountCreation={false} onDone={onDone} />);

    expect(await screen.findByText("Personal onboarding")).toBeVisible();
    expect(screen.getByRole("button", { name: "Skip entire questionnaire" })).toBeEnabled();
    expect(onDone).not.toHaveBeenCalled();
  });
});

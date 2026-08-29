import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import MoveConversationDialog from "../src/MoveConversationDialog";

const projects = [
  { project_id: "proj_test", name: "Test" },
  { project_id: "proj_cedar", name: "Cedar" }
];

describe("MoveConversationDialog", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("offers the supplied local projects by name and submits the stable project ID", () => {
    const onSubmit = vi.fn();

    render(
      <MoveConversationDialog
        open
        currentProjectId=""
        projects={projects}
        projectListState="ready"
        onClose={vi.fn()}
        onSubmit={onSubmit}
        onRetryProjects={vi.fn()}
      />
    );

    const picker = screen.getByRole("combobox", { name: "Project" });
    expect(within(picker).getByRole("option", { name: "Test" })).toHaveValue(
      "proj_test"
    );
    expect(within(picker).getByRole("option", { name: "Cedar" })).toHaveValue(
      "proj_cedar"
    );
    expect(screen.queryByRole("textbox", { name: /project id/i })).not.toBeInTheDocument();

    fireEvent.change(picker, { target: { value: "proj_cedar" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));

    expect(onSubmit).toHaveBeenCalledWith("proj_cedar");
  });

  it("shows an honest no-project state and opens the existing project flow", () => {
    const onClose = vi.fn();
    const onOpenProjects = vi.fn();

    render(
      <MoveConversationDialog
        open
        currentProjectId=""
        projects={[]}
        projectListState="ready"
        onClose={onClose}
        onSubmit={vi.fn()}
        onRetryProjects={vi.fn()}
        onOpenProjects={onOpenProjects}
      />
    );

    expect(
      screen.getByText(/No projects are available yet/i)
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create a project" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onOpenProjects).toHaveBeenCalledTimes(1);
  });

  it("keeps bridge list and move failures visible inside the dialog", () => {
    const { rerender } = render(
      <MoveConversationDialog
        open
        currentProjectId=""
        projects={[]}
        projectListState="error"
        projectListError="Project list is unavailable."
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        onRetryProjects={vi.fn()}
      />
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Project list is unavailable."
    );

    rerender(
      <MoveConversationDialog
        open
        currentProjectId=""
        projects={projects}
        projectListState="ready"
        moveError="Move to project failed. Project was not found."
        onClose={vi.fn()}
        onSubmit={vi.fn()}
        onRetryProjects={vi.fn()}
      />
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Move to project failed. Project was not found."
    );
  });
});

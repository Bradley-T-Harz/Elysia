import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const bridgeMocks = vi.hoisted(() => ({
  createAccount: vi.fn(),
  selectAccountProfilePhoto: vi.fn()
}));

vi.mock("../src/api/bridgeClient", async () => {
  const actual = await vi.importActual<typeof import("../src/api/bridgeClient")>(
    "../src/api/bridgeClient"
  );

  return {
    ...actual,
    createAccount: bridgeMocks.createAccount,
    selectAccountProfilePhoto: bridgeMocks.selectAccountProfilePhoto
  };
});

vi.mock("../src/api/localFilePicker", () => ({
  openLocalProfilePhotoFile: vi.fn()
}));

import UserCreatorPage from "../src/UserCreatorPage";

describe("Personal Identity responsive layout", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("creates only local identity ownership before optional personal onboarding", () => {
    render(
      <UserCreatorPage
        colors={[{ id: "meteor_rose", label: "Meteor Rose", hex: "#c98276" }]}
        onCreated={vi.fn()}
      />
    );

    const scrollRegion = screen.getByTestId("personal-identity-scroll-region");
    expect(scrollRegion).toHaveClass("elysia-account-setup-scroll");
    expect(scrollRegion.querySelector("form")).toHaveClass(
      "elysia-account-setup-form"
    );

    ["Username", "Password", "Password confirmation"].forEach((label) => {
      expect(screen.getByLabelText(label)).toBeEnabled();
    });
    ["Interests", "Story", "Birthdate", "Phone Number", "Emails", "Social Media", "GitHub", "City", "State"].forEach((label) => {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Personal onboarding is a separate, optional step/i)).toBeVisible();
    expect(screen.getByText(/first account becomes this installation's Owner/i)).toBeVisible();
    expect(screen.getByRole("checkbox", { name: /losing the passphrase/i })).toBeEnabled();

    expect(
      screen.getByRole("button", { name: /Identity Photo.*No image selected/i })
    ).toBeEnabled();
    expect(
      screen.getByRole("button", {
        name: "Create Local Account"
      })
    ).toBeEnabled();
  });
});

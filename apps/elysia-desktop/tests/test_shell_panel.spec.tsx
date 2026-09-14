import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ShellPanel from "../src/ShellPanel";
afterEach(cleanup);
it("keeps secondary controls reachable as a native modal at compact widths", () => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  const close = vi.fn();
  const panel = (compact: boolean, open: boolean) => <ShellPanel compact={compact} open={open} onClose={close} label="Rooms" side="left"><button>Conversations</button></ShellPanel>;
  const view = render(panel(false, false));
  expect(screen.getByRole("button", { name: "Conversations" })).toBeVisible();
  view.rerender(panel(true, false));
  expect(screen.queryByRole("button", { name: "Conversations" })).toBeNull();
  view.rerender(panel(true, true));
  expect(screen.getByRole("dialog", { name: "Rooms" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Close Rooms" }));
  expect(close).toHaveBeenCalledOnce();
});

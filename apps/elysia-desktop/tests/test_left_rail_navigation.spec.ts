import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LeftRail, { type LeftRailRoom } from "../src/LeftRail";

const groupedRooms: Array<{
  group: string;
  rooms: Array<{ label: string; room: LeftRailRoom }>;
}> = [
  {
    group: "Workrooms",
    rooms: [
      { label: "Conversations", room: "conversations" },
      { label: "Projects", room: "projects" },
      { label: "Artifacts", room: "artifacts" },
      { label: "Requests", room: "requests" }
    ]
  },
  {
    group: "Memory & Identity",
    rooms: [
      { label: "Memory", room: "memory" },
      { label: "Personal Identity", room: "user_profile" }
    ]
  },
  {
    group: "Control & System",
    rooms: [
      { label: "Governance", room: "governance" },
      { label: "Capabilities", room: "capabilities" },
      { label: "Add-ons", room: "addons" },
      { label: "Health", room: "health" }
    ]
  }
];

function expectInDocumentOrder(elements: HTMLElement[]) {
  elements.slice(1).forEach((element, index) => {
    expect(
      elements[index].compareDocumentPosition(element) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });
}

describe("LeftRail room organization", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("starts quietly with Chamber first and every visual group collapsed", () => {
    render(
      React.createElement(LeftRail, {
        activeRoom: "home",
        onSelectRoom: vi.fn()
      })
    );

    const navigation = screen.getByRole("navigation", { name: "Rooms" });
    const chamber = within(navigation).getByRole("button", { name: "Chamber" });
    const groupHeaders = groupedRooms.map(({ group }) =>
      within(navigation).getByRole("button", { name: group })
    );

    expect(chamber.parentElement).toBe(navigation);
    expect(chamber).toHaveAttribute("aria-current", "page");
    expectInDocumentOrder([chamber, ...groupHeaders]);

    groupedRooms.forEach(({ group, rooms }) => {
      const header = within(navigation).getByRole("button", { name: group });

      expect(header).toHaveAttribute("aria-expanded", "false");
      expect(
        within(navigation).queryByRole("group", { name: group })
      ).not.toBeInTheDocument();
      rooms.forEach(({ label }) => {
        expect(
          within(navigation).queryByRole("button", { name: label })
        ).not.toBeInTheDocument();
      });
    });
  });

  it("can start with every visual group expanded as a local preference", () => {
    render(
      React.createElement(LeftRail, {
        activeRoom: "home",
        onSelectRoom: vi.fn(),
        defaultGroupBehavior: "expanded"
      })
    );

    groupedRooms.forEach(({ group, rooms }) => {
      expect(screen.getByRole("button", { name: group })).toHaveAttribute(
        "aria-expanded",
        "true"
      );
      rooms.forEach(({ label }) => {
        expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
      });
    });
  });

  it("reapplies a changed default while keeping the active room group open", () => {
    const onSelectRoom = vi.fn();
    const view = render(
      React.createElement(LeftRail, {
        activeRoom: "memory",
        onSelectRoom,
        defaultGroupBehavior: "expanded"
      })
    );

    view.rerender(
      React.createElement(LeftRail, {
        activeRoom: "memory",
        onSelectRoom,
        defaultGroupBehavior: "collapsed"
      })
    );

    expect(screen.getByRole("button", { name: "Workrooms" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(
      screen.getByRole("button", { name: "Memory & Identity" })
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("button", { name: "Control & System" })
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("button", { name: "Memory" })).toHaveAttribute(
      "aria-current",
      "page"
    );
    expect(onSelectRoom).not.toHaveBeenCalled();
  });

  it("expands Workrooms to reveal its rooms in the requested order", () => {
    render(
      React.createElement(LeftRail, {
        activeRoom: "home",
        onSelectRoom: vi.fn()
      })
    );

    const header = screen.getByRole("button", { name: "Workrooms" });
    fireEvent.click(header);

    const roomGroup = screen.getByRole("group", { name: "Workrooms" });
    const roomButtons = groupedRooms[0].rooms.map(({ label }) =>
      within(roomGroup).getByRole("button", { name: label })
    );

    expect(header).toHaveAttribute("aria-expanded", "true");
    expectInDocumentOrder(roomButtons);
    expect(
      screen.queryByRole("button", { name: "Memory" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Governance" })
    ).not.toBeInTheDocument();
  });

  it("passes every existing room ID through the unchanged room-selection callback", () => {
    const onSelectRoom = vi.fn();

    render(
      React.createElement(LeftRail, {
        activeRoom: "home",
        onSelectRoom
      })
    );

    fireEvent.click(screen.getByRole("button", { name: "Chamber" }));

    groupedRooms.forEach(({ group, rooms }) => {
      fireEvent.click(screen.getByRole("button", { name: group }));
      rooms.forEach(({ label }) => {
        fireEvent.click(screen.getByRole("button", { name: label }));
      });
    });

    expect(onSelectRoom.mock.calls.map(([room]) => room)).toEqual(
      [
        "home",
        ...groupedRooms.flatMap(({ rooms }) => rooms.map(({ room }) => room))
      ]
    );
  });

  it("uses group headers only for visual expansion, never navigation", () => {
    const onSelectRoom = vi.fn();

    render(
      React.createElement(LeftRail, {
        activeRoom: "home",
        onSelectRoom
      })
    );

    groupedRooms.forEach(({ group, rooms }) => {
      const header = screen.getByRole("button", { name: group });

      fireEvent.click(header);

      expect(header).toHaveAttribute("aria-expanded", "true");
      rooms.forEach(({ label }) => {
        expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
      });
      expect(screen.getByRole("button", { name: "Chamber" })).toBeInTheDocument();
      expect(onSelectRoom).not.toHaveBeenCalled();

      fireEvent.click(header);

      expect(header).toHaveAttribute("aria-expanded", "false");
      rooms.forEach(({ label }) => {
        expect(
          screen.queryByRole("button", { name: label })
        ).not.toBeInTheDocument();
      });
      expect(onSelectRoom).not.toHaveBeenCalled();
    });
  });

  it.each(
    groupedRooms.map(({ group, rooms }) => ({
      group,
      activeLabel: rooms[0].label,
      activeRoom: rooms[0].room
    }))
  )(
    "automatically opens $group when its active route is selected",
    ({ group, activeLabel, activeRoom }) => {
      const onSelectRoom = vi.fn();

      render(
        React.createElement(LeftRail, {
          activeRoom,
          onSelectRoom
        })
      );

      expect(screen.getByRole("button", { name: group })).toHaveAttribute(
        "aria-expanded",
        "true"
      );
      expect(screen.getByRole("button", { name: activeLabel })).toHaveAttribute(
        "aria-current",
        "page"
      );
      expect(onSelectRoom).not.toHaveBeenCalled();
    }
  );

  it("preserves every existing room description", () => {
    render(
      React.createElement(LeftRail, {
        activeRoom: "home",
        onSelectRoom: vi.fn()
      })
    );

    groupedRooms.forEach(({ group }) => {
      fireEvent.click(screen.getByRole("button", { name: group }));
    });

    [
      "Boot page and startup truth.",
      "Enter the first working room.",
      "Project index and continuity room.",
      "Local generated outputs and safe previews.",
      "Inspectable request ledger and trace truth.",
      "Inspectable continuity and memory governance.",
      "Sealed local identity and private user portfolio.",
      "Rules of the house, trust zones, and control truth.",
      "Truth map of Elysia's available limbs.",
      "Marketplace-gated catalog and preview room.",
      "Local organism health and subsystem truth."
    ].forEach((description) => {
      expect(screen.getByText(description)).toBeVisible();
    });
  });
});

export const DESKTOP_PREFERENCES_STORAGE_KEY =
  "elysia.desktop.preferences.v1";

export const STARTUP_ROOM_OPTIONS = [
  { id: "home", label: "Chamber" },
  { id: "conversations", label: "Conversations" },
  { id: "projects", label: "Projects" },
  { id: "artifacts", label: "Artifacts" },
  { id: "requests", label: "Requests" },
  { id: "memory", label: "Memory" },
  { id: "governance", label: "Governance" },
  { id: "capabilities", label: "Capabilities" },
  { id: "health", label: "Health" },
  { id: "user_profile", label: "Personal Identity" },
  { id: "addons", label: "Add-ons" }
] as const;

export type DesktopStartupRoom =
  (typeof STARTUP_ROOM_OPTIONS)[number]["id"];
export type DesktopDensity = "comfortable" | "compact";
export type LeftRailDefaultBehavior = "collapsed" | "expanded";
export type DesktopMotionPreference = "system" | "reduced";

export type DesktopPreferences = {
  density: DesktopDensity;
  startupRoom: DesktopStartupRoom;
  leftRailDefaultBehavior: LeftRailDefaultBehavior;
  motionPreference: DesktopMotionPreference;
};

export const DEFAULT_DESKTOP_PREFERENCES: DesktopPreferences = {
  density: "comfortable",
  startupRoom: "home",
  leftRailDefaultBehavior: "collapsed",
  motionPreference: "system"
};

const startupRoomIds = new Set<DesktopStartupRoom>(
  STARTUP_ROOM_OPTIONS.map((option) => option.id)
);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isDesktopStartupRoom(
  value: unknown
): value is DesktopStartupRoom {
  return (
    typeof value === "string" &&
    startupRoomIds.has(value as DesktopStartupRoom)
  );
}

export function normalizeDesktopPreferences(
  value: unknown
): DesktopPreferences {
  if (!isRecord(value)) {
    return { ...DEFAULT_DESKTOP_PREFERENCES };
  }

  return {
    density:
      value.density === "compact" || value.density === "comfortable"
        ? value.density
        : DEFAULT_DESKTOP_PREFERENCES.density,
    startupRoom: isDesktopStartupRoom(value.startupRoom)
      ? value.startupRoom
      : DEFAULT_DESKTOP_PREFERENCES.startupRoom,
    leftRailDefaultBehavior:
      value.leftRailDefaultBehavior === "expanded" ||
      value.leftRailDefaultBehavior === "collapsed"
        ? value.leftRailDefaultBehavior
        : DEFAULT_DESKTOP_PREFERENCES.leftRailDefaultBehavior,
    motionPreference:
      value.motionPreference === "system" || value.motionPreference === "reduced"
        ? value.motionPreference
        : DEFAULT_DESKTOP_PREFERENCES.motionPreference
  };
}

export function readDesktopPreferences(): DesktopPreferences {
  try {
    const storedValue = window.localStorage.getItem(
      DESKTOP_PREFERENCES_STORAGE_KEY
    );

    if (!storedValue) {
      return { ...DEFAULT_DESKTOP_PREFERENCES };
    }

    return normalizeDesktopPreferences(JSON.parse(storedValue));
  } catch {
    return { ...DEFAULT_DESKTOP_PREFERENCES };
  }
}

export function writeDesktopPreferences(
  preferences: DesktopPreferences
): void {
  try {
    window.localStorage.setItem(
      DESKTOP_PREFERENCES_STORAGE_KEY,
      JSON.stringify(normalizeDesktopPreferences(preferences))
    );
  } catch {
    // The live preference still applies for this mount when storage is blocked.
  }
}

export function resetDesktopPreferences(): DesktopPreferences {
  try {
    window.localStorage.removeItem(DESKTOP_PREFERENCES_STORAGE_KEY);
  } catch {
    // Reset still applies for this mount when storage is blocked.
  }

  return { ...DEFAULT_DESKTOP_PREFERENCES };
}

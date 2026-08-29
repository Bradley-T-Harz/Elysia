import type { AccountColorOption } from "./api/bridgeClient";

export const fallbackAccountColors: AccountColorOption[] = [
  { id: "meteor_rose", label: "Meteor Rose", hex: "#F45B8A" },
  { id: "aurora_teal", label: "Aurora Teal", hex: "#26D9C7" },
  { id: "volcanic_coral", label: "Volcanic Coral", hex: "#FF6B57" },
  { id: "stellar_indigo", label: "Stellar Indigo", hex: "#6C63FF" },
  { id: "vapor_mint", label: "Vapor Mint", hex: "#94F5C8" },
  { id: "laser_lemon", label: "Laser Lemon", hex: "#F8F36A" },
  { id: "blue_flame", label: "Blue Flame", hex: "#35A7FF" },
  { id: "magenta_comet", label: "Magenta Comet", hex: "#F443D1" },
  { id: "prismatic_amber", label: "Prismatic Amber", hex: "#FFB72B" },
  { id: "bioelectric_green", label: "Bioelectric Green", hex: "#74F24D" }
];

export const accountPalette = {
  obsidian: "#0B0E12",
  midnight: "#121925",
  panel: "rgba(18, 25, 37, 0.92)",
  panelSoft: "rgba(24, 33, 48, 0.68)",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  sandstone: "#B8A27B",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  danger: "#D8A5A5"
} as const;

export function colorForId(
  colors: AccountColorOption[] | null | undefined,
  colorId: string | null | undefined
): AccountColorOption {
  const source = colors && colors.length > 0 ? colors : fallbackAccountColors;
  return source.find((color) => color.id === colorId) ?? source[0];
}

export function splitListInput(value: string): string[] {
  return value
    .split(/[\n,;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function joinListInput(value: string[] | null | undefined): string {
  return (value ?? []).join("\n");
}

export function splitCityState(value: string | null | undefined): {
  city: string;
  state: string;
} {
  const text = (value ?? "").trim();
  if (!text) {
    return { city: "", state: "" };
  }
  const [city, ...rest] = text.split(",");
  return {
    city: city.trim(),
    state: rest.join(",").trim()
  };
}

export function combineCityState(city: string, state: string): string | null {
  const cleanCity = city.trim();
  const cleanState = state.trim();
  if (cleanCity && cleanState) {
    return `${cleanCity}, ${cleanState}`;
  }
  return cleanCity || cleanState || null;
}

export function readEnvelopeError(payload: {
  errors?: string[];
  warnings?: string[];
  message?: string;
}): string {
  return (
    payload.errors?.find((value) => value.trim()) ??
    payload.warnings?.find((value) => value.trim()) ??
    payload.message ??
    "The local account bridge did not return a detailed reason."
  );
}

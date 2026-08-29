export type ModeChipOption = {
  value: string;
  label: string;
};

type ModeChipsProps = {
  options: ModeChipOption[];
  selectedValue: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  ariaLabel?: string;
};

const palette = {
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.10)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  teal: "#7ED7D1"
} as const;

export default function ModeChips({
  options,
  selectedValue,
  onChange,
  disabled = false,
  ariaLabel = "Conversation mode"
}: ModeChipsProps) {
  return (
    <div
      aria-label={ariaLabel}
      style={{
        display: "flex",
        gap: "0.55rem",
        flexWrap: "wrap"
      }}
    >
      {options.map((option) => {
        const selected = selectedValue === option.value;

        return (
          <button
            key={option.value}
            type="button"
            onClick={() => {
              if (disabled || selected) {
                return;
              }

              onChange(option.value);
            }}
            disabled={disabled}
            aria-pressed={selected}
            style={{
              padding: "0.55rem 0.8rem",
              borderRadius: "999px",
              border: selected
                ? `1px solid ${palette.lineTeal}`
                : `1px solid ${palette.lineSilver}`,
              background: selected
                ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.76) 100%)"
                : "linear-gradient(180deg, rgba(24, 33, 48, 0.52) 0%, rgba(18, 25, 37, 0.56) 100%)",
              color: selected ? palette.teal : palette.silverMuted,
              cursor: disabled ? "default" : selected ? "default" : "pointer",
              opacity: disabled ? 0.72 : 1
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

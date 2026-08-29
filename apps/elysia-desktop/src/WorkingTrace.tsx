type WorkingTraceProps = {
  phaseLabel: string;
  phaseDetail?: string | null;
  selectedMode?: string | null;
  selectedRole?: string | null;
  selectedRuntime?: string | null;
  selectedModelRuntimeTag?: string | null;
  localityState?: string | null;
  approvalState?: string | null;
  usedFallback?: boolean | null;
  steps?: string[];
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  glowTeal: "rgba(126, 215, 209, 0.14)"
} as const;

function buildMetaItems({
  selectedMode,
  selectedRole,
  selectedRuntime,
  selectedModelRuntimeTag,
  localityState,
  approvalState,
  usedFallback
}: Omit<WorkingTraceProps, "phaseLabel" | "phaseDetail" | "steps">): string[] {
  const items: string[] = [];

  if (selectedMode) {
    items.push(`Mode ${selectedMode}`);
  }

  if (selectedRole) {
    items.push(`Role ${selectedRole}`);
  }

  if (selectedRuntime) {
    items.push(`Runtime ${selectedRuntime}`);
  }

  if (selectedModelRuntimeTag) {
    items.push(selectedModelRuntimeTag);
  }

  if (localityState) {
    items.push(`Locality ${localityState}`);
  }

  if (approvalState) {
    items.push(`Approval ${approvalState}`);
  }

  if (usedFallback === true) {
    items.push("Fallback used");
  } else if (usedFallback === false) {
    items.push("No fallback");
  }

  return items;
}

export default function WorkingTrace({
  phaseLabel,
  phaseDetail = null,
  selectedMode = null,
  selectedRole = null,
  selectedRuntime = null,
  selectedModelRuntimeTag = null,
  localityState = null,
  approvalState = null,
  usedFallback = null,
  steps = []
}: WorkingTraceProps) {
  const metaItems = buildMetaItems({
    selectedMode,
    selectedRole,
    selectedRuntime,
    selectedModelRuntimeTag,
    localityState,
    approvalState,
    usedFallback
  });

  return (
    <div
      aria-live="polite"
      aria-busy="true"
      style={{
        display: "grid",
        gap: "0.8rem",
        padding: "0.95rem 1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineTeal}`,
        background:
          "linear-gradient(180deg, rgba(16, 41, 43, 0.42) 0%, rgba(18, 25, 37, 0.76) 100%)",
        boxShadow: `0 0 18px ${palette.glowTeal}`
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: "0.8rem",
          alignItems: "flex-start",
          flexWrap: "wrap"
        }}
      >
        <div>
          <div
            style={{
              fontSize: "0.76rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.28rem"
            }}
          >
            Working trace
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.55rem",
              color: palette.silver,
              fontWeight: 700,
              lineHeight: 1.45
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: "0.62rem",
                height: "0.62rem",
                borderRadius: "999px",
                background: palette.teal,
                boxShadow: `0 0 14px ${palette.teal}`,
                flexShrink: 0
              }}
            />
            <span>{phaseLabel}</span>
          </div>

          {phaseDetail && (
            <div
              style={{
                marginTop: "0.38rem",
                color: palette.silverMuted,
                lineHeight: 1.55
              }}
            >
              {phaseDetail}
            </div>
          )}
        </div>

        <div
          style={{
            padding: "0.35rem 0.65rem",
            borderRadius: "999px",
            border: `1px solid ${palette.lineSilver}`,
            background: "rgba(11, 14, 18, 0.32)",
            color: palette.emerald,
            fontSize: "0.76rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            whiteSpace: "nowrap"
          }}
        >
          In progress
        </div>
      </div>

      {metaItems.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: "0.55rem",
            flexWrap: "wrap",
            color: palette.silverMuted,
            fontSize: "0.78rem"
          }}
        >
          {metaItems.map((item) => (
            <span
              key={item}
              style={{
                padding: "0.28rem 0.55rem",
                borderRadius: "999px",
                border: `1px solid ${palette.lineSilver}`,
                background: "rgba(11, 14, 18, 0.28)"
              }}
            >
              {item}
            </span>
          ))}
        </div>
      )}

      {steps.length > 0 && (
        <div
          style={{
            display: "grid",
            gap: "0.45rem"
          }}
        >
          {steps.map((step) => (
            <div
              key={step}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "0.55rem",
                color: palette.silverMuted,
                lineHeight: 1.5
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: "0.48rem",
                  height: "0.48rem",
                  borderRadius: "999px",
                  background: palette.bronze,
                  marginTop: "0.42rem",
                  flexShrink: 0
                }}
              />
              <span>{step}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

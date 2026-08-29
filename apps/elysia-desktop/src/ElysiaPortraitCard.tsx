import portraitImage from "../elysia-personal-portfolio/First_Image_Elysia.png";
import invokerIcon from "../elysia-personal-portfolio/Invoker_Icon.png";
import QuickInvokeLauncher from "./QuickInvokeLauncher";

type ElysiaPortraitCardProps = {
  sticky?: boolean;
  title?: string;
  subtitle?: string;
  onOpenQuickInvoke?: () => void;
};

const palette = {
  bronze: "#8A6A3C",
  bronzeSoft: "rgba(138, 106, 60, 0.52)",
  sandstone: "#B8A27B",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.74)",
  lineSilver: "rgba(199, 210, 218, 0.12)",
  frameOuter: "rgba(58, 41, 25, 0.96)",
  frameInner: "rgba(24, 33, 48, 0.96)",
  imageBackdrop: "rgba(11, 14, 18, 0.92)",
  glowBronze: "rgba(138, 106, 60, 0.16)",
  glowTeal: "rgba(126, 215, 209, 0.08)"
} as const;

export default function ElysiaPortraitCard({
  sticky = false,
  title = "Elysia",
  subtitle = "Present in chamber",
  onOpenQuickInvoke
}: ElysiaPortraitCardProps) {
  return (
    <section
      aria-label="Elysia portrait"
      style={{
        position: sticky ? "sticky" : "relative",
        top: sticky ? "0.35rem" : undefined,
        display: "flex",
        flexDirection: "column",
        gap: "0.7rem",
        padding: "0.8rem",
        borderRadius: "24px",
        border: `1px solid ${palette.bronzeSoft}`,
        background:
          "linear-gradient(180deg, rgba(42, 31, 22, 0.94) 0%, rgba(18, 25, 37, 0.98) 100%)",
        boxShadow:
          `0 16px 34px rgba(0,0,0,0.24), 0 0 24px ${palette.glowBronze}, inset 0 1px 0 rgba(255,255,255,0.03)`,
        overflow: "hidden",
        zIndex: sticky ? 1 : "auto"
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "0.7rem",
          paddingInline: "0.15rem"
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.2rem",
            minWidth: 0
          }}
        >
          <div
            style={{
              fontSize: "0.78rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: palette.sandstone
            }}
          >
            Portrait
          </div>
          <div
            style={{
              fontSize: "1.05rem",
              fontWeight: 600,
              color: palette.silver
            }}
          >
            {title}
          </div>
          <div
            style={{
              color: palette.silverMuted,
              fontSize: "0.84rem",
              lineHeight: 1.45
            }}
          >
            {subtitle}
          </div>
        </div>

        <QuickInvokeLauncher
          variant="icon"
          ariaLabel="Quick Invoke"
          title="Quick Invoke"
          onOpenQuickInvoke={onOpenQuickInvoke}
          style={{
            width: "6.15rem",
            aspectRatio: "2048 / 1365",
            borderRadius: "20px"
          }}
        >
          <img
            src={invokerIcon}
            alt=""
            aria-hidden="true"
            style={{
              display: "block",
              width: "100%",
              height: "100%",
              objectFit: "cover",
              borderRadius: "20px",
              pointerEvents: "none",
              userSelect: "none"
            }}
          />
        </QuickInvokeLauncher>
      </div>

      <div
        style={{
          padding: "0.7rem",
          borderRadius: "22px",
          border: `1px solid ${palette.bronzeSoft}`,
          background:
            "linear-gradient(180deg, rgba(60, 44, 28, 0.96) 0%, rgba(24, 33, 48, 0.94) 100%)",
          boxShadow:
            `inset 0 1px 0 rgba(255,255,255,0.03), inset 0 0 0 1px rgba(199, 210, 218, 0.05), 0 0 18px ${palette.glowTeal}`
        }}
      >
        <div
          style={{
            padding: "0.5rem",
            borderRadius: "18px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(24, 33, 48, 0.96) 0%, rgba(11, 14, 18, 0.96) 100%)"
          }}
        >
          <div
            style={{
              position: "relative",
              width: "100%",
              aspectRatio: "3 / 4",
              borderRadius: "16px",
              overflow: "hidden",
              background: palette.imageBackdrop,
              boxShadow:
                "inset 0 0 0 1px rgba(199, 210, 218, 0.06), inset 0 18px 34px rgba(0,0,0,0.12)"
            }}
          >
            <img
              src={portraitImage}
              alt="Elysia portrait"
              style={{
                display: "block",
                width: "100%",
                height: "100%",
                objectFit: "cover",
                objectPosition: "center top"
              }}
            />

            <div
              aria-hidden="true"
              style={{
                position: "absolute",
                inset: 0,
                borderRadius: "16px",
                boxShadow:
                  "inset 0 0 0 1px rgba(184, 162, 123, 0.12), inset 0 -30px 60px rgba(11, 14, 18, 0.14)"
              }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

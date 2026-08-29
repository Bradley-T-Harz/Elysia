import { useState } from "react";
import type { CSSProperties } from "react";
import { loginAccount } from "./api/bridgeClient";
import { accountPalette, readEnvelopeError } from "./accountPresentation";

type LoginPageProps = {
  onLoggedIn: () => Promise<void>;
};

export default function LoginPage({ onLoggedIn }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const result = await loginAccount({ username, password });
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      await onLoggedIn();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: "2rem",
        color: accountPalette.silver,
        background:
          "linear-gradient(180deg, #111726 0%, #0B0E12 100%)",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: "min(520px, 100%)",
          display: "grid",
          gap: "1rem",
          padding: "1.35rem",
          borderRadius: "18px",
          border: `1px solid ${accountPalette.lineSilver}`,
          background: accountPalette.panel,
          boxShadow: "0 18px 42px rgba(0,0,0,0.26)"
        }}
      >
        <div>
          <div
            style={{
              fontSize: "0.72rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: accountPalette.sandstone,
              marginBottom: "0.42rem"
            }}
          >
            Local Identity Gate
          </div>
          <h1 style={{ margin: 0, fontSize: "1.7rem" }}>Log in to Elysia</h1>
          <p style={{ color: accountPalette.silverMuted, lineHeight: 1.55 }}>
            The chamber stays closed until the local sealed session is restored.
          </p>
        </div>

        <label style={{ display: "grid", gap: "0.38rem" }}>
          <span>Username</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
            style={inputStyle}
          />
        </label>

        <label style={{ display: "grid", gap: "0.38rem" }}>
          <span>Password</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
            required
            style={inputStyle}
          />
        </label>

        {error && (
          <div
            role="alert"
            style={{
              color: accountPalette.danger,
              border: "1px solid rgba(216, 165, 165, 0.28)",
              borderRadius: "12px",
              padding: "0.75rem",
              background: "rgba(216, 165, 165, 0.08)"
            }}
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          style={{
            border: "1px solid rgba(126, 215, 209, 0.34)",
            borderRadius: "12px",
            padding: "0.78rem 1rem",
            background:
              "linear-gradient(180deg, rgba(16, 71, 75, 0.72) 0%, rgba(18, 25, 37, 0.86) 100%)",
            color: "#C7D2DA",
            cursor: saving ? "wait" : "pointer",
            fontWeight: 700
          }}
        >
          {saving ? "Opening local session..." : "Enter Chamber"}
        </button>
      </form>
    </div>
  );
}

const inputStyle: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "12px",
  background: "rgba(11, 14, 18, 0.48)",
  color: accountPalette.silver,
  padding: "0.72rem 0.78rem",
  font: "inherit"
};

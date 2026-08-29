import { useEffect, useState, type ReactNode } from "react";
import { accountPalette, readEnvelopeError } from "./accountPresentation";
import { fetchSetupState, type SetupStateEnvelope } from "./api/bridgeClient";
import ElysiaSetupPage from "./ElysiaSetupPage";

const STARTUP_RECONCILIATION_ATTEMPTS = 2;
const STARTUP_RECONCILIATION_DELAY_MS = 2_000;

export default function SetupGate({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [required, setRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [setupState, setSetupState] = useState<SetupStateEnvelope["data"] | null>(null);

  async function refresh() {
    setLoading(true);
    for (let attempt = 0; attempt < STARTUP_RECONCILIATION_ATTEMPTS; attempt += 1) {
      const result = await fetchSetupState();
      if (result.ok && result.payload.status === "ok") {
        setError(null);
        setSetupState(result.payload.data ?? null);
        setRequired(Boolean(result.payload.data?.setup_required));
        setLoading(false);
        return;
      }
      if (attempt + 1 < STARTUP_RECONCILIATION_ATTEMPTS) {
        await new Promise((resolve) => window.setTimeout(resolve, STARTUP_RECONCILIATION_DELAY_MS));
        continue;
      }
      setError(readEnvelopeError(result.payload));
      setSetupState(null);
      setRequired(false);
    }
    setLoading(false);
  }

  useEffect(() => { void refresh(); }, []);

  if (loading) return <div style={frameStyle}>Checking machine installation truth…</div>;
  if (error) {
    return (
      <div style={frameStyle}>
        <section role="alert" style={errorStyle}>
          <h1 style={{ margin: 0 }}>Machine installation truth is temporarily unavailable</h1>
          <p style={{ margin: 0 }}>{error}</p>
          <p style={{ margin: 0 }}>Elysia will not invent a Setup state while the owned local API is unavailable.</p>
          <button type="button" onClick={() => { void refresh(); }} style={retryStyle}>Retry machine check</button>
        </section>
      </div>
    );
  }
  if (required) return <ElysiaSetupPage error={error} initialState={setupState} onConfigured={refresh} />;
  return <>{children}</>;
}

const frameStyle = {
  minHeight: "100vh",
  display: "grid",
  placeItems: "center",
  background: "linear-gradient(180deg,#111726,#0B0E12)",
  color: accountPalette.silver,
  fontFamily: "Inter,ui-sans-serif,system-ui,sans-serif"
};

const errorStyle = {
  width: "min(42rem,calc(100vw - 2rem))",
  display: "grid",
  gap: "1rem",
  padding: "1.5rem",
  border: "1px solid #5f4343",
  borderRadius: "1rem",
  background: "#151923"
};

const retryStyle = {
  justifySelf: "start",
  minHeight: "2.75rem",
  padding: "0.65rem 1rem",
  borderRadius: "0.7rem",
  border: "1px solid #3b8f91",
  background: "#103f42",
  color: accountPalette.silver,
  cursor: "pointer"
};

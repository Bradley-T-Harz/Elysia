import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import {
  fetchAccountColors,
  fetchAccountState,
  logoutAccount,
  type AccountColorOption,
  type AccountStateData
} from "./api/bridgeClient";
import { accountPalette, fallbackAccountColors, readEnvelopeError } from "./accountPresentation";
import LoginPage from "./LoginPage";
import UserCreatorPage from "./UserCreatorPage";
import PersonalOnboardingPage from "./PersonalOnboardingPage";
import {
  clearMarketplaceSessionForLocalProfile,
  LOCAL_PROFILE_SESSION_OWNER_KEY
} from "./api/marketplaceClient";

type AccountSessionContextValue = {
  state: AccountStateData | null;
  colors: AccountColorOption[];
  refreshAccountState: () => Promise<void>;
  logout: () => Promise<void>;
};

const AccountSessionContext = createContext<AccountSessionContextValue | null>(null);

export function useAccountSession(): AccountSessionContextValue {
  const context = useContext(AccountSessionContext);
  if (!context) {
    throw new Error("useAccountSession must be used inside AccountGate.");
  }
  return context;
}

export function useOptionalAccountSession(): AccountSessionContextValue | null {
  return useContext(AccountSessionContext);
}

function GateFrame({
  children,
  title,
  detail
}: {
  children?: ReactNode;
  title: string;
  detail?: string;
}) {
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
      <div
        style={{
          width: "min(760px, 100%)",
          padding: "1.4rem",
          borderRadius: "18px",
          border: `1px solid ${accountPalette.lineSilver}`,
          background: accountPalette.panel,
          boxShadow: "0 18px 42px rgba(0,0,0,0.26)"
        }}
      >
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
        <h1 style={{ margin: 0, fontSize: "1.6rem" }}>{title}</h1>
        {detail && (
          <p style={{ color: accountPalette.silverMuted, lineHeight: 1.55 }}>
            {detail}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}

export default function AccountGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AccountStateData | null>(null);
  const [colors, setColors] = useState<AccountColorOption[]>(fallbackAccountColors);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offerOnboarding, setOfferOnboarding] = useState(false);
  const [onboardingResolved, setOnboardingResolved] = useState(false);

  async function refreshAccountState() {
    setError(null);
    const result = await fetchAccountState();
    if (!result.ok || result.payload.status !== "ok") {
      setState(null);
      setError(readEnvelopeError(result.payload));
      return;
    }
    setState(result.payload.data ?? null);
  }

  async function refreshColors() {
    const result = await fetchAccountColors();
    if (result.ok && result.payload.status === "ok" && result.payload.data?.colors?.length) {
      setColors(result.payload.data.colors);
    }
  }

  async function handleLogout() {
    clearMarketplaceSessionForLocalProfile();
    sessionStorage.removeItem(LOCAL_PROFILE_SESSION_OWNER_KEY);
    await logoutAccount();
    setOfferOnboarding(false);
    setOnboardingResolved(false);
    await refreshAccountState();
  }

  async function handleAccountCreated() {
    setOfferOnboarding(true);
    setOnboardingResolved(false);
    await refreshAccountState();
  }

  useEffect(() => {
    let cancelled = false;
    async function loadGate() {
      setLoading(true);
      try {
        await refreshColors();
        const result = await fetchAccountState();
        if (cancelled) return;
        if (!result.ok || result.payload.status !== "ok") {
          setError(readEnvelopeError(result.payload));
          setState(null);
        } else {
          setState(result.payload.data ?? null);
          setError(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadGate();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const userId = state?.active_user_id ?? null;
    const previous = sessionStorage.getItem(LOCAL_PROFILE_SESSION_OWNER_KEY);
    if (previous && previous !== userId) {
      clearMarketplaceSessionForLocalProfile();
    }
    if (userId) {
      sessionStorage.setItem(LOCAL_PROFILE_SESSION_OWNER_KEY, userId);
    } else {
      sessionStorage.removeItem(LOCAL_PROFILE_SESSION_OWNER_KEY);
    }
  }, [state?.active_user_id]);

  const contextValue = useMemo(
    () => ({
      state,
      colors,
      refreshAccountState,
      logout: handleLogout
    }),
    [state, colors]
  );

  if (loading) {
    return (
      <GateFrame
        title="Checking sealed local account state"
        detail="The chamber opens only after local identity truth is known."
      />
    );
  }

  if (error) {
    return (
      <GateFrame title="Local account bridge unavailable" detail={error}>
        <button
          type="button"
          onClick={() => {
            setLoading(true);
            void refreshAccountState().finally(() => setLoading(false));
          }}
          style={{
            border: `1px solid ${accountPalette.lineSilver}`,
            borderRadius: "12px",
            padding: "0.72rem 0.95rem",
            background: accountPalette.panelSoft,
            color: accountPalette.silver,
            cursor: "pointer"
          }}
        >
          Try again
        </button>
      </GateFrame>
    );
  }

  if (state?.requires_user_creation || state?.account_status === "needs_creation") {
    return (
      <AccountSessionContext.Provider value={contextValue}>
        <UserCreatorPage colors={colors} onCreated={handleAccountCreated} />
      </AccountSessionContext.Provider>
    );
  }

  if (state?.requires_login || state?.account_status === "logged_out") {
    return (
      <AccountSessionContext.Provider value={contextValue}>
        <LoginPage onLoggedIn={refreshAccountState} />
      </AccountSessionContext.Provider>
    );
  }

  if (!onboardingResolved) {
    return (
      <AccountSessionContext.Provider value={contextValue}>
        <PersonalOnboardingPage
          offeredAfterAccountCreation={offerOnboarding}
          onDone={() => {
            setOfferOnboarding(false);
            setOnboardingResolved(true);
          }}
        />
      </AccountSessionContext.Provider>
    );
  }

  return (
    <AccountSessionContext.Provider value={contextValue}>
      {children}
    </AccountSessionContext.Provider>
  );
}

import AccountGate, { useAccountSession } from "./AccountGate";
import AppShell from "./AppShell";
import SetupGate from "./SetupGate";

function AuthenticatedShell() {
  const { state } = useAccountSession();
  return <AppShell accountState={state} />;
}

export default function App() {
  return (
    <SetupGate>
      <AccountGate>
        <AuthenticatedShell />
      </AccountGate>
    </SetupGate>
  );
}

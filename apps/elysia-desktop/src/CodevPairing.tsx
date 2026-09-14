import { useEffect, useRef, useState } from "react";
import { codevRequest } from "./api/codevNative";
import type { PairingIntent } from "./api/codevContracts";

type Pairing = { pairing_id: string; intent: PairingIntent; note: string; cloud_revoked?: boolean };
export default function CodevPairing({ clientId }: { clientId: string | null }) {
  const mutation = useRef(0);
  const inFlight = useRef(false);
  const currentClient = useRef(clientId);
  currentClient.current = clientId;
  const [opened, setOpened] = useState(false);
  const [code, setCode] = useState("");
  const [pairings, setPairings] = useState<Pairing[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => { mutation.current += 1; inFlight.current = false; setBusy(false); setPairings([]); setCode(""); setError(""); setNotice(""); }, [clientId]);
  useEffect(() => {
    if (!opened || !clientId) return;
    let stopped = false;
    const refresh = async () => {
      if (inFlight.current) return;
      const version = mutation.current;
      try {
        const result = await codevRequest<{ pairings: Pairing[] }>("pairing/list", { client_id: clientId });
        if (!stopped && currentClient.current === clientId && version === mutation.current) setPairings(result.pairings);
      } catch { /* The explicit operation reports its own unavailable state. */ }
    };
    void refresh(); const timer = window.setInterval(() => void refresh(), 4000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [opened, clientId]);
  async function claim() {
    if (!clientId || inFlight.current) return;
    inFlight.current = true; const version = ++mutation.current;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await codevRequest<Pairing>("pairing/claim", { client_id: clientId, code: code.trim() });
      if (currentClient.current !== clientId || mutation.current !== version) return;
      setPairings(previous => [result, ...previous.filter(item => item.pairing_id !== result.pairing_id)]); setCode("");
    } catch (reason) { if (currentClient.current === clientId && mutation.current === version) setError(reason instanceof Error ? reason.message : "The pairing intent could not be verified."); }
    finally { if (mutation.current === version) { mutation.current += 1; inFlight.current = false; setBusy(false); } }
  }
  async function action(pairingId: string, confirm: boolean) {
    if (!clientId || inFlight.current) return;
    inFlight.current = true; const version = ++mutation.current;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await codevRequest<Pairing>(confirm ? "pairing/action" : "pairing/revoke", {
        client_id: clientId, pairing_id: pairingId, ...(confirm ? { action: "confirm", explicitly_approved: true } : {}) });
      if (currentClient.current !== clientId || mutation.current !== version) return;
      setPairings(previous => confirm ? previous.map(item => item.pairing_id === pairingId ? result : item) : previous.filter(item => item.pairing_id !== pairingId));
      setNotice(confirm ? "Approved. Return to the website to finish connecting and refresh the page. No workspace has been shared."
        : result.cloud_revoked === false ? "Local connection and grants revoked. The website could not be reached; its short-lived intent will expire."
        : "Connection and all its workspace grants revoked.");
    } catch (reason) { if (currentClient.current === clientId && mutation.current === version) setError(reason instanceof Error ? reason.message : "The pairing action could not complete."); }
    finally { if (mutation.current === version) { mutation.current += 1; inFlight.current = false; setBusy(false); } }
  }
  return <details className="codev-pairing" open={opened} onToggle={event => setOpened(event.currentTarget.open)}>
    <summary>Website connections</summary>
    <div className="codev-pairing-content">
      <p>Press Sync Codev on Marketplace Submit or Developer Forge, then paste its short-lived code here.</p>
      <form onSubmit={event => { event.preventDefault(); void claim(); }} className="codev-pairing-form">
        <label htmlFor="codev-pairing-code">Pairing code</label>
        <input id="codev-pairing-code" value={code} maxLength={49} autoComplete="off" spellCheck={false} disabled={busy}
          onChange={event => setCode(event.target.value)} placeholder="EC1.…"/>
        <button type="submit" disabled={!clientId || busy || !/^EC1\.[AW]\.[A-Za-z0-9_-]{43}$/.test(code.trim())}>Review pairing</button>
      </form>
      {error && <p role="alert" className="codev-error">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {pairings.map(pair => <article key={pair.pairing_id} className="codev-pairing-review">
        <div><strong>{pair.intent.account_label}</strong><p>{pair.intent.origin} · {pair.intent.surface === "forge" ? "Developer Forge" : "Marketplace Submit"}</p>
          <p>{pair.intent.status === "pending" ? "Awaiting your local approval" : pair.intent.status === "native_approved" ? "Waiting for the website" : "Connected"} · Expires {new Date(pair.intent.expires_at).toLocaleTimeString()}</p></div>
        <p>Connect this website account to your current local profile. Pairing shares no files or workspaces and grants no commands or publishing authority.</p>
        <div className="codev-actions">{pair.intent.status === "pending" && <button className="codev-primary" disabled={busy} onClick={() => void action(pair.pairing_id, true)}>Approve this connection</button>}
          <button disabled={busy} onClick={() => void action(pair.pairing_id, false)}>{pair.intent.status === "pending" ? "Deny" : "Revoke connection"}</button></div>
      </article>)}
    </div>
  </details>;
}

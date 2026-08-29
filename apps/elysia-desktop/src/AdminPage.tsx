import { useCallback, useEffect, useState } from "react";
import {
  applyAdminChange,
  createAccount,
  fetchAdminSummary,
  previewAdminChange,
  type AdminRosterEntry,
  type ManagedProfilePolicy
} from "./api/bridgeClient";
import type { DrawerSection } from "./RightDrawer";
import { palette, shellTokens } from "./themeTokens";

type Props = {
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
};

const defaultPolicy: ManagedProfilePolicy = {
  autonomy_maximum: 3,
  internet_allowed: false,
  addons_allowed: false,
  connectors_allowed: false,
  coding_execution_allowed: false,
  project_agent_limit: 1,
  external_mutations_allowed: false,
  background_cognition_allowed: false,
  cpu_percent_ceiling: 70,
  ram_mb_ceiling: 4096,
  vram_mb_ceiling: 4096,
  network_filter_level: "strict",
  consolidation_allowed: true,
  managed_backups_allowed: true,
  cold_archive_allowed: true,
  storage_budget_mb_ceiling: 32768,
  backup_retention_maximum: 5
};

type PendingChange = {
  preview_id: string;
  approval_token: string;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
};

function readError(payload: { errors?: string[]; message?: string }): string {
  return payload.errors?.[0] ?? payload.message ?? "The local Admin authority rejected this operation.";
}

function ManagedMemoryPolicyEditor({
  policy,
  busy,
  onPreview
}: {
  policy: ManagedProfilePolicy;
  busy: boolean;
  onPreview: (policy: ManagedProfilePolicy) => void;
}) {
  const [draft, setDraft] = useState<ManagedProfilePolicy>({ ...defaultPolicy, ...policy });

  return (
    <div style={{ display: "grid", gap: "0.45rem", marginTop: "0.65rem", padding: "0.65rem", border: `1px solid ${palette.lineBronze}`, borderRadius: "10px" }}>
      <strong style={{ color: palette.sandstone, fontSize: "0.76rem" }}>Managed memory ceilings</strong>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.7rem", color: palette.silverMuted, fontSize: "0.72rem" }}>
        <label><input type="checkbox" checked={draft.consolidation_allowed} onChange={(event) => setDraft({ ...draft, consolidation_allowed: event.target.checked })} /> Consolidation</label>
        <label><input type="checkbox" checked={draft.managed_backups_allowed} onChange={(event) => setDraft({ ...draft, managed_backups_allowed: event.target.checked })} /> Opaque managed backups</label>
        <label><input type="checkbox" checked={draft.cold_archive_allowed} onChange={(event) => setDraft({ ...draft, cold_archive_allowed: event.target.checked })} /> Cold archival</label>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.7rem", color: palette.silverMuted, fontSize: "0.72rem" }}>
        <label>Storage ceiling MiB <input aria-label="Managed storage ceiling MiB" type="number" min={512} max={10000000} value={draft.storage_budget_mb_ceiling} onChange={(event) => setDraft({ ...draft, storage_budget_mb_ceiling: Number(event.target.value) })} /></label>
        <label>Backup retention maximum <input aria-label="Managed backup retention maximum" type="number" min={1} max={50} value={draft.backup_retention_maximum} onChange={(event) => setDraft({ ...draft, backup_retention_maximum: Number(event.target.value) })} /></label>
      </div>
      <button type="button" disabled={busy} onClick={() => onPreview(draft)}>Preview managed memory ceilings</button>
      <div style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>These limits narrow background/storage authority. They never grant Admin access to profile memory or backup plaintext.</div>
    </div>
  );
}

export default function AdminPage({ onRightDrawerSectionsChange }: Props) {
  const [roster, setRoster] = useState<AdminRosterEntry[]>([]);
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [memoryStorage, setMemoryStorage] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("Loading installation-governance truth…");
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [busy, setBusy] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<"user" | "admin">("user");
  const [newManaged, setNewManaged] = useState(false);

  const load = useCallback(async () => {
    const result = await fetchAdminSummary();
    if (result.ok && result.payload.status === "ok") {
      setRoster((result.payload.data?.roster ?? []).map((profile) => ({
        ...profile,
        managed_policy: profile.managed_policy
          ? { ...defaultPolicy, ...profile.managed_policy }
          : undefined
      })));
      setEvents(result.payload.data?.events ?? []);
      setMemoryStorage(result.payload.data?.memory_storage_by_profile ?? []);
      setMessage("Objective local installation-governance truth loaded. Private content was not queried.");
      setPending(null);
      return;
    }
    setMessage(readError(result.payload));
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    onRightDrawerSectionsChange([
      {
        key: "admin_boundary",
        title: "Admin Boundary",
        state: "live",
        accent: "warm",
        rows: [
          { label: "Authority", value: "Installation governance only" },
          { label: "Content access", value: "Not granted" },
          { label: "Online identity", value: "Separate authority; no federation" }
        ]
      },
      {
        key: "managed_profiles",
        title: "Managed Profiles",
        state: "live",
        rows: [
          { label: "Visibility", value: "Supervision is disclosed to the managed profile" },
          { label: "Policy", value: "Ceilings narrow authority; they never transfer memory ownership" }
        ]
      }
    ]);
  }, [onRightDrawerSectionsChange]);

  async function plan(request: Parameters<typeof previewAdminChange>[0]) {
    setBusy(true);
    setMessage("Preparing an exact one-time change preview…");
    const result = await previewAdminChange(request);
    const data = result.payload.data;
    if (result.ok && data?.preview_id && data?.approval_token) {
      setPending(data as PendingChange);
      setMessage("Preview ready. Review before and after, then explicitly apply or discard it.");
    } else {
      setPending(null);
      setMessage(readError(result.payload));
    }
    setBusy(false);
  }

  async function applyPending() {
    if (!pending) return;
    setBusy(true);
    const result = await applyAdminChange(pending.preview_id, pending.approval_token);
    if (result.ok && result.payload.status === "ok") {
      await load();
      setMessage("The reviewed local governance change was applied and receipted.");
    } else {
      setMessage(readError(result.payload));
    }
    setBusy(false);
  }

  async function createLocalProfile() {
    setBusy(true);
    const result = await createAccount({
      username: newUsername,
      password: newPassword,
      requested_role: newRole,
      managed_profile: newRole === "user" && newManaged
    });
    if (result.ok && result.payload.status === "ok") {
      setNewUsername("");
      setNewPassword("");
      await load();
      setMessage("The local profile was created under installation authority. No online identity was created or linked.");
    } else {
      setMessage(readError(result.payload));
    }
    setBusy(false);
  }

  return (
    <main style={{ display: "grid", gap: "0.9rem", minHeight: 0, overflowY: "auto", padding: "1rem" }}>
      <section style={{ padding: "1rem", border: `1px solid ${palette.lineBronze}`, borderRadius: "16px", background: shellTokens.rightDrawerSectionBackground }}>
        <div style={{ color: palette.bronze, fontSize: "0.7rem", letterSpacing: "0.1em", textTransform: "uppercase" }}>Local installation authority</div>
        <h1 style={{ color: palette.silver, margin: "0.28rem 0" }}>Admin</h1>
        <p style={{ color: palette.silverMuted, margin: 0, lineHeight: 1.5 }}>
          Admin governs roles, sessions, and policy ceilings. It is not a content-superuser: conversations, memories, private files, projects, prompts, queries, and model context remain owned by their users.
        </p>
      </section>

      <div role="status" aria-live="polite" style={{ color: palette.silverMuted }}>{message}</div>

      <section style={{ display: "grid", gap: "0.5rem", padding: "0.9rem", border: `1px solid ${palette.lineSilver}`, borderRadius: "14px" }}>
        <h2 style={{ margin: 0, color: palette.sandstone, fontSize: "0.9rem" }}>Create a separate local profile</h2>
        <p style={{ margin: 0, color: palette.silverMuted, fontSize: "0.73rem" }}>This creates only a local Elysia identity. It never creates, federates, or elevates an Elysia Ecobotics Online account.</p>
        <input aria-label="New local username" value={newUsername} onChange={(event) => setNewUsername(event.target.value)} placeholder="Local username" />
        <input aria-label="New local password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="Local password" />
        <select aria-label="New local role" value={newRole} onChange={(event) => setNewRole(event.target.value as "user" | "admin")}><option value="user">Normal local user</option><option value="admin">Local Admin</option></select>
        {newRole === "user" && <label style={{ color: palette.silverMuted }}><input type="checkbox" checked={newManaged} onChange={(event) => setNewManaged(event.target.checked)} /> Create as visibly managed/supervised</label>}
        <button type="button" disabled={busy || newUsername.trim().length < 3 || newPassword.length < 12} onClick={() => void createLocalProfile()}>Create local profile</button>
      </section>

      {pending && (
        <section style={{ padding: "0.9rem", border: `1px solid ${palette.teal}`, borderRadius: "14px", background: "rgba(16,41,43,0.48)" }}>
          <strong style={{ color: palette.teal }}>Exact change preview</strong>
          <pre style={{ whiteSpace: "pre-wrap", color: palette.silverMuted, fontSize: "0.72rem" }}>{JSON.stringify({ before: pending.before, after: pending.after }, null, 2)}</pre>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" disabled={busy} onClick={() => void applyPending()}>Apply reviewed change</button>
            <button type="button" disabled={busy} onClick={() => setPending(null)}>Discard</button>
          </div>
        </section>
      )}

      <section style={{ display: "grid", gap: "0.65rem" }} aria-label="Local profile roster">
        {roster.map((profile) => {
          // Roster load normalizes this object once. Keep its reference stable
          // across parent renders so an in-progress Admin edit cannot be reset
          // by the editor's policy synchronization effect.
          const policy = profile.managed_policy ?? defaultPolicy;
          return (
            <article key={profile.user_id} style={{ padding: "0.9rem", border: `1px solid ${palette.lineSilver}`, borderRadius: "14px", background: shellTokens.rightDrawerSectionBackground }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <div>
                  <strong style={{ color: palette.silver }}>{profile.username}</strong>
                  <div style={{ color: palette.silverMuted, fontSize: "0.74rem" }}>{profile.role} · {profile.enabled ? "enabled" : "disabled"} · {profile.active_session_count} active sessions</div>
                </div>
                {profile.managed && <span style={{ color: palette.sandstone }}>Managed / visibly supervised</span>}
              </div>
              {profile.role !== "installation_owner" && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem", marginTop: "0.7rem" }}>
                  {profile.role === "user" && <button disabled={busy} type="button" onClick={() => void plan({ target_user_id: profile.user_id, change_kind: "set_role", target_role: "admin", reason: "Explicit local Admin role change" })}>Preview Admin role</button>}
                  {profile.role === "admin" && <button disabled={busy} type="button" onClick={() => void plan({ target_user_id: profile.user_id, change_kind: "set_role", target_role: "user", reason: "Explicit local user role change" })}>Preview normal role</button>}
                  {profile.role === "user" && <button disabled={busy} type="button" onClick={() => void plan({ target_user_id: profile.user_id, change_kind: "set_managed_policy", managed: !profile.managed, managed_policy: !profile.managed ? policy : undefined, reason: profile.managed ? "Explicitly remove managed-profile ceilings" : "Explicitly establish visible managed-profile ceilings" })}>{profile.managed ? "Preview unsupervise" : "Preview managed policy"}</button>}
                  <button disabled={busy} type="button" onClick={() => void plan({ target_user_id: profile.user_id, change_kind: "set_account_enabled", enabled: !profile.enabled, reason: profile.enabled ? "Explicitly disable local account" : "Explicitly restore local account" })}>Preview {profile.enabled ? "disable" : "enable"}</button>
                </div>
              )}
              {profile.managed && <pre style={{ whiteSpace: "pre-wrap", color: palette.silverMuted, fontSize: "0.7rem" }}>{JSON.stringify(policy, null, 2)}</pre>}
              {profile.managed && profile.role === "user" && (
                <ManagedMemoryPolicyEditor
                  key={`${profile.user_id}:${profile.policy_version}`}
                  policy={policy}
                  busy={busy}
                  onPreview={(managedPolicy) => void plan({
                    target_user_id: profile.user_id,
                    change_kind: "set_managed_policy",
                    managed: true,
                    managed_policy: managedPolicy,
                    reason: "Explicit managed-profile Memory maintenance ceiling change"
                  })}
                />
              )}
            </article>
          );
        })}
      </section>

      <section style={{ padding: "0.9rem", border: `1px solid ${palette.lineSilver}`, borderRadius: "14px" }}>
        <h2 style={{ color: palette.sandstone, fontSize: "0.9rem" }}>Profile storage and maintenance truth</h2>
        <p style={{ color: palette.silverMuted, fontSize: "0.72rem" }}>Metadata-only installation governance. No memory, conversation, project, prompt, query, backup plaintext, or relationship content was queried.</p>
        {memoryStorage.map((entry) => (
          <div key={String(entry.user_id)} style={{ color: palette.silverMuted, fontSize: "0.72rem", padding: "0.36rem 0", borderTop: `1px solid ${palette.lineSilver}` }}>
            {String(entry.user_id)} · {String(entry.record_count ?? 0)} records · {String(entry.managed_object_bytes ?? 0)} managed-object bytes · {String(entry.managed_backup_count ?? 0)} backups · {String(entry.maintenance_attention_count ?? 0)} maintenance events · content included: no
          </div>
        ))}
        {!memoryStorage.length && <div style={{ color: palette.silverMuted, fontSize: "0.72rem" }}>No profile storage metadata is present.</div>}
      </section>

      <section style={{ padding: "0.9rem", border: `1px solid ${palette.lineSilver}`, borderRadius: "14px" }}>
        <h2 style={{ color: palette.sandstone, fontSize: "0.9rem" }}>Objective governance events</h2>
        {events.slice(0, 20).map((event) => <div key={String(event.event_id)} style={{ color: palette.silverMuted, fontSize: "0.72rem", padding: "0.36rem 0", borderTop: `1px solid ${palette.lineSilver}` }}>{String(event.created_at_utc ?? "")} · {String(event.safe_summary ?? event.event_type ?? "Governance event")}</div>)}
      </section>
    </main>
  );
}

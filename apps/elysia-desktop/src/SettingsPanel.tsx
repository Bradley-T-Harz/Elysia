import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  fetchMemorySettings,
  updateMemorySettings,
  type MemoryFoundationalSettings
} from "./api/bridgeClient";
import {
  activateEmergencyStop,
  resetEmergencyStop
} from "./api/emergencyClient";
import { clearMarketplaceSessionForLocalProfile } from "./api/marketplaceClient";
import {
  STARTUP_ROOM_OPTIONS,
  type DesktopDensity,
  type DesktopMotionPreference,
  type DesktopPreferences,
  type DesktopStartupRoom,
  type LeftRailDefaultBehavior
} from "./desktopPreferences";
import { palette, shellTokens } from "./themeTokens";

export type SettingsDestination = "memory" | "governance" | "health" | "capabilities";

type SettingsPanelProps = {
  onClose: () => void;
  onOpenRoom?: (room: SettingsDestination) => void;
  desktopPreferences: DesktopPreferences;
  onDesktopPreferencesChange: (preferences: DesktopPreferences) => void;
  onDesktopPreferencesReset: () => void;
};

type ControlRow = { label: string; description: string; control: ReactNode };

const densityOptions: ReadonlyArray<{ value: DesktopDensity; label: string }> = [
  { value: "comfortable", label: "Comfortable" },
  { value: "compact", label: "Compact" }
];
const motionOptions: ReadonlyArray<{ value: DesktopMotionPreference; label: string }> = [
  { value: "system", label: "Follow system" },
  { value: "reduced", label: "Reduce chamber motion" }
];
const leftRailBehaviorOptions: ReadonlyArray<{ value: LeftRailDefaultBehavior; label: string }> = [
  { value: "collapsed", label: "Collapsed by default" },
  { value: "expanded", label: "Expanded by default" }
];
const startupRoomOptions: ReadonlyArray<{ value: DesktopStartupRoom; label: string }> =
  STARTUP_ROOM_OPTIONS.map((option) => ({ value: option.id, label: option.label }));
const autonomyConsequences: Record<number, string> = {
  1: "Directed: direct requests, local context, audit, safety, and explicitly requested tools; no autonomous initiative.",
  2: "Assisted: may propose next steps, candidates, contradiction checks, and routine safe local maintenance.",
  3: "Collaborative: may take bounded useful substeps, research when permitted, maintain continuity, and adapt local resources.",
  4: "Proactive: may run visible budgeted investigations and background plans with checkpoints and cancellation.",
  5: "Stewarded Initiative: may sustain approved multi-stage local work, but never bypasses approval, privacy, Internet OFF, or stop authority."
};

function withPart2DDefaults(settings: MemoryFoundationalSettings): MemoryFoundationalSettings {
  return {
    ...settings,
    preferred_reasoning_gear: settings.preferred_reasoning_gear ?? "automatic",
    autonomy_domain_overrides: settings.autonomy_domain_overrides ?? {},
    compute_preference: settings.compute_preference ?? "automatic",
    model_performance_preference: settings.model_performance_preference ?? "balanced",
    background_cognition_enabled: settings.background_cognition_enabled ?? false,
    cpu_percent_ceiling: settings.cpu_percent_ceiling ?? 85,
    ram_mb_ceiling: settings.ram_mb_ceiling ?? 16384,
    vram_mb_ceiling: settings.vram_mb_ceiling ?? 12288,
    max_background_jobs: settings.max_background_jobs ?? 2,
    memory_storage_profile: settings.memory_storage_profile ?? "balanced",
    storage_budget_mode: settings.storage_budget_mode ?? "absolute_mb",
    storage_budget_value: settings.storage_budget_value ?? 8192,
    emergency_free_space_reserve_mb: settings.emergency_free_space_reserve_mb ?? 2048,
    consolidation_enabled: settings.consolidation_enabled ?? true,
    consolidation_schedule: settings.consolidation_schedule ?? "daily",
    consolidation_resource_percent: settings.consolidation_resource_percent ?? 25,
    backup_enabled: settings.backup_enabled ?? false,
    backup_schedule: settings.backup_schedule ?? "weekly",
    backup_retention_count: settings.backup_retention_count ?? 3,
    retention_policy: settings.retention_policy ?? "balanced",
    hot_retention_days: settings.hot_retention_days ?? 14,
    cold_after_days: settings.cold_after_days ?? 180,
    prospective_notifications_enabled: settings.prospective_notifications_enabled ?? true
  };
}

function SettingSelect<TValue extends string>({ label, value, options, onChange, disabled = false }: {
  label: string;
  value: TValue;
  options: ReadonlyArray<{ value: TValue; label: string }>;
  onChange: (value: TValue) => void;
  disabled?: boolean;
}) {
  return (
    <select aria-label={label} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value as TValue)} style={{ width: "100%", padding: "0.5rem 0.58rem", borderRadius: "10px", border: "1px solid rgba(126, 215, 209, 0.28)", background: "rgba(11, 14, 18, 0.72)", color: palette.silver, cursor: disabled ? "wait" : "pointer" }}>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  );
}

function ControlSection({ title, note, rows }: { title: string; note: string; rows: ControlRow[] }) {
  return (
    <section style={{ display: "grid", gap: "0.62rem", padding: "0.82rem", borderRadius: "15px", border: `1px solid ${palette.lineSilver}`, background: shellTokens.rightDrawerSectionBackground }}>
      <div style={{ display: "grid", gap: "0.18rem" }}>
        <h3 style={{ margin: 0, color: palette.sandstone, fontSize: "0.76rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>{title}</h3>
        <p style={{ margin: 0, color: palette.silverMuted, fontSize: "0.72rem", lineHeight: 1.42 }}>{note}</p>
      </div>
      {rows.map((row) => (
        <div key={row.label} style={{ display: "grid", gap: "0.3rem", paddingTop: "0.52rem", borderTop: `1px solid ${palette.lineSilver}` }}>
          <strong style={{ color: palette.silver, fontSize: "0.75rem" }}>{row.label}</strong>
          <span style={{ color: palette.silverMuted, fontSize: "0.71rem", lineHeight: 1.45 }}>{row.description}</span>
          {row.control}
        </div>
      ))}
    </section>
  );
}

function RoomLinkButton({ room, label, onOpenRoom }: { room: SettingsDestination; label: string; onOpenRoom: (room: SettingsDestination) => void }) {
  return <button type="button" onClick={() => onOpenRoom(room)} style={{ padding: "0.48rem 0.6rem", borderRadius: "10px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43, 31, 21, 0.34)", color: palette.sandstone, cursor: "pointer" }}>{label}</button>;
}

function MemoryAndAuthorityControls() {
  const [settings, setSettings] = useState<MemoryFoundationalSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingAutonomy, setPendingAutonomy] = useState<number | null>(null);
  const [message, setMessage] = useState("Loading authoritative per-account controls…");

  useEffect(() => {
    let cancelled = false;
    void fetchMemorySettings().then((result) => {
      if (cancelled) return;
      const loaded = result.payload.data?.settings as MemoryFoundationalSettings | undefined;
      if (result.ok && loaded) {
        setSettings(withPart2DDefaults(loaded));
        setMessage("Authoritative per-account controls loaded.");
      } else {
        setMessage(result.payload.errors?.[0] ?? "Per-account controls are unavailable.");
      }
    });
    return () => { cancelled = true; };
  }, []);

  async function persist(next: MemoryFoundationalSettings) {
    if (saving) return;
    setSaving(true);
    setMessage("Saving authoritative per-account behavior…");
    const result = await updateMemorySettings(next);
    const saved = result.payload.data?.settings as MemoryFoundationalSettings | undefined;
    if (result.ok && saved) {
      setSettings(withPart2DDefaults(saved));
      setMessage("Saved. Runtime readers now use this persisted account policy.");
    } else {
      setMessage(result.payload.errors?.[0] ?? "The setting was rejected; authoritative state was not changed.");
      const reread = await fetchMemorySettings();
      const authoritative = reread.payload.data?.settings as MemoryFoundationalSettings | undefined;
      if (reread.ok && authoritative) setSettings(withPart2DDefaults(authoritative));
    }
    setSaving(false);
  }

  if (!settings) {
    return <div role="status" style={{ color: palette.silverMuted, padding: "0.8rem", border: `1px solid ${palette.lineSilver}`, borderRadius: "14px" }}>{message}</div>;
  }

  const rows: ControlRow[] = [
    {
      label: "Memory recording",
      description: "Controls whether explicit durable Memory recording is allowed for this account.",
      control: <label style={{ color: palette.silver, fontSize: "0.75rem" }}><input type="checkbox" disabled={saving} checked={settings.memory_recording_enabled} onChange={(event) => void persist({ ...settings, memory_recording_enabled: event.target.checked })} /> Record explicitly approved memories</label>
    },
    {
      label: "Storage resource profile",
      description: "Changes the persisted local Memory storage posture used by resource-aware Memory services.",
      control: <SettingSelect label="Memory storage profile" disabled={saving} value={settings.storage_resource_profile} options={[{ value: "core_local", label: "Core local" }, { value: "balanced_local", label: "Balanced local" }, { value: "minimal_local", label: "Minimal local" }]} onChange={(storage_resource_profile) => void persist({ ...settings, storage_resource_profile })} />
    },
    {
      label: "Long-term memory profile",
      description: "Controls real tiering, compaction, compression, and archive policy. It never authorizes silent deletion.",
      control: <SettingSelect label="Long-term memory profile" disabled={saving} value={settings.memory_storage_profile} options={[{ value: "efficient", label: "Efficient" }, { value: "balanced", label: "Balanced" }, { value: "deep_memory", label: "Deep Memory" }, { value: "custom", label: "Custom" }]} onChange={(memory_storage_profile) => void persist({ ...settings, memory_storage_profile })} />
    },
    {
      label: "Storage budget and emergency reserve",
      description: "Sets a real per-account budget and a free-space floor. Pressure pauses nonessential work; it never hard-deletes memory.",
      control: <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "0.4rem" }}>
        <SettingSelect label="Memory storage budget mode" disabled={saving} value={settings.storage_budget_mode} options={[{ value: "absolute_mb", label: "MiB" }, { value: "percent", label: "Percent" }]} onChange={(storage_budget_mode) => void persist({ ...settings, storage_budget_mode })} />
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Budget<input aria-label="Memory storage budget value" type="number" min={1} max={settings.storage_budget_mode === "percent" ? 95 : 10000000} disabled={saving} value={settings.storage_budget_value} onChange={(event) => void persist({ ...settings, storage_budget_value: Number(event.target.value) })} /></label>
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Reserve MiB<input aria-label="Emergency free space reserve MiB" type="number" min={256} max={1000000} disabled={saving} value={settings.emergency_free_space_reserve_mb} onChange={(event) => void persist({ ...settings, emergency_free_space_reserve_mb: Number(event.target.value) })} /></label>
      </div>
    },
    {
      label: "Consolidation policy",
      description: "Controls governed, checkpointed Memory maintenance through the existing Compute Governor and emergency stop.",
      control: <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "0.4rem" }}>
        <label style={{ color: palette.silver, fontSize: "0.72rem" }}><input type="checkbox" disabled={saving} checked={settings.consolidation_enabled} onChange={(event) => void persist({ ...settings, consolidation_enabled: event.target.checked })} /> Enabled</label>
        <SettingSelect label="Consolidation schedule" disabled={saving} value={settings.consolidation_schedule} options={[{ value: "manual", label: "Manual" }, { value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }]} onChange={(consolidation_schedule) => void persist({ ...settings, consolidation_schedule })} />
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Resource %<input aria-label="Consolidation resource percent" type="number" min={5} max={75} disabled={saving} value={settings.consolidation_resource_percent} onChange={(event) => void persist({ ...settings, consolidation_resource_percent: Number(event.target.value) })} /></label>
      </div>
    },
    {
      label: "Backup policy",
      description: "Controls opaque encrypted managed backups. Portable user exports still require user-controlled recovery material in Memory.",
      control: <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "0.4rem" }}>
        <label style={{ color: palette.silver, fontSize: "0.72rem" }}><input type="checkbox" disabled={saving} checked={settings.backup_enabled} onChange={(event) => void persist({ ...settings, backup_enabled: event.target.checked })} /> Enabled</label>
        <SettingSelect label="Backup schedule" disabled={saving} value={settings.backup_schedule} options={[{ value: "manual", label: "Manual" }, { value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }]} onChange={(backup_schedule) => void persist({ ...settings, backup_schedule })} />
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Retain<input aria-label="Managed backup retention count" type="number" min={1} max={50} disabled={saving} value={settings.backup_retention_count} onChange={(event) => void persist({ ...settings, backup_retention_count: Number(event.target.value) })} /></label>
      </div>
    },
    {
      label: "Retention and tier timing",
      description: "Controls non-destructive lifecycle timing. Expiry, archive, suppression, supersession, and hard delete remain distinct operations.",
      control: <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: "0.4rem" }}>
        <SettingSelect label="Retention policy" disabled={saving} value={settings.retention_policy} options={[{ value: "conservative", label: "Conservative" }, { value: "balanced", label: "Balanced" }, { value: "compact", label: "Compact" }]} onChange={(retention_policy) => void persist({ ...settings, retention_policy })} />
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Hot days<input aria-label="Hot memory retention days" type="number" min={1} max={3650} disabled={saving} value={settings.hot_retention_days} onChange={(event) => void persist({ ...settings, hot_retention_days: Number(event.target.value) })} /></label>
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Cold after<input aria-label="Cold memory age days" type="number" min={7} max={36500} disabled={saving} value={settings.cold_after_days} onChange={(event) => void persist({ ...settings, cold_after_days: Number(event.target.value) })} /></label>
      </div>
    },
    {
      label: "Prospective-memory notifications",
      description: "Controls local notification eligibility for owned reminders and deadlines; it grants no connector or external-message authority.",
      control: <label style={{ color: palette.silver, fontSize: "0.75rem" }}><input type="checkbox" disabled={saving} checked={settings.prospective_notifications_enabled} onChange={(event) => void persist({ ...settings, prospective_notifications_enabled: event.target.checked })} /> Allow local prospective notifications</label>
    },
    {
      label: "Default memory privacy",
      description: "Applies the selected privacy class to new explicit Memory records; sealed writes still require an unlocked vault.",
      control: <SettingSelect label="Default memory privacy" disabled={saving} value={settings.default_privacy} options={[{ value: "normal", label: "Normal" }, { value: "private", label: "Private" }, { value: "sealed", label: "Sealed" }]} onChange={(default_privacy) => void persist({ ...settings, default_privacy })} />
    },
    {
      label: "Candidate-memory behavior",
      description: "Controls whether inferred personal material must be reviewed before it can become approved identity truth.",
      control: <SettingSelect label="Candidate review posture" disabled={saving} value={settings.candidate_behavior} options={[{ value: "review_all", label: "Review all" }, { value: "review_personal_inference", label: "Review personal inference" }, { value: "direct_explicit_only", label: "Direct explicit only" }]} onChange={(candidate_behavior) => void persist({ ...settings, candidate_behavior })} />
    },
    {
      label: "Autonomy level",
      description: "Changes the authoritative five-level ceiling used by runtime planning and bounded Project goal pursuit. It never bypasses approval or policy ceilings.",
      control: <div style={{ display: "grid", gap: "0.4rem" }}>
        <SettingSelect label="Autonomy level" disabled={saving} value={String(pendingAutonomy ?? settings.autonomy_level)} options={[1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: `Level ${value}` }))} onChange={(value) => setPendingAutonomy(Number(value))} />
        <span style={{ color: palette.silverMuted, fontSize: "0.68rem", lineHeight: 1.42 }}>{autonomyConsequences[pendingAutonomy ?? settings.autonomy_level]}</span>
        {pendingAutonomy !== null && pendingAutonomy !== settings.autonomy_level && <div aria-label="Autonomy consequence preview" style={{ display: "grid", gap: "0.36rem", padding: "0.48rem", border: `1px solid ${palette.lineBronze}`, borderRadius: "10px" }}>
          <strong style={{ color: palette.sandstone, fontSize: "0.69rem" }}>Consequence preview: Level {settings.autonomy_level} → Level {pendingAutonomy}</strong>
          <span style={{ color: palette.silverMuted, fontSize: "0.67rem" }}>Domain, managed-profile, approval, privacy, ownership, Internet, and emergency ceilings remain stricter authorities.</span>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <button type="button" disabled={saving} onClick={() => void persist({ ...settings, autonomy_level: pendingAutonomy, autonomy_domain_overrides: Object.fromEntries(Object.entries(settings.autonomy_domain_overrides).map(([domain, value]) => [domain, Math.min(value, pendingAutonomy)])) })}>Apply reviewed autonomy change</button>
            <button type="button" disabled={saving} onClick={() => setPendingAutonomy(null)}>Discard autonomy change</button>
          </div>
        </div>}
      </div>
    },
    {
      label: "Preferred reasoning depth",
      description: "Automatic starts with the cheapest adequate gear. A preference may request more depth but cannot grant tool, network, or mutation authority.",
      control: <SettingSelect label="Preferred reasoning gear" disabled={saving} value={settings.preferred_reasoning_gear} options={[{ value: "automatic", label: "Automatic" }, { value: "reflex", label: "Reflex" }, { value: "quick", label: "Quick" }, { value: "standard", label: "Standard" }, { value: "deep", label: "Deep" }, { value: "deliberative", label: "Deliberative" }, { value: "research_engineering", label: "Research / Engineering" }]} onChange={(preferred_reasoning_gear) => void persist({ ...settings, preferred_reasoning_gear })} />
    },
    ...Object.entries({ memory_capture: "Memory capture", scientific_promotion: "Scientific promotion", web_initiative: "Web initiative", project_initiative: "Project initiative", background_cognition: "Background cognition", coding_execution: "Coding / execution", external_mutations: "External mutations" }).map(([domain, label]): ControlRow => ({
      label: `${label} autonomy ceiling`,
      description: "This domain-specific value may only narrow the account level and all stronger constitutional, installation, and managed-profile ceilings.",
      control: <SettingSelect label={`${label} autonomy ceiling`} disabled={saving} value={String(Math.min(settings.autonomy_domain_overrides[domain] ?? settings.autonomy_level, settings.autonomy_level))} options={Array.from({ length: settings.autonomy_level }, (_, index) => index + 1).map((value) => ({ value: String(value), label: `Level ${value}` }))} onChange={(value) => void persist({ ...settings, autonomy_domain_overrides: { ...settings.autonomy_domain_overrides, [domain]: Number(value) } })} />
    })),
    {
      label: "Compute preference",
      description: "Guides the Compute Governor. Resource, privacy, availability, and workload ceilings remain authoritative.",
      control: <SettingSelect label="Compute preference" disabled={saving} value={settings.compute_preference} options={[{ value: "automatic", label: "Automatic" }, { value: "cpu", label: "Prefer CPU" }, { value: "gpu", label: "Prefer GPU" }]} onChange={(compute_preference) => void persist({ ...settings, compute_preference })} />
    },
    {
      label: "Model performance preference",
      description: "Balances measured quality, latency, residency, and local resource cost during model routing.",
      control: <SettingSelect label="Model performance preference" disabled={saving} value={settings.model_performance_preference} options={[{ value: "balanced", label: "Balanced" }, { value: "quality", label: "Quality" }, { value: "latency", label: "Latency" }, { value: "resource", label: "Resource saver" }]} onChange={(model_performance_preference) => void persist({ ...settings, model_performance_preference })} />
    },
    {
      label: "Background cognition",
      description: "Allows visible, owned, bounded work through Elysia's governed scheduler within autonomy, resource, and managed-profile ceilings.",
      control: <label style={{ color: palette.silver, fontSize: "0.75rem" }}><input type="checkbox" disabled={saving} checked={settings.background_cognition_enabled} onChange={(event) => void persist({ ...settings, background_cognition_enabled: event.target.checked })} /> Allow bounded background cognition</label>
    },
    {
      label: "Resource ceilings",
      description: "Hard per-profile CPU, RAM, VRAM, and background-job ceilings consumed by governed schedulers.",
      control: <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: "0.4rem" }}>
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>CPU %<input aria-label="Maximum CPU percent" type="number" min={10} max={100} disabled={saving} value={settings.cpu_percent_ceiling} onChange={(event) => void persist({ ...settings, cpu_percent_ceiling: Number(event.target.value) })} /></label>
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>RAM MiB<input aria-label="Maximum RAM MiB" type="number" min={512} max={262144} disabled={saving} value={settings.ram_mb_ceiling} onChange={(event) => void persist({ ...settings, ram_mb_ceiling: Number(event.target.value) })} /></label>
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>VRAM MiB<input aria-label="Maximum VRAM MiB" type="number" min={0} max={131072} disabled={saving} value={settings.vram_mb_ceiling} onChange={(event) => void persist({ ...settings, vram_mb_ceiling: Number(event.target.value) })} /></label>
        <label style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Background jobs<input aria-label="Maximum background jobs" type="number" min={0} max={32} disabled={saving} value={settings.max_background_jobs} onChange={(event) => void persist({ ...settings, max_background_jobs: Number(event.target.value) })} /></label>
      </div>
    },
    {
      label: "Internet master switch",
      description: "OFF fails closed for Elysia's non-local research and connector paths. ON permits only governed network capabilities with their own disclosure and policy gates.",
      control: <label style={{ color: palette.silver, fontSize: "0.75rem" }}><input type="checkbox" disabled={saving} checked={settings.internet_master_enabled} onChange={(event) => void persist({ ...settings, internet_master_enabled: event.target.checked })} /> Allow governed Internet capabilities</label>
    },
    {
      label: "Memory retrieval breadth",
      description: "Changes how much authorized prior context the working workspace may consider. Privacy and ownership gates always run first.",
      control: <SettingSelect label="Memory retrieval breadth" disabled={saving} value={settings.retrieval_breadth} options={[{ value: "focused", label: "Focused" }, { value: "balanced", label: "Balanced" }, { value: "broad", label: "Broad" }]} onChange={(retrieval_breadth) => void persist({ ...settings, retrieval_breadth })} />
    },
    {
      label: "Research initiative",
      description: "Controls whether governed public research is started only when asked, when clearly useful, or proactively within the existing autonomy ceiling.",
      control: <SettingSelect label="Research initiative" disabled={saving} value={settings.research_initiative} options={[{ value: "manual", label: "Only when asked" }, { value: "balanced", label: "When clearly useful" }, { value: "proactive", label: "Proactive within limits" }]} onChange={(research_initiative) => void persist({ ...settings, research_initiative })} />
    },
    {
      label: "Public research safe search",
      description: "Changes the persisted SearXNG safe-search level for public queries. It does not relax privacy, egress, or untrusted-content controls.",
      control: <SettingSelect label="Public research safe search" disabled={saving} value={settings.safe_search_level} options={[{ value: "strict", label: "Strict" }, { value: "moderate", label: "Moderate" }, { value: "off", label: "Off" }]} onChange={(safe_search_level) => void persist({ ...settings, safe_search_level })} />
    }
  ];

  return (
    <>
      <ControlSection title="Memory, privacy, and authority" note="Controls write validated authoritative per-account state; autonomy changes receive an explicit consequence preview before apply." rows={rows} />
      <div role="status" aria-live="polite" style={{ color: palette.silverMuted, fontSize: "0.7rem", lineHeight: 1.45 }}>{message}</div>
    </>
  );
}

function EmergencySettingsControl() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(
    "STOP is available globally and here. Resuming requires Installation Owner or Admin authority."
  );

  async function stopGovernedWork() {
    if (busy) return;
    setBusy(true);
    setMessage("Stopping governed work and closing connector authority…");
    clearMarketplaceSessionForLocalProfile();
    const result = await activateEmergencyStop("Operator emergency stop from Desktop Settings");
    setMessage(
      result.ok
        ? "Emergency posture is active. Governance contains the content-free cleanup receipt."
        : result.payload.errors?.[0] ?? "Native hard stop was invoked; inspect Governance before recovery."
    );
    setBusy(false);
  }

  async function resumeGovernedWork() {
    if (busy) return;
    setBusy(true);
    setMessage("Verifying Installation Owner or Admin recovery authority…");
    const result = await resetEmergencyStop();
    setMessage(
      result.ok
        ? "Emergency posture reset after explicit governed recovery."
        : result.payload.errors?.[0] ?? "Installation Owner or Admin recovery is required."
    );
    setBusy(false);
  }

  return (
    <div style={{ display: "grid", gap: "0.4rem" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.42rem" }}>
        <button type="button" disabled={busy} onClick={() => void stopGovernedWork()} style={{ padding: "0.5rem 0.62rem", borderRadius: "10px", border: "1px solid #E36B58", background: "rgba(132, 32, 28, 0.68)", color: "#F4D3CD", fontWeight: 800, cursor: busy ? "wait" : "pointer" }}>STOP governed work</button>
        <button type="button" disabled={busy} onClick={() => void resumeGovernedWork()} style={{ padding: "0.5rem 0.62rem", borderRadius: "10px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43, 31, 21, 0.34)", color: palette.sandstone, cursor: busy ? "wait" : "pointer" }}>Owner/Admin resume</button>
      </div>
      <span role="status" aria-live="polite" style={{ color: palette.silverMuted, fontSize: "0.68rem", lineHeight: 1.42 }}>{message}</span>
    </div>
  );
}

export default function SettingsPanel({ onClose, onOpenRoom, desktopPreferences, onDesktopPreferencesChange, onDesktopPreferencesReset }: SettingsPanelProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [preferencesReset, setPreferencesReset] = useState(false);
  useEffect(() => { closeButtonRef.current?.focus(); }, []);

  function updateDesktopPreferences(update: Partial<DesktopPreferences>) {
    setPreferencesReset(false);
    onDesktopPreferencesChange({ ...desktopPreferences, ...update });
  }
  function openRoom(room: SettingsDestination) {
    onOpenRoom?.(room);
    onClose();
  }

  const chamberRows: ControlRow[] = [
    { label: "Density / compactness", description: "Changes chamber spacing and persists on this device.", control: <SettingSelect label="UI density" value={desktopPreferences.density} options={densityOptions} onChange={(density) => updateDesktopPreferences({ density })} /> },
    { label: "Reduced motion", description: "Follows the operating-system preference or suppresses chamber transitions.", control: <SettingSelect label="Motion preference" value={desktopPreferences.motionPreference} options={motionOptions} onChange={(motionPreference) => updateDesktopPreferences({ motionPreference })} /> },
    { label: "Left rail behavior", description: "Changes the initial navigation-group expansion while keeping the active room visible.", control: <SettingSelect label="Left rail default group behavior" value={desktopPreferences.leftRailDefaultBehavior} options={leftRailBehaviorOptions} onChange={(leftRailDefaultBehavior) => updateDesktopPreferences({ leftRailDefaultBehavior })} /> },
    { label: "Startup room", description: "Chooses the room opened on the next chamber mount; invalid saved values fail safely to Chamber.", control: <SettingSelect label="Startup room" value={desktopPreferences.startupRoom} options={startupRoomOptions} onChange={(startupRoom) => updateDesktopPreferences({ startupRoom })} /> },
    { label: "Reset chamber preferences", description: "Resets only the four local chamber controls above. Accounts, projects, Memory, governance, models, and profiles are untouched.", control: <div style={{ display: "grid", gap: "0.35rem" }}><button type="button" onClick={() => { onDesktopPreferencesReset(); setPreferencesReset(true); }} style={{ justifySelf: "start", padding: "0.48rem 0.62rem", borderRadius: "10px", border: `1px solid ${palette.lineBronze}`, background: "rgba(43, 31, 21, 0.34)", color: palette.sandstone, cursor: "pointer" }}>Reset chamber preferences</button>{preferencesReset && <span role="status" style={{ color: palette.silverMuted, fontSize: "0.68rem" }}>Chamber preferences reset; no user or body data changed.</span>}</div> }
  ];
  const emergencyRows: ControlRow[] = [
    {
      label: "Emergency stop and governed recovery",
      description: "Stops active requests, workers, sustained goals, GPU leases, background compute, connector authorization, and unlocked Sealed Memory. Recovery is explicit and role-gated; it never deletes canonical user data.",
      control: <EmergencySettingsControl />
    }
  ];

  return (
    <div id="elysia-settings-panel" role="dialog" aria-modal="false" aria-labelledby="elysia-settings-title" style={{ position: "absolute", top: "calc(100% + 1.15rem)", right: 0, zIndex: 40, display: "grid", gridTemplateRows: "auto minmax(0, 1fr)", width: "min(440px, calc(100vw - 2rem))", maxHeight: "calc(100vh - 104px)", overflow: "hidden", borderRadius: "18px", border: `1px solid ${palette.lineBronze}`, background: shellTokens.rightDrawerBackground, boxShadow: "0 24px 56px rgba(0, 0, 0, 0.48), inset 0 1px 0 rgba(255,255,255,0.04)" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem", padding: "0.88rem 0.92rem 0.78rem", borderBottom: `1px solid ${palette.lineSilver}`, background: shellTokens.topBarBackground }}>
        <div style={{ display: "grid", gap: "0.28rem" }}>
          <div style={{ color: palette.bronze, fontSize: "0.68rem", letterSpacing: "0.1em", textTransform: "uppercase" }}>Real user control</div>
          <h2 id="elysia-settings-title" style={{ margin: 0, color: palette.silver, fontSize: "1rem" }}>Settings</h2>
          <p style={{ margin: 0, color: palette.silverMuted, fontSize: "0.73rem", lineHeight: 1.42 }}>Controls here change authoritative behavior. Runtime, capability, governance, and diagnostic truth remain in their owning rooms.</p>
        </div>
        <button ref={closeButtonRef} type="button" aria-label="Close settings" title="Close settings" onClick={onClose} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "2rem", height: "2rem", flexShrink: 0, padding: 0, borderRadius: "10px", border: `1px solid ${palette.lineSilver}`, background: "rgba(24, 33, 48, 0.58)", color: palette.silverMuted, cursor: "pointer" }}>×</button>
      </div>
      <div style={{ display: "grid", gap: "0.7rem", overflowY: "auto", padding: "0.78rem 0.78rem 1.4rem" }}>
        <ControlSection title="Chamber behavior" note="Local presentation and navigation controls; none grants body authority." rows={chamberRows} />
        <MemoryAndAuthorityControls />
        <ControlSection title="Emergency authority" note="A real end-to-end operator control. Read-only stop state and cleanup truth remain in Governance, Health, Status, and Admin." rows={emergencyRows} />
        {onOpenRoom && <div style={{ display: "grid", gap: "0.48rem", padding: "0.7rem", borderRadius: "14px", border: `1px dashed ${palette.lineBronze}`, color: palette.silverMuted, fontSize: "0.71rem", lineHeight: 1.4 }}>
          <span>Inspect non-mutating system truth in its owning Control &amp; System room.</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.42rem" }}>
            <RoomLinkButton room="governance" label="Open Governance" onOpenRoom={openRoom} />
            <RoomLinkButton room="memory" label="Open Memory" onOpenRoom={openRoom} />
            <RoomLinkButton room="health" label="Open Health" onOpenRoom={openRoom} />
            <RoomLinkButton room="capabilities" label="Open Capabilities" onOpenRoom={openRoom} />
          </div>
        </div>}
      </div>
    </div>
  );
}

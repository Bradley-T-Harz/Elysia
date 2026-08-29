import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  fetchApprovedMarketplaceAddons,
  fetchSavedAddonSlugs,
  getAddonsGateState,
  inspectLocalAddonPackage,
  loadLocalAddonAudit,
  loadLocalAddonInstallerStatus,
  loadLocalInstalledAddons,
  MARKETPLACE_AUTH_CHANGED_EVENT,
  planLocalAddonInstall,
  planLocalAddonLifecycleAction,
  planMarketplaceAddonAction,
  removeSavedAddonSlug,
  runLocalAddonValidationSandbox,
  saveAddonSlug,
  approveAndApplyLocalAddonTransition,
  type AddonAction,
  type AddonActionPlanResult,
  type AddonManifest,
  type AddonsGateState
} from "./api/addonsClient";
import { requireInternetMasterEnabled } from "./api/internetMaster";

type AddonsPageProps = {
  onOpenUserProfile: () => void;
};

type PreviewState = {
  addon: AddonManifest;
  action: AddonAction;
  previewKind: "install" | "enable" | "disable" | "uninstall" | "manifest";
  plan?: AddonActionPlanResult | null;
};

type SafeAddonFact = {
  label: string;
  value: string;
};

type SafeAddonAuditRow = {
  timestamp: string;
  action: string;
  addon: string;
  result: string;
  reason: string;
};

const MARKETPLACE_URL_FALLBACK = "https://elysiaecobotics.com/marketplace/browse";

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  panel: "rgba(18, 25, 37, 0.76)",
  panelSoft: "rgba(11, 14, 18, 0.42)",
  danger: "#D8A5A5"
} as const;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function displayScalar(value: unknown): string | null {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return null;
}

function firstRecord(
  records: Array<Record<string, unknown> | null>,
  key: string
): Record<string, unknown> | null {
  for (const record of records) {
    const nested = asRecord(record?.[key]);
    if (nested) {
      return nested;
    }
  }
  return null;
}

export function buildSafeAddonResultFacts(
  result: Record<string, unknown> | null
): SafeAddonFact[] {
  if (!result) {
    return [];
  }

  const top = asRecord(result);
  const installPlan = firstRecord([top], "install_plan");
  const installResult = firstRecord([top], "install_result");
  const transitionPlan = firstRecord([top], "transition_plan");
  const transitionResult = firstRecord([top], "transition_result");
  const sandboxResult = firstRecord([top], "sandbox_result");
  const operationResult = firstRecord([top], "operation_result");
  const inspection = firstRecord([top, installPlan, installResult, transitionPlan, transitionResult, sandboxResult], "inspection");
  const entry = firstRecord([top, installResult, transitionResult, operationResult], "entry");
  const manifest = firstRecord([inspection], "manifest");
  const records = [top, transitionPlan, transitionResult, installPlan, installResult, sandboxResult, operationResult, inspection, entry, manifest];

  const facts: SafeAddonFact[] = [];
  const addFirst = (label: string, keys: string[]) => {
    for (const record of records) {
      for (const key of keys) {
        const value = displayScalar(record?.[key]);
        if (value) {
          facts.push({ label, value });
          return;
        }
      }
    }
  };

  addFirst("Add-on", ["addon_id", "id", "name"]);
  addFirst("Version", ["version"]);
  addFirst("Registry state", ["status"]);
  addFirst("Action", ["action"]);
  addFirst("Current state", ["current_state"]);
  addFirst("Proposed state", ["proposed_state"]);
  addFirst("Plan state", ["plan_state"]);
  addFirst("Validation result", ["result", "valid", "installable"]);
  addFirst("Package staged", ["installed", "already_installed"]);
  addFirst("Execution enabled", ["execution_enabled", "executed_code"]);
  addFirst("Bridge enabled", ["bridge_enabled"]);
  addFirst("Files retained", ["files_retained"]);
  addFirst("Validation mode", ["sandbox_mode"]);
  addFirst("Network allowed", ["network_allowed"]);
  addFirst("Shell allowed", ["shell_allowed"]);
  addFirst("Private memory allowed", ["private_memory_allowed"]);
  addFirst("Separate enable approval", ["enable_requires_separate_approval"]);
  addFirst("Registry operation", ["ok", "blocked"]);
  addFirst("Package hash", ["package_hash"]);
  addFirst("Manifest hash", ["manifest_hash"]);

  return facts;
}

export function buildSafeAddonAuditRows(
  audit: Array<Record<string, unknown>>
): SafeAddonAuditRow[] {
  return audit.slice(-25).map((record) => ({
    timestamp: displayScalar(record.timestamp_utc) ?? "Time not surfaced",
    action: displayScalar(record.action) ?? "Unknown action",
    addon: displayScalar(record.addon_id) ?? "No add-on ID",
    result: displayScalar(record.result) ?? "Unknown result",
    reason: displayScalar(record.reason_code) ?? "No refusal code"
  }));
}

export function sanitizeAddonUiMessage(value: string): string {
  return value
    .replace(/(?:[A-Za-z]:\\)[^\s,;]+/g, "[local path hidden]")
    .replace(/(^|[\s("'=])\/(?!\/)[^\s,;)"']+/g, "$1[local path hidden]")
    .replace(/\b(bearer|token|secret|password|api[_ -]?key)\s*[:=]\s*[^\s,;]+/gi, "$1=[private value hidden]");
}

export default function AddonsPage({ onOpenUserProfile }: AddonsPageProps) {
  const [gate, setGate] = useState<AddonsGateState | null>(null);
  const [addons, setAddons] = useState<AddonManifest[]>([]);
  const [savedSlugs, setSavedSlugs] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [loading, setLoading] = useState(true);
  const [planningAction, setPlanningAction] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [marketplaceOpenHint, setMarketplaceOpenHint] = useState<string | null>(null);
  const [packagePath, setPackagePath] = useState("");
  const [localStatus, setLocalStatus] = useState<Record<string, unknown> | null>(null);
  const [localInstalled, setLocalInstalled] = useState<Array<Record<string, unknown>>>([]);
  const [localAudit, setLocalAudit] = useState<Array<Record<string, unknown>>>([]);
  const [localResult, setLocalResult] = useState<Record<string, unknown> | null>(null);
  const [pendingLocalPlan, setPendingLocalPlan] = useState<Record<string, unknown> | null>(null);
  const [officialCandidates, setOfficialCandidates] = useState<Array<Record<string, unknown>>>([]);

  async function loadAddons() {
    setLoading(true);
    setMessage(null);
    try {
      const nextGate = await getAddonsGateState();
      setGate(nextGate);
      if (!nextGate.unlocked || !nextGate.session) {
        setAddons([]);
        setSavedSlugs(new Set());
        return;
      }
      const [catalog, saved] = await Promise.all([
        fetchApprovedMarketplaceAddons(nextGate.session),
        fetchSavedAddonSlugs(nextGate.session)
      ]);
      setAddons(catalog);
      setSavedSlugs(new Set(saved));
      setSelectedId(catalog[0]?.id ?? null);
      setMessage(nextGate.reason);
    } catch (error) {
      setMessage(sanitizeAddonUiMessage(error instanceof Error ? error.message : "Add-ons room failed to load Marketplace data."));
    } finally {
      setLoading(false);
    }
  }

  async function loadLocalInstallerTruth() {
    try {
      const [statusData, installedData, auditData] = await Promise.all([
        loadLocalAddonInstallerStatus(),
        loadLocalInstalledAddons(),
        loadLocalAddonAudit()
      ]);
      setLocalStatus((statusData.addons_status as Record<string, unknown>) ?? null);
      setLocalInstalled((installedData.installed_addons as Array<Record<string, unknown>>) ?? []);
      setLocalAudit((auditData.audit_records as Array<Record<string, unknown>>) ?? []);
      setOfficialCandidates((statusData.official_candidates as Array<Record<string, unknown>>) ?? []);
    } catch (error) {
      setMessage(sanitizeAddonUiMessage(error instanceof Error ? error.message : "Local add-on installer status failed to load."));
    }
  }

  useEffect(() => {
    void loadAddons();
    void loadLocalInstallerTruth();
    function handleMarketplaceAuthChanged() {
      void loadAddons();
    }
    window.addEventListener(MARKETPLACE_AUTH_CHANGED_EVENT, handleMarketplaceAuthChanged);
    window.addEventListener("focus", handleMarketplaceAuthChanged);
    return () => {
      window.removeEventListener(MARKETPLACE_AUTH_CHANGED_EVENT, handleMarketplaceAuthChanged);
      window.removeEventListener("focus", handleMarketplaceAuthChanged);
    };
  }, []);

  const selectedAddon = useMemo(
    () => addons.find((addon) => addon.id === selectedId) ?? addons[0] ?? null,
    [addons, selectedId]
  );
  const marketplaceUrl = normalizeMarketplaceUrl(gate?.marketplaceUrl);

  async function toggleSaved(addon: AddonManifest) {
    if (!gate?.session) return;
    try {
      if (savedSlugs.has(addon.id)) {
        await removeSavedAddonSlug(gate.session, addon.id);
        setSavedSlugs((current) => {
          const next = new Set(current);
          next.delete(addon.id);
          return next;
        });
        setMessage(`${addon.name} removed from Marketplace saved add-ons.`);
      } else {
        await saveAddonSlug(gate.session, addon.id);
        setSavedSlugs((current) => new Set(current).add(addon.id));
        setMessage(`${addon.name} saved to Marketplace My Add-ons.`);
      }
    } catch (error) {
      setMessage(sanitizeAddonUiMessage(error instanceof Error ? error.message : "Saved add-on update failed."));
    }
  }

  async function openMarketplaceWebsite(event?: React.MouseEvent<HTMLAnchorElement | HTMLButtonElement>) {
    event?.preventDefault();
    try {
      await requireInternetMasterEnabled();
      await openUrl(marketplaceUrl);
      setMarketplaceOpenHint("Opened Elysia Marketplace in your default browser.");
    } catch (error) {
      setMarketplaceOpenHint(
        `External opener failed: ${sanitizeAddonUiMessage(formatExternalOpenError(error))}`
      );
    }
  }

  async function openActionPreview(
    addon: AddonManifest,
    previewKind: PreviewState["previewKind"],
    action: AddonAction
  ) {
    if (previewKind === "manifest") {
      setPreview({ addon, action, previewKind, plan: null });
      return;
    }
    setPlanningAction(true);
    setMessage(null);
    try {
      const plan = await planMarketplaceAddonAction(addon, action);
      setPreview({ addon, action, previewKind, plan });
      setMessage(`Prepared preview-only ${previewKind} plan for ${addon.name}. No local execution occurred.`);
    } catch (error) {
      setPreview({ addon, action, previewKind, plan: null });
      setMessage(sanitizeAddonUiMessage(error instanceof Error ? error.message : "Add-on action planning failed."));
    } finally {
      setPlanningAction(false);
    }
  }

  async function runLocalPackageAction(action: "inspect" | "plan" | "sandbox") {
    if (!packagePath.trim()) {
      setMessage("Enter a local .elysia-addon package path first.");
      return;
    }
    setMessage(null);
    try {
      const path = packagePath.trim();
      const data =
        action === "inspect" ? await inspectLocalAddonPackage(path)
        : action === "plan" ? await planLocalAddonInstall(path)
        : await runLocalAddonValidationSandbox(path);
      setLocalResult(data);
      setPendingLocalPlan(action === "plan" ? asRecord(data.transition_plan) : null);
      await loadLocalInstallerTruth();
      setMessage(action === "plan"
        ? "Exact disabled-staging plan prepared. Nothing changed; review and approve the bound transition below."
        : `Local add-on ${action} completed without execution or installation.`);
    } catch (error) {
      setMessage(sanitizeAddonUiMessage(error instanceof Error ? error.message : `Local add-on ${action} failed.`));
    }
  }

  async function runInstalledAction(entry: Record<string, unknown>, action: "enable" | "disable" | "revoke" | "remove") {
    const addonId = String(entry.addon_id ?? "");
    const version = String(entry.version ?? "");
    if (!addonId || !version) return;
    try {
      const data = await planLocalAddonLifecycleAction(entry, action);
      setLocalResult(data);
      setPendingLocalPlan(asRecord(data.transition_plan));
      setMessage(`Exact ${action} plan prepared for ${addonId}@${version}. Registry state has not changed.`);
    } catch (error) {
      setMessage(sanitizeAddonUiMessage(error instanceof Error ? error.message : `Local add-on ${action} failed.`));
    }
  }

  async function applyPendingLocalTransition() {
    if (!pendingLocalPlan) return;
    try {
      const data = await approveAndApplyLocalAddonTransition(pendingLocalPlan);
      setLocalResult(data);
      setPendingLocalPlan(null);
      await loadLocalInstallerTruth();
      setMessage("Exact approved add-on transition applied. Execution and bridge authority remain disabled.");
    } catch (error) {
      setMessage(sanitizeAddonUiMessage(error instanceof Error ? error.message : "Exact add-on transition failed."));
    }
  }

  if (loading) {
    return <Shell title="Add-ons"><div style={cardStyle}>Checking Marketplace link gate...</div></Shell>;
  }

  if (!gate?.unlocked) {
    const signedInEmail = gate?.session?.user.email ?? null;
    const linkedIdentity = gate?.link?.marketplace_email ?? gate?.link?.marketplace_username ?? null;
    const signedInButNotLinked = Boolean(gate?.session && !gate.link?.linked);
    const accountMismatch = Boolean(
      gate?.session?.user.id && gate.link?.linked && gate.link.marketplace_user_id !== gate.session.user.id
    );
    return (
      <Shell title="Add-ons">
        <section style={lockedStyle}>
          <div style={eyebrowStyle}>Marketplace gate required</div>
          <h2 style={{ margin: "0.25rem 0" }}>Marketplace catalog is locked.</h2>
          <p style={bodyStyle}>
            {gate?.reason ?? "Sign in and link your Marketplace account in Personal Identity to use Add-ons."}
            {" "}Local package governance remains available below without a Marketplace account.
          </p>
          <dl style={gateFactsStyle}>
            <Fact label="Marketplace session" value={signedInEmail ? `Signed in as ${signedInEmail}` : "Not signed in"} />
            <Fact label="Local Marketplace link" value={gate?.link?.linked ? `Linked to ${linkedIdentity ?? "Marketplace profile"}` : "Not linked"} />
            <Fact label="Account match" value={accountMismatch ? "Mismatch" : gate?.unlocked ? "Matched" : "Not ready"} />
          </dl>
          {signedInButNotLinked && (
            <div style={statusStyle}>
              Use <strong>Link Marketplace Account</strong> in Personal Identity to unlock Add-ons for this local Elysia chamber.
            </div>
          )}
          {accountMismatch && (
            <div style={warningStyle}>
              No catalog fetch was performed because the signed-in Marketplace account does not match the locally linked account.
            </div>
          )}
          <div style={actionRowStyle}>
            <button type="button" onClick={onOpenUserProfile} style={primaryButtonStyle}>
              Go to Personal Identity
            </button>
            <button type="button" onClick={(event) => void openMarketplaceWebsite(event)} style={secondaryButtonStyle}>
              Open Elysia Marketplace
            </button>
            <button type="button" onClick={() => void loadAddons()} style={secondaryButtonStyle}>
              Recheck Link
            </button>
          </div>
          {marketplaceOpenHint && (
            <div style={statusStyle}>
              {marketplaceOpenHint}{" "}
              <a
                href={marketplaceUrl}
                target="_blank"
                rel="noreferrer noopener"
                onClick={(event) => void openMarketplaceWebsite(event)}
                style={inlineLinkStyle}
              >
                {marketplaceUrl}
              </a>
            </div>
          )}
          <p style={marketplaceUrlStyle}>
            Marketplace URL:{" "}
            <a
              href={marketplaceUrl}
              target="_blank"
              rel="noreferrer noopener"
              onClick={(event) => void openMarketplaceWebsite(event)}
              style={inlineLinkStyle}
            >
              {marketplaceUrl}
            </a>
          </p>
          <div style={privacyNoteStyle}>
            Locked state performs no catalog fetch requiring a Marketplace account, no saved-addons fetch,
            and no local execution.
          </div>
          <LocalInstallerPanel
            packagePath={packagePath}
            setPackagePath={setPackagePath}
            status={localStatus}
            installed={localInstalled}
            audit={localAudit}
            result={localResult}
            pendingPlan={pendingLocalPlan}
            officialCandidates={officialCandidates}
            onRefresh={() => void loadLocalInstallerTruth()}
            onPackageAction={(action) => void runLocalPackageAction(action)}
            onInstalledAction={(entry, action) => void runInstalledAction(entry, action)}
            onApplyPending={() => void applyPendingLocalTransition()}
          />
        </section>
      </Shell>
    );
  }

  return (
    <Shell title="Add-ons">
      <div style={toplineStyle}>
        <div>
          <div style={eyebrowStyle}>Marketplace catalog</div>
          <p style={bodyStyle}>
            Signed-in Marketplace account matches the local link. Catalog and saved add-ons are read from Supabase.
            Local package validation, disabled staging, registry-state changes, and sanitized audit truth are available below.
            Registry state never means add-on code is executing; execution remains disabled. Admin review records a process,
            not a guarantee of safety.
          </p>
        </div>
        <button type="button" onClick={() => void loadAddons()} style={secondaryButtonStyle}>Refresh</button>
      </div>
      {message && <div style={statusStyle}>{message}</div>}
      {planningAction && <div style={statusStyle}>Preparing preview-only action plan...</div>}
      <LocalInstallerPanel
        packagePath={packagePath}
        setPackagePath={setPackagePath}
        status={localStatus}
        installed={localInstalled}
        audit={localAudit}
        result={localResult}
        pendingPlan={pendingLocalPlan}
        officialCandidates={officialCandidates}
        onRefresh={() => void loadLocalInstallerTruth()}
        onPackageAction={(action) => void runLocalPackageAction(action)}
        onInstalledAction={(entry, action) => void runInstalledAction(entry, action)}
        onApplyPending={() => void applyPendingLocalTransition()}
      />
      <div style={layoutStyle}>
        <section style={catalogStyle}>
          {addons.length === 0 ? (
            <div style={cardStyle}>No approved Marketplace add-ons were returned for this account.</div>
          ) : addons.map((addon) => (
            <AddonCard
              key={addon.id}
              addon={addon}
              selected={selectedAddon?.id === addon.id}
              saved={savedSlugs.has(addon.id)}
              onSelect={() => setSelectedId(addon.id)}
              onToggleSaved={() => void toggleSaved(addon)}
              onPreview={(previewKind, action) => void openActionPreview(addon, previewKind, action)}
            />
          ))}
        </section>
        <aside style={detailStyle}>
          {selectedAddon ? <AddonDetail addon={selectedAddon} saved={savedSlugs.has(selectedAddon.id)} /> : null}
          {preview && <ActionPreview preview={preview} />}
        </aside>
      </div>
    </Shell>
  );
}

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ height: "100%", overflowY: "auto", padding: "0.2rem" }}>
      <div style={pageFrameStyle}>
        <header>
          <div style={eyebrowStyle}>Operator room</div>
          <h1 style={{ margin: 0, fontSize: "2rem" }}>{title}</h1>
          <p style={bodyStyle}>
            Marketplace manifests are visible here after link verification. Local Elysia remains the installer authority.
          </p>
        </header>
        {children}
      </div>
    </div>
  );
}

function AddonCard({
  addon,
  selected,
  saved,
  onSelect,
  onToggleSaved,
  onPreview
}: {
  addon: AddonManifest;
  selected: boolean;
  saved: boolean;
  onSelect: () => void;
  onToggleSaved: () => void;
  onPreview: (kind: PreviewState["previewKind"], action: AddonAction) => void;
}) {
  const primaryAction = addon.actions[0] ?? manualAction("review_manifest", "Review manifest");
  const previewActions = getPreviewActions(addon);
  return (
    <article style={{ ...cardStyle, borderColor: selected ? "rgba(126, 215, 209, 0.44)" : palette.lineSilver }}>
      <button type="button" onClick={onSelect} style={selectButtonStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "start" }}>
          <div>
            <h3 style={{ margin: 0 }}>{addon.name}</h3>
            <p style={bodyStyle}>{addon.summary}</p>
          </div>
          <span style={badgeStyle}>{addon.trust_tier}</span>
        </div>
      </button>
      <dl style={miniFactsStyle}>
        <Fact label="Publisher" value={addon.publisher} />
        <Fact label="Category" value={addon.category} />
        <Fact label="Version" value={addon.version} />
        <Fact label="Boundary" value={addon.network_access ? "Network declared" : "Local-only declared"} />
      </dl>
      <div style={actionRowStyle}>
        <button type="button" onClick={onToggleSaved} style={primaryButtonStyle}>
          {saved ? "Remove from My Add-ons" : "Save to My Add-ons"}
        </button>
        <button type="button" onClick={() => onPreview("manifest", primaryAction)} style={secondaryButtonStyle}>View Manifest</button>
        {previewActions.map(({ kind, action, label }) => (
          <button key={`${kind}-${action.action_key}`} type="button" onClick={() => onPreview(kind, action)} style={secondaryButtonStyle}>
            {label}
          </button>
        ))}
      </div>
      {previewActions.length === 0 && (
        <p style={bodyStyle}>
          {addon.actions.length
            ? "This add-on currently provides manual instructions only."
            : "Install action not declared by developer."}
        </p>
      )}
    </article>
  );
}

function AddonDetail({ addon, saved }: { addon: AddonManifest; saved: boolean }) {
  return (
    <section style={cardStyle}>
      <div style={eyebrowStyle}>Selected add-on</div>
      <h2 style={{ margin: "0.2rem 0" }}>{addon.name}</h2>
      <p style={bodyStyle}>{addon.description}</p>
      <dl style={miniFactsStyle}>
        <Fact label="Saved" value={saved ? "Saved in Marketplace" : "Not saved"} />
        <Fact label="Manifest" value={addon.status ?? "approved"} />
        <Fact label="Local files" value={addon.security.local_file_access} />
        <Fact label="Model/chat access" value={addon.security.model_accessible || addon.security.chat_accessible ? "Declared" : "Blocked"} />
      </dl>
      <h3>Dependencies</h3>
      {addon.dependencies.length ? (
        <ul style={listStyle}>
          {addon.dependencies.map((dependency) => (
            <li key={`${dependency.ecosystem}-${dependency.package_name}`}>
              <strong>{dependency.ecosystem}</strong>: {dependency.package_name}
              {dependency.version_constraint ? ` ${dependency.version_constraint}` : ""} ({dependency.required ? "required" : "optional"})
            </li>
          ))}
        </ul>
      ) : <p style={bodyStyle}>No dependencies declared.</p>}
      <h3>Available action declarations</h3>
      <ul style={listStyle}>
        {addon.actions.map((action) => (
          <li key={action.action_key}>
            {action.action_label} - {action.action_kind} - {action.risk_level}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ActionPreview({ preview }: { preview: PreviewState }) {
  return (
    <section style={previewStyle}>
      <div style={eyebrowStyle}>Preview only</div>
      <h2 style={{ margin: "0.2rem 0" }}>{preview.previewKind === "manifest" ? "Manifest Preview" : `${preview.previewKind} preview`}</h2>
      <p style={bodyStyle}>
        Exact add-on: <strong>{preview.addon.name}</strong>. Declared action: <strong>{preview.action.action_label}</strong>.
      </p>
      <dl style={miniFactsStyle}>
        <Fact label="Action kind" value={preview.action.action_kind} />
        <Fact label="Risk" value={preview.action.risk_level} />
        <Fact label="Network" value={preview.addon.network_access || preview.action.network_access ? "Network declared" : "Local-only declared"} />
        <Fact label="Future local password" value={preview.action.requires_local_operator_password ? "Required" : "Review required"} />
        {preview.plan && (
          <>
            <Fact label="Plan state" value={preview.plan.plan_state} />
            <Fact label="Execution" value={preview.plan.execution_enabled ? "Enabled" : "Not implemented"} />
            <Fact label="Mutation" value={preview.plan.mutation_allowed ? "Allowed" : "Blocked"} />
            <Fact label="Command/package manager" value={preview.plan.command_execution_allowed || preview.plan.package_manager_allowed ? "Declared" : "Blocked"} />
          </>
        )}
      </dl>
      {preview.plan && (
        <div style={statusStyle}>
          <strong>{preview.plan.plan_summary}</strong>
          <br />
          Approval: {preview.plan.requires_future_approval ? "future local operator approval required" : "not available"}.
          Rollback note: {preview.plan.rollback_note}
        </div>
      )}
      <p style={privacyNoteStyle}>
        Local execution is not implemented yet. Future execution will require local Elysia password/operator approval.
        This preview runs no commands, installs no packages, mutates no files, and starts no workers.
      </p>
      <dl style={miniFactsStyle}>
        <Fact label="Publisher" value={preview.addon.publisher} />
        <Fact label="Version" value={preview.addon.version} />
        <Fact label="Trust tier" value={preview.addon.trust_tier} />
        <Fact label="Declared permissions" value={String(preview.addon.actions.length)} />
        <Fact label="External boundary" value={preview.addon.network_access ? "Network use declared; review required" : "Local-only declared"} />
        <Fact label="Review status" value={preview.addon.status ?? "Listing metadata only"} />
      </dl>
      <p style={privacyNoteStyle}>Only allowlisted manifest facts are rendered. Raw manifests and payloads stay out of the chamber.</p>
    </section>
  );
}

export function LocalInstallerPanel({
  packagePath,
  setPackagePath,
  status,
  installed,
  audit,
  result,
  pendingPlan,
  officialCandidates,
  onRefresh,
  onPackageAction,
  onInstalledAction,
  onApplyPending
}: {
  packagePath: string;
  setPackagePath: (value: string) => void;
  status: Record<string, unknown> | null;
  installed: Array<Record<string, unknown>>;
  audit: Array<Record<string, unknown>>;
  result: Record<string, unknown> | null;
  pendingPlan?: Record<string, unknown> | null;
  officialCandidates?: Array<Record<string, unknown>>;
  onRefresh: () => void;
  onPackageAction: (action: "inspect" | "plan" | "sandbox") => void;
  onInstalledAction: (entry: Record<string, unknown>, action: "enable" | "disable" | "revoke" | "remove") => void;
  onApplyPending?: () => void;
}) {
  return (
    <section style={cardStyle}>
      <div style={eyebrowStyle}>Local package staging</div>
      <h2 style={{ margin: "0.2rem 0" }}>Add-ons Manager</h2>
      <p style={bodyStyle}>
        Local Elysia can statically validate packages, prepare exact state-transition plans, and stage an approved package disabled.
        The website may prepare intent only. No state grants code execution, shell, network, workers, or private-memory access in Pass 7.
      </p>
      <dl style={miniFactsStyle}>
        <Fact label="Installed" value={String(status?.installed_count ?? installed.length)} />
        <Fact label="Limited enabled state" value={String(status?.enabled_count ?? 0)} />
        <Fact label="Execution" value="Disabled" />
        <Fact label="Validation mode" value={String(status?.sandbox_mode ?? "validation_only")} />
        <Fact label="Deep link" value={String(status?.deep_link_status ?? "parser/status pending")} />
      </dl>
      <div style={packageInputRowStyle}>
        <input
          value={packagePath}
          onChange={(event) => setPackagePath(event.target.value)}
          placeholder="/path/to/addon.elysia-addon"
          style={inputStyle}
          aria-label="Local .elysia-addon package path"
        />
        <button type="button" onClick={onRefresh} style={secondaryButtonStyle}>Refresh</button>
      </div>
      <div style={actionRowStyle}>
        <button type="button" onClick={() => onPackageAction("inspect")} style={secondaryButtonStyle}>Inspect</button>
        <button type="button" onClick={() => onPackageAction("plan")} style={primaryButtonStyle}>Plan disabled staging</button>
        <button type="button" onClick={() => onPackageAction("sandbox")} style={secondaryButtonStyle}>Validate package only</button>
      </div>
      <p style={privacyNoteStyle}>
        Installed does not mean enabled. Enabled does not mean unrestricted. A limited-enabled registry state does not execute code
        while the governed bridge and local sandbox proof remain unavailable. Validation mode is static inspection, not an execution sandbox.
      </p>
      {pendingPlan && (
        <section style={previewStyle} aria-label="Pending exact add-on transition">
          <div style={eyebrowStyle}>Requires approval</div>
          <h3 style={{ margin: "0.2rem 0" }}>Exact non-executing change</h3>
          <dl style={miniFactsStyle}>
            <Fact label="Action" value={displayScalar(pendingPlan.action)} />
            <Fact label="Add-on" value={displayScalar(pendingPlan.addon_id)} />
            <Fact label="Current state" value={displayScalar(pendingPlan.current_state)} />
            <Fact label="Proposed state" value={displayScalar(pendingPlan.proposed_state)} />
            <Fact label="Package hash" value={displayScalar(pendingPlan.package_hash)} />
            <Fact label="Approved permissions" value={String(Array.isArray(pendingPlan.approved_permissions) ? pendingPlan.approved_permissions.length : 0)} />
            <Fact label="Effective permissions" value={String(Array.isArray(pendingPlan.effective_permissions) ? pendingPlan.effective_permissions.length : 0)} />
            <Fact label="Execution" value={pendingPlan.execution_enabled === true ? "Enabled" : "Disabled"} />
            <Fact label="Bridge" value={pendingPlan.bridge_enabled === true ? "Enabled" : "Disabled"} />
            <Fact label="Files after removal" value={pendingPlan.files_retained === false ? "Deleted" : "Retained"} />
          </dl>
          <p style={privacyNoteStyle}>
            Approval is one-time and bound to this exact plan, state, package hash, and registry revision. Approval values are never rendered.
          </p>
          <button
            type="button"
            onClick={onApplyPending}
            disabled={!onApplyPending || pendingPlan.plan_state !== "ready_for_exact_approval"}
            style={primaryButtonStyle}
          >
            Approve and apply exact non-executing change
          </button>
        </section>
      )}
      <h3>Installed / staged locally</h3>
      {installed.length ? (
        <div style={catalogStyle}>
          {installed.map((entry) => (
            <article key={`${entry.addon_id}-${entry.version}`} style={cardStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", alignItems: "start" }}>
                <div>
                  <h3 style={{ margin: 0 }}>{String(entry.name ?? entry.addon_id)}</h3>
                  <p style={bodyStyle}><code>{String(entry.addon_id)}</code> version {String(entry.version)}</p>
                </div>
                <span style={badgeStyle}>{String(entry.status)}</span>
              </div>
              <dl style={miniFactsStyle}>
                <Fact label="Source" value={String(entry.source ?? "local")} />
                <Fact label="Package hash" value={String(entry.package_hash ?? "missing")} />
                <Fact label="Manifest hash" value={String(entry.manifest_hash ?? "missing")} />
                <Fact label="Requested permissions" value={String(Array.isArray(entry.permissions_requested) ? entry.permissions_requested.length : 0)} />
                <Fact label="Approved permissions" value={String(Array.isArray(entry.permissions_approved) ? entry.permissions_approved.length : 0)} />
                <Fact label="Effective permissions" value={String(Array.isArray(entry.permissions_effective) ? entry.permissions_effective.length : 0)} />
                <Fact label="Bridge authority" value={entry.bridge_authority_active === true ? "Active" : "Off"} />
                <Fact label="Revocation" value={String(entry.revocation_status ?? "not_checked")} />
                <Fact label="Files retained" value={entry.files_retained === false ? "No" : "Yes"} />
              </dl>
              <div style={actionRowStyle}>
                {["installed_disabled", "disabled"].includes(String(entry.status)) && (
                  <button type="button" onClick={() => onInstalledAction(entry, "enable")} style={secondaryButtonStyle}>Plan limited enable · no execution</button>
                )}
                {["installed_disabled", "enabled_limited"].includes(String(entry.status)) && (
                  <button type="button" onClick={() => onInstalledAction(entry, "disable")} style={secondaryButtonStyle}>Plan disable</button>
                )}
                {!["revoked", "removed"].includes(String(entry.status)) && (
                  <button type="button" onClick={() => onInstalledAction(entry, "revoke")} style={secondaryButtonStyle}>Plan trust revocation</button>
                )}
                {["installed_disabled", "disabled", "revoked"].includes(String(entry.status)) && (
                  <button type="button" onClick={() => onInstalledAction(entry, "remove")} style={secondaryButtonStyle}>Plan registry removal · retain files</button>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p style={bodyStyle}>No locally installed add-ons are registered yet.</p>
      )}
      <details style={previewStyle}>
        <summary>Official add-ons</summary>
        {(officialCandidates ?? []).length ? (
          <div style={catalogStyle}>
            {(officialCandidates ?? []).map((candidate) => (
              <dl key={String(candidate.addon_id)} style={miniFactsStyle}>
                <Fact label="Add-on" value={displayScalar(candidate.name) ?? displayScalar(candidate.addon_id)} />
                <Fact label="Status" value={displayScalar(candidate.listing_state)} />
                <Fact label="Required profile" value={displayScalar(candidate.required_profile)} />
                <Fact label="Version" value={displayScalar(candidate.version)} />
                <Fact label="Local installation" value={candidate.install_action_live === true ? "Reviewed VSIX CLI contract live" : "Unavailable"} />
                <Fact label="Public distribution" value={candidate.public_distribution_supported === true ? "Supported · verify canonical Marketplace" : "Unavailable"} />
                <Fact label="In-app install control" value={candidate.in_app_install_control_live === true ? "Available" : "Not provided"} />
              </dl>
            ))}
          </div>
        ) : <p style={bodyStyle}>No official add-ons are declared.</p>}
        <p style={privacyNoteStyle}>
          Codev is the official stable v1.0.0 Developer-profile add-on. A reviewed local VSIX can be installed through the explicit user-local CLI contract; this chamber has no install control. Public availability is authoritative at the canonical Elysia Ecobotics Marketplace.
        </p>
      </details>
      <details style={previewStyle}>
        <summary>Marketplace submission boundary</summary>
        <p style={bodyStyle}>
          Local Developer Forge preparation does not upload. Choosing a repository, folder, source bundle, Git URL, or .elysia-addon
          for website submission transfers submitted material off this computer to Elysia Ecobotics / EcoSyneva Commons review infrastructure.
        </p>
        <p style={privacyNoteStyle}>
          Submitted does not mean approved or public. Admin review reduces risk but does not guarantee safety. No upload action is available in this chamber.
        </p>
      </details>
      {result && (
        <details style={previewStyle} open>
          <summary>Latest sanitized local result</summary>
          <dl style={miniFactsStyle}>
            {buildSafeAddonResultFacts(result).map((fact) => (
              <Fact key={`${fact.label}-${fact.value}`} label={fact.label} value={fact.value} />
            ))}
          </dl>
          <p style={privacyNoteStyle}>Raw result payloads and local paths are not rendered in the chamber.</p>
        </details>
      )}
      <details style={previewStyle}>
        <summary>Sanitized local audit summary</summary>
        {audit.length ? (
          <div style={catalogStyle}>
            {buildSafeAddonAuditRows(audit).map((row, index) => (
              <dl key={`${row.timestamp}-${row.action}-${index}`} style={miniFactsStyle}>
                <Fact label="Time" value={row.timestamp} />
                <Fact label="Action" value={row.action} />
                <Fact label="Add-on" value={row.addon} />
                <Fact label="Result" value={row.result} />
                <Fact label="Reason" value={row.reason} />
              </dl>
            ))}
          </div>
        ) : <p style={bodyStyle}>No add-on audit records yet.</p>}
        <p style={privacyNoteStyle}>Raw audit details, package paths, install paths, and private values are not rendered.</p>
      </details>
    </section>
  );
}

function Fact({ label, value }: { label: string; value?: string | null }) {
  return (
    <div style={{ minWidth: 0 }}>
      <dt style={eyebrowStyle}>{label}</dt>
      <dd style={{ margin: "0.24rem 0 0", overflowWrap: "anywhere" }}>{value || "Not declared"}</dd>
    </div>
  );
}

function manualAction(action_key: string, action_label: string): AddonAction {
  return {
    action_key,
    action_label,
    action_kind: "manual_instruction",
    allowed: true,
    risk_level: "unknown",
    requires_local_operator_password: true,
    notes: ["Manual review only."]
  };
}

function getPreviewActions(addon: AddonManifest): Array<{
  kind: Exclude<PreviewState["previewKind"], "manifest">;
  action: AddonAction;
  label: string;
}> {
  const matches: Array<{
    kind: Exclude<PreviewState["previewKind"], "manifest">;
    action: AddonAction;
    label: string;
  }> = [];
  const seenKinds = new Set<string>();
  for (const action of addon.actions) {
    const kind = previewKindForAction(action);
    if (!kind || seenKinds.has(kind)) continue;
    seenKinds.add(kind);
    matches.push({
      kind,
      action,
      label: `${titleCase(kind)} Preview`
    });
  }
  return matches;
}

function previewKindForAction(action: AddonAction): Exclude<PreviewState["previewKind"], "manifest"> | null {
  switch (action.action_kind) {
    case "python_package_install":
    case "docker_compose_setup":
      return "install";
    case "python_package_uninstall":
      return "uninstall";
    case "docker_compose_start":
    case "config_toggle":
      return "enable";
    case "docker_compose_stop":
      return "disable";
    default:
      return null;
  }
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function normalizeMarketplaceUrl(url?: string): string {
  try {
    const parsed = new URL(url ?? MARKETPLACE_URL_FALLBACK);
    const fallback = new URL(MARKETPLACE_URL_FALLBACK);
    if (parsed.protocol === "https:" && parsed.origin === fallback.origin) {
      return parsed.toString().replace(/\/$/, "");
    }
  } catch {
    return MARKETPLACE_URL_FALLBACK;
  }
  return MARKETPLACE_URL_FALLBACK;
}

function formatExternalOpenError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  try {
    return JSON.stringify(error);
  } catch {
    return "Unknown opener error";
  }
}

const pageFrameStyle: CSSProperties = {
  display: "grid",
  gap: "1rem",
  minHeight: "100%",
  padding: "1rem",
  borderRadius: "20px",
  border: `1px solid ${palette.lineSilver}`,
  background: "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.96) 100%)"
};

const toplineStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: "1rem",
  alignItems: "center"
};

const layoutStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1.15fr) minmax(300px, 0.85fr)",
  gap: "1rem",
  alignItems: "start"
};

const catalogStyle: CSSProperties = {
  display: "grid",
  gap: "0.85rem",
  minWidth: 0
};

const detailStyle: CSSProperties = {
  display: "grid",
  gap: "0.85rem",
  minWidth: 0
};

const cardStyle: CSSProperties = {
  border: `1px solid ${palette.lineSilver}`,
  borderRadius: "16px",
  background: palette.panelSoft,
  padding: "1rem",
  minWidth: 0
};

const lockedStyle: CSSProperties = {
  ...cardStyle,
  display: "grid",
  gap: "0.85rem"
};

const selectButtonStyle: CSSProperties = {
  border: 0,
  padding: 0,
  margin: 0,
  textAlign: "left",
  background: "transparent",
  color: palette.silver,
  cursor: "pointer"
};

const eyebrowStyle: CSSProperties = {
  fontSize: "0.7rem",
  letterSpacing: "0.11em",
  textTransform: "uppercase",
  color: palette.sandstone
};

const bodyStyle: CSSProperties = {
  color: palette.silverMuted,
  lineHeight: 1.55,
  margin: "0.35rem 0"
};

const badgeStyle: CSSProperties = {
  display: "inline-flex",
  border: "1px solid rgba(126, 215, 209, 0.28)",
  borderRadius: "999px",
  padding: "0.24rem 0.55rem",
  color: palette.teal,
  fontWeight: 800,
  fontSize: "0.78rem"
};

const miniFactsStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(145px, 1fr))",
  gap: "0.65rem",
  margin: "0.7rem 0"
};

const gateFactsStyle: CSSProperties = {
  ...miniFactsStyle,
  gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
  margin: 0
};

const actionRowStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.55rem",
  alignItems: "center"
};

const packageInputRowStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  gap: "0.55rem",
  alignItems: "center"
};

const inputStyle: CSSProperties = {
  width: "100%",
  minWidth: 0,
  boxSizing: "border-box",
  border: `1px solid ${palette.lineSilver}`,
  borderRadius: "12px",
  padding: "0.7rem 0.78rem",
  background: "rgba(11, 14, 18, 0.66)",
  color: palette.silver
};

const primaryButtonStyle: CSSProperties = {
  border: "1px solid rgba(126, 215, 209, 0.34)",
  borderRadius: "12px",
  padding: "0.62rem 0.78rem",
  background: "linear-gradient(180deg, rgba(16, 71, 75, 0.74) 0%, rgba(18, 25, 37, 0.88) 100%)",
  color: palette.silver,
  cursor: "pointer",
  fontWeight: 800
};

const secondaryButtonStyle: CSSProperties = {
  border: `1px solid ${palette.lineSilver}`,
  borderRadius: "12px",
  padding: "0.62rem 0.78rem",
  background: palette.panel,
  color: palette.silver,
  cursor: "pointer",
  textDecoration: "none"
};

const statusStyle: CSSProperties = {
  border: "1px solid rgba(126, 215, 209, 0.28)",
  borderRadius: "13px",
  padding: "0.75rem",
  color: palette.teal,
  background: "rgba(126, 215, 209, 0.08)",
  overflowWrap: "anywhere"
};

const warningStyle: CSSProperties = {
  border: "1px solid rgba(216, 165, 165, 0.34)",
  borderRadius: "13px",
  padding: "0.75rem",
  color: palette.danger,
  background: "rgba(216, 165, 165, 0.08)",
  overflowWrap: "anywhere"
};

const inlineLinkStyle: CSSProperties = {
  color: palette.teal,
  overflowWrap: "anywhere"
};

const marketplaceUrlStyle: CSSProperties = {
  ...bodyStyle,
  margin: 0,
  overflowWrap: "anywhere"
};

const privacyNoteStyle: CSSProperties = {
  border: "1px dashed rgba(184, 162, 123, 0.34)",
  borderRadius: "13px",
  padding: "0.75rem",
  color: palette.silverMuted,
  background: "rgba(11, 14, 18, 0.32)",
  lineHeight: 1.55
};

const previewStyle: CSSProperties = {
  ...cardStyle,
  borderColor: "rgba(184, 162, 123, 0.4)"
};

const listStyle: CSSProperties = {
  color: palette.silverMuted,
  lineHeight: 1.55,
  paddingLeft: "1.1rem"
};

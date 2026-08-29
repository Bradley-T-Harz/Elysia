import type { CSSProperties } from "react";
import type { CodePatchPlanSummaryData } from "./api/bridgeClient";

export type CommandGateCardProps = {
  mode?: string | null;
  codePatchPlan?: CodePatchPlanSummaryData | null;
  compact?: boolean;
};

function safeString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function safeBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isCoderMode(mode?: string | null): boolean {
  const normalized = safeString(mode)?.toLowerCase();
  return normalized === "coder" || normalized === "coding";
}

function Row({
  label,
  value,
  detail
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div style={styles.row}>
      <span style={styles.rowLabel}>{label}</span>
      <span style={styles.rowValue}>
        {value}
        {detail && <span style={styles.detail}> {detail}</span>}
      </span>
    </div>
  );
}

export default function CommandGateCard({
  mode,
  codePatchPlan,
  compact = false
}: CommandGateCardProps) {
  const active = isCoderMode(mode) || Boolean(codePatchPlan);
  const shellUsed = safeBoolean(codePatchPlan?.shell_execution_used);
  const networkUsed = safeBoolean(codePatchPlan?.network_access_used);
  const filesMutated = safeBoolean(codePatchPlan?.mutated_files);
  const externalWorkersUsed = safeBoolean(codePatchPlan?.external_workers_used);
  const patchApplicationLive = safeBoolean(codePatchPlan?.patch_application_live);
  const canApplyPatch = safeBoolean(codePatchPlan?.can_apply_patch);
  const unexpectedAuthority =
    shellUsed === true ||
    networkUsed === true ||
    filesMutated === true ||
    externalWorkersUsed === true ||
    patchApplicationLive === true ||
    canApplyPatch === true;

  return (
    <section
      style={{
        ...styles.card,
        ...(active ? styles.blockedCard : styles.inactiveCard)
      }}
    >
      <div style={styles.header}>
        <div>
          <div style={styles.eyebrow}>Derived UI boundary</div>
          <h3 style={styles.title}>Command Gate</h3>
        </div>
        <span style={styles.badge}>{active ? "Blocked / Not live" : "Inactive"}</span>
      </div>

      {!active && (
        <p style={styles.emptyText}>
          No command gate active in the current room state. Command execution is
          not live from this surface.
        </p>
      )}

      {active && (
        <>
          <div style={styles.grid}>
            <Row
              label="Shell execution"
              value="Blocked / not live"
              detail={shellUsed === true ? "Unexpected use surfaced." : undefined}
            />
            <Row
              label="Patch application"
              value="Approval required / not live"
              detail={
                patchApplicationLive === true || canApplyPatch === true
                  ? "Unexpected live authority surfaced."
                  : undefined
              }
            />
            <Row
              label="File mutation"
              value="Not live from this UI path"
              detail={filesMutated === true ? "Unexpected mutation surfaced." : undefined}
            />
            <Row
              label="External workers"
              value="Aider/OpenHands planned / not live"
              detail={
                externalWorkersUsed === true
                  ? "Unexpected external worker use surfaced."
                  : undefined
              }
            />
            <Row
              label="Network"
              value="Blocked unless a future governed tool path explicitly allows it"
              detail={networkUsed === true ? "Unexpected network use surfaced." : undefined}
            />
            {!compact && (
              <>
                <Row label="Git mutation" value="Blocked / not live" />
                <Row label="Package install" value="Blocked / not live" />
                <Row
                  label="Mode"
                  value={mode ? humanize(mode) : "Mode not surfaced"}
                />
              </>
            )}
          </div>

          {unexpectedAuthority && (
            <div style={styles.warningPanel}>
              Unexpected command authority surfaced. Verify governance before
              proceeding.
            </div>
          )}

          <div style={styles.boundaryPanel}>
            <strong>Truth card only</strong>
            <span>
              This is a UI truth card derived from current Coder posture. It is
              not a live command runner and does not grant execution authority.
            </span>
          </div>
        </>
      )}
    </section>
  );
}

const styles: Record<string, CSSProperties> = {
  card: {
    borderRadius: 18,
    padding: 16,
    boxShadow: "0 18px 50px rgba(0, 0, 0, 0.24)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    color: "rgba(248, 250, 252, 0.92)"
  },
  blockedCard: {
    border: "1px solid rgba(251, 113, 133, 0.42)",
    background: "rgba(76, 5, 25, 0.46)"
  },
  inactiveCard: {
    border: "1px solid rgba(148, 163, 184, 0.22)",
    background: "rgba(15, 23, 42, 0.76)"
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12
  },
  eyebrow: {
    color: "rgba(226, 232, 240, 0.64)",
    fontSize: 11,
    letterSpacing: "0.12em",
    textTransform: "uppercase"
  },
  title: {
    margin: "3px 0 0",
    color: "rgba(248, 250, 252, 0.96)",
    fontSize: 18,
    lineHeight: 1.2
  },
  badge: {
    border: "1px solid rgba(226, 232, 240, 0.22)",
    borderRadius: 999,
    padding: "4px 9px",
    fontSize: 12,
    color: "rgba(248, 250, 252, 0.9)",
    background: "rgba(15, 23, 42, 0.45)",
    whiteSpace: "nowrap"
  },
  grid: {
    display: "grid",
    gap: 8
  },
  row: {
    display: "grid",
    gridTemplateColumns: "minmax(128px, 0.42fr) 1fr",
    gap: 10,
    alignItems: "baseline"
  },
  rowLabel: {
    color: "rgba(254, 205, 211, 0.72)",
    fontSize: 12
  },
  rowValue: {
    color: "rgba(255, 241, 242, 0.92)",
    fontSize: 13,
    overflowWrap: "anywhere"
  },
  detail: {
    color: "rgba(254, 202, 202, 0.82)",
    fontWeight: 700
  },
  emptyText: {
    margin: 0,
    color: "rgba(226, 232, 240, 0.76)",
    fontSize: 13,
    lineHeight: 1.5
  },
  boundaryPanel: {
    border: "1px solid rgba(254, 205, 211, 0.28)",
    borderRadius: 14,
    padding: 12,
    background: "rgba(127, 29, 29, 0.24)",
    display: "grid",
    gap: 5,
    color: "rgba(255, 228, 230, 0.92)",
    fontSize: 13,
    lineHeight: 1.45
  },
  warningPanel: {
    border: "1px solid rgba(251, 191, 36, 0.42)",
    borderRadius: 14,
    padding: 12,
    background: "rgba(69, 26, 3, 0.44)",
    color: "rgba(254, 243, 199, 0.94)",
    fontSize: 13,
    lineHeight: 1.45
  }
};

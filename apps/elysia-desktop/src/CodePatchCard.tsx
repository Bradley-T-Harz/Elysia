import type { CSSProperties } from "react";
import type { CodePatchPlanSummaryData } from "./api/bridgeClient";

type CardState = "live" | "blocked" | "degraded" | "partial" | "planned";

export type CodePatchCardProps = {
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

function safeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return "Unknown";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatBool(value: boolean | null | undefined, trueText: string, falseText: string): string {
  if (value === true) {
    return trueText;
  }

  if (value === false) {
    return falseText;
  }

  return "Not surfaced";
}

function getCodePatchPlanState(
  codePatchPlan?: CodePatchPlanSummaryData | null
): CardState {
  if (!codePatchPlan) {
    return "planned";
  }

  const status = safeString(codePatchPlan.status)?.toLowerCase() ?? "";

  if (codePatchPlan.used === true && status === "completed") {
    return "live";
  }

  if (status === "blocked") {
    return "blocked";
  }

  if (["failed", "error", "degraded"].includes(status)) {
    return "degraded";
  }

  if (codePatchPlan.used === false || status === "not_needed") {
    return "partial";
  }

  return "partial";
}

function stateLabel(state: CardState): string {
  switch (state) {
    case "live":
      return "Proposal ready";
    case "blocked":
      return "Blocked";
    case "degraded":
      return "Degraded";
    case "partial":
      return "Partial";
    case "planned":
      return "Planned";
  }
}

function stateStyle(state: CardState): CSSProperties {
  const base: CSSProperties = {
    border: "1px solid rgba(229, 231, 235, 0.18)",
    color: "rgba(248, 250, 252, 0.92)",
    background: "rgba(15, 23, 42, 0.86)"
  };

  if (state === "live") {
    return {
      ...base,
      borderColor: "rgba(196, 181, 253, 0.48)",
      background: "rgba(49, 46, 129, 0.46)"
    };
  }

  if (state === "blocked") {
    return {
      ...base,
      borderColor: "rgba(251, 113, 133, 0.45)",
      background: "rgba(76, 5, 25, 0.5)"
    };
  }

  if (state === "degraded") {
    return {
      ...base,
      borderColor: "rgba(251, 191, 36, 0.45)",
      background: "rgba(69, 26, 3, 0.48)"
    };
  }

  if (state === "partial") {
    return {
      ...base,
      borderColor: "rgba(148, 163, 184, 0.38)",
      background: "rgba(30, 41, 59, 0.58)"
    };
  }

  return base;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.row}>
      <span style={styles.rowLabel}>{label}</span>
      <span style={styles.rowValue}>{value}</span>
    </div>
  );
}

function ListSection({
  title,
  values,
  emptyText,
  limit = 6
}: {
  title: string;
  values: string[];
  emptyText: string;
  limit?: number;
}) {
  if (values.length === 0) {
    return (
      <div style={styles.listSection}>
        <div style={styles.sectionTitle}>{title}</div>
        <div style={styles.muted}>{emptyText}</div>
      </div>
    );
  }

  const visible = values.slice(0, limit);
  const remainder = values.length - visible.length;

  return (
    <div style={styles.listSection}>
      <div style={styles.sectionTitle}>{title}</div>
      <ol style={styles.list}>
        {visible.map((value, index) => (
          <li key={`${value}-${index}`}>{value}</li>
        ))}
      </ol>
      {remainder > 0 && <div style={styles.muted}>+ {remainder} more</div>}
    </div>
  );
}

export default function CodePatchCard({
  codePatchPlan,
  compact = false
}: CodePatchCardProps) {
  const state = getCodePatchPlanState(codePatchPlan);

  if (!codePatchPlan) {
    return (
      <section style={{ ...styles.card, ...stateStyle(state) }}>
        <div style={styles.header}>
          <div>
            <div style={styles.eyebrow}>Coder truth surface</div>
            <h3 style={styles.title}>Code Patch Plan</h3>
          </div>
          <span style={styles.badge}>{stateLabel(state)}</span>
        </div>

        <p style={styles.emptyText}>
          No code patch plan surfaced for the latest response. Coder can still
          discuss code, but this card only appears when the governed runtime
          returns a proposal-only patch plan.
        </p>
      </section>
    );
  }

  const status = safeString(codePatchPlan.status);
  const summary = safeString(codePatchPlan.summary);
  const filesToTouch = safeStringArray(codePatchPlan.files_to_touch);
  const patchPlan = safeStringArray(codePatchPlan.patch_plan);
  const testsToRun = safeStringArray(codePatchPlan.tests_to_run);
  const riskNotes = safeStringArray(codePatchPlan.risk_notes);
  const rollbackNotes = safeStringArray(codePatchPlan.rollback_notes);
  const approvalReason = safeString(codePatchPlan.approval_reason);
  const warnings = safeStringArray(codePatchPlan.warnings);
  const errors = safeStringArray(codePatchPlan.errors);

  const canApplyPatch = safeBoolean(codePatchPlan.can_apply_patch);
  const patchApplicationLive = safeBoolean(codePatchPlan.patch_application_live);
  const unexpectedAuthority = canApplyPatch === true || patchApplicationLive === true;

  return (
    <section style={{ ...styles.card, ...stateStyle(state) }}>
      <div style={styles.header}>
        <div>
          <div style={styles.eyebrow}>Proposal-only Coder plan</div>
          <h3 style={styles.title}>Code Patch Plan</h3>
        </div>
        <span style={styles.badge}>{stateLabel(state)}</span>
      </div>

      <div style={styles.grid}>
        <Row label="Status" value={humanize(status)} />
        <Row label="Summary" value={summary ?? "No summary surfaced"} />
        <Row
          label="Files"
          value={
            filesToTouch.length > 0
              ? filesToTouch.join(", ")
              : "No explicit files surfaced"
          }
        />
        <Row
          label="Approval"
          value={
            safeBoolean(codePatchPlan.approval_needed) === true
              ? approvalReason ?? "Approval required before any future patch application"
              : "No patch approval request surfaced"
          }
        />
        <Row
          label="Patch application"
          value={formatBool(
            patchApplicationLive,
            "Unexpectedly marked live",
            "Not live"
          )}
        />
        <Row
          label="Can apply patch"
          value={formatBool(canApplyPatch, "Unexpectedly true", "No")}
        />
        <Row
          label="Shell execution"
          value={formatBool(
            safeBoolean(codePatchPlan.shell_execution_used),
            "Unexpectedly used",
            "Not used"
          )}
        />
        <Row
          label="External workers"
          value={formatBool(
            safeBoolean(codePatchPlan.external_workers_used),
            "Unexpectedly used",
            "Not used"
          )}
        />
        <Row
          label="Network"
          value={formatBool(
            safeBoolean(codePatchPlan.network_access_used),
            "Unexpectedly used",
            "Not used"
          )}
        />
        <Row
          label="Files mutated"
          value={formatBool(
            safeBoolean(codePatchPlan.mutated_files),
            "Unexpectedly mutated",
            "No"
          )}
        />
      </div>

      {unexpectedAuthority && (
        <div style={styles.warningPanel}>
          Unexpected live patch authority surfaced. Verify governance before
          proceeding.
        </div>
      )}

      {!compact && (
        <>
          <div style={styles.divider} />
          <ListSection
            title="Patch steps"
            values={patchPlan}
            emptyText="Patch steps not surfaced"
          />
          <ListSection
            title="Tests to run"
            values={testsToRun}
            emptyText="Test commands not surfaced"
          />
          <ListSection
            title="Risk notes"
            values={riskNotes}
            emptyText="Risk notes not surfaced"
          />
          <ListSection
            title="Rollback notes"
            values={rollbackNotes}
            emptyText="Rollback notes not surfaced"
          />
        </>
      )}

      <div style={styles.boundaryPanel}>
        <strong>Proposal only · No files changed</strong>
        <span>
          No shell commands were run. No external coding worker was invoked.
          Approval is required before any future patch application.
        </span>
      </div>

      {warnings.length > 0 && (
        <ListSection title="Warnings" values={warnings} emptyText="" limit={4} />
      )}
      {errors.length > 0 && (
        <ListSection title="Errors" values={errors} emptyText="" limit={4} />
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
    gap: 12
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
    gridTemplateColumns: "minmax(118px, 0.42fr) 1fr",
    gap: 10,
    alignItems: "baseline"
  },
  rowLabel: {
    color: "rgba(203, 213, 225, 0.68)",
    fontSize: 12
  },
  rowValue: {
    color: "rgba(248, 250, 252, 0.9)",
    fontSize: 13,
    overflowWrap: "anywhere"
  },
  divider: {
    height: 1,
    background: "rgba(226, 232, 240, 0.12)"
  },
  listSection: {
    display: "grid",
    gap: 6
  },
  sectionTitle: {
    color: "rgba(226, 232, 240, 0.86)",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.04em",
    textTransform: "uppercase"
  },
  list: {
    margin: 0,
    paddingLeft: 18,
    color: "rgba(248, 250, 252, 0.86)",
    fontSize: 13,
    lineHeight: 1.45
  },
  muted: {
    color: "rgba(203, 213, 225, 0.58)",
    fontSize: 13
  },
  emptyText: {
    margin: 0,
    color: "rgba(226, 232, 240, 0.76)",
    fontSize: 13,
    lineHeight: 1.5
  },
  boundaryPanel: {
    border: "1px solid rgba(196, 181, 253, 0.24)",
    borderRadius: 14,
    padding: 12,
    background: "rgba(49, 46, 129, 0.28)",
    display: "grid",
    gap: 5,
    color: "rgba(237, 233, 254, 0.92)",
    fontSize: 13,
    lineHeight: 1.45
  },
  warningPanel: {
    border: "1px solid rgba(251, 113, 133, 0.38)",
    borderRadius: 14,
    padding: 12,
    background: "rgba(76, 5, 25, 0.34)",
    color: "rgba(255, 228, 230, 0.92)",
    fontSize: 13,
    lineHeight: 1.45
  }
};

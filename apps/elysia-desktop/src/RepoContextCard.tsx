import type { CSSProperties } from "react";
import type { RepoContextSummaryData } from "./api/bridgeClient";

type CardState = "live" | "blocked" | "degraded" | "partial" | "planned";

export type RepoContextCardProps = {
  repoContext?: RepoContextSummaryData | null;
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

function formatList(values: string[], emptyText: string, limit = 4): string {
  if (values.length === 0) {
    return emptyText;
  }

  const visible = values.slice(0, limit);
  const remainder = values.length - visible.length;

  return remainder > 0
    ? `${visible.join(", ")} + ${remainder} more`
    : visible.join(", ");
}

function getRepoContextState(repoContext?: RepoContextSummaryData | null): CardState {
  if (!repoContext) {
    return "planned";
  }

  const status = safeString(repoContext.status)?.toLowerCase() ?? "";

  if (repoContext.used === true && status === "completed") {
    return "live";
  }

  if (status === "blocked") {
    return "blocked";
  }

  if (["failed", "error", "degraded"].includes(status)) {
    return "degraded";
  }

  if (repoContext.used === false || status === "not_needed") {
    return "partial";
  }

  return "partial";
}

function stateLabel(state: CardState): string {
  switch (state) {
    case "live":
      return "Live";
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
      borderColor: "rgba(125, 211, 252, 0.45)",
      background: "rgba(8, 47, 73, 0.55)"
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
      borderColor: "rgba(167, 139, 250, 0.42)",
      background: "rgba(49, 46, 129, 0.38)"
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
      <ul style={styles.list}>
        {visible.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
      {remainder > 0 && <div style={styles.muted}>+ {remainder} more</div>}
    </div>
  );
}

export default function RepoContextCard({
  repoContext,
  compact = false
}: RepoContextCardProps) {
  const state = getRepoContextState(repoContext);

  if (!repoContext) {
    return (
      <section style={{ ...styles.card, ...stateStyle(state) }}>
        <div style={styles.header}>
          <div>
            <div style={styles.eyebrow}>Coder truth surface</div>
            <h3 style={styles.title}>Repo Context</h3>
          </div>
          <span style={styles.badge}>{stateLabel(state)}</span>
        </div>

        <p style={styles.emptyText}>
          No repo context surfaced for the latest response. Coder repo context is
          display-only here and only appears after a governed Coder request uses
          the approved repo-context path.
        </p>
      </section>
    );
  }

  const status = safeString(repoContext.status);
  const repoLabel = safeString(repoContext.repo_label);
  const repoKey = safeString(repoContext.repo_key);
  const repoRoot = safeString(repoContext.repo_root);
  const trustZone = safeString(repoContext.trust_zone);
  const branch = safeString(repoContext.current_branch);
  const changedFilesNote = safeString(repoContext.changed_files_note);
  const languageHints = safeStringArray(repoContext.language_hints);
  const frameworkHints = safeStringArray(repoContext.framework_hints);
  const importantFiles = safeStringArray(repoContext.important_top_level_files);
  const topLevelDirectories = safeStringArray(repoContext.top_level_directories);
  const safeTreeEntries = safeStringArray(repoContext.safe_tree_entries);
  const testCommandHints = safeStringArray(repoContext.test_command_hints);
  const warnings = safeStringArray(repoContext.warnings);
  const errors = safeStringArray(repoContext.errors);

  return (
    <section style={{ ...styles.card, ...stateStyle(state) }}>
      <div style={styles.header}>
        <div>
          <div style={styles.eyebrow}>Read-only Coder context</div>
          <h3 style={styles.title}>Repo Context</h3>
        </div>
        <span style={styles.badge}>{stateLabel(state)}</span>
      </div>

      <div style={styles.grid}>
        <Row label="Status" value={humanize(status)} />
        <Row label="Repo" value={repoLabel ?? repoKey ?? "Not surfaced"} />
        <Row label="Root" value={repoRoot ?? "Not surfaced"} />
        <Row label="Trust zone" value={humanize(trustZone)} />
        <Row label="Branch" value={branch ?? "Not surfaced"} />
        <Row
          label="Git repo"
          value={formatBool(
            safeBoolean(repoContext.appears_git_repo),
            "Appears to be a git repo",
            "Not marked as git repo"
          )}
        />
        <Row
          label="Changed files"
          value={
            safeBoolean(repoContext.changed_files_live) === true
              ? "Live changed-file hints surfaced"
              : changedFilesNote ?? "Changed-file detection not live"
          }
        />
      </div>

      {!compact && (
        <>
          <div style={styles.divider} />

          <ListSection
            title="Languages"
            values={languageHints}
            emptyText="Language hints not surfaced"
          />
          <ListSection
            title="Frameworks"
            values={frameworkHints}
            emptyText="Framework hints not surfaced"
          />
          <ListSection
            title="Important top-level files"
            values={importantFiles}
            emptyText="Important files not surfaced"
          />
          <ListSection
            title="Top-level directories"
            values={topLevelDirectories}
            emptyText="Top-level directories not surfaced"
          />
          <ListSection
            title="Safe tree entries"
            values={safeTreeEntries}
            emptyText="Safe tree entries not surfaced"
            limit={8}
          />
          <ListSection
            title="Test command hints"
            values={testCommandHints}
            emptyText="Test hints not surfaced"
            limit={4}
          />
        </>
      )}

      {compact && (
        <div style={styles.compactLine}>
          {formatList(languageHints, "No language hints")} ·{" "}
          {formatList(frameworkHints, "No framework hints", 2)}
        </div>
      )}

      <div style={styles.boundaryPanel}>
        <strong>No shell · No network · No file mutation</strong>
        <span>
          Read-only approved repo context. This card displays what was surfaced;
          it does not open files, run git commands, or grant repo authority.
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
    gridTemplateColumns: "minmax(110px, 0.42fr) 1fr",
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
  compactLine: {
    color: "rgba(226, 232, 240, 0.76)",
    fontSize: 13
  },
  boundaryPanel: {
    border: "1px solid rgba(125, 211, 252, 0.22)",
    borderRadius: 14,
    padding: 12,
    background: "rgba(8, 47, 73, 0.28)",
    display: "grid",
    gap: 5,
    color: "rgba(224, 242, 254, 0.9)",
    fontSize: 13,
    lineHeight: 1.45
  }
};

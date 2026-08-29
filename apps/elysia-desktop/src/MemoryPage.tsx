import { useEffect, useMemo, useState } from "react";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";
import MemoryFilters, {
  DEFAULT_MEMORY_FILTERS,
  type MemoryFilterState
} from "./MemoryFilters";
import MemoryList from "./MemoryList";
import type {
  MemoryItemSummary,
  MemoryItemsEnvelope,
  MemorySummaryEnvelope
} from "./api/bridgeClient";
import {
  applyMemoryConsequence,
  applyMemoryArchiveRestore,
  applyMemoryFormAction,
  addMemoryRelation,
  applyMemoryMigration,
  correctMemory,
  createMemory,
  createMemorySpace,
  createMemoryJob,
  decideMemoryCandidate,
  fetchMemoryItems,
  fetchMemoryHealth,
  fetchMemoryGraph,
  fetchMemoryBeliefExplanation,
  fetchDueProspectiveMemory,
  fetchMemoryHomeostasis,
  fetchMemoryJobs,
  fetchMemoryBackupStatus,
  fetchMemoryMigrationStatus,
  fetchMemoryReceipts,
  fetchMemorySettings,
  fetchMemoryRevisions,
  fetchMemorySpaces,
  fetchMemorySpaceInvitations,
  fetchMemorySummary,
  fetchMemoryTierHistory,
  exportMemoryArchive,
  moveMemoryTier,
  pinMemory,
  previewMemoryConsequence,
  previewMemoryArchiveRestore,
  respondMemorySpaceInvitation,
  relockSealedMemory,
  runMemoryJob,
  setMemoryAutomaticRecall,
  setMemoryArchived,
  unlockSealedMemory
} from "./api/bridgeClient";
import type {
  MemoryItemCardActionAvailability,
  MemoryItemCardData
} from "./MemoryItemCard";

type MemoryPageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  red: "#A95A61",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)"
} as const;

type LoadState = "idle" | "loading" | "loaded" | "error";

const allowedMemoryClasses = new Set<MemoryItemCardData["memoryClass"]>([
  "working",
  "conversation",
  "project",
  "research",
  "operational",
  "preference",
  "sealed_private",
  "audit"
]);

const allowedSensitivities = new Set<MemoryItemCardData["sensitivity"]>([
  "public",
  "internal",
  "private",
  "sealed"
]);

const allowedMutabilities = new Set<MemoryItemCardData["mutability"]>([
  "live_editable",
  "append_only",
  "review_required",
  "immutable",
  "not_yet_live"
]);

const allowedStatuses = new Set<MemoryItemCardData["status"]>([
  "active",
  "provisional",
  "archived",
  "superseded",
  "blocked"
]);

export default function MemoryPage({
  startupReady,
  onRightDrawerSectionsChange
}: MemoryPageProps) {
  const [filters, setFilters] = useState<MemoryFilterState>(
    DEFAULT_MEMORY_FILTERS
  );
  const [summaryEnvelope, setSummaryEnvelope] =
    useState<MemorySummaryEnvelope | null>(null);
  const [itemsEnvelope, setItemsEnvelope] =
    useState<MemoryItemsEnvelope | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [foundationTruth, setFoundationTruth] = useState<Record<string, any>>({});
  const [pendingDelete, setPendingDelete] = useState<Record<string, any> | null>(null);

  const hasActiveFilters = useMemo(() => {
    return Boolean(
      filters.searchQuery.trim() ||
        filters.memoryClass ||
        filters.sensitivity ||
        filters.mutability ||
        filters.status ||
        filters.scope ||
        filters.form
        || filters.tier
    );
  }, [filters]);

  useEffect(() => {
    if (!startupReady) {
      setSummaryEnvelope(null);
      setItemsEnvelope(null);
      setLoadState("idle");
      setLoadError(null);
      return;
    }

    let cancelled = false;

    async function loadMemoryTruth() {
      setLoadState("loading");
      setLoadError(null);

      const [summaryResult, itemsResult, candidatesResult, receiptsResult, spacesResult, invitationsResult, healthResult, migrationResult, backupResult, homeostasisResult, jobsResult, prospectiveResult, settingsResult] = await Promise.all([
        fetchMemorySummary(),
        fetchMemoryItems({
          searchQuery: filters.searchQuery,
          memoryClass: filters.memoryClass,
          sensitivity: filters.sensitivity,
          mutability: filters.mutability,
          status: filters.status,
          scope: filters.scope,
          form: filters.form,
          activationTier: filters.tier,
          limit: 50,
          offset: 0
        }),
        fetchMemoryItems({ status: "provisional", limit: 200, offset: 0 }),
        fetchMemoryReceipts(),
        fetchMemorySpaces(),
        fetchMemorySpaceInvitations(),
        fetchMemoryHealth(),
        fetchMemoryMigrationStatus(),
        fetchMemoryBackupStatus(),
        fetchMemoryHomeostasis(),
        fetchMemoryJobs(),
        fetchDueProspectiveMemory(),
        fetchMemorySettings()
      ]);

      if (cancelled) {
        return;
      }

      setSummaryEnvelope(summaryResult.payload);
      setItemsEnvelope(itemsResult.payload);
      setFoundationTruth({
        receipts: receiptsResult.payload.data?.receipts ?? [],
        spaces: spacesResult.payload.data?.spaces ?? [],
        invitations: invitationsResult.payload.data?.invitations ?? [],
        health: healthResult.payload.data?.health ?? null,
        migration: migrationResult.payload.data?.migration ?? null,
        backup: backupResult.payload.data?.backup ?? null,
        homeostasis: homeostasisResult.payload.data?.homeostasis ?? null,
        jobs: jobsResult.payload.data?.jobs ?? [],
        prospective: prospectiveResult.payload.data?.prospective ?? null,
        settings: settingsResult.payload.data?.settings ?? null,
        candidates: (candidatesResult.payload.data?.items ?? []).filter(
          (item) => item.status === "candidate" || item.state === "candidate"
        )
      });

      const errors = [
        ...(summaryResult.payload.errors ?? []),
        ...(itemsResult.payload.errors ?? []),
        ...(candidatesResult.payload.errors ?? [])
      ].filter((value) => value.trim());

      if (!summaryResult.ok || !itemsResult.ok || !candidatesResult.ok || errors.length > 0) {
        setLoadState("error");
        setLoadError(
          errors[0] ??
            "Memory endpoints did not return usable bridge truth."
        );
        return;
      }

      setLoadState("loaded");
      setLoadError(null);
    }

    void loadMemoryTruth();

    return () => {
      cancelled = true;
    };
  }, [filters, refreshNonce, startupReady]);

  function refreshMemory(message?: string) {
    setActionMessage(message ?? null);
    setRefreshNonce((value) => value + 1);
  }

  async function handlePin(memoryId: string) {
    const item = itemsEnvelope?.data?.items?.find((candidate) => candidate.memory_id === memoryId);
    const result = await pinMemory(memoryId, !(item?.is_pinned ?? item?.pinned));
    refreshMemory(result.ok ? "Pin state saved with a mutation receipt." : result.payload.errors?.[0]);
  }

  async function handleEdit(memoryId: string) {
    const item = itemsEnvelope?.data?.items?.find((candidate) => candidate.memory_id === memoryId);
    const body = window.prompt("Correct this memory body. The prior revision remains immutable.", item?.body_excerpt ?? "");
    if (body === null || !body.trim()) return;
    const reason = window.prompt("Why is this correction needed?");
    if (!reason?.trim()) return;
    const selectedKind = window.prompt(
      "Truth change kind: correction, refinement, changed_reality, direct_contradiction, or retraction",
      "correction"
    ) ?? "correction";
    const allowedKinds = new Set(["correction", "refinement", "changed_reality", "direct_contradiction", "retraction"]);
    if (!allowedKinds.has(selectedKind)) {
      refreshMemory("Choose one of the supported truth-change kinds.");
      return;
    }
    const result = await correctMemory(
      memoryId,
      body,
      reason,
      item?.title ?? undefined,
      selectedKind as "correction" | "refinement" | "changed_reality" | "direct_contradiction" | "retraction"
    );
    refreshMemory(result.ok ? "Temporal truth event and immutable revision were stored." : result.payload.errors?.[0]);
  }

  async function handleArchive(memoryId: string) {
    const item = itemsEnvelope?.data?.items?.find((candidate) => candidate.memory_id === memoryId);
    const archived = (item?.status ?? item?.state) !== "archived";
    const reason = window.prompt(archived ? "Why archive this memory?" : "Why restore this memory?");
    if (!reason?.trim()) return;
    const result = await setMemoryArchived(memoryId, archived, reason);
    refreshMemory(result.ok ? (archived ? "Memory archived." : "Memory restored.") : result.payload.errors?.[0]);
  }

  async function handleForget(memoryId: string) {
    const preview = await previewMemoryConsequence(memoryId, {
      action: "hard_delete",
      reason: "Operator requested permanent deletion from the Memory room."
    });
    const approval = preview.payload.data?.approval as Record<string, any> | undefined;
    if (!preview.ok || !approval) {
      setActionMessage(preview.payload.errors?.[0] ?? "Deletion preview failed.");
      return;
    }
    setPendingDelete({ memoryId, ...approval });
    setActionMessage("Review the exact content-free deletion plan below before applying it.");
  }

  async function applyPendingDelete() {
    if (!pendingDelete) return;
    const result = await applyMemoryConsequence(
      String(pendingDelete.memoryId),
      String(pendingDelete.approval_id),
      String(pendingDelete.approval_token)
    );
    setPendingDelete(null);
    refreshMemory(result.ok ? "Memory content purged; content-free receipt retained." : result.payload.errors?.[0]);
  }

  async function handleMove(memoryId: string) {
    const targetSpace = window.prompt("Enter the exact shared-space ID to move this memory into:");
    if (!targetSpace?.trim()) return;
    const preview = await previewMemoryConsequence(memoryId, {
      action: "move_to_space",
      target_space_id: targetSpace.trim(),
      reason: "Operator requested shared-space placement."
    });
    const approval = preview.payload.data?.approval as Record<string, any> | undefined;
    if (!preview.ok || !approval) {
      setActionMessage(preview.payload.errors?.[0] ?? "Move preview failed.");
      return;
    }
    if (!window.confirm(`Sharing consequence:\n\n${JSON.stringify(approval.consequence, null, 2)}`)) return;
    const result = await applyMemoryConsequence(memoryId, String(approval.approval_id), String(approval.approval_token));
    refreshMemory(result.ok ? "Memory moved under the shared-space ACL." : result.payload.errors?.[0]);
  }

  async function handleHistory(memoryId: string) {
    const result = await fetchMemoryRevisions(memoryId);
    if (!result.ok) {
      setActionMessage(result.payload.errors?.[0] ?? "Revision history is unavailable.");
      return;
    }
    const revisions = (result.payload.data?.revisions ?? []) as Array<Record<string, unknown>>;
    setActionMessage(
      revisions.length
        ? revisions.map((row) => `Revision ${row.revision_number}: ${row.reason ?? "No reason recorded"}`).join(" · ")
        : "No revision history was returned."
    );
  }

  const memoryItems = useMemo(() => {
    return (itemsEnvelope?.data?.items ?? []).map(mapMemoryItemForCard);
  }, [itemsEnvelope]);

  const actionAvailability = useMemo<MemoryItemCardActionAvailability>(() => {
    const items = itemsEnvelope?.data?.items ?? [];
    return {
      canPin: items.some((item) => item.actions?.can_pin === true),
      canMove: items.some((item) => item.actions?.can_move === true),
      canEdit: items.some((item) => item.actions?.can_edit === true),
      canForget: items.some((item) => item.actions?.can_forget === true)
    };
  }, [itemsEnvelope]);

  const totalItems = summaryEnvelope?.data?.summary?.total_items ?? 0;
  const classCount = summaryEnvelope?.data?.summary?.class_summaries?.length ?? 0;
  const generatedAt = summaryEnvelope?.data?.summary?.generated_at_utc ?? null;
  const writeActionsLive =
    summaryEnvelope?.data?.store_posture?.write_actions_live === true ||
    itemsEnvelope?.data?.query_truth?.write_actions_live === true;

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    return [
      {
        key: "active_context",
        title: "Active Context",
        state: startupReady ? "live" : "partial",
        accent: "warm",
        rows: [
          { label: "Room", value: "Memory" },
          { label: "Surface", value: "Memory chamber" },
          {
            label: "Context source",
            value: startupReady
              ? "Memory summary and item bridge paths"
              : "Waiting on startup truth"
          }
        ]
      },
      {
        key: "memory_classes",
        title: "Memory Classes",
        state: startupReady ? "live" : "partial",
        rows: [
          { label: "Total items", value: String(totalItems) },
          { label: "Classes visible", value: String(classCount) },
          {
            label: "Sealed private",
            value:
              itemsEnvelope?.data?.query_truth?.sealed_private_excluded === false
                ? "Included by backend policy"
                : "Excluded from casual item feed"
          }
        ]
      },
      {
        key: "mutability_truth",
        title: "Mutability Truth",
        state: writeActionsLive ? "live" : "inactive",
        rows: [
          {
            label: "Write actions",
            value: writeActionsLive ? "Live by backend policy" : "Inactive / not exposed"
          },
          {
            label: "Pin / move / edit / forget",
            value: writeActionsLive
              ? "Available only per item action truth"
              : "Not rendered as fake-live controls"
          },
          {
            label: "Attached files",
            value: "Not memory unless explicitly promoted"
          },
          {
            label: "Retrieval context",
            value: "Separate from stored memory"
          }
        ]
      },
      {
        key: "memory_metabolism",
        title: "Memory Metabolism",
        state: foundationTruth.health?.release_closure ? "live" : "partial",
        rows: [
          { label: "Canonical writers", value: String(foundationTruth.health?.release_closure?.canonical_writer_count ?? 1) },
          { label: "Graph", value: String(foundationTruth.health?.release_closure?.graph?.state ?? "loading") },
          { label: "Archives", value: String(foundationTruth.health?.release_closure?.archives?.state ?? "loading") },
          { label: "Jobs visible", value: String(Array.isArray(foundationTruth.jobs) ? foundationTruth.jobs.length : 0) },
          {
            label: "Summary generated",
            value: generatedAt ? formatDateTimeLabel(generatedAt) : "No summary timestamp yet"
          }
        ]
      }
    ];
  }, [
    classCount,
    generatedAt,
    foundationTruth,
    itemsEnvelope,
    startupReady,
    totalItems,
    writeActionsLive
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);

    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  if (!startupReady) {
    return (
      <div
        className="elysia-room-scroll-at-narrow"
        style={{
          display: "grid",
          gap: "1rem",
          minHeight: 0,
          flex: 1
        }}
      >
        <PageHeader
          eyebrow="Memory"
          title="Memory is waiting on startup truth."
          detail="The chamber is mounted, but memory inspection stays downstream of real startup and backend truth."
        />
      </div>
    );
  }

  const summaryCards = [
    {
      title: "Memory summary",
      tone: palette.teal,
      body:
        loadState === "error"
          ? "Summary endpoint returned an error. The room is showing that failure instead of inventing memory truth."
          : `${totalItems} stored memory item${totalItems === 1 ? "" : "s"} visible through the summary path.`
    },
    {
      title: "Continuity classes",
      tone: palette.bronze,
      body:
        classCount > 0
          ? `${classCount} class summar${classCount === 1 ? "y" : "ies"} returned by the backend.`
          : "No stored class counts are visible yet. Empty memory is valid local truth."
    },
    {
      title: "Mutability truth",
      tone: palette.emerald,
      body: writeActionsLive
        ? "Some write actions are reported live by backend policy. Item cards still respect per-item action truth."
        : "Pin, move, edit, and forget are inactive unless backend policy explicitly reports them live."
    }
  ];

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        minHeight: 0,
        flex: 1
      }}
    >
      <PageHeader
        eyebrow="Memory"
        title="Inspectable continuity belongs here."
        detail="This room distinguishes stored memory from retrieval context and attached files. It shows source, sensitivity, mutability, and action truth only where the backend provides it."
      />

      <MemoryFoundationPanel
        truth={foundationTruth}
        message={actionMessage}
        onChanged={refreshMemory}
      />

      <MemoryStewardshipPanel
        truth={foundationTruth}
        onChanged={refreshMemory}
      />

      {pendingDelete ? (
        <section
          role="dialog"
          aria-label="Exact hard-delete consequence plan"
          style={{
            display: "grid",
            gap: "0.75rem",
            padding: "1rem",
            borderRadius: "18px",
            border: `1px solid ${palette.red}`,
            background: "rgba(55, 20, 23, 0.72)"
          }}
        >
          <strong style={{ color: palette.sandstone }}>Permanent deletion plan</strong>
          <div style={{ color: palette.silverMuted }}>
            This one-time approval expires at {String(pendingDelete.expires_at_utc)} and is
            bound to the exact managed-state fingerprint below. Any managed-state change
            invalidates it.
          </div>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: "0.55rem", margin: 0 }}>
            {Object.entries(pendingDelete.consequence?.deletion_plan ?? {}).map(([label, value]) => (
              <div key={label} style={{ padding: "0.55rem", border: `1px solid ${palette.lineSilver}`, borderRadius: "10px" }}>
                <dt style={{ color: palette.silverMuted }}>{label.replaceAll("_", " ")}</dt>
                <dd style={{ color: palette.silver, margin: 0, overflowWrap: "anywhere" }}>{String(value)}</dd>
              </div>
            ))}
          </dl>
          <div style={{ color: palette.sandstone }}>
            Managed writable backups are rewritten or purged. Elysia cannot erase
            disconnected or user-exported offline copies.
          </div>
          <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
            <button type="button" onClick={() => void applyPendingDelete()} style={foundationButtonStyle}>Apply this exact permanent deletion</button>
            <button type="button" onClick={() => { setPendingDelete(null); setActionMessage("Permanent deletion cancelled; memory remains unchanged."); }} style={foundationButtonStyle}>Cancel and keep memory</button>
          </div>
        </section>
      ) : null}

      <div
        className="elysia-summary-grid-3"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: "0.85rem"
        }}
      >
        {summaryCards.map((card) => (
          <SummaryCard
            key={card.title}
            title={card.title}
            body={card.body}
            tone={card.tone}
          />
        ))}
      </div>

      <div
        className="elysia-responsive-split"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 0.95fr) minmax(0, 1.35fr)",
          gap: "1rem",
          minHeight: 0,
          flex: 1
        }}
      >
        <div
          style={{
            display: "grid",
            gap: "1rem",
            alignContent: "start",
            minHeight: 0
          }}
        >
          <MemoryFilters
            filters={filters}
            onFiltersChange={setFilters}
            isLoading={loadState === "loading"}
            onClearFilters={() => setFilters(DEFAULT_MEMORY_FILTERS)}
          />

          <section
            style={{
              padding: "1rem",
              borderRadius: "18px",
              border: `1px solid ${palette.lineBronze}`,
              background:
                "linear-gradient(180deg, rgba(43, 31, 21, 0.44) 0%, rgba(18, 25, 37, 0.72) 100%)"
            }}
          >
            <div
              style={{
                fontSize: "0.82rem",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: palette.bronze,
                marginBottom: "0.45rem"
              }}
            >
              Memory boundary truth
            </div>
            <div
              style={{
                color: palette.silverMuted,
                lineHeight: 1.6
              }}
            >
              Attached files and retrieval context are not treated as memory
              unless a later policy path explicitly promotes them. Write actions
              are live only through authenticated canonical policy, exact
              consequence previews, and durable receipts.
            </div>
          </section>
        </div>

        <section
          style={{
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
            padding: "1rem",
            borderRadius: "18px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(18, 25, 37, 0.78) 0%, rgba(11, 14, 18, 0.82) 100%)"
          }}
        >
          <div
            style={{
              fontSize: "0.82rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.emerald,
              marginBottom: "0.45rem"
            }}
          >
            Memory list
          </div>

          <MemoryList
            items={memoryItems}
            isLoading={loadState === "loading"}
            error={loadError}
            hasActiveFilters={hasActiveFilters}
            showRoomTruthNote={memoryItems.length > 0}
            actions={actionAvailability}
            onPin={handlePin}
            onMove={handleMove}
            onEdit={handleEdit}
            onForget={handleForget}
            onArchive={handleArchive}
            onHistory={handleHistory}
            emptyTitle={
              loadState === "loaded"
                ? "No memory items are visible through the current endpoint."
                : undefined
            }
            emptyDetail={
              loadState === "loaded"
                ? "This can be correct if the local memory stores are empty or filters exclude the visible slice."
                : undefined
            }
          />
        </section>
      </div>
    </div>
  );
}

const foundationInputStyle = {
  padding: "0.72rem 0.82rem",
  borderRadius: "11px",
  border: `1px solid ${palette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.55)",
  color: palette.silver,
  minWidth: 0
} as const;

const foundationButtonStyle = {
  padding: "0.7rem 0.9rem",
  borderRadius: "11px",
  border: `1px solid ${palette.lineBronze}`,
  background: "rgba(43, 31, 21, 0.46)",
  color: palette.silver,
  cursor: "pointer"
} as const;

function MemoryFoundationPanel({
  truth,
  message,
  onChanged
}: {
  truth: Record<string, any>;
  message: string | null;
  onChanged: (message?: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [whyStored, setWhyStored] = useState("");
  const [privacy, setPrivacy] = useState<"normal" | "private" | "sealed">("normal");
  const [scope, setScope] = useState("user");
  const [form, setForm] = useState("semantic");
  const [authorityId, setAuthorityId] = useState("");
  const [formDetail, setFormDetail] = useState("");
  const [candidate, setCandidate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [accountPassword, setAccountPassword] = useState("");
  const [defaultPrivacyApplied, setDefaultPrivacyApplied] = useState(false);

  useEffect(() => {
    const configured = truth.settings?.default_privacy;
    if (
      !defaultPrivacyApplied
      && (configured === "normal" || configured === "private" || configured === "sealed")
    ) {
      setPrivacy(configured);
      setDefaultPrivacyApplied(true);
    }
  }, [defaultPrivacyApplied, truth.settings]);

  async function handleCreate() {
    if (!title.trim() || !body.trim() || !whyStored.trim()) return;
    const link = authorityId.trim();
    if (["conversation", "project", "shared_space"].includes(scope) && !link) {
      onChanged(`The ${scope} scope requires its stable authority ID.`);
      return;
    }
    setBusy(true);
    const detail = formDetail.trim();
    const formData: Record<string, unknown> = form === "episodic"
      ? { context: detail || "User-declared event", occurred_at: new Date().toISOString() }
      : form === "semantic"
        ? { confirmation: "explicit" }
        : form === "procedural"
          ? { steps: detail.split(";").map((step) => step.trim()).filter(Boolean), verified: false }
          : form === "prospective"
            ? { due_at: detail, state: "pending" }
            : form === "relational"
              ? { relation: detail.split("|", 2)[0]?.trim() || "related_to", target: detail.split("|", 2)[1]?.trim() || authorityId.trim() }
              : form === "predictive"
                ? { basis: detail || whyStored.trim(), prediction: body.trim() }
                : form === "corrective"
                  ? { change_kind: detail || "changed_reality" }
                  : form === "metacognitive"
                    ? { metric: detail || "user_declared_strategy_observation" }
                    : { event_code: detail || "user_declared_audit_event", content_minimized: true };
    const result = await createMemory(
      {
        title: title.trim(),
        body: body.trim(),
        why_stored: whyStored.trim(),
        privacy,
        scope,
        form,
        form_data: formData,
        ...(form === "episodic" ? { observed_at: String(formData.occurred_at) } : {}),
        ...(scope === "conversation" ? { conversation_id: link } : {}),
        ...(scope === "project" ? { project_id: link } : {}),
        ...(scope === "shared_space" ? { space_id: link } : {}),
        status: candidate ? "candidate" : "active",
        user_confirmed: !candidate,
        inference_kind: candidate ? "operator_review_candidate" : null,
        ...(candidate ? {
          candidate_kind: "user_submitted_candidate",
          proposed_wording: body.trim(),
          evidence_summary: whyStored.trim()
        } : {}),
        source: {
          source_type: "manual_entry",
          source_authority: "user",
          provenance_status: "declared"
        }
      },
      candidate
    );
    setBusy(false);
    if (result.ok) {
      setTitle("");
      setBody("");
      setWhyStored("");
      setAuthorityId("");
      setFormDetail("");
      onChanged(candidate ? "Memory candidate submitted for review." : "Memory stored canonically.");
    } else {
      onChanged(result.payload.errors?.[0] ?? "Memory creation failed.");
    }
  }

  async function handleSealedUnlock() {
    if (!accountPassword) {
      onChanged("Enter the current local-account password in the masked field first.");
      return;
    }
    const result = await unlockSealedMemory(accountPassword, 300);
    setAccountPassword("");
    onChanged(result.ok ? "Sealed vault unlocked for a bounded five-minute window." : result.payload.errors?.[0]);
  }

  async function handleCandidateDecision(decision: "approve" | "reject") {
    const memoryId = window.prompt(`Enter the candidate memory ID to ${decision}:`);
    if (!memoryId?.trim()) return;
    const reason = window.prompt("Record the review reason:") ?? "Operator reviewed candidate.";
    const result = await decideMemoryCandidate(memoryId.trim(), decision, reason);
    onChanged(result.ok ? `Candidate ${decision}d with a durable receipt.` : result.payload.errors?.[0]);
  }

  async function handleCreateSpace() {
    const label = window.prompt("Shared-space label:");
    if (!label?.trim()) return;
    const description = window.prompt("Shared-space description:") ?? "";
    const result = await createMemorySpace(label.trim(), description.trim());
    onChanged(result.ok ? "Shared space created with owner ACL." : result.payload.errors?.[0]);
  }

  async function handleSpaceMemberLifecycle() {
    const spaceId = window.prompt("Exact shared-space ID:");
    const action = window.prompt(
      "Action: invite, direct_add, change_role, or revoke",
      "invite"
    )?.trim();
    const actionMap = {
      invite: "invite_space_member",
      direct_add: "add_space_member",
      change_role: "change_space_member_role",
      revoke: "remove_space_member"
    } as const;
    if (!action || !(action in actionMap)) return;
    const userId = window.prompt("Exact local user ID:");
    const role = action === "revoke"
      ? null
      : window.prompt("Role: editor, contributor, or reader")?.trim();
    if (
      !spaceId?.trim() ||
      !userId?.trim() ||
      (action !== "revoke" && (!role || !["editor", "contributor", "reader"].includes(role)))
    ) return;
    const preview = await previewMemoryConsequence(spaceId.trim(), {
      action: actionMap[action as keyof typeof actionMap],
      target_user_id: userId.trim(),
      ...(role ? { target_role: role } : {}),
      reason: "Operator requested an explicit shared-space ACL change."
    });
    const approval = preview.payload.data?.approval as Record<string, any> | undefined;
    if (!preview.ok || !approval) {
      onChanged(preview.payload.errors?.[0] ?? "Member approval preview failed.");
      return;
    }
    if (!window.confirm(`ACL consequence:\n\n${JSON.stringify(approval.consequence, null, 2)}`)) return;
    const result = await applyMemoryConsequence(
      spaceId.trim(),
      String(approval.approval_id),
      String(approval.approval_token)
    );
    onChanged(
      result.ok
        ? "Shared-space invitation or membership changed with an exact approval receipt."
        : result.payload.errors?.[0]
    );
  }

  async function handleInvitationResponse(invitationId: string, decision: "accept" | "decline") {
    const result = await respondMemorySpaceInvitation(invitationId, decision);
    onChanged(
      result.ok
        ? `Shared-space invitation ${decision === "accept" ? "accepted" : "declined"}.`
        : result.payload.errors?.[0]
    );
  }

  async function handlePrivacyChange() {
    const memoryId = window.prompt("Memory ID whose privacy should change:");
    if (!memoryId?.trim()) return;
    const target = window.prompt("Target privacy: normal, private, or sealed")?.trim();
    if (!target || !["normal", "private", "sealed"].includes(target)) return;
    const preview = await previewMemoryConsequence(memoryId.trim(), {
      action: "change_privacy",
      target_privacy: target,
      reason: "Operator requested a privacy transition."
    });
    const approval = preview.payload.data?.approval as Record<string, any> | undefined;
    if (!preview.ok || !approval) {
      onChanged(preview.payload.errors?.[0] ?? "Privacy preview failed.");
      return;
    }
    if (!window.confirm(`Privacy consequence:\n\n${JSON.stringify(approval.consequence, null, 2)}`)) return;
    const result = await applyMemoryConsequence(memoryId.trim(), String(approval.approval_id), String(approval.approval_token));
    onChanged(result.ok ? "Memory privacy changed and content re-encrypted." : result.payload.errors?.[0]);
  }

  async function handleMigration() {
    if (!accountPassword) {
      onChanged("Enter the current local-account password in the masked field first.");
      return;
    }
    const result = await applyMemoryMigration(accountPassword);
    setAccountPassword("");
    onChanged(result.ok ? "Legacy discovery/migration completed with validation and receipt." : result.payload.errors?.[0]);
  }

  const receipts = Array.isArray(truth.receipts) ? truth.receipts : [];
  const spaces = Array.isArray(truth.spaces) ? truth.spaces : [];
  const candidates = Array.isArray(truth.candidates) ? truth.candidates : [];

  return (
    <section style={{ display: "grid", gap: "0.85rem", padding: "1rem", borderRadius: "18px", border: `1px solid ${palette.lineSilver}`, background: "rgba(18, 25, 37, 0.72)" }}>
      <div>
        <div style={{ color: palette.teal, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.8rem" }}>Canonical Memory Fabric</div>
        <div style={{ color: palette.silverMuted, marginTop: "0.35rem" }}>Create explicit memory, submit candidates, unlock sealed records, govern sharing/privacy, inspect migration, and see durable receipts.</div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "0.65rem" }}>
        <input aria-label="Memory title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Memory title" style={foundationInputStyle} />
        <input aria-label="Memory body" value={body} onChange={(event) => setBody(event.target.value)} placeholder="Memory body" style={foundationInputStyle} />
        <input aria-label="Memory storage reason" value={whyStored} onChange={(event) => setWhyStored(event.target.value)} placeholder="Why store it?" style={foundationInputStyle} />
        <select aria-label="Memory privacy" value={privacy} onChange={(event) => setPrivacy(event.target.value as typeof privacy)} style={foundationInputStyle}>
          <option value="normal">Normal</option><option value="private">Private</option><option value="sealed">Sealed</option>
        </select>
        <select value={scope} onChange={(event) => setScope(event.target.value)} style={foundationInputStyle} aria-label="Memory scope">
          {["user", "conversation", "project", "research", "operational", "system", "shared_space"].map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        <select value={form} onChange={(event) => setForm(event.target.value)} style={foundationInputStyle} aria-label="Memory form">
          {["episodic", "semantic", "procedural", "prospective", "relational", "predictive", "corrective", "metacognitive", "audit"].map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        <input aria-label="Memory form detail" value={formDetail} onChange={(event) => setFormDetail(event.target.value)} placeholder={form === "prospective" ? "Due time (ISO)" : form === "procedural" ? "Steps separated by semicolons" : form === "relational" ? "relation | target authority ID" : "Form-specific context/basis/event code"} style={foundationInputStyle} />
        <input aria-label="Memory authority ID" value={authorityId} onChange={(event) => setAuthorityId(event.target.value)} placeholder="Conversation/project/space ID when required" style={foundationInputStyle} />
        <button type="button" disabled={busy || truth.settings?.memory_recording_enabled === false} onClick={() => void handleCreate()} style={foundationButtonStyle}>{truth.settings?.memory_recording_enabled === false ? "Memory recording disabled in Settings" : busy ? "Storing…" : candidate ? "Submit candidate" : "Store memory"}</button>
      </div>
      <label style={{ color: palette.silverMuted }}><input type="checkbox" checked={candidate} onChange={(event) => setCandidate(event.target.checked)} /> Require candidate review before activation</label>
      <label style={{ display: "grid", gap: "0.3rem", color: palette.silverMuted, maxWidth: "34rem" }}>
        Local password for sealed unlock or migration
        <input
          aria-label="Local password for sealed unlock or migration"
          type="password"
          autoComplete="current-password"
          value={accountPassword}
          onChange={(event) => setAccountPassword(event.target.value)}
          placeholder="Used only for this operation; never displayed in receipts"
          style={foundationInputStyle}
        />
      </label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.55rem" }}>
        <button type="button" onClick={() => void handleSealedUnlock()} style={foundationButtonStyle}>Unlock sealed vault</button>
        <button type="button" onClick={() => void relockSealedMemory().then(() => onChanged("Sealed vault relocked."))} style={foundationButtonStyle}>Relock sealed vault</button>
        <button type="button" onClick={() => void handleCandidateDecision("approve")} style={foundationButtonStyle}>Approve candidate</button>
        <button type="button" onClick={() => void handleCandidateDecision("reject")} style={foundationButtonStyle}>Reject candidate</button>
        <button type="button" onClick={() => void handleCreateSpace()} style={foundationButtonStyle}>Create shared space</button>
        <button type="button" onClick={() => void handleSpaceMemberLifecycle()} style={foundationButtonStyle}>Invite or govern shared-space member</button>
        <button type="button" onClick={() => void handlePrivacyChange()} style={foundationButtonStyle}>Change privacy</button>
        <button type="button" onClick={() => void handleMigration()} style={foundationButtonStyle}>Run legacy migration</button>
      </div>
      {candidates.length ? (
        <div style={{ display: "grid", gap: "0.45rem" }}>
          <strong>Pending candidate queue</strong>
          {candidates.map((item: any) => (
            <div key={item.memory_id} style={{ display: "grid", gridTemplateColumns: "minmax(14rem, 1fr) minmax(16rem, 2fr) auto", gap: "0.6rem", alignItems: "center" }}>
              <span>{item.title ?? "Untitled candidate"} · {item.candidate_kind ?? "review required"} · {item.memory_id}</span>
              <span style={{ color: palette.silverMuted, lineHeight: 1.5 }}>
                Proposed: {item.candidate_proposed_wording ?? item.body_excerpt ?? item.body ?? "No wording supplied"}
                {item.candidate_evidence_summary ? ` · Evidence: ${item.candidate_evidence_summary}` : ""}
                {item.why_stored ? ` · Why: ${item.why_stored}` : ""}
                {` · Form: ${item.form ?? "unspecified"} · Scope: ${item.scope ?? "unspecified"} · Privacy: ${item.privacy ?? "normal"}`}
                {item.confidence !== null && item.confidence !== undefined ? ` · Confidence: ${item.confidence}` : ""}
                {item.activation_tier ? ` · Suggested tier: ${item.activation_tier}` : ""}
                {Array.isArray(item.sources) && item.sources.length ? ` · Sources: ${item.sources.length}` : ""}
                {item.candidate_deferred_until ? ` · Deferred until ${item.candidate_deferred_until}` : ""}
              </span>
              <span style={{ display: "flex", gap: "0.4rem" }}>
                <button type="button" onClick={() => void decideMemoryCandidate(item.memory_id, "approve", "Operator approved candidate from Memory queue.").then((result) => onChanged(result.ok ? "Candidate approved." : result.payload.errors?.[0]))} style={foundationButtonStyle}>Approve</button>
                <button type="button" onClick={() => { const edited = window.prompt("Edit the proposed memory before approval:", item.candidate_proposed_wording ?? item.body ?? ""); if (edited?.trim()) void decideMemoryCandidate(item.memory_id, "approve", "Operator edited and approved candidate from Memory queue.", { edited_body: edited.trim() }).then((result) => onChanged(result.ok ? "Candidate edited and approved." : result.payload.errors?.[0])); }} style={foundationButtonStyle}>Edit + approve</button>
                <button type="button" onClick={() => void decideMemoryCandidate(item.memory_id, "reject", "Operator rejected candidate from Memory queue.").then((result) => onChanged(result.ok ? "Candidate rejected." : result.payload.errors?.[0]))} style={foundationButtonStyle}>Reject</button>
                <button type="button" onClick={() => { const until = window.prompt("Optional ISO date/time to revisit this candidate:") ?? ""; void decideMemoryCandidate(item.memory_id, "defer", "Operator deferred candidate review.", { defer_until: until || null }).then((result) => onChanged(result.ok ? "Candidate deferred without promotion." : result.payload.errors?.[0])); }} style={foundationButtonStyle}>Defer</button>
                <button type="button" onClick={() => void decideMemoryCandidate(item.memory_id, "seal", "Operator approved candidate into Sealed Memory.").then((result) => onChanged(result.ok ? "Candidate approved into Sealed Memory." : result.payload.errors?.[0]))} style={foundationButtonStyle}>Seal</button>
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {(truth.invitations ?? []).some((item: any) => item.direction === "incoming" && item.state === "pending") ? (
        <div style={{ display: "grid", gap: "0.45rem" }}>
          <strong>Pending Shared Space invitations</strong>
          {(truth.invitations ?? []).filter((item: any) => item.direction === "incoming" && item.state === "pending").map((item: any) => (
            <div key={item.invitation_id} style={{ display: "flex", flexWrap: "wrap", gap: "0.55rem", alignItems: "center" }}>
              <span>{item.space_label} · role {item.role}</span>
              <button type="button" onClick={() => void handleInvitationResponse(String(item.invitation_id), "accept")} style={foundationButtonStyle}>Accept</button>
              <button type="button" onClick={() => void handleInvitationResponse(String(item.invitation_id), "decline")} style={foundationButtonStyle}>Decline</button>
            </div>
          ))}
        </div>
      ) : null}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.65rem", color: palette.silverMuted, fontSize: "0.86rem" }}>
        <div>Receipts: {receipts.length}<br />{receipts.slice(0, 3).map((row: any) => row.action).filter(Boolean).join(", ") || "None yet"}</div>
        <div>Shared spaces: {spaces.length} · invitations: {(truth.invitations ?? []).length}<br />{spaces.map((space: any) => `${space.label} (${space.space_id})`).join(", ") || "None"}</div>
        <div>Migration: {String(truth.migration?.state ?? truth.migration?.status ?? "not yet recorded")}<br />Legacy writer: off</div>
        <div>Backup: {truth.backup?.automatic_pre_migration_backup ? "pre-migration enabled" : "status unavailable"}<br />Sealed index: none persistent</div>
        <div>Lexical projection: {String(truth.health?.lexical_projection?.state ?? "unknown")}<br />Indexed normal: {String(truth.health?.lexical_projection?.indexed_normal_records ?? 0)} · private plaintext index: no</div>
        <div>Semantic projection: {String(truth.health?.semantic_projection?.state ?? "unknown")}<br />Indexed normal: {String(truth.health?.semantic_projection?.indexed_normal_records ?? 0)} · Private/Sealed vectors: none</div>
        <div>Research evidence: {String(truth.health?.research_evidence?.state ?? "unknown")}<br />Durable records: {String(truth.health?.research_evidence?.evidence_count ?? 0)}</div>
      </div>
      {message ? <div role="status" style={{ color: palette.sandstone }}>{message}</div> : null}
    </section>
  );
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return window.btoa(binary);
}

function MemoryStewardshipPanel({
  truth,
  onChanged
}: {
  truth: Record<string, any>;
  onChanged: (message?: string) => void;
}) {
  const [memoryId, setMemoryId] = useState("");
  const [tier, setTier] = useState<"working" | "hot" | "warm" | "cold" | "archived">("warm");
  const [formAction, setFormAction] = useState("complete");
  const [formValue, setFormValue] = useState("");
  const [jobKind, setJobKind] = useState("tier_maintenance");
  const [recovery, setRecovery] = useState("");
  const [archiveScope, setArchiveScope] = useState<"full_account" | "selected_project" | "selected_space" | "metadata_audit">("full_account");
  const [archiveAuthorityId, setArchiveAuthorityId] = useState("");
  const [restoreBase64, setRestoreBase64] = useState("");
  const [restorePlan, setRestorePlan] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);

  async function inspect(kind: "history" | "graph" | "belief") {
    if (!memoryId.trim()) return;
    const result = kind === "history"
      ? await fetchMemoryTierHistory(memoryId.trim())
      : kind === "graph"
        ? await fetchMemoryGraph(memoryId.trim())
        : await fetchMemoryBeliefExplanation(memoryId.trim());
    onChanged(
      result.ok
        ? `${kind === "history" ? "Tier history" : kind === "graph" ? "Bounded relationship view" : "Why currently believed"}: ${JSON.stringify(result.payload.data)}`
        : result.payload.errors?.[0]
    );
  }

  async function relateMemory() {
    if (!memoryId.trim()) return;
    const targetId = window.prompt("Exact target memory ID:");
    if (!targetId?.trim()) return;
    const relationType = window.prompt("Relationship type (for example supports, depends_on, related_to):", "related_to");
    if (!relationType?.trim()) return;
    const result = await addMemoryRelation(memoryId.trim(), {
      target_type: "memory",
      target_id: targetId.trim(),
      relation_type: relationType.trim(),
      inferred: false
    });
    onChanged(result.ok ? "Provenance-bearing relationship stored canonically." : result.payload.errors?.[0]);
  }

  async function applyTier() {
    if (!memoryId.trim()) return;
    setBusy(true);
    const result = await moveMemoryTier(memoryId.trim(), tier, "Operator changed the lifecycle tier from Memory stewardship.");
    setBusy(false);
    onChanged(result.ok ? `Memory moved to ${tier}; movement history and projection policy were updated.` : result.payload.errors?.[0]);
  }

  async function applyFormBehavior() {
    if (!memoryId.trim()) return;
    const payload: Record<string, unknown> = {
      action: formAction,
      reason: "Operator applied form-specific behavior from Memory stewardship."
    };
    if (formAction === "snooze") payload.due_at = formValue;
    if (formAction === "record_outcome") payload.outcome = formValue;
    const result = await applyMemoryFormAction(memoryId.trim(), payload);
    onChanged(result.ok ? "Form-specific memory state changed with an immutable revision." : result.payload.errors?.[0]);
  }

  async function startJob() {
    setBusy(true);
    const created = await createMemoryJob(jobKind);
    const jobId = created.payload.data?.job?.job_id as string | undefined;
    if (!created.ok || !jobId) {
      setBusy(false);
      onChanged(created.payload.errors?.[0] ?? "Memory maintenance job was not accepted.");
      return;
    }
    const result = await runMemoryJob(jobId);
    setBusy(false);
    onChanged(result.ok ? `Governed ${jobKind} job completed through the Compute ledger.` : result.payload.errors?.[0]);
  }

  async function exportArchive() {
    if (recovery.length < 12) {
      onChanged("Portable archive recovery material must be at least 12 characters.");
      return;
    }
    if (["selected_project", "selected_space"].includes(archiveScope) && !archiveAuthorityId.trim()) {
      onChanged("Selected Project/Shared Space export requires its exact stable authority ID.");
      return;
    }
    setBusy(true);
    const result = await exportMemoryArchive(
      recovery,
      "portable_export",
      archiveScope,
      archiveAuthorityId.trim() || null
    );
    setBusy(false);
    const archive = result.payload.data?.archive as Record<string, any> | undefined;
    if (!result.ok || !archive?.archive_base64) {
      onChanged(result.payload.errors?.[0] ?? "Portable archive export failed.");
      return;
    }
    const raw = window.atob(String(archive.archive_base64));
    const bytes = new Uint8Array(raw.length);
    for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.elysia.memory-archive" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${archive.archive_id}.elysia-memory-archive`;
    anchor.click();
    URL.revokeObjectURL(url);
    setRecovery("");
    onChanged(`Encrypted portable archive created with ${archive.record_count} records. Keep its recovery material separately.`);
  }

  async function previewRestore() {
    if (!restoreBase64 || recovery.length < 12) return;
    setBusy(true);
    const result = await previewMemoryArchiveRestore(restoreBase64, recovery);
    setBusy(false);
    const preview = result.payload.data?.restore as Record<string, any> | undefined;
    setRestorePlan(result.ok && preview ? preview : null);
    onChanged(result.ok && preview ? `Restore preview ready: ${JSON.stringify(preview.plan)}` : result.payload.errors?.[0]);
  }

  async function applyRestore() {
    if (!restorePlan) return;
    setBusy(true);
    const result = await applyMemoryArchiveRestore(
      String(restorePlan.restore_plan_id),
      String(restorePlan.approval_id),
      String(restorePlan.approval_token),
      recovery
    );
    setBusy(false);
    setRestorePlan(null);
    if (result.ok) {
      setRecovery("");
      setRestoreBase64("");
    }
    onChanged(result.ok ? "Archive restored atomically; derived projections were rebuilt and verified." : result.payload.errors?.[0]);
  }

  const homeostasis = truth.homeostasis ?? {};
  const jobs = Array.isArray(truth.jobs) ? truth.jobs : [];
  const prospective = truth.prospective ?? {};
  return (
    <section style={{ display: "grid", gap: "0.75rem", padding: "1rem", borderRadius: "18px", border: `1px solid ${palette.lineBronze}`, background: "rgba(18, 25, 37, 0.72)" }}>
      <div><strong style={{ color: palette.teal }}>Memory stewardship</strong><div style={{ color: palette.silverMuted }}>Real tiers, form behavior, governed maintenance, encrypted portability, and bounded graph/provenance inspection.</div></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: "0.55rem" }}>
        <input aria-label="Memory ID for stewardship" value={memoryId} onChange={(event) => setMemoryId(event.target.value)} placeholder="Exact memory ID" style={foundationInputStyle} />
        <select aria-label="Memory lifecycle tier" value={tier} onChange={(event) => setTier(event.target.value as typeof tier)} style={foundationInputStyle}>{["working", "hot", "warm", "cold", "archived"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
        <button type="button" disabled={busy || !memoryId.trim()} onClick={() => void applyTier()} style={foundationButtonStyle}>Move tier</button>
        <button type="button" disabled={!memoryId.trim()} onClick={() => void setMemoryAutomaticRecall(memoryId.trim(), true, "Operator suppressed automatic recall.").then((result) => onChanged(result.ok ? "Automatic recall suppressed; explicit lookup remains available." : result.payload.errors?.[0]))} style={foundationButtonStyle}>Suppress auto-recall</button>
        <button type="button" disabled={!memoryId.trim()} onClick={() => void setMemoryAutomaticRecall(memoryId.trim(), false, "Operator restored automatic recall.").then((result) => onChanged(result.ok ? "Automatic recall restored under authorization policy." : result.payload.errors?.[0]))} style={foundationButtonStyle}>Restore auto-recall</button>
        <button type="button" disabled={!memoryId.trim()} onClick={() => void inspect("history")} style={foundationButtonStyle}>Tier timeline</button>
        <button type="button" disabled={!memoryId.trim()} onClick={() => void inspect("graph")} style={foundationButtonStyle}>Relationships</button>
        <button type="button" disabled={!memoryId.trim()} onClick={() => void inspect("belief")} style={foundationButtonStyle}>Why believed?</button>
        <button type="button" disabled={!memoryId.trim()} onClick={() => void relateMemory()} style={foundationButtonStyle}>Add relationship</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: "0.55rem" }}>
        <select aria-label="Memory form action" value={formAction} onChange={(event) => setFormAction(event.target.value)} style={foundationInputStyle}>{["complete", "reopen", "dismiss", "snooze", "record_outcome", "verify_procedure", "invalidate_procedure"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
        <input aria-label="Form action due time or outcome" value={formValue} onChange={(event) => setFormValue(event.target.value)} placeholder="Due time or outcome when required" style={foundationInputStyle} />
        <button type="button" disabled={!memoryId.trim()} onClick={() => void applyFormBehavior()} style={foundationButtonStyle}>Apply form behavior</button>
        <select aria-label="Memory maintenance job" value={jobKind} onChange={(event) => setJobKind(event.target.value)} style={foundationInputStyle}>{["conversation_compaction", "semantic_candidates", "duplicate_detection", "relation_candidates", "contradiction_scan", "project_summary_refresh", "tier_maintenance", "archive_compression", "fts_rebuild", "embedding_rebuild", "graph_rebuild", "object_integrity", "projection_rebuild", "homeostasis", "managed_backup", "integrity_check", "metacognitive_statistics", "consolidation", "replay_validation"].map((value) => <option key={value} value={value}>{value}</option>)}</select>
        <button type="button" disabled={busy} onClick={() => void startJob()} style={foundationButtonStyle}>Run governed job</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: "0.55rem" }}>
        <input aria-label="Portable archive recovery material" type="password" value={recovery} onChange={(event) => setRecovery(event.target.value)} placeholder="User-controlled archive recovery material" style={foundationInputStyle} />
        <select aria-label="Portable archive scope" value={archiveScope} onChange={(event) => setArchiveScope(event.target.value as typeof archiveScope)} style={foundationInputStyle}><option value="full_account">Full account</option><option value="selected_project">Selected Project</option><option value="selected_space">Selected Shared Space</option><option value="metadata_audit">Metadata/audit only</option></select>
        {archiveScope === "selected_project" || archiveScope === "selected_space" ? <input aria-label="Archive selected authority ID" value={archiveAuthorityId} onChange={(event) => setArchiveAuthorityId(event.target.value)} placeholder="Exact Project or Shared Space ID" style={foundationInputStyle} /> : null}
        <button type="button" disabled={busy} onClick={() => void exportArchive()} style={foundationButtonStyle}>Export encrypted portable archive</button>
        <label style={{ ...foundationButtonStyle, display: "grid", gap: "0.25rem" }}>Select archive to restore<input aria-label="Select Elysia Memory Archive" type="file" accept=".elysia-memory-archive,application/vnd.elysia.memory-archive" onChange={(event) => { const file = event.target.files?.[0]; if (file) void file.arrayBuffer().then((buffer) => setRestoreBase64(bytesToBase64(new Uint8Array(buffer)))); }} /></label>
        <button type="button" disabled={busy || !restoreBase64} onClick={() => void previewRestore()} style={foundationButtonStyle}>Validate and preview restore</button>
        <button type="button" disabled={busy || !restorePlan || Number(restorePlan?.plan?.conflicts ?? 0) > 0} onClick={() => void applyRestore()} style={foundationButtonStyle}>Apply exact restore plan</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: "0.55rem", color: palette.silverMuted }}>
        <div>Storage: {String(homeostasis.state ?? "unknown")}<br />Tier counts: {JSON.stringify(homeostasis.tier_counts ?? {})}</div>
        <div>Objects: {String(homeostasis.objects?.object_count ?? 0)}<br />Silent hard delete: never</div>
        <div>Maintenance jobs: {jobs.length}<br />Active state is shown here, not in Settings.</div>
        <div>Prospective due: {String(prospective.due_count ?? 0)}<br />Sealed reminders remain outside ordinary notifications.</div>
        <div>Restore: {restorePlan ? `previewed · ${restorePlan.plan_hash}` : "no pending plan"}<br />Offline export copies remain user-controlled.</div>
      </div>
    </section>
  );
}

function PageHeader({
  eyebrow,
  title,
  detail
}: {
  eyebrow: string;
  title: string;
  detail: string;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: "0.76rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: palette.sandstone,
          marginBottom: "0.4rem"
        }}
      >
        {eyebrow}
      </div>
      <h1
        style={{
          margin: 0,
          fontSize: "2.15rem",
          lineHeight: 1.1
        }}
      >
        {title}
      </h1>
      <div
        style={{
          marginTop: "0.7rem",
          color: palette.silverMuted,
          lineHeight: 1.65,
          maxWidth: "78ch"
        }}
      >
        {detail}
      </div>
    </div>
  );
}

function SummaryCard({
  title,
  body,
  tone
}: {
  title: string;
  body: string;
  tone: string;
}) {
  return (
    <div
      style={{
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(24, 33, 48, 0.66) 0%, rgba(18, 25, 37, 0.74) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.55rem",
          marginBottom: "0.55rem"
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: "0.7rem",
            height: "0.7rem",
            borderRadius: "999px",
            background: tone,
            boxShadow: `0 0 14px ${tone}`
          }}
        />
        <strong style={{ fontSize: "0.98rem" }}>{title}</strong>
      </div>
      <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
        {body}
      </div>
    </div>
  );
}

function mapMemoryItemForCard(item: MemoryItemSummary): MemoryItemCardData {
  const sourceLabel =
    item.source_label ??
    item.provenance?.source_label ??
    item.source_ref ??
    item.provenance?.source_ref ??
    "Unknown source";

  return {
    memoryId: item.memory_id,
    title: item.title ?? "Untitled memory",
    bodyExcerpt:
      item.body_excerpt ??
      item.summary ??
      "No memory body excerpt was provided by the backend.",
    whyStored:
      item.why_stored ??
      "No storage rationale was provided by the backend.",
    memoryClass: coerceMemoryClass(item.memory_class),
    sensitivity: coerceSensitivity(item.sensitivity),
    mutability: coerceMutability(item.mutability),
    status: coerceStatus(item.status ?? item.state),
    sourceLabel,
    sourceKind: item.source_type ?? item.provenance?.source_kind ?? undefined,
    createdAtLabel: item.created_at_utc
      ? formatDateTimeLabel(item.created_at_utc)
      : undefined,
    updatedAtLabel: item.updated_at_utc
      ? formatDateTimeLabel(item.updated_at_utc)
      : "Unknown",
    projectLabel: item.context_links?.project_id ?? undefined,
    conversationLabel: item.context_links?.conversation_id ?? undefined,
    flags: {
      pinned: item.is_pinned === true || item.flags?.pinned === true,
      userDeclared: item.flags?.user_declared === true,
      inferred: item.flags?.inferred === true,
      verified: item.flags?.verified === true,
      stale: item.flags?.stale === true
    }
  };
}

function coerceMemoryClass(value: string | null | undefined): MemoryItemCardData["memoryClass"] {
  return allowedMemoryClasses.has(value as MemoryItemCardData["memoryClass"])
    ? (value as MemoryItemCardData["memoryClass"])
    : "working";
}

function coerceSensitivity(value: string | null | undefined): MemoryItemCardData["sensitivity"] {
  return allowedSensitivities.has(value as MemoryItemCardData["sensitivity"])
    ? (value as MemoryItemCardData["sensitivity"])
    : "internal";
}

function coerceMutability(value: string | null | undefined): MemoryItemCardData["mutability"] {
  return allowedMutabilities.has(value as MemoryItemCardData["mutability"])
    ? (value as MemoryItemCardData["mutability"])
    : "not_yet_live";
}

function coerceStatus(value: string | null | undefined): MemoryItemCardData["status"] {
  if (value === "candidate" || value === "working") {
    return "provisional";
  }
  return allowedStatuses.has(value as MemoryItemCardData["status"])
    ? (value as MemoryItemCardData["status"])
    : "active";
}

function formatDateTimeLabel(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

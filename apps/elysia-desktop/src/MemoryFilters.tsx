export type MemoryFilterClass =
  | ""
  | "working"
  | "conversation"
  | "project"
  | "research"
  | "operational"
  | "preference"
  | "sealed_private"
  | "audit";

export type MemoryFilterSensitivity =
  | ""
  | "public"
  | "internal"
  | "private"
  | "sealed";

export type MemoryFilterMutability =
  | ""
  | "live_editable"
  | "append_only"
  | "review_required"
  | "immutable"
  | "not_yet_live";

export type MemoryFilterStatus =
  | ""
  | "active"
  | "provisional"
  | "archived"
  | "superseded"
  | "blocked";

export type MemoryFilterScope =
  | ""
  | "user"
  | "conversation"
  | "project"
  | "research"
  | "operational"
  | "system"
  | "shared_space";

export type MemoryFilterForm =
  | ""
  | "episodic"
  | "semantic"
  | "procedural"
  | "prospective"
  | "relational"
  | "predictive"
  | "corrective"
  | "metacognitive"
  | "audit";

export type MemoryFilterTier = "" | "working" | "hot" | "warm" | "cold" | "archived";

export type MemoryFilterState = {
  searchQuery: string;
  memoryClass: MemoryFilterClass;
  sensitivity: MemoryFilterSensitivity;
  mutability: MemoryFilterMutability;
  status: MemoryFilterStatus;
  scope: MemoryFilterScope;
  form: MemoryFilterForm;
  tier: MemoryFilterTier;
};

export const DEFAULT_MEMORY_FILTERS: MemoryFilterState = {
  searchQuery: "",
  memoryClass: "",
  sensitivity: "",
  mutability: "",
  status: "",
  scope: "",
  form: ""
  ,tier: ""
};

type MemoryFiltersProps = {
  filters: MemoryFilterState;
  onFiltersChange: (next: MemoryFilterState) => void;
  disabled?: boolean;
  isLoading?: boolean;
  onClearFilters?: () => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  glowTeal: "rgba(126, 215, 209, 0.14)"
} as const;

const classOptions: Array<{ value: MemoryFilterClass; label: string }> = [
  { value: "", label: "All classes" },
  { value: "working", label: "Working" },
  { value: "conversation", label: "Conversation" },
  { value: "project", label: "Project" },
  { value: "research", label: "Research" },
  { value: "operational", label: "Operational" },
  { value: "preference", label: "Preference" },
  { value: "sealed_private", label: "Sealed private" },
  { value: "audit", label: "Audit" }
];

const sensitivityOptions: Array<{
  value: MemoryFilterSensitivity;
  label: string;
}> = [
  { value: "", label: "All sensitivities" },
  { value: "public", label: "Public" },
  { value: "internal", label: "Internal" },
  { value: "private", label: "Private" },
  { value: "sealed", label: "Sealed" }
];

const mutabilityOptions: Array<{
  value: MemoryFilterMutability;
  label: string;
}> = [
  { value: "", label: "All mutability" },
  { value: "live_editable", label: "Live editable" },
  { value: "append_only", label: "Append only" },
  { value: "review_required", label: "Review required" },
  { value: "immutable", label: "Immutable" },
  { value: "not_yet_live", label: "Not yet live" }
];

const statusOptions: Array<{ value: MemoryFilterStatus; label: string }> = [
  { value: "", label: "All status" },
  { value: "active", label: "Active" },
  { value: "provisional", label: "Provisional" },
  { value: "archived", label: "Archived" },
  { value: "superseded", label: "Superseded" },
  { value: "blocked", label: "Blocked" }
];

const scopeOptions: Array<{ value: MemoryFilterScope; label: string }> = [
  { value: "", label: "All scopes" },
  { value: "user", label: "User" },
  { value: "conversation", label: "Conversation" },
  { value: "project", label: "Project" },
  { value: "research", label: "Research" },
  { value: "operational", label: "Operational" },
  { value: "system", label: "System" },
  { value: "shared_space", label: "Shared space" }
];

const formOptions: Array<{ value: MemoryFilterForm; label: string }> = [
  { value: "", label: "All forms" },
  { value: "episodic", label: "Episodic" },
  { value: "semantic", label: "Semantic" },
  { value: "procedural", label: "Procedural" },
  { value: "prospective", label: "Prospective" },
  { value: "relational", label: "Relational" },
  { value: "predictive", label: "Predictive" },
  { value: "corrective", label: "Corrective" },
  { value: "metacognitive", label: "Metacognitive" },
  { value: "audit", label: "Audit" }
];

function getActiveFilterCount(filters: MemoryFilterState): number {
  let count = 0;

  if (filters.searchQuery.trim()) count += 1;
  if (filters.memoryClass) count += 1;
  if (filters.sensitivity) count += 1;
  if (filters.mutability) count += 1;
  if (filters.status) count += 1;
  if (filters.scope) count += 1;
  if (filters.form) count += 1;
  if (filters.tier) count += 1;

  return count;
}

export default function MemoryFilters({
  filters,
  onFiltersChange,
  disabled = false,
  isLoading = false,
  onClearFilters
}: MemoryFiltersProps) {
  const activeFilterCount = getActiveFilterCount(filters);

  function updateFilter<K extends keyof MemoryFilterState>(
    key: K,
    value: MemoryFilterState[K]
  ) {
    onFiltersChange({
      ...filters,
      [key]: value
    });
  }

  function handleClearFilters() {
    if (onClearFilters) {
      onClearFilters();
      return;
    }

    onFiltersChange(DEFAULT_MEMORY_FILTERS);
  }

  const controlDisabled = disabled || isLoading;

  return (
    <section
      style={{
        display: "grid",
        gap: "0.9rem",
        padding: "1rem",
        borderRadius: "18px",
        border: `1px solid ${palette.lineSilver}`,
        background:
          "linear-gradient(180deg, rgba(18, 25, 37, 0.78) 0%, rgba(11, 14, 18, 0.82) 100%)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)"
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "1rem",
          flexWrap: "wrap"
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: "0.82rem",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: palette.teal,
              marginBottom: "0.35rem"
            }}
          >
            Filters
          </div>
          <div
            style={{
              color: palette.silverMuted,
              lineHeight: 1.55,
              maxWidth: "68ch"
            }}
          >
            Narrow the visible memory slice by canonical scope, form, privacy,
            lifecycle, and the established compatibility labels.
          </div>
        </div>

        <button
          type="button"
          onClick={handleClearFilters}
          disabled={controlDisabled || activeFilterCount === 0}
          style={{
            alignSelf: "center",
            padding: "0.72rem 0.95rem",
            borderRadius: "12px",
            border: `1px solid ${
              controlDisabled || activeFilterCount === 0
                ? "rgba(199, 210, 218, 0.08)"
                : palette.lineBronze
            }`,
            background:
              controlDisabled || activeFilterCount === 0
                ? "rgba(24, 33, 48, 0.34)"
                : "linear-gradient(180deg, rgba(43, 31, 21, 0.42) 0%, rgba(24, 33, 48, 0.52) 100%)",
            color:
              controlDisabled || activeFilterCount === 0
                ? palette.silverMuted
                : palette.silver,
            cursor:
              controlDisabled || activeFilterCount === 0
                ? "not-allowed"
                : "pointer",
            opacity: controlDisabled || activeFilterCount === 0 ? 0.72 : 1
          }}
        >
          Clear filters
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: "0.85rem"
        }}
      >
        <label style={{ display: "grid", gap: "0.35rem", minWidth: 0 }}>
          <span
            style={{
              fontSize: "0.76rem",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: palette.sandstone
            }}
          >
            Search
          </span>
          <input
            type="text"
            value={filters.searchQuery}
            onChange={(event) => updateFilter("searchQuery", event.target.value)}
            placeholder="Search memory..."
            disabled={controlDisabled}
            style={{
              width: "100%",
              minWidth: 0,
              boxSizing: "border-box",
              padding: "0.78rem 0.9rem",
              borderRadius: "12px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(11, 14, 18, 0.48)",
              color: palette.silver,
              outline: "none",
              boxShadow: "none"
            }}
          />
        </label>

        <FilterSelect
          label="Scope"
          value={filters.scope}
          onChange={(value) => updateFilter("scope", value as MemoryFilterScope)}
          options={scopeOptions}
          disabled={controlDisabled}
        />

        <FilterSelect
          label="Form"
          value={filters.form}
          onChange={(value) => updateFilter("form", value as MemoryFilterForm)}
          options={formOptions}
          disabled={controlDisabled}
        />

        <FilterSelect
          label="Tier"
          value={filters.tier}
          onChange={(value) => updateFilter("tier", value as MemoryFilterTier)}
          options={[{ value: "", label: "All tiers" }, { value: "working", label: "Working" }, { value: "hot", label: "Hot" }, { value: "warm", label: "Warm" }, { value: "cold", label: "Cold" }, { value: "archived", label: "Archived" }]}
          disabled={controlDisabled}
        />

        <FilterSelect
          label="Class"
          value={filters.memoryClass}
          onChange={(value) =>
            updateFilter("memoryClass", value as MemoryFilterClass)
          }
          options={classOptions}
          disabled={controlDisabled}
        />

        <FilterSelect
          label="Sensitivity"
          value={filters.sensitivity}
          onChange={(value) =>
            updateFilter("sensitivity", value as MemoryFilterSensitivity)
          }
          options={sensitivityOptions}
          disabled={controlDisabled}
        />

        <FilterSelect
          label="Mutability"
          value={filters.mutability}
          onChange={(value) =>
            updateFilter("mutability", value as MemoryFilterMutability)
          }
          options={mutabilityOptions}
          disabled={controlDisabled}
        />

        <FilterSelect
          label="Status"
          value={filters.status}
          onChange={(value) =>
            updateFilter("status", value as MemoryFilterStatus)
          }
          options={statusOptions}
          disabled={controlDisabled}
        />
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "0.8rem",
          flexWrap: "wrap",
          paddingTop: "0.15rem"
        }}
      >
        <div
          style={{
            color: palette.silverMuted,
            fontSize: "0.88rem",
            lineHeight: 1.5
          }}
        >
          {activeFilterCount === 0
            ? "Showing all available memory."
            : `${activeFilterCount} filter${activeFilterCount === 1 ? "" : "s"} active.`}
        </div>

        <div
          style={{
            color: palette.silverMuted,
            fontSize: "0.82rem",
            lineHeight: 1.45
          }}
        >
          {isLoading
            ? "Updating visible memory slice..."
            : disabled
              ? "Filtering is temporarily unavailable."
              : "Filters are room-controlled and ready for list wiring."}
        </div>
      </div>
    </section>
  );
}

type FilterSelectProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  disabled: boolean;
};

function FilterSelect({
  label,
  value,
  onChange,
  options,
  disabled
}: FilterSelectProps) {
  return (
    <label style={{ display: "grid", gap: "0.35rem", minWidth: 0 }}>
      <span
        style={{
          fontSize: "0.76rem",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: palette.sandstone
        }}
      >
        {label}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        style={{
          width: "100%",
          minWidth: 0,
          boxSizing: "border-box",
          padding: "0.78rem 0.9rem",
          borderRadius: "12px",
          border: `1px solid ${palette.lineSilver}`,
          background: "rgba(11, 14, 18, 0.48)",
          color: palette.silver,
          outline: "none",
          boxShadow: "none",
          cursor: disabled ? "not-allowed" : "pointer"
        }}
      >
        {options.map((option) => (
          <option key={`${label}-${option.value || "all"}`} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

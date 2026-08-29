import { invoke } from "@tauri-apps/api/core";

export type BridgeStartupState =
  | "checking"
  | "ok"
  | "degraded"
  | "unavailable"
  | "error";

export type BridgeEnvelope<TData = Record<string, unknown>> = {
  status?: string;
  request_id?: string;
  result_type?: string;
  api_version?: string;
  contract_version?: string;
  capability_state?: string;
  approval_state?: string;
  boundary_state?: string;
  locality?: string;
  locality_state?: string;
  fallback_state?: string;
  timestamp_utc?: string;
  errors?: string[];
  warnings?: string[];
  message?: string;
  data?: TData;
};

export type HealthSubsystemEntry = {
  state?: string | null;
  healthy?: boolean | null;
  note?: string | null;
};

export type HealthSubsystems = {
  api?: HealthSubsystemEntry | null;
  runtime?: HealthSubsystemEntry | null;
  ollama?: HealthSubsystemEntry | null;
  searxng?: HealthSubsystemEntry | null;
  config?: HealthSubsystemEntry | null;
  logging?: HealthSubsystemEntry | null;
  journaling?: HealthSubsystemEntry | null;
  memory?: HealthSubsystemEntry | null;
  [key: string]: HealthSubsystemEntry | null | undefined;
};

export type BridgeHealthEnvelope = BridgeEnvelope<{
  health_state?: string | null;
  healthy?: boolean | null;
  startup_state?: string | null;
  api_reachable?: boolean | null;
  runtime_reachable?: boolean | null;
  ollama_reachable?: boolean | null;
  searxng_reachable?: boolean | null;
  config_loadable?: boolean | null;
  logging_writable?: boolean | null;
  journaling_writable?: boolean | null;
  memory_path_available?: boolean | null;
  last_health_check_utc?: string | null;
  health_notes?: string[];
  subsystems?: HealthSubsystems | null;
}>;

export type RuntimeStatusEnvelope = BridgeEnvelope<{
  runtime_state?: string;
  runtime_available?: boolean;
  active_mode?: string;
  selected_role?: string;
  selected_runtime?: string;
  selected_model_runtime_tag?: string;
  stayed_local?: boolean;
  used_fallback?: boolean;
  fallback_from?: string;
  fallback_to?: string;
  approval_needed?: boolean;
  last_request_id?: string;
  last_invocation_status?: string;
  last_updated_utc?: string;
}>;

export type InvokerStatusEnvelope = BridgeEnvelope<{
  invoker_state?: string;
  invoker_available?: boolean;
  selected_role?: string;
  selected_runtime?: string;
  selected_model_runtime_tag?: string;
  stayed_local?: boolean;
  used_fallback?: boolean;
  fallback_from?: string;
  fallback_to?: string;
  approval_needed?: boolean;
  last_request_id?: string;
  last_invocation_status?: string;
  last_error?: string;
  last_updated_utc?: string;
}>;

export type CapabilityManifestEnvelope = BridgeEnvelope<Record<string, unknown>>;

export type CognitionStatusEnvelope = BridgeEnvelope<{
  governor_contract?: string;
  reasoning_gears?: string[];
  autonomy_levels?: Record<string, string>;
  effective_controls?: Record<string, unknown>;
  model_registry?: Record<string, any>;
  compute?: Record<string, any>;
  active_gpu_leases?: Array<Record<string, unknown>>;
  emergency?: Record<string, unknown>;
  private_content_included?: boolean;
}>;

export type InstallDependencyStatus =
  | "present"
  | "missing"
  | "optional_missing"
  | "blocked"
  | "degraded"
  | "unknown"
  | "profile_gated"
  | "lab_gated"
  | "not_applicable";

export type InstallProfileSummary = {
  profile_id: string;
  display_name: string;
  selected?: boolean;
  included?: boolean;
  default_enabled?: boolean;
  maturity?: string;
  risk_level?: string;
  readiness?: string;
  dependency_count?: number;
  required_missing_count?: number;
  required_unknown_count?: number;
  optional_missing_count?: number;
  network_runtime_default?: string;
  large_downloads_may_occur?: boolean;
  private_data_leaves_machine_by_default?: boolean;
  doctor_checks?: string[];
};

export type InstallDependencySummary = {
  dependency_id: string;
  label: string;
  profile_id: string;
  category: string;
  required?: boolean;
  status?: InstallDependencyStatus;
  activation_state?: string;
  check_method?: string;
  version?: string | null;
  warning?: string | null;
  external_download_required?: boolean;
  private_data_may_be_involved?: boolean;
  allowed_in_core?: boolean;
};

export type InstallWorkerSummary = {
  worker_id: string;
  label: string;
  profile_id: string;
  status?: InstallDependencyStatus;
  configured?: boolean;
  enabled?: boolean;
  doctor_proof_required?: boolean;
  note?: string;
};

export type InstallProfileStatusEnvelope = BridgeEnvelope<{
  resolution_state?: string;
  active_profile_id?: string;
  active_profile_label?: string;
  selected_profile_ids?: string[];
  resolved_profile_ids?: string[];
  available_profiles?: InstallProfileSummary[];
  dependencies?: InstallDependencySummary[];
  dependency_summary?: Record<string, number>;
  missing_core_dependency_ids?: string[];
  resolved_capability_groups?: string[];
  capability_tiers?: Record<string, string[]>;
  local_overrides?: {
    state?: string;
    selection_source?: string;
    model_override_source?: string;
    configured_labels?: string[];
    configured_count?: number;
    raw_values_exposed?: boolean;
    authority_granted?: boolean;
    warning?: string | null;
  };
  provider_summary?: {
    provider_id?: string;
    command_status?: InstallDependencyStatus;
    configured_role_ids?: string[];
    local_override_loaded?: boolean;
    network_check_performed?: boolean;
    model_loaded?: boolean;
    selection_authority_available?: boolean;
    note?: string;
  };
  worker_summaries?: InstallWorkerSummary[];
  profile_selection_grants_approval?: boolean;
  install_authority_available?: boolean;
  download_authority_available?: boolean;
  worker_start_authority_available?: boolean;
  doctor_executed?: boolean;
  generated_at_utc?: string;
}>;

export type InstallDoctorCheck = {
  check_id: string;
  label: string;
  category: string;
  status: InstallDependencyStatus;
  classification: "ready" | "degraded" | "blocked" | "missing" | "not_selected";
  required: boolean;
  summary: string;
  remediation?: string | null;
};

export type InstallDoctorStatusEnvelope = BridgeEnvelope<{
  doctor_version?: string;
  overall_status?: InstallDependencyStatus;
  runtime_mode?: string;
  active_profile_id?: string;
  checks?: InstallDoctorCheck[];
  status_counts?: Record<string, number>;
  core_ready?: boolean;
  optional_profiles_ready?: boolean;
  local_api_reachable?: boolean;
  local_auth?: {
    required_for_mutations?: boolean;
    initialized?: boolean;
    storage?: string;
    credential_exposed?: boolean;
    source?: string;
  };
  path_contract?: {
    runtime_mode?: string;
    config?: string;
    data?: string;
    cache?: string;
    state?: string;
    runtime?: string;
    raw_paths_exposed?: boolean;
    source_tree_runtime_state?: boolean;
  };
  first_run?: {
    state?: string;
    required_directories_ready?: boolean;
    authentication_ready?: boolean;
    doctor_run_recorded?: boolean;
    raw_paths_exposed?: boolean;
  };
  desktop_api_compatible?: boolean;
  worker_execution_enabled?: boolean;
  install_authority_available?: boolean;
  repair_authority_available?: boolean;
  raw_paths_exposed?: boolean;
  generated_at_utc?: string;
}>;

export type GovernanceControlState =
  | "live_editable"
  | "display_only"
  | "inactive"
  | "planned";

export type GovernanceMutationClassification =
  | "safe-live-editable-now"
  | "plan-only"
  | "read-only-constitutional"
  | "profile-gated-later"
  | "lab-gated-later"
  | "hard-prohibited-by-default";

export type GovernanceMutationRisk = "low" | "moderate" | "high" | "critical";

export type GovernanceSourceKind =
  | "config_file"
  | "policy_file"
  | "runtime_state"
  | "bridge_constant"
  | "service_summary"
  | "route_surface"
  | "derived_summary"
  | "planned_surface";

export type GovernanceAuthorityLevel =
  | "canonical"
  | "authoritative"
  | "derived"
  | "informative";

export type TrustZoneAccessState =
  | "open"
  | "bounded"
  | "review_required"
  | "sealed"
  | "planned";

export type GovernanceControlSource = {
  kind: GovernanceSourceKind;
  label: string;
  path?: string | null;
  authority_level?: GovernanceAuthorityLevel;
  note?: string | null;
};

export type GovernanceControl = {
  control_id: string;
  label: string;
  value?: string | boolean | number | null;
  detail?: string | null;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  category?: string | null;
  authority_note?: string | null;
  mutation_classification?: GovernanceMutationClassification;
  mutation_risk?: GovernanceMutationRisk;
  mutation_allowed?: boolean;
  approval_required?: boolean;
  mutation_reason?: string | null;
  mutation_later_gate?: string | null;
};

export type TrustZoneSummary = {
  zone_id: string;
  label: string;
  description?: string | null;
  access_state: TrustZoneAccessState;
  assistant_can_read?: boolean;
  assistant_can_write?: boolean;
  user_can_read?: boolean;
  user_can_write?: boolean;
  sealed?: boolean;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  detail?: string | null;
};

export type LocalityGovernanceSummary = {
  local_only_by_default?: boolean | null;
  outbound_networking_posture?: string | null;
  crossed_boundary_default?: string | null;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  controls?: GovernanceControl[];
  detail?: string | null;
};

export type RoleAuthorityEntry = {
  role_key: string;
  label: string;
  preferred_model?: string | null;
  fallback_models?: string[];
  runtime?: string | null;
  local_only?: boolean | null;
  enabled_by_default?: boolean | null;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  detail?: string | null;
};

export type RoleAuthoritySummary = {
  authority_label?: string | null;
  default_role?: string | null;
  roles?: RoleAuthorityEntry[];
  controls?: GovernanceControl[];
  detail?: string | null;
};

export type RoutingPolicySummary = {
  routing_mode?: string | null;
  local_first?: boolean | null;
  silent_cloud_fallback_allowed?: boolean | null;
  sensitive_work_must_remain_local?: boolean | null;
  selected_default_role?: string | null;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  controls?: GovernanceControl[];
  detail?: string | null;
};

export type MemoryGovernanceSummary = {
  autonomous_updates_enabled?: boolean | null;
  review_required_for_sensitive_mutations?: boolean | null;
  known_memory_classes?: string[];
  sealed_memory_posture?: string | null;
  retention_posture?: string | null;
  promotion_posture?: string | null;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  controls?: GovernanceControl[];
  detail?: string | null;
};

export type ApprovalGovernanceSummary = {
  approval_mode?: string | null;
  risky_actions_require_approval?: boolean | null;
  destructive_actions_require_approval?: boolean | null;
  outbound_actions_allowed?: boolean | null;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  controls?: GovernanceControl[];
  detail?: string | null;
};

export type JournalingGovernanceSummary = {
  journaling_enabled?: boolean | null;
  journal_mode?: string | null;
  request_trace_enabled?: boolean | null;
  audit_append_only?: boolean | null;
  state: GovernanceControlState;
  source: GovernanceControlSource;
  controls?: GovernanceControl[];
  detail?: string | null;
};

export type GovernanceStateData = {
  locality_summary?: LocalityGovernanceSummary | null;
  trust_zones?: TrustZoneSummary[];
  role_authority?: RoleAuthoritySummary | null;
  routing_summary?: RoutingPolicySummary | null;
  memory_summary?: MemoryGovernanceSummary | null;
  approval_summary?: ApprovalGovernanceSummary | null;
  journaling_summary?: JournalingGovernanceSummary | null;
  control_states?: GovernanceControl[];
  control_sources?: GovernanceControlSource[];
  generated_at_utc?: string | null;
  governance_note?: string | null;
  governance_config_hash?: string | null;
  mutation_contract_version?: string | null;
  mutation_summary?: Partial<Record<GovernanceMutationClassification, number>>;
};

export type GovernanceStateEnvelope = BridgeEnvelope<GovernanceStateData>;

export type GovernanceMutationReceipt = {
  request_id: string;
  operation_id: string;
  action: "plan" | "apply" | "restore";
  outcome: "planned" | "applied" | "restored" | "blocked" | "expired" | "stale" | "tampered";
  control_id: string;
  classification: GovernanceMutationClassification;
  risk: GovernanceMutationRisk;
  recorded_at_utc: string;
  config_hash_before?: string | null;
  config_hash_after?: string | null;
  plan_hash?: string | null;
  approval_id?: string | null;
  reason_code?: string | null;
  sanitized: boolean;
  raw_values_logged: boolean;
  raw_paths_logged: boolean;
};

export type GovernanceChangePlanRequest = {
  control_id: string;
  proposed_value: string | boolean | number | null;
  expected_config_hash: string;
  reason?: string | null;
  ui_surface?: string;
};

export type GovernanceChangeApplyRequest = {
  plan_id: string;
  plan_hash: string;
  expected_config_hash: string;
  approval_id?: string | null;
  approval_token?: string | null;
  confirmed: boolean;
};

export type GovernanceRestoreRequest = {
  restore_id: string;
  restore_plan_hash: string;
  expected_config_hash: string;
  approval_id?: string | null;
  approval_token?: string | null;
  confirmed: boolean;
};

export type GovernanceMutationEnvelope = BridgeEnvelope<Record<string, unknown>>;

export type ApprovalResolveRequest = {
  request_id: string;
  decision: "approved" | "denied" | "cancelled";
  reason?: string | null;
  ui_surface?: string | null;
};

export type ApprovalResolveEnvelope = BridgeEnvelope<Record<string, unknown>>;


export type MemorySummaryClassCount = {
  memory_class?: string | null;
  total_count?: number | null;
  active_count?: number | null;
  archived_count?: number | null;
  provisional_count?: number | null;
  blocked_count?: number | null;
  superseded_count?: number | null;
  pinned_count?: number | null;
};

export type MemorySummaryCount = {
  sensitivity?: string | null;
  mutability?: string | null;
  status?: string | null;
  count?: number | null;
};

export type MemoryInspectionSummary = {
  total_items?: number | null;
  class_summaries?: MemorySummaryClassCount[];
  sensitivity_summaries?: MemorySummaryCount[];
  mutability_summaries?: MemorySummaryCount[];
  status_summaries?: MemorySummaryCount[];
  recent_activity?: Record<string, unknown> | null;
  mutation_posture?: Record<string, unknown> | null;
  generated_at_utc?: string | null;
  scope_counts?: Record<string, number>;
  form_counts?: Record<string, number>;
  privacy_counts?: Record<string, number>;
  status_counts?: Record<string, number>;
  pinned_count?: number | null;
  pending_candidate_count?: number | null;
  canonical_authority?: string | null;
  legacy_writer_active?: boolean | null;
};

export type MemoryStorePosture = {
  source?: string | null;
  retrieval_context_is_memory?: boolean | null;
  attached_files_are_memory?: boolean | null;
  write_actions_live?: boolean | null;
  canonical_writer?: boolean | null;
  legacy_writer_active?: boolean | null;
  note?: string | null;
};

export type MemorySummaryEnvelope = BridgeEnvelope<{
  summary?: MemoryInspectionSummary | null;
  store_posture?: MemoryStorePosture | null;
}>;

export type MemoryItemFlags = {
  pinned?: boolean | null;
  user_declared?: boolean | null;
  inferred?: boolean | null;
  verified?: boolean | null;
  stale?: boolean | null;
};

export type MemoryItemActions = {
  can_pin?: boolean | null;
  can_move?: boolean | null;
  can_edit?: boolean | null;
  can_forget?: boolean | null;
  reason?: string | null;
};

export type MemoryItemProvenance = {
  source_kind?: string | null;
  source_ref?: string | null;
  source_label?: string | null;
  captured_at_utc?: string | null;
};

export type MemoryItemContextLinks = {
  conversation_id?: string | null;
  message_id?: string | null;
  project_id?: string | null;
  request_id?: string | null;
  evidence_id?: string | null;
  artifact_id?: string | null;
  parent_memory_id?: string | null;
};

export type MemoryItemSummary = {
  memory_id: string;
  title?: string | null;
  summary?: string | null;
  body_excerpt?: string | null;
  why_stored?: string | null;
  memory_class?: string | null;
  source_type?: string | null;
  source_label?: string | null;
  source_ref?: string | null;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  provenance?: MemoryItemProvenance | null;
  sensitivity?: string | null;
  mutability?: string | null;
  state?: string | null;
  status?: string | null;
  is_pinned?: boolean | null;
  is_ephemeral?: boolean | null;
  is_promoted?: boolean | null;
  flags?: MemoryItemFlags | null;
  actions?: MemoryItemActions | null;
  context_links?: MemoryItemContextLinks | null;
  owner_user_id?: string | null;
  space_id?: string | null;
  scope?: string | null;
  form?: string | null;
  privacy?: string | null;
  content_state?: string | null;
  current_revision_id?: string | null;
  revision_number?: number | null;
  importance?: number | null;
  confidence?: number | null;
  user_confirmed?: boolean | null;
  inference_kind?: string | null;
  candidate_kind?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  activation_tier?: string | null;
  pinned?: boolean | null;
  egress_allowed?: boolean | null;
  sources?: Array<Record<string, unknown>>;
};

export type MemoryItemsQueryTruth = {
  retrieval_context_is_memory?: boolean | null;
  attached_files_are_memory?: boolean | null;
  sealed_private_excluded?: boolean | null;
  write_actions_live?: boolean | null;
  lexical_projection_used?: boolean | null;
  lexical_projection_version?: string | null;
  ordinary_persistent_semantic_index?: boolean | null;
  semantic_projection_state?: string | null;
  semantic_projection_version?: string | null;
  private_plaintext_persistently_indexed?: boolean | null;
};

export type MemoryItemsEnvelope = BridgeEnvelope<{
  items?: MemoryItemSummary[];
  total?: number | null;
  limit?: number | null;
  offset?: number | null;
  query_truth?: MemoryItemsQueryTruth | null;
}>;

export type FetchMemorySummaryOptions = {
  projectId?: string | null;
  conversationId?: string | null;
};

export type FetchMemoryItemsOptions = FetchMemorySummaryOptions & {
  searchQuery?: string | null;
  memoryClass?: string | null;
  sensitivity?: string | null;
  mutability?: string | null;
  status?: string | null;
  scope?: string | null;
  form?: string | null;
  activationTier?: string | null;
  limit?: number | null;
  offset?: number | null;
};

export type MemoryCreateRequest = {
  title: string;
  body: string;
  why_stored: string;
  scope?: string;
  form?: string;
  privacy?: "normal" | "private" | "sealed";
  status?: string;
  user_confirmed?: boolean;
  inference_kind?: string | null;
  project_id?: string | null;
  conversation_id?: string | null;
  space_id?: string | null;
  source?: Record<string, unknown>;
  form_data?: Record<string, unknown>;
  candidate_kind?: string;
  proposed_wording?: string | null;
  evidence_summary?: string | null;
};

export type MemoryActionEnvelope = BridgeEnvelope<Record<string, any>>;

export type MemoryFoundationalSettings = {
  memory_recording_enabled: boolean;
  storage_resource_profile: "core_local" | "balanced_local" | "minimal_local";
  default_privacy: "normal" | "private" | "sealed";
  candidate_behavior: "review_all" | "review_personal_inference" | "direct_explicit_only";
  autonomy_level: number;
  internet_master_enabled: boolean;
  retrieval_breadth: "focused" | "balanced" | "broad";
  research_initiative: "manual" | "balanced" | "proactive";
  safe_search_level: "strict" | "moderate" | "off";
  preferred_reasoning_gear: "automatic" | "reflex" | "quick" | "standard" | "deep" | "deliberative" | "research_engineering";
  autonomy_domain_overrides: Record<string, number>;
  compute_preference: "automatic" | "cpu" | "gpu";
  model_performance_preference: "balanced" | "quality" | "latency" | "resource";
  background_cognition_enabled: boolean;
  cpu_percent_ceiling: number;
  ram_mb_ceiling: number;
  vram_mb_ceiling: number;
  max_background_jobs: number;
  memory_storage_profile: "efficient" | "balanced" | "deep_memory" | "custom";
  storage_budget_mode: "absolute_mb" | "percent";
  storage_budget_value: number;
  emergency_free_space_reserve_mb: number;
  consolidation_enabled: boolean;
  consolidation_schedule: "manual" | "daily" | "weekly";
  consolidation_resource_percent: number;
  backup_enabled: boolean;
  backup_schedule: "manual" | "daily" | "weekly";
  backup_retention_count: number;
  retention_policy: "conservative" | "balanced" | "compact";
  hot_retention_days: number;
  cold_after_days: number;
  prospective_notifications_enabled: boolean;
};

export type FileProcessingState =
  | "attached"
  | "queued"
  | "detecting_type"
  | "parsing"
  | "indexed"
  | "ready"
  | "failed"
  | "blocked";

export type FileKind =
  | "text"
  | "markdown"
  | "docx"
  | "pdf"
  | "csv"
  | "xlsx"
  | "json"
  | "html"
  | "image"
  | "unknown"
  | "unsupported";

export type FileTrustZone =
  | "user_selected"
  | "project_local"
  | "sandboxed"
  | "external_import"
  | "sealed"
  | "unknown";

export type FileMemoryPosture =
  | "not_memory"
  | "memory_candidate"
  | "promoted_memory"
  | "blocked_from_memory"
  | "unknown";

export type AttachedFile = {
  file_id: string;
  display_name: string;
  original_name?: string | null;
  file_kind?: FileKind | string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  trust_zone?: FileTrustZone | string | null;
  processing_state?: FileProcessingState | string | null;
  memory_posture?: FileMemoryPosture | string | null;
  attached_at_utc?: string | null;
  source_conversation_id?: string | null;
  source_project_id?: string | null;
  user_selected?: boolean | null;
  can_use_as_context?: boolean | null;
  can_promote_to_memory?: boolean | null;
  parser_used?: string | null;
  chunks_created_count?: number | null;
  chunks_used_count?: number | null;
  memory_promotion_allowed?: boolean | null;
  outward_sharing_allowed?: boolean | null;
  blocked_reason?: string | null;
  notes?: string[];
};

export type FileProcessingStep = {
  step_name: string;
  state: FileProcessingState | string;
  started_at_utc?: string | null;
  completed_at_utc?: string | null;
  message?: string | null;
  warnings?: string[];
  errors?: string[];
};

export type FileContextChunkSummary = {
  chunk_id: string;
  file_id: string;
  chunk_index: number;
  heading?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  token_estimate?: number | null;
  excerpt?: string | null;
};

export type FileContextSummary = {
  file_id: string;
  display_name: string;
  file_kind?: FileKind | string | null;
  processing_state?: FileProcessingState | string | null;
  memory_posture?: FileMemoryPosture | string | null;
  usable_as_context?: boolean | null;
  chunk_count?: number | null;
  selected_chunk_count?: number | null;
  chunks?: FileContextChunkSummary[];
  summary_note?: string | null;
  parser_used?: string | null;
  memory_promotion_allowed?: boolean | null;
  outward_sharing_allowed?: boolean | null;
  retrieval_method?: string | null;
  warnings?: string[];
  errors?: string[];
};

export type FileIngestResult = {
  file_id: string;
  processing_state?: FileProcessingState | string | null;
  accepted?: boolean | null;
  blocked?: boolean | null;
  ready?: boolean | null;
  file?: AttachedFile | null;
  steps?: FileProcessingStep[];
  warnings?: string[];
  errors?: string[];
  context_summary?: FileContextSummary | null;
};

export type FileLookupMissingData = {
  file_id?: string | null;
  found?: boolean | null;
};

export type FileAttachRequest = {
  source_path: string;
  conversation_id?: string | null;
  project_id?: string | null;
  max_size_bytes?: number | null;
  chunk_char_limit?: number | null;
};

export type FileIngestEnvelope = BridgeEnvelope<FileIngestResult>;

export type FileStatusEnvelope = BridgeEnvelope<
  FileIngestResult | FileLookupMissingData
>;

export type FileContextSummaryEnvelope = BridgeEnvelope<
  FileContextSummary | FileLookupMissingData
>;

export type CodingFileCapabilities = {
  readable?: boolean;
  writable?: boolean;
  patchable?: boolean;
  creatable?: boolean;
  deletable?: boolean;
  renameable?: boolean;
};

export type CodingFileRiskFlags = {
  secret_sensitive?: boolean;
  generated_sensitive?: boolean;
  lockfile?: boolean;
  executable_sensitive?: boolean;
};

export type CodingFileTypeDescriptor = {
  type_id?: string;
  label?: string;
  category?: string;
  adapter?: string;
  language_id?: string | null;
  capabilities?: CodingFileCapabilities;
  risk_flags?: CodingFileRiskFlags;
  max_preview_bytes?: number;
  max_patch_bytes?: number;
  notes?: string[];
};

export type CodingFileTypeInspection = {
  status?: string;
  relative_path?: string | null;
  descriptor?: CodingFileTypeDescriptor;
  blocked_reason?: string | null;
};

export type CodingFilePreview = {
  status?: string;
  file_label?: string;
  relative_path?: string | null;
  path_hash?: string;
  content_hash?: string | null;
  byte_hash?: string | null;
  language_hint?: string | null;
  file_type_id?: string | null;
  file_type_label?: string | null;
  category?: string | null;
  adapter?: string | null;
  language_id?: string | null;
  encoding?: string | null;
  line_ending?: string | null;
  line_count?: number;
  byte_count?: number;
  parse_status?: string | null;
  parse_summary?: Record<string, unknown>;
  risk_flags?: CodingFileRiskFlags;
  capabilities?: CodingFileCapabilities;
  redactions?: string[];
  source_contents_included?: boolean;
  content_preview?: string | null;
  bytes_returned?: number;
  lines_returned?: number;
  truncated?: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
  secret_scan_findings?: string[];
};

export type CodingFilePathRequest = {
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
};

export type CodingFilePreviewRequest = CodingFilePathRequest & {
  approval_granted: boolean;
  approval_reason?: string | null;
  max_bytes?: number | null;
  max_lines?: number | null;
};

export type CodingFileTypeInspectionEnvelope = BridgeEnvelope<{
  file_type_inspection?: CodingFileTypeInspection | null;
}>;

export type CodingFilePreviewEnvelope = BridgeEnvelope<{
  file_preview?: CodingFilePreview | null;
}>;

export type CodingPatchProposal = {
  status?: string;
  patch_id?: string;
  patch_hash?: string;
  expected_content_hash?: string | null;
  change_summary?: string;
  target_files?: string[];
  allowed_target_files?: string[];
  blocked_target_files?: Array<Record<string, string>>;
  diff_preview?: string | null;
  truncated?: boolean;
  apply_allowed?: boolean;
  approval_required_for_apply?: boolean;
  rollback_note?: string;
  warnings?: string[];
};

export type CodingPatchProposeRequest = {
  session_id?: string | null;
  approval_mode?: string;
  workspace_root: string;
  target_files: string[];
  change_summary: string;
  proposed_diff?: string | null;
};

export type CodingPatchApplyRequest = {
  session_id?: string | null;
  approval_mode?: string;
  workspace_root: string;
  target_file: string;
  proposed_diff: string;
  expected_content_hash: string;
  patch_hash: string;
  operator_approved: boolean;
  approval_phrase?: string | null;
  approval_id: string;
  approval_token: string;
};

export type CodingPatchApplyResult = {
  status?: string;
  target_relative_path?: string | null;
  patch_hash?: string;
  expected_content_hash?: string;
  previous_content_hash?: string | null;
  new_content_hash?: string | null;
  approval_id?: string | null;
  backup_relative_path?: string | null;
  rollback_receipt_id?: string | null;
  mutation_performed?: boolean;
  audit_written?: boolean;
  blocked_reason?: string | null;
  rollback_note?: string;
  warnings?: string[];
};

export type CodingPatchProposalEnvelope = BridgeEnvelope<{
  patch_proposal?: CodingPatchProposal | null;
}>;

export type CodingPatchApplyEnvelope = BridgeEnvelope<{
  patch_apply?: CodingPatchApplyResult | null;
}>;

export type CodingFileOperationPlanRequest = {
  session_id?: string | null;
  approval_mode?: string;
  workspace_root: string;
  operation_kind: string;
  target_path: string;
  destination_path?: string | null;
  content_hash?: string | null;
  summary: string;
  new_text?: string | null;
};

export type CodingFileOperationPlan = {
  status?: string;
  operation_kind?: string;
  target_relative_path?: string | null;
  destination_relative_path?: string | null;
  blocked_reason?: string | null;
  mutation_performed?: boolean;
  approval_required?: boolean;
  source_hash?: string | null;
  plan_hash?: string | null;
  plan_steps?: string[];
  risk_labels?: string[];
  warnings?: string[];
};

export type CodingFileOperationExecuteRequest = CodingFileOperationPlanRequest & {
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  approval_phrase?: string | null;
  expected_content_hash?: string | null;
};

export type CodingFileOperationResult = {
  status?: string;
  operation_kind?: string;
  target_relative_path?: string | null;
  destination_relative_path?: string | null;
  previous_content_hash?: string | null;
  new_content_hash?: string | null;
  backup_relative_path?: string | null;
  rollback_receipt_id?: string | null;
  mutation_performed?: boolean;
  audit_written?: boolean;
  blocked_reason?: string | null;
  rollback_note?: string;
  warnings?: string[];
};

export type CodingFileOperationPlanEnvelope = BridgeEnvelope<{
  file_operation_plan?: CodingFileOperationPlan | null;
}>;

export type CodingFileOperationResultEnvelope = BridgeEnvelope<{
  file_operation_result?: CodingFileOperationResult | null;
}>;

export type CodingDocumentDescriptor = {
  type_id?: string;
  label?: string;
  extension?: string;
  family?: string;
  adapter?: string;
  readable?: boolean;
  extractable?: boolean;
  exportable?: boolean;
  editable?: boolean;
  stable_edit_operations?: string[];
  risk_flags?: Record<string, boolean>;
  notes?: string[];
};

export type CodingDocumentPreview = {
  status?: string;
  file_label?: string;
  relative_path?: string | null;
  path_hash?: string | null;
  blocked_reason?: string | null;
  descriptor?: CodingDocumentDescriptor;
  safety?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  text_preview?: string | null;
  tables?: Array<Record<string, unknown>>;
  outline?: Array<Record<string, unknown>>;
  provenance?: Array<Record<string, unknown>>;
  warnings?: string[];
  redactions?: string[];
  secret_scan_findings?: string[];
};

export type CodingDocumentPathRequest = {
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
  approval_granted?: boolean;
  approval_reason?: string | null;
  max_chars?: number | null;
  max_tables?: number | null;
  max_rows?: number | null;
};

export type CodingDocumentExportPlanRequest = CodingDocumentPathRequest & {
  export_format: "markdown" | "text";
  target_path?: string | null;
};

export type CodingDocumentExportApplyRequest = CodingDocumentExportPlanRequest & {
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  overwrite_existing?: boolean;
  expected_source_hash?: string | null;
};

export type CodingDocumentEditPlanRequest = CodingDocumentPathRequest & {
  operation: string;
  parameters?: Record<string, unknown>;
};

export type CodingDocumentEditApplyRequest = CodingDocumentEditPlanRequest & {
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  expected_source_hash?: string | null;
};

export type CodingDocumentPlan = {
  status?: string;
  action?: string;
  file_label?: string;
  relative_path?: string | null;
  target_relative_path?: string | null;
  blocked_reason?: string | null;
  plan_summary?: string;
  source_hash?: string | null;
  plan_hash?: string | null;
  preview?: string | null;
  operation_details?: Record<string, unknown>;
  warnings?: string[];
  approval_required?: boolean;
};

export type CodingDocumentApplyResult = {
  status?: string;
  action?: string;
  file_label?: string;
  relative_path?: string | null;
  target_relative_path?: string | null;
  blocked_reason?: string | null;
  mutation_performed?: boolean;
  audit_written?: boolean;
  previous_hash?: string | null;
  new_hash?: string | null;
  approval_id?: string | null;
  backup_relative_path?: string | null;
  rollback_receipt_id?: string | null;
  operation_details?: Record<string, unknown>;
  warnings?: string[];
  rollback_note?: string;
};

export type CodingDocumentPreviewEnvelope = BridgeEnvelope<{
  document?: CodingDocumentPreview | null;
}>;

export type CodingDocumentExportPlanEnvelope = BridgeEnvelope<{
  document_export_plan?: CodingDocumentPlan | null;
}>;

export type CodingDocumentExportApplyEnvelope = BridgeEnvelope<{
  document_export_result?: CodingDocumentApplyResult | null;
}>;

export type CodingDocumentEditPlanEnvelope = BridgeEnvelope<{
  document_edit_plan?: CodingDocumentPlan | null;
}>;

export type CodingDocumentEditApplyEnvelope = BridgeEnvelope<{
  document_edit_result?: CodingDocumentApplyResult | null;
}>;

export type CodingDataDescriptor = {
  type_id?: string;
  label?: string;
  category?: string;
  adapter?: string;
  extensions?: string[];
  readable?: boolean;
  previewable?: boolean;
  exportable?: boolean;
  editable?: boolean;
  mutation_supported?: boolean;
  derived_copy_preferred?: boolean;
  risk?: string;
  capabilities?: Record<string, unknown>;
  notes?: string[];
};

export type CodingDataPreview = {
  status?: string;
  file_label?: string;
  relative_path?: string | null;
  path_hash?: string | null;
  content_hash?: string | null;
  blocked_reason?: string | null;
  descriptor?: CodingDataDescriptor;
  size_bytes?: number;
  metadata?: Record<string, unknown>;
  schema_summary?: Record<string, unknown>;
  preview?: Record<string, unknown>;
  layers?: Array<Record<string, unknown>>;
  tables?: Array<Record<string, unknown>>;
  bands?: Array<Record<string, unknown>>;
  dimensions?: Array<Record<string, unknown>>;
  variables?: Array<Record<string, unknown>>;
  warnings?: string[];
  risk_flags?: Record<string, unknown>;
  provenance_refs?: Array<Record<string, unknown>>;
  redaction_count?: number;
  preview_truncated?: boolean;
  dependencies?: Record<string, string>;
};

export type CodingDataPathRequest = {
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
  approval_granted?: boolean;
  approval_reason?: string | null;
  max_rows?: number | null;
  max_features?: number | null;
  max_values?: number | null;
};

export type CodingDataExportPlanRequest = CodingDataPathRequest & {
  export_format: "markdown" | "json" | "csv" | "geojson";
  target_path?: string | null;
};

export type CodingDataExportApplyRequest = CodingDataExportPlanRequest & {
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  overwrite_existing?: boolean;
  expected_source_hash?: string | null;
};

export type CodingDataEditPlanRequest = CodingDataPathRequest & {
  operation: string;
  parameters?: Record<string, unknown>;
};

export type CodingDataApplyRequest = CodingDataEditPlanRequest & {
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  expected_source_hash?: string | null;
};

export type CodingDataPlan = CodingDocumentPlan & {
  transaction?: Record<string, unknown>;
  backup?: Record<string, unknown>;
};

export type CodingDataApplyResult = CodingDocumentApplyResult & {
  transaction?: Record<string, unknown>;
  backup?: Record<string, unknown>;
};

export type CodingDataPreviewEnvelope = BridgeEnvelope<{
  data?: CodingDataPreview | null;
}>;

export type CodingDataExportPlanEnvelope = BridgeEnvelope<{
  data_export_plan?: CodingDataPlan | null;
}>;

export type CodingDataEditPlanEnvelope = BridgeEnvelope<{
  data_edit_plan?: CodingDataPlan | null;
  data_mutation_plan?: CodingDataPlan | null;
}>;

export type CodingDataApplyEnvelope = BridgeEnvelope<{
  data_apply_result?: CodingDataApplyResult | null;
  data_mutation_result?: CodingDataApplyResult | null;
  data_export_result?: CodingDataApplyResult | null;
}>;

export type CodingVisualDescriptor = {
  type_id?: string;
  label?: string;
  extensions?: string[];
  mime?: string;
  category?: string;
  adapter?: string;
  capabilities?: Record<string, unknown>;
  risk_flags?: Record<string, unknown>;
  stable_operations?: string[];
  notes?: string[];
};

export type CodingVisualPreview = {
  status?: string;
  file_label?: string;
  relative_path?: string | null;
  path_hash?: string | null;
  content_hash?: string | null;
  blocked_reason?: string | null;
  descriptor?: CodingVisualDescriptor;
  size_bytes?: number;
  metadata?: Record<string, unknown>;
  preview?: Record<string, unknown>;
  exif_privacy?: Record<string, unknown>;
  svg_safety?: Record<string, unknown>;
  risk_flags?: Record<string, unknown>;
  warnings?: string[];
  sanitized_preview?: string | null;
};

export type CodingVisualPathRequest = {
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
  approval_granted?: boolean;
  approval_reason?: string | null;
};

export type CodingVisualOcrRequest = CodingVisualPathRequest & {
  max_chars?: number | null;
};

export type CodingVisualAnalysisRequest = CodingVisualPathRequest & {
  include_semantic_provider?: boolean;
};

export type CodingVisualExportPlanRequest = CodingVisualPathRequest & {
  export_format: "markdown" | "json" | "png" | "jpg" | "jpeg" | "webp" | "tiff" | "svg";
  target_path?: string | null;
};

export type CodingVisualExportApplyRequest = CodingVisualExportPlanRequest & {
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  overwrite_existing?: boolean;
  expected_source_hash?: string | null;
};

export type CodingVisualEditPlanRequest = CodingVisualPathRequest & {
  operation: string;
  parameters?: Record<string, unknown>;
};

export type CodingVisualApplyRequest = CodingVisualEditPlanRequest & {
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  expected_source_hash?: string | null;
  overwrite_existing?: boolean;
};

export type CodingVisualPlan = CodingDocumentPlan;
export type CodingVisualApplyResult = CodingDocumentApplyResult;

export type CodingMediaDescriptor = {
  type_id?: string;
  label?: string;
  extensions?: string[];
  mime_types?: string[];
  media_family?: "audio" | "video" | "unknown" | string;
  expected_formats?: string[];
  capabilities?: Record<string, boolean>;
  risk?: string;
  notes?: string[];
};

export type CodingMediaPreview = {
  status?: string;
  file_label?: string;
  relative_path?: string | null;
  path_hash?: string | null;
  content_hash?: string | null;
  blocked_reason?: string | null;
  descriptor?: CodingMediaDescriptor;
  size_bytes?: number;
  media_family?: string;
  container?: string | null;
  duration_seconds?: number | null;
  bitrate_bps?: number | null;
  stream_count?: number;
  audio?: Record<string, unknown>;
  video?: Record<string, unknown>;
  privacy_flags?: Record<string, boolean>;
  safety_flags?: Record<string, boolean>;
  dependencies?: Record<string, unknown>;
  thumbnail_status?: string;
  thumbnail_data_url?: string | null;
  thumbnail_path?: string | null;
  operation_id?: string | null;
  request_id?: string | null;
  audit_written?: boolean;
  warnings?: string[];
};

export type CodingMediaPathRequest = {
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
  approval_granted?: boolean;
  approval_reason?: string | null;
};

export type CodingMediaPreviewEnvelope = BridgeEnvelope<{
  media?: CodingMediaPreview | null;
}>;

export type ArchiveMemberRecord = {
  index: number;
  display_path: string;
  path_hash: string;
  normalized_relative_path?: string | null;
  kind: string;
  compressed_size: number;
  uncompressed_size: number;
  is_directory: boolean;
  is_regular_file: boolean;
  is_symlink: boolean;
  is_hardlink: boolean;
  is_device: boolean;
  is_fifo: boolean;
  is_socket: boolean;
  is_executable: boolean;
  is_encrypted: boolean;
  is_nested_archive_candidate: boolean;
  extractable: boolean;
  blocked_reason?: string | null;
  risk_flags?: string[];
};

export type ArchiveRiskFlag = {
  code: string;
  severity: "info" | "warning" | "high" | "blocked" | string;
  count: number;
  blocks_extraction: boolean;
  summary: string;
};

export type ArchiveContainerPreview = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  path_hash: string;
  archive_sha256?: string | null;
  archive_size_bytes: number;
  extension_type: string;
  detected_type: string;
  extension_content_match: boolean;
  descriptor: {
    type_id: string;
    label: string;
    inspection_state: string;
    extraction_state: string;
    package_container: boolean;
    selected_sandbox_extraction_supported: boolean;
    install_state: string;
    execute_state: string;
    tool_license_status: string;
    notes?: string[];
  };
  member_count: number;
  directory_count: number;
  projected_uncompressed_bytes: number;
  largest_member_bytes: number;
  nested_archive_count: number;
  compression_ratio: number;
  encrypted: boolean;
  members: ArchiveMemberRecord[];
  member_list_truncated: boolean;
  risk_flags: ArchiveRiskFlag[];
  risk_counts: Record<string, number>;
  package_metadata?: {
    container_kind: string;
    summary: Record<string, unknown>;
    scripts_present: string[];
    native_binary_count: number;
    executable_entrypoint_count: number;
    metadata_truncated: boolean;
    install_supported: false;
    execute_supported: false;
    warnings?: string[];
  } | null;
  manifest_digest?: string | null;
  artifacts?: Array<{ artifact_id: string; artifact_kind: string; sha256: string; size_bytes: number }>;
  policy_version: string;
  tool_used: string;
  blocked_reason?: string | null;
  audit_written: boolean;
  warnings?: string[];
};

export type ArchiveExtractionPlan = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  archive_type: string;
  archive_sha256: string;
  archive_size_bytes: number;
  manifest_digest: string;
  selected_member_indexes: number[];
  selected_members_digest: string;
  selected_file_count: number;
  projected_write_bytes: number;
  sandbox_id: string;
  sandbox_destination_hash: string;
  plan_hash: string;
  policy_version: string;
  approval_required: true;
  exact_approval?: Record<string, unknown>;
  artifact?: { artifact_id: string; artifact_kind: string; sha256: string; size_bytes: number } | null;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type ArchiveExtractionResult = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  approval_id?: string | null;
  archive_type: string;
  archive_sha256: string;
  manifest_digest: string;
  plan_hash: string;
  sandbox_id: string;
  sandbox_destination_hash: string;
  extracted_file_count: number;
  extracted_bytes: number;
  blocked_member_count: number;
  skipped_member_count: number;
  audit_written: boolean;
  mutation_performed: boolean;
  source_mutated: false;
  project_root_written: false;
  install_performed: false;
  execution_performed: false;
  cleanup_performed: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type ArchiveInspectEnvelope = BridgeEnvelope<{ archive?: ArchiveContainerPreview | null }>;
export type ArchiveExtractionPlanEnvelope = BridgeEnvelope<{ archive_extraction_plan?: ArchiveExtractionPlan | null }>;
export type ArchiveExtractionResultEnvelope = BridgeEnvelope<{ archive_extraction_result?: ArchiveExtractionResult | null }>;

export type DataBinaryArtifactReceipt = {
  artifact_id: string;
  artifact_kind: string;
  sha256: string;
  size_bytes: number;
};

export type DatabaseInspection = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  path_hash: string;
  source_sha256?: string | null;
  source_blake3?: string | null;
  size_bytes: number;
  extension_type: string;
  detected_engine: string;
  extension_content_match: boolean;
  magic_summary: string;
  descriptor: {
    type_id: string;
    label: string;
    metadata_state: string;
    schema_preview_state: string;
    row_preview_state: string;
    arbitrary_sql_state: string;
    mutation_state: string;
    install_load_state: string;
    notes?: string[];
  };
  sidecars: Record<string, { present?: boolean; size_bytes?: number; regular_file?: boolean; symlink?: boolean }>;
  source_state_digest?: string | null;
  schema_preview_plan_hash?: string | null;
  artifact?: DataBinaryArtifactReceipt | null;
  policy_version: string;
  worker_policy_version: string;
  audit_written: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type DatabaseSchemaPreview = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  approval_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  path_hash: string;
  detected_engine: string;
  source_sha256: string;
  snapshot_sha256?: string | null;
  snapshot_strategy?: string | null;
  table_count: number;
  view_count: number;
  index_count: number;
  trigger_count: number;
  schema_object_count: number;
  risk_counts: Record<string, number>;
  artifact?: DataBinaryArtifactReceipt | null;
  policy_version: string;
  mutation_performed: false;
  row_data_returned: false;
  arbitrary_sql_executed: false;
  audit_written: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type BinaryInspection = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  path_hash: string;
  source_sha256?: string | null;
  source_blake3?: string | null;
  size_bytes: number;
  extension_type: string;
  detected_format: string;
  extension_content_match: boolean;
  magic_summary: string;
  descriptor: { type_id: string; label: string; inspection_state: string; disassembly_state: string; execution_state: string; load_state: string; install_state: string; mutation_state: string; patch_state: string; notes?: string[] };
  architecture?: string | null;
  bitness?: number | null;
  endianness?: string | null;
  section_count: number;
  import_count: number;
  export_count: number;
  symbol_count: number;
  string_count: number;
  entropy?: number | null;
  executable_bit: boolean;
  debug_symbols_present?: boolean | null;
  stripped?: boolean | null;
  risk_flags: Array<{ code: string; severity: string; count: number; summary: string }>;
  risk_counts: Record<string, number>;
  artifact?: DataBinaryArtifactReceipt | null;
  policy_version: string;
  worker_policy_version: string;
  toolchain: string[];
  execution_performed: false;
  loading_performed: false;
  mutation_performed: false;
  audit_written: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type DatabaseInspectEnvelope = BridgeEnvelope<{ database?: DatabaseInspection | null }>;
export type DatabaseSchemaEnvelope = BridgeEnvelope<{ database_schema?: DatabaseSchemaPreview | null }>;
export type BinaryInspectEnvelope = BridgeEnvelope<{ binary?: BinaryInspection | null }>;

export type EngineeringArtifactReceipt = {
  artifact_id: string;
  artifact_kind: string;
  file_name: string;
  media_type: string;
  sha256: string;
  size_bytes: number;
  local_only: true;
};

export type EngineeringInspection = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  path_hash: string;
  source_sha256?: string | null;
  size_bytes: number;
  extension_type: string;
  detected_type: string;
  extension_content_match: boolean;
  magic_summary: string;
  descriptor: {
    type_id: string;
    label: string;
    family: string;
    forge: string;
    static_inspection_state: string;
    report_state: string;
    preview_state: string;
    conversion_state: string;
    repair_state: string;
    simulation_state: string;
    generation_state: string;
    physical_output_state: string;
    maximum_live_level: number;
    notes?: string[];
  };
  report: Record<string, unknown>;
  capability_truth: Record<string, string>;
  risk_flags: Array<{ code: string; severity: string; count: number; summary: string }>;
  risk_counts: Record<string, number>;
  external_references: Array<{ reference_kind: string; display_reference: string; reference_hash: string; scheme: string; resolution_state: string; blocked_reason?: string | null }>;
  external_reference_count: number;
  artifacts: EngineeringArtifactReceipt[];
  preview_plan_hash?: string | null;
  preview_kind?: string | null;
  policy_version: string;
  worker_policy_version: string;
  worker_key: string;
  worker_state: string;
  audit_written: boolean;
  source_mutated: false;
  network_used: false;
  scripts_executed: false;
  plugins_loaded: false;
  physical_output_performed: false;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type EngineeringPreviewPlan = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  path_hash: string;
  source_sha256: string;
  size_bytes: number;
  detected_type: string;
  family: string;
  preview_kind: string;
  plan_hash: string;
  policy_version: string;
  approval_required: true;
  artifact?: EngineeringArtifactReceipt | null;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type EngineeringPreviewResult = {
  status: string;
  operation_id: string;
  request_id?: string | null;
  approval_id?: string | null;
  file_label: string;
  relative_path?: string | null;
  path_hash: string;
  source_sha256: string;
  detected_type: string;
  family: string;
  preview_kind: string;
  plan_hash: string;
  artifact?: EngineeringArtifactReceipt | null;
  receipt_artifact?: EngineeringArtifactReceipt | null;
  policy_version: string;
  audit_written: boolean;
  source_mutated: false;
  project_root_written: false;
  network_used: false;
  scripts_executed: false;
  plugins_loaded: false;
  physical_output_performed: false;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type EngineeringInspectEnvelope = BridgeEnvelope<{ engineering?: EngineeringInspection | null }>;
export type EngineeringPreviewPlanEnvelope = BridgeEnvelope<{ engineering_preview_plan?: EngineeringPreviewPlan | null }>;
export type EngineeringPreviewResultEnvelope = BridgeEnvelope<{ engineering_preview_result?: EngineeringPreviewResult | null }>;

export type MediaWorkerModelTruth = {
  id?: string;
  display_name?: string;
  capability?: string;
  state?: string;
  enabled_state?: string;
  gate_status?: string;
  local_assets_present?: boolean;
  voice_assets_present?: boolean;
  license?: string;
  license_review_status?: string;
  provenance_review_status?: string;
  training_data_provenance?: string;
  production_blockers?: string[];
  known_failure_modes?: string[];
  gates?: Record<string, unknown>;
};

export type MediaWorkerTruth = {
  speechforge?: Record<string, unknown> & { models?: MediaWorkerModelTruth[] };
  imageforge?: Record<string, unknown> & { models?: MediaWorkerModelTruth[] };
  videoforge?: Record<string, unknown> & { models?: MediaWorkerModelTruth[] };
  voice_cloning?: Record<string, unknown>;
  gates?: Record<string, unknown>;
  runtime_registry?: Array<Record<string, unknown>>;
};

export type MediaWorkerTruthEnvelope = BridgeEnvelope<{
  media_workers?: MediaWorkerTruth | null;
}>;

export type TtsVoice = {
  id: string;
  display_name?: string;
  language?: string;
  style?: string;
  enabled?: boolean;
};

export type TtsVoiceCatalogEnvelope = BridgeEnvelope<{
  voices?: TtsVoice[];
  voice_cloning_available?: boolean;
}>;

export type SpeechTtsPlanRequest = {
  session_id?: string | null;
  workspace_root: string;
  text: string;
  voice_id?: string;
  speed?: number;
  target_path?: string | null;
  approval_granted?: boolean;
  approval_reason?: string | null;
  purpose_category?: "accessibility" | "private_reading" | "local_artifact";
};

export type SpeechTtsPlan = {
  status?: string;
  voice_id: string;
  voice_label?: string | null;
  language?: string | null;
  text_hash: string;
  text_length: number;
  speed: number;
  purpose_category: string;
  target_relative_path?: string | null;
  sidecar_relative_path?: string | null;
  plan_hash?: string | null;
  model_id?: string;
  synthetic_reading_voice?: boolean;
  voice_cloning_available?: boolean;
  approval_required?: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type SpeechTtsApplyRequest = SpeechTtsPlanRequest & {
  expected_text_hash: string;
  expected_plan_hash: string;
  approval_id: string;
  approval_token: string;
};

export type SpeechTtsResult = SpeechTtsPlan & {
  artifact_id?: string | null;
  output_sha256?: string | null;
  sidecar_sha256?: string | null;
  output_bytes?: number;
  sample_rate_hz?: number | null;
  duration_seconds?: number | null;
  audio_data_url?: string | null;
  operation_id?: string | null;
  request_id?: string | null;
  approval_id?: string | null;
  audit_written?: boolean;
  network_used?: boolean;
  cloud_used?: boolean;
};

export type SpeechTtsPlanEnvelope = BridgeEnvelope<{ tts_plan?: SpeechTtsPlan | null }>;
export type SpeechTtsResultEnvelope = BridgeEnvelope<{ tts_result?: SpeechTtsResult | null }>;

export type SpeechTranscriptionPlanRequest = CodingMediaPathRequest & {
  target_path?: string | null;
  output_format?: "txt" | "json" | "srt" | "vtt";
  operator_has_processing_rights?: boolean;
  contains_other_people?: boolean;
  other_people_consent_confirmed?: boolean;
  private_local_use?: boolean;
  redact_sensitive_text?: boolean;
};

export type SpeechTranscriptionPlan = {
  status?: string;
  file_label?: string;
  relative_path?: string | null;
  target_relative_path?: string | null;
  sidecar_relative_path?: string | null;
  source_hash?: string | null;
  plan_hash?: string | null;
  model_id?: string | null;
  engine?: string | null;
  language?: string | null;
  duration_seconds?: number | null;
  size_bytes?: number;
  output_format?: string;
  consent_state?: string;
  approval_required?: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type SpeechTranscriptionApplyRequest = SpeechTranscriptionPlanRequest & {
  expected_source_hash: string;
  expected_plan_hash: string;
  approval_id: string;
  approval_token: string;
};

export type SpeechTranscriptionResult = SpeechTranscriptionPlan & {
  artifact_id?: string | null;
  transcript_sha256?: string | null;
  sidecar_sha256?: string | null;
  transcript_bytes?: number;
  segment_count?: number;
  operation_id?: string | null;
  request_id?: string | null;
  approval_id?: string | null;
  audit_written?: boolean;
  raw_transcript_returned?: boolean;
};

export type SpeechTranscriptionPlanEnvelope = BridgeEnvelope<{ transcription_plan?: SpeechTranscriptionPlan | null }>;
export type SpeechTranscriptionResultEnvelope = BridgeEnvelope<{ transcription_result?: SpeechTranscriptionResult | null }>;

export type VideoForgePlanRequest = {
  session_id?: string | null;
  workspace_root: string;
  model_id?: "wan21-t2v-1.3b";
  prompt: string;
  negative_prompt?: string;
  purpose_category?: "private_creative" | "documentary_illustration" | "lab_smoke";
  width?: 416;
  height?: 256;
  frames?: 9;
  fps?: 8;
  steps?: 4;
  seed?: number;
  target_path?: string | null;
  approval_granted?: boolean;
  approval_reason?: string | null;
  lab_acknowledged?: boolean;
  contains_real_person_request?: boolean;
};

export type VideoForgePlan = {
  status?: string;
  model_id: string;
  model_state: string;
  prompt_hash: string;
  prompt_length: number;
  purpose_category: string;
  width: number;
  height: number;
  frames: number;
  fps: number;
  steps: number;
  seed: number;
  target_relative_path?: string | null;
  sidecar_relative_path?: string | null;
  plan_hash?: string | null;
  synthetic_media?: boolean;
  production_enabled?: boolean;
  approval_required?: boolean;
  cancellation_supported?: boolean;
  blocked_reason?: string | null;
  warnings?: string[];
};

export type VideoForgeJob = VideoForgePlan & {
  operation_id: string;
  request_id?: string | null;
  approval_id?: string | null;
  workspace_root_hash?: string | null;
  artifact_id?: string | null;
  output_sha256?: string | null;
  sidecar_sha256?: string | null;
  output_bytes?: number;
  duration_seconds?: number | null;
  runtime_seconds?: number | null;
  peak_gpu_memory_mib?: number | null;
  audit_written?: boolean;
  cancel_requested?: boolean;
  network_used?: boolean;
  cloud_used?: boolean;
};

export type VideoForgeApplyRequest = VideoForgePlanRequest & {
  expected_prompt_hash: string;
  expected_plan_hash: string;
  approval_id: string;
  approval_token: string;
};

export type VideoForgePlanEnvelope = BridgeEnvelope<{ videoforge_plan?: VideoForgePlan | null }>;
export type VideoForgeJobEnvelope = BridgeEnvelope<{ videoforge_job?: VideoForgeJob | null }>;

export type CodingOperationApprovalRequest = {
  session_id?: string | null;
  operation_kind: string;
  operation_summary: string;
  workspace_root: string;
  exact_files: string[];
  source_hash?: string | null;
  plan_hash: string;
  allowed_mutation_class: string;
  expires_in_seconds?: number;
  operator_approved: boolean;
  approval_phrase?: string | null;
  rollback_note: string;
};

export type CodingOperationApproval = {
  status?: string;
  approval_id: string;
  approval_token?: string | null;
  exact_files?: string[];
  workspace_root_hash?: string | null;
  source_hash?: string | null;
  plan_hash?: string | null;
  allowed_mutation_class?: string | null;
  expires_at_utc?: string;
  one_time_use?: boolean;
  audit_written?: boolean;
  warnings?: string[];
};

export type CodingOperationApprovalEnvelope = BridgeEnvelope<{
  operation_approval?: CodingOperationApproval | null;
}>;

export type CodingVisualPreviewEnvelope = BridgeEnvelope<{
  visual?: CodingVisualPreview | null;
}>;

export type CodingVisualOcrEnvelope = BridgeEnvelope<{
  ocr?: Record<string, unknown> | null;
}>;

export type CodingVisualAnalysisEnvelope = BridgeEnvelope<{
  analysis?: Record<string, unknown> | null;
}>;

export type CodingVisualExportPlanEnvelope = BridgeEnvelope<{
  visual_export_plan?: CodingVisualPlan | null;
}>;

export type CodingVisualEditPlanEnvelope = BridgeEnvelope<{
  visual_edit_plan?: CodingVisualPlan | null;
}>;

export type CodingVisualApplyEnvelope = BridgeEnvelope<{
  visual_export_result?: CodingVisualApplyResult | null;
  visual_apply_result?: CodingVisualApplyResult | null;
}>;

export type TruthBearingFields = {
  runtime_state?: string;
  selected_role?: string;
  selected_model_role?: string;
  selected_runtime?: string;
  selected_model_runtime_tag?: string;
  stayed_local?: boolean;
  used_fallback?: boolean;
  fallback_from?: string;
  fallback_to?: string;
  approval_needed?: boolean;
  invocation_status?: string;
  blocked?: boolean;
  degraded?: boolean;
  blocked_reasons?: string[];
  degraded_reasons?: string[];
};

export type ConversationSummary = {
  conversation_id: string;
  title?: string | null;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  last_message_preview?: string | null;
  message_count?: number | null;
  current_mode?: string | null;
  current_role?: string | null;
  capability_state?: string | null;
  locality?: string | null;
  approval_state?: string | null;
  project_id?: string | null;
  archived?: boolean | null;
  pinned?: boolean | null;
  conversation_state?: string | null;
  last_message_role?: string | null;
};

export type ConversationMessage = TruthBearingFields & {
  message_id?: string;
  conversation_id?: string;
  role: "system" | "user" | "assistant" | "tool" | string;
  content: string;
  created_at_utc?: string | null;
  request_id?: string | null;
  response_source?: string | null;
  approval_state?: string | null;
  locality_state?: string | null;
  capability_state?: string | null;
  error?: string | null;
  warnings?: string[];
  caveats?: string[];
};

export type ConversationThreadMetadata = {
  conversation_id: string;
  title?: string | null;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  last_message_preview?: string | null;
  message_count?: number | null;
  current_mode?: string | null;
  current_role?: string | null;
  capability_state?: string | null;
  locality?: string | null;
  approval_state?: string | null;
  project_id?: string | null;
  archived?: boolean | null;
  pinned?: boolean | null;
  conversation_state?: string | null;
};

export type ConversationListEnvelope = BridgeEnvelope<{
  conversations?: ConversationSummary[];
  active_conversation_id?: string | null;
  total?: number | null;
}>;

export type ConversationThreadEnvelope = BridgeEnvelope<{
  conversation_id?: string;
  metadata?: ConversationThreadMetadata | null;
  messages?: ConversationMessage[] | null;
  last_message_role?: string | null;
  message_count?: number | null;
  storage_version?: number | null;
}>;

export type ConversationDeleteEnvelope = BridgeEnvelope<{
  conversation_id?: string | null;
  deleted?: boolean;
}>;

export type ConversationUpdatePatch = {
  title?: string | null;
  project_id?: string | null;
  pinned?: boolean | null;
  archived?: boolean | null;
};

export type ConversationUpdateEnvelope = BridgeEnvelope<{
  conversation_id?: string | null;
  metadata?: ConversationThreadMetadata | null;
  updated_fields?: string[];
}>;

export type FetchConversationListOptions = {
  includeArchived?: boolean;
  limit?: number | null;
};

export type ProjectSummary = {
  project_id: string;
  name?: string | null;
  description?: string | null;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  status?: string | null;
  conversation_count?: number | null;
  notes_summary?: string | null;
  state_summary?: string | null;
  current_state?: string | null;
  latest_chunk?: string | null;
  project_notes?: string | null;
  milestones?: ProjectContinuityItem[];
  decisions?: ProjectContinuityItem[];
  blockers?: ProjectContinuityItem[];
  next_actions?: ProjectContinuityItem[];
  unresolved_questions?: ProjectContinuityItem[];
  corrections?: ProjectContinuityItem[];
  source_count?: number | null;
  archived?: boolean | null;
};

export type ProjectContinuityItem = {
  label?: string | null;
  summary?: string | null;
  status?: string | null;
  source_kind?: string | null;
  source_id?: string | null;
  source_label?: string | null;
  updated_at_utc?: string | null;
};

export type ProjectLinkedArtifact = {
  artifact_id?: string | null;
  kind?: string | null;
  title?: string | null;
  summary?: string | null;
  created_at_utc?: string | null;
  request_id?: string | null;
  conversation_id?: string | null;
  project_id?: string | null;
};

export type ProjectContinuitySummary = {
  project_id?: string | null;
  name?: string | null;
  current_state?: string | null;
  latest_chunk?: string | null;
  project_notes?: string | null;
  recent_milestones?: ProjectContinuityItem[];
  decisions?: ProjectContinuityItem[];
  open_blockers?: ProjectContinuityItem[];
  next_suggested_actions?: ProjectContinuityItem[];
  unresolved_questions?: ProjectContinuityItem[];
  corrections?: ProjectContinuityItem[];
  linked_conversation_ids?: string[];
  linked_request_ids?: string[];
  linked_requests?: Record<string, unknown>[];
  linked_artifact_ids?: string[];
  linked_artifacts?: ProjectLinkedArtifact[];
  linked_evidence_packet_ids?: string[];
  latest_activity?: ProjectContinuityItem[];
  provenance?: ProjectContinuityItem[];
  sealed_private_memory_used?: boolean | null;
  attached_files_are_memory?: boolean | null;
  artifacts_are_memory?: boolean | null;
};

export type ProjectListEnvelope = BridgeEnvelope<{
  projects?: ProjectSummary[];
  active_project_id?: string | null;
  total?: number | null;
}>;

export type ProjectCreateRequest = {
  name: string;
  description?: string | null;
};

export type ProjectCreateEnvelope = BridgeEnvelope<{
  project_id?: string | null;
  project?: ProjectSummary | null;
  created?: boolean;
}>;

export type ProjectUpdatePatch = {
  name?: string | null;
  description?: string | null;
  status?: string | null;
  notes_summary?: string | null;
  state_summary?: string | null;
  current_state?: string | null;
  latest_chunk?: string | null;
  project_notes?: string | null;
  milestones?: ProjectContinuityItem[];
  decisions?: ProjectContinuityItem[];
  blockers?: ProjectContinuityItem[];
  next_actions?: ProjectContinuityItem[];
  unresolved_questions?: ProjectContinuityItem[];
  corrections?: ProjectContinuityItem[];
};

export type ProjectUpdateEnvelope = BridgeEnvelope<{
  project_id?: string | null;
  project?: ProjectSummary | null;
  updated_fields?: string[];
}>;

export type ProjectDeleteEnvelope = BridgeEnvelope<{
  project_id?: string | null;
  deleted?: boolean;
  active_project_id?: string | null;
}>;

export type ProjectDetailConversationSummary = {
  conversation_id: string;
  title?: string | null;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  last_message_preview?: string | null;
  message_count?: number | null;
  current_mode?: string | null;
  current_role?: string | null;
  capability_state?: string | null;
  locality?: string | null;
  approval_state?: string | null;
  project_id?: string | null;
  archived?: boolean | null;
  pinned?: boolean | null;
  conversation_state?: string | null;
};

export type ProjectDetailEnvelope = BridgeEnvelope<{
  project_id?: string | null;
  metadata?: ProjectSummary | null;
  related_conversations?: ProjectDetailConversationSummary[];
  conversation_count?: number | null;
  notes_summary?: string | null;
  state_summary?: string | null;
  continuity_summary?: ProjectContinuitySummary | null;
  source_count?: number | null;
  active_project_id?: string | null;
}>;

export type ProjectContinuityEnvelope = BridgeEnvelope<{
  project_id?: string | null;
  continuity_summary?: ProjectContinuitySummary | null;
  active_project_id?: string | null;
}>;

export type ProjectSelectionRequest = {
  project_id?: string | null;
};

export type ProjectSelectionEnvelope = BridgeEnvelope<{
  active_project_id?: string | null;
  selected_at_utc?: string | null;
  project?: ProjectSummary | null;
}>;

export type ProjectSource = {
  source_id?: string;
  display_name?: string;
  file_kind?: string;
  sha256?: string;
  size_bytes?: number;
  parser_used?: string;
  attached_at_utc?: string;
  local_only?: boolean;
  memory_promoted?: boolean;
};

export type ProjectStudyModule = {
  module_id?: string;
  sequence?: number;
  objective?: string;
  grounding_excerpt?: string;
  practice_prompt?: string;
  review_state?: string;
  review_history?: Array<{ action?: string; reflection?: string; confidence?: number; recorded_at_utc?: string }>;
};

export type ProjectStudyPlan = {
  study_plan_id?: string;
  topic?: string;
  goals?: string[];
  difficulty?: string;
  source_sha256?: string;
  grounding_state?: string;
  modules?: ProjectStudyModule[];
  created_at_utc?: string;
  progress?: { completed_modules?: number; module_count?: number; percent?: number; review_due?: number };
};

export type ProjectResearchInvestigation = {
  investigation_id?: string;
  question?: string;
  status?: string;
  iterations?: Array<{ iteration_id?: string; query?: string; evidence_count?: number; evidence_verified?: boolean; recorded_at_utc?: string }>;
  evidence?: Array<Record<string, unknown>>;
  source_count?: number;
  comparison?: { status?: string; explicit_notes?: string[]; conflicting_claims?: string[] };
  created_at_utc?: string;
  updated_at_utc?: string;
};

export type ProjectQuizQuestion = {
  question_id?: string;
  prompt?: string;
  explanation?: string;
  attempts?: Array<{ attempted_at_utc?: string; answer?: string; correct?: boolean }>;
  mastered?: boolean;
};

export type ProjectQuiz = {
  quiz_id?: string;
  title?: string;
  difficulty?: string;
  source_sha256?: string;
  grounding_state?: string;
  questions?: ProjectQuizQuestion[];
  score?: number;
};

export type ProjectGoal = {
  goal_id?: string;
  goal?: string;
  status?: string;
  autonomy_level?: number;
  budget_steps?: number;
  budget_minutes?: number;
  steps_used?: number;
  steps?: Array<{ step_id?: string; sequence?: number; description?: string; status?: string }>;
  checkpoints?: Array<Record<string, unknown>>;
  receipts?: Array<Record<string, unknown>>;
  policy?: Record<string, boolean>;
};

export type ProjectCanvasElement = {
  element_id?: string;
  kind: "note" | "heading" | "link" | "image_reference";
  content: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  color?: "bronze" | "teal" | "emerald" | "silver" | "oxide";
};

export type ProjectWorkbench = {
  store_version?: number;
  project_id?: string;
  sources?: ProjectSource[];
  study_plans?: ProjectStudyPlan[];
  quizzes?: ProjectQuiz[];
  research_investigations?: ProjectResearchInvestigation[];
  goals?: ProjectGoal[];
  canvas?: { title?: string; elements?: ProjectCanvasElement[]; updated_at_utc?: string };
  created_at_utc?: string;
  updated_at_utc?: string;
};

export type ProjectCapabilityEnvelope = BridgeEnvelope<{
  workbench?: ProjectWorkbench;
  project_id?: string;
  source?: ProjectSource;
  source_count?: number;
  study_plan?: ProjectStudyPlan;
  study_module?: ProjectStudyModule;
  quiz?: ProjectQuiz;
  research_investigation?: ProjectResearchInvestigation;
  goal?: ProjectGoal;
  canvas?: ProjectWorkbench["canvas"];
  correct?: boolean;
  score?: number;
  question_count?: number;
  explanation?: string;
  attempt_count?: number;
  imageforge_plan?: Record<string, unknown>;
  imageforge_job?: Record<string, unknown>;
  job_started?: boolean;
  tts_plan?: Record<string, unknown>;
  tts_result?: Record<string, unknown>;
  gimp?: Record<string, unknown>;
  soundcloud?: Record<string, unknown>;
  completed?: boolean;
}>;

export type FetchProjectListOptions = {
  limit?: number | null;
};

export type ChatSendRequest = {
  message: string;
  request_id?: string | null;
  conversation_id?: string | null;
  project_id?: string | null;
  requested_mode?: string;
  requested_role?: string;
  requested_gear?: string;
  request_context?: Record<string, unknown> | null;
  ui_surface?: string;
};

export type PlanSummaryData =
  | string
  | {
      goal?: string | null;
      steps?: string[];
      note?: string | null;
      [key: string]: unknown;
    }
  | null;

export type MemorySummaryData = {
  loaded_memory_classes?: string[];
  memory_status?: string | null;
  promoted_write_candidates?: string[];
  memory_note?: string | null;
};

export type JournalSummaryData = {
  will_journal?: boolean | null;
  journal_mode?: string | null;
  journal_note?: string | null;
};

export type AttachedContextSummaryData = {
  active_project_id?: string | null;
  active_project_name?: string | null;
  files_in_use?: string[];
  text_files_in_use?: string[];
  data_files_in_use?: string[];
  attached_file_ids?: string[];
  attached_text_file_ids?: string[];
  attached_data_file_ids?: string[];
  attached_files_are_memory?: boolean | null;
  attached_files_source?: string | null;
  file_count?: number | null;
  text_file_count?: number | null;
  data_file_count?: number | null;
  bounded?: boolean | null;
  warnings?: string[];
  errors?: string[];
  active_context_note?: string | null;
};

export type TraceSummaryData = {
  request_id?: string | null;
  route_decision_note?: string | null;
  log_written?: boolean | null;
  journal_candidate?: boolean | null;
  body_path_used?: string | null;
  prompt_source?: string | null;
  config_sources?: string[];
  trace_note?: string | null;
};

export type MathExecutionSummaryData = {
  used?: boolean | null;
  status?: string | null;
  tool_kind?: string | null;
  operation?: string | null;
  input?: string | null;
  variable?: string | null;
  expected?: string | null;
  result?: string | null;
  numeric_result?: number | null;
  exact_match?: boolean | null;
  tolerance?: number | null;
  stayed_local?: boolean | null;
  approval_required?: boolean | null;
  warnings?: string[];
  errors?: string[];
};

export type DataExecutionSummaryData = {
  used?: boolean | null;
  status?: string | null;
  tool_kind?: string | null;
  operation?: string | null;
  source_kind?: string | null;
  source_path?: string | null;
  file_id?: string | null;
  file_name?: string | null;
  file_kind?: string | null;
  row_count?: number | null;
  column_count?: number | null;
  columns?: string[];
  numeric_columns?: string[];
  text_columns?: string[];
  missing_values_by_column?: Record<string, number>;
  numeric_stats?: Record<string, unknown>;
  stayed_local?: boolean | null;
  approval_required?: boolean | null;
  network_access_used?: boolean | null;
  mutated_files?: boolean | null;
  warnings?: string[];
  errors?: string[];
};

export type RepoContextSummaryData = {
  used?: boolean | null;
  status?: string | null;
  tool_kind?: string | null;
  operation?: string | null;
  repo_key?: string | null;
  repo_label?: string | null;
  repo_root?: string | null;
  trust_zone?: string | null;
  appears_git_repo?: boolean | null;
  current_branch?: string | null;
  git_head_read?: boolean | null;
  changed_files_live?: boolean | null;
  changed_files_note?: string | null;
  important_top_level_files?: string[];
  top_level_directories?: string[];
  safe_tree_entries?: string[];
  language_hints?: string[];
  framework_hints?: string[];
  test_command_hints?: string[];
  read_only?: boolean | null;
  approval_required?: boolean | null;
  network_access_used?: boolean | null;
  shell_used?: boolean | null;
  mutated_files?: boolean | null;
  warnings?: string[];
  errors?: string[];
};

export type CodePatchPlanSummaryData = {
  used?: boolean | null;
  status?: string | null;
  tool_kind?: string | null;
  operation?: string | null;
  summary?: string | null;
  repo_key?: string | null;
  repo_root?: string | null;
  files_to_touch?: string[];
  patch_plan?: string[];
  tests_to_run?: string[];
  risk_notes?: string[];
  rollback_notes?: string[];
  approval_needed?: boolean | null;
  approval_reason?: string | null;
  can_apply_patch?: boolean | null;
  patch_application_live?: boolean | null;
  shell_execution_used?: boolean | null;
  network_access_used?: boolean | null;
  mutated_files?: boolean | null;
  external_workers_used?: boolean | null;
  warnings?: string[];
  errors?: string[];
};

export type ArtifactKind =
  | "data_summary"
  | "table_preview"
  | "plot_image"
  | "text_report"
  | "transcript"
  | "speech_audio"
  | "generated_image"
  | "generated_video"
  | string;

export type ArtifactSummaryData = {
  artifact_id?: string | null;
  kind?: ArtifactKind | string | null;
  title?: string | null;
  summary?: string | null;
  created_at_utc?: string | null;
  request_id?: string | null;
  conversation_id?: string | null;
  project_id?: string | null;
  locality?: string | null;
  memory_posture?: string | null;
  producer_tool_kind?: string | null;
  producer_operation?: string | null;
  source_file_id?: string | null;
  source_file_name?: string | null;
  source_file_kind?: string | null;
  row_count?: number | null;
  column_count?: number | null;
  plot_kind?: string | null;
  svg_text?: string | null;
  svg_mime_type?: string | null;
  width?: number | null;
  height?: number | null;
  metric?: string | null;
  plotted_columns?: string[];
  model_id?: string | null;
  mime_type?: string | null;
  output_sha256?: string | null;
  output_bytes?: number | null;
  synthetic_media?: boolean | null;
  warnings?: string[];
  errors?: string[];
  memory_promotion?: boolean | null;
  private_context_sent?: boolean | null;
  preview_available?: boolean | null;
  detail_available?: boolean | null;
};

export type ArtifactDetailData = {
  summary?: ArtifactSummaryData | null;
  detail_kind?: string | null;
  safe_preview?: Record<string, unknown> | null;
  provenance?: Record<string, unknown>[];
  boundary_truth?: Record<string, unknown> | null;
};

export type ArtifactListEnvelope = BridgeEnvelope<{
  artifacts?: ArtifactSummaryData[];
  total?: number | null;
  limit?: number | null;
  filters?: Record<string, unknown> | null;
}>;

export type ArtifactDetailEnvelope = BridgeEnvelope<ArtifactDetailData>;

export type ChatSendEnvelope = BridgeEnvelope<
  TruthBearingFields & {
    user_message?: string;
    response_text?: string;
    response_source?: string;
    mode_effective?: string;
    action_requested?: string;
    selected_model_role?: string;
    selected_runtime?: string;
    selected_model_runtime_tag?: string;
    used_fallback?: boolean;
    fallback_from?: string | null;
    fallback_to?: string | null;
    caveats?: string[];
    approval_needed?: boolean;
    approval_token?: string | null;
    conversation_id?: string | null;
    project_id?: string | null;
    plan_summary?: PlanSummaryData;
    boundary_flags?: string[];
    memory_summary?: MemorySummaryData | null;
    journal_summary?: JournalSummaryData | null;
    attached_context_summary?: AttachedContextSummaryData | null;
    mode_profile?: Record<string, unknown> | null;
    continuity?: Record<string, unknown> | null;
    workspace?: Record<string, unknown> | null;
    context_receipt?: Record<string, unknown> | null;
    research?: Record<string, unknown> | null;
    trace_summary?: TraceSummaryData | null;
    math_execution?: MathExecutionSummaryData | null;
    data_execution?: DataExecutionSummaryData | null;
    repo_context?: RepoContextSummaryData | null;
    code_patch_plan?: CodePatchPlanSummaryData | null;
    artifacts?: ArtifactSummaryData[];
  }
>;

export type QuickInvokeSendBridgeRequest = {
  message: string;
  request_id?: string | null;
  conversation_id?: string | null;
  project_id?: string | null;
  requested_mode?: string;
  requested_role?: string;
  requested_gear?: string;
  request_context?: Record<string, unknown> | null;
  ui_surface?: string;
};

export type QuickInvokeBridgeResultStatus =
  | "ok"
  | "blocked"
  | "unavailable"
  | "degraded"
  | "error";

export type QuickInvokeBridgeResult = {
  status: QuickInvokeBridgeResultStatus;
  responseText?: string | null;
  errorMessage?: string | null;
  requestId?: string | null;
  envelope: ChatSendEnvelope;
  truth: ResponseTruth;
};

export type RequestTraceEntry = {
  entry_id?: string | null;
  request_id?: string | null;
  phase?: string | null;
  label?: string | null;
  detail?: string | null;
  timestamp_utc?: string | null;
  selected_mode?: string | null;
  selected_role?: string | null;
  selected_runtime?: string | null;
  selected_model_runtime_tag?: string | null;
  locality_state?: string | null;
  approval_state?: string | null;
  used_fallback?: boolean | null;
  memory_classes?: string[];
  skill_name?: string | null;
  tool_name?: string | null;
  app_name?: string | null;
  worker_name?: string | null;
  execution_tool_kind?: string | null;
  execution_status?: string | null;
  execution_operation?: string | null;
  execution_summary?: string | null;
};

export type RequestTraceFileSummary = {
  file_id?: string | null;
  file_name?: string | null;
  file_kind?: string | null;
  status?: string | null;
  summary?: string | null;
  parser_used?: string | null;
  chunks_created_count?: number | null;
  chunks_used_count?: number | null;
  memory_promotion_allowed?: boolean | null;
  outward_sharing_allowed?: boolean | null;
  trust_zone?: string | null;
  blocked_reason?: string | null;
};

export type RequestTraceToolEntry = {
  tool_key?: string | null;
  tool_label?: string | null;
  tool_kind?: string | null;
  state?: string | null;
  available?: boolean | null;
  used?: boolean | null;
  approval_required?: boolean | null;
  approval_state?: string | null;
  locality?: string | null;
  boundary_kind?: string | null;
  boundary_state?: string | null;
  worker_name?: string | null;
  operation?: string | null;
  summary?: string | null;
  input_count?: number | null;
  output_count?: number | null;
  mutated_files?: boolean | null;
  network_access_used?: boolean | null;
  private_context_sent?: boolean | null;
  shell_used?: boolean | null;
  git_mutation_used?: boolean | null;
  cloud_used?: boolean | null;
  warnings?: string[];
  errors?: string[];
  session_id?: string | null;
  operation_id?: string | null;
  approval_id?: string | null;
  workspace_root_hash?: string | null;
  relative_paths?: string[];
  source_hash?: string | null;
  plan_hash?: string | null;
  result_hash?: string | null;
  mutation_class?: string | null;
  backup_summary?: string | null;
  audit_persisted?: boolean | null;
};

export type RequestTraceListItem = {
  request_id: string;
  request_status?: string | null;
  current_phase?: string | null;
  updated_at_utc?: string | null;
  selected_mode?: string | null;
  route_used?: string | null;
  locality_state?: string | null;
  approval_state?: string | null;
  artifact_count?: number;
  evidence_packet_count?: number;
};

export type RequestTraceListEnvelope = BridgeEnvelope<{
  request_traces?: RequestTraceListItem[];
  count?: number;
}>;

export type RequestTraceArtifactSummary = {
  artifact_id?: string | null;
  kind?: string | null;
  title?: string | null;
  summary?: string | null;
  created_at_utc?: string | null;
  locality?: string | null;
  memory_posture?: string | null;
  producer_tool_kind?: string | null;
  producer_operation?: string | null;
  source_file_id?: string | null;
  source_file_name?: string | null;
  source_file_kind?: string | null;
  warnings?: string[];
  errors?: string[];
};

export type RequestTraceSnapshot = {
  route_used?: string | null;
  ui_surface?: string | null;
  selected_mode?: string | null;
  selected_role?: string | null;
  selected_runtime?: string | null;
  selected_model_runtime_tag?: string | null;
  locality_state?: string | null;
  approval_state?: string | null;
  approval_needed?: boolean | null;
  used_fallback?: boolean | null;
  mode_profile_key?: string | null;
  mode_profile_label?: string | null;
  mode_profile_used?: boolean | null;
  mode_profile_effects?: string[];
  mode_profile_warnings?: string[];
  authority_granted_by_mode?: boolean | null;
  memory_classes?: string[];
  skill_name?: string | null;
  tool_name?: string | null;
  app_name?: string | null;
  worker_name?: string | null;
  research_ticket_id?: string | null;
  research_worker_name?: string | null;
  research_status?: string | null;
  research_query_count?: number | null;
  research_queries_sent?: string[];
  research_query_hashes?: string[];
  blocked_query_preview?: string | null;
  evidence_packet_count?: number | null;
  outward_boundary_state?: string | null;
  private_context_sent?: boolean | null;
  network_access_used?: boolean | null;
  page_fetch_used?: boolean | null;
  cloud_search_used?: boolean | null;
  cloud_model_used?: boolean | null;
  reasoning_gear?: string | null;
  workspace_version?: string | null;
  context_receipt_version?: string | null;
  retrieval_considered_count?: number | null;
  retrieval_admitted_count?: number | null;
  retrieval_excluded_count?: number | null;
  retrieval_admitted_ids?: string[];
  retrieval_exclusions?: Array<{ candidate_id?: string; source_type?: string; reason?: string }>;
  retrieval_token_budget?: Record<string, number>;
  retrieval_projection_versions?: Record<string, string>;
  retrieval_contradiction_count?: number | null;
  execution_tool_kind?: string | null;
  execution_status?: string | null;
  execution_operation?: string | null;
  execution_summary?: string | null;
  files_attached_count?: number | null;
  files_attached?: RequestTraceFileSummary[];
  files_used_count?: number | null;
  file_chunks_used_count?: number | null;
  file_parsers_used?: string[];
  file_memory_promotion?: boolean | null;
  file_outward_sharing?: boolean | null;
  tools_available_count?: number | null;
  tools_used_count?: number | null;
  tools_available?: RequestTraceToolEntry[];
  tools_used?: RequestTraceToolEntry[];
  artifact_count?: number | null;
  artifacts?: RequestTraceArtifactSummary[];
  repo_context_status?: string | null;
  repo_context_file_count?: number | null;
  repo_context_files?: string[];
  patch_plan_status?: string | null;
  patch_plan_file_count?: number | null;
  patch_plan_files?: string[];
  patch_id?: string | null;
  patch_hash?: string | null;
  patch_diff_preview?: string | null;
  patch_preview_truncated?: boolean | null;
  rollback_note?: string | null;
  command_key?: string | null;
  command_argv?: string[];
  command_exit_code?: number | null;
  command_duration_ms?: number | null;
  command_output_preview?: string | null;
  command_output_truncated?: boolean | null;
  mutated_files?: boolean | null;
  shell_used?: boolean | null;
  git_mutation_used?: boolean | null;
  external_worker_used?: boolean | null;
  related_conversation_id?: string | null;
  related_project_id?: string | null;
  errors?: string[];
  warnings?: string[];
};

export type RequestTraceData = {
  request_id?: string | null;
  request_status?: string | null;
  current_phase?: string | null;
  current_phase_label?: string | null;
  current_phase_detail?: string | null;
  created_at_utc?: string | null;
  updated_at_utc?: string | null;
  completed_at_utc?: string | null;
  trace_entries?: RequestTraceEntry[];
  snapshot?: RequestTraceSnapshot | null;
};

export type RequestTraceEnvelope = BridgeEnvelope<RequestTraceData>;

export type ResearchSearchRequest = {
  request_id?: string | null;
  ticket_id?: string | null;
  question: string;
  queries: string[];
  max_results_per_query?: number;
  requires_recent_sources?: boolean;
  requires_primary_sources?: boolean;
  requires_peer_reviewed_sources?: boolean;
  allowed_source_types?: string[];
  disallowed_source_types?: string[];
  approval_id?: string | null;
  approval_token?: string | null;
  project_id?: string | null;
  conversation_id?: string | null;
  reasoning_gear?: string;
  research_session_id?: string | null;
  keep_session_open?: boolean;
};

export type ResearchSearchResponse = BridgeEnvelope<Record<string, unknown>>;

export type ResearchFetchRequest = {
  request_id?: string | null;
  ticket_id?: string | null;
  question: string;
  url: string;
  research_session_id?: string | null;
  project_id?: string | null;
  conversation_id?: string | null;
  approval_id?: string | null;
  approval_token?: string | null;
  approval_reference?: string | null;
  approved_by_user?: boolean;
};

export type ResponseTruth = {
  selectedRole?: string | null;
  selectedRuntime?: string;
  selectedModelRuntimeTag?: string;
  stayedLocal: boolean | null;
  usedFallback: boolean | null;
  fallbackFrom?: string;
  fallbackTo?: string;
  approvalNeeded: boolean | null;
  approvalState?: string;
  boundaryState?: string;
  localityState?: string;
  runtimeState?: string;
  invocationStatus?: string;
  blocked: boolean;
  degraded: boolean;
  errors: string[];
  warnings: string[];
};

export type EnvelopeResult<T> = {
  ok: boolean;
  payload: T;
};

export type AccountStatus = "needs_creation" | "logged_in" | "logged_out";

export type AccountStateData = {
  has_user?: boolean;
  is_authenticated?: boolean;
  requires_user_creation?: boolean;
  requires_login?: boolean;
  active_username?: string | null;
  account_status?: AccountStatus | string;
  active_user_id?: string | null;
  account_count?: number | null;
  multiple_accounts_available?: boolean | null;
  active_role?: "installation_owner" | "admin" | "user" | null;
  active_profile_managed?: boolean | null;
  supervision_notice?: string | null;
};

export type AccountColorOption = {
  id: string;
  label: string;
  hex: string;
};

export type ProfilePhotoAsset = {
  asset_id?: string | null;
  mime_type?: string | null;
  extension?: string | null;
  byte_size?: number | null;
  sha256?: string | null;
  preview_available?: boolean | null;
};

export type AccountProfilePrivate = {
  username?: string | null;
  interests?: string | null;
  bio?: string | null;
  birthdate?: string | null;
  emails?: string[];
  phone_number?: string | null;
  social_media?: string[];
  github?: string | null;
  city_state?: string | null;
  profile_color_id?: string | null;
  profile_photo_asset_id?: string | null;
  profile_photo_available?: boolean | null;
  profile_photo?: ProfilePhotoAsset | null;
};

export type ElysiaVisibleProfile = {
  name_or_username?: string | null;
  interests?: string | null;
  bio?: string | null;
  profile_photo_asset_id?: string | null;
  profile_photo_available?: boolean | null;
};

export type AccountCreateRequest = {
  username: string;
  password: string;
  interests?: string;
  bio?: string;
  birthdate?: string | null;
  emails?: string[];
  phone_number?: string | null;
  social_media?: string[];
  github?: string | null;
  city_state?: string | null;
  profile_color_id?: string;
  profile_photo_asset_id?: string | null;
  requested_role?: "admin" | "user";
  managed_profile?: boolean;
};

export type ManagedProfilePolicy = {
  autonomy_maximum: number;
  internet_allowed: boolean;
  addons_allowed: boolean;
  connectors_allowed: boolean;
  coding_execution_allowed: boolean;
  project_agent_limit: number;
  external_mutations_allowed: boolean;
  background_cognition_allowed: boolean;
  cpu_percent_ceiling: number;
  ram_mb_ceiling: number;
  vram_mb_ceiling: number;
  network_filter_level: "standard" | "moderate" | "strict";
  consolidation_allowed: boolean;
  managed_backups_allowed: boolean;
  cold_archive_allowed: boolean;
  storage_budget_mb_ceiling: number;
  backup_retention_maximum: number;
};

export type AdminRosterEntry = {
  user_id: string;
  username: string;
  role: "installation_owner" | "admin" | "user";
  managed: boolean;
  enabled: boolean;
  active_session_count: number;
  policy_version: number;
  created_at_utc: string;
  managed_policy?: ManagedProfilePolicy | null;
};

export type AdminSummaryEnvelope = BridgeEnvelope<{
  installation_authority?: Record<string, unknown>;
  roster?: AdminRosterEntry[];
  events?: Array<Record<string, unknown>>;
  content_authorities_queried?: string[];
  admin_content_access_granted?: boolean;
  local_online_identity_federated?: boolean;
  memory_storage_by_profile?: Array<Record<string, unknown>>;
  metadata_authorities_queried?: string[];
}>;

export type EmergencyStateEnvelope = BridgeEnvelope<{
  contract?: string;
  active?: boolean;
  resume_required?: boolean;
  trigger_id?: string | null;
  triggered_at_utc?: string | null;
  reason?: string | null;
  internet_effectively_enabled?: boolean;
  runtime_autonomy_override?: number;
  cleanup?: Record<string, unknown>;
  restart_recovery_performed?: boolean;
}>;

export type AccountLoginRequest = {
  username: string;
  password: string;
};

export type AccountProfileUpdateRequest = {
  username?: string | null;
  password?: string | null;
  current_password?: string | null;
  interests?: string | null;
  bio?: string | null;
  birthdate?: string | null;
  emails?: string[];
  phone_number?: string | null;
  social_media?: string[];
  github?: string | null;
  city_state?: string | null;
  profile_color_id?: string | null;
  profile_photo_asset_id?: string | null;
};

export type AccountDeleteRequest = {
  current_password: string;
  confirmation_username: string;
};

export type AccountProfileArchiveEnvelope = BridgeEnvelope<{
  archive?: {
    archive_base64?: string;
    archive_sha256?: string;
    archive_size_bytes?: number;
    encrypted?: boolean;
    profile_photo_included?: boolean;
    memory_included?: boolean;
    companion_memory_archive_required_for_memory_recovery?: boolean;
  };
  restored?: boolean;
  profile?: AccountProfilePrivate | null;
  source_username?: string;
  username_changed?: boolean;
  password_changed?: boolean;
  role_or_admin_authority_changed?: boolean;
  memory_restored?: boolean;
}>;

export type AccountDeletionInventory = {
  memory_records?: number;
  shared_spaces?: number;
  project_records?: number;
  conversation_records?: number;
  profile_photo_assets?: number;
  blocking_owned_records?: number;
};

export type AccountPrivacyPolicyView = {
  elysia_visible_fields?: string[];
  sealed_fields?: string[];
  runtime_private_access?: boolean;
  tools_private_access?: boolean;
  workers_private_access?: boolean;
  memory_import_private_profile?: boolean;
  prudence_note?: string | null;
};

export type AccountStateEnvelope = BridgeEnvelope<AccountStateData>;
export type AccountCreateEnvelope = BridgeEnvelope<{
  state?: AccountStateData | null;
  profile?: AccountProfilePrivate | null;
}>;
export type AccountLoginEnvelope = BridgeEnvelope<{
  state?: AccountStateData | null;
}>;
export type AccountLogoutEnvelope = BridgeEnvelope<{
  state?: AccountStateData | null;
  session_revoked?: boolean | null;
}>;
export type AccountDeleteEnvelope = BridgeEnvelope<{
  deleted?: boolean | null;
  state?: AccountStateData | null;
  deletion_inventory?: AccountDeletionInventory | null;
  sessions_removed?: number | null;
  profile_assets_removed?: number | null;
}>;
export type AccountProfileEnvelope = BridgeEnvelope<{
  profile?: AccountProfilePrivate | null;
}>;
export type AccountProfileUpdateEnvelope = BridgeEnvelope<{
  profile?: AccountProfilePrivate | null;
  password_changed?: boolean | null;
}>;
export type AccountVisibleProfileEnvelope = BridgeEnvelope<{
  profile?: ElysiaVisibleProfile | null;
}>;
export type AccountProfilePhotoEnvelope = BridgeEnvelope<{
  profile_photo?: ProfilePhotoAsset | null;
}>;
export type AccountProfilePhotoDeleteEnvelope = BridgeEnvelope<{
  deleted?: boolean | null;
  profile_photo_asset_id?: string | null;
}>;
export type AccountColorsEnvelope = BridgeEnvelope<{
  colors?: AccountColorOption[];
}>;
export type AccountPrivacyEnvelope = BridgeEnvelope<{
  privacy?: AccountPrivacyPolicyView | null;
}>;

export type OnboardingAnswer = {
  question_id: string;
  exact_answer: string;
  proposed_title: string;
  proposed_wording: string;
  privacy: "normal" | "private" | "sealed";
  retention: "persistent" | "temporary" | "not_remembered";
};

export type OnboardingQuestion = {
  question_id: string;
  prompt: string;
};

export type OnboardingSection = {
  section_id: string;
  title: string;
  questions: OnboardingQuestion[];
};

export type OnboardingStateEnvelope = BridgeEnvelope<{
  contract_version?: string;
  status?: string;
  sections?: OnboardingSection[];
  answers?: OnboardingAnswer[];
  answered_count?: number;
  imported_memory_ids?: Record<string, string>;
  account_scoped?: boolean;
  encrypted_at_rest?: boolean;
  external_egress?: boolean;
  canonical_memory_before_review?: boolean;
  may_skip_all?: boolean;
  raw_paths_exposed?: boolean;
}>;

export type SetupStateEnvelope = BridgeEnvelope<{
  contract_version?: string;
  runtime_mode?: string;
  detected_distribution_form?: "deb" | "appimage" | "user_local_desktop" | "onefile_core" | "source";
  distribution_form_locked?: boolean;
  configured?: boolean;
  machine_ready?: boolean;
  setup_required?: boolean;
  status?: string;
  profile_id?: string | null;
  distribution_form?: string | null;
  component_ids?: string[];
  pending_component_ids?: string[];
  component_status?: Record<string, string>;
  machine_installation_separate_from_personal_onboarding?: boolean;
  profile_selection_grants_operation_approval?: boolean;
  raw_paths_exposed?: boolean;
  preview_id?: string;
  approval_token?: string;
  plan_hash?: string;
  ready_to_apply?: boolean;
  warnings?: string[];
  path_truth?: Record<string, unknown>;
  hardware?: Record<string, any>;
  network_preview?: Record<string, unknown>;
  privilege_preview?: Record<string, unknown>;
  system_prerequisites?: SystemPrerequisiteEnvelope["data"];
  unresolved_acquisition_component_ids?: string[];
  acquisition_component_ids?: string[];
  estimated_download_bytes?: number;
  estimated_installed_bytes?: number;
  component_license_preview?: Array<{ component_id?: string; license?: string; redistribution?: string }>;
  dependency_install_dispositions?: {
    dependency_count?: number;
    category_counts?: Record<string, number>;
    category_e_actions?: Array<{
      dependency_id?: string;
      label?: string;
      purpose?: string;
      guidance?: {
        title?: string;
        why?: string;
        official_source?: string;
        signup_required?: string;
        data_leaving_local_control?: string;
        license_privacy_security?: string;
        supported_steps?: string[];
        doctor_detection?: string;
        retry_repair?: string;
      };
    }>;
    system_dependency_count?: number;
    system_category_counts?: Record<string, number>;
    system_category_e_actions?: Array<{
      dependency_id?: string;
      dependency_ids?: string[];
      purposes?: string[];
      kind?: string;
      guidance?: {
        title?: string;
        why?: string;
        official_source?: string;
        signup_required?: string;
        data_leaving_local_control?: string;
        license_privacy_security?: string;
        supported_steps?: string[];
        doctor_detection?: string;
        retry_repair?: string;
      };
    }>;
  };
  blockers?: string[];
  mutation_performed?: boolean;
  doctor_required?: boolean;
  doctor_passed?: boolean;
  doctor_classification?: string | null;
  doctor_degraded_check_ids?: string[];
}>;

export type ComponentInstallEnvelope = BridgeEnvelope<{
  contract_version?: string;
  component_id?: string;
  operation?: "install" | "repair" | "remove";
  status?: string;
  source?: string;
  publisher?: string;
  identity?: string;
  digest?: string;
  license?: string;
  redistribution?: string;
  network?: string;
  privilege?: string;
  estimated_installed_bytes?: number;
  exact_download_bytes?: number;
  exact_installed_input_bytes?: number;
  artifact_count?: number;
  artifact_identities?: Array<Record<string, unknown>>;
  model_plan?: {
    selected_model_ids?: string[];
    models?: Array<Record<string, any>>;
    local_model_vault_adoption?: boolean;
    local_model_vault_verified?: boolean;
    model_exact_download_bytes?: number;
    model_artifact_count?: number;
  };
  preview_id?: string;
  approval_token?: string;
  job_id?: string;
  phase?: string;
  cancellable?: boolean;
  cancellation_accepted?: boolean;
  cleanup_complete?: boolean;
  recoverable?: boolean;
  error_summary?: string;
  raw_paths_exposed?: boolean;
}>;

export type SystemPrerequisiteEnvelope = BridgeEnvelope<{
  contract_version?: string;
  component_ids?: string[];
  dependency_rows?: Array<{
    dependency_id?: string;
    kind?: string;
    purpose?: string;
    present?: boolean;
    installed_package_versions?: Record<string, string>;
    missing_packages?: string[];
    optional?: boolean;
  }>;
  exact_package_operations?: string[];
  package_manager_network_may_be_used?: boolean;
  package_manager_privilege_required?: boolean;
  authorization_mechanism?: string;
  silent_sudo?: boolean;
  full_setup_runs_as_root?: boolean;
  external_missing_dependency_ids?: string[];
  external_missing_guidance?: Array<{
    dependency_id?: string;
    title?: string;
    why?: string;
    official_source?: string;
    signup_required?: string;
    data_leaving_local_control?: string;
    license_privacy_security?: string;
    supported_steps?: string[];
    doctor_detection?: string;
    retry_repair?: string;
  }>;
  preview_id?: string;
  approval_token?: string;
  mutation_performed?: boolean;
  receipt_written?: boolean;
}>;

export type ApplicationLifecycleEnvelope = BridgeEnvelope<{
  contract_version?: string;
  operation?: string;
  installed?: boolean;
  current_release_id?: string | null;
  target_release_id?: string | null;
  incomplete_operation_detected?: boolean;
  incomplete_operation_recovery?: string;
  user_data_preserved?: boolean;
  preview_id?: string;
  approval_token?: string;
  artifact_sha256?: string;
  artifact_size_bytes?: number;
  current_memory_schema?: number;
  target_memory_schema?: number;
  memory_migration_ids?: string[];
  component_changes?: string[];
  local_data_inventory?: { root_count?: number; file_count?: number; exact_bytes?: number };
  private_export_created_before_removal?: boolean;
  applied?: boolean;
  raw_paths_exposed?: boolean;
}>;

export type MarketplaceLinkStatus = {
  linked?: boolean;
  marketplace_user_id?: string | null;
  marketplace_email?: string | null;
  marketplace_username?: string | null;
  linked_at_utc?: string | null;
  last_sync_at_utc?: string | null;
  sync_enabled_fields?: string[];
  allowed_sync_fields?: string[];
  password_stored?: boolean;
  token_stored?: boolean;
  service_role_key_used?: boolean;
  local_private_profile_shared?: boolean;
  local_files_shared?: boolean;
  memory_shared?: boolean;
  request_traces_shared?: boolean;
  dependency_inventory_shared?: boolean;
  runtime_access_allowed?: boolean;
};

export type MarketplaceLinkRequest = {
  marketplace_user_id: string;
  marketplace_email?: string | null;
  marketplace_username?: string | null;
  sync_enabled_fields?: string[];
};

export type MarketplaceProfileSyncRecordRequest = {
  direction?: string;
  fields_synced: string[];
};

export type MarketplaceProfileSyncRecord = {
  recorded?: boolean;
  synced_at_utc?: string;
  direction?: string;
  fields_synced?: string[];
  raw_values_stored?: boolean;
  marketplace_token_received?: boolean;
  marketplace_password_received?: boolean;
  local_private_fields_synced?: boolean;
};

export type MarketplaceLinkEnvelope = BridgeEnvelope<{
  marketplace_link?: MarketplaceLinkStatus | null;
  unlinked?: boolean | null;
  profile_sync?: MarketplaceProfileSyncRecord | null;
}>;

export type AddonActionPlanRequest = {
  addon_id: string;
  addon_name: string;
  publisher?: string | null;
  action: {
    action_key: string;
    action_label: string;
    action_kind: string;
    allowed: boolean;
    risk_level: string;
    requires_local_operator_password: boolean;
    network_access?: boolean;
    notes?: string[];
  };
  dependencies?: Array<{
    ecosystem: string;
    package_name: string;
    source?: string | null;
    version_constraint?: string | null;
    required: boolean;
  }>;
  trust_tier?: string;
  local_only?: boolean;
  network_access?: boolean;
};

export type AddonActionPlan = {
  addon_id?: string;
  addon_name?: string;
  action_key?: string;
  action_label?: string;
  action_kind?: string;
  plan_state?: string;
  execution_enabled?: boolean;
  mutation_allowed?: boolean;
  command_execution_allowed?: boolean;
  package_manager_allowed?: boolean;
  shell_allowed?: boolean;
  subprocess_allowed?: boolean;
  requires_local_operator_password?: boolean;
  operator_approval_required?: boolean;
  requires_future_approval?: boolean;
  trust_tier?: string;
  risk_level?: string;
  network_boundary?: string;
  dependency_count?: number;
  dependency_summary?: string[];
  plan_summary?: string;
  rollback_note?: string;
  refusal_reason?: string;
};

export type AddonActionPlanEnvelope = BridgeEnvelope<{
  addon_action_plan?: AddonActionPlan | null;
}>;

export type AddonPackagePathRequest = {
  package_path: string;
  source?: string;
  plan_id?: string;
  plan_hash?: string;
  approval_id?: string;
  approval_token?: string;
};

export type AddonStatusChangeRequest = {
  addon_id: string;
  version: string;
  reason?: string | null;
  plan_id?: string;
  plan_hash?: string;
  approval_id?: string;
  approval_token?: string;
};

export type AddonTransitionAction =
  | "install_disabled"
  | "enable_limited"
  | "disable"
  | "revoke"
  | "remove";

export type AddonTransitionPlanRequest = {
  action: AddonTransitionAction;
  package_path?: string;
  addon_id?: string;
  version?: string;
  expected_state?: string;
  expected_package_hash?: string;
  approved_permissions?: string[];
  actor?: string;
  reason?: string;
  source?: string;
};

export type AddonTransitionApprovalRequest = {
  plan_id: string;
  plan_hash: string;
  operator_confirmed: boolean;
  actor?: string;
  confirmation: string;
};

export type AddonTransitionApplyRequest = {
  plan_id: string;
  plan_hash: string;
  approval_id: string;
  approval_token: string;
};

export type DeveloperAddonPackagePlanRequest = {
  source_kind: "local_project" | "local_folder" | "local_repository" | "source_bundle" | "external_tool_output";
  manifest: Record<string, unknown>;
  files: Array<{
    relative_path: string;
    size_bytes: number;
    sha256?: string;
    kind: "text" | "source" | "binary" | "archive" | "document" | "unknown";
  }>;
  output_name?: string;
  actor?: string;
};

export type MarketplaceAddonSubmissionPreviewRequest = {
  addon_id: string;
  version: string;
  package_hash: string;
  source_kind: "elysia_addon" | "source_bundle" | "browser_folder" | "browser_repository" | "git_url_metadata";
  publisher_identity: string;
  file_count?: number;
  total_size_bytes?: number;
  dependency_count?: number;
  requested_permissions?: string[];
  static_scan_passed: boolean;
  privacy_notice_acknowledged: boolean;
  actor?: string;
};

export type MarketplaceAddonReviewPreviewRequest = {
  addon_id: string;
  version: string;
  package_hash: string;
  publisher_identity: string;
  requested_permissions?: string[];
  dependency_count?: number;
  reviewer: string;
  decision: "approved" | "rejected";
  permission_review_complete: boolean;
  compatibility_review_complete: boolean;
  dependency_review_complete: boolean;
  license_provenance_review_complete: boolean;
  static_scan_passed: boolean;
  known_risks?: string[];
  sandbox_result?: "not_performed" | "passed" | "blocked" | "failed";
  test_environment_label?: string;
};

export type AddonInstallerEnvelope = BridgeEnvelope<{
  addons_status?: Record<string, unknown>;
  installed_addons?: Array<Record<string, unknown>>;
  inspection?: Record<string, unknown>;
  install_plan?: Record<string, unknown>;
  install_result?: Record<string, unknown>;
  transition_plan?: Record<string, unknown>;
  transition_approval?: Record<string, unknown>;
  transition_result?: Record<string, unknown>;
  package_preparation_plan?: Record<string, unknown>;
  submission_preview?: Record<string, unknown>;
  review_preview?: Record<string, unknown>;
  official_candidates?: Array<Record<string, unknown>>;
  operation_result?: Record<string, unknown>;
  sandbox_result?: Record<string, unknown>;
  audit_records?: Array<Record<string, unknown>>;
  intent?: Record<string, unknown> | null;
}>;

const BRIDGE_BASE_URL = "http://127.0.0.1:8000";
const CHAT_SEND_PATH = "/chat/send";
const CONVERSATION_LIST_PATH = "/conversations";
const PROJECTS_PATH = "/projects";
const PROJECT_SELECT_PATH = `${PROJECTS_PATH}/select`;
const REQUEST_TRACE_PATH = "/request-trace";
const ARTIFACTS_PATH = "/artifacts";
const GOVERNANCE_STATE_PATH = "/governance/state";
const GOVERNANCE_CHANGES_PATH = "/governance/changes";
const APPROVAL_RESOLVE_PATH = "/approval/resolve";
const MEMORY_SUMMARY_PATH = "/memory/summary";
const MEMORY_ITEMS_PATH = "/memory/items";
const FILES_PATH = "/files";
const RESEARCH_SEARCH_PATH = "/research/search";
const RESEARCH_FETCH_PATH = "/research/fetch";
const ACCOUNT_PATH = "/account";
const ONBOARDING_PATH = "/onboarding";
const MARKETPLACE_PATH = "/marketplace";
const ADDON_ACTIONS_PATH = "/addon-actions";
const ADDONS_PATH = "/addons";
const CODING_PATH = "/coding";
const CODING_FILE_PATH = `${CODING_PATH}/file`;
const CODING_PATCH_PATH = `${CODING_PATH}/patch`;
const CODING_DOCUMENT_PATH = `${CODING_PATH}/document`;
const CODING_DATA_PATH = `${CODING_PATH}/data`;
const CODING_VISUAL_PATH = `${CODING_PATH}/visual`;
const CODING_MEDIA_PATH = `${CODING_PATH}/media`;
const CODING_ARCHIVE_PATH = `${CODING_PATH}/archive`;
const CODING_DATABASE_PATH = `${CODING_PATH}/database`;
const CODING_BINARY_PATH = `${CODING_PATH}/binary`;
const CODING_ENGINEERING_PATH = `${CODING_PATH}/engineering`;
const CODING_OPERATION_PATH = `${CODING_PATH}/operation`;

function buildConversationListPath(
  options?: FetchConversationListOptions
): string {
  const searchParams = new URLSearchParams();

  if (options?.includeArchived) {
    searchParams.set("include_archived", "true");
  }

  if (
    typeof options?.limit === "number" &&
    Number.isFinite(options.limit) &&
    options.limit > 0
  ) {
    searchParams.set("limit", String(Math.trunc(options.limit)));
  }

  const query = searchParams.toString();
  return query ? `${CONVERSATION_LIST_PATH}?${query}` : CONVERSATION_LIST_PATH;
}

function buildMemorySummaryPath(
  options?: FetchMemorySummaryOptions
): string {
  const searchParams = new URLSearchParams();

  if (options?.projectId) {
    searchParams.set("project_id", options.projectId);
  }

  if (options?.conversationId) {
    searchParams.set("conversation_id", options.conversationId);
  }

  const query = searchParams.toString();
  return query ? `${MEMORY_SUMMARY_PATH}?${query}` : MEMORY_SUMMARY_PATH;
}

function buildMemoryItemsPath(
  options?: FetchMemoryItemsOptions
): string {
  const searchParams = new URLSearchParams();

  if (options?.projectId) {
    searchParams.set("project_id", options.projectId);
  }

  if (options?.conversationId) {
    searchParams.set("conversation_id", options.conversationId);
  }

  if (options?.searchQuery?.trim()) {
    searchParams.set("search", options.searchQuery.trim());
  }

  if (options?.scope) {
    searchParams.set("scope", options.scope);
  }

  if (options?.form) {
    searchParams.set("form", options.form);
  }
  if (options?.activationTier) {
    searchParams.set("activation_tier", options.activationTier);
  }

  if (options?.memoryClass) {
    if (["conversation", "project", "research", "operational"].includes(options.memoryClass)) {
      searchParams.set("scope", options.memoryClass);
    } else if (options.memoryClass === "working") {
      searchParams.set("status", "working");
    } else if (options.memoryClass === "audit") {
      searchParams.set("form", "audit");
    } else if (options.memoryClass === "sealed_private") {
      searchParams.set("privacy", "sealed");
    } else if (options.memoryClass === "preference") {
      searchParams.set("form", "semantic");
    }
  }

  if (options?.sensitivity) {
    searchParams.set(
      "privacy",
      options.sensitivity === "sealed"
        ? "sealed"
        : options.sensitivity === "private"
          ? "private"
          : "normal"
    );
  }

  if (options?.mutability) {
    searchParams.set("mutability", options.mutability);
  }

  if (options?.status) {
    searchParams.set(
      "status",
      options.status === "provisional" ? "candidate" : options.status
    );
  }

  if (
    typeof options?.limit === "number" &&
    Number.isFinite(options.limit) &&
    options.limit > 0
  ) {
    searchParams.set("limit", String(Math.trunc(options.limit)));
  }

  if (
    typeof options?.offset === "number" &&
    Number.isFinite(options.offset) &&
    options.offset >= 0
  ) {
    searchParams.set("offset", String(Math.trunc(options.offset)));
  }

  const query = searchParams.toString();
  return query ? `${MEMORY_ITEMS_PATH}?${query}` : MEMORY_ITEMS_PATH;
}

function buildProjectListPath(
  options?: FetchProjectListOptions
): string {
  const searchParams = new URLSearchParams();

  if (
    typeof options?.limit === "number" &&
    Number.isFinite(options.limit) &&
    options.limit > 0
  ) {
    searchParams.set("limit", String(Math.trunc(options.limit)));
  }

  const query = searchParams.toString();
  return query ? `${PROJECTS_PATH}?${query}` : PROJECTS_PATH;
}

function buildProjectDetailPath(projectId: string): string {
  return `${PROJECTS_PATH}/${encodeURIComponent(projectId)}`;
}

function buildConversationThreadPath(conversationId: string): string {
  return `${CONVERSATION_LIST_PATH}/${encodeURIComponent(conversationId)}`;
}

function buildConversationUpdatePath(conversationId: string): string {
  return `${CONVERSATION_LIST_PATH}/${encodeURIComponent(conversationId)}`;
}

function buildConversationDeletePath(conversationId: string): string {
  return `${CONVERSATION_LIST_PATH}/${encodeURIComponent(conversationId)}`;
}

function buildRequestTracePath(requestId: string): string {
  return `${REQUEST_TRACE_PATH}/${encodeURIComponent(requestId)}`;
}

function buildArtifactListPath(options?: {
  projectId?: string | null;
  requestId?: string | null;
  conversationId?: string | null;
  artifactType?: string | null;
  limit?: number | null;
}): string {
  const searchParams = new URLSearchParams();
  if (options?.projectId) searchParams.set("project_id", options.projectId);
  if (options?.requestId) searchParams.set("request_id", options.requestId);
  if (options?.conversationId) searchParams.set("conversation_id", options.conversationId);
  if (options?.artifactType) searchParams.set("artifact_type", options.artifactType);
  if (typeof options?.limit === "number" && Number.isFinite(options.limit) && options.limit > 0) {
    searchParams.set("limit", String(Math.trunc(options.limit)));
  }
  const query = searchParams.toString();
  return query ? `${ARTIFACTS_PATH}?${query}` : ARTIFACTS_PATH;
}

function buildFileStatusPath(fileId: string): string {
  return `${FILES_PATH}/${encodeURIComponent(fileId)}/status`;
}

function buildFileContextSummaryPath(fileId: string): string {
  return `${FILES_PATH}/${encodeURIComponent(fileId)}/context-summary`;
}

export function newRequestId(prefix = "req"): string {
  if (
    typeof globalThis !== "undefined" &&
    "crypto" in globalThis &&
    typeof globalThis.crypto?.randomUUID === "function"
  ) {
    return `${prefix}_${globalThis.crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
  }

  const fallback = Math.random().toString(16).slice(2, 18).padEnd(16, "0");
  return `${prefix}_${fallback}`;
}

function getRequestMethod(init?: RequestInit): string {
  const method = init?.method?.toUpperCase();
  return method && method.length > 0 ? method : "GET";
}

function buildBridgeUrl(path: string): string {
  return `${BRIDGE_BASE_URL}${path}`;
}

function shouldLogBridgeClientDebug(): boolean {
  try {
    return Boolean(import.meta.env?.DEV);
  } catch {
    return false;
  }
}

function logBridgeClientFailure(
  message: string,
  context: {
    method: string;
    path: string;
    url: string;
    error?: unknown;
    statusCode?: number;
    responseBodyLength?: number;
  }
): void {
  if (!shouldLogBridgeClientDebug()) {
    return;
  }

  console.error("[bridgeClient]", message, context);
}

function normalizeThrownMessage(error: unknown): string {
  if (error instanceof Error) {
    const trimmed = error.message.trim();
    if (trimmed) {
      return trimmed;
    }
  }

  return "Unknown bridge request error.";
}

function buildFetchFailureMessage(
  method: string,
  path: string,
  error: unknown,
  nativeSession: NativeLocalApiSession | null
): string {
  if (nativeSession?.lifecycleState === "launcher_missing") {
    return `${method} ${path} could not reach the packaged local API because the Core launcher is not installed. Run the user-local Core installer, then verify the install.`;
  }
  if (nativeSession?.lifecycleState === "launcher_failed") {
    return `${method} ${path} could not reach the packaged local API because the fixed Core launcher did not become ready. Run the non-repairing install verifier for sanitized details.`;
  }
  if (nativeSession?.lifecycleState === "port_conflict") {
    return `${method} ${path} refused an unowned loopback listener. Close stale Elysia processes and relaunch; the Desktop will select its own bounded local API port.`;
  }
  if (nativeSession?.lifecycleState === "unverified_listener") {
    return `${method} ${path} found an unverified loopback listener without usable Elysia authentication. Elysia will not replace or trust it.`;
  }
  const originalMessage = normalizeThrownMessage(error);

  if (nativeSession) {
    return `${method} ${path} failed in the native Desktop-to-local-API bridge. The Core listener state is ${nativeSession.lifecycleState}. Run Elysia Doctor for sanitized package and XDG readiness details. Original error: ${originalMessage}`;
  }

  return `${method} ${path} failed before any bridge response was received. This usually means a network, preflight, CORS, desktop-webview, or fetch-layer failure. Original error: ${originalMessage}`;
}

function buildNonJsonFailureMessage(
  method: string,
  path: string,
  statusCode: number
): string {
  return `${method} ${path} returned a non-JSON response from the bridge (HTTP ${statusCode}).`;
}

type NativeLocalApiSession = {
  runtimeMode: string;
  lifecycleState: string;
  baseUrl: string;
  authenticationRequired: boolean;
  authenticationState: string;
  rawPathExposed: boolean;
};

type NativeLocalApiResponse = {
  statusCode: number;
  body: string;
  contentType: string;
};

let nativeLocalApiSessionPromise: Promise<NativeLocalApiSession | null> | null = null;

function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in window
  );
}

async function resolveNativeLocalApiSession(): Promise<NativeLocalApiSession | null> {
  if (!isTauriRuntime()) {
    return null;
  }
  if (!nativeLocalApiSessionPromise) {
    nativeLocalApiSessionPromise = invoke<NativeLocalApiSession>("local_api_session").catch(
      () => {
        nativeLocalApiSessionPromise = null;
        return null;
      }
    );
  }
  return nativeLocalApiSessionPromise;
}

async function buildRequestHeaders(init?: RequestInit): Promise<HeadersInit> {
  return {
    Accept: "application/json",
    "X-Elysia-Client": "elysia-desktop/1.0.0",
    ...(init?.body ? { "Content-Type": "application/json" } : {}),
    ...(init?.headers ?? {})
  };
}

async function requestEnvelope<T>(
  path: string,
  init?: RequestInit
): Promise<EnvelopeResult<T>> {
  const method = getRequestMethod(init);
  const url = buildBridgeUrl(path);

  try {
    const nativeResponse = isTauriRuntime()
      ? await invoke<NativeLocalApiResponse>("local_api_request", {
          method,
          path,
          body: typeof init?.body === "string" ? init.body : null
        })
      : null;
    let responseOk: boolean;
    let responseStatus: number;
    let raw: string;
    if (nativeResponse) {
      responseOk = nativeResponse.statusCode >= 200 && nativeResponse.statusCode < 300;
      responseStatus = nativeResponse.statusCode;
      raw = nativeResponse.body;
    } else {
      const response = await fetch(url, {
        ...init,
        headers: await buildRequestHeaders(init)
      });
      responseOk = response.ok;
      responseStatus = response.status;
      raw = await response.text();
    }

    let payload: T;
    try {
      payload = raw ? (JSON.parse(raw) as T) : ({} as T);
    } catch {
      const errorMessage = buildNonJsonFailureMessage(method, path, responseStatus);

      logBridgeClientFailure(errorMessage, {
        method,
        path,
        url,
        statusCode: responseStatus,
        responseBodyLength: raw.length
      });

      payload = {
        status: "error",
        errors: [errorMessage]
      } as T;
    }

    return {
      ok: responseOk,
      payload
    };
  } catch (error) {
    const nativeSession = await resolveNativeLocalApiSession();
    const errorMessage = buildFetchFailureMessage(method, path, error, nativeSession);

    logBridgeClientFailure(errorMessage, {
      method,
      path,
      url,
      error
    });

    return {
      ok: false,
      payload: {
        status: "error",
        errors: [errorMessage]
      } as T
    };
  }
}

async function fetchEnvelope<T>(
  path: string,
  init?: RequestInit
): Promise<EnvelopeResult<T>> {
  return requestEnvelope<T>(path, {
    method: "GET",
    cache: "no-store",
    ...(init ?? {})
  });
}

async function postEnvelope<TResponse>(
  path: string,
  body: unknown
): Promise<EnvelopeResult<TResponse>> {
  return requestEnvelope<TResponse>(path, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

async function patchEnvelope<TResponse>(
  path: string,
  body: unknown
): Promise<EnvelopeResult<TResponse>> {
  return requestEnvelope<TResponse>(path, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

async function deleteEnvelope<TResponse>(
  path: string
): Promise<EnvelopeResult<TResponse>> {
  return requestEnvelope<TResponse>(path, {
    method: "DELETE"
  });
}

export function readResponseTruth(
  envelope?: Partial<BridgeEnvelope<TruthBearingFields>>
): ResponseTruth {
  const data = envelope?.data ?? {};
  const topErrors = envelope?.errors ?? [];
  const topWarnings = envelope?.warnings ?? [];

  const blockedReasons = data.blocked_reasons ?? [];
  const degradedReasons = data.degraded_reasons ?? [];

  const localityState = envelope?.locality_state ?? envelope?.locality;

  const stayedLocal =
    typeof data.stayed_local === "boolean"
      ? data.stayed_local
      : localityState === "local"
        ? true
        : localityState === "external" || localityState === "crossed_boundary"
          ? false
          : null;

  const usedFallback =
    typeof data.used_fallback === "boolean"
      ? data.used_fallback
      : envelope?.fallback_state === "used"
        ? true
        : envelope?.fallback_state === "not_used"
          ? false
          : null;

  const approvalNeeded =
    typeof data.approval_needed === "boolean"
      ? data.approval_needed
      : envelope?.approval_state === "needed"
        ? true
        : envelope?.approval_state === "not_needed"
          ? false
          : null;

  const blocked =
    data.blocked === true ||
    envelope?.status === "blocked" ||
    envelope?.capability_state === "blocked" ||
    envelope?.boundary_state === "blocked";

  const degraded =
    data.degraded === true ||
    envelope?.status === "degraded" ||
    envelope?.status === "unavailable" ||
    envelope?.capability_state === "degraded" ||
    envelope?.capability_state === "unavailable" ||
    data.runtime_state === "degraded";

  return {
    selectedRole: data.selected_role ?? data.selected_model_role,
    selectedRuntime: data.selected_runtime,
    selectedModelRuntimeTag: data.selected_model_runtime_tag,
    stayedLocal,
    usedFallback,
    fallbackFrom: data.fallback_from,
    fallbackTo: data.fallback_to,
    approvalNeeded,
    approvalState: envelope?.approval_state,
    boundaryState: envelope?.boundary_state,
    localityState,
    runtimeState: data.runtime_state,
    invocationStatus: data.invocation_status,
    blocked,
    degraded,
    errors: [...topErrors, ...blockedReasons],
    warnings: [...topWarnings, ...degradedReasons]
  };
}

function readEnvelopePrimaryMessage(
  envelope?: Partial<BridgeEnvelope<Record<string, unknown>>>
): string | null {
  const message = envelope?.message?.trim();
  if (message) {
    return message;
  }

  const error = envelope?.errors?.find(
    (value) => typeof value === "string" && value.trim()
  );
  if (error) {
    return error.trim();
  }

  const warning = envelope?.warnings?.find(
    (value) => typeof value === "string" && value.trim()
  );
  if (warning) {
    return warning.trim();
  }

  return null;
}

export function toQuickInvokeBridgeResult(
  result: EnvelopeResult<ChatSendEnvelope>
): QuickInvokeBridgeResult {
  const envelope = result.payload;
  const truth = readResponseTruth(envelope);
  const responseText = envelope?.data?.response_text ?? null;
  const requestId =
    envelope?.data?.trace_summary?.request_id ??
    envelope?.request_id ??
    null;

  const primaryMessage =
    readEnvelopePrimaryMessage(envelope) ??
    truth.errors[0] ??
    truth.warnings[0] ??
    null;

  let status: QuickInvokeBridgeResultStatus = "ok";

  if (truth.blocked) {
    status = "blocked";
  } else if (
    envelope?.status === "unavailable" ||
    envelope?.capability_state === "unavailable"
  ) {
    status = "unavailable";
  } else if (
    envelope?.status === "error" ||
    result.ok === false
  ) {
    status = "error";
  } else if (truth.degraded) {
    status = "degraded";
  }

  return {
    status,
    responseText,
    errorMessage: primaryMessage,
    requestId,
    envelope,
    truth
  };
}

export async function fetchBridgeHealth(): Promise<
  EnvelopeResult<BridgeHealthEnvelope>
> {
  return fetchEnvelope<BridgeHealthEnvelope>("/status/health");
}

export async function fetchRuntimeStatus(): Promise<
  EnvelopeResult<RuntimeStatusEnvelope>
> {
  return fetchEnvelope<RuntimeStatusEnvelope>("/status/runtime");
}

export async function fetchInvokerStatus(): Promise<
  EnvelopeResult<InvokerStatusEnvelope>
> {
  return fetchEnvelope<InvokerStatusEnvelope>("/status/invoker");
}

export async function fetchCapabilityManifest(): Promise<
  EnvelopeResult<CapabilityManifestEnvelope>
> {
  return fetchEnvelope<CapabilityManifestEnvelope>("/status/capabilities");
}

export async function fetchInstallProfileStatus(): Promise<
  EnvelopeResult<InstallProfileStatusEnvelope>
> {
  return fetchEnvelope<InstallProfileStatusEnvelope>("/status/profiles");
}

export async function fetchInstallDoctorStatus(): Promise<
  EnvelopeResult<InstallDoctorStatusEnvelope>
> {
  return fetchEnvelope<InstallDoctorStatusEnvelope>("/status/doctor");
}

export async function fetchCognitionStatus(): Promise<
  EnvelopeResult<CognitionStatusEnvelope>
> {
  return fetchEnvelope<CognitionStatusEnvelope>("/cognition/status");
}

export async function probeLocalApiAuthentication(): Promise<
  EnvelopeResult<BridgeEnvelope<Record<string, unknown>>>
> {
  return postEnvelope<BridgeEnvelope<Record<string, unknown>>>(
    "/install/auth/probe",
    {}
  );
}

export async function fetchGovernanceState(): Promise<
  EnvelopeResult<GovernanceStateEnvelope>
> {
  return fetchEnvelope<GovernanceStateEnvelope>(GOVERNANCE_STATE_PATH);
}

export async function planGovernanceChange(
  request: GovernanceChangePlanRequest
): Promise<EnvelopeResult<GovernanceMutationEnvelope>> {
  return postEnvelope<GovernanceMutationEnvelope>(
    `${GOVERNANCE_CHANGES_PATH}/plan`,
    request
  );
}

export async function applyGovernanceChange(
  request: GovernanceChangeApplyRequest
): Promise<EnvelopeResult<GovernanceMutationEnvelope>> {
  return postEnvelope<GovernanceMutationEnvelope>(
    `${GOVERNANCE_CHANGES_PATH}/apply`,
    request
  );
}

export async function restoreGovernanceChange(
  request: GovernanceRestoreRequest
): Promise<EnvelopeResult<GovernanceMutationEnvelope>> {
  return postEnvelope<GovernanceMutationEnvelope>(
    `${GOVERNANCE_CHANGES_PATH}/restore`,
    request
  );
}

export async function resolveGovernanceApproval(
  request: ApprovalResolveRequest
): Promise<EnvelopeResult<ApprovalResolveEnvelope>> {
  return postEnvelope<ApprovalResolveEnvelope>(APPROVAL_RESOLVE_PATH, request);
}

export async function fetchMemorySummary(
  options?: FetchMemorySummaryOptions
): Promise<EnvelopeResult<MemorySummaryEnvelope>> {
  return fetchEnvelope<MemorySummaryEnvelope>(
    buildMemorySummaryPath(options)
  );
}

export async function fetchMemoryItems(
  options?: FetchMemoryItemsOptions
): Promise<EnvelopeResult<MemoryItemsEnvelope>> {
  return fetchEnvelope<MemoryItemsEnvelope>(
    buildMemoryItemsPath(options)
  );
}

export async function createMemory(
  request: MemoryCreateRequest,
  candidate = false
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    candidate ? "/memory/candidates" : MEMORY_ITEMS_PATH,
    request
  );
}

export async function correctMemory(
  memoryId: string,
  body: string,
  reason: string,
  title?: string,
  changeKind: "correction" | "refinement" | "changed_reality" | "direct_contradiction" | "retraction" = "correction"
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `${MEMORY_ITEMS_PATH}/${encodeURIComponent(memoryId)}/correct`,
    { body, reason, title, change_kind: changeKind }
  );
}

export async function fetchMemoryRevisions(
  memoryId: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>(
    `${MEMORY_ITEMS_PATH}/${encodeURIComponent(memoryId)}/revisions`
  );
}

export async function setMemoryArchived(
  memoryId: string,
  archived: boolean,
  reason: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `${MEMORY_ITEMS_PATH}/${encodeURIComponent(memoryId)}/${archived ? "archive" : "restore"}`,
    { reason }
  );
}

export async function pinMemory(
  memoryId: string,
  pinned: boolean
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return requestEnvelope<MemoryActionEnvelope>(
    `${MEMORY_ITEMS_PATH}/${encodeURIComponent(memoryId)}/pin`,
    { method: "PUT", body: JSON.stringify({ pinned }) }
  );
}

export async function decideMemoryCandidate(
  memoryId: string,
  decision: "approve" | "reject" | "defer" | "seal",
  reason: string,
  extras: Record<string, unknown> = {}
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `${MEMORY_ITEMS_PATH}/${encodeURIComponent(memoryId)}/candidate-decision`,
    { decision, reason, ...extras }
  );
}

export async function previewMemoryConsequence(
  targetId: string,
  request: Record<string, unknown>
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `/memory/targets/${encodeURIComponent(targetId)}/consequences/preview`,
    request
  );
}

export async function applyMemoryConsequence(
  targetId: string,
  approvalId: string,
  approvalToken: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `/memory/targets/${encodeURIComponent(targetId)}/consequences/apply`,
    { approval_id: approvalId, approval_token: approvalToken }
  );
}

export async function unlockSealedMemory(
  password: string,
  ttlSeconds: number
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/sealed/unlock", {
    password,
    ttl_seconds: ttlSeconds
  });
}

export async function relockSealedMemory(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/sealed/relock", {});
}

export async function fetchMemoryReceipts(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/receipts");
}

export async function fetchMemoryPendingApprovals(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/approvals/pending");
}

export async function fetchMemorySpaces(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/spaces");
}

export async function fetchMemorySpaceInvitations(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/spaces/invitations");
}

export async function respondMemorySpaceInvitation(
  invitationId: string,
  decision: "accept" | "decline"
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `/memory/spaces/invitations/${encodeURIComponent(invitationId)}/respond`,
    { decision }
  );
}

export async function createMemorySpace(
  label: string,
  description: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/spaces", { label, description });
}

export async function fetchMemorySettings(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/settings");
}

export async function updateMemorySettings(
  settings: MemoryFoundationalSettings
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return requestEnvelope<MemoryActionEnvelope>("/memory/settings", {
    method: "PUT",
    body: JSON.stringify(settings)
  });
}

export async function fetchEmergencyState(): Promise<EnvelopeResult<EmergencyStateEnvelope>> {
  return fetchEnvelope<EmergencyStateEnvelope>("/emergency/status");
}

export async function activateEmergencyStop(
  reason = "Operator emergency stop"
): Promise<EnvelopeResult<EmergencyStateEnvelope>> {
  if (isTauriRuntime()) {
    try {
      const response = await invoke<NativeLocalApiResponse>("emergency_stop_owned", { reason });
      const payload = JSON.parse(response.body) as EmergencyStateEnvelope;
      return { ok: response.statusCode >= 200 && response.statusCode < 300 && payload.status === "ok", payload };
    } catch {
      // The native command performs its hard owned-process fallback before it
      // rejects. Return the durable status through the normal bridge if the
      // local API recovered quickly enough to answer.
    }
  }
  return postEnvelope<EmergencyStateEnvelope>("/emergency/stop", { reason });
}

export async function resetEmergencyStop(): Promise<EnvelopeResult<EmergencyStateEnvelope>> {
  return postEnvelope<EmergencyStateEnvelope>("/emergency/reset", {
    acknowledge_safe_restart: true
  });
}

export async function fetchMemoryHealth(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/health");
}

export async function fetchMemoryMigrationStatus(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/migration/status");
}

export async function applyMemoryMigration(
  password: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/migration/apply", { password });
}

export async function fetchMemoryBackupStatus(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/backup/status");
}

export async function moveMemoryTier(
  memoryId: string,
  tier: "working" | "hot" | "warm" | "cold" | "archived",
  reason: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return requestEnvelope<MemoryActionEnvelope>(
    `/memory/items/${encodeURIComponent(memoryId)}/tier`,
    { method: "PUT", body: JSON.stringify({ tier, reason, automatic: false }) }
  );
}

export async function setMemoryAutomaticRecall(
  memoryId: string,
  suppressed: boolean,
  reason: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return requestEnvelope<MemoryActionEnvelope>(
    `/memory/items/${encodeURIComponent(memoryId)}/automatic-recall`,
    { method: "PUT", body: JSON.stringify({ suppressed, reason }) }
  );
}

export async function fetchMemoryTierHistory(memoryId: string): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>(
    `/memory/items/${encodeURIComponent(memoryId)}/tier-history`
  );
}

export async function fetchMemoryGraph(memoryId: string): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>(
    `/memory/items/${encodeURIComponent(memoryId)}/graph`
  );
}

export async function applyMemoryFormAction(
  memoryId: string,
  request: Record<string, unknown>
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `/memory/items/${encodeURIComponent(memoryId)}/form-action`, request
  );
}

export async function addMemoryRelation(
  memoryId: string,
  request: Record<string, unknown>
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(
    `/memory/items/${encodeURIComponent(memoryId)}/relations`, request
  );
}

export async function fetchMemoryBeliefExplanation(
  memoryId: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>(
    `/memory/items/${encodeURIComponent(memoryId)}/belief-explanation`
  );
}

export async function fetchMemoryHomeostasis(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/homeostasis");
}

export async function fetchDueProspectiveMemory(
  horizonHours = 168
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>(
    `/memory/prospective/due?horizon_hours=${encodeURIComponent(String(horizonHours))}`
  );
}

export async function fetchMemoryJobs(): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return fetchEnvelope<MemoryActionEnvelope>("/memory/jobs");
}

export async function createMemoryJob(jobKind: string): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/jobs", { job_kind: jobKind });
}

export async function runMemoryJob(jobId: string): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(`/memory/jobs/${encodeURIComponent(jobId)}/run`, {});
}

export async function cancelMemoryJob(jobId: string): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>(`/memory/jobs/${encodeURIComponent(jobId)}/cancel`, {});
}

export async function exportMemoryArchive(
  recoveryMaterial: string,
  archiveKind: "portable_export" | "managed_backup" = "portable_export",
  scope: "full_account" | "selected_project" | "selected_space" | "metadata_audit" = "full_account",
  selectedAuthorityId?: string | null
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/archives/export", {
    recovery_material: recoveryMaterial,
    archive_kind: archiveKind,
    scope,
    selected_authority_id: selectedAuthorityId ?? null
  });
}

export async function previewMemoryArchiveRestore(
  archiveBase64: string,
  recoveryMaterial: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/archives/restore/preview", {
    archive_base64: archiveBase64,
    recovery_material: recoveryMaterial
  });
}

export async function applyMemoryArchiveRestore(
  restorePlanId: string,
  approvalId: string,
  approvalToken: string,
  recoveryMaterial: string
): Promise<EnvelopeResult<MemoryActionEnvelope>> {
  return postEnvelope<MemoryActionEnvelope>("/memory/archives/restore/apply", {
    restore_plan_id: restorePlanId,
    approval_id: approvalId,
    approval_token: approvalToken,
    recovery_material: recoveryMaterial
  });
}

export async function fetchProjectList(
  options?: FetchProjectListOptions
): Promise<EnvelopeResult<ProjectListEnvelope>> {
  return fetchEnvelope<ProjectListEnvelope>(
    buildProjectListPath(options)
  );
}

export async function createProject(
  request: ProjectCreateRequest
): Promise<EnvelopeResult<ProjectCreateEnvelope>> {
  return postEnvelope<ProjectCreateEnvelope>(PROJECTS_PATH, request);
}

export async function deleteProject(
  projectId: string
): Promise<EnvelopeResult<ProjectDeleteEnvelope>> {
  return deleteEnvelope<ProjectDeleteEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}`
  );
}

export async function fetchProjectDetail(
  projectId: string
): Promise<EnvelopeResult<ProjectDetailEnvelope>> {
  return fetchEnvelope<ProjectDetailEnvelope>(
    buildProjectDetailPath(projectId)
  );
}

export async function updateProject(
  projectId: string,
  patch: ProjectUpdatePatch
): Promise<EnvelopeResult<ProjectUpdateEnvelope>> {
  return patchEnvelope<ProjectUpdateEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}`,
    patch
  );
}

export async function fetchProjectContinuity(
  projectId: string
): Promise<EnvelopeResult<ProjectContinuityEnvelope>> {
  return fetchEnvelope<ProjectContinuityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/continuity`
  );
}

export async function fetchArtifacts(options?: {
  projectId?: string | null;
  requestId?: string | null;
  conversationId?: string | null;
  artifactType?: string | null;
  limit?: number | null;
}): Promise<EnvelopeResult<ArtifactListEnvelope>> {
  return fetchEnvelope<ArtifactListEnvelope>(buildArtifactListPath(options));
}

export async function fetchArtifactDetail(
  artifactId: string
): Promise<EnvelopeResult<ArtifactDetailEnvelope>> {
  return fetchEnvelope<ArtifactDetailEnvelope>(
    `${ARTIFACTS_PATH}/${encodeURIComponent(artifactId)}`
  );
}

export async function selectProject(
  request: ProjectSelectionRequest
): Promise<EnvelopeResult<ProjectSelectionEnvelope>> {
  return postEnvelope<ProjectSelectionEnvelope>(
    PROJECT_SELECT_PATH,
    request
  );
}

export async function fetchProjectWorkbench(
  projectId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return fetchEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/workbench`
  );
}

export async function attachProjectSource(
  projectId: string,
  sourcePath: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/sources`,
    { source_path: sourcePath }
  );
}

export async function createProjectStudyPlan(
  projectId: string,
  request: { topic: string; goals?: string[]; source_material: string; difficulty?: string }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/study-plans`,
    request
  );
}

export async function reviewProjectStudyModule(
  projectId: string,
  studyPlanId: string,
  moduleId: string,
  request: { action: "start" | "complete" | "needs_review" | "reset"; reflection?: string; confidence?: number }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/study-plans/${encodeURIComponent(studyPlanId)}/modules/${encodeURIComponent(moduleId)}/review`,
    request
  );
}

export async function recordProjectResearchIteration(
  projectId: string,
  request: { investigation_id?: string; question: string; query: string; evidence_packets?: Array<Record<string, unknown>>; evidence_verified?: boolean }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/research/iterations`,
    request
  );
}

export async function transitionProjectResearch(
  projectId: string,
  investigationId: string,
  action: "pause" | "resume" | "complete" | "cancel"
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/research/${encodeURIComponent(investigationId)}/transition`,
    { action }
  );
}

export async function createProjectQuiz(
  projectId: string,
  request: { title?: string; source_material: string; difficulty?: string; question_count?: number }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/quizzes`,
    request
  );
}

export async function answerProjectQuiz(
  projectId: string,
  quizId: string,
  request: { question_id: string; answer: string }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/quizzes/${encodeURIComponent(quizId)}/answers`,
    request
  );
}

export async function createProjectGoal(
  projectId: string,
  request: { goal: string; steps?: string[]; budget_steps?: number; budget_minutes?: number }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/goals`,
    request
  );
}

export async function transitionProjectGoal(
  projectId: string,
  goalId: string,
  request: { action: "start" | "pause" | "resume" | "complete_step" | "stop" | "emergency_stop"; step_id?: string; checkpoint_note?: string }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/goals/${encodeURIComponent(goalId)}/transition`,
    request
  );
}

export async function updateProjectCanvas(
  projectId: string,
  request: { title?: string; elements: ProjectCanvasElement[] }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return requestEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/canvas`,
    { method: "PUT", body: JSON.stringify(request) }
  );
}

export async function createProjectImage(
  projectId: string,
  request: { prompt: string; seed?: number; operator_approved: boolean; contains_real_person_request?: boolean }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/images`,
    request
  );
}

export async function fetchProjectImageJob(
  projectId: string,
  operationId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return fetchEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/images/jobs/${encodeURIComponent(operationId)}`
  );
}

export async function cancelProjectImageJob(
  projectId: string,
  operationId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/images/jobs/${encodeURIComponent(operationId)}/cancel`,
    {}
  );
}

export async function speakProjectText(
  projectId: string,
  request: { text: string; voice_id?: string; speed?: number; operator_approved: boolean }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/speak`,
    request
  );
}

export async function fetchProjectGimpStatus(
  projectId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return fetchEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/creative/gimp`
  );
}

export async function openProjectImageInGimp(
  projectId: string,
  request: { source_path: string; operator_approved: boolean }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/creative/gimp`,
    request
  );
}

export async function fetchProjectSoundCloudStatus(
  projectId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return fetchEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/connectors/soundcloud`
  );
}

export async function beginProjectSoundCloudAuthorization(
  projectId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/connectors/soundcloud/authorize`,
    {}
  );
}

export async function completeProjectSoundCloudAuthorization(
  projectId: string,
  request: { authorization_code: string; returned_state: string }
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/connectors/soundcloud/complete`,
    request
  );
}

export async function disconnectProjectSoundCloud(
  projectId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/connectors/soundcloud/disconnect`,
    {}
  );
}

export async function verifyProjectSoundCloudAccount(
  projectId: string
): Promise<EnvelopeResult<ProjectCapabilityEnvelope>> {
  return postEnvelope<ProjectCapabilityEnvelope>(
    `${PROJECTS_PATH}/${encodeURIComponent(projectId)}/connectors/soundcloud/verify`,
    {}
  );
}

export async function fetchConversationList(
  options?: FetchConversationListOptions
): Promise<EnvelopeResult<ConversationListEnvelope>> {
  return fetchEnvelope<ConversationListEnvelope>(
    buildConversationListPath(options)
  );
}

export async function fetchConversationThread(
  conversationId: string
): Promise<EnvelopeResult<ConversationThreadEnvelope>> {
  return fetchEnvelope<ConversationThreadEnvelope>(
    buildConversationThreadPath(conversationId)
  );
}

export async function fetchRequestTrace(
  requestId: string
): Promise<EnvelopeResult<RequestTraceEnvelope>> {
  return fetchEnvelope<RequestTraceEnvelope>(
    buildRequestTracePath(requestId)
  );
}

export async function fetchRecentRequestTraces(
  limit = 50
): Promise<EnvelopeResult<RequestTraceListEnvelope>> {
  const bounded = Math.max(1, Math.min(200, Math.trunc(limit)));
  return fetchEnvelope<RequestTraceListEnvelope>(`${REQUEST_TRACE_PATH}?limit=${bounded}`);
}

export async function runBoundedResearchSearch(
  request: ResearchSearchRequest
): Promise<EnvelopeResult<ResearchSearchResponse>> {
  return postEnvelope<ResearchSearchResponse>(RESEARCH_SEARCH_PATH, request);
}

export async function runBoundedResearchFetch(
  request: ResearchFetchRequest
): Promise<EnvelopeResult<ResearchSearchResponse>> {
  return postEnvelope<ResearchSearchResponse>(RESEARCH_FETCH_PATH, request);
}

export async function fetchDurableResearch(options?: {
  projectId?: string | null;
  conversationId?: string | null;
}): Promise<EnvelopeResult<ResearchSearchResponse>> {
  const params = new URLSearchParams();
  if (options?.projectId) params.set("project_id", options.projectId);
  if (options?.conversationId) params.set("conversation_id", options.conversationId);
  const query = params.toString();
  return fetchEnvelope<ResearchSearchResponse>(`/research/records${query ? `?${query}` : ""}`);
}

export async function fetchContextReceipts(limit = 50): Promise<EnvelopeResult<ResearchSearchResponse>> {
  const bounded = Math.max(1, Math.min(200, Math.trunc(limit)));
  return fetchEnvelope<ResearchSearchResponse>(`/research/context-receipts?limit=${bounded}`);
}

export async function fetchResearchEgressApprovals(): Promise<EnvelopeResult<ResearchSearchResponse>> {
  return fetchEnvelope<ResearchSearchResponse>("/research/egress/approvals/pending");
}

export async function resolveResearchEgressApproval(
  approvalId: string,
  approve: boolean,
  execute = false
): Promise<EnvelopeResult<ResearchSearchResponse>> {
  return postEnvelope<ResearchSearchResponse>("/research/egress/approvals/resolve", {
    approval_id: approvalId,
    approve,
    execute
  });
}

export async function reviewResearchEvidence(
  evidenceId: string,
  verificationStatus: "candidate" | "verified" | "rejected" | "contradicted",
  contradictionNotes: string[] = []
): Promise<EnvelopeResult<ResearchSearchResponse>> {
  return postEnvelope<ResearchSearchResponse>(`/research/evidence/${encodeURIComponent(evidenceId)}/review`, {
    verification_status: verificationStatus,
    contradiction_notes: contradictionNotes
  });
}

export async function correctResearchEvidence(
  evidenceId: string,
  claim: string,
  excerpt: string,
  reason: string
): Promise<EnvelopeResult<ResearchSearchResponse>> {
  return postEnvelope<ResearchSearchResponse>(`/research/evidence/${encodeURIComponent(evidenceId)}/correct`, {
    claim,
    excerpt,
    reason
  });
}

export async function promoteResearchEvidence(
  evidenceId: string
): Promise<EnvelopeResult<ResearchSearchResponse>> {
  return postEnvelope<ResearchSearchResponse>(`/research/evidence/${encodeURIComponent(evidenceId)}/promote`, {});
}

export async function fetchAccountState(): Promise<
  EnvelopeResult<AccountStateEnvelope>
> {
  return fetchEnvelope<AccountStateEnvelope>(`${ACCOUNT_PATH}/state`);
}

export async function fetchAdminSummary(): Promise<EnvelopeResult<AdminSummaryEnvelope>> {
  return fetchEnvelope<AdminSummaryEnvelope>("/admin/summary");
}

export async function previewAdminChange(request: {
  target_user_id: string;
  change_kind: "set_role" | "set_managed_policy" | "set_account_enabled";
  target_role?: "admin" | "user";
  managed?: boolean;
  managed_policy?: ManagedProfilePolicy;
  enabled?: boolean;
  reason: string;
}): Promise<EnvelopeResult<BridgeEnvelope<Record<string, any>>>> {
  return postEnvelope<BridgeEnvelope<Record<string, any>>>("/admin/changes/preview", request);
}

export async function applyAdminChange(
  previewId: string,
  approvalToken: string
): Promise<EnvelopeResult<BridgeEnvelope<Record<string, any>>>> {
  return postEnvelope<BridgeEnvelope<Record<string, any>>>("/admin/changes/apply", {
    preview_id: previewId,
    approval_token: approvalToken
  });
}

export async function createAccount(
  request: AccountCreateRequest
): Promise<EnvelopeResult<AccountCreateEnvelope>> {
  return postEnvelope<AccountCreateEnvelope>(`${ACCOUNT_PATH}/create`, request);
}

export async function loginAccount(
  request: AccountLoginRequest
): Promise<EnvelopeResult<AccountLoginEnvelope>> {
  return postEnvelope<AccountLoginEnvelope>(`${ACCOUNT_PATH}/login`, request);
}

export async function logoutAccount(): Promise<
  EnvelopeResult<AccountLogoutEnvelope>
> {
  return postEnvelope<AccountLogoutEnvelope>(`${ACCOUNT_PATH}/logout`, {});
}

export async function deleteCurrentAccount(
  request: AccountDeleteRequest
): Promise<EnvelopeResult<AccountDeleteEnvelope>> {
  return postEnvelope<AccountDeleteEnvelope>(`${ACCOUNT_PATH}/delete`, request);
}

export async function fetchAccountProfile(): Promise<
  EnvelopeResult<AccountProfileEnvelope>
> {
  return fetchEnvelope<AccountProfileEnvelope>(`${ACCOUNT_PATH}/profile`);
}

export async function updateAccountProfile(
  request: AccountProfileUpdateRequest
): Promise<EnvelopeResult<AccountProfileUpdateEnvelope>> {
  return requestEnvelope<AccountProfileUpdateEnvelope>(`${ACCOUNT_PATH}/profile`, {
    method: "PUT",
    body: JSON.stringify(request)
  });
}

export async function exportAccountProfileArchive(
  currentPassword: string,
  recoveryMaterial: string
): Promise<EnvelopeResult<AccountProfileArchiveEnvelope>> {
  return postEnvelope<AccountProfileArchiveEnvelope>(
    `${ACCOUNT_PATH}/profile/archive/export`,
    { current_password: currentPassword, recovery_material: recoveryMaterial }
  );
}

export async function restoreAccountProfileArchive(
  archiveBase64: string,
  currentPassword: string,
  recoveryMaterial: string
): Promise<EnvelopeResult<AccountProfileArchiveEnvelope>> {
  return postEnvelope<AccountProfileArchiveEnvelope>(
    `${ACCOUNT_PATH}/profile/archive/restore`,
    {
      archive_base64: archiveBase64,
      current_password: currentPassword,
      recovery_material: recoveryMaterial,
      operator_confirmed: true
    }
  );
}

export async function fetchElysiaVisibleProfile(): Promise<
  EnvelopeResult<AccountVisibleProfileEnvelope>
> {
  return fetchEnvelope<AccountVisibleProfileEnvelope>(
    `${ACCOUNT_PATH}/profile/elysia-visible`
  );
}

export async function selectAccountProfilePhoto(
  sourcePath: string
): Promise<EnvelopeResult<AccountProfilePhotoEnvelope>> {
  return postEnvelope<AccountProfilePhotoEnvelope>(
    `${ACCOUNT_PATH}/profile-photo/select`,
    { source_path: sourcePath }
  );
}

export async function deleteAccountProfilePhoto(): Promise<
  EnvelopeResult<AccountProfilePhotoDeleteEnvelope>
> {
  return deleteEnvelope<AccountProfilePhotoDeleteEnvelope>(
    `${ACCOUNT_PATH}/profile-photo`
  );
}

export function getAccountProfilePhotoPreviewUrl(
  assetId: string | null | undefined
): string | null {
  if (!assetId) {
    return null;
  }
  return buildBridgeUrl(
    `${ACCOUNT_PATH}/profile-photo/${encodeURIComponent(assetId)}/preview`
  );
}

export async function fetchAccountColors(): Promise<
  EnvelopeResult<AccountColorsEnvelope>
> {
  return fetchEnvelope<AccountColorsEnvelope>(`${ACCOUNT_PATH}/colors`);
}

export async function fetchAccountPrivacy(): Promise<
  EnvelopeResult<AccountPrivacyEnvelope>
> {
  return fetchEnvelope<AccountPrivacyEnvelope>(`${ACCOUNT_PATH}/privacy`);
}

export async function fetchOnboardingState(): Promise<
  EnvelopeResult<OnboardingStateEnvelope>
> {
  return fetchEnvelope<OnboardingStateEnvelope>(ONBOARDING_PATH);
}

export async function saveOnboardingDraft(
  answers: OnboardingAnswer[]
): Promise<EnvelopeResult<OnboardingStateEnvelope>> {
  return requestEnvelope<OnboardingStateEnvelope>(`${ONBOARDING_PATH}/draft`, {
    method: "PUT",
    body: JSON.stringify({ answers })
  });
}

export async function finalizeOnboarding(request: {
  action: "import_all" | "import_selected" | "import_none" | "retain_draft" | "discard" | "skip";
  selected_question_ids?: string[];
  sealed_password?: string | null;
}): Promise<EnvelopeResult<OnboardingStateEnvelope>> {
  return postEnvelope<OnboardingStateEnvelope>(`${ONBOARDING_PATH}/finalize`, request);
}

export async function fetchSetupState(): Promise<EnvelopeResult<SetupStateEnvelope>> {
  return fetchEnvelope<SetupStateEnvelope>("/install/setup");
}

export async function previewSetup(request: {
  profile_id: string;
  distribution_form: "deb" | "appimage" | "user_local_desktop" | "onefile_core" | "source";
  install_root?: string | null;
  custom_components?: string[];
  internet_available?: boolean;
}): Promise<EnvelopeResult<SetupStateEnvelope>> {
  return postEnvelope<SetupStateEnvelope>("/install/setup/preview", request);
}

export async function applySetup(request: {
  preview_id: string;
  approval_token: string;
  operator_approved: boolean;
}): Promise<EnvelopeResult<SetupStateEnvelope>> {
  return postEnvelope<SetupStateEnvelope>("/install/setup/apply", request);
}

export async function runSetupDoctor(): Promise<EnvelopeResult<SetupStateEnvelope>> {
  return postEnvelope<SetupStateEnvelope>("/install/setup/doctor", {});
}

export async function previewSystemPrerequisites(
  componentIds: string[]
): Promise<EnvelopeResult<SystemPrerequisiteEnvelope>> {
  return postEnvelope<SystemPrerequisiteEnvelope>("/install/prerequisites/preview", {
    component_ids: componentIds
  });
}

export async function applySystemPrerequisites(request: {
  preview_id: string;
  approval_token: string;
  operator_approved: boolean;
}): Promise<EnvelopeResult<SystemPrerequisiteEnvelope>> {
  return postEnvelope<SystemPrerequisiteEnvelope>("/install/prerequisites/apply", request);
}

export async function previewComponentInstall(request: {
  component_id: string;
  operation: "install" | "repair" | "remove";
  metadata_network_approved: boolean;
  local_artifact_path?: string | null;
  selected_model_ids?: string[];
  local_model_root?: string | null;
  model_terms_accepted?: boolean;
}): Promise<EnvelopeResult<ComponentInstallEnvelope>> {
  return postEnvelope<ComponentInstallEnvelope>("/install/components/preview", request);
}

export async function applyComponentInstall(request: {
  preview_id: string;
  approval_token: string;
  operator_approved: boolean;
}): Promise<EnvelopeResult<ComponentInstallEnvelope>> {
  return postEnvelope<ComponentInstallEnvelope>("/install/components/apply", request);
}

export async function fetchComponentJob(jobId: string): Promise<EnvelopeResult<ComponentInstallEnvelope>> {
  return fetchEnvelope<ComponentInstallEnvelope>(`/install/components/jobs/${encodeURIComponent(jobId)}`);
}

export async function cancelComponentJob(jobId: string): Promise<EnvelopeResult<ComponentInstallEnvelope>> {
  return postEnvelope<ComponentInstallEnvelope>("/install/components/jobs/cancel", {
    job_id: jobId,
    operator_approved: true
  });
}

export async function fetchApplicationLifecycleState(): Promise<EnvelopeResult<ApplicationLifecycleEnvelope>> {
  return fetchEnvelope<ApplicationLifecycleEnvelope>("/install/lifecycle/state");
}

export async function previewApplicationLifecycle(request: {
  operation: "update" | "repair" | "rollback" | "uninstall_preserve" | "export_then_remove" | "purge_local_data";
  artifact_path?: string | null;
  manifest_path?: string | null;
  signature_path?: string | null;
  target_release_id?: string | null;
  export_path?: string | null;
  destructive_confirmation?: string | null;
}): Promise<EnvelopeResult<ApplicationLifecycleEnvelope>> {
  return postEnvelope<ApplicationLifecycleEnvelope>("/install/lifecycle/preview", request);
}

export async function applyApplicationLifecycle(request: {
  preview_id: string;
  approval_token: string;
  operator_approved: boolean;
}): Promise<EnvelopeResult<ApplicationLifecycleEnvelope>> {
  return postEnvelope<ApplicationLifecycleEnvelope>("/install/lifecycle/apply", request);
}

export async function fetchMarketplaceLinkStatus(): Promise<
  EnvelopeResult<MarketplaceLinkEnvelope>
> {
  return fetchEnvelope<MarketplaceLinkEnvelope>(`${MARKETPLACE_PATH}/link/status`);
}

export async function linkMarketplaceAccount(
  request: MarketplaceLinkRequest
): Promise<EnvelopeResult<MarketplaceLinkEnvelope>> {
  return postEnvelope<MarketplaceLinkEnvelope>(`${MARKETPLACE_PATH}/link`, request);
}

export async function unlinkMarketplaceAccount(): Promise<
  EnvelopeResult<MarketplaceLinkEnvelope>
> {
  return deleteEnvelope<MarketplaceLinkEnvelope>(`${MARKETPLACE_PATH}/link`);
}

export async function recordMarketplaceProfileSync(
  request: MarketplaceProfileSyncRecordRequest
): Promise<EnvelopeResult<MarketplaceLinkEnvelope>> {
  return postEnvelope<MarketplaceLinkEnvelope>(`${MARKETPLACE_PATH}/profile-sync/record`, request);
}

export async function planAddonAction(
  request: AddonActionPlanRequest
): Promise<EnvelopeResult<AddonActionPlanEnvelope>> {
  return postEnvelope<AddonActionPlanEnvelope>(`${ADDON_ACTIONS_PATH}/plan`, request);
}

export async function fetchAddonInstallerStatus(): Promise<
  EnvelopeResult<AddonInstallerEnvelope>
> {
  return fetchEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/status`);
}

export async function fetchInstalledAddons(): Promise<
  EnvelopeResult<AddonInstallerEnvelope>
> {
  return fetchEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/installed`);
}

export async function inspectAddonPackage(
  request: AddonPackagePathRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/inspect-package`, request);
}

export async function createAddonInstallPlan(
  request: AddonPackagePathRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/install-plan`, request);
}

export async function createAddonTransitionPlan(
  request: AddonTransitionPlanRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/transitions/plan`, request);
}

export async function approveAddonTransition(
  request: AddonTransitionApprovalRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/transitions/approve`, request);
}

export async function applyAddonTransition(
  request: AddonTransitionApplyRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/transitions/apply`, request);
}

export async function prepareDeveloperAddonPackagePlan(
  request: DeveloperAddonPackagePlanRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/developer/package-plan`, request);
}

export async function previewMarketplaceAddonSubmission(
  request: MarketplaceAddonSubmissionPreviewRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/marketplace/submission-preview`, request);
}

export async function previewMarketplaceAddonReview(
  request: MarketplaceAddonReviewPreviewRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/marketplace/review-preview`, request);
}

export async function fetchOfficialAddonCandidates(): Promise<
  EnvelopeResult<AddonInstallerEnvelope>
> {
  return fetchEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/official-candidates`);
}

export async function installAddonDisabled(
  request: AddonPackagePathRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/install-disabled`, request);
}

export async function enableAddon(
  request: AddonStatusChangeRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/enable`, request);
}

export async function disableAddon(
  request: AddonStatusChangeRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/disable`, request);
}

export async function removeAddon(
  request: AddonStatusChangeRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/remove`, request);
}

export async function revokeAddon(
  request: AddonStatusChangeRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/revoke`, request);
}

export async function rollbackAddon(
  request: AddonStatusChangeRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/rollback`, request);
}

export async function testAddonSandbox(
  request: AddonPackagePathRequest
): Promise<EnvelopeResult<AddonInstallerEnvelope>> {
  return postEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/test-sandbox`, request);
}

export async function fetchAddonAudit(): Promise<
  EnvelopeResult<AddonInstallerEnvelope>
> {
  return fetchEnvelope<AddonInstallerEnvelope>(`${ADDONS_PATH}/audit`);
}

export async function inspectCodingFileType(
  request: CodingFilePathRequest
): Promise<EnvelopeResult<CodingFileTypeInspectionEnvelope>> {
  return postEnvelope<CodingFileTypeInspectionEnvelope>(
    `${CODING_PATH}/file/inspect-type`,
    request
  );
}

export async function readCodingFilePreview(
  request: CodingFilePreviewRequest
): Promise<EnvelopeResult<CodingFilePreviewEnvelope>> {
  return postEnvelope<CodingFilePreviewEnvelope>(
    `${CODING_FILE_PATH}/read-preview`,
    request
  );
}

export async function proposeCodingPatch(
  request: CodingPatchProposeRequest
): Promise<EnvelopeResult<CodingPatchProposalEnvelope>> {
  return postEnvelope<CodingPatchProposalEnvelope>(
    `${CODING_PATCH_PATH}/propose`,
    request
  );
}

export async function applyApprovedCodingPatch(
  request: CodingPatchApplyRequest
): Promise<EnvelopeResult<CodingPatchApplyEnvelope>> {
  return postEnvelope<CodingPatchApplyEnvelope>(
    `${CODING_PATCH_PATH}/apply-approved`,
    request
  );
}

export async function approveCodingOperation(
  request: CodingOperationApprovalRequest
): Promise<EnvelopeResult<CodingOperationApprovalEnvelope>> {
  return postEnvelope<CodingOperationApprovalEnvelope>(
    `${CODING_OPERATION_PATH}/approve`,
    request
  );
}

export async function planCodingFileOperation(
  request: CodingFileOperationPlanRequest
): Promise<EnvelopeResult<CodingFileOperationPlanEnvelope>> {
  return postEnvelope<CodingFileOperationPlanEnvelope>(
    `${CODING_FILE_PATH}/operation-plan`,
    request
  );
}

export async function executeApprovedCodingFileOperation(
  request: CodingFileOperationExecuteRequest
): Promise<EnvelopeResult<CodingFileOperationResultEnvelope>> {
  return postEnvelope<CodingFileOperationResultEnvelope>(
    `${CODING_FILE_PATH}/operation-execute-approved`,
    request
  );
}

export async function inspectCodingDocument(
  request: CodingDocumentPathRequest
): Promise<EnvelopeResult<CodingDocumentPreviewEnvelope>> {
  return postEnvelope<CodingDocumentPreviewEnvelope>(
    `${CODING_DOCUMENT_PATH}/inspect`,
    request
  );
}

export async function extractCodingDocumentPreview(
  request: CodingDocumentPathRequest
): Promise<EnvelopeResult<CodingDocumentPreviewEnvelope>> {
  return postEnvelope<CodingDocumentPreviewEnvelope>(
    `${CODING_DOCUMENT_PATH}/extract-preview`,
    request
  );
}

export async function planCodingDocumentExport(
  request: CodingDocumentExportPlanRequest
): Promise<EnvelopeResult<CodingDocumentExportPlanEnvelope>> {
  return postEnvelope<CodingDocumentExportPlanEnvelope>(
    `${CODING_DOCUMENT_PATH}/export-plan`,
    request
  );
}

export async function applyApprovedCodingDocumentExport(
  request: CodingDocumentExportApplyRequest
): Promise<EnvelopeResult<CodingDocumentExportApplyEnvelope>> {
  return postEnvelope<CodingDocumentExportApplyEnvelope>(
    `${CODING_DOCUMENT_PATH}/export-approved`,
    request
  );
}

export async function planCodingDocumentEdit(
  request: CodingDocumentEditPlanRequest
): Promise<EnvelopeResult<CodingDocumentEditPlanEnvelope>> {
  return postEnvelope<CodingDocumentEditPlanEnvelope>(
    `${CODING_DOCUMENT_PATH}/edit-plan`,
    request
  );
}

export async function applyApprovedCodingDocumentEdit(
  request: CodingDocumentEditApplyRequest
): Promise<EnvelopeResult<CodingDocumentEditApplyEnvelope>> {
  return postEnvelope<CodingDocumentEditApplyEnvelope>(
    `${CODING_DOCUMENT_PATH}/apply-approved`,
    request
  );
}

export async function inspectCodingData(
  request: CodingDataPathRequest
): Promise<EnvelopeResult<CodingDataPreviewEnvelope>> {
  return postEnvelope<CodingDataPreviewEnvelope>(
    `${CODING_DATA_PATH}/inspect`,
    request
  );
}

export async function previewCodingData(
  request: CodingDataPathRequest
): Promise<EnvelopeResult<CodingDataPreviewEnvelope>> {
  return postEnvelope<CodingDataPreviewEnvelope>(
    `${CODING_DATA_PATH}/preview`,
    request
  );
}

export async function planCodingDataExport(
  request: CodingDataExportPlanRequest
): Promise<EnvelopeResult<CodingDataExportPlanEnvelope>> {
  return postEnvelope<CodingDataExportPlanEnvelope>(
    `${CODING_DATA_PATH}/export-plan`,
    request
  );
}

export async function applyApprovedCodingDataExport(
  request: CodingDataExportApplyRequest
): Promise<EnvelopeResult<CodingDataApplyEnvelope>> {
  return postEnvelope<CodingDataApplyEnvelope>(
    `${CODING_DATA_PATH}/export-approved`,
    request
  );
}

export async function planCodingDataEdit(
  request: CodingDataEditPlanRequest
): Promise<EnvelopeResult<CodingDataEditPlanEnvelope>> {
  return postEnvelope<CodingDataEditPlanEnvelope>(
    `${CODING_DATA_PATH}/edit-plan`,
    request
  );
}

export async function planCodingDataMutation(
  request: CodingDataEditPlanRequest
): Promise<EnvelopeResult<CodingDataEditPlanEnvelope>> {
  return postEnvelope<CodingDataEditPlanEnvelope>(
    `${CODING_DATA_PATH}/mutation-plan`,
    request
  );
}

export async function applyApprovedCodingDataOperation(
  request: CodingDataApplyRequest
): Promise<EnvelopeResult<CodingDataApplyEnvelope>> {
  return postEnvelope<CodingDataApplyEnvelope>(
    `${CODING_DATA_PATH}/apply-approved`,
    request
  );
}

export async function applyApprovedCodingDataMutation(
  request: CodingDataApplyRequest
): Promise<EnvelopeResult<CodingDataApplyEnvelope>> {
  return postEnvelope<CodingDataApplyEnvelope>(
    `${CODING_DATA_PATH}/apply-mutation-approved`,
    request
  );
}

export async function inspectCodingVisual(
  request: CodingVisualPathRequest
): Promise<EnvelopeResult<CodingVisualPreviewEnvelope>> {
  return postEnvelope<CodingVisualPreviewEnvelope>(
    `${CODING_VISUAL_PATH}/inspect`,
    request
  );
}

export async function previewCodingVisual(
  request: CodingVisualPathRequest
): Promise<EnvelopeResult<CodingVisualPreviewEnvelope>> {
  return postEnvelope<CodingVisualPreviewEnvelope>(
    `${CODING_VISUAL_PATH}/preview`,
    request
  );
}

export async function runCodingVisualOcr(
  request: CodingVisualOcrRequest
): Promise<EnvelopeResult<CodingVisualOcrEnvelope>> {
  return postEnvelope<CodingVisualOcrEnvelope>(
    `${CODING_VISUAL_PATH}/ocr`,
    request
  );
}

export async function analyzeCodingVisual(
  request: CodingVisualAnalysisRequest
): Promise<EnvelopeResult<CodingVisualAnalysisEnvelope>> {
  return postEnvelope<CodingVisualAnalysisEnvelope>(
    `${CODING_VISUAL_PATH}/analysis`,
    request
  );
}

export async function planCodingVisualExport(
  request: CodingVisualExportPlanRequest
): Promise<EnvelopeResult<CodingVisualExportPlanEnvelope>> {
  return postEnvelope<CodingVisualExportPlanEnvelope>(
    `${CODING_VISUAL_PATH}/export-plan`,
    request
  );
}

export async function applyApprovedCodingVisualExport(
  request: CodingVisualExportApplyRequest
): Promise<EnvelopeResult<CodingVisualApplyEnvelope>> {
  return postEnvelope<CodingVisualApplyEnvelope>(
    `${CODING_VISUAL_PATH}/export-approved`,
    request
  );
}

export async function planCodingVisualEdit(
  request: CodingVisualEditPlanRequest
): Promise<EnvelopeResult<CodingVisualEditPlanEnvelope>> {
  return postEnvelope<CodingVisualEditPlanEnvelope>(
    `${CODING_VISUAL_PATH}/edit-plan`,
    request
  );
}

export async function applyApprovedCodingVisualEdit(
  request: CodingVisualApplyRequest
): Promise<EnvelopeResult<CodingVisualApplyEnvelope>> {
  return postEnvelope<CodingVisualApplyEnvelope>(
    `${CODING_VISUAL_PATH}/apply-approved`,
    request
  );
}

export async function inspectCodingMedia(
  request: CodingMediaPathRequest
): Promise<EnvelopeResult<CodingMediaPreviewEnvelope>> {
  return postEnvelope<CodingMediaPreviewEnvelope>(
    `${CODING_MEDIA_PATH}/inspect`,
    request
  );
}

export async function thumbnailCodingMedia(
  request: CodingMediaPathRequest
): Promise<EnvelopeResult<CodingMediaPreviewEnvelope>> {
  return postEnvelope<CodingMediaPreviewEnvelope>(
    `${CODING_MEDIA_PATH}/thumbnail`,
    request
  );
}

export async function inspectCodingArchive(request: {
  session_id?: string | null;
  workspace_root: string;
  archive_path: string;
  approval_granted: boolean;
  approval_reason?: string | null;
}): Promise<EnvelopeResult<ArchiveInspectEnvelope>> {
  return postEnvelope<ArchiveInspectEnvelope>(`${CODING_ARCHIVE_PATH}/inspect`, request);
}

export async function planCodingArchiveExtraction(request: {
  session_id?: string | null;
  workspace_root: string;
  archive_path: string;
  selected_member_indexes: number[];
  sandbox_id?: string | null;
  approval_granted: boolean;
  approval_reason?: string | null;
}): Promise<EnvelopeResult<ArchiveExtractionPlanEnvelope>> {
  return postEnvelope<ArchiveExtractionPlanEnvelope>(`${CODING_ARCHIVE_PATH}/extract/plan`, request);
}

export async function applyApprovedCodingArchiveExtraction(request: {
  operation_id: string;
  session_id?: string | null;
  workspace_root: string;
  archive_path: string;
  selected_member_indexes: number[];
  sandbox_id: string;
  approval_granted: boolean;
  approval_reason?: string | null;
  approval_id: string;
  approval_token: string;
  operator_approved: boolean;
  expected_archive_sha256: string;
  expected_manifest_digest: string;
  expected_plan_hash: string;
}): Promise<EnvelopeResult<ArchiveExtractionResultEnvelope>> {
  return postEnvelope<ArchiveExtractionResultEnvelope>(`${CODING_ARCHIVE_PATH}/extract/apply`, request);
}

export async function inspectCodingDatabase(request: {
  session_id?: string | null;
  workspace_root: string;
  database_path: string;
  approval_granted: boolean;
  approval_reason?: string | null;
}): Promise<EnvelopeResult<DatabaseInspectEnvelope>> {
  return postEnvelope<DatabaseInspectEnvelope>(`${CODING_DATABASE_PATH}/inspect`, request);
}

export async function previewCodingDatabaseSchema(request: {
  session_id?: string | null;
  workspace_root: string;
  database_path: string;
  approval_id: string;
  approval_token: string;
  operator_approved: true;
  expected_source_sha256: string;
  expected_plan_hash: string;
}): Promise<EnvelopeResult<DatabaseSchemaEnvelope>> {
  return postEnvelope<DatabaseSchemaEnvelope>(`${CODING_DATABASE_PATH}/schema/preview`, request);
}

export async function inspectCodingBinary(request: {
  session_id?: string | null;
  workspace_root: string;
  binary_path: string;
  approval_granted: boolean;
  approval_reason?: string | null;
}): Promise<EnvelopeResult<BinaryInspectEnvelope>> {
  return postEnvelope<BinaryInspectEnvelope>(`${CODING_BINARY_PATH}/inspect`, request);
}

export async function inspectCodingEngineering(request: {
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
  approval_granted: boolean;
  approval_reason?: string | null;
}): Promise<EnvelopeResult<EngineeringInspectEnvelope>> {
  return postEnvelope<EngineeringInspectEnvelope>(`${CODING_ENGINEERING_PATH}/inspect`, request);
}

export async function planCodingEngineeringPreview(request: {
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
  approval_granted: boolean;
  approval_reason?: string | null;
}): Promise<EnvelopeResult<EngineeringPreviewPlanEnvelope>> {
  return postEnvelope<EngineeringPreviewPlanEnvelope>(`${CODING_ENGINEERING_PATH}/preview/plan`, request);
}

export async function applyApprovedCodingEngineeringPreview(request: {
  operation_id: string;
  session_id?: string | null;
  workspace_root: string;
  file_path: string;
  approval_granted: boolean;
  approval_reason?: string | null;
  approval_id: string;
  approval_token: string;
  operator_approved: true;
  expected_source_sha256: string;
  expected_plan_hash: string;
}): Promise<EnvelopeResult<EngineeringPreviewResultEnvelope>> {
  return postEnvelope<EngineeringPreviewResultEnvelope>(`${CODING_ENGINEERING_PATH}/preview/apply`, request);
}

export async function fetchMediaWorkerTruth(): Promise<EnvelopeResult<MediaWorkerTruthEnvelope>> {
  return fetchEnvelope<MediaWorkerTruthEnvelope>(`${CODING_MEDIA_PATH}/workers`);
}

export async function fetchTtsVoices(): Promise<EnvelopeResult<TtsVoiceCatalogEnvelope>> {
  return fetchEnvelope<TtsVoiceCatalogEnvelope>(`${CODING_MEDIA_PATH}/tts/voices`);
}

export async function planSpeechTts(
  request: SpeechTtsPlanRequest
): Promise<EnvelopeResult<SpeechTtsPlanEnvelope>> {
  return postEnvelope<SpeechTtsPlanEnvelope>(`${CODING_MEDIA_PATH}/tts/preview`, request);
}

export async function applyApprovedSpeechTts(
  request: SpeechTtsApplyRequest
): Promise<EnvelopeResult<SpeechTtsResultEnvelope>> {
  return postEnvelope<SpeechTtsResultEnvelope>(`${CODING_MEDIA_PATH}/tts/apply`, request);
}

export async function planSpeechTranscription(
  request: SpeechTranscriptionPlanRequest
): Promise<EnvelopeResult<SpeechTranscriptionPlanEnvelope>> {
  return postEnvelope<SpeechTranscriptionPlanEnvelope>(`${CODING_MEDIA_PATH}/transcribe/preview`, request);
}

export async function applyApprovedSpeechTranscription(
  request: SpeechTranscriptionApplyRequest
): Promise<EnvelopeResult<SpeechTranscriptionResultEnvelope>> {
  return postEnvelope<SpeechTranscriptionResultEnvelope>(`${CODING_MEDIA_PATH}/transcribe/apply`, request);
}

export async function planVideoForge(
  request: VideoForgePlanRequest
): Promise<EnvelopeResult<VideoForgePlanEnvelope>> {
  return postEnvelope<VideoForgePlanEnvelope>(`${CODING_MEDIA_PATH}/videoforge/preview`, request);
}

export async function applyApprovedVideoForge(
  request: VideoForgeApplyRequest
): Promise<EnvelopeResult<VideoForgeJobEnvelope>> {
  return postEnvelope<VideoForgeJobEnvelope>(`${CODING_MEDIA_PATH}/videoforge/apply`, request);
}

export async function fetchVideoForgeJob(
  operationId: string
): Promise<EnvelopeResult<VideoForgeJobEnvelope>> {
  return fetchEnvelope<VideoForgeJobEnvelope>(`${CODING_MEDIA_PATH}/videoforge/jobs/${encodeURIComponent(operationId)}`);
}

export async function cancelVideoForgeJob(
  operationId: string
): Promise<EnvelopeResult<VideoForgeJobEnvelope>> {
  return postEnvelope<VideoForgeJobEnvelope>(
    `${CODING_MEDIA_PATH}/videoforge/jobs/${encodeURIComponent(operationId)}/cancel`,
    { reason: "desktop_operator_cancelled" }
  );
}

export async function attachFile(
  request: FileAttachRequest
): Promise<EnvelopeResult<FileIngestEnvelope>> {
  return postEnvelope<FileIngestEnvelope>(
    `${FILES_PATH}/attach`,
    request
  );
}

export async function fetchFileStatus(
  fileId: string
): Promise<EnvelopeResult<FileStatusEnvelope>> {
  return fetchEnvelope<FileStatusEnvelope>(
    buildFileStatusPath(fileId)
  );
}

export async function fetchFileContextSummary(
  fileId: string
): Promise<EnvelopeResult<FileContextSummaryEnvelope>> {
  return fetchEnvelope<FileContextSummaryEnvelope>(
    buildFileContextSummaryPath(fileId)
  );
}

export async function updateConversation(
  conversationId: string,
  patch: ConversationUpdatePatch
): Promise<EnvelopeResult<ConversationUpdateEnvelope>> {
  return patchEnvelope<ConversationUpdateEnvelope>(
    buildConversationUpdatePath(conversationId),
    patch
  );
}

export async function deleteConversation(
  conversationId: string
): Promise<EnvelopeResult<ConversationDeleteEnvelope>> {
  return deleteEnvelope<ConversationDeleteEnvelope>(
    buildConversationDeletePath(conversationId)
  );
}

export async function sendChatMessage(
  request: ChatSendRequest
): Promise<EnvelopeResult<ChatSendEnvelope>> {
  return postEnvelope<ChatSendEnvelope>(CHAT_SEND_PATH, request);
}

export async function cancelCognitionRequest(
  requestId: string
): Promise<EnvelopeResult<BridgeEnvelope<{ request_id?: string; cancel_requested?: boolean }>>> {
  return postEnvelope<BridgeEnvelope<{ request_id?: string; cancel_requested?: boolean }>>(
    `/cognition/requests/${encodeURIComponent(requestId)}/cancel`,
    {}
  );
}

export async function sendQuickInvokeMessage(
  request: QuickInvokeSendBridgeRequest
): Promise<QuickInvokeBridgeResult> {
  const envelopeResult = await sendChatMessage({
    ...request,
    ui_surface: request.ui_surface ?? "quick_invoke"
  });

  return toQuickInvokeBridgeResult(envelopeResult);
}

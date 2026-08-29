import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ArtifactCard from "./ArtifactCard";
import PlotArtifactView from "./PlotArtifactView";
import RepoContextCard from "./RepoContextCard";
import CodePatchCard from "./CodePatchCard";
import CommandGateCard from "./CommandGateCard";
import Composer from "./Composer";
import { openLocalAttachableFile } from "./api/localFilePicker";
import ConversationActionsMenu from "./ConversationActionsMenu";
import ConversationThread from "./ConversationThread";
import ModeChips from "./ModeChips";
import MoveConversationDialog from "./MoveConversationDialog";
import RenameConversationDialog from "./RenameConversationDialog";
import WorkingTrace from "./WorkingTrace";
import ArchiveContainerPanel from "./ArchiveContainerPanel";
import DataBinaryForgePanel from "./DataBinaryForgePanel";
import EngineeringForgePanel from "./EngineeringForgePanel";
import {
  DEFAULT_RIGHT_DRAWER_SECTIONS,
  type DrawerSection
} from "./RightDrawer";
import {
  analyzeCodingVisual,
  approveCodingOperation,
  applyApprovedCodingArchiveExtraction,
  applyApprovedCodingEngineeringPreview,
  applyApprovedVideoForge,
  applyApprovedSpeechTranscription,
  applyApprovedSpeechTts,
  applyApprovedCodingDocumentEdit,
  applyApprovedCodingDocumentExport,
  applyApprovedCodingDataExport,
  applyApprovedCodingDataMutation,
  applyApprovedCodingPatch,
  applyApprovedCodingVisualEdit,
  applyApprovedCodingVisualExport,
  attachFile,
  cancelVideoForgeJob,
  cancelCognitionRequest,
  deleteConversation,
  executeApprovedCodingFileOperation,
  extractCodingDocumentPreview,
  fetchConversationList,
  fetchConversationThread,
  fetchMemoryItems,
  fetchMediaWorkerTruth,
  fetchProjectList,
  fetchRequestTrace,
  fetchTtsVoices,
  fetchVideoForgeJob,
  inspectCodingDocument,
  inspectCodingData,
  inspectCodingFileType,
  inspectCodingMedia,
  inspectCodingArchive,
  inspectCodingDatabase,
  previewCodingDatabaseSchema,
  inspectCodingBinary,
  inspectCodingEngineering,
  inspectCodingVisual,
  newRequestId,
  planCodingDocumentEdit,
  planCodingDocumentExport,
  planCodingDataExport,
  planCodingDataMutation,
  planCodingVisualEdit,
  planCodingVisualExport,
  planCodingArchiveExtraction,
  planCodingEngineeringPreview,
  planSpeechTranscription,
  planSpeechTts,
  planVideoForge,
  planCodingFileOperation,
  previewCodingData,
  previewCodingVisual,
  proposeCodingPatch,
  readCodingFilePreview,
  readResponseTruth,
  runCodingVisualOcr,
  resolveResearchEgressApproval,
  thumbnailCodingMedia,
  sendChatMessage,
  updateConversation,
  type ArtifactSummaryData,
  type CodePatchPlanSummaryData,
  type ChatSendRequest,
  type CodingDataApplyResult,
  type CodingDataPlan,
  type CodingDataPreview,
  type CodingDocumentApplyResult,
  type CodingDocumentPlan,
  type CodingDocumentPreview,
  type CodingFileOperationPlan,
  type CodingFileOperationResult,
  type CodingFilePreview,
  type CodingFileTypeInspection,
  type CodingMediaPreview,
  type ArchiveContainerPreview,
  type ArchiveExtractionPlan,
  type ArchiveExtractionResult,
  type DatabaseInspection,
  type DatabaseSchemaPreview,
  type BinaryInspection,
  type EngineeringInspection,
  type EngineeringPreviewPlan,
  type EngineeringPreviewResult,
  type CodingPatchApplyResult,
  type CodingPatchProposal,
  type CodingOperationApproval,
  type CodingVisualApplyResult,
  type CodingVisualPlan,
  type CodingVisualPreview,
  type MediaWorkerTruth,
  type MemoryItemSummary,
  type ProjectSummary,
  type SpeechTranscriptionPlan,
  type SpeechTranscriptionResult,
  type SpeechTtsPlan,
  type SpeechTtsResult,
  type TtsVoice,
  type VideoForgeJob,
  type VideoForgePlan,
  type FileIngestResult,
  type RepoContextSummaryData,
  type RequestTraceData,
  type ResponseTruth
} from "./api/bridgeClient";

type ConversationsPageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
  onOpenProjects?: () => void;
  initialConversationId?: string | null;
};

type LoadState = "idle" | "loading" | "ready" | "error";
type SendState = "idle" | "sending" | "error";
type FileAttachState = "idle" | "attaching" | "error";
type FileBrowseState = "idle" | "browsing" | "error";
type ThreadNoticeTone = "info" | "degraded" | "blocked" | null;
type ConversationListView = "active" | "archived";
type StewardshipBusyAction =
  | "inspect_file"
  | "read_file"
  | "propose_patch"
  | "apply_patch"
  | "plan_file_operation"
  | "execute_file_operation"
  | "inspect_document"
  | "extract_document"
  | "plan_document_export"
  | "apply_document_export"
  | "plan_document_edit"
  | "apply_document_edit"
  | "inspect_data"
  | "preview_data"
  | "plan_data_export"
  | "apply_data_export"
  | "plan_data_mutation"
  | "apply_data_mutation"
  | "inspect_visual"
  | "preview_visual"
  | "ocr_visual"
  | "analyze_visual"
  | "plan_visual_export"
  | "apply_visual_export"
  | "plan_visual_edit"
  | "apply_visual_edit"
  | "inspect_media"
  | "thumbnail_media"
  | "inspect_archive"
  | "plan_archive_extraction"
  | "apply_archive_extraction"
  | "inspect_database"
  | "preview_database_schema"
  | "inspect_binary"
  | "inspect_engineering"
  | "plan_engineering_preview"
  | "apply_engineering_preview"
  | "plan_transcription"
  | "apply_transcription"
  | "plan_tts"
  | "apply_tts"
  | "plan_videoforge"
  | "apply_videoforge"
  | "cancel_videoforge"
  | null;

type StewardshipOperationKind =
  | "create"
  | "edit"
  | "replace"
  | "delete"
  | "rename"
  | "move";

type StewardshipState = {
  busyAction: StewardshipBusyAction;
  error: string | null;
  notice: string | null;
  targetPath: string | null;
  workspaceRoot: string | null;
  fileInspection: CodingFileTypeInspection | null;
  filePreview: CodingFilePreview | null;
  patchProposal: CodingPatchProposal | null;
  patchApplyResult: CodingPatchApplyResult | null;
  fileOperationPlan: CodingFileOperationPlan | null;
  fileOperationResult: CodingFileOperationResult | null;
  documentInspection: CodingDocumentPreview | null;
  documentPreview: CodingDocumentPreview | null;
  documentExportPlan: CodingDocumentPlan | null;
  documentExportResult: CodingDocumentApplyResult | null;
  documentEditPlan: CodingDocumentPlan | null;
  documentEditResult: CodingDocumentApplyResult | null;
  dataInspection: CodingDataPreview | null;
  dataPreview: CodingDataPreview | null;
  dataExportPlan: CodingDataPlan | null;
  dataExportResult: CodingDataApplyResult | null;
  dataMutationPlan: CodingDataPlan | null;
  dataMutationResult: CodingDataApplyResult | null;
  visualInspection: CodingVisualPreview | null;
  visualPreview: CodingVisualPreview | null;
  visualOcr: Record<string, unknown> | null;
  visualAnalysis: Record<string, unknown> | null;
  visualExportPlan: CodingVisualPlan | null;
  visualExportResult: CodingVisualApplyResult | null;
  visualEditPlan: CodingVisualPlan | null;
  visualEditResult: CodingVisualApplyResult | null;
  mediaInspection: CodingMediaPreview | null;
  mediaThumbnail: CodingMediaPreview | null;
  archiveInspection: ArchiveContainerPreview | null;
  archiveExtractionPlan: ArchiveExtractionPlan | null;
  archiveExtractionResult: ArchiveExtractionResult | null;
  databaseInspection: DatabaseInspection | null;
  databaseSchema: DatabaseSchemaPreview | null;
  binaryInspection: BinaryInspection | null;
  engineeringInspection: EngineeringInspection | null;
  engineeringPreviewPlan: EngineeringPreviewPlan | null;
  engineeringPreviewResult: EngineeringPreviewResult | null;
  transcriptionPlan: SpeechTranscriptionPlan | null;
  transcriptionResult: SpeechTranscriptionResult | null;
  ttsPlan: SpeechTtsPlan | null;
  ttsResult: SpeechTtsResult | null;
  videoForgePlan: VideoForgePlan | null;
  videoForgeJob: VideoForgeJob | null;
};

type WorkingTraceState = {
  phaseLabel: string;
  phaseDetail: string | null;
  selectedMode: string | null;
  selectedRole: string | null;
  selectedRuntime: string | null;
  selectedModelRuntimeTag: string | null;
  localityState: string | null;
  approvalState: string | null;
  usedFallback: boolean | null;
  steps: string[];
};

type BackendConversationSummary = {
  conversation_id?: string;
  title?: string | null;
  last_message_preview?: string | null;
  updated_at_utc?: string | null;
  message_count?: number | null;
  current_mode?: string | null;
  current_role?: string | null;
  last_message_role?: string | null;
  project_id?: string | null;
  archived?: boolean | null;
  pinned?: boolean | null;
  capability_state?: string | null;
  locality?: string | null;
  approval_state?: string | null;
};

type BackendConversationListData = {
  conversations?: BackendConversationSummary[];
  active_conversation_id?: string | null;
  total?: number | null;
};

type BackendConversationMessage = {
  message_id?: string;
  conversation_id?: string;
  role?: string;
  content?: string;
  created_at_utc?: string | null;
  request_id?: string | null;
  invocation_status?: string | null;
  response_source?: string | null;
  selected_role?: string | null;
  selected_runtime?: string | null;
  selected_model_runtime_tag?: string | null;
  used_fallback?: boolean | null;
  fallback_from?: string | null;
  fallback_to?: string | null;
  approval_needed?: boolean | null;
  approval_state?: string | null;
  locality_state?: string | null;
  capability_state?: string | null;
  blocked?: boolean | null;
  degraded?: boolean | null;
  error?: string | null;
  warnings?: string[] | null;
  caveats?: string[] | null;
};

type BackendConversationMetadata = {
  conversation_id?: string;
  title?: string | null;
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
};

type BackendConversationThreadData = {
  conversation_id?: string;
  metadata?: BackendConversationMetadata | null;
  messages?: BackendConversationMessage[] | null;
  last_message_role?: string | null;
  message_count?: number | null;
};

type UiConversationSummary = {
  conversationId: string;
  title: string;
  displayTitle: string;
  preview: string | null;
  updatedAtUtc: string | null;
  messageCount: number;
  currentMode: string | null;
  currentRole: string | null;
  lastMessageRole: string | null;
  projectId: string | null;
  archived: boolean;
  pinned: boolean;
  capabilityState: string | null;
  locality: string | null;
  approvalState: string | null;
};

type UiConversationMessage = {
  messageId: string;
  conversationId: string | null;
  role: string;
  content: string;
  createdAtUtc: string | null;
  requestId: string | null;
  invocationStatus: string | null;
  responseSource: string | null;
  selectedRole: string | null;
  selectedRuntime: string | null;
  selectedModelRuntimeTag: string | null;
  usedFallback: boolean | null;
  fallbackFrom: string | null;
  fallbackTo: string | null;
  approvalNeeded: boolean | null;
  approvalState: string | null;
  localityState: string | null;
  capabilityState: string | null;
  blocked: boolean | null;
  degraded: boolean | null;
  error: string | null;
  warnings: string[];
  caveats: string[];
};

type UiConversationThread = {
  conversationId: string | null;
  title: string;
  displayTitle: string;
  preview: string | null;
  updatedAtUtc: string | null;
  messageCount: number;
  currentMode: string | null;
  currentRole: string | null;
  capabilityState: string | null;
  locality: string | null;
  approvalState: string | null;
  projectId: string | null;
  archived: boolean;
  pinned: boolean;
  lastMessageRole: string | null;
  messages: UiConversationMessage[];
};

type UiAttachedFile = {
  fileId: string;
  displayName: string;
  fileKind: string | null;
  processingState: string | null;
  memoryPosture: string | null;
  parserUsed: string | null;
  chunksCreatedCount: number | null;
  chunksUsedCount: number | null;
  memoryPromotionAllowed: boolean | null;
  outwardSharingAllowed: boolean | null;
  usableAsContext: boolean | null;
  ready: boolean | null;
  blocked: boolean | null;
  errors: string[];
};

type ModeMathProfile = {
  mode: string;
  label: string;
  summary: string;
  responseStyle: string;
  boundaryNote: string;
  capabilities: string[];
  useCases: string[];
};

type UiMathExecutionSummary = {
  used: boolean | null;
  status: string | null;
  toolKind: string | null;
  operation: string | null;
  input: string | null;
  result: string | null;
  numericResult: number | null;
  exactMatch: boolean | null;
  stayedLocal: boolean | null;
  approvalRequired: boolean | null;
  warnings: string[];
  errors: string[];
};

type UiDataExecutionSummary = {
  used: boolean | null;
  status: string | null;
  toolKind: string | null;
  operation: string | null;
  sourceKind: string | null;
  fileId: string | null;
  fileName: string | null;
  fileKind: string | null;
  rowCount: number | null;
  columnCount: number | null;
  columns: string[];
  numericColumns: string[];
  textColumns: string[];
  stayedLocal: boolean | null;
  approvalRequired: boolean | null;
  networkAccessUsed: boolean | null;
  mutatedFiles: boolean | null;
  warnings: string[];
  errors: string[];
};

type UiArtifactSummary = {
  artifactId: string;
  kind: string | null;
  title: string;
  summary: string | null;
  createdAtUtc: string | null;
  locality: string | null;
  memoryPosture: string | null;
  producerToolKind: string | null;
  producerOperation: string | null;
  sourceFileId: string | null;
  sourceFileName: string | null;
  sourceFileKind: string | null;
  rowCount: number | null;
  columnCount: number | null;
  plotKind: string | null;
  svgText: string | null;
  svgMimeType: string | null;
  width: number | null;
  height: number | null;
  metric: string | null;
  plottedColumns: string[];
  modelId: string | null;
  mimeType: string | null;
  outputSha256: string | null;
  outputBytes: number | null;
  syntheticMedia: boolean | null;
  warnings: string[];
  errors: string[];
};

type UiRepoContextSummary = {
  used: boolean | null;
  status: string | null;
  toolKind: string | null;
  operation: string | null;
  repoKey: string | null;
  repoLabel: string | null;
  repoRoot: string | null;
  trustZone: string | null;
  appearsGitRepo: boolean | null;
  currentBranch: string | null;
  gitHeadRead: boolean | null;
  changedFilesLive: boolean | null;
  changedFilesNote: string | null;
  importantTopLevelFiles: string[];
  topLevelDirectories: string[];
  safeTreeEntries: string[];
  languageHints: string[];
  frameworkHints: string[];
  testCommandHints: string[];
  readOnly: boolean | null;
  approvalRequired: boolean | null;
  networkAccessUsed: boolean | null;
  shellUsed: boolean | null;
  mutatedFiles: boolean | null;
  warnings: string[];
  errors: string[];
};

type UiCodePatchPlanSummary = {
  used: boolean | null;
  status: string | null;
  toolKind: string | null;
  operation: string | null;
  summary: string | null;
  repoKey: string | null;
  repoRoot: string | null;
  filesToTouch: string[];
  patchPlan: string[];
  testsToRun: string[];
  riskNotes: string[];
  rollbackNotes: string[];
  approvalNeeded: boolean | null;
  approvalReason: string | null;
  canApplyPatch: boolean | null;
  patchApplicationLive: boolean | null;
  shellExecutionUsed: boolean | null;
  networkAccessUsed: boolean | null;
  mutatedFiles: boolean | null;
  externalWorkersUsed: boolean | null;
  warnings: string[];
  errors: string[];
};

const palette = {
  bronze: "#8A6A3C",
  oxide: "#8B4E2F",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  lineBronze: "rgba(138, 106, 60, 0.30)",
  lineTeal: "rgba(126, 215, 209, 0.24)",
  panel: "rgba(18, 25, 37, 0.92)",
  panelInset: "rgba(11, 14, 18, 0.64)",
  panelRaised: "rgba(24, 33, 48, 0.88)",
  glowTeal: "rgba(126, 215, 209, 0.14)",
  glowBronze: "rgba(138, 106, 60, 0.12)",
  glowEmerald: "rgba(47, 138, 104, 0.14)"
} as const;

const MODE_OPTIONS = [
  { value: "default", label: "Default" },
  { value: "tutor", label: "Tutor" },
  { value: "researcher", label: "Researcher" },
  { value: "writer", label: "Writer" },
  { value: "coder", label: "Coder" }
] as const;

const MODE_MATH_PROFILES: Record<string, ModeMathProfile> = {
  default: {
    mode: "default",
    label: "Default math",
    summary:
      "Quiet calculator-style support for ordinary conversation, arithmetic checks, unit checks, simple equations, and quick numerical sanity checks.",
    responseStyle:
      "Direct and brief unless the user asks for steps. Use the bounded local math lane as a quiet truth check, not as a full lesson.",
    boundaryNote:
      "Bounded local math only. No arbitrary Python, shell, web, file mutation, or external computation.",
    capabilities: [
      "Evaluate arithmetic and expressions",
      "Check percent change and reduction math",
      "Simplify straightforward expressions",
      "Solve simple equations when clearly requested",
      "Catch obvious arithmetic or unit mistakes"
    ],
    useCases: [
      "Is my percent reduction calculation right?",
      "Evaluate this expression.",
      "Check this unit conversion.",
      "Give me the number without turning it into a full lesson."
    ]
  },
  tutor: {
    mode: "tutor",
    label: "Tutor math",
    summary:
      "Wolfram-style calculation plus step-by-step teaching for algebra, calculus, chemistry math, physics math, and homework-style reasoning.",
    responseStyle:
      "Teach the method, show the reasoning, identify mistakes gently, and use local math execution as a verification layer.",
    boundaryNote:
      "Bounded local math can verify calculations, but the explanation should remain educational and not hide the reasoning.",
    capabilities: [
      "Evaluate and verify expressions",
      "Explain algebra and calculus steps",
      "Check student work and locate the first mistake",
      "Support derivatives, integrals, equations, and unit-aware homework reasoning",
      "Separate conceptual misunderstanding from arithmetic error"
    ],
    useCases: [
      "Walk me through this derivative.",
      "Check my algebra and tell me where I went wrong.",
      "Explain the formula before plugging in numbers.",
      "Help me learn it, not just get the answer."
    ]
  },
  researcher: {
    mode: "researcher",
    label: "Research math",
    summary:
      "Engineering, ecology, and research-oriented calculation support with assumptions, units, provenance, uncertainty, and reproducible reasoning.",
    responseStyle:
      "Be precise, assumption-explicit, and conservative. Report what was computed, what was assumed, and what still needs validation.",
    boundaryNote:
      "Bounded local math supports calculations and sanity checks, but does not replace statistical analysis, external datasets, or validated models.",
    capabilities: [
      "Check research calculations and derived quantities",
      "Support dimensional reasoning and unit sanity checks",
      "Compare formulas and assumptions",
      "Estimate scales, rates, ratios, and uncertainty-sensitive values",
      "Prepare calculation notes suitable for research documentation"
    ],
    useCases: [
      "Check this engineering calculation.",
      "Does this scaling assumption make physical sense?",
      "Calculate this ratio and state assumptions.",
      "Help me write a reproducible calculation note."
    ]
  },
  writer: {
    mode: "writer",
    label: "Writer math",
    summary:
      "Creative realism support that uses calculation to ground stories, worlds, creatures, ships, disasters, ecologies, and technologies.",
    responseStyle:
      "Stay creative and vivid, but use math as a realism compass. Hide calculations unless the user wants to see them.",
    boundaryNote:
      "Bounded local math can estimate scale and plausibility, but the result should serve story truth rather than overwhelm the prose.",
    capabilities: [
      "Estimate travel time, distance, mass, speed, energy, and scale",
      "Ground sci-fi, fantasy, and ecological worldbuilding in plausible constraints",
      "Check whether scenes feel physically or biologically believable",
      "Convert calculations into natural prose",
      "Create constraints that make fictional systems feel real"
    ],
    useCases: [
      "How long would this airship trip take?",
      "Would this creature size make biological sense?",
      "How much water would this settlement need?",
      "Make this scene feel scientifically grounded without sounding like homework."
    ]
  },
  coder: {
    mode: "coder",
    label: "Coder checks",
    summary:
      "Coding posture for repo-aware reasoning, read-only repo context, proposal-only patch planning, dry-run worker truth, debugging, test planning, and review. Patch application and shell execution remain approval-gated/not live.",
    responseStyle:
      "Be precise, patch-oriented, test-aware, and approval-gated. Prefer repo context and proposal-only patch planning when governed paths are available. Do not claim files changed, tests ran, shell executed, git mutated, or external workers ran unless trace truth says so.",
    boundaryNote:
      "Coder mode can surface repo context and proposal-only patch plans when governed paths are available. It must not claim file mutation, shell execution, package installs, git mutation, or external workers ran unless they actually did. Patch application remains not live unless a later approved path grants it.",
    capabilities: [
      "Read selected repo context when available",
      "Draft proposal-only patch plans",
      "Suggest tests to run",
      "Surface Aider dry-run/skeleton validation truth",
      "Review proposed changes",
      "Keep mutation, shell, package install, git, and external-worker authority approval-gated"
    ],
    useCases: [
      "Inspect this repo path and summarize relevant files.",
      "Draft a proposal-only patch plan.",
      "Explain which tests should be run after approval.",
      "Show whether any worker, mutation, shell, git, or test execution actually ran."
    ]
  }
};

const REQUEST_TRACE_POLL_INTERVAL_MS = 450;
const REQUEST_TRACE_STARTUP_GRACE_MS = 1200;
const MAX_TRACE_STEPS = 4;
const CONVERSATIONS_COMPACT_LAYOUT_BREAKPOINT_PX = 760;
const conversationPinImageUrl = new URL(
  "../elysia-personal-portfolio/Conversation_Pin.png",
  import.meta.url
).href;

function safeString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function humanize(value: string | null | undefined): string {
  const text = safeString(value);

  if (!text) {
    return "Not surfaced";
  }

  return text
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function safeBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function safeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry) => safeString(entry))
    .filter((entry): entry is string => Boolean(entry));
}

function truncate(value: string | null | undefined, limit: number): string | null {
  const text = safeString(value);
  if (!text) {
    return null;
  }

  if (text.length <= limit) {
    return text;
  }

  return `${text.slice(0, Math.max(1, limit - 1)).trimEnd()}…`;
}

function formatTimestamp(value: string | null): string | null {
  const text = safeString(value);
  if (!text) {
    return null;
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }

  return date.toLocaleString();
}

function getConversationDisplayTitle(
  title: string | null,
  preview: string | null,
  firstUserMessage: string | null = null
): string {
  const cleanTitle = safeString(title);
  if (cleanTitle && cleanTitle !== "New conversation") {
    return cleanTitle;
  }

  const fallback = truncate(preview, 56) ?? truncate(firstUserMessage, 56);
  return fallback ?? cleanTitle ?? "New conversation";
}

function getEnvelopeData<T>(payload: unknown): T | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  if (!("data" in payload)) {
    return null;
  }

  const data = (payload as { data?: unknown }).data;
  if (!data || typeof data !== "object") {
    return null;
  }

  return data as T;
}

function getEnvelopePrimaryError(
  payload: { errors?: string[] } | null | undefined,
  fallback: string
): string {
  const primaryError = payload?.errors?.find(
    (entry) => typeof entry === "string" && entry.trim().length > 0
  );

  return primaryError?.trim() ?? fallback;
}

function shouldLogMutationDebug(): boolean {
  try {
    return Boolean(import.meta.env?.DEV);
  } catch {
    return false;
  }
}

function logMutationDebug(
  label: string,
  context: Record<string, unknown>
): void {
  if (!shouldLogMutationDebug()) {
    return;
  }

  console.error(`[ConversationsPage] ${label}`, context);
}

function normalizeConversationSummary(
  summary: BackendConversationSummary
): UiConversationSummary | null {
  const conversationId = safeString(summary.conversation_id);
  if (!conversationId) {
    return null;
  }

  const preview = truncate(summary.last_message_preview, 120);

  return {
    conversationId,
    title: safeString(summary.title) ?? "New conversation",
    displayTitle: getConversationDisplayTitle(summary.title ?? null, preview),
    preview,
    updatedAtUtc: safeString(summary.updated_at_utc),
    messageCount:
      typeof summary.message_count === "number" && summary.message_count >= 0
        ? summary.message_count
        : 0,
    currentMode: safeString(summary.current_mode),
    currentRole: safeString(summary.current_role),
    lastMessageRole: safeString(summary.last_message_role),
    projectId: safeString(summary.project_id),
    archived: summary.archived === true,
    pinned: summary.pinned === true,
    capabilityState: safeString(summary.capability_state),
    locality: safeString(summary.locality),
    approvalState: safeString(summary.approval_state)
  };
}

function normalizeConversationMessage(
  message: BackendConversationMessage
): UiConversationMessage | null {
  const role = safeString(message.role) ?? "unknown";
  const content = safeString(message.content);
  if (!content) {
    return null;
  }

  return {
    messageId: safeString(message.message_id) ?? `msg_${Math.random().toString(16).slice(2)}`,
    conversationId: safeString(message.conversation_id),
    role,
    content,
    createdAtUtc: safeString(message.created_at_utc),
    requestId: safeString(message.request_id),
    invocationStatus: safeString(message.invocation_status),
    responseSource: safeString(message.response_source),
    selectedRole: safeString(message.selected_role),
    selectedRuntime: safeString(message.selected_runtime),
    selectedModelRuntimeTag: safeString(message.selected_model_runtime_tag),
    usedFallback: safeBoolean(message.used_fallback),
    fallbackFrom: safeString(message.fallback_from),
    fallbackTo: safeString(message.fallback_to),
    approvalNeeded: safeBoolean(message.approval_needed),
    approvalState: safeString(message.approval_state),
    localityState: safeString(message.locality_state),
    capabilityState: safeString(message.capability_state),
    blocked: safeBoolean(message.blocked),
    degraded: safeBoolean(message.degraded),
    error: safeString(message.error),
    warnings: safeStringArray(message.warnings),
    caveats: safeStringArray(message.caveats)
  };
}

function normalizeConversationThread(
  data: BackendConversationThreadData
): UiConversationThread | null {
  const metadata = data.metadata ?? {};
  const conversationId =
    safeString(data.conversation_id) ?? safeString(metadata.conversation_id);

  if (!conversationId) {
    return null;
  }

  const messages = Array.isArray(data.messages)
    ? data.messages
        .map((message) => normalizeConversationMessage(message))
        .filter((message): message is UiConversationMessage => Boolean(message))
    : [];

  const firstUserMessage =
    messages.find((message) => message.role === "user")?.content ?? null;

  const preview = truncate(metadata.last_message_preview, 120);

  return {
    conversationId,
    title: safeString(metadata.title) ?? "New conversation",
    displayTitle: getConversationDisplayTitle(
      metadata.title ?? null,
      preview,
      firstUserMessage
    ),
    preview,
    updatedAtUtc: safeString(metadata.updated_at_utc),
    messageCount:
      typeof data.message_count === "number" && data.message_count >= 0
        ? data.message_count
        : typeof metadata.message_count === "number" && metadata.message_count >= 0
          ? metadata.message_count
          : messages.length,
    currentMode: safeString(metadata.current_mode),
    currentRole: safeString(metadata.current_role),
    capabilityState: safeString(metadata.capability_state),
    locality: safeString(metadata.locality),
    approvalState: safeString(metadata.approval_state),
    projectId: safeString(metadata.project_id),
    archived: metadata.archived === true,
    pinned: metadata.pinned === true,
    lastMessageRole: safeString(data.last_message_role),
    messages
  };
}

function chooseActiveConversationId(
  items: UiConversationSummary[],
  preferredId: string | null,
  backendSuggestedId: string | null,
  currentActiveId: string | null
): string | null {
  const ids = new Set(items.map((item) => item.conversationId));

  if (preferredId && ids.has(preferredId)) {
    return preferredId;
  }

  if (backendSuggestedId && ids.has(backendSuggestedId)) {
    return backendSuggestedId;
  }

  if (currentActiveId && ids.has(currentActiveId)) {
    return currentActiveId;
  }

  return items[0]?.conversationId ?? null;
}

function filterConversationListByView(
  items: UiConversationSummary[],
  view: ConversationListView
): UiConversationSummary[] {
  if (view === "archived") {
    return items.filter((item) => item.archived);
  }

  return items.filter((item) => !item.archived);
}

function getConversationListEmptyMessage(view: ConversationListView): string {
  if (view === "archived") {
    return "No archived conversations are visible yet.";
  }

  return "No active conversations are visible here yet. Start a new one from the right side or switch to Archived.";
}

function getLatestAssistantMessage(
  messages: UiConversationMessage[]
): UiConversationMessage | null {
  const reversed = [...messages].reverse();
  return reversed.find((message) => message.role === "assistant") ?? null;
}

function normalizeSendTruth(payload: unknown): ResponseTruth {
  const envelope = (payload ?? {}) as Parameters<typeof readResponseTruth>[0];
  const baseTruth = readResponseTruth(envelope);

  const data = getEnvelopeData<Record<string, unknown>>(payload) ?? {};
  const selectedRole =
    baseTruth.selectedRole ?? safeString(data.selected_model_role);

  return {
    ...baseTruth,
    selectedRole
  };
}

function extractConversationIdFromSendPayload(payload: unknown): string | null {
  const data = getEnvelopeData<Record<string, unknown>>(payload);
  return safeString(data?.conversation_id);
}

function normalizeAttachedFile(
  result: FileIngestResult | null | undefined
): UiAttachedFile | null {
  const fileId = safeString(result?.file_id);
  if (!fileId) {
    return null;
  }

  const displayName =
    safeString(result?.file?.display_name) ??
    safeString(result?.file?.original_name) ??
    fileId;
  const processingState =
    safeString(result?.file?.processing_state) ??
    safeString(result?.processing_state);
  const memoryPosture =
    safeString(result?.file?.memory_posture) ??
    safeString(result?.context_summary?.memory_posture) ??
    "not_memory";

  return {
    fileId,
    displayName,
    fileKind:
      safeString(result?.file?.file_kind) ??
      safeString(result?.context_summary?.file_kind),
    processingState,
    memoryPosture,
    parserUsed:
      safeString(result?.file?.parser_used) ??
      safeString(result?.context_summary?.parser_used),
    chunksCreatedCount:
      safeNumber(result?.file?.chunks_created_count) ??
      safeNumber(result?.context_summary?.chunk_count),
    chunksUsedCount:
      safeNumber(result?.file?.chunks_used_count) ??
      safeNumber(result?.context_summary?.selected_chunk_count),
    memoryPromotionAllowed:
      safeBoolean(result?.file?.memory_promotion_allowed) ??
      safeBoolean(result?.context_summary?.memory_promotion_allowed) ??
      false,
    outwardSharingAllowed:
      safeBoolean(result?.file?.outward_sharing_allowed) ??
      safeBoolean(result?.context_summary?.outward_sharing_allowed) ??
      false,
    usableAsContext: safeBoolean(result?.context_summary?.usable_as_context),
    ready: safeBoolean(result?.ready),
    blocked: safeBoolean(result?.blocked),
    errors: safeStringArray(result?.errors)
  };
}


function isReadyAttachedContextFile(file: UiAttachedFile): boolean {
  const processingState = safeString(file.processingState)?.toLowerCase();

  if (file.blocked === true || processingState === "blocked" || processingState === "failed") {
    return false;
  }

  if (file.usableAsContext === false) {
    return false;
  }

  return file.ready === true || processingState === "ready";
}

function isCsvAttachedFile(file: UiAttachedFile): boolean {
  const fileKind = safeString(file.fileKind)?.toLowerCase();

  return fileKind === "csv" || fileKind === "xlsx";
}

function isTextContextAttachedFile(file: UiAttachedFile): boolean {
  const fileKind = safeString(file.fileKind)?.toLowerCase();

  return [
    "text",
    "markdown",
    "json",
    "html",
    "pdf",
    "docx",
    "pptx",
    "odt",
    "odp"
  ].includes(fileKind ?? "");
}

function formatAttachedFileNames(files: UiAttachedFile[], emptyText: string): string {
  if (files.length === 0) {
    return emptyText;
  }

  return files.map((file) => file.displayName).join(", ");
}

function formatCompactList(
  values: string[],
  emptyText: string,
  limit = 4
): string {
  if (values.length === 0) {
    return emptyText;
  }

  const visible = values.slice(0, limit);
  const remainder = values.length - visible.length;
  return remainder > 0
    ? `${visible.join(", ")} + ${remainder} more`
    : visible.join(", ");
}

function buildAttachedFileRequestContext(
  files: UiAttachedFile[]
): Record<string, unknown> | null {
  const attachedFileIds = files
    .filter((file) => isReadyAttachedContextFile(file))
    .map((file) => file.fileId);

  if (attachedFileIds.length === 0) {
    return null;
  }

  return {
    attached_file_ids: attachedFileIds,
    attached_files_are_memory: false,
    attached_files_source: "user_selected_local_files",
    attached_context_note:
      "Attached files are local, user-selected inputs only. TXT/Markdown/JSON/saved HTML/PDF/DOCX may be used as bounded text context when local parser support is available. CSV/XLSX may be used for bounded local data summary. They are not memory and are not shared outward by default."
  };
}

function getModeMathProfile(mode: string): ModeMathProfile {
  return MODE_MATH_PROFILES[mode] ?? MODE_MATH_PROFILES.default;
}

function buildModeMathRequestContext(mode: string): Record<string, unknown> {
  const profile = getModeMathProfile(mode);
  const baseContext: Record<string, unknown> = {
    math_profile_id: profile.mode,
    math_profile_label: profile.label,
    math_profile_summary: profile.summary,
    math_profile_capabilities: profile.capabilities,
    math_profile_use_cases: profile.useCases,
    math_profile_response_style: profile.responseStyle,
    math_execution_available: true,
    math_execution_policy: "bounded_local_non_side_effecting",
    math_boundary_note: profile.boundaryNote
  };

  if (profile.mode === "coder") {
    return {
      ...baseContext,
      coder_mode_posture: "repo_aware_proposal_only",
      coder_repo_inspection_state: "governed_read_only_when_selected",
      coder_patch_planning_state: "proposal_only_when_explicit_files_exist",
      coder_patch_application_state: "not_live_approval_required",
      coder_shell_execution_state: "blocked_not_live",
      coder_external_workers_state: "aider_skeleton_dry_run_only",
      coder_boundary_note: profile.boundaryNote
    };
  }

  return baseContext;
}

function mergeRequestContexts(
  ...contexts: Array<Record<string, unknown> | null>
): Record<string, unknown> | null {
  const merged: Record<string, unknown> = {};

  for (const context of contexts) {
    if (!context) {
      continue;
    }

    Object.assign(merged, context);
  }

  return Object.keys(merged).length > 0 ? merged : null;
}

function createInitialStewardshipState(): StewardshipState {
  return {
    busyAction: null,
    error: null,
    notice: null,
    targetPath: null,
    workspaceRoot: null,
    fileInspection: null,
    filePreview: null,
    patchProposal: null,
    patchApplyResult: null,
    fileOperationPlan: null,
    fileOperationResult: null,
    documentInspection: null,
    documentPreview: null,
    documentExportPlan: null,
    documentExportResult: null,
    documentEditPlan: null,
    documentEditResult: null,
    dataInspection: null,
    dataPreview: null,
    dataExportPlan: null,
    dataExportResult: null,
    dataMutationPlan: null,
    dataMutationResult: null,
    visualInspection: null,
    visualPreview: null,
    visualOcr: null,
    visualAnalysis: null,
    visualExportPlan: null,
    visualExportResult: null,
    visualEditPlan: null,
    visualEditResult: null,
    mediaInspection: null,
    mediaThumbnail: null,
    archiveInspection: null,
    archiveExtractionPlan: null,
    archiveExtractionResult: null,
    databaseInspection: null,
    databaseSchema: null,
    binaryInspection: null,
    engineeringInspection: null,
    engineeringPreviewPlan: null,
    engineeringPreviewResult: null,
    transcriptionPlan: null,
    transcriptionResult: null,
    ttsPlan: null,
    ttsResult: null,
    videoForgePlan: null,
    videoForgeJob: null
  };
}

function deriveWorkspaceRoot(targetPath: string): string | null {
  const trimmed = safeString(targetPath);
  if (!trimmed) {
    return null;
  }

  const normalized = trimmed.replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  if (index <= 0) {
    return null;
  }

  return normalized.slice(0, index);
}

function getFileLabelFromPath(targetPath: string): string {
  const normalized = targetPath.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? targetPath;
}

function getStewardshipTarget(
  filePathDraft: string
): { targetPath: string; workspaceRoot: string } | { error: string } {
  const targetPath = safeString(filePathDraft);
  if (!targetPath) {
    return {
      error:
        "Choose or paste a local file path first. Stewardship actions require an explicit operator-selected file."
    };
  }

  const workspaceRoot = deriveWorkspaceRoot(targetPath);
  if (!workspaceRoot) {
    return {
      error:
        "Use an absolute or folder-qualified local path so Elysia can derive a bounded workspace root."
    };
  }

  return { targetPath, workspaceRoot };
}

function buildApprovedStewardshipRequestContext(
  filePreview: CodingFilePreview | null,
  documentPreview: CodingDocumentPreview | null,
  dataPreview: CodingDataPreview | null,
  visualPreview: CodingVisualPreview | null,
  mediaPreview: CodingMediaPreview | null
): Record<string, unknown> | null {
  const context: Record<string, unknown> = {
    stewardship_context_source: "explicit_operator_approved_local_preview",
    stewardship_context_memory_posture: "not_memory",
    stewardship_context_outward_sharing_allowed: false,
    stewardship_context_absolute_paths_included: false
  };

  let hasContext = false;

  if (
    filePreview?.status === "completed" &&
    filePreview.source_contents_included === true &&
    safeString(filePreview.content_preview)
  ) {
    hasContext = true;
    context.approved_file_context = {
      file_label: safeString(filePreview.file_label) ?? "approved file",
      relative_path: safeString(filePreview.relative_path) ?? "selected file",
      language_hint:
        safeString(filePreview.language_hint) ??
        safeString(filePreview.language_id) ??
        safeString(filePreview.file_type_id),
      path_hash: safeString(filePreview.path_hash),
      content_hash: safeString(filePreview.content_hash),
      file_type_id: safeString(filePreview.file_type_id),
      file_type_label: safeString(filePreview.file_type_label),
      category: safeString(filePreview.category),
      adapter: safeString(filePreview.adapter),
      parse_status: safeString(filePreview.parse_status),
      redaction_count: filePreview.redactions?.length ?? 0,
      source_contents_included: true,
      approval_granted: true,
      content_preview: filePreview.content_preview
    };
  }

  if (
    documentPreview?.status === "completed" &&
    safeString(documentPreview.text_preview)
  ) {
    hasContext = true;
    context.approved_document_context = {
      file_label: safeString(documentPreview.file_label) ?? "approved document",
      relative_path: safeString(documentPreview.relative_path) ?? "selected document",
      path_hash: safeString(documentPreview.path_hash),
      document_type_id: safeString(documentPreview.descriptor?.type_id),
      document_label: safeString(documentPreview.descriptor?.label),
      adapter: safeString(documentPreview.descriptor?.adapter),
      table_count: documentPreview.tables?.length ?? 0,
      outline_count: documentPreview.outline?.length ?? 0,
      provenance_count: documentPreview.provenance?.length ?? 0,
      redaction_count: documentPreview.redactions?.length ?? 0,
      source_contents_included: true,
      approval_granted: true,
      text_preview: documentPreview.text_preview,
      metadata: documentPreview.metadata ?? {},
      provenance: (documentPreview.provenance ?? []).slice(0, 12)
    };
  }

  if (dataPreview?.status === "completed" || dataPreview?.status === "reduced_dependency_missing") {
    hasContext = true;
    context.approved_data_context = {
      file_label: safeString(dataPreview.file_label) ?? "approved data file",
      relative_path: safeString(dataPreview.relative_path) ?? "selected data file",
      path_hash: safeString(dataPreview.path_hash),
      content_hash: safeString(dataPreview.content_hash),
      data_type_id: safeString(dataPreview.descriptor?.type_id),
      data_label: safeString(dataPreview.descriptor?.label),
      adapter: safeString(dataPreview.descriptor?.adapter),
      category: safeString(dataPreview.descriptor?.category),
      status: safeString(dataPreview.status),
      redaction_count: dataPreview.redaction_count ?? 0,
      preview_truncated: dataPreview.preview_truncated === true,
      source_contents_included: false,
      approval_granted: true,
      metadata: dataPreview.metadata ?? {},
      schema_summary: dataPreview.schema_summary ?? {},
      preview: dataPreview.preview ?? {},
      layers: (dataPreview.layers ?? []).slice(0, 8),
      tables: (dataPreview.tables ?? []).slice(0, 8),
      bands: (dataPreview.bands ?? []).slice(0, 8),
      dimensions: (dataPreview.dimensions ?? []).slice(0, 8),
      variables: (dataPreview.variables ?? []).slice(0, 8),
      provenance_refs: (dataPreview.provenance_refs ?? []).slice(0, 12),
      warnings: (dataPreview.warnings ?? []).slice(0, 8)
    };
  }

  if (visualPreview?.status === "completed") {
    hasContext = true;
    context.approved_visual_context = {
      file_label: safeString(visualPreview.file_label) ?? "approved visual file",
      relative_path: safeString(visualPreview.relative_path) ?? "selected visual file",
      path_hash: safeString(visualPreview.path_hash),
      content_hash: safeString(visualPreview.content_hash),
      visual_type_id: safeString(visualPreview.descriptor?.type_id),
      visual_label: safeString(visualPreview.descriptor?.label),
      adapter: safeString(visualPreview.descriptor?.adapter),
      category: safeString(visualPreview.descriptor?.category),
      status: safeString(visualPreview.status),
      source_contents_included: false,
      raw_pixels_included: false,
      precise_exif_gps_included: false,
      approval_granted: true,
      metadata: visualPreview.metadata ?? {},
      exif_privacy: visualPreview.exif_privacy ?? {},
      svg_safety: visualPreview.svg_safety ?? {},
      warnings: (visualPreview.warnings ?? []).slice(0, 8)
    };
  }

  if (mediaPreview?.status === "completed") {
    hasContext = true;
    context.approved_media_context = {
      file_label: safeString(mediaPreview.file_label) ?? "approved media file",
      relative_path: safeString(mediaPreview.relative_path) ?? "selected media file",
      path_hash: safeString(mediaPreview.path_hash),
      content_hash: safeString(mediaPreview.content_hash),
      media_type_id: safeString(mediaPreview.descriptor?.type_id),
      media_family: safeString(mediaPreview.media_family),
      container: safeString(mediaPreview.container),
      duration_seconds: mediaPreview.duration_seconds ?? null,
      bitrate_bps: mediaPreview.bitrate_bps ?? null,
      stream_count: mediaPreview.stream_count ?? 0,
      audio: mediaPreview.audio ?? {},
      video: mediaPreview.video ?? {},
      privacy_flags: mediaPreview.privacy_flags ?? {},
      safety_flags: mediaPreview.safety_flags ?? {},
      approval_granted: true,
      source_contents_included: false,
      raw_media_included: false
    };
  }

  if (!hasContext) {
    return null;
  }

  context.stewardship_context_note =
    "Elysia may use only this explicitly approved bounded local preview in the current conversation. It is not memory, excludes absolute source paths, and must not be shared outward by default.";
  return context;
}

function formatObjectSummary(value: Record<string, unknown> | undefined): string {
  if (!value || Object.keys(value).length === 0) {
    return "Not surfaced";
  }

  return Object.entries(value)
    .slice(0, 6)
    .map(([key, entry]) => `${humanize(key)}: ${String(entry)}`)
    .join(" · ");
}

function normalizeMathExecutionFromSendPayload(
  payload: unknown
): UiMathExecutionSummary | null {
  const data = getEnvelopeData<Record<string, unknown>>(payload);
  const rawMathExecution = data?.math_execution;

  if (
    !rawMathExecution ||
    typeof rawMathExecution !== "object" ||
    Array.isArray(rawMathExecution)
  ) {
    return null;
  }

  const record = rawMathExecution as Record<string, unknown>;
  const used = safeBoolean(record.used);
  const status = safeString(record.status);
  const toolKind = safeString(record.tool_kind);
  const operation = safeString(record.operation);
  const input = safeString(record.input);
  const result = safeString(record.result);
  const numericResult = safeNumber(record.numeric_result);

  if (
    used === null &&
    !status &&
    !toolKind &&
    !operation &&
    !input &&
    !result &&
    numericResult === null
  ) {
    return null;
  }

  return {
    used,
    status,
    toolKind,
    operation,
    input,
    result,
    numericResult,
    exactMatch: safeBoolean(record.exact_match),
    stayedLocal: safeBoolean(record.stayed_local),
    approvalRequired: safeBoolean(record.approval_required),
    warnings: safeStringArray(record.warnings),
    errors: safeStringArray(record.errors)
  };
}

function summarizeMathExecution(
  execution: UiMathExecutionSummary | null
): string {
  if (!execution) {
    return "No math execution recorded in current room state";
  }

  const parts = [
    execution.status ? humanize(execution.status) : null,
    execution.operation ? humanize(execution.operation) : null,
    execution.result ? `result ${execution.result}` : null,
    execution.numericResult !== null ? `numeric ${execution.numericResult}` : null
  ].filter((part): part is string => Boolean(part));

  return parts.length > 0 ? parts.join(" · ") : "Math execution surfaced without summary details";
}

function normalizeDataExecutionFromSendPayload(
  payload: unknown
): UiDataExecutionSummary | null {
  const data = getEnvelopeData<Record<string, unknown>>(payload);
  const rawDataExecution = data?.data_execution;

  if (
    !rawDataExecution ||
    typeof rawDataExecution !== "object" ||
    Array.isArray(rawDataExecution)
  ) {
    return null;
  }

  const record = rawDataExecution as Record<string, unknown>;
  const used = safeBoolean(record.used);
  const status = safeString(record.status);
  const toolKind = safeString(record.tool_kind);
  const operation = safeString(record.operation);
  const fileId = safeString(record.file_id);
  const fileName = safeString(record.file_name);
  const rowCount = safeNumber(record.row_count);
  const columnCount = safeNumber(record.column_count);

  if (
    used === null &&
    !status &&
    !toolKind &&
    !operation &&
    !fileId &&
    !fileName &&
    rowCount === null &&
    columnCount === null
  ) {
    return null;
  }

  return {
    used,
    status,
    toolKind,
    operation,
    sourceKind: safeString(record.source_kind),
    fileId,
    fileName,
    fileKind: safeString(record.file_kind),
    rowCount,
    columnCount,
    columns: safeStringArray(record.columns),
    numericColumns: safeStringArray(record.numeric_columns),
    textColumns: safeStringArray(record.text_columns),
    stayedLocal: safeBoolean(record.stayed_local),
    approvalRequired: safeBoolean(record.approval_required),
    networkAccessUsed: safeBoolean(record.network_access_used),
    mutatedFiles: safeBoolean(record.mutated_files),
    warnings: safeStringArray(record.warnings),
    errors: safeStringArray(record.errors)
  };
}

function summarizeDataExecution(
  execution: UiDataExecutionSummary | null
): string {
  if (!execution) {
    return "No data execution recorded in current room state";
  }

  if (execution.used === false) {
    return "No data execution used on latest response";
  }

  const parts = [
    execution.status ? humanize(execution.status) : null,
    execution.operation ? humanize(execution.operation) : null,
    execution.fileName ?? execution.fileId,
    execution.rowCount !== null ? `${execution.rowCount} rows` : null,
    execution.columnCount !== null ? `${execution.columnCount} columns` : null
  ].filter((part): part is string => Boolean(part));

  return parts.length > 0
    ? parts.join(" · ")
    : "Data execution surfaced without summary details";
}


function normalizeRepoContextFromSendPayload(
  payload: unknown
): UiRepoContextSummary | null {
  const data = getEnvelopeData<Record<string, unknown>>(payload);
  const rawRepoContext = data?.repo_context;

  if (
    !rawRepoContext ||
    typeof rawRepoContext !== "object" ||
    Array.isArray(rawRepoContext)
  ) {
    return null;
  }

  const record = rawRepoContext as RepoContextSummaryData;
  const used = safeBoolean(record.used);
  const status = safeString(record.status);
  const toolKind = safeString(record.tool_kind);
  const repoKey = safeString(record.repo_key);
  const repoLabel = safeString(record.repo_label);
  const repoRoot = safeString(record.repo_root);

  if (
    used === null &&
    !status &&
    !toolKind &&
    !repoKey &&
    !repoLabel &&
    !repoRoot
  ) {
    return null;
  }

  return {
    used,
    status,
    toolKind,
    operation: safeString(record.operation),
    repoKey,
    repoLabel,
    repoRoot,
    trustZone: safeString(record.trust_zone),
    appearsGitRepo: safeBoolean(record.appears_git_repo),
    currentBranch: safeString(record.current_branch),
    gitHeadRead: safeBoolean(record.git_head_read),
    changedFilesLive: safeBoolean(record.changed_files_live),
    changedFilesNote: safeString(record.changed_files_note),
    importantTopLevelFiles: safeStringArray(record.important_top_level_files),
    topLevelDirectories: safeStringArray(record.top_level_directories),
    safeTreeEntries: safeStringArray(record.safe_tree_entries),
    languageHints: safeStringArray(record.language_hints),
    frameworkHints: safeStringArray(record.framework_hints),
    testCommandHints: safeStringArray(record.test_command_hints),
    readOnly: safeBoolean(record.read_only),
    approvalRequired: safeBoolean(record.approval_required),
    networkAccessUsed: safeBoolean(record.network_access_used),
    shellUsed: safeBoolean(record.shell_used),
    mutatedFiles: safeBoolean(record.mutated_files),
    warnings: safeStringArray(record.warnings),
    errors: safeStringArray(record.errors)
  };
}

function summarizeRepoContext(repoContext: UiRepoContextSummary | null): string {
  if (!repoContext) {
    return "No repo context recorded in current room state";
  }

  if (repoContext.used === false) {
    return "Repo context not used on latest response";
  }

  const parts = [
    repoContext.status ? humanize(repoContext.status) : null,
    repoContext.repoLabel ?? repoContext.repoKey,
    repoContext.currentBranch ? `branch ${repoContext.currentBranch}` : null,
    repoContext.safeTreeEntries.length > 0
      ? `${repoContext.safeTreeEntries.length} safe entries`
      : null
  ].filter((part): part is string => Boolean(part));

  return parts.length > 0
    ? parts.join(" · ")
    : "Repo context surfaced without compact details";
}

function normalizeCodePatchPlanFromSendPayload(
  payload: unknown
): UiCodePatchPlanSummary | null {
  const data = getEnvelopeData<Record<string, unknown>>(payload);
  const rawCodePatchPlan = data?.code_patch_plan;

  if (
    !rawCodePatchPlan ||
    typeof rawCodePatchPlan !== "object" ||
    Array.isArray(rawCodePatchPlan)
  ) {
    return null;
  }

  const record = rawCodePatchPlan as CodePatchPlanSummaryData;
  const used = safeBoolean(record.used);
  const status = safeString(record.status);
  const toolKind = safeString(record.tool_kind);
  const summary = safeString(record.summary);
  const filesToTouch = safeStringArray(record.files_to_touch);

  if (
    used === null &&
    !status &&
    !toolKind &&
    !summary &&
    filesToTouch.length === 0
  ) {
    return null;
  }

  return {
    used,
    status,
    toolKind,
    operation: safeString(record.operation),
    summary,
    repoKey: safeString(record.repo_key),
    repoRoot: safeString(record.repo_root),
    filesToTouch,
    patchPlan: safeStringArray(record.patch_plan),
    testsToRun: safeStringArray(record.tests_to_run),
    riskNotes: safeStringArray(record.risk_notes),
    rollbackNotes: safeStringArray(record.rollback_notes),
    approvalNeeded: safeBoolean(record.approval_needed),
    approvalReason: safeString(record.approval_reason),
    canApplyPatch: safeBoolean(record.can_apply_patch),
    patchApplicationLive: safeBoolean(record.patch_application_live),
    shellExecutionUsed: safeBoolean(record.shell_execution_used),
    networkAccessUsed: safeBoolean(record.network_access_used),
    mutatedFiles: safeBoolean(record.mutated_files),
    externalWorkersUsed: safeBoolean(record.external_workers_used),
    warnings: safeStringArray(record.warnings),
    errors: safeStringArray(record.errors)
  };
}

function summarizeCodePatchPlan(
  codePatchPlan: UiCodePatchPlanSummary | null
): string {
  if (!codePatchPlan) {
    return "No code patch plan recorded in current room state";
  }

  if (codePatchPlan.used === false) {
    return "Code patch planning not used on latest response";
  }

  const parts = [
    codePatchPlan.status ? humanize(codePatchPlan.status) : null,
    codePatchPlan.filesToTouch.length > 0
      ? `${codePatchPlan.filesToTouch.length} files`
      : null,
    codePatchPlan.approvalNeeded === true ? "approval required" : null
  ].filter((part): part is string => Boolean(part));

  return parts.length > 0
    ? parts.join(" · ")
    : codePatchPlan.summary ?? "Code patch plan surfaced without compact details";
}

function normalizeArtifactsFromSendPayload(
  payload: unknown
): UiArtifactSummary[] {
  const data = getEnvelopeData<Record<string, unknown>>(payload);
  const rawArtifacts = data?.artifacts;

  if (!Array.isArray(rawArtifacts)) {
    return [];
  }

  return rawArtifacts
    .map((entry): UiArtifactSummary | null => {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
        return null;
      }

      const record = entry as ArtifactSummaryData;
      const artifactId = safeString(record.artifact_id);
      if (!artifactId) {
        return null;
      }

      return {
        artifactId,
        kind: safeString(record.kind),
        title:
          safeString(record.title) ??
          safeString(record.summary) ??
          artifactId,
        summary: safeString(record.summary),
        createdAtUtc: safeString(record.created_at_utc),
        locality: safeString(record.locality),
        memoryPosture: safeString(record.memory_posture),
        producerToolKind: safeString(record.producer_tool_kind),
        producerOperation: safeString(record.producer_operation),
        sourceFileId: safeString(record.source_file_id),
        sourceFileName: safeString(record.source_file_name),
        sourceFileKind: safeString(record.source_file_kind),
        rowCount: safeNumber(record.row_count),
        columnCount: safeNumber(record.column_count),
        plotKind: safeString(record.plot_kind),
        svgText: safeString(record.svg_text),
        svgMimeType: safeString(record.svg_mime_type),
        width: safeNumber(record.width),
        height: safeNumber(record.height),
        metric: safeString(record.metric),
        plottedColumns: safeStringArray(record.plotted_columns),
        modelId: safeString(record.model_id),
        mimeType: safeString(record.mime_type),
        outputSha256: safeString(record.output_sha256),
        outputBytes: safeNumber(record.output_bytes),
        syntheticMedia: safeBoolean(record.synthetic_media),
        warnings: safeStringArray(record.warnings),
        errors: safeStringArray(record.errors)
      };
    })
    .filter((entry): entry is UiArtifactSummary => Boolean(entry));
}

function summarizeArtifactOutput(
  artifacts: UiArtifactSummary[],
  dataExecution: UiDataExecutionSummary | null
): string {
  const latestArtifact = artifacts[0] ?? null;

  if (latestArtifact) {
    const parts = [
      latestArtifact.kind ? humanize(latestArtifact.kind) : "Artifact",
      latestArtifact.sourceFileName ?? latestArtifact.sourceFileId,
      latestArtifact.kind === "plot_image" && latestArtifact.metric
        ? `metric ${latestArtifact.metric}`
        : null,
      latestArtifact.rowCount !== null ? `${latestArtifact.rowCount} rows` : null,
      latestArtifact.columnCount !== null ? `${latestArtifact.columnCount} columns` : null
    ].filter((part): part is string => Boolean(part));

    return parts.length > 0
      ? parts.join(" · ")
      : "Artifact output surfaced without compact details";
  }

  if (dataExecution?.used === true && dataExecution.status === "completed") {
    return "Data execution completed; saved artifact summary has not surfaced yet";
  }

  return "No saved artifact output recorded in current room state";
}

function formatArtifactRowsAndColumns(
  artifact: UiArtifactSummary | null
): string {
  if (!artifact) {
    return "No artifact row/column summary surfaced";
  }

  const rows =
    artifact.rowCount !== null ? `${artifact.rowCount} rows` : "rows not surfaced";
  const columns =
    artifact.columnCount !== null
      ? `${artifact.columnCount} columns`
      : "columns not surfaced";

  return `${rows} · ${columns}`;
}


function artifactSummaryToBridgeData(
  artifact: UiArtifactSummary
): ArtifactSummaryData {
  return {
    artifact_id: artifact.artifactId,
    kind: artifact.kind,
    title: artifact.title,
    summary: artifact.summary,
    created_at_utc: artifact.createdAtUtc,
    locality: artifact.locality,
    memory_posture: artifact.memoryPosture,
    producer_tool_kind: artifact.producerToolKind,
    producer_operation: artifact.producerOperation,
    source_file_id: artifact.sourceFileId,
    source_file_name: artifact.sourceFileName,
    source_file_kind: artifact.sourceFileKind,
    row_count: artifact.rowCount,
    column_count: artifact.columnCount,
    plot_kind: artifact.plotKind,
    svg_text: artifact.svgText,
    svg_mime_type: artifact.svgMimeType,
    width: artifact.width,
    height: artifact.height,
    metric: artifact.metric,
    plotted_columns: artifact.plottedColumns,
    model_id: artifact.modelId,
    mime_type: artifact.mimeType,
    output_sha256: artifact.outputSha256,
    output_bytes: artifact.outputBytes,
    synthetic_media: artifact.syntheticMedia,
    warnings: artifact.warnings,
    errors: artifact.errors
  };
}

function repoContextSummaryToBridgeData(
  repoContext: UiRepoContextSummary
): RepoContextSummaryData {
  return {
    used: repoContext.used,
    status: repoContext.status,
    tool_kind: repoContext.toolKind,
    operation: repoContext.operation,
    repo_key: repoContext.repoKey,
    repo_label: repoContext.repoLabel,
    repo_root: repoContext.repoRoot,
    trust_zone: repoContext.trustZone,
    appears_git_repo: repoContext.appearsGitRepo,
    current_branch: repoContext.currentBranch,
    git_head_read: repoContext.gitHeadRead,
    changed_files_live: repoContext.changedFilesLive,
    changed_files_note: repoContext.changedFilesNote,
    important_top_level_files: repoContext.importantTopLevelFiles,
    top_level_directories: repoContext.topLevelDirectories,
    safe_tree_entries: repoContext.safeTreeEntries,
    language_hints: repoContext.languageHints,
    framework_hints: repoContext.frameworkHints,
    test_command_hints: repoContext.testCommandHints,
    read_only: repoContext.readOnly,
    approval_required: repoContext.approvalRequired,
    network_access_used: repoContext.networkAccessUsed,
    shell_used: repoContext.shellUsed,
    mutated_files: repoContext.mutatedFiles,
    warnings: repoContext.warnings,
    errors: repoContext.errors
  };
}

function codePatchPlanSummaryToBridgeData(
  codePatchPlan: UiCodePatchPlanSummary
): CodePatchPlanSummaryData {
  return {
    used: codePatchPlan.used,
    status: codePatchPlan.status,
    tool_kind: codePatchPlan.toolKind,
    operation: codePatchPlan.operation,
    summary: codePatchPlan.summary,
    repo_key: codePatchPlan.repoKey,
    repo_root: codePatchPlan.repoRoot,
    files_to_touch: codePatchPlan.filesToTouch,
    patch_plan: codePatchPlan.patchPlan,
    tests_to_run: codePatchPlan.testsToRun,
    risk_notes: codePatchPlan.riskNotes,
    rollback_notes: codePatchPlan.rollbackNotes,
    approval_needed: codePatchPlan.approvalNeeded,
    approval_reason: codePatchPlan.approvalReason,
    can_apply_patch: codePatchPlan.canApplyPatch,
    patch_application_live: codePatchPlan.patchApplicationLive,
    shell_execution_used: codePatchPlan.shellExecutionUsed,
    network_access_used: codePatchPlan.networkAccessUsed,
    mutated_files: codePatchPlan.mutatedFiles,
    external_workers_used: codePatchPlan.externalWorkersUsed,
    warnings: codePatchPlan.warnings,
    errors: codePatchPlan.errors
  };
}


function getThreadTruthSummary(
  thread: UiConversationThread | null,
  lastSendTruth: ResponseTruth | null
): string | null {
  if (lastSendTruth?.blocked) {
    return "The most recent request was blocked by governed runtime/invoker boundary rules. No side-effecting action was performed.";
  }

  if (lastSendTruth?.approvalNeeded === true) {
    return "The most recent request is awaiting approval before any side-effecting action. No action has been performed.";
  }

  if (lastSendTruth?.degraded) {
    return "The most recent request completed in a degraded path. The response is shown honestly below.";
  }

  if (thread?.capabilityState === "degraded") {
    return "This conversation is available, but the current thread surface indicates degraded capability truth.";
  }

  return null;
}

function getThreadNoticeTone(
  thread: UiConversationThread | null,
  lastSendTruth: ResponseTruth | null
): ThreadNoticeTone {
  if (lastSendTruth?.blocked) {
    return "blocked";
  }

  if (lastSendTruth?.approvalNeeded === true) {
    return "info";
  }

  if (lastSendTruth?.degraded || thread?.capabilityState === "degraded") {
    return "degraded";
  }

  return null;
}

function getSendDisabledReason(
  startupReady: boolean,
  sendState: SendState
): string | null {
  if (!startupReady) {
    return "Startup truth is not ready yet. Send remains gated until the local body is actually ready.";
  }

  if (sendState === "sending") {
    return "A request is already being carried through the local bridge.";
  }

  return null;
}

function buildInitialWorkingTrace(selectedMode: string): WorkingTraceState {
  return {
    phaseLabel: "Preparing governed request",
    phaseDetail:
      "Establishing the local governed path before live trace updates begin arriving from the bridge.",
    selectedMode,
    selectedRole: null,
    selectedRuntime: null,
    selectedModelRuntimeTag: null,
    localityState: "local",
    approvalState: null,
    usedFallback: null,
    steps: [
      "Preparing governed request.",
      "Starting live request trace polling.",
      "Waiting for bridge-visible phase updates."
    ]
  };
}

function buildTraceStepLabel(label: string | null, detail: string | null): string | null {
  const cleanLabel = safeString(label);
  const cleanDetail = safeString(detail);

  if (cleanLabel && cleanDetail) {
    return `${cleanLabel}. ${cleanDetail}`;
  }

  return cleanLabel ?? cleanDetail;
}

function isTerminalRequestTraceStatus(status: string | null): boolean {
  const normalized = safeString(status)?.toLowerCase();

  return (
    normalized === "completed" ||
    normalized === "blocked" ||
    normalized === "degraded" ||
    normalized === "error"
  );
}

function isFallbackStartupTrace(trace: RequestTraceData): boolean {
  const normalizedStatus = safeString(trace.request_status)?.toLowerCase();
  return normalizedStatus === "pending_startup" || normalizedStatus === "unknown";
}

function hasMeaningfulLiveTrace(trace: RequestTraceData): boolean {
  if (Array.isArray(trace.trace_entries) && trace.trace_entries.length > 0) {
    return true;
  }

  const normalizedStatus = safeString(trace.request_status)?.toLowerCase();
  if (
    normalizedStatus === "running" ||
    normalizedStatus === "completed" ||
    normalizedStatus === "blocked" ||
    normalizedStatus === "degraded" ||
    normalizedStatus === "error"
  ) {
    return true;
  }

  const currentPhase = safeString(trace.current_phase)?.toLowerCase();
  if (
    currentPhase &&
    currentPhase !== "waiting_for_trace_startup" &&
    currentPhase !== "unknown_request_id"
  ) {
    return true;
  }

  const currentPhaseLabel = safeString(trace.current_phase_label)?.toLowerCase();
  if (
    currentPhaseLabel &&
    currentPhaseLabel !== "waiting for trace startup" &&
    currentPhaseLabel !== "unknown request id"
  ) {
    return true;
  }

  return false;
}

function buildWorkingTraceFromRequestTrace(
  trace: RequestTraceData,
  fallbackMode: string
): WorkingTraceState {
  const snapshot = trace.snapshot ?? {};
  const traceEntries = Array.isArray(trace.trace_entries) ? trace.trace_entries : [];

  const steps = traceEntries
    .map((entry) => buildTraceStepLabel(entry.label ?? null, entry.detail ?? null))
    .filter((entry): entry is string => Boolean(entry))
    .slice(-MAX_TRACE_STEPS);

  if (steps.length === 0) {
    const fallbackStep = buildTraceStepLabel(
      trace.current_phase_label ?? null,
      trace.current_phase_detail ?? null
    );

    if (fallbackStep) {
      steps.push(fallbackStep);
    }
  }

  return {
    phaseLabel: safeString(trace.current_phase_label) ?? "Working governed request",
    phaseDetail: safeString(trace.current_phase_detail),
    selectedMode: safeString(snapshot.selected_mode) ?? fallbackMode,
    selectedRole: safeString(snapshot.selected_role),
    selectedRuntime: safeString(snapshot.selected_runtime),
    selectedModelRuntimeTag: safeString(snapshot.selected_model_runtime_tag),
    localityState: safeString(snapshot.locality_state),
    approvalState: safeString(snapshot.approval_state),
    usedFallback: safeBoolean(snapshot.used_fallback),
    steps
  };
}

function buildDeleteConfirmationMessage(displayTitle: string): string {
  return `Delete "${displayTitle}" permanently from the local conversation store?`;
}

function buildConversationShareText(thread: UiConversationThread): string {
  const lines: string[] = [];

  lines.push(thread.displayTitle || "Conversation");
  lines.push("");

  for (const message of thread.messages) {
    const roleLabel = message.role ? message.role.toUpperCase() : "UNKNOWN";
    const timestamp = formatTimestamp(message.createdAtUtc);
    lines.push(timestamp ? `${roleLabel} — ${timestamp}` : roleLabel);
    lines.push(message.content);
    lines.push("");
  }

  return lines.join("\n").trim();
}

export default function ConversationsPage({
  startupReady,
  onRightDrawerSectionsChange,
  onOpenProjects,
  initialConversationId = null
}: ConversationsPageProps) {
  const [conversationList, setConversationList] = useState<UiConversationSummary[]>([]);
  const [conversationListState, setConversationListState] = useState<LoadState>("idle");
  const [conversationListView, setConversationListView] =
    useState<ConversationListView>("active");
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [threadState, setThreadState] = useState<LoadState>("idle");
  const [activeThread, setActiveThread] = useState<UiConversationThread | null>(null);
  const [draftMessage, setDraftMessage] = useState("");
  const [filePathDraft, setFilePathDraft] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<UiAttachedFile[]>([]);
  const [fileAttachState, setFileAttachState] = useState<FileAttachState>("idle");
  const [fileBrowseState, setFileBrowseState] = useState<FileBrowseState>("idle");
  const [fileAttachError, setFileAttachError] = useState<string | null>(null);
  const [selectedMode, setSelectedMode] = useState<string>("default");
  const [requestedGear, setRequestedGear] = useState<string>("automatic");
  const [useUnlockedSealedMemoryOnce, setUseUnlockedSealedMemoryOnce] = useState(false);
  const [sendState, setSendState] = useState<SendState>("idle");
  const [listError, setListError] = useState<string | null>(null);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [roomError, setRoomError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [mutatingConversationId, setMutatingConversationId] = useState<string | null>(null);
  const [renameDialogConversationId, setRenameDialogConversationId] = useState<string | null>(null);
  const [moveDialogConversationId, setMoveDialogConversationId] = useState<string | null>(null);
  const [moveProjectOptions, setMoveProjectOptions] = useState<ProjectSummary[]>([]);
  const [moveProjectListState, setMoveProjectListState] =
    useState<LoadState>("idle");
  const [moveProjectListError, setMoveProjectListError] = useState<string | null>(null);
  const [moveDialogError, setMoveDialogError] = useState<string | null>(null);
  const [lastSendTruth, setLastSendTruth] = useState<ResponseTruth | null>(null);
  const [lastCognitionTruth, setLastCognitionTruth] = useState<Record<string, any> | null>(null);
  const [conversationMemory, setConversationMemory] = useState<MemoryItemSummary[]>([]);
  const [conversationMemoryState, setConversationMemoryState] =
    useState<LoadState>("idle");
  const [lastMathExecution, setLastMathExecution] =
    useState<UiMathExecutionSummary | null>(null);
  const [lastDataExecution, setLastDataExecution] =
    useState<UiDataExecutionSummary | null>(null);
  const [lastArtifacts, setLastArtifacts] = useState<UiArtifactSummary[]>([]);
  const [lastRepoContext, setLastRepoContext] =
    useState<UiRepoContextSummary | null>(null);
  const [lastCodePatchPlan, setLastCodePatchPlan] =
    useState<UiCodePatchPlanSummary | null>(null);
  const [stewardshipState, setStewardshipState] = useState<StewardshipState>(
    () => createInitialStewardshipState()
  );
  const [patchDiffDraft, setPatchDiffDraft] = useState("");
  const [patchSummaryDraft, setPatchSummaryDraft] = useState("");
  const [fileOperationKind, setFileOperationKind] =
    useState<StewardshipOperationKind>("edit");
  const [fileOperationDestinationDraft, setFileOperationDestinationDraft] =
    useState("");
  const [fileOperationTextDraft, setFileOperationTextDraft] = useState("");
  const [documentExportFormat, setDocumentExportFormat] =
    useState<"markdown" | "text">("markdown");
  const [documentExportTargetDraft, setDocumentExportTargetDraft] = useState("");
  const [documentEditOperationDraft, setDocumentEditOperationDraft] = useState("");
  const [documentEditParametersDraft, setDocumentEditParametersDraft] =
    useState("{}");
  const [dataExportFormat, setDataExportFormat] =
    useState<"markdown" | "json" | "csv" | "geojson">("markdown");
  const [dataExportTargetDraft, setDataExportTargetDraft] = useState("");
  const [dataMutationOperationDraft, setDataMutationOperationDraft] = useState("");
  const [dataMutationParametersDraft, setDataMutationParametersDraft] =
    useState("{}");
  const [visualExportFormat, setVisualExportFormat] =
    useState<"markdown" | "json" | "png" | "jpg" | "webp" | "tiff" | "svg">("markdown");
  const [visualExportTargetDraft, setVisualExportTargetDraft] = useState("");
  const [visualEditOperationDraft, setVisualEditOperationDraft] = useState("");
  const [visualEditParametersDraft, setVisualEditParametersDraft] =
    useState("{}");
  const [mediaWorkerTruth, setMediaWorkerTruth] = useState<MediaWorkerTruth | null>(null);
  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);
  const [ttsTextDraft, setTtsTextDraft] = useState("");
  const [ttsVoiceId, setTtsVoiceId] = useState("af_sarah");
  const [speechConsentConfirmed, setSpeechConsentConfirmed] = useState(false);
  const [videoForgePromptDraft, setVideoForgePromptDraft] = useState("");
  const [videoForgeLabAcknowledged, setVideoForgeLabAcknowledged] = useState(false);
  const [workingTrace, setWorkingTrace] = useState<WorkingTraceState | null>(null);
  const [isCompactLayout, setIsCompactLayout] = useState(false);

  const activeConversationIdRef = useRef<string | null>(null);
  const pageLayoutRef = useRef<HTMLDivElement | null>(null);
  const draftConversationOpenRef = useRef(false);
  const listLoadTokenRef = useRef(0);
  const threadLoadTokenRef = useRef(0);
  const moveProjectLoadTokenRef = useRef(0);
  const requestTracePollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeRequestTraceIdRef = useRef<string | null>(null);
  const requestTracePollInFlightRef = useRef(false);
  const requestTraceStartedAtRef = useRef<number | null>(null);
  const hasSeenLiveTraceRef = useRef(false);

  const stopRequestTracePolling = useCallback(() => {
    if (requestTracePollIntervalRef.current !== null) {
      clearInterval(requestTracePollIntervalRef.current);
      requestTracePollIntervalRef.current = null;
    }

    activeRequestTraceIdRef.current = null;
    requestTracePollInFlightRef.current = false;
    requestTraceStartedAtRef.current = null;
    hasSeenLiveTraceRef.current = false;
  }, []);

  const clearWorkingTrace = useCallback(() => {
    setWorkingTrace(null);
  }, []);

  const startRequestTracePolling = useCallback(
    (requestId: string, mode: string) => {
      stopRequestTracePolling();
      activeRequestTraceIdRef.current = requestId;
      requestTraceStartedAtRef.current = Date.now();
      hasSeenLiveTraceRef.current = false;
      setWorkingTrace(buildInitialWorkingTrace(mode));

      const pollOnce = async () => {
        if (requestTracePollInFlightRef.current) {
          return;
        }

        if (activeRequestTraceIdRef.current !== requestId) {
          return;
        }

        requestTracePollInFlightRef.current = true;

        try {
          const traceResult = await fetchRequestTrace(requestId);

          if (activeRequestTraceIdRef.current !== requestId) {
            return;
          }

          const traceData = getEnvelopeData<RequestTraceData>(traceResult.payload);
          if (!traceData) {
            return;
          }

          const meaningfulLiveTrace = hasMeaningfulLiveTrace(traceData);
          const fallbackStartupTrace = isFallbackStartupTrace(traceData);
          const startedAt = requestTraceStartedAtRef.current;
          const withinStartupGrace =
            startedAt !== null && Date.now() - startedAt < REQUEST_TRACE_STARTUP_GRACE_MS;

          if (meaningfulLiveTrace) {
            hasSeenLiveTraceRef.current = true;
            setWorkingTrace(buildWorkingTraceFromRequestTrace(traceData, mode));
          } else if (hasSeenLiveTraceRef.current && fallbackStartupTrace) {
            return;
          } else if (fallbackStartupTrace && withinStartupGrace) {
            return;
          } else {
            setWorkingTrace(buildWorkingTraceFromRequestTrace(traceData, mode));
          }

          if (isTerminalRequestTraceStatus(traceData.request_status ?? null)) {
            if (requestTracePollIntervalRef.current !== null) {
              clearInterval(requestTracePollIntervalRef.current);
              requestTracePollIntervalRef.current = null;
            }
          }
        } finally {
          requestTracePollInFlightRef.current = false;
        }
      };

      void pollOnce();

      requestTracePollIntervalRef.current = setInterval(() => {
        void pollOnce();
      }, REQUEST_TRACE_POLL_INTERVAL_MS);
    },
    [stopRequestTracePolling]
  );

  useEffect(() => {
    activeConversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  useEffect(() => {
    if (!startupReady || !activeConversationId) {
      setConversationMemory([]);
      setConversationMemoryState("idle");
      return;
    }

    let active = true;
    setConversationMemoryState("loading");

    void fetchMemoryItems({ conversationId: activeConversationId, limit: 100 }).then(
      (result) => {
        if (!active) return;
        if (!result.ok) {
          setConversationMemory([]);
          setConversationMemoryState("error");
          return;
        }
        setConversationMemory(result.payload.data?.items ?? []);
        setConversationMemoryState("ready");
      }
    );

    return () => {
      active = false;
    };
  }, [activeConversationId, startupReady]);

  useEffect(() => {
    return () => {
      stopRequestTracePolling();
    };
  }, [stopRequestTracePolling]);

  useEffect(() => {
    return () => {
      onRightDrawerSectionsChange(DEFAULT_RIGHT_DRAWER_SECTIONS);
    };
  }, [onRightDrawerSectionsChange]);

  useEffect(() => {
    if (!startupReady) return;
    let active = true;
    void Promise.all([fetchMediaWorkerTruth(), fetchTtsVoices()]).then(([truthResult, voiceResult]) => {
      if (!active) return;
      const truthData = getEnvelopeData<{ media_workers?: MediaWorkerTruth }>(truthResult.payload);
      const voiceData = getEnvelopeData<{ voices?: TtsVoice[] }>(voiceResult.payload);
      setMediaWorkerTruth(truthData?.media_workers ?? null);
      setTtsVoices(voiceData?.voices ?? []);
    });
    return () => {
      active = false;
    };
  }, [startupReady]);

  useEffect(() => {
    const operationId = stewardshipState.videoForgeJob?.operation_id;
    const status = stewardshipState.videoForgeJob?.status;
    if (!operationId || !["queued", "running", "cancel_requested"].includes(status ?? "")) {
      return;
    }
    let active = true;
    const poll = async () => {
      const result = await fetchVideoForgeJob(operationId);
      if (!active) return;
      const data = getEnvelopeData<{ videoforge_job?: VideoForgeJob }>(result.payload);
      const job = data?.videoforge_job;
      if (!job) return;
      setStewardshipState((current) => ({
        ...current,
        videoForgeJob: job,
        notice:
          job.status === "completed"
            ? "Lab-only synthetic video saved locally with provenance and compact trace truth."
            : job.status === "cancelled"
              ? "VideoForge job cancelled; no partial output was retained."
              : current.notice
      }));
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [stewardshipState.videoForgeJob?.operation_id, stewardshipState.videoForgeJob?.status]);


  useEffect(() => {
    const pageLayout = pageLayoutRef.current;
    if (!pageLayout) {
      return;
    }

    const updateLayoutMode = (width: number) => {
      setIsCompactLayout(width < CONVERSATIONS_COMPACT_LAYOUT_BREAKPOINT_PX);
    };

    updateLayoutMode(pageLayout.getBoundingClientRect().width);

    if (typeof ResizeObserver === "undefined") {
      const handleResize = () => {
        updateLayoutMode(pageLayout.getBoundingClientRect().width);
      };

      window.addEventListener("resize", handleResize);
      return () => {
        window.removeEventListener("resize", handleResize);
      };
    }

    const observer = new ResizeObserver((entries) => {
      const nextWidth =
        entries[0]?.contentRect.width ?? pageLayout.getBoundingClientRect().width;
      updateLayoutMode(nextWidth);
    });

    observer.observe(pageLayout);

    return () => {
      observer.disconnect();
    };
  }, []);

  const activeSummary = useMemo(
    () =>
      conversationList.find(
        (conversation) => conversation.conversationId === activeConversationId
      ) ?? null,
    [conversationList, activeConversationId]
  );

  const threadTruthSummary = useMemo(
    () => getThreadTruthSummary(activeThread, lastSendTruth),
    [activeThread, lastSendTruth]
  );

  const threadNoticeTone = useMemo(
    () => getThreadNoticeTone(activeThread, lastSendTruth),
    [activeThread, lastSendTruth]
  );

  const sendDisabledReason = useMemo(
    () => getSendDisabledReason(startupReady, sendState),
    [startupReady, sendState]
  );

  const activeDisplayMode = useMemo(
    () => safeString(workingTrace?.selectedMode) ?? selectedMode ?? "default",
    [selectedMode, workingTrace?.selectedMode]
  );

  const activeMathProfile = useMemo(
    () => getModeMathProfile(activeDisplayMode),
    [activeDisplayMode]
  );

  const readyAttachedContextFiles = useMemo(
    () => attachedFiles.filter((file) => isReadyAttachedContextFile(file)),
    [attachedFiles]
  );

  const readyTextContextFiles = useMemo(
    () => readyAttachedContextFiles.filter((file) => isTextContextAttachedFile(file)),
    [readyAttachedContextFiles]
  );

  const readyCsvDataFiles = useMemo(
    () => readyAttachedContextFiles.filter((file) => isCsvAttachedFile(file)),
    [readyAttachedContextFiles]
  );

  const renameDialogConversation = useMemo(
    () =>
      conversationList.find(
        (conversation) => conversation.conversationId === renameDialogConversationId
      ) ?? null,
    [conversationList, renameDialogConversationId]
  );

  const moveDialogConversation = useMemo(
    () =>
      conversationList.find(
        (conversation) => conversation.conversationId === moveDialogConversationId
      ) ?? null,
    [conversationList, moveDialogConversationId]
  );

  const loadConversationThread = useCallback(async (conversationId: string) => {
    const loadToken = ++threadLoadTokenRef.current;
    setThreadState("loading");
    setThreadError(null);

    const result = await fetchConversationThread(conversationId);

    if (loadToken !== threadLoadTokenRef.current) {
      return;
    }

    const data = getEnvelopeData<BackendConversationThreadData>(result.payload);
    const normalizedThread = data ? normalizeConversationThread(data) : null;

    if (
      !result.ok ||
      !normalizedThread ||
      normalizedThread.conversationId !== conversationId
    ) {
      setActiveThread(null);
      setThreadState("error");
      setThreadError("Conversation thread could not be loaded honestly.");
      return;
    }

    setActiveThread(normalizedThread);
    setSelectedMode(normalizedThread.currentMode ?? "default");
    setThreadState("ready");
  }, []);

  const loadConversationList = useCallback(
    async (preferredConversationId: string | null = null) => {
      const loadToken = ++listLoadTokenRef.current;
      setConversationListState("loading");
      setListError(null);
      setRoomError(null);

      const includeArchived = conversationListView === "archived";
      const result = await fetchConversationList({
        includeArchived
      });

      if (loadToken !== listLoadTokenRef.current) {
        return;
      }

      const data = getEnvelopeData<BackendConversationListData>(result.payload);

      const normalizedItems = Array.isArray(data?.conversations)
        ? data.conversations
            .map((summary) => normalizeConversationSummary(summary))
            .filter((summary): summary is UiConversationSummary => Boolean(summary))
        : [];

      const items = filterConversationListByView(
        normalizedItems,
        conversationListView
      );

      if (!result.ok || !data) {
        setConversationList([]);
        setConversationListState("error");
        setListError("Conversation list is not currently available.");
        activeConversationIdRef.current = null;
        setActiveConversationId(null);
        setActiveThread(null);
        setThreadState("idle");
        return;
      }

      setConversationList(items);
      setConversationListState("ready");

      if (
        draftConversationOpenRef.current &&
        preferredConversationId === null &&
        activeConversationIdRef.current === null
      ) {
        return;
      }

      const nextActiveId = chooseActiveConversationId(
        items,
        preferredConversationId,
        safeString(data.active_conversation_id),
        activeConversationIdRef.current
      );

      activeConversationIdRef.current = nextActiveId;
      setActiveConversationId(nextActiveId);

      if (nextActiveId) {
        draftConversationOpenRef.current = false;
        void loadConversationThread(nextActiveId);
      } else {
        setActiveThread(null);
        setThreadState("ready");
      }
    },
    [conversationListView, loadConversationThread]
  );

  useEffect(() => {
    void loadConversationList(initialConversationId);
  }, [initialConversationId, loadConversationList]);

  const getConversationThreadForAction = useCallback(
    async (conversationId: string): Promise<UiConversationThread | null> => {
      if (activeThread?.conversationId === conversationId) {
        return activeThread;
      }

      const result = await fetchConversationThread(conversationId);
      const data = getEnvelopeData<BackendConversationThreadData>(result.payload);
      if (!result.ok || !data) {
        return null;
      }

      return normalizeConversationThread(data);
    },
    [activeThread]
  );

  const handleSelectConversation = useCallback(
    (conversationId: string) => {
      stopRequestTracePolling();
      clearWorkingTrace();
      draftConversationOpenRef.current = false;
      setLastSendTruth(null);
      setLastMathExecution(null);
      setLastDataExecution(null);
      setLastArtifacts([]);
      setLastRepoContext(null);
      setLastCodePatchPlan(null);
      setSendError(null);
      setActionError(null);
      setActionNotice(null);
      setThreadError(null);
      setFilePathDraft("");
      setAttachedFiles([]);
      setFileAttachState("idle");
      setFileBrowseState("idle");
      setFileAttachError(null);
      setStewardshipState(createInitialStewardshipState());
      setPatchDiffDraft("");
      setPatchSummaryDraft("");
      setFileOperationTextDraft("");
      setFileOperationDestinationDraft("");
      activeConversationIdRef.current = conversationId;
      setActiveConversationId(conversationId);
      void loadConversationThread(conversationId);
    },
    [clearWorkingTrace, loadConversationThread, stopRequestTracePolling]
  );

  const handleStartNewConversation = useCallback(() => {
    stopRequestTracePolling();
    clearWorkingTrace();
    setConversationListView("active");
    draftConversationOpenRef.current = true;
    threadLoadTokenRef.current += 1;
    setLastSendTruth(null);
    setLastMathExecution(null);
    setLastDataExecution(null);
    setLastArtifacts([]);
    setLastRepoContext(null);
    setLastCodePatchPlan(null);
    setSendError(null);
    setActionError(null);
    setActionNotice(null);
    setThreadError(null);
    setRoomError(null);
    setFilePathDraft("");
    setAttachedFiles([]);
    setFileAttachState("idle");
    setFileBrowseState("idle");
    setFileAttachError(null);
    setStewardshipState(createInitialStewardshipState());
    setPatchDiffDraft("");
    setPatchSummaryDraft("");
    setFileOperationTextDraft("");
    setFileOperationDestinationDraft("");
    activeConversationIdRef.current = null;
    setActiveConversationId(null);
    setActiveThread({
      conversationId: null,
      title: "New conversation",
      displayTitle: "New conversation",
      preview: null,
      updatedAtUtc: null,
      messageCount: 0,
      currentMode: selectedMode,
      currentRole: null,
      capabilityState: "live",
      locality: "local",
      approvalState: "not_needed",
      projectId: null,
      archived: false,
      pinned: false,
      lastMessageRole: null,
      messages: []
    });
    setThreadState("ready");
  }, [clearWorkingTrace, selectedMode, stopRequestTracePolling]);

  const handleShareConversation = useCallback(
    async (conversationId: string) => {
      setActionError(null);
      setActionNotice(null);

      const thread = await getConversationThreadForAction(conversationId);
      if (!thread) {
        setActionError("Conversation could not be prepared for local sharing.");
        return;
      }

      const shareText = buildConversationShareText(thread);

      try {
        if (
          typeof navigator === "undefined" ||
          !navigator.clipboard ||
          typeof navigator.clipboard.writeText !== "function"
        ) {
          throw new Error("Clipboard access is not available in this environment.");
        }

        await navigator.clipboard.writeText(shareText);
        setActionNotice("Conversation copied to clipboard.");
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Conversation could not be copied.";
        setActionError(message);
      }
    },
    [getConversationThreadForAction]
  );

  const handleConversationMutation = useCallback(
    async (
      conversationId: string,
      patch: {
        title?: string | null;
        project_id?: string | null;
        pinned?: boolean | null;
        archived?: boolean | null;
      },
      options: {
        actionLabel: string;
        successMessage: string;
        failureFallback: string;
        onFailure?: (message: string) => void;
      }
    ): Promise<boolean> => {
      if (!conversationId || sendState === "sending") {
        return false;
      }

      setActionError(null);
      setActionNotice(null);
      setMutatingConversationId(conversationId);

      try {
        const result = await updateConversation(conversationId, patch);

        if (!result.ok) {
          const errorMessage = getEnvelopePrimaryError(
            result.payload,
            options.failureFallback
          );
          const contextualError = `${options.actionLabel} failed. ${errorMessage}`;

          setActionError(contextualError);
          options.onFailure?.(contextualError);
          logMutationDebug(`${options.actionLabel} mutation failed`, {
            conversationId,
            patch,
            payload: result.payload
          });

          void loadConversationList(activeConversationIdRef.current);
          return false;
        }

        await loadConversationList(conversationId);
        setActionNotice(options.successMessage);
        return true;
      } finally {
        setMutatingConversationId(null);
      }
    },
    [loadConversationList, sendState]
  );

  const handleRenameConversation = useCallback((conversationId: string) => {
    setActionError(null);
    setActionNotice(null);
    setRenameDialogConversationId(conversationId);
  }, []);

  const loadMoveProjectOptions = useCallback(async () => {
    const loadToken = ++moveProjectLoadTokenRef.current;
    setMoveProjectListState("loading");
    setMoveProjectListError(null);

    const result = await fetchProjectList();
    if (loadToken !== moveProjectLoadTokenRef.current) {
      return;
    }

    const data = getEnvelopeData<{ projects?: ProjectSummary[] }>(result.payload);
    if (!result.ok || !data || !Array.isArray(data.projects)) {
      setMoveProjectOptions([]);
      setMoveProjectListState("error");
      setMoveProjectListError(
        getEnvelopePrimaryError(
          result.payload,
          "Projects could not be loaded from the local bridge."
        )
      );
      return;
    }

    setMoveProjectOptions(
      data.projects.filter(
        (project) => typeof project.project_id === "string" && project.project_id.trim()
      )
    );
    setMoveProjectListState("ready");
  }, []);

  const handleMoveConversationToProject = useCallback(
    (conversationId: string) => {
      setActionError(null);
      setActionNotice(null);
      setMoveDialogError(null);
      setMoveDialogConversationId(conversationId);
      void loadMoveProjectOptions();
    },
    [loadMoveProjectOptions]
  );

  const handleRenameConversationSubmit = useCallback(
    async (nextTitle: string) => {
      const conversationId = renameDialogConversationId;
      if (!conversationId) {
        return;
      }

      const succeeded = await handleConversationMutation(
        conversationId,
        { title: nextTitle },
        {
          actionLabel: "Rename",
          successMessage: "Conversation renamed.",
          failureFallback: "Conversation could not be renamed."
        }
      );

      if (succeeded) {
        setRenameDialogConversationId(null);
      }
    },
    [handleConversationMutation, renameDialogConversationId]
  );

  const handleMoveConversationSubmit = useCallback(
    async (nextProjectId: string) => {
      const conversationId = moveDialogConversationId;
      if (!conversationId) {
        return;
      }

      setMoveDialogError(null);

      const succeeded = await handleConversationMutation(
        conversationId,
        { project_id: nextProjectId },
        {
          actionLabel: "Move to project",
          successMessage: "Conversation moved to project.",
          failureFallback: "Conversation could not be moved to a project.",
          onFailure: setMoveDialogError
        }
      );

      if (succeeded) {
        setMoveDialogConversationId(null);
      }
    },
    [handleConversationMutation, moveDialogConversationId]
  );

  const handleTogglePinnedConversation = useCallback(
    async (conversationId: string, nextPinned: boolean) => {
      await handleConversationMutation(
        conversationId,
        { pinned: nextPinned },
        {
          actionLabel: nextPinned ? "Pin chat" : "Unpin chat",
          successMessage: nextPinned
            ? "Conversation pinned."
            : "Conversation unpinned.",
          failureFallback: nextPinned
            ? "Conversation could not be pinned."
            : "Conversation could not be unpinned."
        }
      );
    },
    [handleConversationMutation]
  );

  const handleToggleArchivedConversation = useCallback(
    async (conversationId: string, nextArchived: boolean) => {
      await handleConversationMutation(
        conversationId,
        { archived: nextArchived },
        {
          actionLabel: nextArchived ? "Archive" : "Unarchive",
          successMessage: nextArchived
            ? "Conversation archived."
            : "Conversation restored from archive.",
          failureFallback: nextArchived
            ? "Conversation could not be archived."
            : "Conversation could not be restored from archive."
        }
      );
    },
    [handleConversationMutation]
  );

  const handleDeleteConversation = useCallback(
    async (conversationId: string) => {
      if (!conversationId || sendState === "sending") {
        return;
      }

      const conversation =
        conversationList.find((item) => item.conversationId === conversationId) ?? null;
      const displayTitle = conversation?.displayTitle ?? "this conversation";

      if (
        typeof window !== "undefined" &&
        !window.confirm(buildDeleteConfirmationMessage(displayTitle))
      ) {
        return;
      }

      setActionError(null);
      setActionNotice(null);
      setMutatingConversationId(conversationId);

      try {
        const result = await deleteConversation(conversationId);
        const payloadData = getEnvelopeData<{ deleted?: boolean }>(result.payload);

        if (!result.ok || payloadData?.deleted === false) {
          const errorMessage = getEnvelopePrimaryError(
            result.payload,
            "Conversation could not be deleted."
          );
          const contextualError = `Delete failed for "${displayTitle}". ${errorMessage}`;

          setActionError(contextualError);
          logMutationDebug("Delete conversation failed", {
            conversationId,
            displayTitle,
            payload: result.payload
          });

          void loadConversationList(activeConversationIdRef.current);
          return;
        }

        const deletingActiveConversation = activeConversationIdRef.current === conversationId;

        if (deletingActiveConversation) {
          stopRequestTracePolling();
          clearWorkingTrace();
          setLastSendTruth(null);
          setLastMathExecution(null);
          setLastDataExecution(null);
          setLastArtifacts([]);
      setLastRepoContext(null);
      setLastCodePatchPlan(null);
          setSendError(null);
          setThreadError(null);
          activeConversationIdRef.current = null;
          setActiveConversationId(null);
          setActiveThread(null);
          setThreadState("ready");
        }

        await loadConversationList(
          deletingActiveConversation ? null : activeConversationIdRef.current
        );
        setActionNotice("Conversation deleted.");
      } finally {
        setMutatingConversationId(null);
      }
    },
    [
      clearWorkingTrace,
      conversationList,
      loadConversationList,
      sendState,
      stopRequestTracePolling
    ]
  );

  const handleBrowseForFile = useCallback(async () => {
    if (sendState === "sending" || fileAttachState === "attaching") {
      setFileAttachState("error");
      setFileAttachError("Wait for the current send or file attach to finish before browsing.");
      return;
    }

    setFileBrowseState("browsing");
    setFileAttachError(null);

    try {
      const selectedPath = await openLocalAttachableFile();

      if (selectedPath) {
        setFilePathDraft(selectedPath);
        setFileAttachState("idle");
        setFileAttachError(null);
      }
    } catch (error) {
      setFileAttachState("error");
      setFileAttachError(
        error instanceof Error
          ? error.message
          : "Native file picker could not be opened."
      );
    } finally {
      setFileBrowseState("idle");
    }
  }, [fileAttachState, sendState]);

  const handleAttachFilePath = useCallback(async () => {
    const trimmedPath = filePathDraft.trim();

    if (!trimmedPath) {
      setFileAttachState("error");
      setFileAttachError("Enter a local TXT, Markdown, CSV, XLSX, JSON, saved HTML, PDF, or DOCX file path before attaching.");
      return;
    }

    if (sendState === "sending") {
      setFileAttachState("error");
      setFileAttachError("Wait for the current governed send to finish before attaching a file.");
      return;
    }

    setFileAttachState("attaching");
    setFileAttachError(null);
    setActionError(null);
    setActionNotice(null);

    const result = await attachFile({
      source_path: trimmedPath,
      conversation_id: activeConversationIdRef.current,
      project_id: activeThread?.projectId ?? activeSummary?.projectId ?? null
    });

    const data = getEnvelopeData<FileIngestResult>(result.payload);
    const normalizedFile = normalizeAttachedFile(data);

    if (!data || !normalizedFile) {
      setFileAttachState("error");
      setFileAttachError(
        getEnvelopePrimaryError(
          result.payload,
          "File attachment did not return usable file truth."
        )
      );
      return;
    }

    setAttachedFiles((items) => {
      const withoutExisting = items.filter(
        (item) => item.fileId !== normalizedFile.fileId
      );
      return [...withoutExisting, normalizedFile];
    });

    const blocked =
      normalizedFile.blocked === true ||
      normalizedFile.processingState === "blocked" ||
      result.payload.status === "blocked";
    const failed =
      normalizedFile.processingState === "failed" ||
      result.payload.status === "error";
    const ready =
      normalizedFile.ready === true ||
      normalizedFile.processingState === "ready";

    if (blocked || failed || !ready) {
      setFileAttachState("error");
      setFileAttachError(
        getEnvelopePrimaryError(
          result.payload,
          normalizedFile.errors[0] ??
            "File was attached with a non-ready state. See the file chip for truth."
        )
      );
      return;
    }

    setFilePathDraft("");
    setFileAttachState("idle");
    setFileAttachError(null);
    setActionNotice(
      "File attached locally. TXT/Markdown/JSON/saved HTML/PDF/DOCX can provide bounded text context when parser support is available; CSV/XLSX can provide bounded local data summary. It is not memory and is not shared outward by default."
    );
  }, [
    activeSummary?.projectId,
    activeThread?.projectId,
    filePathDraft,
    sendState
  ]);

  const handleRemoveAttachedFile = useCallback((fileId: string) => {
    setAttachedFiles((items) => items.filter((item) => item.fileId !== fileId));
    setFileAttachError(null);
    setFileAttachState((currentState) =>
      currentState === "error" ? "idle" : currentState
    );
  }, []);

  const prepareStewardshipAction = useCallback(
    (
      busyAction: StewardshipBusyAction
    ): { targetPath: string; workspaceRoot: string } | null => {
      const target = getStewardshipTarget(filePathDraft);
      if ("error" in target) {
        setStewardshipState((current) => ({
          ...current,
          busyAction: null,
          error: target.error,
          notice: null
        }));
        return null;
      }

      setStewardshipState((current) => ({
        ...current,
        busyAction,
        error: null,
        notice: null,
        targetPath: target.targetPath,
        workspaceRoot: target.workspaceRoot
      }));
      return target;
    },
    [filePathDraft]
  );

  const finishStewardshipAction = useCallback(
    (patch: Partial<StewardshipState>) => {
      setStewardshipState((current) => ({
        ...current,
        ...patch,
        busyAction: null
      }));
    },
    []
  );

  const issueStewardshipApproval = useCallback(async (input: {
    operationKind: string;
    operationSummary: string;
    workspaceRoot: string;
    exactFiles: string[];
    sourceHash?: string | null;
    planHash?: string | null;
    mutationClass: string;
    rollbackNote: string;
  }): Promise<{ approval_id: string; approval_token: string } | { error: string }> => {
    if (!input.planHash) {
      return { error: "The current backend plan does not include the exact plan hash required for approval." };
    }
    const result = await approveCodingOperation({
      operation_kind: input.operationKind,
      operation_summary: input.operationSummary,
      workspace_root: input.workspaceRoot,
      exact_files: input.exactFiles.filter(Boolean),
      source_hash: input.sourceHash,
      plan_hash: input.planHash,
      allowed_mutation_class: input.mutationClass,
      expires_in_seconds: 300,
      operator_approved: true,
      approval_phrase: "Approved in Elysia Desktop",
      rollback_note: input.rollbackNote
    });
    const data = getEnvelopeData<{ operation_approval?: CodingOperationApproval }>(result.payload);
    const approval = data?.operation_approval;
    if (!result.ok || approval?.status !== "approved" || !approval.approval_token) {
      return { error: getEnvelopePrimaryError(result.payload, `Operation approval was not issued (${approval?.status ?? "unknown"}).`) };
    }
    return { approval_id: approval.approval_id, approval_token: approval.approval_token };
  }, []);

  const handleInspectStewardshipFile = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_file");
    if (!target) return;

    const result = await inspectCodingFileType({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath
    });
    const data = getEnvelopeData<{ file_type_inspection?: CodingFileTypeInspection }>(
      result.payload
    );
    const inspection = data?.file_type_inspection ?? null;
    const sameDatabase = Boolean(inspection?.relative_path && inspection.relative_path === stewardshipState.databaseInspection?.relative_path);
    const sameBinary = Boolean(inspection?.relative_path && inspection.relative_path === stewardshipState.binaryInspection?.relative_path);
    const sameEngineering = Boolean(inspection?.relative_path && inspection.relative_path === stewardshipState.engineeringInspection?.relative_path);

    finishStewardshipAction({
      fileInspection: inspection,
      databaseInspection: sameDatabase ? stewardshipState.databaseInspection : null,
      databaseSchema: sameDatabase ? stewardshipState.databaseSchema : null,
      binaryInspection: sameBinary ? stewardshipState.binaryInspection : null,
      engineeringInspection: sameEngineering ? stewardshipState.engineeringInspection : null,
      engineeringPreviewPlan: sameEngineering ? stewardshipState.engineeringPreviewPlan : null,
      engineeringPreviewResult: sameEngineering ? stewardshipState.engineeringPreviewResult : null,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "File type inspection failed."),
      notice: inspection
        ? `Inspected ${inspection.descriptor?.label ?? getFileLabelFromPath(target.targetPath)}.`
        : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction, stewardshipState.binaryInspection, stewardshipState.databaseInspection, stewardshipState.databaseSchema, stewardshipState.engineeringInspection, stewardshipState.engineeringPreviewPlan, stewardshipState.engineeringPreviewResult]);

  const handleReadStewardshipPreview = useCallback(async () => {
    const target = prepareStewardshipAction("read_file");
    if (!target) return;

    const result = await readCodingFilePreview({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_preview",
      max_bytes: 24000,
      max_lines: 600
    });
    const data = getEnvelopeData<{ file_preview?: CodingFilePreview }>(
      result.payload
    );
    const preview = data?.file_preview ?? null;

    finishStewardshipAction({
      filePreview: preview,
      patchProposal: null,
      patchApplyResult: null,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Approved file preview failed."),
      notice:
        preview?.status === "completed"
          ? "Approved bounded file preview is available for this conversation."
          : preview?.blocked_reason ?? "File preview did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleProposeStewardshipPatch = useCallback(async () => {
    const target = prepareStewardshipAction("propose_patch");
    if (!target) return;

    const diff = patchDiffDraft.trim();
    if (!diff) {
      finishStewardshipAction({
        error:
          "Paste a unified diff or backend-produced patch preview before requesting a patch proposal.",
        notice: null
      });
      return;
    }

    const result = await proposeCodingPatch({
      workspace_root: target.workspaceRoot,
      target_files: [target.targetPath],
      approval_mode: "apply_with_approval",
      change_summary:
        patchSummaryDraft.trim() ||
        `Desktop-approved patch proposal for ${getFileLabelFromPath(target.targetPath)}`,
      proposed_diff: diff
    });
    const data = getEnvelopeData<{ patch_proposal?: CodingPatchProposal }>(
      result.payload
    );
    const proposal = data?.patch_proposal ?? null;

    finishStewardshipAction({
      patchProposal: proposal,
      patchApplyResult: null,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Patch proposal failed."),
      notice: proposal
        ? `Patch proposal ${proposal.status ?? "returned"}; apply remains approval-gated.`
        : null
    });
  }, [
    finishStewardshipAction,
    patchDiffDraft,
    patchSummaryDraft,
    prepareStewardshipAction
  ]);

  const handleApplyStewardshipPatch = useCallback(async () => {
    const target = prepareStewardshipAction("apply_patch");
    if (!target) return;

    const proposal = stewardshipState.patchProposal;
    const expectedContentHash =
      proposal?.expected_content_hash ?? stewardshipState.filePreview?.content_hash;
    const patchHash = proposal?.patch_hash;
    const diff = proposal?.diff_preview ?? patchDiffDraft.trim();

    if (!proposal || !expectedContentHash || !patchHash || !diff) {
      finishStewardshipAction({
        error:
          "Patch apply requires a current patch proposal, patch hash, expected content hash, and diff preview.",
        notice: null
      });
      return;
    }

    const exactApproval = await issueStewardshipApproval({
      operationKind: "patch_apply",
      operationSummary: `Apply patch ${patchHash} to ${target.targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath],
      sourceHash: expectedContentHash,
      planHash: patchHash,
      mutationClass: "text_patch",
      rollbackNote: "A pre-mutation backup and rollback receipt are required."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingPatch({
      workspace_root: target.workspaceRoot,
      target_file: target.targetPath,
      approval_mode: "apply_with_approval",
      proposed_diff: diff,
      expected_content_hash: expectedContentHash,
      patch_hash: patchHash,
      operator_approved: true,
      approval_phrase: "APPROVE LOCAL PATCH",
      ...exactApproval
    });
    const data = getEnvelopeData<{ patch_apply?: CodingPatchApplyResult }>(
      result.payload
    );
    const patchApply = data?.patch_apply ?? null;

    finishStewardshipAction({
      patchApplyResult: patchApply,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Approved patch apply failed."),
      notice: patchApply?.mutation_performed
        ? "Approved patch applied locally through the governed backend."
        : patchApply?.blocked_reason ?? "Patch apply did not mutate the file."
    });
  }, [
    finishStewardshipAction,
    patchDiffDraft,
    issueStewardshipApproval,
    prepareStewardshipAction,
    stewardshipState.filePreview?.content_hash,
    stewardshipState.patchProposal
  ]);

  const handlePlanFileOperation = useCallback(async () => {
    const target = prepareStewardshipAction("plan_file_operation");
    if (!target) return;

    const result = await planCodingFileOperation({
      workspace_root: target.workspaceRoot,
      target_path: target.targetPath,
      approval_mode: "apply_with_approval",
      operation_kind: fileOperationKind,
      destination_path: fileOperationDestinationDraft.trim() || null,
      content_hash: stewardshipState.filePreview?.content_hash ?? null,
      summary: `Desktop planned ${fileOperationKind} for ${getFileLabelFromPath(target.targetPath)}`,
      new_text: fileOperationTextDraft || null
    });
    const data = getEnvelopeData<{ file_operation_plan?: CodingFileOperationPlan }>(
      result.payload
    );
    const plan = data?.file_operation_plan ?? null;

    finishStewardshipAction({
      fileOperationPlan: plan,
      fileOperationResult: null,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "File operation plan failed."),
      notice: plan
        ? `File operation plan returned ${plan.status ?? "unknown"}; execution requires approval.`
        : null
    });
  }, [
    fileOperationDestinationDraft,
    fileOperationKind,
    fileOperationTextDraft,
    finishStewardshipAction,
    prepareStewardshipAction,
    stewardshipState.filePreview?.content_hash
  ]);

  const handleExecuteFileOperation = useCallback(async () => {
    const target = prepareStewardshipAction("execute_file_operation");
    if (!target) return;

    const plan = stewardshipState.fileOperationPlan;
    if (!plan?.plan_hash) {
      finishStewardshipAction({ error: "Approved file execution requires a current exact plan hash.", notice: null });
      return;
    }
    const destinationPath = fileOperationDestinationDraft.trim() || null;
    const exactApproval = await issueStewardshipApproval({
      operationKind: `file_operation:${fileOperationKind}`,
      operationSummary: `Execute approved ${fileOperationKind} for ${target.targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, fileOperationKind === "rename" || fileOperationKind === "move" ? destinationPath ?? "" : ""],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: `file_${fileOperationKind}`,
      rollbackNote: fileOperationKind === "create" ? "The exact new file can be removed to roll back." : "A pre-mutation backup and rollback receipt are required."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await executeApprovedCodingFileOperation({
      workspace_root: target.workspaceRoot,
      target_path: target.targetPath,
      approval_mode: "apply_with_approval",
      operation_kind: fileOperationKind,
      destination_path: destinationPath,
      content_hash: stewardshipState.filePreview?.content_hash ?? null,
      expected_content_hash: plan.source_hash ?? null,
      summary: `Desktop approved ${fileOperationKind} for ${getFileLabelFromPath(target.targetPath)}`,
      new_text: fileOperationTextDraft || null,
      operator_approved: true,
      approval_phrase: "APPROVE LOCAL FILE OPERATION",
      ...exactApproval
    });
    const data = getEnvelopeData<{ file_operation_result?: CodingFileOperationResult }>(
      result.payload
    );
    const operationResult = data?.file_operation_result ?? null;

    finishStewardshipAction({
      fileOperationResult: operationResult,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Approved file operation failed."),
      notice: operationResult?.mutation_performed
        ? "Approved file operation completed locally through the governed backend."
        : operationResult?.blocked_reason ?? "File operation did not mutate the file."
    });
  }, [
    fileOperationDestinationDraft,
    fileOperationKind,
    fileOperationTextDraft,
    finishStewardshipAction,
    issueStewardshipApproval,
    prepareStewardshipAction,
    stewardshipState.fileOperationPlan,
    stewardshipState.filePreview?.content_hash
  ]);

  const handleInspectStewardshipDocument = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_document");
    if (!target) return;

    const result = await inspectCodingDocument({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_document_inspect"
    });
    const data = getEnvelopeData<{ document?: CodingDocumentPreview }>(
      result.payload
    );
    const document = data?.document ?? null;

    finishStewardshipAction({
      documentInspection: document,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Document inspection failed."),
      notice: document
        ? `Document inspection returned ${document.status ?? "unknown"}.`
        : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleExtractStewardshipDocument = useCallback(async () => {
    const target = prepareStewardshipAction("extract_document");
    if (!target) return;

    const result = await extractCodingDocumentPreview({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_document_extract",
      max_chars: 14000,
      max_tables: 8,
      max_rows: 20
    });
    const data = getEnvelopeData<{ document?: CodingDocumentPreview }>(
      result.payload
    );
    const document = data?.document ?? null;

    finishStewardshipAction({
      documentPreview: document,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Document extraction failed."),
      notice:
        document?.status === "completed"
          ? "Approved bounded document preview is available for this conversation."
          : document?.blocked_reason ?? "Document extraction did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePlanDocumentExport = useCallback(async () => {
    const target = prepareStewardshipAction("plan_document_export");
    if (!target) return;

    const fallbackTarget =
      documentExportFormat === "markdown"
        ? `${target.targetPath}.md`
        : `${target.targetPath}.txt`;
    const result = await planCodingDocumentExport({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_document_export_plan",
      export_format: documentExportFormat,
      target_path: documentExportTargetDraft.trim() || fallbackTarget
    });
    const data = getEnvelopeData<{ document_export_plan?: CodingDocumentPlan }>(
      result.payload
    );
    const plan = data?.document_export_plan ?? null;

    finishStewardshipAction({
      documentExportPlan: plan,
      documentExportResult: null,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Document export plan failed."),
      notice: plan
        ? `Document export plan returned ${plan.status ?? "unknown"}; writing requires approval.`
        : null
    });
  }, [
    documentExportFormat,
    documentExportTargetDraft,
    finishStewardshipAction,
    prepareStewardshipAction
  ]);

  const handleApplyDocumentExport = useCallback(async () => {
    const target = prepareStewardshipAction("apply_document_export");
    if (!target) return;

    const plan = stewardshipState.documentExportPlan;
    const targetPath = documentExportTargetDraft.trim() || plan?.target_relative_path;
    if (!plan?.source_hash || !plan.plan_hash || !targetPath) {
      finishStewardshipAction({
        error: "Approved document export requires a current export plan and source hash.",
        notice: null
      });
      return;
    }

    const exactApproval = await issueStewardshipApproval({
      operationKind: "document_export",
      operationSummary: `Export ${target.targetPath} to ${targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, targetPath],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: "document_export",
      rollbackNote: "The source document remains unchanged; a new derived export is created."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingDocumentExport({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_document_export",
      export_format: documentExportFormat,
      target_path: targetPath,
      operator_approved: true,
      overwrite_existing: false,
      expected_source_hash: plan.source_hash,
      ...exactApproval
    });
    const data = getEnvelopeData<{ document_export_result?: CodingDocumentApplyResult }>(
      result.payload
    );
    const exportResult = data?.document_export_result ?? null;

    finishStewardshipAction({
      documentExportResult: exportResult,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Approved document export failed."),
      notice: exportResult?.mutation_performed
        ? "Approved document export wrote a local export artifact."
        : exportResult?.blocked_reason ?? "Document export did not write a file."
    });
  }, [
    documentExportFormat,
    documentExportTargetDraft,
    finishStewardshipAction,
    issueStewardshipApproval,
    prepareStewardshipAction,
    stewardshipState.documentExportPlan
  ]);

  const handlePlanDocumentEdit = useCallback(async () => {
    const target = prepareStewardshipAction("plan_document_edit");
    if (!target) return;

    let parameters: Record<string, unknown>;
    try {
      parameters = JSON.parse(documentEditParametersDraft) as Record<string, unknown>;
    } catch {
      finishStewardshipAction({
        error: "Document edit parameters must be valid JSON.",
        notice: null
      });
      return;
    }

    const operation = documentEditOperationDraft.trim();
    if (!operation) {
      finishStewardshipAction({
        error: "Choose or type a stable document edit operation first.",
        notice: null
      });
      return;
    }

    const result = await planCodingDocumentEdit({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_document_edit_plan",
      operation,
      parameters
    });
    const data = getEnvelopeData<{ document_edit_plan?: CodingDocumentPlan }>(
      result.payload
    );
    const plan = data?.document_edit_plan ?? null;

    finishStewardshipAction({
      documentEditPlan: plan,
      documentEditResult: null,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Document edit plan failed."),
      notice: plan
        ? `Document edit plan returned ${plan.status ?? "unknown"}; writing requires approval.`
        : null
    });
  }, [
    documentEditOperationDraft,
    documentEditParametersDraft,
    finishStewardshipAction,
    prepareStewardshipAction
  ]);

  const handleApplyDocumentEdit = useCallback(async () => {
    const target = prepareStewardshipAction("apply_document_edit");
    if (!target) return;

    let parameters: Record<string, unknown>;
    try {
      parameters = JSON.parse(documentEditParametersDraft) as Record<string, unknown>;
    } catch {
      finishStewardshipAction({
        error: "Document edit parameters must be valid JSON.",
        notice: null
      });
      return;
    }

    const plan = stewardshipState.documentEditPlan;
    const operation = documentEditOperationDraft.trim();
    if (!plan?.source_hash || !plan.plan_hash || !operation) {
      finishStewardshipAction({
        error: "Approved document edit requires a current edit plan and source hash.",
        notice: null
      });
      return;
    }

    const exactApproval = await issueStewardshipApproval({
      operationKind: "document_edit",
      operationSummary: `Apply ${operation} to ${target.targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, plan.target_relative_path && plan.target_relative_path !== plan.relative_path ? plan.target_relative_path : ""],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: "document_edit",
      rollbackNote: plan.target_relative_path && plan.target_relative_path !== plan.relative_path ? "A derived document is created." : "A pre-mutation backup and rollback receipt are required."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingDocumentEdit({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_document_edit",
      operation,
      parameters,
      operator_approved: true,
      expected_source_hash: plan.source_hash,
      ...exactApproval
    });
    const data = getEnvelopeData<{ document_edit_result?: CodingDocumentApplyResult }>(
      result.payload
    );
    const editResult = data?.document_edit_result ?? null;

    finishStewardshipAction({
      documentEditResult: editResult,
      error: result.ok
        ? null
        : getEnvelopePrimaryError(result.payload, "Approved document edit failed."),
      notice: editResult?.mutation_performed
        ? "Approved document edit completed locally through the governed backend."
        : editResult?.blocked_reason ?? "Document edit did not mutate the file."
    });
  }, [
    documentEditOperationDraft,
    documentEditParametersDraft,
    finishStewardshipAction,
    issueStewardshipApproval,
    prepareStewardshipAction,
    stewardshipState.documentEditPlan
  ]);

  const handleInspectData = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_data");
    if (!target) return;

    const result = await inspectCodingData({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_data_inspect"
    });
    const data = getEnvelopeData<{ data?: CodingDataPreview }>(result.payload);
    const preview = data?.data ?? null;

    finishStewardshipAction({
      dataInspection: preview,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Data inspection failed."),
      notice: preview ? `Data inspection returned ${preview.status ?? "unknown"}.` : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePreviewData = useCallback(async () => {
    const target = prepareStewardshipAction("preview_data");
    if (!target) return;

    const result = await previewCodingData({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_data_preview"
    });
    const data = getEnvelopeData<{ data?: CodingDataPreview }>(result.payload);
    const preview = data?.data ?? null;

    finishStewardshipAction({
      dataPreview: preview,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Data preview failed."),
      notice:
        preview?.status === "completed" || preview?.status === "reduced_dependency_missing"
          ? "Approved bounded data preview is available for this conversation."
          : preview?.blocked_reason ?? "Data preview did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePlanDataExport = useCallback(async () => {
    const target = prepareStewardshipAction("plan_data_export");
    if (!target) return;
    const suffix =
      dataExportFormat === "markdown"
        ? "md"
        : dataExportFormat === "json"
          ? "json"
          : dataExportFormat === "geojson"
            ? "geojson"
            : "csv";
    const fallbackTarget = `${getFileLabelFromPath(target.targetPath)}.data-export.${suffix}`;
    const result = await planCodingDataExport({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_data_export_plan",
      export_format: dataExportFormat,
      target_path: dataExportTargetDraft.trim() || fallbackTarget
    });
    const data = getEnvelopeData<{ data_export_plan?: CodingDataPlan }>(result.payload);
    const plan = data?.data_export_plan ?? null;
    finishStewardshipAction({
      dataExportPlan: plan,
      dataExportResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Data export plan failed."),
      notice: plan ? `Data export plan returned ${plan.status ?? "unknown"}; writing requires approval.` : null
    });
  }, [dataExportFormat, dataExportTargetDraft, finishStewardshipAction, prepareStewardshipAction]);

  const handleApplyDataExport = useCallback(async () => {
    const target = prepareStewardshipAction("apply_data_export");
    if (!target) return;
    const plan = stewardshipState.dataExportPlan;
    const targetPath = dataExportTargetDraft.trim() || plan?.target_relative_path;
    if (!plan?.source_hash || !plan.plan_hash || !targetPath) {
      finishStewardshipAction({ error: "Approved data export requires a current export plan and source hash.", notice: null });
      return;
    }
    const exactApproval = await issueStewardshipApproval({
      operationKind: "data_export",
      operationSummary: `Export ${target.targetPath} to ${targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, targetPath],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: "data_export",
      rollbackNote: "The source dataset remains unchanged; a bounded derived summary is created."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingDataExport({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_data_export",
      export_format: dataExportFormat,
      target_path: targetPath,
      operator_approved: true,
      expected_source_hash: plan.source_hash,
      ...exactApproval
    });
    const data = getEnvelopeData<{ data_export_result?: CodingDataApplyResult }>(result.payload);
    const exportResult = data?.data_export_result ?? null;
    finishStewardshipAction({
      dataExportResult: exportResult,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved data export failed."),
      notice: exportResult?.mutation_performed ? "Approved data export wrote a local derived summary." : exportResult?.blocked_reason ?? "Data export did not write."
    });
  }, [dataExportFormat, dataExportTargetDraft, finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.dataExportPlan]);

  const handlePlanDataMutation = useCallback(async () => {
    const target = prepareStewardshipAction("plan_data_mutation");
    if (!target) return;
    let parameters: Record<string, unknown>;
    try {
      parameters = JSON.parse(dataMutationParametersDraft) as Record<string, unknown>;
    } catch {
      finishStewardshipAction({ error: "Data mutation parameters must be valid JSON.", notice: null });
      return;
    }
    const operation = dataMutationOperationDraft.trim();
    if (!operation) {
      finishStewardshipAction({ error: "Choose or type a governed data operation first.", notice: null });
      return;
    }
    const result = await planCodingDataMutation({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_data_mutation_plan",
      operation,
      parameters
    });
    const data = getEnvelopeData<{ data_mutation_plan?: CodingDataPlan }>(result.payload);
    const plan = data?.data_mutation_plan ?? null;
    finishStewardshipAction({
      dataMutationPlan: plan,
      dataMutationResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Data mutation plan failed."),
      notice: plan ? `Data mutation plan returned ${plan.status ?? "unknown"}; applying requires approval.` : null
    });
  }, [dataMutationOperationDraft, dataMutationParametersDraft, finishStewardshipAction, prepareStewardshipAction]);

  const handleApplyDataMutation = useCallback(async () => {
    const target = prepareStewardshipAction("apply_data_mutation");
    if (!target) return;
    let parameters: Record<string, unknown>;
    try {
      parameters = JSON.parse(dataMutationParametersDraft) as Record<string, unknown>;
    } catch {
      finishStewardshipAction({ error: "Data mutation parameters must be valid JSON.", notice: null });
      return;
    }
    const plan = stewardshipState.dataMutationPlan;
    const operation = dataMutationOperationDraft.trim();
    if (!plan?.source_hash || !plan.plan_hash || !operation) {
      finishStewardshipAction({ error: "Approved data mutation requires a current plan and source hash.", notice: null });
      return;
    }
    const exactApproval = await issueStewardshipApproval({
      operationKind: "data_edit",
      operationSummary: `Apply ${operation} to ${target.targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, plan.target_relative_path ?? ""],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: "data_edit",
      rollbackNote: plan.target_relative_path ? "A derived dataset is created." : "An adapter-appropriate backup or transaction receipt is required."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingDataMutation({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_data_mutation",
      operation,
      parameters,
      operator_approved: true,
      expected_source_hash: plan.source_hash,
      ...exactApproval
    });
    const data = getEnvelopeData<{ data_mutation_result?: CodingDataApplyResult }>(result.payload);
    const mutationResult = data?.data_mutation_result ?? null;
    finishStewardshipAction({
      dataMutationResult: mutationResult,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved data mutation failed."),
      notice: mutationResult?.mutation_performed ? "Approved data mutation completed locally through the governed backend." : mutationResult?.blocked_reason ?? "Data mutation did not change the dataset."
    });
  }, [dataMutationOperationDraft, dataMutationParametersDraft, finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.dataMutationPlan]);

  const handleInspectVisual = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_visual");
    if (!target) return;
    const result = await inspectCodingVisual({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_inspect"
    });
    const data = getEnvelopeData<{ visual?: CodingVisualPreview }>(result.payload);
    const visual = data?.visual ?? null;
    finishStewardshipAction({
      visualInspection: visual,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Visual inspection failed."),
      notice: visual ? `Visual inspection returned ${visual.status ?? "unknown"}.` : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePreviewVisual = useCallback(async () => {
    const target = prepareStewardshipAction("preview_visual");
    if (!target) return;
    const result = await previewCodingVisual({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_preview"
    });
    const data = getEnvelopeData<{ visual?: CodingVisualPreview }>(result.payload);
    const visual = data?.visual ?? null;
    finishStewardshipAction({
      visualPreview: visual,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Visual preview failed."),
      notice:
        visual?.status === "completed"
          ? "Approved bounded visual preview is available for this conversation."
          : visual?.blocked_reason ?? "Visual preview did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleInspectMedia = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_media");
    if (!target) return;
    const result = await inspectCodingMedia({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_media_inspect"
    });
    const data = getEnvelopeData<{ media?: CodingMediaPreview }>(result.payload);
    const media = data?.media ?? null;
    finishStewardshipAction({
      mediaInspection: media,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Media inspection failed."),
      notice: media?.status === "completed"
        ? "Approved local media metadata is available; raw media was not added to context or audit."
        : media?.blocked_reason ?? "Media inspection did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleThumbnailMedia = useCallback(async () => {
    const target = prepareStewardshipAction("thumbnail_media");
    if (!target) return;
    const result = await thumbnailCodingMedia({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_media_thumbnail"
    });
    const data = getEnvelopeData<{ media?: CodingMediaPreview }>(result.payload);
    const media = data?.media ?? null;
    finishStewardshipAction({
      mediaThumbnail: media,
      mediaInspection: media,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Media thumbnail failed."),
      notice: media?.thumbnail_status === "completed"
        ? "Approved video thumbnail was derived locally with a fixed operation."
        : media?.blocked_reason ?? "A thumbnail is not available for this media file."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleInspectArchive = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_archive");
    if (!target) return;
    const result = await inspectCodingArchive({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      archive_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_operator_requested_archive_listing_and_risk_report"
    });
    const data = getEnvelopeData<{ archive?: ArchiveContainerPreview }>(result.payload);
    const archive = data?.archive ?? null;
    finishStewardshipAction({
      archiveInspection: archive,
      archiveExtractionPlan: null,
      archiveExtractionResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Archive inspection failed."),
      notice: archive?.status === "completed"
        ? `ArchiveForge listed ${archive.member_count} members without extracting or executing contents.`
        : archive?.blocked_reason ?? "Archive inspection did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePlanArchiveExtraction = useCallback(async (selectedIndexes: number[]) => {
    const target = prepareStewardshipAction("plan_archive_extraction");
    if (!target) return;
    const result = await planCodingArchiveExtraction({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      archive_path: target.targetPath,
      selected_member_indexes: selectedIndexes,
      approval_granted: true,
      approval_reason: "desktop_operator_requested_selected_sandbox_extraction_plan"
    });
    const data = getEnvelopeData<{ archive_extraction_plan?: ArchiveExtractionPlan }>(result.payload);
    const plan = data?.archive_extraction_plan ?? null;
    finishStewardshipAction({
      archiveExtractionPlan: plan,
      archiveExtractionResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Archive extraction planning failed."),
      notice: plan?.status === "planned"
        ? "Selected-file sandbox extraction plan is ready for fresh exact approval."
        : plan?.blocked_reason ?? "Archive extraction plan was blocked."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleApplyArchiveExtraction = useCallback(async () => {
    const target = prepareStewardshipAction("apply_archive_extraction");
    if (!target) return;
    const plan = stewardshipState.archiveExtractionPlan;
    if (!plan || plan.status !== "planned") {
      finishStewardshipAction({ error: "Plan selected sandbox extraction before approval.", notice: null });
      return;
    }
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `Extract exactly ${plan.selected_file_count} selected file(s) into disposable sandbox ${plan.sandbox_id}? Archive contents will not be opened, installed, executed, trusted, or moved into the project.`
      )
    ) {
      finishStewardshipAction({ error: null, notice: "Archive sandbox extraction cancelled before approval." });
      return;
    }
    const exactApproval = await issueStewardshipApproval({
      operationKind: "archive_extract",
      operationSummary: "Extract the exact selected archive members into the exact disposable sandbox",
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath],
      sourceHash: plan.archive_sha256,
      planHash: plan.plan_hash,
      mutationClass: "archive_sandbox_extract",
      rollbackNote: "Abort cleanup removes partial sandbox output; the source archive remains unchanged."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingArchiveExtraction({
      operation_id: plan.operation_id,
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      archive_path: target.targetPath,
      selected_member_indexes: plan.selected_member_indexes,
      sandbox_id: plan.sandbox_id,
      approval_granted: true,
      approval_reason: "desktop_operator_exact_approved_selected_sandbox_extraction",
      operator_approved: true,
      expected_archive_sha256: plan.archive_sha256,
      expected_manifest_digest: plan.manifest_digest,
      expected_plan_hash: plan.plan_hash,
      ...exactApproval
    });
    const data = getEnvelopeData<{ archive_extraction_result?: ArchiveExtractionResult }>(result.payload);
    const extraction = data?.archive_extraction_result ?? null;
    finishStewardshipAction({
      archiveExtractionResult: extraction,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved sandbox extraction failed."),
      notice: extraction?.status === "completed"
        ? `ArchiveForge wrote ${extraction.extracted_file_count} selected file(s) into the disposable sandbox only.`
        : extraction?.blocked_reason ?? "Sandbox extraction did not complete."
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.archiveExtractionPlan]);

  const handleInspectDatabase = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_database");
    if (!target) return;
    const result = await inspectCodingDatabase({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      database_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_operator_requested_database_static_metadata"
    });
    const data = getEnvelopeData<{ database?: DatabaseInspection }>(result.payload);
    const database = data?.database ?? null;
    finishStewardshipAction({
      databaseInspection: database,
      databaseSchema: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Database metadata inspection failed."),
      notice: database?.status === "completed"
        ? "DatabaseForge identified and hashed the selected database without reading rows."
        : database?.blocked_reason ?? "Database metadata inspection did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePreviewDatabaseSchema = useCallback(async () => {
    const target = prepareStewardshipAction("preview_database_schema");
    if (!target) return;
    const inspected = stewardshipState.databaseInspection;
    if (stewardshipState.targetPath !== target.targetPath) {
      finishStewardshipAction({ error: "The selected database changed. Identify this exact file again before schema approval." });
      return;
    }
    if (!inspected?.source_sha256 || !inspected.schema_preview_plan_hash) {
      finishStewardshipAction({ error: "Identify a recognized SQLite or DuckDB database before requesting schema preview." });
      return;
    }
    if (typeof window !== "undefined" && !window.confirm("Preview schema names and definitions from a private read-only snapshot? Schema can reveal sensitive facts. No rows or arbitrary SQL will be available.")) {
      finishStewardshipAction({ notice: "Database schema preview cancelled before exact approval." });
      return;
    }
    const approval = await issueStewardshipApproval({
      operationKind: "database_schema_preview",
      operationSummary: "Preview exact selected database schema from a private read-only snapshot",
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath],
      sourceHash: inspected.source_sha256,
      planHash: inspected.schema_preview_plan_hash,
      mutationClass: "database_schema_preview",
      rollbackNote: "No source mutation; the private snapshot is destroyed after fixed introspection."
    });
    if ("error" in approval) {
      finishStewardshipAction({ error: approval.error });
      return;
    }
    const result = await previewCodingDatabaseSchema({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      database_path: target.targetPath,
      operator_approved: true,
      expected_source_sha256: inspected.source_sha256,
      expected_plan_hash: inspected.schema_preview_plan_hash,
      ...approval
    });
    const data = getEnvelopeData<{ database_schema?: DatabaseSchemaPreview }>(result.payload);
    const schema = data?.database_schema ?? null;
    finishStewardshipAction({
      databaseSchema: schema,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Exact-approved database schema preview failed."),
      notice: schema?.status === "completed"
        ? `Schema artifact created from a private ${schema.snapshot_strategy ?? "read-only"} snapshot; no rows were returned.`
        : schema?.blocked_reason ?? "Database schema preview did not complete."
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.databaseInspection]);

  const handleInspectBinary = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_binary");
    if (!target) return;
    const result = await inspectCodingBinary({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      binary_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_operator_requested_binary_static_metadata"
    });
    const data = getEnvelopeData<{ binary?: BinaryInspection }>(result.payload);
    const binary = data?.binary ?? null;
    finishStewardshipAction({
      binaryInspection: binary,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Binary static inspection failed."),
      notice: binary?.status === "completed"
        ? "BinaryForge produced a static local report without executing, loading, importing, installing, linking, or mutating the file."
        : binary?.blocked_reason ?? "Binary static inspection did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleInspectEngineering = useCallback(async () => {
    const target = prepareStewardshipAction("inspect_engineering");
    if (!target) return;
    const result = await inspectCodingEngineering({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_operator_requested_bounded_engineering_inspection"
    });
    const data = getEnvelopeData<{ engineering?: EngineeringInspection }>(result.payload);
    const engineering = data?.engineering ?? null;
    finishStewardshipAction({
      engineeringInspection: engineering,
      engineeringPreviewPlan: null,
      engineeringPreviewResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "EngineeringForge inspection failed."),
      notice: engineering?.status === "completed"
        ? `${engineering.descriptor.forge} produced a local static report without mutating, executing, sending, actuating, or uploading anything.`
        : engineering?.blocked_reason ?? "Engineering inspection did not complete."
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePlanEngineeringPreview = useCallback(async () => {
    const target = prepareStewardshipAction("plan_engineering_preview");
    if (!target) return;
    if (stewardshipState.targetPath !== target.targetPath || stewardshipState.engineeringInspection?.source_sha256 == null) {
      finishStewardshipAction({ error: "The selected engineering file changed. Inspect this exact file before planning a preview." });
      return;
    }
    const result = await planCodingEngineeringPreview({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_operator_requested_local_engineering_preview_plan"
    });
    const data = getEnvelopeData<{ engineering_preview_plan?: EngineeringPreviewPlan }>(result.payload);
    const plan = data?.engineering_preview_plan ?? null;
    finishStewardshipAction({
      engineeringPreviewPlan: plan,
      engineeringPreviewResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Engineering preview planning failed."),
      notice: plan?.status === "planned" ? "A local-only engineering preview plan is ready for exact approval." : plan?.blocked_reason ?? null
    });
  }, [finishStewardshipAction, prepareStewardshipAction, stewardshipState.engineeringInspection, stewardshipState.targetPath]);

  const handleApplyEngineeringPreview = useCallback(async () => {
    const target = prepareStewardshipAction("apply_engineering_preview");
    if (!target) return;
    const plan = stewardshipState.engineeringPreviewPlan;
    if (!plan || plan.status !== "planned" || !plan.source_sha256 || !plan.plan_hash) {
      finishStewardshipAction({ error: "Plan a supported safe local engineering preview before approval." });
      return;
    }
    if (typeof window !== "undefined" && !window.confirm("Create a bounded local SVG projection for this exact engineering file? This does not simulate, repair, print, machine, send, actuate, certify, or mutate the source.")) {
      finishStewardshipAction({ notice: "Engineering preview cancelled before exact approval." });
      return;
    }
    const approval = await issueStewardshipApproval({
      operationKind: "engineering_preview",
      operationSummary: "Create the exact bounded local engineering SVG projection",
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath],
      sourceHash: plan.source_sha256,
      planHash: plan.plan_hash,
      mutationClass: "engineering_preview_artifact",
      rollbackNote: "Delete the private local artifact; the engineering source and project remain unchanged."
    });
    if ("error" in approval) {
      finishStewardshipAction({ error: approval.error });
      return;
    }
    const result = await applyApprovedCodingEngineeringPreview({
      operation_id: plan.operation_id,
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_operator_exact_approved_local_engineering_preview",
      operator_approved: true,
      expected_source_sha256: plan.source_sha256,
      expected_plan_hash: plan.plan_hash,
      ...approval
    });
    const data = getEnvelopeData<{ engineering_preview_result?: EngineeringPreviewResult }>(result.payload);
    const preview = data?.engineering_preview_result ?? null;
    finishStewardshipAction({
      engineeringPreviewResult: preview,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Exact-approved engineering preview failed."),
      notice: preview?.status === "completed"
        ? "Private local EngineeringForge preview and receipt created; source and project remain unchanged."
        : preview?.blocked_reason ?? "Engineering preview did not complete."
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.engineeringPreviewPlan]);

  const handlePlanTranscription = useCallback(async () => {
    const target = prepareStewardshipAction("plan_transcription");
    if (!target) return;
    if (!speechConsentConfirmed) {
      finishStewardshipAction({ error: "Confirm processing rights and consent before planning transcription." });
      return;
    }
    const result = await planSpeechTranscription({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      output_format: "txt",
      approval_granted: true,
      approval_reason: "desktop_operator_requested_local_transcription_plan",
      operator_has_processing_rights: true,
      contains_other_people: true,
      other_people_consent_confirmed: true,
      private_local_use: true,
      redact_sensitive_text: true
    });
    const data = getEnvelopeData<{ transcription_plan?: SpeechTranscriptionPlan }>(result.payload);
    const plan = data?.transcription_plan ?? null;
    finishStewardshipAction({
      transcriptionPlan: plan,
      transcriptionResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Transcription plan failed."),
      notice: plan?.status === "planned" ? "Local machine-transcript plan is ready for exact approval." : plan?.blocked_reason ?? null
    });
  }, [finishStewardshipAction, prepareStewardshipAction, speechConsentConfirmed]);

  const handleApplyTranscription = useCallback(async () => {
    const target = prepareStewardshipAction("apply_transcription");
    if (!target) return;
    const plan = stewardshipState.transcriptionPlan;
    if (!plan?.source_hash || !plan.plan_hash || !plan.target_relative_path || !plan.sidecar_relative_path) {
      finishStewardshipAction({ error: "Plan transcription before approving it." });
      return;
    }
    const approval = await issueStewardshipApproval({
      operationKind: "speech_transcription",
      operationSummary: `Create an approved local machine transcript for ${target.targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, plan.target_relative_path, plan.sidecar_relative_path],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: "artifact_generation",
      rollbackNote: "Delete the derived transcript and provenance sidecar if no longer wanted. The source media is not changed."
    });
    if ("error" in approval) {
      finishStewardshipAction({ error: approval.error });
      return;
    }
    const result = await applyApprovedSpeechTranscription({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      output_format: "txt",
      approval_granted: true,
      approval_reason: "desktop_operator_approved_local_transcription",
      operator_has_processing_rights: true,
      contains_other_people: true,
      other_people_consent_confirmed: true,
      private_local_use: true,
      redact_sensitive_text: true,
      expected_source_hash: plan.source_hash,
      expected_plan_hash: plan.plan_hash,
      ...approval
    });
    const data = getEnvelopeData<{ transcription_result?: SpeechTranscriptionResult }>(result.payload);
    const transcriptionResult = data?.transcription_result ?? null;
    finishStewardshipAction({
      transcriptionResult,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved transcription failed."),
      notice: transcriptionResult?.status === "completed"
        ? "Machine transcript saved locally as a governed artifact; raw text was not added to central trace."
        : transcriptionResult?.blocked_reason ?? null
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.transcriptionPlan]);

  const handlePlanTts = useCallback(async () => {
    const target = prepareStewardshipAction("plan_tts");
    if (!target) return;
    if (!ttsTextDraft.trim()) {
      finishStewardshipAction({ error: "Enter a short passage for the local synthetic reading voice." });
      return;
    }
    const result = await planSpeechTts({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      text: ttsTextDraft.trim(),
      voice_id: ttsVoiceId,
      speed: 1,
      approval_granted: true,
      approval_reason: "desktop_operator_requested_local_tts_plan",
      purpose_category: "private_reading"
    });
    const data = getEnvelopeData<{ tts_plan?: SpeechTtsPlan }>(result.payload);
    const plan = data?.tts_plan ?? null;
    finishStewardshipAction({
      ttsPlan: plan,
      ttsResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Reading-voice plan failed."),
      notice: plan?.status === "planned" ? "Synthetic reading-voice plan is ready for exact approval." : plan?.blocked_reason ?? null
    });
  }, [finishStewardshipAction, prepareStewardshipAction, ttsTextDraft, ttsVoiceId]);

  const handleApplyTts = useCallback(async () => {
    const target = prepareStewardshipAction("apply_tts");
    if (!target) return;
    const plan = stewardshipState.ttsPlan;
    const text = ttsTextDraft.trim();
    if (!plan?.text_hash || !plan.plan_hash || !plan.target_relative_path || !plan.sidecar_relative_path || !text) {
      finishStewardshipAction({ error: "Plan the current reading text before approving it." });
      return;
    }
    const approval = await issueStewardshipApproval({
      operationKind: "speech_tts",
      operationSummary: "Create one approved local synthetic reading-voice artifact",
      workspaceRoot: target.workspaceRoot,
      exactFiles: [plan.target_relative_path, plan.sidecar_relative_path],
      sourceHash: plan.text_hash,
      planHash: plan.plan_hash,
      mutationClass: "artifact_generation",
      rollbackNote: "Delete the derived WAV and provenance sidecar if no longer wanted."
    });
    if ("error" in approval) {
      finishStewardshipAction({ error: approval.error });
      return;
    }
    const result = await applyApprovedSpeechTts({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      text,
      voice_id: plan.voice_id,
      speed: plan.speed,
      approval_granted: true,
      approval_reason: "desktop_operator_approved_local_tts",
      purpose_category: "private_reading",
      expected_text_hash: plan.text_hash,
      expected_plan_hash: plan.plan_hash,
      ...approval
    });
    const data = getEnvelopeData<{ tts_result?: SpeechTtsResult }>(result.payload);
    const ttsResult = data?.tts_result ?? null;
    finishStewardshipAction({
      ttsResult,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved reading voice failed."),
      notice: ttsResult?.status === "completed"
        ? "Synthetic reading voice saved locally with provenance and compact audit truth."
        : ttsResult?.blocked_reason ?? null
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.ttsPlan, ttsTextDraft]);

  const handlePlanVideoForge = useCallback(async () => {
    const target = prepareStewardshipAction("plan_videoforge");
    if (!target) return;
    const prompt = videoForgePromptDraft.trim();
    if (!prompt || !videoForgeLabAcknowledged) {
      finishStewardshipAction({ error: "Enter a bounded prompt and acknowledge the lab-only VideoForge gates." });
      return;
    }
    const result = await planVideoForge({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      prompt,
      purpose_category: "private_creative",
      approval_granted: true,
      approval_reason: "desktop_operator_requested_lab_videoforge_plan",
      lab_acknowledged: true,
      contains_real_person_request: false
    });
    const data = getEnvelopeData<{ videoforge_plan?: VideoForgePlan }>(result.payload);
    const plan = data?.videoforge_plan ?? null;
    finishStewardshipAction({
      videoForgePlan: plan,
      videoForgeJob: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "VideoForge plan failed."),
      notice: plan?.status === "planned" ? "Fixed low-resource Wan lab plan is ready for exact approval." : plan?.blocked_reason ?? null
    });
  }, [finishStewardshipAction, prepareStewardshipAction, videoForgeLabAcknowledged, videoForgePromptDraft]);

  const handleApplyVideoForge = useCallback(async () => {
    const target = prepareStewardshipAction("apply_videoforge");
    if (!target) return;
    const plan = stewardshipState.videoForgePlan;
    const prompt = videoForgePromptDraft.trim();
    if (!plan?.prompt_hash || !plan.plan_hash || !plan.target_relative_path || !plan.sidecar_relative_path || !prompt) {
      finishStewardshipAction({ error: "Plan the current VideoForge prompt before approving it." });
      return;
    }
    const approval = await issueStewardshipApproval({
      operationKind: "videoforge_generate",
      operationSummary: "Generate one fixed-profile local synthetic Wan lab video",
      workspaceRoot: target.workspaceRoot,
      exactFiles: [plan.target_relative_path, plan.sidecar_relative_path],
      sourceHash: plan.prompt_hash,
      planHash: plan.plan_hash,
      mutationClass: "artifact_generation",
      rollbackNote: "Delete the derived MP4 and provenance sidecar if no longer wanted."
    });
    if ("error" in approval) {
      finishStewardshipAction({ error: approval.error });
      return;
    }
    const result = await applyApprovedVideoForge({
      session_id: activeConversationIdRef.current,
      workspace_root: target.workspaceRoot,
      prompt,
      purpose_category: "private_creative",
      approval_granted: true,
      approval_reason: "desktop_operator_approved_lab_videoforge",
      lab_acknowledged: true,
      contains_real_person_request: false,
      expected_prompt_hash: plan.prompt_hash,
      expected_plan_hash: plan.plan_hash,
      ...approval
    });
    const data = getEnvelopeData<{ videoforge_job?: VideoForgeJob }>(result.payload);
    const job = data?.videoforge_job ?? null;
    finishStewardshipAction({
      videoForgeJob: job,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved VideoForge job failed to start."),
      notice: job?.status === "queued" || job?.status === "running"
        ? "Lab-only VideoForge job is running locally. This panel will track it."
        : job?.blocked_reason ?? null
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.videoForgePlan, videoForgePromptDraft]);

  const handleCancelVideoForge = useCallback(async () => {
    const operationId = stewardshipState.videoForgeJob?.operation_id;
    if (!operationId) return;
    setStewardshipState((current) => ({ ...current, busyAction: "cancel_videoforge", error: null }));
    const result = await cancelVideoForgeJob(operationId);
    const data = getEnvelopeData<{ videoforge_job?: VideoForgeJob }>(result.payload);
    const job = data?.videoforge_job ?? null;
    finishStewardshipAction({
      videoForgeJob: job,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "VideoForge cancellation failed."),
      notice: job ? `VideoForge cancellation state: ${humanize(job.status)}.` : null
    });
  }, [finishStewardshipAction, stewardshipState.videoForgeJob?.operation_id]);

  const handleVisualOcr = useCallback(async () => {
    const target = prepareStewardshipAction("ocr_visual");
    if (!target) return;
    const result = await runCodingVisualOcr({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_ocr",
      max_chars: 1200
    });
    const data = getEnvelopeData<{ ocr?: Record<string, unknown> }>(result.payload);
    const ocr = data?.ocr ?? null;
    finishStewardshipAction({
      visualOcr: ocr,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Visual OCR failed."),
      notice: ocr ? `Visual OCR returned ${safeString(ocr.status) ?? "unknown"}.` : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handleVisualAnalysis = useCallback(async () => {
    const target = prepareStewardshipAction("analyze_visual");
    if (!target) return;
    const result = await analyzeCodingVisual({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_analysis",
      include_semantic_provider: true
    });
    const data = getEnvelopeData<{ analysis?: Record<string, unknown> }>(result.payload);
    const analysis = data?.analysis ?? null;
    finishStewardshipAction({
      visualAnalysis: analysis,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Visual analysis failed."),
      notice: analysis ? `Visual analysis returned ${safeString(analysis.status) ?? "unknown"}.` : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction]);

  const handlePlanVisualExport = useCallback(async () => {
    const target = prepareStewardshipAction("plan_visual_export");
    if (!target) return;
    const suffix =
      visualExportFormat === "markdown"
        ? "md"
        : visualExportFormat === "json"
          ? "json"
          : visualExportFormat;
    const fallbackTarget = `${getFileLabelFromPath(target.targetPath)}.visual-export.${suffix}`;
    const result = await planCodingVisualExport({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_export_plan",
      export_format: visualExportFormat,
      target_path: visualExportTargetDraft.trim() || fallbackTarget
    });
    const data = getEnvelopeData<{ visual_export_plan?: CodingVisualPlan }>(result.payload);
    const plan = data?.visual_export_plan ?? null;
    finishStewardshipAction({
      visualExportPlan: plan,
      visualExportResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Visual export plan failed."),
      notice: plan ? `Visual export plan returned ${plan.status ?? "unknown"}; writing requires approval.` : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction, visualExportFormat, visualExportTargetDraft]);

  const handleApplyVisualExport = useCallback(async () => {
    const target = prepareStewardshipAction("apply_visual_export");
    if (!target) return;
    const plan = stewardshipState.visualExportPlan;
    const targetPath = visualExportTargetDraft.trim() || plan?.target_relative_path;
    if (!plan?.source_hash || !plan.plan_hash || !targetPath) {
      finishStewardshipAction({ error: "Approved visual export requires a current export plan and source hash.", notice: null });
      return;
    }
    const exactApproval = await issueStewardshipApproval({
      operationKind: "visual_export",
      operationSummary: `Export ${target.targetPath} to ${targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, targetPath],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: "visual_export",
      rollbackNote: "The source visual remains unchanged; a governed derived copy is created."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingVisualExport({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_export",
      export_format: visualExportFormat,
      target_path: targetPath,
      operator_approved: true,
      expected_source_hash: plan.source_hash,
      ...exactApproval
    });
    const data = getEnvelopeData<{ visual_export_result?: CodingVisualApplyResult }>(result.payload);
    const exportResult = data?.visual_export_result ?? null;
    finishStewardshipAction({
      visualExportResult: exportResult,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved visual export failed."),
      notice: exportResult?.mutation_performed ? "Approved visual export wrote a local derived file." : exportResult?.blocked_reason ?? "Visual export did not write."
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.visualExportPlan, visualExportFormat, visualExportTargetDraft]);

  const handlePlanVisualEdit = useCallback(async () => {
    const target = prepareStewardshipAction("plan_visual_edit");
    if (!target) return;
    let parameters: Record<string, unknown>;
    try {
      parameters = JSON.parse(visualEditParametersDraft) as Record<string, unknown>;
    } catch {
      finishStewardshipAction({ error: "Visual edit parameters must be valid JSON.", notice: null });
      return;
    }
    const operation = visualEditOperationDraft.trim();
    if (!operation) {
      finishStewardshipAction({ error: "Choose or type a governed visual operation first.", notice: null });
      return;
    }
    const result = await planCodingVisualEdit({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_edit_plan",
      operation,
      parameters
    });
    const data = getEnvelopeData<{ visual_edit_plan?: CodingVisualPlan }>(result.payload);
    const plan = data?.visual_edit_plan ?? null;
    finishStewardshipAction({
      visualEditPlan: plan,
      visualEditResult: null,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Visual edit plan failed."),
      notice: plan ? `Visual edit plan returned ${plan.status ?? "unknown"}; applying requires approval.` : null
    });
  }, [finishStewardshipAction, prepareStewardshipAction, visualEditOperationDraft, visualEditParametersDraft]);

  const handleApplyVisualEdit = useCallback(async () => {
    const target = prepareStewardshipAction("apply_visual_edit");
    if (!target) return;
    let parameters: Record<string, unknown>;
    try {
      parameters = JSON.parse(visualEditParametersDraft) as Record<string, unknown>;
    } catch {
      finishStewardshipAction({ error: "Visual edit parameters must be valid JSON.", notice: null });
      return;
    }
    const plan = stewardshipState.visualEditPlan;
    const operation = visualEditOperationDraft.trim();
    if (!plan?.source_hash || !plan.plan_hash || !operation) {
      finishStewardshipAction({ error: "Approved visual edit requires a current plan and source hash.", notice: null });
      return;
    }
    const exactApproval = await issueStewardshipApproval({
      operationKind: "visual_edit",
      operationSummary: `Apply ${operation} to ${target.targetPath}`,
      workspaceRoot: target.workspaceRoot,
      exactFiles: [target.targetPath, plan.target_relative_path ?? ""],
      sourceHash: plan.source_hash,
      planHash: plan.plan_hash,
      mutationClass: "visual_edit",
      rollbackNote: "The source visual remains unchanged; a privacy-preserving derived copy is created."
    });
    if ("error" in exactApproval) {
      finishStewardshipAction({ error: exactApproval.error, notice: null });
      return;
    }
    const result = await applyApprovedCodingVisualEdit({
      workspace_root: target.workspaceRoot,
      file_path: target.targetPath,
      approval_granted: true,
      approval_reason: "desktop_conversation_operator_approved_visual_edit",
      operation,
      parameters,
      operator_approved: true,
      expected_source_hash: plan.source_hash,
      ...exactApproval
    });
    const data = getEnvelopeData<{ visual_apply_result?: CodingVisualApplyResult }>(result.payload);
    const editResult = data?.visual_apply_result ?? null;
    finishStewardshipAction({
      visualEditResult: editResult,
      error: result.ok ? null : getEnvelopePrimaryError(result.payload, "Approved visual edit failed."),
      notice: editResult?.mutation_performed ? "Approved visual edit wrote a local derived copy." : editResult?.blocked_reason ?? "Visual edit did not write."
    });
  }, [finishStewardshipAction, issueStewardshipApproval, prepareStewardshipAction, stewardshipState.visualEditPlan, visualEditOperationDraft, visualEditParametersDraft]);

  const handleSend = useCallback(async () => {
    const trimmedMessage = draftMessage.trim();

    if (!trimmedMessage || sendState === "sending" || !startupReady) {
      return;
    }

    setSendState("sending");
    setSendError(null);
    setActionError(null);
    setActionNotice(null);
    setRoomError(null);

    const currentConversationId = activeConversationIdRef.current;
    const requestId = newRequestId();
    const attachedFileRequestContext = buildAttachedFileRequestContext(
      readyAttachedContextFiles
    );
    const stewardshipRequestContext = buildApprovedStewardshipRequestContext(
      stewardshipState.filePreview,
      stewardshipState.documentPreview,
      stewardshipState.dataPreview,
      stewardshipState.visualPreview,
      stewardshipState.mediaThumbnail ?? stewardshipState.mediaInspection
    );
    const modeMathRequestContext = buildModeMathRequestContext(selectedMode);
    const requestContext = mergeRequestContexts(
      modeMathRequestContext,
      attachedFileRequestContext,
      stewardshipRequestContext,
      useUnlockedSealedMemoryOnce
        ? { explicit_sealed_memory: true }
        : null
    );
    // This permission is deliberately one-shot. A later message requires a
    // fresh user action even while the sealed-vault TTL remains active.
    setUseUnlockedSealedMemoryOnce(false);

    setLastMathExecution(null);
    setLastDataExecution(null);
    setLastArtifacts([]);
    setLastRepoContext(null);
    setLastCodePatchPlan(null);
    startRequestTracePolling(requestId, selectedMode);

    const requestPayload: ChatSendRequest = {
      message: trimmedMessage,
      request_id: requestId,
      conversation_id: currentConversationId,
      project_id: activeThread?.projectId ?? activeSummary?.projectId ?? null,
      requested_mode: selectedMode,
      requested_gear: requestedGear,
      request_context: requestContext,
      ui_surface: "conversations_room"
    };

    let result = await sendChatMessage(requestPayload);
    const pendingResearch = result.payload.data?.research;
    const pendingApproval = pendingResearch && typeof pendingResearch === "object"
      ? (pendingResearch as Record<string, any>).approval
      : null;
    if (
      result.payload.status === "blocked" &&
      pendingApproval &&
      typeof pendingApproval === "object" &&
      pendingApproval.approval_id
    ) {
      const approval = pendingApproval as Record<string, any>;
      const preview = approval.preview && typeof approval.preview === "object"
        ? approval.preview as Record<string, any>
        : {};
      const approve = window.confirm(
        `Sensitive public research needs one exact, short-lived approval.\n\nDestination: ${String(approval.destination_class ?? "public search engines via local SearXNG")}\nCategories: ${Array.isArray(approval.data_categories) ? approval.data_categories.join(", ") : "classified sensitive query"}\nPreview: ${String(preview.query_preview ?? "sanitized query unavailable")}\n\nApprove this one query and continue the conversation?`
      );
      const resolution = await resolveResearchEgressApproval(
        String(approval.approval_id),
        approve,
        false
      );
      if (approve && resolution.ok) {
        const resolvedApproval = resolution.payload.data?.approval;
        const token = resolvedApproval && typeof resolvedApproval === "object"
          ? String((resolvedApproval as Record<string, any>).approval_token ?? "")
          : "";
        if (token) {
          const approvedRequestId = newRequestId();
          stopRequestTracePolling();
          clearWorkingTrace();
          startRequestTracePolling(approvedRequestId, selectedMode);
          result = await sendChatMessage({
            ...requestPayload,
            request_id: approvedRequestId,
            conversation_id: String(result.payload.data?.conversation_id ?? currentConversationId ?? "") || null,
            request_context: mergeRequestContexts(
              requestContext,
              {
                research_approval_id: String(approval.approval_id),
                research_approval_token: token
              }
            )
          });
        }
      }
    }
    const truth = normalizeSendTruth(result.payload);
    const mathExecution = normalizeMathExecutionFromSendPayload(result.payload);
    const dataExecution = normalizeDataExecutionFromSendPayload(result.payload);
    const artifacts = normalizeArtifactsFromSendPayload(result.payload);
    const repoContext = normalizeRepoContextFromSendPayload(result.payload);
    const codePatchPlan = normalizeCodePatchPlanFromSendPayload(result.payload);
    const returnedConversationId = extractConversationIdFromSendPayload(result.payload);
    setLastCognitionTruth({
      continuity: result.payload.data?.continuity ?? null,
      workspace: result.payload.data?.workspace ?? null,
      receipt: result.payload.data?.context_receipt ?? null,
      research: result.payload.data?.research ?? null
    });

    stopRequestTracePolling();
    clearWorkingTrace();
    setLastSendTruth(
      truth.blocked || truth.degraded || truth.approvalNeeded === true ? truth : null
    );
    setLastMathExecution(mathExecution);
    setLastDataExecution(dataExecution);
    setLastArtifacts(artifacts);
    setLastRepoContext(repoContext);
    setLastCodePatchPlan(codePatchPlan);

    if (!result.ok) {
      setSendState("error");
      setSendError(truth.errors[0] ?? "Message send failed.");
      return;
    }

    if (!truth.blocked) {
      setDraftMessage("");
    }

    if (returnedConversationId) {
      draftConversationOpenRef.current = false;
      activeConversationIdRef.current = returnedConversationId;
      setActiveConversationId(returnedConversationId);
      await loadConversationList(returnedConversationId);
    } else if (currentConversationId) {
      await loadConversationThread(currentConversationId);
    } else if (!truth.blocked) {
      setSendState("error");
      setSendError(
        "The bridge completed the response, but no conversation ID was returned for the new thread."
      );
      return;
    }

    if (truth.errors.length > 0 && !truth.blocked) {
      setSendError(truth.errors[0]);
      setSendState("error");
      return;
    }

    setSendState("idle");
  }, [
    clearWorkingTrace,
    activeSummary?.projectId,
    activeThread?.projectId,
    draftMessage,
    loadConversationList,
    loadConversationThread,
    readyAttachedContextFiles,
    selectedMode,
    requestedGear,
    sendState,
    startupReady,
    startRequestTracePolling,
    stewardshipState.documentPreview,
    stewardshipState.dataPreview,
    stewardshipState.filePreview,
    stewardshipState.mediaInspection,
    stewardshipState.mediaThumbnail,
    stewardshipState.visualPreview,
    stopRequestTracePolling,
    useUnlockedSealedMemoryOnce
  ]);

  const handleCancelActiveRequest = useCallback(async () => {
    const requestId = activeRequestTraceIdRef.current;
    if (!requestId || sendState !== "sending") return;
    const result = await cancelCognitionRequest(requestId);
    const requested = result.payload.data?.cancel_requested === true;
    setActionNotice(
      requested
        ? "Cancellation requested. Elysia is closing the local model stream and will retain only a sanitized receipt."
        : "The request already finished or is no longer cancellable."
    );
  }, [sendState]);

  const latestAssistantMessage = useMemo(
    () => getLatestAssistantMessage(activeThread?.messages ?? []),
    [activeThread]
  );

  const rightDrawerSections = useMemo<DrawerSection[]>(() => {
    const modeLabel = activeDisplayMode;
    const conversationLabel =
      activeThread?.displayTitle ?? activeSummary?.displayTitle ?? "New conversation";
    const conversationLoaded = Boolean(
      activeThread?.conversationId ?? activeSummary?.conversationId
    );
    const projectId = activeThread?.projectId ?? activeSummary?.projectId ?? null;
    const projectName = projectId
      ? moveProjectOptions.find((project) => project.project_id === projectId)?.name?.trim() ??
        projectId
      : null;
    const localityState =
      lastSendTruth?.localityState ??
      activeThread?.locality ??
      activeSummary?.locality ??
      (startupReady ? "local" : "startup pending");
    const approvalState =
      lastSendTruth?.approvalState ??
      activeThread?.approvalState ??
      activeSummary?.approvalState ??
      null;
    const approvalNeeded =
      lastSendTruth?.approvalNeeded === true || approvalState === "needed";
    const boundaryState =
      lastSendTruth?.boundaryState ??
      (lastSendTruth?.blocked
        ? "blocked"
        : lastSendTruth?.degraded
          ? "degraded"
          : "clear");
    const latestTraceStep =
      workingTrace?.steps[workingTrace.steps.length - 1] ?? null;
    const traceLive = sendState === "sending" && Boolean(workingTrace);
    const cognitionReceipt = lastCognitionTruth?.receipt && typeof lastCognitionTruth.receipt === "object"
      ? lastCognitionTruth.receipt as Record<string, any>
      : null;
    const admittedSources = Array.isArray(cognitionReceipt?.admitted) ? cognitionReceipt.admitted : [];
    const excludedSources = Array.isArray(cognitionReceipt?.excluded) ? cognitionReceipt.excluded : [];
    const researchTruth = lastCognitionTruth?.research && typeof lastCognitionTruth.research === "object"
      ? lastCognitionTruth.research as Record<string, any>
      : null;
    const linkedForms = Array.from(
      new Set(
        conversationMemory
          .map((item) => item.form?.trim())
          .filter((item): item is string => Boolean(item))
      )
    );
    const linkedProspectiveCount = conversationMemory.filter(
      (item) => item.form === "prospective"
    ).length;
    const linkedCorrectiveCount = conversationMemory.filter(
      (item) => item.form === "corrective"
    ).length;
    const filesInUseState: DrawerSection["state"] =
      attachedFiles.length > 0
        ? readyAttachedContextFiles.length > 0
          ? "live"
          : "partial"
        : "planned";
    const filesInUseRows: DrawerSection["rows"] =
      attachedFiles.length > 0
        ? [
            {
              label: "Attachments",
              value: `${attachedFiles.length} attached`
            },
            {
              label: "Text context",
              value: formatAttachedFileNames(
                readyTextContextFiles,
                "No ready text-context file"
              )
            },
            {
              label: "Data inputs",
              value: formatAttachedFileNames(
                readyCsvDataFiles,
                "No ready CSV/XLSX data input"
              )
            },
            {
              label: "Memory",
              value: "Not memory; local user-selected inputs only"
            },
            {
              label: "Status",
              value:
                readyAttachedContextFiles.length > 0
                  ? "TXT/Markdown/JSON/saved HTML/PDF/DOCX may enter bounded text context when local parser support is available; CSV/XLSX waits for bounded data-summary requests"
                  : "Attached files visible, but not ready for send use"
            }
          ]
        : [
            { label: "Attachments", value: "No files attached" },
            { label: "Status", value: "Not yet live" }
          ];
    const stewardshipLive =
      stewardshipState.filePreview?.status === "completed" ||
      stewardshipState.documentPreview?.status === "completed" ||
      stewardshipState.dataPreview?.status === "completed" ||
      stewardshipState.dataPreview?.status === "reduced_dependency_missing" ||
      stewardshipState.visualPreview?.status === "completed" ||
      stewardshipState.mediaInspection?.status === "completed" ||
      stewardshipState.mediaThumbnail?.status === "completed" ||
      stewardshipState.archiveInspection?.status === "completed" ||
      stewardshipState.databaseInspection?.status === "completed" ||
      stewardshipState.databaseSchema?.status === "completed" ||
      stewardshipState.binaryInspection?.status === "completed";
    const stewardshipRows: DrawerSection["rows"] = [
      {
        label: "Selected file",
        value:
          stewardshipState.filePreview?.file_label ??
          stewardshipState.documentPreview?.file_label ??
          stewardshipState.dataPreview?.file_label ??
          stewardshipState.mediaThumbnail?.file_label ??
          stewardshipState.mediaInspection?.file_label ??
          stewardshipState.archiveInspection?.file_label ??
          stewardshipState.databaseSchema?.file_label ??
          stewardshipState.databaseInspection?.file_label ??
          stewardshipState.binaryInspection?.file_label ??
          stewardshipState.fileInspection?.relative_path ??
          "No approved stewardship preview"
      },
      {
        label: "File type",
        value:
          stewardshipState.filePreview?.file_type_label ??
          stewardshipState.fileInspection?.descriptor?.label ??
          stewardshipState.documentPreview?.descriptor?.label ??
          stewardshipState.dataPreview?.descriptor?.label ??
          stewardshipState.mediaThumbnail?.descriptor?.label ??
          stewardshipState.mediaInspection?.descriptor?.label ??
          stewardshipState.archiveInspection?.descriptor?.label ??
          stewardshipState.databaseInspection?.descriptor?.label ??
          stewardshipState.binaryInspection?.descriptor?.label ??
          "Not inspected"
      },
      {
        label: "Preview",
        value: stewardshipLive
          ? stewardshipState.databaseInspection || stewardshipState.databaseSchema || stewardshipState.binaryInspection
            ? "Static/schema truth is surfaced in its governed panel and private artifact; raw details do not enter chat context"
            : "Approved bounded preview may enter current conversation context"
          : "No approved preview in context"
      },
      {
        label: "Mutation",
        value:
          stewardshipState.patchApplyResult?.mutation_performed === true ||
          stewardshipState.fileOperationResult?.mutation_performed === true ||
          stewardshipState.documentExportResult?.mutation_performed === true ||
          stewardshipState.documentEditResult?.mutation_performed === true ||
          stewardshipState.dataExportResult?.mutation_performed === true ||
          stewardshipState.dataMutationResult?.mutation_performed === true
            ? "Approved local mutation recorded by backend result"
            : "No mutation recorded in current room state"
      },
      {
        label: "Boundary",
        value:
          "Local path-guarded adapters only; DatabaseForge is snapshot-first schema-only; BinaryForge is static-only; no database/binary execution, loading, SQL, mutation, install, patch, or trust"
      }
    ];

    const dataExecutionState: DrawerSection["state"] =
      lastDataExecution?.used === true
        ? lastDataExecution.status === "completed"
          ? "live"
          : "degraded"
        : readyCsvDataFiles.length > 0
          ? "partial"
          : "planned";
    const dataExecutionRows: DrawerSection["rows"] = [
      {
        label: "Execution",
        value: summarizeDataExecution(lastDataExecution)
      },
      {
        label: "Ready data input",
        value: formatAttachedFileNames(
          readyCsvDataFiles,
          "No ready CSV/XLSX data input"
        )
      },
      {
        label: "Boundary",
        value:
          "Bounded local CSV/XLSX table summary only; no arbitrary Python, web, shell, plotting, or file mutation"
      }
    ];


    const latestArtifact = lastArtifacts[0] ?? null;
    const artifactOutputState: DrawerSection["state"] =
      lastArtifacts.length > 0
        ? "live"
        : lastDataExecution?.used === true && lastDataExecution.status === "completed"
          ? "partial"
          : "planned";
    const artifactOutputRows: DrawerSection["rows"] = latestArtifact
      ? [
          {
            label: "Latest",
            value: summarizeArtifactOutput(lastArtifacts, lastDataExecution)
          },
          {
            label: "Source",
            value:
              latestArtifact.sourceFileName ??
              latestArtifact.sourceFileId ??
              "Source not surfaced"
          },
          {
            label: "Rows/columns",
            value: formatArtifactRowsAndColumns(latestArtifact)
          },
          {
            label: "Memory",
            value: latestArtifact.memoryPosture
              ? humanize(latestArtifact.memoryPosture)
              : "Not memory"
          },
          {
            label: "Locality",
            value: latestArtifact.locality
              ? humanize(latestArtifact.locality)
              : "Local"
          },
          {
            label: "Boundary",
            value:
              latestArtifact.kind === "plot_image"
                ? "Saved local plot preview only; not memory, not a notebook, not local-path fetching, and not source-file mutation"
                : "Saved local result summary only; not memory, not a notebook, and not source-file mutation"
          }
        ]
      : [
          {
            label: "Latest",
            value: summarizeArtifactOutput(lastArtifacts, lastDataExecution)
          },
          {
            label: "Status",
            value:
              lastDataExecution?.used === true && lastDataExecution.status === "completed"
                ? "Data summary completed; artifact summary not yet visible in this room state"
                : "No saved artifact output for current room state"
          },
          {
            label: "Boundary",
            value:
              "Artifact outputs are local generated receipts/results, not memory"
          }
        ];

    const coderModeActive = activeDisplayMode === "coder";
    const repoContextStatus = safeString(lastRepoContext?.status)?.toLowerCase() ?? null;
    const codePatchPlanStatus = safeString(lastCodePatchPlan?.status)?.toLowerCase() ?? null;

    const repoContextState: DrawerSection["state"] =
      lastRepoContext?.used === true
        ? repoContextStatus === "completed"
          ? "live"
          : repoContextStatus === "blocked"
            ? "blocked"
            : "degraded"
        : coderModeActive
          ? "partial"
          : "planned";

    const repoContextRows: DrawerSection["rows"] = [
      {
        label: "Status",
        value: summarizeRepoContext(lastRepoContext)
      },
      {
        label: "Repo",
        value:
          lastRepoContext?.repoLabel ??
          lastRepoContext?.repoKey ??
          "No approved repo context surfaced"
      },
      {
        label: "Branch",
        value: lastRepoContext?.currentBranch ?? "Branch not surfaced"
      },
      {
        label: "Languages",
        value: formatCompactList(
          lastRepoContext?.languageHints ?? [],
          "Language hints not surfaced"
        )
      },
      {
        label: "Frameworks",
        value: formatCompactList(
          lastRepoContext?.frameworkHints ?? [],
          "Framework hints not surfaced"
        )
      },
      {
        label: "Safe tree",
        value:
          lastRepoContext?.safeTreeEntries.length
            ? `${lastRepoContext.safeTreeEntries.length} entries · ${formatCompactList(
                lastRepoContext.safeTreeEntries,
                "Safe tree not surfaced",
                3
              )}`
            : "Safe tree not surfaced"
      },
      {
        label: "Tests",
        value: formatCompactList(
          lastRepoContext?.testCommandHints ?? [],
          "Test hints not surfaced",
          2
        )
      },
      {
        label: "Boundary",
        value:
          "Read-only approved repo context. No shell, network, git status/diff command, or file mutation."
      }
    ];

    const codePatchPlanState: DrawerSection["state"] =
      lastCodePatchPlan?.used === true
        ? codePatchPlanStatus === "completed"
          ? "live"
          : codePatchPlanStatus === "blocked"
            ? "blocked"
            : "degraded"
        : coderModeActive
          ? "partial"
          : "planned";

    const codePatchPlanRows: DrawerSection["rows"] = [
      {
        label: "Status",
        value: summarizeCodePatchPlan(lastCodePatchPlan)
      },
      {
        label: "Files",
        value: formatCompactList(
          lastCodePatchPlan?.filesToTouch ?? [],
          "No explicit files surfaced"
        )
      },
      {
        label: "Tests",
        value: formatCompactList(
          lastCodePatchPlan?.testsToRun ?? [],
          "No test commands surfaced",
          2
        )
      },
      {
        label: "Approval",
        value:
          lastCodePatchPlan?.approvalNeeded === true
            ? lastCodePatchPlan.approvalReason ??
              "Approval required before any future patch application"
            : "No patch approval request surfaced"
      },
      {
        label: "Patch application",
        value:
          lastCodePatchPlan?.canApplyPatch === true ||
          lastCodePatchPlan?.patchApplicationLive === true
            ? "Unexpectedly marked live; verify governance before proceeding"
            : "Not live from this UI path"
      },
      {
        label: "Shell/workers",
        value:
          lastCodePatchPlan?.shellExecutionUsed === true ||
          lastCodePatchPlan?.externalWorkersUsed === true
            ? "Unexpected execution surfaced; verify governance"
            : "No shell, Aider, OpenHands, or external worker used"
      },
      {
        label: "Boundary",
        value:
          "Proposal-only patch plan. No files changed. Approval required before any future patch application."
      }
    ];

    const commandGateActive = coderModeActive || Boolean(lastCodePatchPlan);
    const commandGateRows: DrawerSection["rows"] = [
      {
        label: "Shell execution",
        value: "Blocked/not live"
      },
      {
        label: "Patch application",
        value: "Approval required/not live"
      },
      {
        label: "External workers",
        value: "Aider/OpenHands planned/not live"
      },
      {
        label: "Network",
        value: "Blocked unless a future governed tool path explicitly allows it"
      },
      {
        label: "File mutation",
        value: "Not live from this UI path"
      }
    ];

    const requestTraceState: DrawerSection["state"] = traceLive
      ? "live"
      : lastSendTruth?.blocked
        ? "blocked"
        : lastSendTruth?.degraded
          ? "degraded"
          : approvalNeeded
            ? "live"
            : "partial";

    const requestTraceRows: DrawerSection["rows"] = traceLive
      ? [
          {
            label: "Current trace",
            value: workingTrace?.phaseLabel ?? "Working governed request"
          },
          {
            label: "Detail",
            value: workingTrace?.phaseDetail ?? "Live request trace is active"
          },
          {
            label: "Status",
            value: "Live room trace active"
          }
        ]
      : lastSendTruth?.blocked
        ? [
            {
              label: "Current trace",
              value: "Most recent request blocked"
            },
            {
              label: "Detail",
              value: "Blocked by governed runtime/invoker boundary rules"
            },
            {
              label: "Status",
              value: "Terminal blocked trace"
            }
          ]
        : approvalNeeded
          ? [
              {
                label: "Current trace",
                value: "Most recent request awaiting approval"
              },
              {
                label: "Detail",
                value: "No side-effecting action has been completed"
              },
              {
                label: "Status",
                value: "Approval gate active"
              }
            ]
          : lastSendTruth?.degraded
            ? [
                {
                  label: "Current trace",
                  value: "Most recent request degraded"
                },
                {
                  label: "Detail",
                  value:
                    lastSendTruth.usedFallback === true
                      ? "Local fallback model was used"
                      : "Request completed through a degraded local path"
                },
                {
                  label: "Status",
                  value: "Completed through degraded local path"
                }
              ]
            : [
                {
                  label: "Current trace",
                  value: "No active trace"
                },
                {
                  label: "Detail",
                  value: "No live request trace running"
                },
                {
                  label: "Status",
                  value: "Idle summary only; richer trace surfacing is still maturing"
                }
              ];

    return [
      {
        key: "active_context",
        title: "Active Context",
        state: conversationLoaded ? "live" : "partial",
        accent: "warm",
        rows: [
          { label: "Mode", value: modeLabel },
          { label: "Mode profile", value: activeMathProfile.label },
          { label: "Conversation", value: conversationLabel },
          {
            label: "Context source",
            value: conversationLoaded
              ? "Active thread plus room continuity"
              : "Current room state only"
          }
        ]
      },
      {
        key: "memory_classes",
        title: "Memory Classes",
        state:
          conversationMemoryState === "ready"
            ? "live"
            : conversationMemoryState === "error"
              ? "degraded"
              : "partial",
        rows: [
          {
            label: "Working",
            value: traceLive ? "Active during current governed request" : "Idle"
          },
          {
            label: "Conversation",
            value: conversationLoaded ? "Loaded from active thread" : "No active thread loaded"
          },
          {
            label: "Canonical linked Memory",
            value:
              conversationMemoryState === "ready"
                ? `${conversationMemory.length} authorized record${conversationMemory.length === 1 ? "" : "s"}${
                    linkedForms.length ? ` · ${linkedForms.join(", ")}` : ""
                  }`
                : conversationMemoryState === "loading"
                  ? "Loading authorized conversation-linked Memory…"
                  : conversationMemoryState === "error"
                    ? "Conversation-linked Memory could not be loaded"
                    : "Select a persisted conversation to inspect linked Memory"
          },
          {
            label: "Prospective / corrective",
            value:
              conversationMemoryState === "ready"
                ? `${linkedProspectiveCount} prospective · ${linkedCorrectiveCount} corrective`
                : "No linked-memory count available"
          },
          {
            label: "Archive / deletion",
            value:
              "Conversation archival or deletion does not hard-delete linked canonical Memory; Memory stewardship separately governs archival, suppression, and approved purge"
          },
          {
            label: "Project",
            value: projectName ? `Linked to ${projectName}` : "No project memory linked"
          },
          {
            label: "Sealed private",
            value: useUnlockedSealedMemoryOnce
              ? "Explicit one-message use selected; vault must already be unlocked"
              : admittedSources.some((item) => item?.privacy === "sealed")
                ? "Used for the preceding local request only; not retained in the index"
                : "Not touched in current room state"
          },
          {
            label: "Restored sources",
            value: cognitionReceipt
              ? `${admittedSources.length} admitted · ${excludedSources.length} excluded`
              : "No completed cognition receipt yet"
          },
          {
            label: "Reasoning gear",
            value: String(cognitionReceipt?.reasoning_gear ?? "Not yet selected")
          },
          {
            label: "Autonomy",
            value: cognitionReceipt?.governor
              ? `Level ${String(cognitionReceipt.governor.effective_autonomy_level ?? "unknown")}`
              : "No completed Governor receipt yet"
          },
          {
            label: "Model / device",
            value: cognitionReceipt?.compute
              ? `${String(cognitionReceipt.governor?.model_role_hint ?? "local role")} · ${String(cognitionReceipt.compute.selected_device ?? "unknown")}`
              : "No completed compute receipt yet"
          },
          {
            label: "Research",
            value: researchTruth
              ? `${String(researchTruth.state ?? "unknown")} · ${String(researchTruth.evidence_ids?.length ?? 0)} evidence records`
              : "No governed research activity"
          }
        ]
      },
      {
        key: "current_project",
        title: "Current Project",
        state: "partial",
        rows: [
          {
            label: "Selection",
            value: projectName ?? "No current project selected"
          },
          {
            label: "Status",
            value: projectId
              ? "Conversation-linked project is visible"
              : "No project linkage visible"
          }
        ]
      },
      {
        key: "files_in_use",
        title: "Files in Use",
        state: filesInUseState,
        rows: filesInUseRows
      },
      {
        key: "file_document_stewardship",
        title: "File/Document Stewardship",
        state: stewardshipLive ? "live" : stewardshipState.error ? "blocked" : "partial",
        rows: stewardshipRows
      },
      {
        key: "plan_preview",
        title: "Plan Preview",
        state: traceLive ? "live" : "partial",
        rows: [
          {
            label: "Phase",
            value: workingTrace?.phaseLabel ?? "No active request in progress"
          },
          {
            label: "Detail",
            value:
              workingTrace?.phaseDetail ??
              latestAssistantMessage?.invocationStatus ??
              "Waiting for richer planner summary wiring"
          },
          {
            label: "Latest step",
            value: latestTraceStep ?? "No live trace step available"
          }
        ]
      },
      {
        key: "math_profile",
        title: "Mode Profile",
        state:
          lastMathExecution?.used === true
            ? lastMathExecution.status === "completed"
              ? "live"
              : "degraded"
            : "partial",
        rows: [
          { label: "Profile", value: activeMathProfile.label },
          { label: "Use", value: activeMathProfile.summary },
          { label: "Style", value: activeMathProfile.responseStyle },
          {
            label: "Execution",
            value: summarizeMathExecution(lastMathExecution)
          },
          {
            label: "Boundary",
            value: activeMathProfile.boundaryNote
          }
        ]
      },
      {
        key: "data_execution",
        title: "Data Execution",
        state: dataExecutionState,
        rows: dataExecutionRows
      },
      {
        key: "artifact_outputs",
        title: "Artifact Outputs",
        state: artifactOutputState,
        rows: artifactOutputRows
      },
      {
        key: "repo_context",
        title: "Repo Context",
        state: repoContextState,
        rows: repoContextRows
      },
      {
        key: "code_patch_plan",
        title: "Code Patch Plan",
        state: codePatchPlanState,
        rows: codePatchPlanRows
      },
      {
        key: "command_gate",
        title: "Command Gate",
        state: commandGateActive ? "blocked" : "inactive",
        rows: commandGateRows
      },
      {
        key: "boundary_flags",
        title: "Boundary Flags",
        state: lastSendTruth?.blocked
          ? "blocked"
          : lastSendTruth?.degraded
            ? "degraded"
            : "live",
        accent: "teal",
        rows: [
          { label: "Locality", value: localityState ?? "Unknown" },
          { label: "Boundary", value: boundaryState ?? "Clear" },
          {
            label: "Fallback",
            value:
              lastSendTruth?.usedFallback === true
                ? `Used${lastSendTruth.fallbackTo ? ` → ${lastSendTruth.fallbackTo}` : ""}`
                : "No fallback recorded"
          }
        ]
      },
      {
        key: "approval_needed",
        title: "Approval Needed",
        state: approvalNeeded ? "live" : "inactive",
        rows: [
          {
            label: "Current state",
            value: approvalNeeded
              ? "Approval required"
              : approvalState ?? "No approval required"
          },
          {
            label: "Blocked state",
            value: approvalNeeded
              ? "Awaiting approval before side-effecting action; no blocked path active"
              : "No approval gate active"
          }
        ]
      },
      {
        key: "journal_summary",
        title: "Journal Summary",
        state: "partial",
        rows: [
          {
            label: "Journaling",
            value: latestAssistantMessage ? "Most recent turn completed" : "Idle"
          },
          {
            label: "Idle state",
            value: latestAssistantMessage
              ? "Journal summary not yet surfaced into room state"
              : "No journal entry for current idle state"
          },
          {
            label: "Status",
            value: "Compact drawer summary still maturing"
          }
        ]
      },
      {
        key: "request_trace",
        title: "Request Trace",
        state: requestTraceState,
        rows: requestTraceRows
      }
    ];
  }, [
    activeDisplayMode,
    activeMathProfile,
    activeSummary,
    activeThread,
    attachedFiles,
    conversationMemory,
    conversationMemoryState,
    readyAttachedContextFiles,
    readyCsvDataFiles,
    readyTextContextFiles,
    lastArtifacts,
    lastCodePatchPlan,
    lastCognitionTruth,
    lastDataExecution,
    lastMathExecution,
    lastRepoContext,
    lastSendTruth,
    latestAssistantMessage,
    selectedMode,
    sendState,
    startupReady,
    stewardshipState,
    useUnlockedSealedMemoryOnce,
    moveProjectOptions,
    workingTrace
  ]);

  useEffect(() => {
    onRightDrawerSectionsChange(rightDrawerSections);
  }, [onRightDrawerSectionsChange, rightDrawerSections]);

  const composerSendDisabled = !startupReady;
  const readyAttachmentSummary = [
    readyTextContextFiles.length > 0
      ? `${readyTextContextFiles.length} text context file${readyTextContextFiles.length === 1 ? "" : "s"}`
      : null,
    readyCsvDataFiles.length > 0
      ? `${readyCsvDataFiles.length} data input${readyCsvDataFiles.length === 1 ? "" : "s"}`
      : null
  ].filter((item): item is string => Boolean(item)).join(", ");
  const composerStatusText =
    attachedFiles.length > 0
      ? readyAttachedContextFiles.length > 0
        ? `Ready attachments: ${readyAttachmentSummary}. They are not memory. ${activeMathProfile.label} is active.`
        : `Local file attachment is visible, but no attached file is ready for send use yet. ${activeMathProfile.label} is active.`
      : startupReady
        ? `Local body is ready. Send will use the governed chat path with ${activeMathProfile.label}.`
        : "Visible room, gated send. You can still write, but send waits for startup truth.";

  const repoContextCardData = lastRepoContext
    ? repoContextSummaryToBridgeData(lastRepoContext)
    : null;
  const codePatchPlanCardData = lastCodePatchPlan
    ? codePatchPlanSummaryToBridgeData(lastCodePatchPlan)
    : null;
  const showCoderTruthCards =
    activeDisplayMode === "coder" ||
    Boolean(repoContextCardData) ||
    Boolean(codePatchPlanCardData);
  const stewardshipBusy = Boolean(stewardshipState.busyAction);
  const stewardshipDescriptor =
    stewardshipState.filePreview
      ? {
          label:
            stewardshipState.filePreview.file_type_label ??
            stewardshipState.filePreview.file_type_id ??
            "Inspected file",
          category: stewardshipState.filePreview.category ?? null,
          adapter: stewardshipState.filePreview.adapter ?? null,
          capabilities: stewardshipState.filePreview.capabilities ?? {},
          riskFlags: stewardshipState.filePreview.risk_flags ?? {},
          notes: stewardshipState.filePreview.warnings ?? []
        }
      : stewardshipState.fileInspection?.descriptor
        ? {
            label: stewardshipState.fileInspection.descriptor.label ?? "Inspected file",
            category: stewardshipState.fileInspection.descriptor.category ?? null,
            adapter: stewardshipState.fileInspection.descriptor.adapter ?? null,
            capabilities: stewardshipState.fileInspection.descriptor.capabilities ?? {},
            riskFlags: stewardshipState.fileInspection.descriptor.risk_flags ?? {},
            notes: stewardshipState.fileInspection.descriptor.notes ?? []
          }
        : null;
  const documentDescriptor =
    stewardshipState.documentPreview?.descriptor ??
    stewardshipState.documentInspection?.descriptor ??
    null;
  const visualDescriptor =
    stewardshipState.visualPreview?.descriptor ??
    stewardshipState.visualInspection?.descriptor ??
    null;
  const mediaDescriptor =
    stewardshipState.mediaThumbnail?.descriptor ??
    stewardshipState.mediaInspection?.descriptor ??
    null;
  const stableDocumentOperations =
    documentDescriptor?.stable_edit_operations?.filter(Boolean) ?? [];
  const documentIsPdf = documentDescriptor?.type_id === "pdf_document";
  const isDocumentCandidate =
    stewardshipDescriptor?.category === "document" || Boolean(documentDescriptor);
  const isVisualCandidate =
    stewardshipDescriptor?.category === "visual" || Boolean(visualDescriptor);
  const isMediaCandidate =
    stewardshipDescriptor?.category === "media" || Boolean(mediaDescriptor);
  const isArchiveCandidate =
    stewardshipDescriptor?.category === "archive" || Boolean(stewardshipState.archiveInspection);
  const isDatabaseCandidate =
    stewardshipDescriptor?.category === "database" || Boolean(stewardshipState.databaseInspection);
  const isBinaryCandidate =
    stewardshipDescriptor?.category === "binary" || Boolean(stewardshipState.binaryInspection);
  const isEngineeringCandidate =
    stewardshipDescriptor?.category === "engineering" || Boolean(stewardshipState.engineeringInspection);
  const approvedPreviewInContext =
    stewardshipState.filePreview?.status === "completed" ||
    stewardshipState.documentPreview?.status === "completed" ||
    stewardshipState.dataPreview?.status === "completed" ||
    stewardshipState.dataPreview?.status === "reduced_dependency_missing" ||
    stewardshipState.visualPreview?.status === "completed" ||
    stewardshipState.mediaInspection?.status === "completed" ||
    stewardshipState.mediaThumbnail?.status === "completed";

  return (
    <div
      ref={pageLayoutRef}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        minHeight: 0,
        flex: 1,
        overflowX: "hidden",
        overflowY: isCompactLayout ? "auto" : "hidden",
        paddingRight: isCompactLayout ? "0.15rem" : undefined
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: isCompactLayout
            ? "minmax(0, 1fr)"
            : "minmax(0, 1fr) minmax(240px, 280px)",
          gap: "0.9rem",
          alignItems: "start",
          padding: "1rem 1.05rem",
          borderRadius: "22px",
          border: `1px solid ${palette.lineSilver}`,
          background:
            "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.92) 100%)",
          boxShadow:
            "inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 28px rgba(0,0,0,0.18)"
        }}
      >
        <div>
          <div
            style={{
              fontSize: "0.76rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: palette.sandstone,
              marginBottom: "0.35rem"
            }}
          >
            Conversations
          </div>
          <h1
            style={{
              margin: 0,
              fontSize: isCompactLayout ? "1.75rem" : "1.9rem",
              lineHeight: 1.08
            }}
          >
            Speak inside the first working room.
          </h1>
          <div
            style={{
              marginTop: "0.45rem",
              color: palette.silverMuted,
              lineHeight: 1.55,
              maxWidth: "72ch"
            }}
          >
            This room carries local conversation continuity, thread truth, governed send,
            and live request inspection without pretending to be a giant workbench.
          </div>
        </div>

        <div
          style={{
            padding: "0.85rem 0.95rem",
            borderRadius: "18px",
            border: `1px dashed ${startupReady ? "rgba(126, 215, 209, 0.26)" : palette.lineBronze}`,
            background: "rgba(11, 14, 18, 0.36)",
            color: palette.silverMuted,
            lineHeight: 1.55
          }}
        >
          {startupReady
            ? "Governed send is live. Local conversation continuity is available."
            : "Startup truth is not yet ready. The room is visible, but governed send remains gated until readiness is actually true."}
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: isCompactLayout
            ? "minmax(0, 1fr)"
            : "300px minmax(0, 1.6fr)",
          gap: "0.9rem",
          minHeight: 0,
          flex: 1,
          overflow: "hidden",
          alignItems: "stretch"
        }}
      >
        <aside
          style={{
            display: "grid",
            gridTemplateRows: "auto auto minmax(0, 1fr)",
            gap: "0.8rem",
            minHeight: 0,
            height: isCompactLayout ? "min(420px, 44vh)" : "100%",
            overflow: "hidden",
            padding: "0.9rem",
            borderRadius: "22px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.92) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 28px rgba(0,0,0,0.18)"
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "0.75rem",
              alignItems: "flex-start"
            }}
          >
            <div>
              <div
                style={{
                  fontSize: "0.76rem",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: palette.sandstone,
                  marginBottom: "0.35rem"
                }}
              >
                Conversations
              </div>
              <div style={{ color: palette.silverMuted, lineHeight: 1.55 }}>
                Local conversation continuity lives here now.
              </div>
            </div>

            <button
              type="button"
              onClick={handleStartNewConversation}
              style={{
                padding: "0.55rem 0.75rem",
                borderRadius: "12px",
                border: `1px solid ${palette.lineBronze}`,
                background:
                  "linear-gradient(180deg, rgba(43, 31, 21, 0.56) 0%, rgba(18, 25, 37, 0.72) 100%)",
                color: palette.silver,
                cursor: "pointer",
                fontSize: "0.82rem",
                whiteSpace: "nowrap"
              }}
            >
              New
            </button>
          </div>

          {actionError && (
            <div
              style={{
                padding: "0.85rem 0.9rem",
                borderRadius: "14px",
                border: `1px solid rgba(139, 78, 47, 0.32)`,
                background:
                  "linear-gradient(180deg, rgba(48, 23, 17, 0.44) 0%, rgba(18, 25, 37, 0.72) 100%)",
                color: palette.silverMuted,
                lineHeight: 1.55
              }}
            >
              {actionError}
            </div>
          )}

          {actionNotice && (
            <div
              style={{
                padding: "0.85rem 0.9rem",
                borderRadius: "14px",
                border: `1px solid rgba(47, 138, 104, 0.32)`,
                background:
                  "linear-gradient(180deg, rgba(24, 53, 43, 0.44) 0%, rgba(18, 25, 37, 0.72) 100%)",
                color: palette.silverMuted,
                lineHeight: 1.55
              }}
            >
              {actionNotice}
            </div>
          )}

          <div
            style={{
              display: "flex",
              gap: "0.5rem",
              flexWrap: "wrap"
            }}
          >
            {(["active", "archived"] as const).map((view) => {
              const selected = conversationListView === view;

              return (
                <button
                  key={view}
                  type="button"
                  onClick={() => {
                    setConversationListView(view);
                  }}
                  style={{
                    padding: "0.5rem 0.75rem",
                    borderRadius: "999px",
                    border: selected
                      ? `1px solid ${palette.lineTeal}`
                      : `1px solid ${palette.lineSilver}`,
                    background: selected
                      ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.76) 100%)"
                      : "linear-gradient(180deg, rgba(24, 33, 48, 0.54) 0%, rgba(18, 25, 37, 0.56) 100%)",
                    boxShadow: selected ? `0 0 18px ${palette.glowTeal}` : "none",
                    color: selected ? palette.teal : palette.silverMuted,
                    cursor: "pointer",
                    fontSize: "0.8rem",
                    letterSpacing: "0.05em",
                    textTransform: "uppercase"
                  }}
                >
                  {view === "active" ? "Active" : "Archived"}
                </button>
              );
            })}
          </div>

          <div
            style={{
              display: "grid",
              gap: "0.6rem",
              flex: 1,
              minHeight: 0,
              alignContent: "start",
              overflowY: "auto",
              overflowX: "hidden",
              scrollbarGutter: "stable",
              paddingRight: "0.35rem"
            }}
          >
            {conversationListState === "loading" && (
              <div
                style={{
                  padding: "1rem",
                  borderRadius: "16px",
                  border: `1px solid ${palette.lineSilver}`,
                  background: "rgba(11, 14, 18, 0.42)",
                  color: palette.silverMuted
                }}
              >
                Loading local conversation list…
              </div>
            )}

            {conversationListState === "error" && (
              <div
                style={{
                  padding: "1rem",
                  borderRadius: "16px",
                  border: `1px solid rgba(139, 78, 47, 0.32)`,
                  background:
                    "linear-gradient(180deg, rgba(48, 23, 17, 0.44) 0%, rgba(18, 25, 37, 0.72) 100%)",
                  color: palette.silverMuted,
                  lineHeight: 1.55
                }}
              >
                {listError ?? "Conversation list could not be loaded."}
              </div>
            )}

            {conversationListState === "ready" && conversationList.length === 0 && (
              <div
                style={{
                  padding: "1rem",
                  borderRadius: "16px",
                  border: `1px dashed ${palette.lineBronze}`,
                  background: "rgba(11, 14, 18, 0.42)",
                  color: palette.silverMuted,
                  lineHeight: 1.55
                }}
              >
                {getConversationListEmptyMessage(conversationListView)}
              </div>
            )}

            {conversationList.map((conversation) => {
              const selected = conversation.conversationId === activeConversationId;
              const mutatingThisConversation =
                mutatingConversationId === conversation.conversationId;

              return (
                <div
                  key={conversation.conversationId}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(0, 1fr) auto",
                    gap: "0.55rem",
                    alignItems: "stretch"
                  }}
                >
                  <button
                    type="button"
                    onClick={() => handleSelectConversation(conversation.conversationId)}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.45rem",
                      width: "100%",
                      padding: "0.9rem",
                      borderRadius: "16px",
                      border: selected
                        ? `1px solid ${palette.lineTeal}`
                        : `1px solid rgba(199, 210, 218, 0.08)`,
                      background: selected
                        ? "linear-gradient(180deg, rgba(16, 41, 43, 0.72) 0%, rgba(18, 25, 37, 0.76) 100%)"
                        : "linear-gradient(180deg, rgba(24, 33, 48, 0.54) 0%, rgba(18, 25, 37, 0.56) 100%)",
                      boxShadow: selected ? `0 0 20px ${palette.glowTeal}` : "none",
                      textAlign: "left",
                      cursor: "pointer",
                      minWidth: 0
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        gap: "0.45rem",
                        alignItems: "center"
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.45rem",
                          minWidth: 0
                        }}
                      >
                        <div
                          style={{
                            fontWeight: selected ? 700 : 600,
                            color: selected ? palette.teal : palette.silver,
                            minWidth: 0
                          }}
                        >
                          {conversation.displayTitle}
                        </div>

                        {conversation.pinned && (
                          <img
                            src={conversationPinImageUrl}
                            alt=""
                            aria-hidden="true"
                            style={{
                              width: "0.95rem",
                              height: "0.95rem",
                              objectFit: "contain",
                              flex: "0 0 auto",
                              filter:
                                "drop-shadow(0 0 6px rgba(184, 162, 123, 0.28))"
                            }}
                          />
                        )}
                      </div>

                    </div>

                    {conversation.preview && (
                      <div
                        className="elysia-preview-clamp"
                        style={{
                          color: palette.silverMuted,
                          lineHeight: 1.45,
                          fontSize: "0.9rem"
                        }}
                      >
                        {conversation.preview}
                      </div>
                    )}

                    <div
                      style={{
                        display: "flex",
                        gap: "0.65rem",
                        flexWrap: "wrap",
                        fontSize: "0.76rem",
                        color: palette.silverMuted
                      }}
                    >
                      {conversation.currentMode && (
                        <span
                          style={{
                            letterSpacing: "0.06em",
                            textTransform: "uppercase"
                          }}
                        >
                          {conversation.currentMode}
                        </span>
                      )}
                      <span>{conversation.messageCount} messages</span>
                      {conversation.pinned && <span>Pinned</span>}
                      {conversation.lastMessageRole && <span>{conversation.lastMessageRole}</span>}
                      {conversation.updatedAtUtc && (
                        <span>{formatTimestamp(conversation.updatedAtUtc)}</span>
                      )}
                    </div>
                  </button>

                  <ConversationActionsMenu
                    conversationId={conversation.conversationId}
                    conversationTitle={conversation.displayTitle}
                    pinned={conversation.pinned}
                    archived={conversation.archived}
                    disabled={mutatingThisConversation || sendState === "sending"}
                    onShare={(conversationId) => {
                      void handleShareConversation(conversationId);
                    }}
                    onRename={(conversationId) => {
                      handleRenameConversation(conversationId);
                    }}
                    onMoveToProject={(conversationId) => {
                      handleMoveConversationToProject(conversationId);
                    }}
                    onTogglePinned={(conversationId, nextPinned) => {
                      void handleTogglePinnedConversation(conversationId, nextPinned);
                    }}
                    onToggleArchived={(conversationId, nextArchived) => {
                      void handleToggleArchivedConversation(conversationId, nextArchived);
                    }}
                    onDelete={(conversationId) => {
                      void handleDeleteConversation(conversationId);
                    }}
                  />
                </div>
              );
            })}
          </div>
        </aside>

        <section
          style={{
            display: "grid",
            gridTemplateRows:
              workingTrace && sendState === "sending"
                ? "auto auto auto minmax(0, 1fr) auto auto auto"
                : "auto auto minmax(0, 1fr) auto auto auto",
            gap: "0.65rem",
            minHeight: 0,
            overflowX: "hidden",
            overflowY: "auto",
            scrollbarGutter: "stable",
            padding: "0.8rem 0.85rem",
            borderRadius: "22px",
            border: `1px solid ${palette.lineSilver}`,
            background:
              "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.94) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 28px rgba(0,0,0,0.18)"
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "0.75rem",
              alignItems: "flex-start",
              flexWrap: "wrap"
            }}
          >
            <div>
              <div
                style={{
                  fontSize: "0.76rem",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  color: palette.sandstone,
                  marginBottom: "0.35rem"
                }}
              >
                Active thread
              </div>
              <h2
                style={{
                  margin: 0,
                  fontSize: "1.45rem",
                  lineHeight: 1.15
                }}
              >
                {activeThread?.displayTitle ?? activeSummary?.displayTitle ?? "New conversation"}
              </h2>
            </div>

            <div
              style={{
                display: "flex",
                gap: "0.55rem",
                flexWrap: "wrap",
                color: palette.silverMuted,
                fontSize: "0.82rem",
                alignItems: "center"
              }}
            >
              {(activeThread?.currentRole ?? activeSummary?.currentRole) && (
                <span>Role {(activeThread?.currentRole ?? activeSummary?.currentRole) as string}</span>
              )}
              <span>Mode {activeDisplayMode}</span>
              {(activeThread?.pinned ?? activeSummary?.pinned) && <span>Pinned</span>}
              {activeThread?.updatedAtUtc && <span>{formatTimestamp(activeThread.updatedAtUtc)}</span>}
            </div>
          </div>

          {workingTrace && sendState === "sending" && (
            <div style={{ display: "grid", gap: "0.45rem" }}>
              <WorkingTrace
                phaseLabel={workingTrace.phaseLabel}
                phaseDetail={workingTrace.phaseDetail}
                selectedMode={workingTrace.selectedMode}
                selectedRole={workingTrace.selectedRole}
                selectedRuntime={workingTrace.selectedRuntime}
                selectedModelRuntimeTag={workingTrace.selectedModelRuntimeTag}
                localityState={workingTrace.localityState}
                approvalState={workingTrace.approvalState}
                usedFallback={workingTrace.usedFallback}
                steps={workingTrace.steps}
              />
              <button type="button" onClick={() => void handleCancelActiveRequest()} style={{ justifySelf: "start" }}>
                Cancel current response
              </button>
            </div>
          )}

          <ModeChips
            options={[...MODE_OPTIONS]}
            selectedValue={selectedMode}
            onChange={setSelectedMode}
            disabled={sendState === "sending"}
          />
          <label style={{ display: "flex", gap: "0.55rem", alignItems: "center", color: palette.silverMuted, fontSize: "0.78rem" }}>
            Reasoning depth
            <select aria-label="Reasoning depth for this request" value={requestedGear} disabled={sendState === "sending"} onChange={(event) => setRequestedGear(event.target.value)}>
              <option value="automatic">Automatic</option>
              <option value="reflex">Reflex</option>
              <option value="quick">Quick</option>
              <option value="standard">Standard</option>
              <option value="deep">Deep</option>
              <option value="deliberative">Deliberative</option>
              <option value="research_engineering">Research / Engineering</option>
            </select>
            <span>Depth changes cognition effort, never authority.</span>
          </label>

          <div
            style={{
              minHeight: 0,
              display: "flex",
              overflow: "hidden"
            }}
          >
            <ConversationThread
              thread={activeThread}
              threadState={threadState}
              threadError={threadError}
              threadNotice={threadTruthSummary}
              threadNoticeTone={threadNoticeTone}
              latestAssistantMessageId={latestAssistantMessage?.messageId ?? null}
            />
          </div>


          {lastArtifacts.length > 0 && (
            <div
              aria-label="Local artifact outputs"
              style={{
                display: "grid",
                gap: "0.75rem",
                maxHeight: isCompactLayout ? "40vh" : "34vh",
                overflowY: "auto",
                overflowX: "hidden",
                paddingRight: "0.25rem"
              }}
            >
              {lastArtifacts.map((artifact) => {
                const bridgeArtifact = artifactSummaryToBridgeData(artifact);

                return artifact.kind === "plot_image" ? (
                  <PlotArtifactView
                    key={artifact.artifactId}
                    artifact={bridgeArtifact}
                    svgText={artifact.svgText}
                    compact={isCompactLayout}
                  />
                ) : (
                  <ArtifactCard
                    key={artifact.artifactId}
                    artifact={bridgeArtifact}
                    compact={isCompactLayout}
                  />
                );
              })}
            </div>
          )}

          {showCoderTruthCards && (
            <div
              aria-label="Coder runtime truth surfaces"
              style={{
                display: "grid",
                gap: "0.75rem",
                maxHeight: isCompactLayout ? "46vh" : "36vh",
                overflowY: "auto",
                overflowX: "hidden",
                paddingRight: "0.25rem"
              }}
            >
              <RepoContextCard
                repoContext={repoContextCardData}
                compact={isCompactLayout}
              />
              <CodePatchCard
                codePatchPlan={codePatchPlanCardData}
                compact={isCompactLayout}
              />
              <CommandGateCard
                mode={activeDisplayMode}
                codePatchPlan={codePatchPlanCardData}
                compact={isCompactLayout}
              />
            </div>
          )}

          <details
            aria-label="Governed file and document stewardship"
            style={{
              display: "grid",
              gap: "0.6rem",
              maxHeight: isCompactLayout ? "52vh" : "42vh",
              overflowY: "auto",
              overflowX: "hidden",
              padding: "0.65rem",
              borderRadius: "16px",
              border: `1px solid ${palette.lineSilver}`,
              background: "rgba(7, 11, 16, 0.62)"
            }}
          >
            <summary
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "0.75rem",
                alignItems: "center",
                minHeight: "1.8rem",
                color: palette.sandstone,
                cursor: "pointer",
                fontSize: "0.76rem",
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase"
              }}
            >
              <span>File and document stewardship</span>
              <span
                style={{
                  color: approvedPreviewInContext ? palette.teal : palette.silverMuted,
                  fontSize: "0.74rem",
                  fontWeight: 600,
                  letterSpacing: "normal",
                  textTransform: "none"
                }}
              >
                {stewardshipBusy
                  ? "Working…"
                  : approvedPreviewInContext
                    ? "Approved context ready"
                    : "Open tools"}
              </span>
            </summary>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: "0.75rem",
                alignItems: "flex-start",
                flexWrap: "wrap"
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    color: palette.sandstone,
                    fontSize: "0.72rem",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase"
                  }}
                >
                  File and document stewardship
                </div>
                <div
                  style={{
                    color: palette.silverMuted,
                    fontSize: "0.86rem",
                    lineHeight: 1.45,
                    marginTop: "0.25rem"
                  }}
                >
                  Uses the selected local file path above. Approved previews can enter this conversation;
                  writes require explicit approval and backend path/type/hash guards.
                </div>
              </div>
              <div
                style={{
                  border: `1px solid ${approvedPreviewInContext ? palette.teal : palette.lineSilver}`,
                  borderRadius: "999px",
                  color: approvedPreviewInContext ? palette.teal : palette.silverMuted,
                  padding: "0.28rem 0.55rem",
                  fontSize: "0.76rem",
                  whiteSpace: "nowrap"
                }}
              >
                {approvedPreviewInContext ? "Approved context ready" : "No approved preview"}
              </div>
            </div>

            {(stewardshipState.error || stewardshipState.notice) && (
              <div
                style={{
                  border: `1px solid ${stewardshipState.error ? palette.oxide : palette.teal}`,
                  borderRadius: "12px",
                  padding: "0.65rem",
                  color: stewardshipState.error ? "#FFB7A7" : palette.teal,
                  background: stewardshipState.error
                    ? "rgba(255, 118, 118, 0.08)"
                    : "rgba(58, 202, 184, 0.08)",
                  fontSize: "0.85rem",
                  lineHeight: 1.45
                }}
              >
                {stewardshipState.error ?? stewardshipState.notice}
              </div>
            )}

            <div
              style={{
                display: "flex",
                gap: "0.55rem",
                flexWrap: "wrap"
              }}
            >
              <button
                type="button"
                onClick={() => void handleInspectStewardshipFile()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.lineSilver}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(255,255,255,0.04)",
                  color: palette.silver,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Inspect file type
              </button>
              <button
                type="button"
                onClick={() => void handleReadStewardshipPreview()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.teal}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(58, 202, 184, 0.1)",
                  color: palette.teal,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Approve bounded preview
              </button>
              <button
                type="button"
                onClick={() => void handleInspectStewardshipDocument()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.lineSilver}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(255,255,255,0.04)",
                  color: palette.silver,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Inspect document
              </button>
              <button
                type="button"
                onClick={() => void handleExtractStewardshipDocument()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.lineSilver}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(255,255,255,0.04)",
                  color: palette.silver,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Extract document preview
              </button>
              <button
                type="button"
                onClick={() => void handleInspectData()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.lineSilver}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(255,255,255,0.04)",
                  color: palette.silver,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Inspect data
              </button>
              <button
                type="button"
                onClick={() => void handlePreviewData()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.lineSilver}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(255,255,255,0.04)",
                  color: palette.silver,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Preview data
              </button>
              <button
                type="button"
                onClick={() => void handleInspectVisual()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.lineSilver}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(255,255,255,0.04)",
                  color: palette.silver,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Inspect visual
              </button>
              <button
                type="button"
                onClick={() => void handlePreviewVisual()}
                disabled={stewardshipBusy}
                style={{
                  border: `1px solid ${palette.lineSilver}`,
                  borderRadius: "999px",
                  padding: "0.45rem 0.7rem",
                  background: "rgba(255,255,255,0.04)",
                  color: palette.silver,
                  cursor: stewardshipBusy ? "not-allowed" : "pointer"
                }}
              >
                Preview visual
              </button>
              {isMediaCandidate && (
                <>
                  <button
                    type="button"
                    onClick={() => void handleInspectMedia()}
                    disabled={stewardshipBusy}
                    style={{
                      border: `1px solid ${palette.teal}`,
                      borderRadius: "999px",
                      padding: "0.45rem 0.7rem",
                      background: "rgba(58, 202, 184, 0.1)",
                      color: palette.teal,
                      cursor: stewardshipBusy ? "not-allowed" : "pointer"
                    }}
                  >
                    Inspect media metadata
                  </button>
                  {mediaDescriptor?.media_family === "video" && (
                    <button
                      type="button"
                      onClick={() => void handleThumbnailMedia()}
                      disabled={stewardshipBusy}
                      style={{
                        border: `1px solid ${palette.lineSilver}`,
                        borderRadius: "999px",
                        padding: "0.45rem 0.7rem",
                        background: "rgba(255,255,255,0.04)",
                        color: palette.silver,
                        cursor: stewardshipBusy ? "not-allowed" : "pointer"
                      }}
                    >
                      Derive safe video thumbnail
                    </button>
                  )}
                </>
              )}
            </div>

            {isArchiveCandidate && (
              <ArchiveContainerPanel
                preview={stewardshipState.archiveInspection}
                plan={stewardshipState.archiveExtractionPlan}
                result={stewardshipState.archiveExtractionResult}
                busy={stewardshipBusy}
                onInspect={() => void handleInspectArchive()}
                onPlan={(indexes) => void handlePlanArchiveExtraction(indexes)}
                onApply={() => void handleApplyArchiveExtraction()}
              />
            )}

            {isDatabaseCandidate && (
              <DataBinaryForgePanel
                kind="database"
                database={stewardshipState.databaseInspection}
                schema={stewardshipState.databaseSchema}
                binary={null}
                busy={stewardshipBusy}
                onInspectDatabase={() => void handleInspectDatabase()}
                onPreviewSchema={() => void handlePreviewDatabaseSchema()}
                onInspectBinary={() => undefined}
              />
            )}

            {isBinaryCandidate && (
              <DataBinaryForgePanel
                kind="binary"
                database={null}
                schema={null}
                binary={stewardshipState.binaryInspection}
                busy={stewardshipBusy}
                onInspectDatabase={() => undefined}
                onPreviewSchema={() => undefined}
                onInspectBinary={() => void handleInspectBinary()}
              />
            )}

            {isEngineeringCandidate && (
              <EngineeringForgePanel
                inspection={stewardshipState.engineeringInspection}
                previewPlan={stewardshipState.engineeringPreviewPlan}
                previewResult={stewardshipState.engineeringPreviewResult}
                busy={stewardshipBusy}
                onInspect={() => void handleInspectEngineering()}
                onPlanPreview={() => void handlePlanEngineeringPreview()}
                onApplyPreview={() => void handleApplyEngineeringPreview()}
              />
            )}

            {(stewardshipDescriptor || documentDescriptor || visualDescriptor || mediaDescriptor) && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: isCompactLayout
                    ? "minmax(0, 1fr)"
                    : "repeat(2, minmax(0, 1fr))",
                  gap: "0.7rem"
                }}
              >
                {stewardshipDescriptor && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(255,255,255,0.03)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ fontWeight: 700, color: palette.silver }}>
                      {stewardshipDescriptor.label}
                    </div>
                    <div
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.82rem",
                        lineHeight: 1.5,
                        marginTop: "0.35rem"
                      }}
                    >
                      {humanize(stewardshipDescriptor.category)} · {humanize(stewardshipDescriptor.adapter)}
                      <br />
                      Capabilities:{" "}
                      {Object.entries(stewardshipDescriptor.capabilities ?? {})
                        .filter(([, value]) => value === true)
                        .map(([key]) => humanize(key))
                        .join(", ") || "No write capability surfaced"}
                      <br />
                      Risk:{" "}
                      {Object.entries(stewardshipDescriptor.riskFlags ?? {})
                        .filter(([, value]) => value === true)
                        .map(([key]) => humanize(key))
                        .join(", ") || "No risk flags surfaced"}
                    </div>
                  </div>
                )}

                {documentDescriptor && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(255,255,255,0.03)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ fontWeight: 700, color: palette.silver }}>
                      {documentDescriptor.label ?? "Document"}
                    </div>
                    <div
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.82rem",
                        lineHeight: 1.5,
                        marginTop: "0.35rem"
                      }}
                    >
                      {humanize(documentDescriptor.family)} · {humanize(documentDescriptor.adapter)}
                      <br />
                      Export: {documentDescriptor.exportable ? "available" : "not available"} · Edit:{" "}
                      {documentIsPdf
                        ? "approved derived-copy PDF operations"
                        : documentDescriptor.editable
                          ? "stable operations only"
                          : "unsafe direct edits blocked"}
                      <br />
                      Stable edits:{" "}
                      {stableDocumentOperations.length > 0
                        ? stableDocumentOperations.map((entry) => humanize(entry)).join(", ")
                        : "None surfaced"}
                    </div>
                  </div>
                )}

                {visualDescriptor && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(255,255,255,0.03)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ fontWeight: 700, color: palette.silver }}>
                      {visualDescriptor.label ?? "Visual file"}
                    </div>
                    <div
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.82rem",
                        lineHeight: 1.5,
                        marginTop: "0.35rem"
                      }}
                    >
                      {humanize(visualDescriptor.category)} · {humanize(visualDescriptor.adapter)}
                      <br />
                      EXIF/GPS: summary only · Raw pixels: not in audit
                      <br />
                      Stable ops:{" "}
                      {(visualDescriptor.stable_operations ?? [])
                        .slice(0, 8)
                        .map((entry) => humanize(entry))
                        .join(", ") || "Inspect/export only"}
                    </div>
                  </div>
                )}

                {mediaDescriptor && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(255,255,255,0.03)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ fontWeight: 700, color: palette.silver }}>
                      {mediaDescriptor.label ?? "Media file"}
                    </div>
                    <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.5, marginTop: "0.35rem" }}>
                      {humanize(mediaDescriptor.media_family)} · local metadata only
                      <br />
                      Thumbnail: {mediaDescriptor.capabilities?.thumbnail_capable ? "fixed video frame only" : "not applicable"}
                      <br />
                      STT: exact-approved local artifact · TTS: exact-approved synthetic reading voice
                      <br />
                      Mutation/transcoding: unavailable · ImageForge: cancellable optional Creator-profile route · VideoForge: cancellable disabled-by-default lab route
                    </div>
                  </div>
                )}
              </div>
            )}

            {(stewardshipState.filePreview || stewardshipState.documentPreview || stewardshipState.dataPreview || stewardshipState.visualPreview || stewardshipState.mediaInspection || stewardshipState.mediaThumbnail) && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: isCompactLayout
                    ? "minmax(0, 1fr)"
                    : "repeat(4, minmax(0, 1fr))",
                  gap: "0.7rem"
                }}
              >
                {stewardshipState.filePreview && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(0,0,0,0.18)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ color: palette.silver, fontWeight: 700 }}>
                      File preview · {humanize(stewardshipState.filePreview.status)}
                    </div>
                    <div
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.8rem",
                        lineHeight: 1.45,
                        marginTop: "0.3rem"
                      }}
                    >
                      {stewardshipState.filePreview.relative_path ?? stewardshipState.filePreview.file_label}
                      {" · "}
                      {stewardshipState.filePreview.lines_returned ?? 0} lines returned
                      {" · "}
                      {stewardshipState.filePreview.redactions?.length ?? 0} redactions
                    </div>
                    <pre
                      style={{
                        margin: "0.6rem 0 0",
                        maxHeight: "12rem",
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                        overflowWrap: "anywhere",
                        color: palette.silver,
                        fontSize: "0.78rem",
                        lineHeight: 1.45
                      }}
                    >
                      {stewardshipState.filePreview.content_preview ??
                        stewardshipState.filePreview.blocked_reason ??
                        "No preview text surfaced."}
                    </pre>
                  </div>
                )}

                {stewardshipState.documentPreview && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(0,0,0,0.18)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ color: palette.silver, fontWeight: 700 }}>
                      Document preview · {humanize(stewardshipState.documentPreview.status)}
                    </div>
                    <div
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.8rem",
                        lineHeight: 1.45,
                        marginTop: "0.3rem"
                      }}
                    >
                      Metadata: {formatObjectSummary(stewardshipState.documentPreview.metadata)}
                      <br />
                      Tables: {stewardshipState.documentPreview.tables?.length ?? 0} · Outline:{" "}
                      {stewardshipState.documentPreview.outline?.length ?? 0} · Provenance:{" "}
                      {stewardshipState.documentPreview.provenance?.length ?? 0}
                    </div>
                    <pre
                      style={{
                        margin: "0.6rem 0 0",
                        maxHeight: "12rem",
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                        overflowWrap: "anywhere",
                        color: palette.silver,
                        fontSize: "0.78rem",
                        lineHeight: 1.45
                      }}
                    >
                      {stewardshipState.documentPreview.text_preview ??
                        stewardshipState.documentPreview.blocked_reason ??
                        "No document preview text surfaced."}
                    </pre>
                  </div>
                )}

                {stewardshipState.dataPreview && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(0,0,0,0.18)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ color: palette.silver, fontWeight: 700 }}>
                      Data preview · {humanize(stewardshipState.dataPreview.status)}
                    </div>
                    <div
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.8rem",
                        lineHeight: 1.45,
                        marginTop: "0.3rem"
                      }}
                    >
                      {stewardshipState.dataPreview.descriptor?.label ?? "Data file"} ·{" "}
                      {humanize(stewardshipState.dataPreview.descriptor?.adapter)}
                      <br />
                      Metadata: {formatObjectSummary(stewardshipState.dataPreview.metadata)}
                      <br />
                      Tables: {stewardshipState.dataPreview.tables?.length ?? 0} · Layers:{" "}
                      {stewardshipState.dataPreview.layers?.length ?? 0} · Redactions:{" "}
                      {stewardshipState.dataPreview.redaction_count ?? 0}
                    </div>
                    <pre
                      style={{
                        margin: "0.6rem 0 0",
                        maxHeight: "12rem",
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                        overflowWrap: "anywhere",
                        color: palette.silver,
                        fontSize: "0.78rem",
                        lineHeight: 1.45
                      }}
                    >
                      {JSON.stringify(
                        stewardshipState.dataPreview.preview ??
                          stewardshipState.dataPreview.schema_summary ??
                          stewardshipState.dataPreview.metadata ??
                          stewardshipState.dataPreview.blocked_reason,
                        null,
                        2
                      )}
                    </pre>
                  </div>
                )}

                {stewardshipState.visualPreview && (
                  <div
                    style={{
                      border: `1px solid ${palette.lineSilver}`,
                      borderRadius: "12px",
                      padding: "0.7rem",
                      background: "rgba(0,0,0,0.18)",
                      minWidth: 0
                    }}
                  >
                    <div style={{ color: palette.silver, fontWeight: 700 }}>
                      Visual preview · {humanize(stewardshipState.visualPreview.status)}
                    </div>
                    {typeof stewardshipState.visualPreview.preview?.thumbnail_data_url === "string" && (
                      <img
                        src={stewardshipState.visualPreview.preview.thumbnail_data_url}
                        alt=""
                        style={{
                          width: "100%",
                          maxHeight: "12rem",
                          objectFit: "contain",
                          marginTop: "0.55rem",
                          borderRadius: "10px",
                          border: `1px solid ${palette.lineSilver}`,
                          background: "rgba(255,255,255,0.04)"
                        }}
                      />
                    )}
                    <div
                      style={{
                        color: palette.silverMuted,
                        fontSize: "0.8rem",
                        lineHeight: 1.45,
                        marginTop: "0.55rem"
                      }}
                    >
                      {stewardshipState.visualPreview.descriptor?.label ?? "Visual file"} ·{" "}
                      {humanize(stewardshipState.visualPreview.descriptor?.adapter)}
                      <br />
                      Metadata: {formatObjectSummary(stewardshipState.visualPreview.metadata)}
                      <br />
                      EXIF: {formatObjectSummary(stewardshipState.visualPreview.exif_privacy)} · SVG:{" "}
                      {formatObjectSummary(stewardshipState.visualPreview.svg_safety)}
                      <br />
                      Raw pixels and precise GPS are not included in audit or chat context.
                    </div>
                  </div>
                )}

                {(stewardshipState.mediaThumbnail ?? stewardshipState.mediaInspection) && (() => {
                  const media = stewardshipState.mediaThumbnail ?? stewardshipState.mediaInspection;
                  if (!media) return null;
                  return (
                    <div
                      style={{
                        border: `1px solid ${palette.lineSilver}`,
                        borderRadius: "12px",
                        padding: "0.7rem",
                        background: "rgba(0,0,0,0.18)",
                        minWidth: 0
                      }}
                    >
                      <div style={{ color: palette.silver, fontWeight: 700 }}>
                        Media metadata · {humanize(media.status)}
                      </div>
                      {typeof media.thumbnail_data_url === "string" && (
                        <img
                          src={media.thumbnail_data_url}
                          alt="Locally derived video thumbnail"
                          style={{
                            width: "100%",
                            maxHeight: "12rem",
                            objectFit: "contain",
                            marginTop: "0.55rem",
                            borderRadius: "10px",
                            border: `1px solid ${palette.lineSilver}`,
                            background: "rgba(255,255,255,0.04)"
                          }}
                        />
                      )}
                      <div style={{ color: palette.silverMuted, fontSize: "0.8rem", lineHeight: 1.5, marginTop: "0.55rem" }}>
                        {media.descriptor?.label ?? media.file_label ?? "Media file"} · {media.container ?? "container unknown"}
                        <br />
                        Duration: {media.duration_seconds ?? "unknown"} s · Bitrate: {media.bitrate_bps ?? "unknown"} bps · Streams: {media.stream_count ?? 0}
                        <br />
                        Audio: {formatObjectSummary(media.audio)}
                        <br />
                        Video: {formatObjectSummary(media.video)}
                        <br />
                        Privacy flags: {formatObjectSummary(media.privacy_flags)}
                        <br />
                        Safety flags: {formatObjectSummary(media.safety_flags)}
                        <br />
                        Approval: explicit · Request: {media.request_id ?? "not surfaced"} · Operation: {media.operation_id ?? "not surfaced"} · Audit: {media.audit_written ? "persisted" : "not persisted"}
                        <br />
                        Raw media and embedded tag values are not in chat context or audit. STT and non-cloning TTS use separate exact-approved local worker operations; mutation and transcoding are unavailable.
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            <details>
              <summary style={{ color: palette.teal, cursor: "pointer", fontWeight: 700 }}>
                Governed speech and media workers
              </summary>
              <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.7rem" }}>
                <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.5 }}>
                  SpeechForge: {mediaWorkerTruth?.speechforge?.stt_enabled === true ? "local STT available" : "STT unavailable"} ·{" "}
                  {mediaWorkerTruth?.speechforge?.tts_enabled === true ? "local Kokoro reading voice available" : "TTS unavailable"}
                  <br />
                  ImageForge: {humanize(safeString(mediaWorkerTruth?.imageforge?.state) ?? "unknown")} · VideoForge:{" "}
                  {humanize(safeString(mediaWorkerTruth?.videoforge?.state) ?? "unknown")}
                  <br />
                  Voice cloning and reference-voice input: deliberately unavailable by design. Image/video generation has no production-enabled control; lab use never implies production approval.
                </div>

                {isMediaCandidate && (
                  <div style={{ border: `1px solid ${palette.lineSilver}`, borderRadius: "12px", padding: "0.7rem" }}>
                    <div style={{ color: palette.silver, fontWeight: 700 }}>Local machine transcript</div>
                    <label style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", color: palette.silverMuted, fontSize: "0.8rem", marginTop: "0.5rem" }}>
                      <input
                        type="checkbox"
                        checked={speechConsentConfirmed}
                        onChange={(event) => setSpeechConsentConfirmed(event.target.checked)}
                      />
                      <span>I confirm processing rights and all required consent for voices in this selected file.</span>
                    </label>
                    <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap", marginTop: "0.55rem" }}>
                      <button type="button" onClick={() => void handlePlanTranscription()} disabled={stewardshipBusy || !speechConsentConfirmed}>
                        Plan transcript
                      </button>
                      <button type="button" onClick={() => void handleApplyTranscription()} disabled={stewardshipBusy || stewardshipState.transcriptionPlan?.status !== "planned"}>
                        Approve and transcribe
                      </button>
                    </div>
                    {(stewardshipState.transcriptionPlan || stewardshipState.transcriptionResult) && (
                      <div style={{ color: palette.silverMuted, fontSize: "0.78rem", lineHeight: 1.5, marginTop: "0.55rem" }}>
                        Plan: {humanize(stewardshipState.transcriptionPlan?.status)} · Result: {humanize(stewardshipState.transcriptionResult?.status)}
                        <br />
                        Artifact: {stewardshipState.transcriptionResult?.artifact_id ?? "not created"} · Request: {stewardshipState.transcriptionResult?.request_id ?? "not surfaced"} · Audit: {stewardshipState.transcriptionResult?.audit_written ? "persisted" : "not yet persisted"}
                        <br />
                        Raw transcript is saved only to the approved local artifact and is not returned or placed in central trace.
                        Machine transcripts can be inaccurate or hallucinate words; verify important content against the source recording.
                      </div>
                    )}
                  </div>
                )}

                <div style={{ border: `1px solid ${palette.lineSilver}`, borderRadius: "12px", padding: "0.7rem" }}>
                  <div style={{ color: palette.silver, fontWeight: 700 }}>Synthetic reading voice</div>
                  <textarea
                    value={ttsTextDraft}
                    onChange={(event) => setTtsTextDraft(event.target.value)}
                    maxLength={4000}
                    rows={3}
                    placeholder="Short passage to read locally with a catalog voice"
                    style={{ width: "100%", boxSizing: "border-box", marginTop: "0.5rem", resize: "vertical" }}
                  />
                  <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap", marginTop: "0.55rem" }}>
                    <select value={ttsVoiceId} onChange={(event) => setTtsVoiceId(event.target.value)}>
                      {(ttsVoices.length > 0 ? ttsVoices : [{ id: "af_sarah", display_name: "Sarah" }]).map((voice) => (
                        <option key={voice.id} value={voice.id}>{voice.display_name ?? voice.id}</option>
                      ))}
                    </select>
                    <button type="button" onClick={() => void handlePlanTts()} disabled={stewardshipBusy || !ttsTextDraft.trim()}>
                      Plan local reading
                    </button>
                    <button type="button" onClick={() => void handleApplyTts()} disabled={stewardshipBusy || stewardshipState.ttsPlan?.status !== "planned"}>
                      Approve and speak
                    </button>
                  </div>
                  {stewardshipState.ttsResult?.audio_data_url && (
                    <audio controls src={stewardshipState.ttsResult.audio_data_url} style={{ width: "100%", marginTop: "0.6rem" }}>
                      Local synthetic reading audio
                    </audio>
                  )}
                  {(stewardshipState.ttsPlan || stewardshipState.ttsResult) && (
                    <div style={{ color: palette.silverMuted, fontSize: "0.78rem", lineHeight: 1.5, marginTop: "0.55rem" }}>
                      Plan: {humanize(stewardshipState.ttsPlan?.status)} · Result: {humanize(stewardshipState.ttsResult?.status)} · Voice: {stewardshipState.ttsPlan?.voice_label ?? ttsVoiceId}
                      <br />
                      Artifact: {stewardshipState.ttsResult?.artifact_id ?? "not created"} · Request: {stewardshipState.ttsResult?.request_id ?? "not surfaced"} · Audit: {stewardshipState.ttsResult?.audit_written ? "persisted" : "not yet persisted"}
                      <br />
                      Synthetic reading voice only. No reference audio, identity cloning, or impersonation workflow exists.
                    </div>
                  )}
                </div>

                <details style={{ border: `1px solid ${palette.lineSilver}`, borderRadius: "12px", padding: "0.7rem" }}>
                  <summary style={{ color: palette.silver, cursor: "pointer", fontWeight: 700 }}>
                    Generative media labs
                  </summary>
                  <div style={{ color: palette.silverMuted, fontSize: "0.78rem", lineHeight: 1.5, marginTop: "0.55rem" }}>
                    CommonCanvas remains lab-only because its local license files conflict. FLUX has one lab-only 256×256, one-step sequential-offload profile; provenance, cancellation, and sustained resource gates remain open. Mitsua is blocked because the local weights require unsafe pickle loading. Wan is lab-only and fixed to 416×256, 9 frames, 8 fps, and 4 steps.
                  </div>
                  <textarea
                    value={videoForgePromptDraft}
                    onChange={(event) => setVideoForgePromptDraft(event.target.value)}
                    maxLength={1200}
                    rows={3}
                    placeholder="Short non-identity-bearing prompt for one local synthetic Wan lab clip"
                    style={{ width: "100%", boxSizing: "border-box", marginTop: "0.55rem", resize: "vertical" }}
                    disabled={mediaWorkerTruth?.videoforge?.lab_environment_enabled !== true}
                  />
                  <label style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", color: palette.silverMuted, fontSize: "0.78rem", marginTop: "0.5rem" }}>
                    <input
                      type="checkbox"
                      checked={videoForgeLabAcknowledged}
                      onChange={(event) => setVideoForgeLabAcknowledged(event.target.checked)}
                      disabled={mediaWorkerTruth?.videoforge?.lab_environment_enabled !== true}
                    />
                    <span>I understand this is a local-only lab feature, synthetic media must not be represented as a real event, and production licensing/provenance/resource gates remain open.</span>
                  </label>
                  <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap", marginTop: "0.55rem" }}>
                    <button
                      type="button"
                      onClick={() => void handlePlanVideoForge()}
                      disabled={stewardshipBusy || mediaWorkerTruth?.videoforge?.lab_environment_enabled !== true || !videoForgeLabAcknowledged || !videoForgePromptDraft.trim()}
                    >
                      Plan Wan lab clip
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleApplyVideoForge()}
                      disabled={stewardshipBusy || stewardshipState.videoForgePlan?.status !== "planned"}
                    >
                      Approve and generate
                    </button>
                    {["queued", "running", "cancel_requested"].includes(stewardshipState.videoForgeJob?.status ?? "") && (
                      <button type="button" onClick={() => void handleCancelVideoForge()} disabled={stewardshipBusy}>
                        Cancel local job
                      </button>
                    )}
                  </div>
                  <div style={{ color: palette.silverMuted, fontSize: "0.78rem", lineHeight: 1.5, marginTop: "0.55rem" }}>
                    Route: {mediaWorkerTruth?.videoforge?.routes_live === true ? "live" : "unavailable"} · Lab environment: {mediaWorkerTruth?.videoforge?.lab_environment_enabled === true ? "enabled" : "disabled by default"} · Cancellation: {mediaWorkerTruth?.videoforge?.cancellation_supported === true ? "supported" : "unavailable"}
                    {(stewardshipState.videoForgePlan || stewardshipState.videoForgeJob) && (
                      <>
                        <br />
                        Plan: {humanize(stewardshipState.videoForgePlan?.status)} · Job: {humanize(stewardshipState.videoForgeJob?.status)} · Operation: {stewardshipState.videoForgeJob?.operation_id ?? "not started"}
                        <br />
                        Artifact: {stewardshipState.videoForgeJob?.artifact_id ?? "not created"} · Request: {stewardshipState.videoForgeJob?.request_id ?? "not surfaced"} · Audit: {stewardshipState.videoForgeJob?.audit_written ? "persisted" : "pending/not persisted"}
                      </>
                    )}
                  </div>
                </details>
              </div>
            </details>

            <details open={isVisualCandidate}>
              <summary style={{ color: palette.teal, cursor: "pointer", fontWeight: 700 }}>
                Visual OCR, analysis, export, and derived edit
              </summary>
              <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.7rem" }}>
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handleVisualOcr()} disabled={stewardshipBusy}>
                    Run approved OCR
                  </button>
                  <button type="button" onClick={() => void handleVisualAnalysis()} disabled={stewardshipBusy}>
                    Run local analysis
                  </button>
                </div>
                {(stewardshipState.visualOcr || stewardshipState.visualAnalysis) && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    OCR: {safeString(stewardshipState.visualOcr?.status) ?? "not run"} · Analysis:{" "}
                    {safeString(stewardshipState.visualAnalysis?.status) ?? "not run"}
                    <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                      {JSON.stringify(
                        {
                          ocr: stewardshipState.visualOcr,
                          analysis: stewardshipState.visualAnalysis
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                )}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isCompactLayout
                      ? "minmax(0, 1fr)"
                      : "minmax(130px, 160px) minmax(0, 1fr)",
                    gap: "0.55rem"
                  }}
                >
                  <select
                    value={visualExportFormat}
                    onChange={(event) =>
                      setVisualExportFormat(
                        event.target.value as "markdown" | "json" | "png" | "jpg" | "webp" | "tiff" | "svg"
                      )
                    }
                  >
                    <option value="markdown">Markdown summary</option>
                    <option value="json">JSON summary</option>
                    <option value="png">PNG derived copy</option>
                    <option value="jpg">JPG derived copy</option>
                    <option value="webp">WebP derived copy</option>
                    <option value="tiff">TIFF derived copy</option>
                    <option value="svg">Sanitized SVG copy</option>
                  </select>
                  <input
                    value={visualExportTargetDraft}
                    onChange={(event) => setVisualExportTargetDraft(event.target.value)}
                    placeholder="Optional visual export target path"
                  />
                </div>
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handlePlanVisualExport()} disabled={stewardshipBusy}>
                    Plan visual export
                  </button>
                  <button type="button" onClick={() => void handleApplyVisualExport()} disabled={stewardshipBusy || !stewardshipState.visualExportPlan}>
                    Approve visual export
                  </button>
                </div>
                {stewardshipState.visualExportPlan && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Export plan: {humanize(stewardshipState.visualExportPlan.status)} ·{" "}
                    {stewardshipState.visualExportPlan.plan_summary}
                    {stewardshipState.visualExportPlan.preview && (
                      <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                        {stewardshipState.visualExportPlan.preview}
                      </pre>
                    )}
                  </div>
                )}
                {stewardshipState.visualExportResult && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Export result: {humanize(stewardshipState.visualExportResult.status)} · Mutation:{" "}
                    {stewardshipState.visualExportResult.mutation_performed ? "yes" : "no"} · Audit:{" "}
                    {stewardshipState.visualExportResult.audit_written ? "yes" : "no"}
                  </div>
                )}
                <input
                  value={visualEditOperationDraft}
                  onChange={(event) => setVisualEditOperationDraft(event.target.value)}
                  placeholder="Governed visual operation, e.g. strip_exif, make_thumbnail, redact_rectangles, sanitize_svg"
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem"
                  }}
                />
                <textarea
                  value={visualEditParametersDraft}
                  onChange={(event) => setVisualEditParametersDraft(event.target.value)}
                  placeholder='JSON parameters, e.g. {"target_path":"thumb.png","size":512}'
                  rows={5}
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem",
                    resize: "vertical",
                    fontFamily: "monospace",
                    fontSize: "0.8rem"
                  }}
                />
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handlePlanVisualEdit()} disabled={stewardshipBusy}>
                    Plan visual edit
                  </button>
                  <button type="button" onClick={() => void handleApplyVisualEdit()} disabled={stewardshipBusy || !stewardshipState.visualEditPlan}>
                    Approve derived edit
                  </button>
                </div>
                {(stewardshipState.visualEditPlan || stewardshipState.visualEditResult) && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Edit plan: {humanize(stewardshipState.visualEditPlan?.status)} · Result:{" "}
                    {humanize(stewardshipState.visualEditResult?.status)}
                    <br />
                    {stewardshipState.visualEditPlan?.plan_summary}
                    {stewardshipState.visualEditResult?.blocked_reason
                      ? ` Blocked: ${stewardshipState.visualEditResult.blocked_reason}.`
                      : ""}
                    <br />
                    Details: {formatObjectSummary(stewardshipState.visualEditResult?.operation_details)}
                  </div>
                )}
              </div>
            </details>

            <details>
              <summary style={{ color: palette.teal, cursor: "pointer", fontWeight: 700 }}>
                Science/data export and governed mutation
              </summary>
              <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.7rem" }}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isCompactLayout
                      ? "minmax(0, 1fr)"
                      : "minmax(130px, 160px) minmax(0, 1fr)",
                    gap: "0.55rem"
                  }}
                >
                  <select
                    value={dataExportFormat}
                    onChange={(event) =>
                      setDataExportFormat(event.target.value as "markdown" | "json" | "csv" | "geojson")
                    }
                  >
                    <option value="markdown">Markdown summary</option>
                    <option value="json">JSON summary</option>
                    <option value="csv">CSV preview</option>
                    <option value="geojson">GeoJSON preview</option>
                  </select>
                  <input
                    value={dataExportTargetDraft}
                    onChange={(event) => setDataExportTargetDraft(event.target.value)}
                    placeholder="Optional data export target path"
                  />
                </div>
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handlePlanDataExport()} disabled={stewardshipBusy}>
                    Plan data export
                  </button>
                  <button type="button" onClick={() => void handleApplyDataExport()} disabled={stewardshipBusy || !stewardshipState.dataExportPlan}>
                    Approve data export
                  </button>
                </div>
                {stewardshipState.dataExportPlan && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Export plan: {humanize(stewardshipState.dataExportPlan.status)} ·{" "}
                    {stewardshipState.dataExportPlan.plan_summary}
                    {stewardshipState.dataExportPlan.preview && (
                      <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                        {stewardshipState.dataExportPlan.preview}
                      </pre>
                    )}
                  </div>
                )}
                {stewardshipState.dataExportResult && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Export result: {humanize(stewardshipState.dataExportResult.status)} · Mutation:{" "}
                    {stewardshipState.dataExportResult.mutation_performed ? "yes" : "no"} · Audit:{" "}
                    {stewardshipState.dataExportResult.audit_written ? "yes" : "no"}
                  </div>
                )}
                <input
                  value={dataMutationOperationDraft}
                  onChange={(event) => setDataMutationOperationDraft(event.target.value)}
                  placeholder="Governed data operation, e.g. tabular_append_row, jsonl_append_record, sqlite_insert_row, geojson_update_properties"
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem"
                  }}
                />
                <textarea
                  value={dataMutationParametersDraft}
                  onChange={(event) => setDataMutationParametersDraft(event.target.value)}
                  placeholder='JSON parameters, e.g. {"row":{"name":"beta"}}'
                  rows={5}
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem",
                    resize: "vertical",
                    fontFamily: "monospace",
                    fontSize: "0.8rem"
                  }}
                />
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handlePlanDataMutation()} disabled={stewardshipBusy}>
                    Plan data mutation
                  </button>
                  <button type="button" onClick={() => void handleApplyDataMutation()} disabled={stewardshipBusy || !stewardshipState.dataMutationPlan}>
                    Approve data mutation
                  </button>
                </div>
                {(stewardshipState.dataMutationPlan || stewardshipState.dataMutationResult) && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Mutation plan: {humanize(stewardshipState.dataMutationPlan?.status)} · Result:{" "}
                    {humanize(stewardshipState.dataMutationResult?.status)}
                    <br />
                    {stewardshipState.dataMutationPlan?.plan_summary}
                    {stewardshipState.dataMutationResult?.blocked_reason
                      ? ` Blocked: ${stewardshipState.dataMutationResult.blocked_reason}.`
                      : ""}
                    <br />
                    Backup: {formatObjectSummary(stewardshipState.dataMutationResult?.backup)}
                    <br />
                    Details: {formatObjectSummary(stewardshipState.dataMutationResult?.operation_details)}
                  </div>
                )}
              </div>
            </details>

            <details>
              <summary style={{ color: palette.teal, cursor: "pointer", fontWeight: 700 }}>
                Patch and file operations
              </summary>
              <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.7rem" }}>
                <input
                  value={patchSummaryDraft}
                  onChange={(event) => setPatchSummaryDraft(event.target.value)}
                  placeholder="Patch summary"
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem"
                  }}
                />
                <textarea
                  value={patchDiffDraft}
                  onChange={(event) => setPatchDiffDraft(event.target.value)}
                  placeholder="Paste a unified diff for governed proposal/apply."
                  rows={5}
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem",
                    resize: "vertical",
                    fontFamily: "monospace",
                    fontSize: "0.8rem"
                  }}
                />
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handleProposeStewardshipPatch()} disabled={stewardshipBusy}>
                    Preview patch proposal
                  </button>
                  <button type="button" onClick={() => void handleApplyStewardshipPatch()} disabled={stewardshipBusy || !stewardshipState.patchProposal}>
                    Approve apply patch
                  </button>
                </div>
                {stewardshipState.patchProposal && (
                  <pre
                    style={{
                      margin: 0,
                      maxHeight: "10rem",
                      overflow: "auto",
                      whiteSpace: "pre-wrap",
                      overflowWrap: "anywhere",
                      color: palette.silverMuted,
                      fontSize: "0.78rem"
                    }}
                  >
                    {stewardshipState.patchProposal.diff_preview ??
                      stewardshipState.patchProposal.warnings?.join("\n") ??
                      "Patch proposal surfaced without diff preview."}
                  </pre>
                )}
                {stewardshipState.patchApplyResult && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem" }}>
                    Patch result: {humanize(stewardshipState.patchApplyResult.status)} · Mutation:{" "}
                    {stewardshipState.patchApplyResult.mutation_performed ? "yes" : "no"} · Audit:{" "}
                    {stewardshipState.patchApplyResult.audit_written ? "yes" : "no"}
                  </div>
                )}

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isCompactLayout
                      ? "minmax(0, 1fr)"
                      : "minmax(120px, 160px) minmax(0, 1fr)",
                    gap: "0.55rem"
                  }}
                >
                  <select
                    value={fileOperationKind}
                    onChange={(event) =>
                      setFileOperationKind(event.target.value as StewardshipOperationKind)
                    }
                  >
                    <option value="create">create</option>
                    <option value="edit">edit</option>
                    <option value="replace">replace</option>
                    <option value="delete">delete</option>
                    <option value="rename">rename</option>
                    <option value="move">move</option>
                  </select>
                  <input
                    value={fileOperationDestinationDraft}
                    onChange={(event) => setFileOperationDestinationDraft(event.target.value)}
                    placeholder="Destination path for rename/move, optional otherwise"
                  />
                </div>
                <textarea
                  value={fileOperationTextDraft}
                  onChange={(event) => setFileOperationTextDraft(event.target.value)}
                  placeholder="New text for create/edit/replace operations"
                  rows={4}
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem",
                    resize: "vertical",
                    fontFamily: "monospace",
                    fontSize: "0.8rem"
                  }}
                />
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handlePlanFileOperation()} disabled={stewardshipBusy}>
                    Plan file operation
                  </button>
                  <button type="button" onClick={() => void handleExecuteFileOperation()} disabled={stewardshipBusy || !stewardshipState.fileOperationPlan}>
                    Approve file operation
                  </button>
                </div>
                {(stewardshipState.fileOperationPlan || stewardshipState.fileOperationResult) && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Plan: {humanize(stewardshipState.fileOperationPlan?.status)} · Result:{" "}
                    {humanize(stewardshipState.fileOperationResult?.status)}
                    <br />
                    {(stewardshipState.fileOperationPlan?.plan_steps ?? []).join(" ")}
                    {stewardshipState.fileOperationResult?.blocked_reason
                      ? ` Blocked: ${stewardshipState.fileOperationResult.blocked_reason}.`
                      : ""}
                  </div>
                )}
              </div>
            </details>

            <details open={isDocumentCandidate}>
              <summary style={{ color: palette.teal, cursor: "pointer", fontWeight: 700 }}>
                Document export and stable edit
              </summary>
              <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.7rem" }}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isCompactLayout
                      ? "minmax(0, 1fr)"
                      : "minmax(130px, 160px) minmax(0, 1fr)",
                    gap: "0.55rem"
                  }}
                >
                  <select
                    value={documentExportFormat}
                    onChange={(event) =>
                      setDocumentExportFormat(event.target.value as "markdown" | "text")
                    }
                  >
                    <option value="markdown">Markdown export</option>
                    <option value="text">Text export</option>
                  </select>
                  <input
                    value={documentExportTargetDraft}
                    onChange={(event) => setDocumentExportTargetDraft(event.target.value)}
                    placeholder="Optional export target path"
                  />
                </div>
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => void handlePlanDocumentExport()} disabled={stewardshipBusy}>
                    Plan export
                  </button>
                  <button type="button" onClick={() => void handleApplyDocumentExport()} disabled={stewardshipBusy || !stewardshipState.documentExportPlan}>
                    Approve export
                  </button>
                </div>
                {stewardshipState.documentExportPlan && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Export plan: {humanize(stewardshipState.documentExportPlan.status)} ·{" "}
                    {stewardshipState.documentExportPlan.plan_summary}
                    {stewardshipState.documentExportPlan.preview && (
                      <pre
                        style={{
                          maxHeight: "8rem",
                          overflow: "auto",
                          whiteSpace: "pre-wrap",
                          overflowWrap: "anywhere"
                        }}
                      >
                        {stewardshipState.documentExportPlan.preview}
                      </pre>
                    )}
                  </div>
                )}
                {stewardshipState.documentExportResult && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem" }}>
                    Export result: {humanize(stewardshipState.documentExportResult.status)} · Mutation:{" "}
                    {stewardshipState.documentExportResult.mutation_performed ? "yes" : "no"} · Audit:{" "}
                    {stewardshipState.documentExportResult.audit_written ? "yes" : "no"}
                  </div>
                )}

                <select
                  value={documentEditOperationDraft}
                  onChange={(event) => setDocumentEditOperationDraft(event.target.value)}
                >
                  <option value="">Choose stable edit operation</option>
                  {stableDocumentOperations.map((operation) => (
                    <option key={operation} value={operation}>
                      {operation}
                    </option>
                  ))}
                </select>
                <textarea
                  value={documentEditParametersDraft}
                  onChange={(event) => setDocumentEditParametersDraft(event.target.value)}
                  placeholder='Stable edit parameters as JSON, for example {"text":"Append this paragraph."}'
                  rows={4}
                  style={{
                    border: `1px solid ${palette.lineSilver}`,
                    borderRadius: "10px",
                    background: "rgba(0,0,0,0.22)",
                    color: palette.silver,
                    padding: "0.6rem",
                    resize: "vertical",
                    fontFamily: "monospace",
                    fontSize: "0.8rem"
                  }}
                />
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    onClick={() => void handlePlanDocumentEdit()}
                    disabled={stewardshipBusy || stableDocumentOperations.length === 0}
                  >
                    Plan stable edit
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleApplyDocumentEdit()}
                    disabled={stewardshipBusy || !stewardshipState.documentEditPlan}
                  >
                    Approve stable edit
                  </button>
                </div>
                {stableDocumentOperations.length === 0 && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem" }}>
                    No stable direct edit operation is surfaced for this format. Use extraction/export,
                    derived-copy workflows, or let the backend return an honest refusal with the nearest
                    safe alternative.
                  </div>
                )}
                {(stewardshipState.documentEditPlan || stewardshipState.documentEditResult) && (
                  <div style={{ color: palette.silverMuted, fontSize: "0.82rem", lineHeight: 1.45 }}>
                    Edit plan: {humanize(stewardshipState.documentEditPlan?.status)} · Result:{" "}
                    {humanize(stewardshipState.documentEditResult?.status)}
                    <br />
                    {stewardshipState.documentEditPlan?.plan_summary}
                    {stewardshipState.documentEditPlan?.operation_details &&
                    Object.keys(stewardshipState.documentEditPlan.operation_details).length > 0
                      ? ` Details: ${formatObjectSummary(stewardshipState.documentEditPlan.operation_details)}.`
                      : ""}
                    {stewardshipState.documentEditResult?.operation_details &&
                    Object.keys(stewardshipState.documentEditResult.operation_details).length > 0
                      ? ` Result details: ${formatObjectSummary(stewardshipState.documentEditResult.operation_details)}.`
                      : ""}
                    {stewardshipState.documentEditResult?.blocked_reason
                      ? ` Blocked: ${stewardshipState.documentEditResult.blocked_reason}.`
                      : ""}
                  </div>
                )}
              </div>
            </details>
          </details>

          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              color: palette.silverMuted,
              fontSize: "0.8rem",
              padding: "0.1rem 0.25rem"
            }}
          >
            <input
              type="checkbox"
              checked={useUnlockedSealedMemoryOnce}
              onChange={(event) => setUseUnlockedSealedMemoryOnce(event.target.checked)}
              disabled={sendState === "sending"}
            />
            Use the currently unlocked sealed vault for this message only. Sealed content remains local,
            memory-only, and absent from persistent retrieval indexes.
          </label>

          <Composer
            value={draftMessage}
            onChange={setDraftMessage}
            onSend={() => void handleSend()}
            disabled={composerSendDisabled}
            sending={sendState === "sending"}
            disabledReason={sendDisabledReason}
            sendError={sendError ?? roomError}
            statusText={composerStatusText}
            placeholder="Ask Elysia something local and real."
            rows={2}
            filePathValue={filePathDraft}
            onFilePathChange={setFilePathDraft}
            onAttachFilePath={() => void handleAttachFilePath()}
            onBrowseForFile={() => void handleBrowseForFile()}
            attachingFile={fileAttachState === "attaching"}
            browsingFile={fileBrowseState === "browsing"}
            fileAttachDisabled={sendState === "sending"}
            fileBrowseDisabled={sendState === "sending" || fileAttachState === "attaching"}
            fileAttachError={fileAttachError}
            attachedFiles={attachedFiles}
            onRemoveAttachedFile={handleRemoveAttachedFile}
          />
        </section>
      </div>

      <RenameConversationDialog
        open={Boolean(renameDialogConversation)}
        currentTitle={renameDialogConversation?.displayTitle ?? ""}
        busy={mutatingConversationId === renameDialogConversationId}
        onClose={() => setRenameDialogConversationId(null)}
        onSubmit={(nextTitle) => {
          void handleRenameConversationSubmit(nextTitle);
        }}
      />

      <MoveConversationDialog
        open={Boolean(moveDialogConversation)}
        currentProjectId={moveDialogConversation?.projectId ?? ""}
        projects={moveProjectOptions}
        projectListState={
          moveProjectListState === "idle" ? "loading" : moveProjectListState
        }
        projectListError={moveProjectListError}
        moveError={moveDialogError}
        busy={mutatingConversationId === moveDialogConversationId}
        onClose={() => {
          setMoveDialogConversationId(null);
          setMoveDialogError(null);
        }}
        onSubmit={(nextProjectId) => {
          void handleMoveConversationSubmit(nextProjectId);
        }}
        onRetryProjects={() => {
          void loadMoveProjectOptions();
        }}
        onOpenProjects={onOpenProjects}
      />
    </div>
  );
}

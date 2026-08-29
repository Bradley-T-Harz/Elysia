import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import { openLocalAttachableFile, openLocalEditableImageFile } from "./api/localFilePicker";
import { requireInternetMasterEnabled } from "./api/internetMaster";
import {
  answerProjectQuiz,
  attachProjectSource,
  cancelProjectImageJob,
  createProjectGoal,
  createProjectImage,
  createProjectQuiz,
  createProjectStudyPlan,
  reviewProjectStudyModule,
  recordProjectResearchIteration,
  fetchProjectImageJob,
  fetchProjectGimpStatus,
  fetchProjectSoundCloudStatus,
  fetchProjectWorkbench,
  fetchDurableResearch,
  runBoundedResearchSearch,
  runBoundedResearchFetch,
  resolveResearchEgressApproval,
  reviewResearchEvidence,
  correctResearchEvidence,
  promoteResearchEvidence,
  openProjectImageInGimp,
  beginProjectSoundCloudAuthorization,
  completeProjectSoundCloudAuthorization,
  disconnectProjectSoundCloud,
  verifyProjectSoundCloudAccount,
  speakProjectText,
  transitionProjectResearch,
  transitionProjectGoal,
  updateProjectCanvas,
  type ProjectCanvasElement,
  type ProjectGoal,
  type ProjectQuiz,
  type ProjectResearchInvestigation,
  type ProjectWorkbench
} from "./api/bridgeClient";

export type ProjectWorkbenchTool =
  | "sources"
  | "research"
  | "study"
  | "quizzes"
  | "goals"
  | "canvas"
  | "image"
  | "image_editing"
  | "soundcloud"
  | "speak";

type Props = {
  projectId: string;
  initialTool?: ProjectWorkbenchTool;
  onSourceCountChange?: (count: number) => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  line: "rgba(199, 210, 218, 0.16)",
  lineTeal: "rgba(126, 215, 209, 0.28)"
} as const;

function message(payload: { errors?: string[]; message?: string }, fallback: string): string {
  return payload.errors?.find((entry) => entry.trim()) ?? payload.message ?? fallback;
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.map(record).filter((entry): entry is Record<string, unknown> => entry !== null) : [];
}

function buttonStyle(active = false) {
  return {
    padding: "0.58rem 0.76rem",
    borderRadius: "12px",
    border: `1px solid ${active ? palette.lineTeal : palette.line}`,
    background: active ? "rgba(16, 41, 43, 0.72)" : "rgba(11, 14, 18, 0.5)",
    color: active ? palette.teal : palette.silver,
    cursor: "pointer"
  } as const;
}

const fieldStyle = {
  width: "100%",
  boxSizing: "border-box",
  padding: "0.65rem 0.72rem",
  borderRadius: "12px",
  border: `1px solid ${palette.line}`,
  background: "rgba(11, 14, 18, 0.72)",
  color: palette.silver
} as const;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ display: "grid", gap: "0.8rem", padding: "1rem", borderRadius: "18px", border: `1px solid ${palette.line}`, background: "rgba(18, 25, 37, 0.78)" }}>
      <h3 style={{ margin: 0, color: palette.sandstone }}>{title}</h3>
      {children}
    </section>
  );
}

export default function ProjectWorkbenchPanel({ projectId, initialTool = "sources", onSourceCountChange }: Props) {
  const [tool, setTool] = useState<ProjectWorkbenchTool>(initialTool);
  const [workbench, setWorkbench] = useState<ProjectWorkbench | null>(null);
  const [notice, setNotice] = useState("Loading the local Project workbench…");
  const [busy, setBusy] = useState(false);
  const [topic, setTopic] = useState("");
  const [sourceMaterial, setSourceMaterial] = useState("");
  const [studyDifficulty, setStudyDifficulty] = useState("intermediate");
  const [quizDifficulty, setQuizDifficulty] = useState("intermediate");
  const [quizTitle, setQuizTitle] = useState("Project knowledge check");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [quizFeedback, setQuizFeedback] = useState<Record<string, string>>({});
  const [goal, setGoal] = useState("");
  const [canvasTitle, setCanvasTitle] = useState("Project Canvas");
  const [canvasNote, setCanvasNote] = useState("");
  const [researchQuestion, setResearchQuestion] = useState("");
  const [researchQuery, setResearchQuery] = useState("");
  const [researchResult, setResearchResult] = useState<Record<string, unknown> | null>(null);
  const [researchFetchUrl, setResearchFetchUrl] = useState("");
  const [researchFetchResult, setResearchFetchResult] = useState<Record<string, unknown> | null>(null);
  const [durableResearchSessions, setDurableResearchSessions] = useState<Array<Record<string, unknown>>>([]);
  const [durableEvidence, setDurableEvidence] = useState<Array<Record<string, unknown>>>([]);
  const [activeInvestigationId, setActiveInvestigationId] = useState("");
  const [imagePrompt, setImagePrompt] = useState("");
  const [imageJob, setImageJob] = useState<Record<string, unknown> | null>(null);
  const [speechText, setSpeechText] = useState("");
  const [speechResult, setSpeechResult] = useState<Record<string, unknown> | null>(null);
  const [speechVoice, setSpeechVoice] = useState("af_sarah");
  const [speechSpeed, setSpeechSpeed] = useState(1);
  const speechPlayer = useRef<HTMLAudioElement | null>(null);
  const [gimpStatus, setGimpStatus] = useState<Record<string, unknown> | null>(null);
  const [soundCloudStatus, setSoundCloudStatus] = useState<Record<string, unknown> | null>(null);
  const [soundCloudCode, setSoundCloudCode] = useState("");
  const [soundCloudState, setSoundCloudState] = useState("");

  useEffect(() => setTool(initialTool), [initialTool]);

  const reload = useCallback(async () => {
    const [result, durableResult] = await Promise.all([
      fetchProjectWorkbench(projectId),
      fetchDurableResearch({ projectId })
    ]);
    const next = result.payload.data?.workbench;
    if (result.ok && next) {
      setWorkbench(next);
      setCanvasTitle(next.canvas?.title ?? "Project Canvas");
      onSourceCountChange?.(next.sources?.length ?? 0);
      setNotice("Project workbench loaded from the account-scoped local store.");
    } else {
      setNotice(message(result.payload, "The Project workbench could not be loaded."));
    }
    const durableData = record(durableResult.payload.data);
    setDurableResearchSessions(records(durableData?.sessions));
    setDurableEvidence(records(durableData?.evidence));
  }, [onSourceCountChange, projectId]);

  useEffect(() => { void reload(); }, [reload]);

  useEffect(() => {
    const operationId = text(imageJob?.operation_id);
    const status = text(imageJob?.status);
    if (!operationId || !["queued", "running", "cancel_requested"].includes(status)) return;
    const timer = window.setInterval(() => {
      void fetchProjectImageJob(projectId, operationId).then((result) => {
        const next = result.payload.data?.imageforge_job;
        if (next) setImageJob(next);
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [imageJob, projectId]);

  async function perform(operation: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    try { await operation(); } finally { setBusy(false); }
  }

  const tools = useMemo<Array<{ id: ProjectWorkbenchTool; label: string }>>(() => [
    { id: "sources", label: "Sources" },
    { id: "research", label: "Research" },
    { id: "study", label: "Study" },
    { id: "quizzes", label: "Quizzes" },
    { id: "goals", label: "Pursue Goal" },
    { id: "canvas", label: "Canvas" },
    { id: "image", label: "ImageForge" },
    { id: "image_editing", label: "Image editing" },
    { id: "soundcloud", label: "SoundCloud" },
    { id: "speak", label: "Speak" }
  ], []);

  async function attachSource() {
    const selected = await openLocalAttachableFile();
    if (!selected) return;
    const result = await attachProjectSource(projectId, selected);
    setNotice(result.ok ? "Source attached locally; it was not promoted to Memory or sent outward." : message(result.payload, "Source attachment failed."));
    if (result.ok) await reload();
  }

  async function createStudy() {
    const result = await createProjectStudyPlan(projectId, { topic, source_material: sourceMaterial, difficulty: studyDifficulty });
    setNotice(result.ok ? "Grounded study plan persisted locally." : message(result.payload, "Study plan creation failed."));
    if (result.ok) await reload();
  }

  async function createQuiz() {
    const result = await createProjectQuiz(projectId, { title: quizTitle, source_material: sourceMaterial, difficulty: quizDifficulty, question_count: 5 });
    setNotice(result.ok ? "Grounded quiz persisted locally." : message(result.payload, "Quiz creation failed."));
    if (result.ok) await reload();
  }

  async function submitAnswer(quiz: ProjectQuiz, questionId: string) {
    if (!quiz.quiz_id) return;
    const result = await answerProjectQuiz(projectId, quiz.quiz_id, { question_id: questionId, answer: answers[questionId] ?? "" });
    const feedback = `${result.payload.data?.correct ? "Correct" : "Review needed"}. ${result.payload.data?.explanation ?? ""} Attempt ${result.payload.data?.attempt_count ?? 1}.`;
    if (result.ok) setQuizFeedback((current) => ({ ...current, [questionId]: feedback }));
    setNotice(result.ok ? feedback : message(result.payload, "Answer could not be graded."));
    if (result.ok) await reload();
  }

  async function reviewStudy(planId: string, moduleId: string, action: "start" | "complete" | "needs_review" | "reset") {
    const result = await reviewProjectStudyModule(projectId, planId, moduleId, { action, confidence: action === "complete" ? 4 : undefined });
    setNotice(result.ok ? `Study module is now ${result.payload.data?.study_module?.review_state ?? action}. Progress was persisted locally.` : message(result.payload, "Study progress could not be updated."));
    if (result.ok) await reload();
  }

  async function createGoal() {
    const result = await createProjectGoal(projectId, { goal, budget_steps: 8, budget_minutes: 30 });
    setNotice(result.ok ? "Bounded goal created in draft state." : message(result.payload, "Goal creation failed."));
    if (result.ok) await reload();
  }

  async function transitionGoal(item: ProjectGoal, action: "start" | "pause" | "resume" | "complete_step" | "stop" | "emergency_stop", stepId?: string) {
    if (!item.goal_id) return;
    const result = await transitionProjectGoal(projectId, item.goal_id, { action, step_id: stepId, checkpoint_note: action === "complete_step" ? "Operator confirmed this bounded checkpoint." : undefined });
    setNotice(result.ok ? `Goal state: ${result.payload.data?.goal?.status ?? action}.` : message(result.payload, "Goal transition failed."));
    if (result.ok) await reload();
  }

  async function saveCanvas() {
    const elements = [...(workbench?.canvas?.elements ?? [])];
    if (canvasNote.trim()) elements.push({ kind: "note", content: canvasNote.trim(), x: 40, y: 40 + elements.length * 36, color: "bronze" });
    const result = await updateProjectCanvas(projectId, { title: canvasTitle, elements });
    setNotice(result.ok ? "Project Canvas persisted locally." : message(result.payload, "Canvas save failed."));
    if (result.ok) { setCanvasNote(""); await reload(); }
  }

  async function runResearch() {
    const request = { question: researchQuestion, queries: [researchQuery], max_results_per_query: 5, requires_primary_sources: true };
    let result = await runBoundedResearchSearch(request);
    const blockedData = record(result.payload.data);
    const pendingApproval = record(blockedData?.approval);
    if (!result.ok && pendingApproval?.approval_id) {
      const preview = record(pendingApproval.preview);
      const approved = window.confirm(
        `Sensitive public research needs one exact, short-lived approval.\n\nDestination: ${String(pendingApproval.destination_class ?? "public search engines via local SearXNG")}\nCategories: ${Array.isArray(pendingApproval.data_categories) ? pendingApproval.data_categories.join(", ") : "classified sensitive query"}\nPreview: ${String(preview?.query_preview ?? "sanitized query withheld")}\n\nApprove this one request?`
      );
      if (approved) {
        const resolution = await resolveResearchEgressApproval(String(pendingApproval.approval_id), true);
        const approval = record(record(resolution.payload.data)?.approval);
        const token = String(approval?.approval_token ?? "");
        if (resolution.ok && token) {
          result = await runBoundedResearchSearch({
            ...request,
            approval_id: String(pendingApproval.approval_id),
            approval_token: token
          });
        } else {
          setNotice(message(resolution.payload, "The exact research approval could not be resolved."));
        }
      } else {
        await resolveResearchEgressApproval(String(pendingApproval.approval_id), false);
      }
    }
    const resultData = record(result.payload.data);
    setResearchResult(resultData);
    if (result.ok && resultData) {
      const verification = record(resultData.evidence_verification);
      const saved = await recordProjectResearchIteration(projectId, {
        investigation_id: activeInvestigationId || undefined,
        question: researchQuestion,
        query: researchQuery,
        evidence_packets: records(resultData.evidence_packets),
        evidence_verified: verification?.verified === true
      });
      const investigation = saved.payload.data?.research_investigation;
      if (saved.ok && investigation?.investigation_id) setActiveInvestigationId(investigation.investigation_id);
      if (saved.ok) await reload();
    }
    setNotice(result.ok ? "Bounded research returned verified evidence and persisted this investigation step for follow-up comparison." : message(result.payload, "Research did not complete."));
  }

  async function fetchResearchSource() {
    if (!window.confirm("Fetch this exact harmless public URL through Elysia's bounded evidence worker? The URL leaves local control; private Project context is not attached.")) return;
    const result = await runBoundedResearchFetch({
      question: researchQuestion || "Inspect one explicitly approved public source.",
      url: researchFetchUrl,
    });
    setResearchFetchResult(record(result.payload.data) ?? null);
    setNotice(result.ok ? "The exact requested public page returned bounded evidence; every redirect was revalidated and crawling stayed off." : message(result.payload, "The public source could not be fetched."));
    if (result.ok) await reload();
  }

  async function reviewEvidence(evidenceId: string, status: "verified" | "rejected" | "contradicted") {
    const notes = status === "contradicted"
      ? [window.prompt("Record the contradiction without erasing either claim:")?.trim() ?? ""]
          .filter(Boolean)
      : [];
    const result = await reviewResearchEvidence(evidenceId, status, notes);
    setNotice(result.ok ? `Evidence marked ${status}; provenance was preserved.` : message(result.payload, "Evidence review failed."));
    if (result.ok) await reload();
  }

  async function correctEvidence(item: Record<string, unknown>) {
    const evidenceId = text(item.evidence_id);
    const claim = window.prompt("Corrected claim:", text(item.claim))?.trim();
    if (!claim) return;
    const excerpt = window.prompt("Corrected supporting excerpt:", text(item.excerpt))?.trim();
    if (!excerpt) return;
    const reason = window.prompt("Why is this correction needed?")?.trim();
    if (!reason) return;
    const result = await correctResearchEvidence(evidenceId, claim, excerpt, reason);
    setNotice(result.ok ? "A corrected evidence record superseded the prior record; history remains visible." : message(result.payload, "Evidence correction failed."));
    if (result.ok) await reload();
  }

  async function promoteEvidence(evidenceId: string) {
    const result = await promoteResearchEvidence(evidenceId);
    setNotice(result.ok ? "Verified evidence became a review-required Memory candidate; it was not auto-promoted." : message(result.payload, "Evidence promotion failed."));
    if (result.ok) await reload();
  }

  async function generateImage() {
    if (!window.confirm("Generate one local synthetic image through the Creator-profile FLUX worker? The prompt stays out of central traces; an exact artifact approval will be consumed.")) return;
    const result = await createProjectImage(projectId, { prompt: imagePrompt, operator_approved: true });
    const job = result.payload.data?.imageforge_job ?? result.payload.data?.imageforge_plan ?? null;
    setImageJob(job);
    setNotice(result.ok ? `ImageForge status: ${text(job?.status) || "returned"}.` : message(result.payload, "Image generation could not start."));
  }

  async function speak() {
    if (!window.confirm("Create and play one local synthetic reading-voice artifact? Voice cloning is not used.")) return;
    const result = await speakProjectText(projectId, { text: speechText, voice_id: speechVoice, speed: speechSpeed, operator_approved: true });
    const output = result.payload.data?.tts_result ?? result.payload.data?.tts_plan ?? null;
    setSpeechResult(output);
    setNotice(result.ok ? `SpeechForge status: ${text(output?.status) || "returned"}.` : message(result.payload, "Speech generation failed."));
  }

  async function openImageEditor() {
    const selected = await openLocalEditableImageFile();
    if (!selected) return;
    if (!window.confirm("Create a private Project working copy and open it in the installed local GIMP application? The original will not be mutated.")) return;
    const result = await openProjectImageInGimp(projectId, { source_path: selected, operator_approved: true });
    setGimpStatus(result.payload.data?.gimp ?? null);
    setNotice(result.ok ? "GIMP opened an account-scoped private working copy; the selected original was not changed." : message(result.payload, "GIMP could not be opened."));
  }

  async function loadSoundCloudStatus() {
    const result = await fetchProjectSoundCloudStatus(projectId);
    setSoundCloudStatus(result.payload.data?.soundcloud ?? null);
    setNotice(result.ok ? "SoundCloud connector truth loaded from the account-scoped local store." : message(result.payload, "SoundCloud connector status could not be read."));
  }

  async function beginSoundCloud() {
    const result = await beginProjectSoundCloudAuthorization(projectId);
    const connector = result.payload.data?.soundcloud ?? null;
    setSoundCloudStatus(connector);
    const authorizationUrl = text(connector?.authorization_url);
    if (!result.ok || !authorizationUrl) {
      setNotice(message(result.payload, "SoundCloud authorization could not begin."));
      return;
    }
    await requireInternetMasterEnabled();
    await openUrl(authorizationUrl);
    setNotice("SoundCloud opened its authorization page. After approval, copy the returned code and state from the configured local callback into the fields below.");
  }

  async function completeSoundCloud() {
    const result = await completeProjectSoundCloudAuthorization(projectId, { authorization_code: soundCloudCode, returned_state: soundCloudState });
    setSoundCloudStatus(result.payload.data?.soundcloud ?? null);
    setNotice(result.ok ? "SoundCloud is connected for this local account; credentials remained outside webview JavaScript." : message(result.payload, "SoundCloud authorization could not be completed."));
    if (result.ok) { setSoundCloudCode(""); setSoundCloudState(""); await loadSoundCloudStatus(); }
  }

  async function disconnectSoundCloud() {
    if (!window.confirm("Disconnect SoundCloud and revoke Elysia's locally stored connector credential for this account?")) return;
    const result = await disconnectProjectSoundCloud(projectId);
    setSoundCloudStatus(result.payload.data?.soundcloud ?? null);
    setNotice(result.ok ? `SoundCloud disconnected; the account-scoped local credential was removed. Provider sign-out: ${text(result.payload.data?.soundcloud?.provider_sign_out) || "not attempted"}.` : message(result.payload, "SoundCloud could not be disconnected."));
    if (result.ok) await loadSoundCloudStatus();
  }

  async function verifySoundCloud() {
    const result = await verifyProjectSoundCloudAccount(projectId);
    const verified = result.payload.data?.soundcloud ?? null;
    if (verified) setSoundCloudStatus((current) => ({ ...(current ?? {}), ...verified, credential_state: "connected" }));
    setNotice(result.ok ? `SoundCloud authenticated-account check succeeded for ${text(result.payload.data?.soundcloud?.account_label) || "the connected account"}; no credential entered the webview.` : message(result.payload, "SoundCloud account verification failed."));
  }

  return (
    <div style={{ display: "grid", gap: "0.9rem", minHeight: 0, overflow: "auto", paddingRight: "0.2rem" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
        {tools.map((item) => <button key={item.id} type="button" onClick={() => setTool(item.id)} style={buttonStyle(tool === item.id)}>{item.label}</button>)}
      </div>
      <div role="status" style={{ color: palette.silverMuted, padding: "0.68rem 0.8rem", border: `1px solid ${palette.line}`, borderRadius: "12px" }}>{notice}</div>

      {tool === "sources" && <Section title="Governed local sources">
        <button type="button" disabled={busy} onClick={() => void perform(attachSource)} style={buttonStyle()}>Choose and attach source</button>
        {(workbench?.sources ?? []).map((source) => <div key={source.source_id ?? source.sha256} style={{ color: palette.silverMuted }}>{source.display_name} · {source.file_kind} · local only · not Memory</div>)}
      </Section>}

      {tool === "research" && <Section title="Researcher evidence search">
        <p style={{ margin: 0, color: palette.silverMuted }}>Internet must be enabled in Settings. Only the public-safe query terms below leave local control through the loopback SearXNG worker; private Project source is never appended automatically.</p>
        <input aria-label="Research question" value={researchQuestion} onChange={(event) => setResearchQuestion(event.target.value)} placeholder="Question to investigate" style={fieldStyle} />
        <input aria-label="Public search query" value={researchQuery} onChange={(event) => setResearchQuery(event.target.value)} placeholder="Public-safe search query" style={fieldStyle} />
        <button type="button" disabled={busy || !researchQuestion.trim() || !researchQuery.trim()} onClick={() => void perform(runResearch)} style={buttonStyle()}>Search and verify evidence</button>
        {researchResult && <pre aria-label="Research evidence result" style={{ ...fieldStyle, whiteSpace: "pre-wrap", maxHeight: "22rem", overflow: "auto" }}>{JSON.stringify(researchResult, null, 2)}</pre>}
        <div style={{ borderTop: `1px solid ${palette.line}`, paddingTop: "0.8rem", display: "grid", gap: "0.55rem" }}>
          <strong style={{ color: palette.silver }}>Investigate one exact public source</strong>
          <p style={{ margin: 0, color: palette.silverMuted }}>Elysia fetches one operator-selected harmless public HTTP(S) URL without blanket approval, refuses local/private hosts and credentials, revalidates bounded redirects, caps compressed/decompressed bytes, strips active markup, and never crawls. Sensitive query egress still requires an exact one-time approval.</p>
          <input aria-label="Approved public source URL" value={researchFetchUrl} onChange={(event) => setResearchFetchUrl(event.target.value)} placeholder="https://public.example/source" style={fieldStyle} />
          <button type="button" disabled={busy || !/^https?:\/\//i.test(researchFetchUrl.trim())} onClick={() => void perform(fetchResearchSource)} style={buttonStyle()}>Fetch exact public source</button>
          {researchFetchResult && <pre aria-label="Fetched source evidence" style={{ ...fieldStyle, whiteSpace: "pre-wrap", maxHeight: "18rem", overflow: "auto" }}>{JSON.stringify(researchFetchResult, null, 2)}</pre>}
        </div>
        <div style={{ borderTop: `1px solid ${palette.line}`, paddingTop: "0.8rem", display: "grid", gap: "0.55rem" }}>
          <strong style={{ color: palette.silver }}>Durable governed research</strong>
          <span style={{ color: palette.silverMuted }}>{durableResearchSessions.length} sessions · {durableEvidence.length} evidence records linked to this Project</span>
          {durableEvidence.map((item) => {
            const evidenceId = text(item.evidence_id);
            const verification = text(item.verification_status) || "candidate";
            return <div key={evidenceId} style={{ display: "grid", gap: "0.4rem", padding: "0.65rem", border: `1px solid ${palette.line}`, borderRadius: "10px", color: palette.silverMuted }}>
              <strong style={{ color: palette.silver }}>{text(item.title) || "Untitled evidence"}</strong>
              <span>{text(item.claim)} · {verification} · {text(item.source_classification) || "unknown source class"}</span>
              <span>Provenance: {text(item.retrieval_method)} · URL hash retained · quarantine: {text(item.quarantine_state)}</span>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                <button type="button" disabled={busy || !evidenceId} onClick={() => void perform(() => reviewEvidence(evidenceId, "verified"))} style={buttonStyle()}>Verify</button>
                <button type="button" disabled={busy || !evidenceId} onClick={() => void perform(() => reviewEvidence(evidenceId, "contradicted"))} style={buttonStyle()}>Record contradiction</button>
                <button type="button" disabled={busy || !evidenceId} onClick={() => void perform(() => correctEvidence(item))} style={buttonStyle()}>Correct/supersede</button>
                <button type="button" disabled={busy || !evidenceId || verification !== "verified"} onClick={() => void perform(() => promoteEvidence(evidenceId))} style={buttonStyle()}>Create Memory candidate</button>
                <button type="button" disabled={busy || !evidenceId} onClick={() => void perform(() => reviewEvidence(evidenceId, "rejected"))} style={buttonStyle()}>Reject</button>
              </div>
            </div>;
          })}
        </div>
        {(workbench?.research_investigations ?? []).map((investigation: ProjectResearchInvestigation) => <div key={investigation.investigation_id} style={{ display: "grid", gap: "0.45rem", padding: "0.7rem", border: `1px solid ${palette.line}`, borderRadius: "12px", color: palette.silverMuted }}>
          <strong style={{ color: palette.silver }}>{investigation.question} · {investigation.status}</strong>
          <span>{investigation.iterations?.length ?? 0} investigation steps · {investigation.source_count ?? 0} sources · comparison: {investigation.comparison?.status ?? "pending"}</span>
          {(investigation.comparison?.explicit_notes?.length ?? 0) > 0 && <span>Contradictions/caveats: {investigation.comparison?.explicit_notes?.join(" · ")}</span>}
          {investigation.investigation_id && ["active", "paused"].includes(investigation.status ?? "") && <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            <button type="button" onClick={() => setActiveInvestigationId(investigation.investigation_id ?? "")} style={buttonStyle(activeInvestigationId === investigation.investigation_id)}>Continue this investigation</button>
            <button type="button" onClick={() => void perform(async () => { const result = await transitionProjectResearch(projectId, investigation.investigation_id ?? "", investigation.status === "paused" ? "resume" : "pause"); setNotice(result.ok ? "Research status persisted." : message(result.payload, "Research status could not change.")); if (result.ok) await reload(); })} style={buttonStyle()}>{investigation.status === "paused" ? "Resume" : "Pause"}</button>
            <button type="button" onClick={() => void perform(async () => { const result = await transitionProjectResearch(projectId, investigation.investigation_id ?? "", "complete"); setNotice(result.ok ? "Research investigation completed with its evidence preserved." : message(result.payload, "Research could not complete.")); if (result.ok) await reload(); })} style={buttonStyle()}>Complete</button>
            <button type="button" onClick={() => void perform(async () => { const result = await transitionProjectResearch(projectId, investigation.investigation_id ?? "", "cancel"); setNotice(result.ok ? "Research investigation cancelled; no additional network work will run." : message(result.payload, "Research could not be cancelled.")); if (result.ok) await reload(); })} style={buttonStyle()}>Cancel</button>
          </div>}
        </div>)}
      </Section>}

      {tool === "study" && <Section title="Grounded study plan">
        <input aria-label="Study topic" value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Study topic" style={fieldStyle} />
        <textarea aria-label="Study source" value={sourceMaterial} onChange={(event) => setSourceMaterial(event.target.value)} placeholder="Paste source material; Elysia will ground the plan in this text." rows={8} style={fieldStyle} />
        <select aria-label="Study difficulty" value={studyDifficulty} onChange={(event) => setStudyDifficulty(event.target.value)} style={fieldStyle}><option value="foundational">Foundational</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select>
        <button type="button" disabled={busy || !topic.trim() || !sourceMaterial.trim()} onClick={() => void perform(createStudy)} style={buttonStyle()}>Create grounded study plan</button>
        {(workbench?.study_plans ?? []).map((plan) => <div key={plan.study_plan_id} style={{ display: "grid", gap: "0.5rem", color: palette.silverMuted }}><strong style={{ color: palette.silver }}>{plan.topic} · {plan.difficulty} · {plan.progress?.percent ?? 0}% complete</strong>{(plan.modules ?? []).map((module) => <div key={module.module_id} style={{ display: "grid", gap: "0.35rem", padding: "0.55rem", border: `1px solid ${palette.line}`, borderRadius: "10px" }}><span>• {module.objective} — {module.practice_prompt}</span><span>Review state: {module.review_state ?? "not_started"}</span>{plan.study_plan_id && module.module_id && <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}><button type="button" onClick={() => void perform(() => reviewStudy(plan.study_plan_id ?? "", module.module_id ?? "", "start"))} style={buttonStyle()}>Begin practice</button><button type="button" onClick={() => void perform(() => reviewStudy(plan.study_plan_id ?? "", module.module_id ?? "", "complete"))} style={buttonStyle()}>Mark understood</button><button type="button" onClick={() => void perform(() => reviewStudy(plan.study_plan_id ?? "", module.module_id ?? "", "needs_review"))} style={buttonStyle()}>Schedule review</button></div>}</div>)}</div>)}
      </Section>}

      {tool === "quizzes" && <Section title="Evidence-grounded quizzes">
        <input aria-label="Quiz title" value={quizTitle} onChange={(event) => setQuizTitle(event.target.value)} style={fieldStyle} />
        <textarea aria-label="Quiz source" value={sourceMaterial} onChange={(event) => setSourceMaterial(event.target.value)} placeholder="Use `term: definition` lines or grounded source statements." rows={8} style={fieldStyle} />
        <select aria-label="Quiz difficulty" value={quizDifficulty} onChange={(event) => setQuizDifficulty(event.target.value)} style={fieldStyle}><option value="foundational">Foundational</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select>
        <button type="button" disabled={busy || !sourceMaterial.trim()} onClick={() => void perform(createQuiz)} style={buttonStyle()}>Generate quiz</button>
        {(workbench?.quizzes ?? []).map((quiz) => <div key={quiz.quiz_id} style={{ display: "grid", gap: "0.6rem" }}><strong style={{ color: palette.silver }}>{quiz.title} · {quiz.difficulty} · {quiz.score ?? 0}/{quiz.questions?.length ?? 0}</strong>{(quiz.questions ?? []).map((question) => <div key={question.question_id} style={{ display: "grid", gap: "0.35rem" }}><span style={{ color: palette.silverMuted }}>{question.prompt}</span><input aria-label={`Answer ${question.prompt}`} value={answers[question.question_id ?? ""] ?? ""} onChange={(event) => setAnswers({ ...answers, [question.question_id ?? ""]: event.target.value })} style={fieldStyle} /><button type="button" disabled={busy || !question.question_id || !(answers[question.question_id] ?? "").trim()} onClick={() => void perform(() => submitAnswer(quiz, question.question_id ?? ""))} style={buttonStyle()}>{question.mastered ? "Review answer" : (question.attempts?.length ?? 0) > 0 ? "Retry answer" : "Submit answer"}</button>{quizFeedback[question.question_id ?? ""] && <span role="status" style={{ color: palette.teal }}>{quizFeedback[question.question_id ?? ""]}</span>}</div>)}</div>)}
      </Section>}

      {tool === "goals" && <Section title="Bounded goal pursuit">
        <textarea aria-label="Goal" value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="Define the outcome and constraints." rows={4} style={fieldStyle} />
        <button type="button" disabled={busy || !goal.trim()} onClick={() => void perform(createGoal)} style={buttonStyle()}>Create bounded draft goal</button>
        {(workbench?.goals ?? []).map((item) => <div key={item.goal_id} style={{ display: "grid", gap: "0.45rem", color: palette.silverMuted }}><strong style={{ color: palette.silver }}>{item.goal} · {item.status}</strong><span>Budget {item.steps_used ?? 0}/{item.budget_steps ?? 0} steps · hidden execution off · shell/push/publication off</span><div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>{item.status === "draft" && <button type="button" onClick={() => void perform(() => transitionGoal(item, "start"))} style={buttonStyle()}>Start</button>}{item.status === "active" && <><button type="button" onClick={() => void perform(() => transitionGoal(item, "pause"))} style={buttonStyle()}>Pause</button>{item.steps?.find((step) => step.status === "pending") && <button type="button" onClick={() => void perform(() => transitionGoal(item, "complete_step", item.steps?.find((step) => step.status === "pending")?.step_id))} style={buttonStyle()}>Complete next checkpoint</button>}</>}{item.status === "paused" && <button type="button" onClick={() => void perform(() => transitionGoal(item, "resume"))} style={buttonStyle()}>Resume</button>}{["draft", "active", "paused"].includes(item.status ?? "") && <><button type="button" onClick={() => void perform(() => transitionGoal(item, "stop"))} style={buttonStyle()}>Stop</button><button type="button" onClick={() => void perform(() => transitionGoal(item, "emergency_stop"))} style={buttonStyle()}>Emergency stop</button></>}</div></div>)}
      </Section>}

      {tool === "canvas" && <Section title="Local Project Canvas">
        <input aria-label="Canvas title" value={canvasTitle} onChange={(event) => setCanvasTitle(event.target.value)} style={fieldStyle} />
        <textarea aria-label="Canvas note" value={canvasNote} onChange={(event) => setCanvasNote(event.target.value)} placeholder="Add a note to the internal Project Canvas." rows={4} style={fieldStyle} />
        <button type="button" disabled={busy || (!canvasNote.trim() && canvasTitle === workbench?.canvas?.title)} onClick={() => void perform(saveCanvas)} style={buttonStyle()}>Save Canvas</button>
        {(workbench?.canvas?.elements ?? []).map((element: ProjectCanvasElement) => <div key={element.element_id ?? element.content} style={{ padding: "0.7rem", borderRadius: "12px", border: `1px solid ${palette.line}`, color: palette.silverMuted }}>{element.content}</div>)}
      </Section>}

      {tool === "image" && <Section title="ImageForge · local synthetic image">
        <p style={{ margin: 0, color: palette.silverMuted }}>Requires the optional Creator profile and local FLUX.1-schnell assets. One bounded 256×256 step, no network model loading, real-person likeness requests refused, exact approval, cancellable job, and provenance sidecar.</p>
        <textarea aria-label="Image prompt" value={imagePrompt} onChange={(event) => setImagePrompt(event.target.value)} rows={5} style={fieldStyle} />
        <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}><button type="button" disabled={busy || !imagePrompt.trim()} onClick={() => void perform(generateImage)} style={buttonStyle()}>Generate approved image</button>{text(imageJob?.operation_id) && ["queued", "running"].includes(text(imageJob?.status)) && <button type="button" onClick={() => void perform(async () => { const result = await cancelProjectImageJob(projectId, text(imageJob?.operation_id)); if (result.payload.data?.imageforge_job) setImageJob(result.payload.data.imageforge_job); })} style={buttonStyle()}>Cancel</button>}</div>
        {imageJob && <div style={{ color: palette.silverMuted }}>Status: {text(imageJob.status)}{text(imageJob.blocked_reason) ? ` · ${text(imageJob.blocked_reason)}` : ""}</div>}
        {text(imageJob?.image_data_url) && <img src={text(imageJob?.image_data_url)} alt="Locally generated synthetic Project image" style={{ maxWidth: "min(100%, 512px)", borderRadius: "14px" }} />}
      </Section>}

      {tool === "image_editing" && <Section title="Local image editing · GIMP">
        <p style={{ margin: 0, color: palette.silverMuted }}>This replaces the historical vendor-labelled Canva no-op with a governed local/open workflow. Elysia copies one approved image into the private Project artifact area and opens that copy using a fixed GIMP command; the original is never mutated.</p>
        <button type="button" disabled={busy} onClick={() => void perform(openImageEditor)} style={buttonStyle()}>Choose image and open private working copy</button>
        {gimpStatus && <div style={{ color: palette.silverMuted }}>Provider: {text(gimpStatus.provider)} · {gimpStatus.original_unchanged === true ? "original unchanged" : text(gimpStatus.available) ? "available" : "dependency unavailable"}</div>}
        {!gimpStatus && <button type="button" onClick={() => void perform(async () => { const result = await fetchProjectGimpStatus(projectId); setGimpStatus(result.payload.data?.gimp ?? null); setNotice(result.ok ? `GIMP dependency ${result.payload.data?.gimp?.available === true ? "is available" : "is not installed"}.` : message(result.payload, "GIMP status could not be read.")); })} style={buttonStyle()}>Check GIMP dependency</button>}
      </Section>}

      {tool === "soundcloud" && <Section title="Optional SoundCloud connector">
        <p style={{ margin: 0, color: palette.silverMuted }}>SoundCloud is never required by Elysia. A user-owned registered SoundCloud application, explicit OAuth authorization, and Internet ON are required. Credentials stay in the account-scoped local encrypted connector store and can be revoked here.</p>
        <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
          <button type="button" disabled={busy} onClick={() => void perform(loadSoundCloudStatus)} style={buttonStyle()}>Check connector status</button>
          <button type="button" disabled={busy || soundCloudStatus?.configured === false || soundCloudStatus?.internet_master_enabled === false} onClick={() => void perform(beginSoundCloud)} style={buttonStyle()}>Authorize with SoundCloud</button>
          {text(soundCloudStatus?.credential_state) === "connected" && <><button type="button" disabled={busy || soundCloudStatus?.internet_master_enabled === false} onClick={() => void perform(verifySoundCloud)} style={buttonStyle()}>Verify connected account</button><button type="button" disabled={busy} onClick={() => void perform(disconnectSoundCloud)} style={buttonStyle()}>Disconnect and revoke</button></>}
        </div>
        {soundCloudStatus && <div style={{ color: palette.silverMuted }}>Configuration: {soundCloudStatus.configured === true ? "ready" : "registered app required"} · credential: {text(soundCloudStatus.credential_state) || "not connected"} · Internet: {soundCloudStatus.internet_master_enabled === true ? "ON" : "OFF"}</div>}
        {soundCloudStatus?.authorization_pending === true && <div style={{ display: "grid", gap: "0.55rem" }}>
          <input aria-label="SoundCloud authorization code" value={soundCloudCode} onChange={(event) => setSoundCloudCode(event.target.value)} placeholder="Authorization code returned to the local callback" autoComplete="off" style={fieldStyle} />
          <input aria-label="SoundCloud returned state" value={soundCloudState} onChange={(event) => setSoundCloudState(event.target.value)} placeholder="Returned state value" autoComplete="off" style={fieldStyle} />
          <button type="button" disabled={busy || soundCloudCode.trim().length < 8 || soundCloudState.trim().length < 16} onClick={() => void perform(completeSoundCloud)} style={buttonStyle()}>Complete secure connection</button>
        </div>}
      </Section>}

      {tool === "speak" && <Section title="SpeechForge · synthetic reading voice">
        <p style={{ margin: 0, color: palette.silverMuted }}>Local Kokoro catalog voice only. Voice cloning and reference-voice input are unavailable by design.</p>
        <textarea aria-label="Text to speak" value={speechText} onChange={(event) => setSpeechText(event.target.value)} rows={6} style={fieldStyle} />
        <select aria-label="Reading voice" value={speechVoice} onChange={(event) => setSpeechVoice(event.target.value)} style={fieldStyle}><option value="af_sarah">Sarah · local catalog voice</option></select>
        <label style={{ color: palette.silverMuted }}>Reading speed {speechSpeed.toFixed(2)}×<input aria-label="Reading speed" type="range" min="0.75" max="1.25" step="0.05" value={speechSpeed} onChange={(event) => setSpeechSpeed(Number(event.target.value))} style={{ width: "100%" }} /></label>
        <button type="button" disabled={busy || !speechText.trim()} onClick={() => void perform(speak)} style={buttonStyle()}>Create approved reading voice</button>
        {speechResult && <div style={{ color: palette.silverMuted }}>Status: {text(speechResult.status)}{text(speechResult.blocked_reason) ? ` · ${text(speechResult.blocked_reason)}` : ""}</div>}
        {text(speechResult?.audio_data_url) && <><audio ref={speechPlayer} controls autoPlay src={text(speechResult?.audio_data_url)} /><button type="button" onClick={() => { if (speechPlayer.current) { speechPlayer.current.pause(); speechPlayer.current.currentTime = 0; } setNotice("Speech playback stopped by the operator."); }} style={buttonStyle()}>Stop speech</button></>}
      </Section>}
    </div>
  );
}

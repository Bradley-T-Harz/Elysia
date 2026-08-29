import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { accountPalette, readEnvelopeError } from "./accountPresentation";
import {
  fetchOnboardingState,
  finalizeOnboarding,
  saveOnboardingDraft,
  type OnboardingAnswer,
  type OnboardingSection
} from "./api/bridgeClient";

type Props = {
  offeredAfterAccountCreation: boolean;
  onDone: () => void;
};

const newAnswer = (questionId: string): OnboardingAnswer => ({
  question_id: questionId,
  exact_answer: "",
  proposed_title: "",
  proposed_wording: "",
  privacy: "private",
  retention: "persistent"
});

export default function PersonalOnboardingPage({ offeredAfterAccountCreation, onDone }: Props) {
  const [sections, setSections] = useState<OnboardingSection[]>([]);
  const [answers, setAnswers] = useState<Record<string, OnboardingAnswer>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("checking");
  const [reviewing, setReviewing] = useState(false);
  const [sealedPassword, setSealedPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchOnboardingState().then((result) => {
      if (cancelled) return;
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        setStatus("error");
        return;
      }
      const data = result.payload.data;
      const loaded: Record<string, OnboardingAnswer> = {};
      for (const answer of data?.answers ?? []) loaded[answer.question_id] = answer;
      setSections(data?.sections ?? []);
      setAnswers(loaded);
      setSelected(new Set(Object.values(loaded).filter((item) => item.exact_answer && item.retention === "persistent").map((item) => item.question_id)));
      setStatus(data?.status ?? "not_started");
      if (
        !offeredAfterAccountCreation
        && !["not_started", "in_progress", "importing"].includes(data?.status ?? "")
      ) {
        onDone();
      }
    });
    return () => { cancelled = true; };
  }, [offeredAfterAccountCreation, onDone]);

  const answerList = useMemo(
    () => Object.values(answers).filter((answer) => answer.exact_answer.trim()),
    [answers]
  );

  function update(questionId: string, patch: Partial<OnboardingAnswer>) {
    setAnswers((current) => {
      const previous = current[questionId] ?? newAnswer(questionId);
      const next = { ...previous, ...patch };
      if (patch.exact_answer !== undefined && !previous.proposed_wording) {
        next.proposed_wording = patch.exact_answer;
      }
      return { ...current, [questionId]: next };
    });
  }

  async function persist(): Promise<boolean> {
    const result = await saveOnboardingDraft(answerList);
    if (!result.ok || result.payload.status !== "ok") {
      setError(readEnvelopeError(result.payload));
      return false;
    }
    setStatus(result.payload.data?.status ?? "in_progress");
    return true;
  }

  async function finish(action: "import_all" | "import_selected" | "import_none" | "discard" | "skip") {
    setBusy(true);
    setError(null);
    try {
      if (!["skip", "discard"].includes(action) && !(await persist())) return;
      const result = await finalizeOnboarding({
        action,
        selected_question_ids: action === "import_selected" ? [...selected] : [],
        sealed_password: sealedPassword || null
      });
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      onDone();
    } finally {
      setBusy(false);
    }
  }

  async function saveAndExit() {
    setBusy(true);
    setError(null);
    try {
      if (await persist()) onDone();
    } finally {
      setBusy(false);
    }
  }

  if (status === "checking") return <main style={pageStyle}><p>Opening local onboarding truth…</p></main>;

  return (
    <main style={pageStyle} data-testid="personal-onboarding-page">
      <div style={shellStyle}>
        <header>
          <div style={eyebrowStyle}>Optional · local · account-owned</div>
          <h1 style={{ margin: 0 }}>Personal onboarding</h1>
          <p style={mutedStyle}>
            Skip everything or any question. Drafts are encrypted for this local account.
            Nothing becomes autobiographical memory until you review the exact proposed packet
            and explicitly import it. Nothing is sent to the Website, research, connectors, or cloud.
          </p>
        </header>

        {!reviewing ? (
          <>
            {sections.map((section) => (
              <section key={section.section_id} style={sectionStyle}>
                <h2>{section.title}</h2>
                {section.questions.map((question) => {
                  const answer = answers[question.question_id] ?? newAnswer(question.question_id);
                  return (
                    <div key={question.question_id} style={questionStyle}>
                      <label htmlFor={question.question_id} style={{ fontWeight: 750 }}>{question.prompt}</label>
                      <textarea
                        id={question.question_id}
                        value={answer.exact_answer}
                        onChange={(event) => update(question.question_id, { exact_answer: event.target.value })}
                        rows={3}
                        placeholder="Optional — leave blank to skip"
                        style={inputStyle}
                      />
                      {answer.exact_answer && (
                        <div style={choiceGridStyle}>
                          <label>Memory privacy
                            <select value={answer.privacy} onChange={(event) => update(question.question_id, { privacy: event.target.value as OnboardingAnswer["privacy"] })} style={selectStyle}>
                              <option value="normal">Normal</option>
                              <option value="private">Private</option>
                              <option value="sealed">Sealed</option>
                            </select>
                          </label>
                          <label>Retention
                            <select value={answer.retention} onChange={(event) => update(question.question_id, { retention: event.target.value as OnboardingAnswer["retention"] })} style={selectStyle}>
                              <option value="persistent">Propose for memory</option>
                              <option value="temporary">Temporary draft only</option>
                              <option value="not_remembered">Do not remember</option>
                            </select>
                          </label>
                        </div>
                      )}
                    </div>
                  );
                })}
              </section>
            ))}
            <div style={actionRowStyle}>
              <button type="button" disabled={busy} onClick={() => void finish("skip")} style={secondaryButtonStyle}>Skip entire questionnaire</button>
              <button type="button" disabled={busy} onClick={() => void saveAndExit()} style={secondaryButtonStyle}>Save encrypted draft and continue later</button>
              <button
                type="button"
                disabled={busy || answerList.length === 0}
                onClick={() => {
                  setSelected(new Set(answerList.filter((answer) => answer.retention === "persistent").map((answer) => answer.question_id)));
                  setReviewing(true);
                }}
                style={primaryButtonStyle}
              >Review proposed memory packet</button>
            </div>
          </>
        ) : (
          <section style={sectionStyle} aria-label="Exact proposed onboarding memory packet">
            <h2>Review exactly what Elysia proposes to remember</h2>
            {answerList.map((answer) => (
              <article key={answer.question_id} style={questionStyle}>
                <label style={{ display: "flex", gap: ".6rem", alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={selected.has(answer.question_id)}
                    disabled={answer.retention !== "persistent"}
                    onChange={(event) => setSelected((current) => {
                      const next = new Set(current);
                      if (event.target.checked) next.add(answer.question_id); else next.delete(answer.question_id);
                      return next;
                    })}
                  />
                  Include {answer.question_id.toUpperCase()} ({answer.privacy}, {answer.retention})
                </label>
                <label>Memory title
                  <input value={answer.proposed_title} onChange={(event) => update(answer.question_id, { proposed_title: event.target.value })} placeholder={`Personal onboarding ${answer.question_id.toUpperCase()}`} style={selectStyle} />
                </label>
                <label>Exact proposed wording
                  <textarea value={answer.proposed_wording} onChange={(event) => update(answer.question_id, { proposed_wording: event.target.value })} rows={3} style={inputStyle} />
                </label>
              </article>
            ))}
            {answerList.some((answer) => selected.has(answer.question_id) && answer.privacy === "sealed") && (
              <label>Reauthenticate to import Sealed answers
                <input type="password" autoComplete="current-password" value={sealedPassword} onChange={(event) => setSealedPassword(event.target.value)} style={selectStyle} />
              </label>
            )}
            <div style={actionRowStyle}>
              <button type="button" onClick={() => setReviewing(false)} style={secondaryButtonStyle}>Back and edit</button>
              <button type="button" disabled={busy} onClick={() => void finish("discard")} style={secondaryButtonStyle}>Discard packet</button>
              <button type="button" disabled={busy} onClick={() => void finish("import_none")} style={secondaryButtonStyle}>Import none</button>
              <button type="button" disabled={busy || selected.size === 0} onClick={() => void finish("import_selected")} style={primaryButtonStyle}>Import selected reviewed answers</button>
              <button type="button" disabled={busy} onClick={() => void finish("import_all")} style={primaryButtonStyle}>Import all persistent answers</button>
            </div>
          </section>
        )}
        {error && <div role="alert" style={errorStyle}>{error}</div>}
      </div>
    </main>
  );
}

const pageStyle: CSSProperties = { height: "100vh", minHeight: 0, maxHeight: "100vh", overflowX: "hidden", overflowY: "auto", scrollbarGutter: "stable", padding: "2rem 1rem", boxSizing: "border-box", background: "linear-gradient(180deg,#111726,#0B0E12)", color: accountPalette.silver, fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" };
const shellStyle: CSSProperties = { width: "min(980px,100%)", margin: "0 auto", display: "grid", gap: "1rem" };
const sectionStyle: CSSProperties = { display: "grid", gap: "1rem", padding: "1rem", border: `1px solid ${accountPalette.lineSilver}`, borderRadius: 18, background: accountPalette.panel };
const questionStyle: CSSProperties = { display: "grid", gap: ".55rem", paddingBottom: "1rem", borderBottom: "1px solid rgba(199,210,218,.12)" };
const inputStyle: CSSProperties = { width: "100%", boxSizing: "border-box", resize: "vertical", border: `1px solid ${accountPalette.lineSilver}`, borderRadius: 12, padding: ".72rem", color: accountPalette.silver, background: "rgba(11,14,18,.55)", font: "inherit" };
const selectStyle: CSSProperties = { ...inputStyle, resize: undefined, marginTop: ".35rem" };
const choiceGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: ".8rem" };
const actionRowStyle: CSSProperties = { display: "flex", flexWrap: "wrap", gap: ".65rem", justifyContent: "flex-end" };
const secondaryButtonStyle: CSSProperties = { border: `1px solid ${accountPalette.lineSilver}`, borderRadius: 12, padding: ".72rem .9rem", background: accountPalette.panelSoft, color: accountPalette.silver, cursor: "pointer" };
const primaryButtonStyle: CSSProperties = { ...secondaryButtonStyle, border: "1px solid rgba(126,215,209,.42)", background: "rgba(16,71,75,.78)", fontWeight: 800 };
const mutedStyle: CSSProperties = { color: accountPalette.silverMuted, lineHeight: 1.58, maxWidth: 840 };
const eyebrowStyle: CSSProperties = { fontSize: ".72rem", letterSpacing: ".12em", textTransform: "uppercase", color: accountPalette.sandstone, marginBottom: ".42rem" };
const errorStyle: CSSProperties = { color: accountPalette.danger, border: "1px solid rgba(216,165,165,.3)", borderRadius: 12, padding: ".75rem", background: "rgba(216,165,165,.08)" };

import { useCallback, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import type { DrawerSection } from "./RightDrawer";
import type { Actor, ChangePlan, ExactApproval, Installation, OperationReceipt, WorkspaceDescriptor, WorkspaceGrant } from "./api/codevContracts";
import { codevRequest, type ChatResult, type CodevHandoff, type CommandCatalog, type CommandResult } from "./api/codevNative";
import "./CodevWorkroom.css";
import CodevPairing from "./CodevPairing";

type Props = { installation: Installation; active: boolean; handoff: CodevHandoff | null; onRightDrawerSectionsChange: (sections: DrawerSection[]) => void };
type Tab = "conversation" | "file" | "review" | "checks" | "receipts";
const tabs: Array<[Tab, string]> = [["conversation", "Conversation"], ["file", "File"], ["review", "Review"], ["checks", "Checks"], ["receipts", "Receipts"]];
const shortHash = (value?: string | null) => value ? value.slice(0, 12) : "Not captured";
const errorText = (error: unknown) => error instanceof Error ? error.message : "The operation could not complete.";

export default function CodevWorkroom({ installation, active, handoff, onRightDrawerSectionsChange }: Props) {
  const [actor, setActor] = useState<Actor | null>(null);
  const actorPromise = useRef<Promise<{ actor: Actor }> | null>(null);
  const mounted = useRef(true);
  const [workspace, setWorkspace] = useState<WorkspaceDescriptor | null>(null);
  const workspaceRef = useRef(workspace);
  const workspaceClient = useRef<string | null>(null);
  workspaceRef.current = workspace;
  const [files, setFiles] = useState<Array<{ path: string; size_bytes: number }>>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [buffers, setBuffers] = useState<Record<string, string>>({});
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [activeFile, setActiveFile] = useState("");
  const [writeScope, setWriteScope] = useState(false);
  const [commandScope, setCommandScope] = useState(false);
  const [grant, setGrant] = useState<WorkspaceGrant | null>(null);
  const [tab, setTab] = useState<Tab>("conversation");
  const [plan, setPlan] = useState<ChangePlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [gear, setGear] = useState("standard");
  const [sharedHandoff, setSharedHandoff] = useState<CodevHandoff | null>(null);
  const [chatting, setChatting] = useState<string | null>(null);
  const [messages, setMessages] = useState<Array<{ role: string; text: string; trace?: ChatResult }>>([]);
  const [receipts, setReceipts] = useState<OperationReceipt[]>([]);
  const [catalog, setCatalog] = useState<CommandCatalog | null>(null);
  const [run, setRun] = useState<CommandResult | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const currentFile = workspace?.files?.find(file => file.path === activeFile);
  const dirtyPaths = Object.keys(buffers).filter(path => buffers[path] !== workspace?.files?.find(file => file.path === path)?.text);
  const grantActive = !!grant && !grant.revoked && new Date(grant.expires_at).getTime() > now;
  const allowed = grantActive ? grant?.scopes ?? [] : [];
  const planExpired = !!plan && new Date(plan.expires_at).getTime() <= now;

  useEffect(() => {
    mounted.current = true;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { mounted.current = false; window.clearInterval(timer); };
  }, []);
  useEffect(() => {
    let current = true;
    setActor(null); setGrant(null); setPlan(null);
    if (workspaceRef.current) setNotice("The Codev session changed. Choose the repository again before granting access. Existing unsaved buffers are retained.");
    if (!installation.usable) { actorPromise.current = null; return; }
    actorPromise.current = codevRequest<{ actor: Actor }>("session", {});
    void actorPromise.current.then(result => {
      if (current && mounted.current) { setActor(result.actor); setError(""); }
    }).catch(reason => { if (current && mounted.current) setError(errorText(reason)); });
    return () => { current = false; };
  }, [installation.usable, installation.runtime_instance_id, installation.installation_id]);
  useEffect(() => { if (handoff) { setSharedHandoff(handoff); setMessage(handoff.instruction); setTab("conversation"); } }, [handoff]);

  const call = useCallback(<T,>(path: string, body: object = {}) => {
    if (!actor) return Promise.reject(new Error("The local Codev session is not ready."));
    return codevRequest<T>(path, { client_id: actor.client_id, ...body });
  }, [actor]);
  useEffect(() => { if (actor) void call<{ catalog: CommandCatalog }>("commands/catalog").then(result => { if (mounted.current) setCatalog(result.catalog); }).catch(() => {}); }, [actor, call]);

  const remember = useCallback((receipt: OperationReceipt) => {
    setReceipts(previous => [receipt, ...previous.filter(item => item.operation_id !== receipt.operation_id)].slice(0, 40));
  }, []);
  useEffect(() => {
    if (!running || !workspace) return;
    let stopped = false;
    const poll = async () => {
      try {
        const result = await call<CommandResult>("commands/status", { workspace_id: workspace.workspace_id, run_id: running });
        if (stopped) return;
        setRun(result);
        if (result.receipt) { remember(result.receipt); setRunning(null); }
        else if (result.state.status === "not_found") { setRunning(null); setError("This run is no longer available in the local session."); }
      } catch (reason) { if (!stopped) { setError(errorText(reason)); setRunning(null); } }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 700);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [running, workspace, call, remember]);

  useEffect(() => {
    if (!active) return;
    const latest = receipts[0];
    onRightDrawerSectionsChange([
      { key: "codev_context", title: "Development Context", state: workspace ? "live" : "inactive", accent: "teal", rows: [
        { label: "Workspace", value: workspace?.label ?? "No repository selected" },
        { label: "Shared files", value: String(grantActive ? grant?.files?.length ?? 0 : 0) },
        { label: "Revision", value: workspace ? `${workspace.current_revision} · ${shortHash(workspace.content_hash)}` : "No snapshot" },
        { label: "Memory", value: "Selected development context only" }] },
      { key: "codev_authority", title: "Codev Authority", state: grantActive ? "live" : "inactive", accent: "warm", rows: [
        { label: "Files", value: allowed.includes("read") ? "Selected files only" : "No content grant" },
        { label: "Write", value: allowed.includes("apply") ? "Exact review and approval required" : "Not granted" },
        { label: "Commands", value: allowed.includes("command") ? "Fixed Git check, separately approved" : "Not granted" },
        { label: "Git mutation", value: "Not granted" },
        { label: "Network", value: "Not granted" },
        { label: "Grant expiry", value: grantActive && grant ? new Date(grant.expires_at).toLocaleTimeString() : "No active grant" }] },
      { key: "codev_trace", title: "Request Trace", state: chatting || running ? "live" : latest ? latest.status === "completed" ? "live" : "degraded" : "inactive", rows: [
        { label: "State", value: chatting ? "Local reasoning in progress" : running ? "Repository check in progress" : latest?.status ?? "Idle" },
        { label: "Request", value: chatting ?? running ?? latest?.request_id ?? "No request yet" },
        { label: "Verification", value: latest?.verification?.replaceAll("_", " ") ?? "Not run" },
        { label: "Tests", value: latest?.tests_run?.join(", ") || "Not run" }] }
    ]);
  }, [active, workspace, grant, grantActive, chatting, running, receipts, onRightDrawerSectionsChange]);

  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (reason) { if (mounted.current) { setError(errorText(reason)); setPlan(null); } }
    finally { if (mounted.current) setBusy(false); }
  }
  function receiveSnapshot(next: WorkspaceDescriptor, clearEdits = false) {
    const previous = workspaceRef.current;
    if (!clearEdits) setConflicts(next.files?.filter(file => buffers[file.path] !== undefined && buffers[file.path] !== file.text && buffers[file.path] !== previous?.files?.find(old => old.path === file.path)?.text
      && file.content_hash !== previous?.files?.find(old => old.path === file.path)?.content_hash).map(file => file.path) ?? []);
    else { setBuffers({}); setConflicts([]); }
    setWorkspace(next); setPlan(null);
  }
  async function chooseRepository() {
    if (dirtyPaths.length || running || chatting) { setError("Finish the active request and explicitly discard or apply your edits before changing repositories."); return; }
    await perform(async () => {
      const chosen = await open({ directory: true, multiple: false, title: "Choose a Codev repository" });
      if (typeof chosen !== "string") return;
      const result = await call<{ workspace: WorkspaceDescriptor }>("workspaces/select", { root_path: chosen });
      if (workspace && workspaceClient.current === actor?.client_id) await call("grants/revoke", { workspace_id: workspace.workspace_id });
      workspaceClient.current = actor?.client_id ?? null;
      setWorkspace(result.workspace); setFiles([]); setSelected([]); setBuffers({}); setConflicts([]); setGrant(null);
      setPlan(null); setActiveFile(""); setWriteScope(false); setCommandScope(false); setRun(null);
      setNotice("Repository selected. No file list or contents have been shared.");
    });
  }
  async function inspectList() {
    if (!workspace) return;
    await perform(async () => {
      const result = await call<{ workspace: WorkspaceDescriptor; grant: WorkspaceGrant }>("grants/issue", { workspace_id: workspace.workspace_id,
        scopes: ["metadata"], files: [], command_ids: [], expected_epoch: workspace.grant_epoch ?? 0, explicitly_approved: true });
      setGrant(result.grant); receiveSnapshot(result.workspace);
      const tree = await call<{ files: typeof files; truncated: boolean }>("workspaces/tree", { workspace_id: workspace.workspace_id });
      setFiles(tree.files); setNotice(tree.truncated ? "The file list reached its safety limit. Select a smaller repository for a complete list." : "File names are visible. Select the contents you want to share.");
    });
  }
  async function shareSelected() {
    if (!workspace) return;
    if (dirtyPaths.some(path => !selected.includes(path))) { setError("Apply or explicitly discard edits before removing their file grants."); return; }
    await perform(async () => {
      const result = await call<{ workspace: WorkspaceDescriptor; grant: WorkspaceGrant }>("grants/issue", { workspace_id: workspace.workspace_id,
        scopes: ["metadata", "read", "propose", ...(writeScope ? ["apply"] : []), ...(commandScope ? ["command"] : [])], files: selected,
        command_ids: commandScope ? ["git_diff_check"] : [], expected_epoch: workspace.grant_epoch ?? 0, explicitly_approved: true });
      setGrant(result.grant); receiveSnapshot(result.workspace); setActiveFile(selected[0] ?? "");
      setNotice(`${selected.length} selected file${selected.length === 1 ? "" : "s"} shared for this session. Every write and command still requires an exact review.`);
    });
  }
  async function revoke() {
    if (!workspace) return;
    await perform(async () => {
      const result = await call<{ grant_epoch: number }>("grants/revoke", { workspace_id: workspace.workspace_id });
      setGrant(null); setPlan(null); setWorkspace({ ...workspace, grant_epoch: result.grant_epoch, allowed_operations: [] });
      setNotice("Workspace access revoked. Active operations have been asked to stop. Your unsaved editor buffers remain local.");
    });
  }
  async function refresh() {
    if (!workspace) return;
    await perform(async () => { const next = await call<{ workspace: WorkspaceDescriptor }>("workspaces/snapshot", { workspace_id: workspace.workspace_id }); receiveSnapshot(next.workspace); setNotice("Current source hashes refreshed. Unsaved edits are preserved."); });
  }
  async function reviewEdits() {
    if (!workspace || conflicts.length) return;
    await perform(async () => {
      const edits = Object.fromEntries(dirtyPaths.map(path => [path, buffers[path]]));
      const result = await call<{ plan: ChangePlan }>("patches/plan", { workspace_id: workspace.workspace_id, edits, revision: workspace.current_revision, summary: "Apply the reviewed workroom edits." });
      setPlan(result.plan); setTab("review");
    });
  }
  async function approvePlan() {
    if (!plan || !workspace) return;
    await perform(async () => {
      const result = await call<{ approval: ExactApproval; approval_token: string }>("approvals/issue", { plan_id: plan.plan_id, plan_hash: plan.plan_hash, explicitly_approved: true });
      const payload = { workspace_id: workspace.workspace_id, plan_id: plan.plan_id, approval_id: result.approval.approval_id, approval_token: result.approval_token };
      if (plan.command_id) {
        const started = await call<{ run_id: string }>("commands/start", payload);
        setRunning(started.run_id); setRun(null); setTab("checks"); setPlan(null);
      } else {
        const applied = await call<{ receipt: OperationReceipt }>("patches/apply", payload);
        remember(applied.receipt); setPlan(null); setTab("receipts");
        const next = await call<{ workspace: WorkspaceDescriptor }>("workspaces/snapshot", { workspace_id: workspace.workspace_id });
        // Preserve unsuccessful edits after a partial write. Successful bytes no longer count as dirty.
        receiveSnapshot(next.workspace);
      }
    });
  }
  async function send() {
    if (!message.trim() || chatting) return;
    const requestId = `codev_${crypto.randomUUID().replaceAll("-", "")}`;
    const instruction = message;
    setChatting(requestId); setError(""); setMessage("");
    setMessages(previous => [...previous, { role: "You", text: instruction }]);
    try {
      const result = await call<ChatResult>("chat", { workspace_id: allowed.includes("read") ? workspace?.workspace_id : null, message: instruction, request_id: requestId,
        requested_gear: gear, handoff: sharedHandoff ? JSON.stringify(sharedHandoff) : "" });
      if (mounted.current) { setMessages(previous => [...previous, { role: "Codev", text: result.response_text, trace: result }]); remember(result.receipt); }
    } catch (reason) { if (mounted.current) { setError(errorText(reason)); setMessage(instruction); } }
    finally { if (mounted.current) setChatting(null); }
  }

  return <div className="codev-room" hidden={!active}>
    <header className="codev-room-header"><div><span className="codev-eyebrow">LOCAL DEVELOPMENT</span><h1>Codev</h1><p>Understand, review, and change your selected workspace.</p></div><span className="codev-status">{installation.runtime_state === "ready" ? "Ready" : "Installed · service unavailable"} · v{installation.version ?? "1.0.0"}</span></header>
    {!installation.usable && <p className="codev-notice" role="status">{installation.note}</p>}
    <CodevPairing clientId={actor?.client_id ?? null}/>
    {(error || notice) && <div className={`codev-notice ${error ? "codev-error" : ""}`} role={error ? "alert" : "status"}>{error || notice}</div>}
    <div className="codev-layout">
      <aside className="codev-workspace" aria-label="Codev workspace permissions">
        <span className="codev-eyebrow">WORKSPACE</span><h2>{workspace?.label ?? "No workspace selected"}</h2>
        <button disabled={!actor || busy} onClick={() => void chooseRepository()}>{workspace ? "Change repository" : "Choose workspace"}</button>
        {!workspace && <p>Codev is installed. Choose a repository when you are ready. Choosing it shares no files.</p>}
        {workspace && <>
          <p className="codev-mono">Revision {workspace.current_revision} · {shortHash(workspace.content_hash)}</p>
          {!allowed.includes("metadata") && <button disabled={busy} onClick={() => void inspectList()}>Inspect file list</button>}
          {!!files.length && <><p id="codev-file-choice">Choose up to 40 files to share.</p><div className="codev-file-tree" role="group" aria-labelledby="codev-file-choice">
            {files.map(file => <label key={file.path} title={`${file.path} · ${file.size_bytes} bytes`}><input type="checkbox" disabled={busy || (!selected.includes(file.path) && selected.length >= 40)} checked={selected.includes(file.path)}
              onChange={event => setSelected(previous => event.target.checked ? [...previous, file.path] : previous.filter(path => path !== file.path))}/><span>{file.path}</span></label>)}
          </div>
          <label className="codev-check"><input type="checkbox" checked={writeScope} disabled={busy} onChange={event => setWriteScope(event.target.checked)}/>Allow exact approved writes</label>
          <label className="codev-check"><input type="checkbox" checked={commandScope} disabled={busy} onChange={event => setCommandScope(event.target.checked)}/>Allow the fixed Git check</label>
          <p className="codev-subtle">Permissions take effect when you press Share selected files.</p>
          <button className="codev-primary" disabled={busy || !selected.length} onClick={() => void shareSelected()}>Share selected files ({selected.length})</button></>}
          <div className="codev-authority-summary"><strong>{grantActive ? "Session access" : "No active access"}</strong><p>Write: {allowed.includes("apply") ? "exact approval" : "not granted"}<br/>Commands: {allowed.includes("command") ? "fixed check only" : "not granted"}<br/>Network: not granted</p></div>
          {grantActive && <div className="codev-actions"><button disabled={busy} onClick={() => void refresh()}>Refresh files</button><button onClick={() => void revoke()} disabled={busy}>Revoke access</button></div>}
          {!!dirtyPaths.length && <button disabled={busy} onClick={() => { setBuffers({}); setConflicts([]); setPlan(null); setNotice("Unsaved edits discarded. Repository files were not changed."); }}>Discard {dirtyPaths.length} unsaved edit{dirtyPaths.length === 1 ? "" : "s"}</button>}
        </>}
      </aside>
      <section className="codev-workbench" aria-label="Codev development workbench">
        <div className="codev-tabs" role="tablist" aria-label="Development views">{tabs.map(([key, label]) => <button key={key} id={`codev-tab-${key}`} role="tab" tabIndex={tab === key ? 0 : -1} onKeyDown={event => {
          const index = tabs.findIndex(([value]) => value === key);
          const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
          if (next !== null) { event.preventDefault(); setTab(tabs[next][0]); document.getElementById(`codev-tab-${tabs[next][0]}`)?.focus(); }
        }} aria-selected={tab === key} aria-controls={`codev-panel-${key}`} onClick={() => setTab(key)}>{label}{key === "file" && dirtyPaths.length ? ` · ${dirtyPaths.length}` : ""}</button>)}</div>
        <div className="codev-panel" id={`codev-panel-${tab}`} role="tabpanel" aria-labelledby={`codev-tab-${tab}`}>
          {tab === "conversation" && <div className="codev-conversation">
            {sharedHandoff && <details className="codev-handoff"><summary>Context shared from Conversations</summary><p>{sharedHandoff.instruction}</p><small>Conversation: {sharedHandoff.conversationId ?? "unsaved"} · Request: {sharedHandoff.requestId ?? "not sent"}</small><button onClick={() => setSharedHandoff(null)}>Remove shared context</button></details>}
            <div className="codev-messages" aria-live="polite">
              {!messages.length && <div className="codev-empty"><span className="codev-mark" aria-hidden="true">{ "{ }" }</span><h2>Make the next change clear.</h2><p>Ask a coding question, or share selected files for focused local reasoning. Suggestions require your review before they become edits.</p><p className="codev-subtle">Personal memory and network access are outside this workspace.</p></div>}
              {messages.map((item, index) => <article className={`codev-message ${item.role === "You" ? "codev-user" : ""}`} key={index}><strong>{item.role}</strong><p>{item.text}</p>{item.trace && <details><summary>{item.trace.receipt.status} · {item.trace.model_tag ?? "No model result"} · request trace</summary><pre>{JSON.stringify({ request: item.trace.receipt.request_id, model: item.trace.model_tag, role: item.trace.model_role, context: item.trace.context_receipt, governor: item.trace.governor }, null, 2)}</pre></details>}</article>)}
              {chatting && <p role="status">Local reasoning is in progress…</p>}
            </div>
            <form className="codev-composer" onSubmit={event => { event.preventDefault(); void send(); }}><label htmlFor="codev-message">Instruction</label><textarea id="codev-message" maxLength={16000} value={message} disabled={!actor || !!chatting} onChange={event => setMessage(event.target.value)} placeholder="Explain this code, investigate a failure, or plan a change…" rows={3}/>
              <div className="codev-actions"><label>Reasoning <select aria-label="Reasoning gear" value={gear} disabled={!!chatting} onChange={event => setGear(event.target.value)}>{["automatic", "quick", "standard", "deep", "deliberative", "research_engineering"].map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label>{chatting ? <button type="button" onClick={() => void call("chat/cancel", { request_id: chatting }).then(() => setNotice("Cancellation requested; waiting for the local runtime to stop.")).catch(reason => setError(errorText(reason)))}>Stop request</button> : <button className="codev-primary" disabled={!actor || !message.trim()}>Ask Codev</button>}</div>
            </form>
          </div>}
          {tab === "file" && <div className="codev-file-view"><label>Shared file <select aria-label="Shared file" value={activeFile} onChange={event => setActiveFile(event.target.value)}><option value="">Select a shared file</option>{workspace?.files?.map(file => <option key={file.path} value={file.path}>{file.path}</option>)}</select></label>
            {currentFile ? <><p className="codev-subtle">{currentFile.size_bytes} bytes · source {shortHash(currentFile.content_hash)} · {buffers[activeFile] !== undefined && buffers[activeFile] !== currentFile.text ? "Unsaved edit" : "Source snapshot"}</p>
              {currentFile.text != null ? <textarea className="codev-editor" aria-label={`Edit ${activeFile}`} spellCheck={false} value={buffers[activeFile] ?? currentFile.text} disabled={busy || !allowed.includes("propose")} onChange={event => { setBuffers(previous => ({ ...previous, [activeFile]: event.target.value })); setPlan(null); }}/>
                : <p>This file is {currentFile.availability.replaceAll("_", " ")}. Its contents are unavailable for editing.</p>}
              {!!conflicts.length && <div role="alert" className="codev-notice codev-error">Source changed while your edits were open: {conflicts.join(", ")}. Your edits are preserved.<button onClick={() => { setConflicts([]); setNotice("The next review will compare your edits with the newly refreshed source."); }}>Review against the refreshed source</button></div>}
              <button className="codev-primary" disabled={busy || !dirtyPaths.length || !!conflicts.length || !allowed.includes("propose")} onClick={() => void reviewEdits()}>Review {dirtyPaths.length || ""} edit{dirtyPaths.length === 1 ? "" : "s"}</button></>
              : <div className="codev-empty"><h2>Read only what you share.</h2><p>Choose files in the workspace panel and press Share selected files to inspect their contents.</p></div>}
          </div>}
          {tab === "review" && (plan ? <div className="codev-review"><span className="codev-eyebrow">EXACT APPROVAL</span><h2>{plan.summary}</h2><p>Repository: {plan.cwd_label} · revision {plan.base_revision}<br/>Network: none · expires {new Date(plan.expires_at).toLocaleTimeString()}</p>
            {plan.command_id && <pre>{plan.command_argv?.join(" ")}</pre>}
            {plan.changes?.map(change => <div key={change.path}><h3>{change.path}</h3><p className="codev-mono">{shortHash(change.base_hash)} → {shortHash(change.new_hash)}</p><pre className="codev-diff">{change.diff.split("\n").map((line, index) => <span key={index} className={line.startsWith("+") ? "codev-add" : line.startsWith("-") ? "codev-remove" : ""}>{line}{"\n"}</span>)}</pre></div>)}
            <p>{plan.recovery_note}</p><ul>{plan.expected_checks?.map(check => <li key={check}>{check}</li>)}</ul><p className="codev-subtle">{plan.risks?.join(" ")}</p>
            <p>Plan: <code>{shortHash(plan.plan_hash)}</code>. Approval is one use and becomes invalid if the source or grant changes.</p>
            {planExpired && <p role="alert">This plan expired. Create a fresh review.</p>}
            {!plan.command_id && !allowed.includes("apply") && <p>Write permission is not granted. Explicitly grant reviewed writes, then create a new plan.</p>}
            <div className="codev-actions"><button className="codev-primary" disabled={busy || planExpired || !allowed.includes(plan.command_id ? "command" : "apply")} onClick={() => void approvePlan()}>{busy ? "Applying approval…" : plan.command_id ? "Approve and run this check" : "Approve and apply this diff"}</button><button disabled={busy} onClick={() => setPlan(null)}>Reject plan</button></div>
          </div> : <div className="codev-empty"><h2>Review before anything runs.</h2><p>Edit a shared file or select a repository check. Its exact changes, source hashes, and recovery details will appear here.</p></div>)}
          {tab === "checks" && <div><h2>Repository checks</h2><p>Each available check has fixed arguments, bounded output, and a separate approval.</p>{catalog?.entries.map(entry => <article className="codev-check-card" key={entry.command_id}><strong>{entry.label}</strong><p>{entry.purpose}</p><code>{entry.command.join(" ")}</code>{!entry.execution_enabled && <p className="codev-subtle">{entry.disabled_reason ?? "This worker is unavailable."}</p>}<button disabled={!workspace || busy || !!running || !entry.execution_enabled || !allowed.includes("command") || entry.command_id !== "git_diff_check"} onClick={() => void perform(async () => { const result = await call<{ plan: ChangePlan }>("commands/plan", { workspace_id: workspace!.workspace_id, command_id: entry.command_id }); setPlan(result.plan); setTab("review"); })}>Review check</button></article>)}
            {running && <button onClick={() => void call("commands/cancel", { workspace_id: workspace?.workspace_id, run_id: running }).then(() => setNotice("Cancellation requested; waiting for the process result.")).catch(reason => setError(errorText(reason)))}>Stop running check</button>}
            {run && <article className="codev-check-card"><h3>{run.state.status}</h3><p>Exit code: {run.result?.exit_code ?? "Not available yet"}</p><pre>{run.result?.stdout_preview || run.result?.stderr_preview || "No output captured."}</pre></article>}
          </div>}
          {tab === "receipts" && <div><h2>What actually happened</h2>{!receipts.length && <p>Completed actions and blocked attempts will appear here with their verification and recovery details.</p>}{receipts.map(receipt => <article className="codev-receipt" key={receipt.operation_id}><span className="codev-status">{receipt.status}</span><h3>{receipt.summary}</h3><p>{new Date(receipt.created_at).toLocaleString()}</p><dl><dt>Files inspected</dt><dd>{receipt.files_inspected?.join(", ") || "None"}</dd><dt>Files changed</dt><dd>{receipt.files_changed?.join(", ") || "None"}</dd><dt>Commands run</dt><dd>{receipt.commands_run?.map(command => command.join(" ")).join("; ") || "None"}</dd><dt>Tests run</dt><dd>{receipt.tests_run?.join(", ") || "None"}</dd><dt>Network used</dt><dd>{receipt.network_used ? "Yes" : "No"}</dd><dt>Verification</dt><dd>{receipt.verification?.replaceAll("_", " ") ?? "Not run"}</dd><dt>Audit written</dt><dd>{receipt.audit_written ? "Yes" : "No"}</dd></dl>{receipt.artifacts?.map(artifact => <p key={artifact.artifact_id}>{artifact.label}<br/><code>{artifact.relative_path}</code></p>)}{receipt.recovery_note && <p>{receipt.recovery_note}</p>}{receipt.warnings?.map((warning, index) => <p className="codev-error" key={index}>{warning}</p>)}<details><summary>Request identifiers</summary><p className="codev-mono">{receipt.request_id}<br/>{receipt.operation_id}</p></details></article>)}</div>}
        </div>
      </section>
    </div>
  </div>;
}

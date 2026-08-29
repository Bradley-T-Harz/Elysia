import { useEffect, useMemo, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import {
  deleteAccountProfilePhoto,
  deleteCurrentAccount,
  createAccount,
  decideMemoryCandidate,
  fetchAccountProfile,
  fetchMemoryItems,
  exportAccountProfileArchive,
  getAccountProfilePhotoPreviewUrl,
  selectAccountProfilePhoto,
  restoreAccountProfileArchive,
  updateAccountProfile,
  type AccountColorOption,
  type AccountProfilePrivate,
  type AccountProfileUpdateRequest
} from "./api/bridgeClient";
import { openLocalProfilePhotoFile } from "./api/localFilePicker";
import { useAccountSession } from "./AccountGate";
import BirthdateField from "./BirthdateField";
import MarketplaceLinkPanel from "./MarketplaceLinkPanel";
import MarketplaceProfileSyncPanel from "./MarketplaceProfileSyncPanel";
import {
  accountPalette,
  colorForId,
  combineCityState,
  joinListInput,
  readEnvelopeError,
  splitCityState,
  splitListInput
} from "./accountPresentation";

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return window.btoa(binary);
}

export default function UserProfilePage() {
  const { colors, refreshAccountState, logout, state: accountState } = useAccountSession();
  const [profile, setProfile] = useState<AccountProfilePrivate | null>(null);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadProfile() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAccountProfile();
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        setProfile(null);
        return;
      }
      setProfile(result.payload.data?.profile ?? null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProfile();
  }, []);

  const selectedColor = useMemo(
    () => colorForId(colors, profile?.profile_color_id),
    [colors, profile?.profile_color_id]
  );

  async function handleSave(update: AccountProfileUpdateRequest) {
    setSaving(true);
    setError(null);
    try {
      const result = await updateAccountProfile(update);
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      setProfile(result.payload.data?.profile ?? null);
      setEditing(false);
      await refreshAccountState();
    } finally {
      setSaving(false);
    }
  }

  async function choosePhoto() {
    const selected = await openLocalProfilePhotoFile();
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const result = await selectAccountProfilePhoto(selected);
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      await loadProfile();
    } finally {
      setSaving(false);
    }
  }

  async function deletePhoto() {
    setSaving(true);
    setError(null);
    try {
      const result = await deleteAccountProfilePhoto();
      if (!result.ok || result.payload.status !== "ok") {
        setError(readEnvelopeError(result.payload));
        return;
      }
      await loadProfile();
    } finally {
      setSaving(false);
    }
  }

  async function addLocalAccount() {
    const username = window.prompt("New local account username:");
    if (!username?.trim()) return;
    const password = window.prompt("New local account password:");
    if (!password) return;
    setSaving(true);
    const result = await createAccount({ username: username.trim(), password });
    if (!result.ok || result.payload.status !== "ok") {
      setError(readEnvelopeError(result.payload));
    } else {
      await refreshAccountState();
      await loadProfile();
    }
    setSaving(false);
  }

  async function deleteLocalAccount() {
    if (!profile) return;
    const confirmation = window.prompt(
      `This permanently removes only this local Identity after verifying that it owns no Memory, Project, Conversation, or shared-space records. Type the username exactly to continue:\n\n${profile.username}`
    );
    if (!confirmation || confirmation !== profile.username) return;
    const password = window.prompt("Enter the current local account password to authorize deletion:");
    if (!password) return;
    setSaving(true);
    setError(null);
    try {
      const result = await deleteCurrentAccount({
        current_password: password,
        confirmation_username: confirmation
      });
      if (!result.ok || result.payload.status !== "ok" || !result.payload.data?.deleted) {
        setError(readEnvelopeError(result.payload));
        return;
      }
      setProfile(null);
      await refreshAccountState();
    } finally {
      setSaving(false);
    }
  }

  async function exportLocalProfile() {
    const currentPassword = window.prompt("Enter the current local account password:");
    if (!currentPassword) return;
    const recovery = window.prompt("Choose recovery material of at least 12 characters. Keep it separately; Elysia cannot recover it.");
    if (!recovery || recovery.length < 12) return;
    const repeated = window.prompt("Repeat the profile archive recovery material:");
    if (repeated !== recovery) {
      setError("The profile archive recovery material did not match.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await exportAccountProfileArchive(currentPassword, recovery);
      const archive = result.payload.data?.archive;
      if (!result.ok || result.payload.status !== "ok" || !archive?.archive_base64) {
        setError(readEnvelopeError(result.payload));
        return;
      }
      const raw = window.atob(archive.archive_base64);
      const bytes = Uint8Array.from(raw, (character) => character.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.elysia.profile-archive" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "elysia-local-profile.elysia-profile-archive";
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setSaving(false);
    }
  }

  async function restoreLocalProfile(file: File) {
    const currentPassword = window.prompt("Enter the current local account password:");
    if (!currentPassword) return;
    const recovery = window.prompt("Enter the profile archive recovery material:");
    if (!recovery || recovery.length < 12) return;
    if (!window.confirm("Restore private profile fields and the Identity photo into this authenticated local account? Username, password, role, Admin authority, Memory, Projects, and Conversations are not changed.")) return;
    setSaving(true);
    setError(null);
    try {
      const archiveBase64 = bytesToBase64(new Uint8Array(await file.arrayBuffer()));
      const result = await restoreAccountProfileArchive(archiveBase64, currentPassword, recovery);
      if (!result.ok || result.payload.status !== "ok" || !result.payload.data?.restored) {
        setError(readEnvelopeError(result.payload));
        return;
      }
      setProfile(result.payload.data.profile ?? null);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <ProfileShell color={selectedColor} title="Loading identity" />;
  }

  if (!profile) {
    return (
      <ProfileShell color={selectedColor} title="Personal Identity unavailable">
        {error && <div style={errorStyle}>{error}</div>}
        <button type="button" onClick={() => void loadProfile()} style={secondaryButtonStyle}>
          Reload identity
        </button>
      </ProfileShell>
    );
  }

  return (
    <ProfileShell
      color={selectedColor}
      title="Personal Identity"
      subtitle="Sealed local identity and private user portfolio. Private fields stay local; Elysia only receives the explicit runtime-safe projection."
    >
      {error && <div style={errorStyle}>{error}</div>}

      {editing ? (
        <ProfileEditor
          profile={profile}
          colors={colors}
          saving={saving}
          onCancel={() => setEditing(false)}
          onSave={handleSave}
        />
      ) : (
        <div style={{ display: "grid", gap: "1rem" }}>
          <div className="elysia-profile-header" style={profileHeaderStyle}>
            <ProfileAvatar profile={profile} color={selectedColor} />
            <div style={{ display: "grid", gap: "0.42rem", minWidth: 0 }}>
              <div style={eyebrowStyle}>Authenticated local identity</div>
              <h2 style={{ margin: 0, fontSize: "1.65rem", overflowWrap: "anywhere" }}>
                {profile.username || "Unnamed user"}
              </h2>
              <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", flexWrap: "wrap" }}>
                <span
                  aria-hidden="true"
                  style={{
                    width: "0.88rem",
                    height: "0.88rem",
                    borderRadius: "999px",
                    background: selectedColor.hex,
                    boxShadow: `0 0 14px ${selectedColor.hex}`
                  }}
                />
                <span style={{ color: accountPalette.silverMuted }}>
                  {profile.profile_photo_available ? "Identity photo copied into sealed local storage" : "No identity photo set"}
                </span>
                <span style={{ color: accountPalette.silverMuted }}>
                  {accountState?.account_count ?? 1} local account{accountState?.account_count === 1 ? "" : "s"} · active ID {accountState?.active_user_id ?? "not surfaced"}
                </span>
              </div>
            </div>
            <div className="elysia-profile-actions" style={headerActionStyle}>
              <button type="button" onClick={() => setEditing(true)} style={primaryButtonStyle}>
                Edit Profile
              </button>
              <button type="button" onClick={choosePhoto} disabled={saving} style={secondaryButtonStyle}>
                Choose Identity Photo
              </button>
              {profile.profile_photo_available && (
                <button type="button" onClick={deletePhoto} disabled={saving} style={secondaryButtonStyle}>
                  Remove Identity Photo
                </button>
              )}
              <button type="button" onClick={() => void addLocalAccount()} disabled={saving} style={secondaryButtonStyle}>
                Add Local Account
              </button>
              <button type="button" onClick={() => void logout()} disabled={saving} style={secondaryButtonStyle}>
                Switch Account
              </button>
            </div>
          </div>

          <LongTextPanel
            label="Interests"
            value={profile.interests}
            maxHeight="10rem"
          />

          <LongTextPanel
            label="Story"
            value={profile.bio}
            maxHeight="16rem"
          />

          <ProjectionPanel profile={profile} />

          <IdentityProposalPanel />

          <section style={{ display: "grid", gap: "0.75rem" }}>
            <div style={{ ...eyebrowStyle, color: accountPalette.sandstone }}>
              Private details
            </div>
            <div style={privateDetailsGridStyle}>
            <Info label="Birthdate" value={profile.birthdate} />
            <Info label="Emails" value={(profile.emails ?? []).join(", ")} />
            <Info label="Phone Number" value={profile.phone_number} />
            <Info label="Social Media" value={(profile.social_media ?? []).join(", ")} />
            <Info label="GitHub" value={profile.github} />
            <Info label="City / State" value={profile.city_state} />
            <Info label="Profile Color" value="Selected identity color" />
            <Info label="Identity Photo Asset Reference" value={profile.profile_photo_asset_id} />
            </div>
          </section>

          <SealedBoundaryPanel />

          <MarketplaceLinkPanel />
          <MarketplaceProfileSyncPanel profile={profile} />

          <section style={dangerZoneStyle} aria-labelledby="local-profile-recovery-heading">
            <div>
              <div id="local-profile-recovery-heading" style={eyebrowStyle}>Private profile export and recovery</div>
              <p style={{ margin: "0.4rem 0 0", color: accountPalette.silverMuted, lineHeight: 1.55 }}>
                The encrypted profile archive preserves private profile fields and the Identity photo only.
                It never carries a password, role, Admin authority, Memory, Projects, or Conversations;
                use Memory's encrypted portable archive separately for autobiographical memory.
              </p>
            </div>
            <div style={headerActionStyle}>
              <button type="button" onClick={() => void exportLocalProfile()} disabled={saving} style={secondaryButtonStyle}>Export encrypted profile</button>
              <label style={{ ...secondaryButtonStyle, cursor: saving ? "default" : "pointer" }}>
                Restore encrypted profile
                <input
                  type="file"
                  aria-label="Select Elysia local profile archive"
                  accept=".elysia-profile-archive,application/vnd.elysia.profile-archive"
                  disabled={saving}
                  style={{ display: "none" }}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void restoreLocalProfile(file);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
            </div>
          </section>

          <section style={dangerZoneStyle} aria-labelledby="local-account-deletion-heading">
            <div>
              <div id="local-account-deletion-heading" style={{ ...eyebrowStyle, color: "#f2a7a7" }}>
                Local Identity deletion
              </div>
              <p style={{ margin: "0.4rem 0 0", color: accountPalette.silverMuted, lineHeight: 1.55 }}>
                Deletion requires your current password and exact username. It fails closed while this
                account owns Memory, Project, Conversation, or shared-space records.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void deleteLocalAccount()}
              disabled={saving}
              style={dangerButtonStyle}
            >
              Delete This Local Account
            </button>
          </section>
        </div>
      )}
    </ProfileShell>
  );
}

const dangerZoneStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "1rem",
  flexWrap: "wrap",
  padding: "1rem",
  borderRadius: "14px",
  border: "1px solid rgba(220, 100, 100, 0.48)",
  background: "rgba(90, 24, 24, 0.16)"
};

const dangerButtonStyle: CSSProperties = {
  border: "1px solid rgba(238, 116, 116, 0.75)",
  borderRadius: "12px",
  padding: "0.72rem 0.9rem",
  background: accountPalette.panelSoft,
  borderColor: "rgba(238, 116, 116, 0.75)",
  color: "#ffd0d0",
  cursor: "pointer"
};

function ProfileShell({
  children,
  color,
  title,
  subtitle
}: {
  children?: ReactNode;
  color: AccountColorOption;
  title: string;
  subtitle?: string;
}) {
  return (
    <div style={{ minHeight: 0, height: "100%", overflowY: "auto", padding: "0.2rem" }}>
      <div
        style={{
          display: "grid",
          gap: "1rem",
          minHeight: "100%",
          padding: "1rem",
          borderRadius: "20px",
          border: `1px solid ${color.hex}`,
          background:
            `radial-gradient(circle at 12% 8%, ${color.hex}26, transparent 25%), ` +
            "linear-gradient(180deg, rgba(18, 25, 37, 0.94) 0%, rgba(11, 14, 18, 0.96) 100%)",
          boxShadow: `0 0 32px ${color.hex}22, inset 0 1px 0 rgba(255,255,255,0.04)`
        }}
      >
        <header>
          <div style={{ ...eyebrowStyle, color: color.hex }}>Sealed Local Identity</div>
          <h1 style={{ margin: 0, fontSize: "2rem" }}>{title}</h1>
          {subtitle && <p style={{ color: accountPalette.silverMuted, lineHeight: 1.56 }}>{subtitle}</p>}
        </header>
        {children}
      </div>
    </div>
  );
}

function ProfileEditor({
  profile,
  colors,
  saving,
  onCancel,
  onSave
}: {
  profile: AccountProfilePrivate;
  colors: AccountColorOption[];
  saving: boolean;
  onCancel: () => void;
  onSave: (update: AccountProfileUpdateRequest) => Promise<void>;
}) {
  const cityState = splitCityState(profile.city_state);
  const [username, setUsername] = useState(profile.username ?? "");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [interests, setInterests] = useState(profile.interests ?? "");
  const [bio, setBio] = useState(profile.bio ?? "");
  const [birthdate, setBirthdate] = useState(profile.birthdate ?? "");
  const [emails, setEmails] = useState(joinListInput(profile.emails));
  const [phoneNumber, setPhoneNumber] = useState(profile.phone_number ?? "");
  const [socialMedia, setSocialMedia] = useState(joinListInput(profile.social_media));
  const [github, setGithub] = useState(profile.github ?? "");
  const [city, setCity] = useState(cityState.city);
  const [state, setState] = useState(cityState.state);
  const [profileColorId, setProfileColorId] = useState(
    profile.profile_color_id ?? colors[0]?.id ?? "meteor_rose"
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave({
      username,
      password: password || null,
      current_password: password ? currentPassword : null,
      interests,
      bio,
      birthdate: birthdate || null,
      emails: splitListInput(emails),
      phone_number: phoneNumber || null,
      social_media: splitListInput(socialMedia),
      github: github || null,
      city_state: combineCityState(city, state),
      profile_color_id: profileColorId
    });
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "1rem" }}>
      <div style={gridStyle}>
        <Field label="Username"><input value={username} onChange={(event) => setUsername(event.target.value)} required style={inputStyle} /></Field>
        <Field label="Password"><input value={password} onChange={(event) => setPassword(event.target.value)} type="password" placeholder="Leave blank to keep current password" style={inputStyle} /></Field>
        {password ? <Field label="Current Password"><input value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} type="password" required autoComplete="current-password" style={inputStyle} /></Field> : null}
      </div>
      <Field label="Interests"><textarea value={interests} onChange={(event) => setInterests(event.target.value)} rows={3} style={textareaStyle} /></Field>
      <Field label="Story"><textarea value={bio} onChange={(event) => setBio(event.target.value)} rows={4} style={textareaStyle} /></Field>
      <div style={gridStyle}>
        <Field label="Birthdate"><BirthdateField value={birthdate} onChange={setBirthdate} inputStyle={inputStyle} /></Field>
        <Field label="Phone Number"><input value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} style={inputStyle} /></Field>
      </div>
      <div style={gridStyle}>
        <Field label="Emails"><textarea value={emails} onChange={(event) => setEmails(event.target.value)} rows={3} style={textareaStyle} /></Field>
        <Field label="Social Media"><textarea value={socialMedia} onChange={(event) => setSocialMedia(event.target.value)} rows={3} style={textareaStyle} /></Field>
      </div>
      <div style={gridStyle}>
        <Field label="GitHub"><input value={github} onChange={(event) => setGithub(event.target.value)} style={inputStyle} /></Field>
        <Field label="City"><input value={city} onChange={(event) => setCity(event.target.value)} style={inputStyle} /></Field>
        <Field label="State"><input value={state} onChange={(event) => setState(event.target.value)} style={inputStyle} /></Field>
      </div>
      <Field label="Profile Color">
        <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
          {colors.map((color) => (
            <button
              key={color.id}
              type="button"
              title={color.label}
              aria-pressed={color.id === profileColorId}
              onClick={() => setProfileColorId(color.id)}
              style={{
                width: "2rem",
                height: "2rem",
                borderRadius: "999px",
                border: color.id === profileColorId
                  ? `2px solid ${accountPalette.silver}`
                  : "1px solid rgba(199, 210, 218, 0.22)",
                background: color.hex,
                boxShadow: color.id === profileColorId ? `0 0 18px ${color.hex}` : "none",
                cursor: "pointer"
              }}
            />
          ))}
        </div>
      </Field>
      <div style={actionRowStyle}>
      <button type="submit" disabled={saving} style={primaryButtonStyle}>
          {saving ? "Saving..." : "Save Identity"}
        </button>
        <button type="button" onClick={onCancel} disabled={saving} style={secondaryButtonStyle}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label style={{ display: "grid", gap: "0.36rem" }}><span style={{ fontWeight: 700 }}>{label}</span>{children}</label>;
}

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div style={infoStyle}>
      <div style={eyebrowStyle}>{label}</div>
      <div style={{ color: value ? accountPalette.silver : accountPalette.silverMuted, overflowWrap: "anywhere" }}>
        {value || "Not set"}
      </div>
    </div>
  );
}

function ProjectionPanel({ profile }: { profile: AccountProfilePrivate }) {
  return (
    <section style={longTextPanelStyle}>
      <div style={eyebrowStyle}>What Elysia may use</div>
      <p style={{ margin: "0.42rem 0 0.75rem", color: accountPalette.silverMuted, lineHeight: 1.55 }}>
        This is the Elysia-visible identity projection. It points to approved local identity fields Elysia may use without exposing sealed private details.
      </p>
      <div style={projectionStackStyle}>
        <ProjectionInfo label="Name Elysia may use" value={profile.username || "Not set"} />
        <ProjectionInfo label="Interests" value={profile.interests?.trim() ? "Available from the Interests section above." : "Not set"} />
        <ProjectionInfo label="Story" value={profile.bio?.trim() ? "Available from the Story section above through the Elysia-visible projection." : "Not set"} />
        <ProjectionInfo label="Identity photo available" value={profile.profile_photo_available ? "Yes" : "No"} />
      </div>
    </section>
  );
}

function IdentityProposalPanel() {
  const [items, setItems] = useState<Array<{ memory_id: string; title?: string | null; inference_kind?: string | null }>>([]);
  const [message, setMessage] = useState("Loading proposed identity memories…");

  async function load() {
    const result = await fetchMemoryItems({ status: "provisional", limit: 50 });
    if (!result.ok) {
      setMessage(result.payload.errors?.[0] ?? "Identity proposals are unavailable.");
      return;
    }
    const proposals = (result.payload.data?.items ?? []).filter((item) => Boolean(item.inference_kind));
    setItems(proposals);
    setMessage(proposals.length ? "Proposals remain unapproved until you decide." : "No pending identity proposals.");
  }

  useEffect(() => {
    void load();
  }, []);

  async function decide(memoryId: string, decision: "approve" | "reject") {
    const reason = window.prompt(`Reason to ${decision} this proposed identity memory:`) ?? "User reviewed identity proposal.";
    const result = await decideMemoryCandidate(memoryId, decision, reason);
    setMessage(result.ok ? `Proposal ${decision}d; approved identity and proposals remain distinct.` : result.payload.errors?.[0] ?? "Proposal review failed.");
    if (result.ok) await load();
  }

  return (
    <section style={longTextPanelStyle}>
      <div style={eyebrowStyle}>Proposed identity — not approved identity</div>
      <p style={{ color: accountPalette.silverMuted }}>{message}</p>
      <div style={{ display: "grid", gap: "0.55rem" }}>
        {items.map((item) => (
          <div key={item.memory_id} style={{ ...projectionRowStyle, display: "flex", justifyContent: "space-between", gap: "0.7rem", alignItems: "center" }}>
            <span>{item.title || "Untitled proposal"} <small style={{ color: accountPalette.silverMuted }}>({item.memory_id})</small></span>
            <span style={{ display: "flex", gap: "0.45rem" }}>
              <button type="button" style={secondaryButtonStyle} onClick={() => void decide(item.memory_id, "approve")}>Approve</button>
              <button type="button" style={secondaryButtonStyle} onClick={() => void decide(item.memory_id, "reject")}>Reject</button>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProjectionInfo({ label, value }: { label: string; value: string }) {
  return (
    <div style={projectionRowStyle}>
      <div style={eyebrowStyle}>{label}</div>
      <div style={{ color: value === "Not set" ? accountPalette.silverMuted : accountPalette.silver, overflowWrap: "anywhere" }}>
        {value}
      </div>
    </div>
  );
}

function SealedBoundaryPanel() {
  const sealedCategories = [
    "birthdate",
    "emails",
    "phone",
    "private social links",
    "GitHub unless explicitly allowed",
    "city/state unless explicitly allowed",
    "raw photo path",
    "tokens/session data",
    "vault/memory/logs/files"
  ];
  return (
    <section style={privacyNoteStyle}>
      <div style={{ ...eyebrowStyle, color: accountPalette.sandstone }}>What remains sealed</div>
      <p style={{ margin: "0.42rem 0 0.75rem" }}>
        Sealed private details remain local and are not sent to runtime, memory, traces, tools, workers, Marketplace, or Elysia Ecobotics Online.
      </p>
      <div style={sealedListStyle}>
        {sealedCategories.map((category) => <span key={category}>{category}</span>)}
      </div>
    </section>
  );
}

function LongTextPanel({
  label,
  value,
  maxHeight
}: {
  label: string;
  value?: string | null;
  maxHeight: string;
}) {
  const text = value?.trim();
  return (
    <section style={longTextPanelStyle}>
      <div style={eyebrowStyle}>{label}</div>
      <div
        style={{
          marginTop: "0.42rem",
          maxHeight,
          overflowY: "auto",
          whiteSpace: "pre-wrap",
          overflowWrap: "break-word",
          lineHeight: 1.62,
          color: text ? accountPalette.silver : accountPalette.silverMuted
        }}
      >
        {text || "Not set"}
      </div>
    </section>
  );
}

function ProfileAvatar({
  profile,
  color
}: {
  profile: AccountProfilePrivate;
  color: AccountColorOption;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const previewUrl = getAccountProfilePhotoPreviewUrl(profile.profile_photo_asset_id);
  const showImage = Boolean(profile.profile_photo_available && previewUrl && !imageFailed);
  return (
    <div
      className="elysia-profile-avatar"
      style={{
        width: "10rem",
        height: "13rem",
        borderRadius: "24px",
        border: `1px solid ${color.hex}`,
        background:
          `radial-gradient(circle at 35% 28%, ${color.hex}44, transparent 36%), ` +
          "linear-gradient(180deg, rgba(24, 33, 48, 0.84) 0%, rgba(11, 14, 18, 0.92) 100%)",
        boxShadow: `0 0 30px ${color.hex}24`,
        overflow: "hidden",
        display: "grid",
        placeItems: "center",
        flexShrink: 0
      }}
    >
      {showImage ? (
        <img
          src={previewUrl ?? undefined}
          alt="Local personal identity"
          onError={() => setImageFailed(true)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            display: "block"
          }}
        />
      ) : (
        <div
          aria-label="Identity photo placeholder"
          style={{
            width: "100%",
            height: "100%",
            display: "grid",
            placeItems: "center",
            color: color.hex,
            fontSize: "2.8rem",
            fontWeight: 900
          }}
        >
          {(profile.username || "E").slice(0, 1).toUpperCase()}
        </div>
      )}
    </div>
  );
}

const eyebrowStyle: CSSProperties = {
  fontSize: "0.7rem",
  letterSpacing: "0.11em",
  textTransform: "uppercase",
  color: accountPalette.sandstone
};

const gridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "0.85rem"
};

const profileHeaderStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(9rem, 10rem) minmax(0, 1fr) minmax(10rem, 12rem)",
  gap: "1.1rem",
  alignItems: "center",
  padding: "1rem",
  borderRadius: "18px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.34)"
};

const headerActionStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  justifyContent: "flex-end",
  alignItems: "stretch",
  gap: "0.58rem",
  minWidth: 0
};

const longTextPanelStyle: CSSProperties = {
  padding: "1rem",
  borderRadius: "16px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.36)",
  minWidth: 0
};

const privateDetailsGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
  gap: "0.75rem"
};

const projectionStackStyle: CSSProperties = {
  display: "grid",
  gap: "0.65rem"
};

const projectionRowStyle: CSSProperties = {
  padding: "0.85rem",
  borderRadius: "14px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.36)"
};

const infoStyle: CSSProperties = {
  padding: "0.85rem",
  borderRadius: "14px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: "rgba(11, 14, 18, 0.36)"
};

const inputStyle: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "12px",
  background: "rgba(11, 14, 18, 0.48)",
  color: accountPalette.silver,
  padding: "0.72rem 0.78rem",
  font: "inherit"
};

const textareaStyle: CSSProperties = { ...inputStyle, resize: "vertical" };

const actionRowStyle: CSSProperties = {
  display: "flex",
  gap: "0.7rem",
  flexWrap: "wrap",
  alignItems: "center"
};

const primaryButtonStyle: CSSProperties = {
  border: "1px solid rgba(126, 215, 209, 0.34)",
  borderRadius: "12px",
  padding: "0.72rem 0.9rem",
  background: "linear-gradient(180deg, rgba(16, 71, 75, 0.74) 0%, rgba(18, 25, 37, 0.88) 100%)",
  color: accountPalette.silver,
  cursor: "pointer",
  fontWeight: 800
};

const secondaryButtonStyle: CSSProperties = {
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "12px",
  padding: "0.72rem 0.9rem",
  background: accountPalette.panelSoft,
  color: accountPalette.silver,
  cursor: "pointer"
};

const errorStyle: CSSProperties = {
  color: accountPalette.danger,
  border: "1px solid rgba(216, 165, 165, 0.28)",
  borderRadius: "12px",
  padding: "0.75rem",
  background: "rgba(216, 165, 165, 0.08)"
};

const privacyNoteStyle: CSSProperties = {
  padding: "0.9rem",
  borderRadius: "14px",
  border: "1px dashed rgba(184, 162, 123, 0.34)",
  color: accountPalette.silverMuted,
  lineHeight: 1.55,
  background: "rgba(11, 14, 18, 0.32)"
};

const sealedListStyle: CSSProperties = {
  display: "flex",
  gap: "0.5rem",
  flexWrap: "wrap"
};

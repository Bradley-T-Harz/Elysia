import { useMemo, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import {
  createAccount,
  selectAccountProfilePhoto,
  type AccountColorOption,
  type AccountCreateRequest
} from "./api/bridgeClient";
import { openLocalProfilePhotoFile } from "./api/localFilePicker";
import {
  accountPalette,
  colorForId,
  readEnvelopeError
} from "./accountPresentation";

type UserCreatorPageProps = {
  colors: AccountColorOption[];
  onCreated: () => Promise<void>;
};

export default function UserCreatorPage({ colors, onCreated }: UserCreatorPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [ownerAcknowledged, setOwnerAcknowledged] = useState(false);
  const [profileColorId, setProfileColorId] = useState(colors[0]?.id ?? "meteor_rose");
  const [profilePhotoPath, setProfilePhotoPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const selectedColor = useMemo(
    () => colorForId(colors, profileColorId),
    [colors, profileColorId]
  );

  async function choosePhoto() {
    const selected = await openLocalProfilePhotoFile();
    if (selected) {
      setProfilePhotoPath(selected);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (password.length < 12) {
        setError("Use a local passphrase of at least 12 characters.");
        return;
      }
      if (password !== passwordConfirmation) {
        setError("The local passphrase confirmation does not match.");
        return;
      }
      if (!ownerAcknowledged) {
        setError("Confirm the Installation Owner responsibility before creating the first account.");
        return;
      }
      const payload: AccountCreateRequest = {
        username,
        password,
        profile_color_id: profileColorId
      };

      const createResult = await createAccount(payload);
      if (!createResult.ok || createResult.payload.status !== "ok") {
        setError(readEnvelopeError(createResult.payload));
        return;
      }

      if (profilePhotoPath) {
        const photoResult = await selectAccountProfilePhoto(profilePhotoPath);
        if (!photoResult.ok || photoResult.payload.status !== "ok") {
          setError(
            `Account was created, but the profile photo was not copied: ${readEnvelopeError(photoResult.payload)}`
          );
          await onCreated();
          return;
        }
      }

      await onCreated();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="elysia-account-setup-scroll"
      data-testid="personal-identity-scroll-region"
      style={{
        color: accountPalette.silver,
        background: "linear-gradient(180deg, #111726 0%, #0B0E12 100%)",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
      }}
    >
      <form
        className="elysia-account-setup-form"
        onSubmit={handleSubmit}
        style={{
          width: "min(980px, calc(100% - 2rem))",
          margin: "0 auto",
          display: "grid",
          gap: "1rem"
        }}
      >
        <header>
          <div style={eyebrowStyle}>Local Identity Setup</div>
          <h1 style={{ margin: 0, fontSize: "2rem" }}>Create your Personal Identity</h1>
          <p style={{ color: accountPalette.silverMuted, lineHeight: 1.56, maxWidth: "760px" }}>
            Create the local account and its encryption ownership first. Personal onboarding
            is a separate, optional step after this account exists; no biography or questionnaire
            answer is created by machine installation.
          </p>
          <p style={{ color: accountPalette.silverMuted, lineHeight: 1.56, maxWidth: "760px" }}>
            The first account becomes this installation&apos;s Owner and Local Admin. That role governs packages, safety ceilings, Internet, workers, and emergency controls; it is not authority to read another profile&apos;s conversations, files, questionnaire, Private memory, or Sealed memory. Your passphrase owns local encryption. Elysia has no hidden operator bypass, so keep it and any encrypted exports safely outside this machine.
          </p>
        </header>

        <section style={sectionStyle}>
          <div style={gridStyle}>
            <Field label="Username">
              <input value={username} onChange={(event) => setUsername(event.target.value)} required autoComplete="username" style={inputStyle} />
            </Field>
            <Field label="Password">
              <input value={password} onChange={(event) => setPassword(event.target.value)} required minLength={12} type="password" autoComplete="new-password" style={inputStyle} />
            </Field>
            <Field label="Password confirmation">
              <input value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} required minLength={12} type="password" autoComplete="new-password" style={inputStyle} />
            </Field>
          </div>

          <Field label="Identity Photo">
            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
              <button type="button" onClick={choosePhoto} style={secondaryButtonStyle}>
                Choose jpg, png, or webp
              </button>
              <span style={{ color: accountPalette.silverMuted }}>
                {profilePhotoPath ? "Image selected for sealed local copy." : "No image selected"}
              </span>
            </div>
          </Field>

          <Field label="Profile Color">
            <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap" }}>
              {colors.map((color) => {
                const selected = color.id === profileColorId;
                return (
                  <button
                    key={color.id}
                    type="button"
                    onClick={() => setProfileColorId(color.id)}
                    title={color.label}
                    aria-pressed={selected}
                    style={{
                      width: "2.1rem",
                      height: "2.1rem",
                      borderRadius: "999px",
                      border: selected
                        ? `2px solid ${accountPalette.silver}`
                        : "1px solid rgba(199, 210, 218, 0.22)",
                      background: color.hex,
                      boxShadow: selected ? `0 0 18px ${color.hex}` : "none",
                      cursor: "pointer"
                    }}
                  />
                );
              })}
              <span style={{ color: selectedColor.hex, fontWeight: 700 }}>
                {selectedColor.label}
              </span>
            </div>
          </Field>

          <label style={{ display: "flex", gap: ".6rem", alignItems: "flex-start", lineHeight: 1.5 }}>
            <input type="checkbox" required checked={ownerAcknowledged} onChange={(event) => setOwnerAcknowledged(event.target.checked)} />
            I understand that this first account becomes Installation Owner, that local/public identities remain separate, and that losing the passphrase can make encrypted private state unrecoverable without a separately protected export.
          </label>
        </section>

        {error && <div role="alert" style={errorStyle}>{error}</div>}

        <button type="submit" disabled={saving} style={primaryButtonStyle}>
          {saving ? "Creating sealed local identity..." : "Create Local Account"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "grid", gap: "0.36rem" }}>
      <span style={{ fontWeight: 700 }}>{label}</span>
      {children}
    </label>
  );
}

const eyebrowStyle: CSSProperties = {
  fontSize: "0.72rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: accountPalette.sandstone,
  marginBottom: "0.42rem"
};

const sectionStyle: CSSProperties = {
  display: "grid",
  gap: "1rem",
  padding: "1rem",
  borderRadius: "18px",
  border: `1px solid ${accountPalette.lineSilver}`,
  background: accountPalette.panel
};

const gridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "1rem"
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

const secondaryButtonStyle: CSSProperties = {
  border: `1px solid ${accountPalette.lineSilver}`,
  borderRadius: "12px",
  padding: "0.68rem 0.85rem",
  background: accountPalette.panelSoft,
  color: accountPalette.silver,
  cursor: "pointer"
};

const primaryButtonStyle: CSSProperties = {
  border: "1px solid rgba(126, 215, 209, 0.34)",
  borderRadius: "13px",
  padding: "0.86rem 1rem",
  background:
    "linear-gradient(180deg, rgba(16, 71, 75, 0.78) 0%, rgba(18, 25, 37, 0.92) 100%)",
  color: accountPalette.silver,
  fontWeight: 800,
  cursor: "pointer"
};

const errorStyle: CSSProperties = {
  color: accountPalette.danger,
  border: "1px solid rgba(216, 165, 165, 0.28)",
  borderRadius: "12px",
  padding: "0.75rem",
  background: "rgba(216, 165, 165, 0.08)"
};

import { useEffect, useMemo, useState } from "react";
import {
  fetchArtifactDetail,
  fetchArtifacts,
  type ArtifactDetailData,
  type ArtifactSummaryData
} from "./api/bridgeClient";
import ArtifactCard from "./ArtifactCard";
import PlotArtifactView from "./PlotArtifactView";
import type { DrawerSection } from "./RightDrawer";

type ArtifactsPageProps = {
  startupReady: boolean;
  onRightDrawerSectionsChange: (sections: DrawerSection[]) => void;
};

const palette = {
  bronze: "#8A6A3C",
  sandstone: "#B8A27B",
  teal: "#7ED7D1",
  emerald: "#2F8A68",
  silver: "#C7D2DA",
  silverMuted: "rgba(199, 210, 218, 0.72)",
  lineSilver: "rgba(199, 210, 218, 0.16)",
  panel: "rgba(18, 25, 37, 0.76)"
} as const;

function safeString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function humanize(value: unknown): string {
  const text = safeString(value);
  return text ? text.replace(/_/g, " ") : "Not surfaced";
}

function formatBool(value: unknown): string {
  return value === true ? "true" : value === false ? "false" : "not surfaced";
}

function safeArtifacts(value: unknown): ArtifactSummaryData[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is ArtifactSummaryData => Boolean(entry && typeof entry === "object"))
    : [];
}

export default function ArtifactsPage({
  startupReady,
  onRightDrawerSectionsChange
}: ArtifactsPageProps) {
  const [artifacts, setArtifacts] = useState<ArtifactSummaryData[]>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<ArtifactDetailData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadArtifacts() {
      setIsLoading(true);
      setErrorMessage(null);
      const result = await fetchArtifacts({ limit: 50 });
      if (cancelled) return;

      const payload = result.payload;
      if (!result.ok || payload.status !== "ok") {
        setArtifacts([]);
        setErrorMessage(
          payload.errors?.[0] ?? "Artifact list did not return usable truth."
        );
        setIsLoading(false);
        return;
      }

      const nextArtifacts = safeArtifacts(payload.data?.artifacts);
      setArtifacts(nextArtifacts);
      setSelectedArtifactId((current) => current ?? safeString(nextArtifacts[0]?.artifact_id));
      setIsLoading(false);
    }

    void loadArtifacts();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadDetail(artifactId: string) {
      const result = await fetchArtifactDetail(artifactId);
      if (cancelled) return;

      const data = result.payload.data;
      setSelectedDetail(result.ok && result.payload.status === "ok" ? data ?? null : null);
    }

    if (selectedArtifactId) {
      void loadDetail(selectedArtifactId);
    } else {
      setSelectedDetail(null);
    }

    return () => {
      cancelled = true;
    };
  }, [selectedArtifactId]);

  const selectedArtifact = useMemo(
    () =>
      artifacts.find((artifact) => artifact.artifact_id === selectedArtifactId) ??
      selectedDetail?.summary ??
      null,
    [artifacts, selectedArtifactId, selectedDetail]
  );

  useEffect(() => {
    const recent = artifacts.slice(0, 3);
    onRightDrawerSectionsChange([
      {
        key: "artifact_plane",
        title: "Artifact Plane",
        state: errorMessage ? "degraded" : startupReady ? "live" : "partial",
        rows: [
          { label: "Artifacts", value: `${artifacts.length} visible` },
          { label: "Selected", value: selectedArtifactId ?? "None selected" },
          { label: "Memory", value: "Not memory by default" },
          { label: "Private context outward", value: "false by default" }
        ]
      },
      {
        key: "recent_artifacts",
        title: "Recent Artifacts",
        state: recent.length > 0 ? "live" : "partial",
        rows:
          recent.length > 0
            ? recent.map((artifact) => ({
                label: humanize(artifact.kind),
                value: safeString(artifact.title) ?? safeString(artifact.artifact_id) ?? "Artifact"
              }))
            : [{ label: "Recent", value: "No local artifacts surfaced yet" }]
      }
    ]);
  }, [artifacts, errorMessage, onRightDrawerSectionsChange, selectedArtifactId, startupReady]);

  const safePreview = selectedDetail?.safe_preview ?? {};
  const boundaryTruth = selectedDetail?.boundary_truth ?? {};

  return (
    <div
      className="elysia-room-scroll-at-narrow"
      style={{ display: "grid", gap: "1rem", minHeight: 0, overflow: "auto" }}
    >
      <header>
        <div style={{ color: palette.sandstone, fontSize: "0.76rem", textTransform: "uppercase" }}>
          Local outputs
        </div>
        <h1 style={{ margin: "0.2rem 0", color: palette.silver }}>Artifacts</h1>
        <p style={{ margin: 0, color: palette.silverMuted, lineHeight: 1.5 }}>
          Local generated receipts and previews. This room lists known artifact
          summaries and safe details without exposing raw artifact paths, source
          paths, private memory, or publish controls.
        </p>
      </header>

      {errorMessage && (
        <section style={{ border: `1px solid ${palette.lineSilver}`, background: palette.panel, borderRadius: 12, padding: "0.9rem" }}>
          {errorMessage}
        </section>
      )}

      <section
        className="elysia-responsive-split"
        style={{ display: "grid", gridTemplateColumns: "minmax(260px, 0.86fr) minmax(320px, 1.14fr)", gap: "1rem", alignItems: "start" }}
      >
        <div style={{ display: "grid", gap: "0.75rem" }}>
          {isLoading ? (
            <div style={{ color: palette.silverMuted }}>Loading local artifact summaries.</div>
          ) : artifacts.length === 0 ? (
            <div style={{ color: palette.silverMuted }}>No local artifacts are visible yet.</div>
          ) : (
            artifacts.map((artifact, index) => {
              const artifactId = safeString(artifact.artifact_id);
              return (
                <button
                  key={artifactId ?? `artifact_${index}`}
                  type="button"
                  onClick={() => artifactId && setSelectedArtifactId(artifactId)}
                  style={{ all: "unset", cursor: artifactId ? "pointer" : "default" }}
                >
                  <ArtifactCard artifact={artifact} />
                </button>
              );
            })
          )}
        </div>

        <aside style={{ border: `1px solid ${palette.lineSilver}`, background: palette.panel, borderRadius: 14, padding: "1rem", display: "grid", gap: "0.85rem" }}>
          <div>
            <div style={{ color: palette.sandstone, fontSize: "0.76rem", textTransform: "uppercase" }}>
              Safe detail
            </div>
            <h2 style={{ margin: "0.15rem 0", color: palette.silver }}>
              {safeString(selectedArtifact?.title) ?? "No artifact selected"}
            </h2>
            <p style={{ margin: 0, color: palette.silverMuted }}>
              {safeString(selectedArtifact?.summary) ?? "Select an artifact to inspect safe detail."}
            </p>
          </div>

          {selectedArtifact?.kind === "plot_image" ? (
            <PlotArtifactView
              artifact={selectedArtifact}
              svgText={safeString(safePreview.svg_text)}
            />
          ) : (
            <pre style={{ whiteSpace: "pre-wrap", color: palette.silver, background: "rgba(11,14,18,0.64)", padding: "0.8rem", borderRadius: 10, maxHeight: 260, overflow: "auto" }}>
              {JSON.stringify(safePreview, null, 2)}
            </pre>
          )}

          <div style={{ display: "grid", gap: "0.42rem", color: palette.silverMuted }}>
            <DetailRow label="Artifact ID" value={safeString(selectedArtifact?.artifact_id) ?? "Not surfaced"} />
            <DetailRow label="Request" value={safeString(selectedArtifact?.request_id) ?? "Not linked"} />
            <DetailRow label="Project" value={safeString(selectedArtifact?.project_id) ?? "Not linked"} />
            <DetailRow label="Memory promotion" value={formatBool(selectedArtifact?.memory_promotion ?? boundaryTruth.memory_promotion)} />
            <DetailRow label="Private context sent" value={formatBool(selectedArtifact?.private_context_sent ?? boundaryTruth.private_context_sent)} />
            <DetailRow label="Source file mutated" value={formatBool(boundaryTruth.source_file_mutated)} />
            <DetailRow label="Network" value={formatBool(boundaryTruth.network_access_used)} />
          </div>
        </aside>
      </section>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
      <span style={{ color: palette.sandstone }}>{label}</span>
      <span style={{ textAlign: "right" }}>{value}</span>
    </div>
  );
}

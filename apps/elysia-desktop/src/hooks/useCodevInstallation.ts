import { useEffect, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { getCodevInstallation } from "../api/codevNative";
import type { Installation } from "../api/codevContracts";

// Native capability discovery only. Website clients must never use this hook.
export function useCodevInstallation(profileId = "") {
  const [installation, setInstallation] = useState<{ owner: string; value: Installation } | null>(null);
  useEffect(() => {
    let mounted = true;
    let serial = 0;
    const refresh = async () => {
      const current = ++serial;
      try {
        const value = await getCodevInstallation();
        if (mounted && current === serial) setInstallation({ owner: profileId, value });
      } catch {
        // A service outage is not an uninstall. Native package inspection
        // remains available even when no API process can answer.
        try {
          const value = isTauri() ? await invoke<Installation>("codev_installation") : null;
          if (mounted && current === serial) setInstallation(value ? { owner: profileId, value } : null);
        } catch { /* Preserve the last verified installed identity during an outage. */ }
      }
    };
    void refresh();
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 5000);
    return () => { mounted = false; window.removeEventListener("focus", refresh); window.clearInterval(timer); };
  }, [profileId]);
  return installation?.owner === profileId && installation.value.installed ? installation.value : null;
}

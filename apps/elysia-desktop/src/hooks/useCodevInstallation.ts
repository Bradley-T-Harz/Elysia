import { useEffect, useState } from "react";
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
        if (mounted && current === serial) setInstallation(null);
      }
    };
    void refresh();
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void refresh(); }, 30000);
    return () => { mounted = false; window.removeEventListener("focus", refresh); window.clearInterval(timer); };
  }, [profileId]);
  return installation?.owner === profileId && installation.value.usable && installation.value.state === "installed_ready" ? installation.value : null;
}

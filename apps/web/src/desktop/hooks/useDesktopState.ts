import { useState, useEffect, useCallback } from "react";
import { desktopService } from "../services/desktopService.js";
import type { DesktopState } from "../types.js";

export function useDesktopState() {
  const [state, setState] = useState<DesktopState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await desktopService.getDesktopState();
      setState(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { state, loading, error, refresh };
}

import { useState, useEffect, useCallback } from "react";
import { desktopService } from "../services/desktopService.js";
import type { ConnectivityStatus, SyncResult } from "../types.js";
import { isDesktop } from "../isDesktop.js";

export function useConnectivity(autoCheckIntervalMs = 20000) {
  const [status, setStatus] = useState<ConnectivityStatus>({
    is_online: true,
    server_url: null,
    rollback_detected: false,
  });
  const [checking, setChecking] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncResult, setLastSyncResult] = useState<SyncResult | null>(null);

  const check = useCallback(async () => {
    if (!isDesktop()) return;
    setChecking(true);
    try {
      const res = await desktopService.checkConnectivity();
      if (res && typeof res.is_online === "boolean") {
        setStatus(res);
      }
    } catch {
      setStatus((prev) => ({ ...prev, is_online: false }));
    } finally {
      setChecking(false);
    }
  }, []);

  const sync = useCallback(async (): Promise<SyncResult | null> => {
    if (!isDesktop()) return null;
    setSyncing(true);
    try {
      const res = await desktopService.syncOfflineLicenses();
      if (res) {
        setLastSyncResult(res);
        setStatus((prev) => ({
          ...prev,
          is_online: res.is_online,
          rollback_detected: false,
        }));
      }
      return res;
    } catch (err) {
      console.error("Failed to sync offline licenses:", err);
      return null;
    } finally {
      setSyncing(false);
    }
  }, []);

  useEffect(() => {
    void check();
    if (autoCheckIntervalMs > 0) {
      const interval = setInterval(() => {
        void check();
      }, autoCheckIntervalMs);
      return () => clearInterval(interval);
    }
  }, [check, autoCheckIntervalMs]);

  return {
    isOnline: status?.is_online ?? true,
    rollbackDetected: status?.rollback_detected ?? false,
    serverUrl: status?.server_url ?? null,
    checking,
    syncing,
    lastSyncResult,
    checkNow: check,
    syncNow: sync,
  };
}

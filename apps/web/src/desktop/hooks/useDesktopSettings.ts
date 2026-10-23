import { useState, useEffect, useCallback } from "react";
import { desktopService } from "../services/desktopService.js";
import type { DesktopSettingsInfo } from "../types.js";

export function useDesktopSettings() {
  const [settings, setSettings] = useState<DesktopSettingsInfo | null>(null);
  const [serverUrl, setServerUrl] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await desktopService.getSettings();
      setSettings(data);
      setServerUrl(data.server_url);
      setDeviceName(data.device_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSettings();
  }, [fetchSettings]);

  const handleSave = useCallback(
    async (e?: React.FormEvent) => {
      if (e) {
        e.preventDefault();
      }
      setSaving(true);
      setError(null);
      setSuccess(null);
      try {
        const updated = await desktopService.updateSettings(
          serverUrl.trim() || undefined,
          deviceName.trim() || undefined
        );
        setSettings(updated);
        setSuccess("Settings updated successfully");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setSaving(false);
      }
    },
    [serverUrl, deviceName]
  );

  return {
    settings,
    serverUrl,
    setServerUrl,
    deviceName,
    setDeviceName,
    loading,
    saving,
    error,
    success,
    handleSave,
    refresh: fetchSettings,
  };
}

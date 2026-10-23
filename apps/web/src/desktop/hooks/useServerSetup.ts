import { useState } from "react";
import { desktopService } from "../services/desktopService.js";

export function useServerSetup(onSuccess: (url: string) => void) {
  const [serverUrl, setServerUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault();
    }
    const cleanUrl = serverUrl.trim();
    if (!cleanUrl) {
      setError("Please enter a valid server address");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await desktopService.validateAndSetServerUrl(cleanUrl);
      onSuccess(res.server_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return {
    serverUrl,
    setServerUrl,
    loading,
    error,
    handleSubmit,
  };
}

import { useState, useCallback } from "react";
import { desktopService } from "../services/desktopService.js";
import type { UserProfile } from "../types.js";

export function useDesktopAuth(initialUser: UserProfile | null, onLoginSuccess?: () => void) {
  const [user, setUser] = useState<UserProfile | null>(initialUser);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [email, setEmail] = useState(initialUser?.email || "");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = useCallback(
    async (e?: React.FormEvent) => {
      if (e) {
        e.preventDefault();
      }
      if (!email.trim() || !password) {
        setError("Please enter your email and password");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const res = await desktopService.login(email.trim(), password);
        setUser(res.user);
        setDeviceId(res.device_id);
        setPassword("");
        if (onLoginSuccess) {
          onLoginSuccess();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [email, password, onLoginSuccess]
  );

  const handleLogout = useCallback(async () => {
    try {
      await desktopService.logout();
    } catch {
      // Ignore logout errors
    } finally {
      setUser(null);
      setDeviceId(null);
    }
  }, []);

  return {
    user,
    deviceId,
    email,
    setEmail,
    password,
    setPassword,
    loading,
    error,
    handleLogin,
    handleLogout,
  };
}

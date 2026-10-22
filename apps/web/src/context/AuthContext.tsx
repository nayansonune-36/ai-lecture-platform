import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { UserOut } from "@lecture-platform/shared";
import {
  api,
  getMemoryAccessToken,
  setMemoryAccessToken,
  setOnUnauthorizedHandler,
} from "../services/api.js";

interface AuthContextType {
  user: UserOut | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  token: string | null;
}

const AuthContext = createContext<AuthContextType | null>(null);

const REFRESH_TOKEN_KEY = "auth_refresh_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const queryClient = useQueryClient();

  const updateTokens = useCallback((accessToken: string | null, refreshToken?: string | null) => {
    setMemoryAccessToken(accessToken);
    setTokenState(accessToken);
    if (refreshToken) {
      try {
        localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
      } catch {
        // ignore storage errors
      }
    }
  }, []);

  const clearTokens = useCallback(() => {
    setMemoryAccessToken(null);
    setTokenState(null);
    try {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      // Clear cookie if present
      document.cookie = `${REFRESH_TOKEN_KEY}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT; Max-Age=0;`;
    } catch {
      // ignore
    }
  }, []);

  const refreshTokens = useCallback(async (): Promise<string | null> => {
    let storedRefresh: string | null = null;
    try {
      storedRefresh = localStorage.getItem(REFRESH_TOKEN_KEY);
    } catch {
      return null;
    }

    if (!storedRefresh) {
      return null;
    }

    try {
      const res = await api.auth.refresh({ refresh_token: storedRefresh });
      updateTokens(res.access_token, res.refresh_token);
      return res.access_token;
    } catch {
      clearTokens();
      setUser(null);
      queryClient.clear();
      return null;
    }
  }, [clearTokens, queryClient, updateTokens]);

  const logout = useCallback(async () => {
    try {
      const storedRefresh = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (storedRefresh) {
        await api.auth.logout({ refresh_token: storedRefresh });
      }
    } catch {
      // ignore
    } finally {
      clearTokens();
      setUser(null);
      queryClient.clear();
    }
  }, [clearTokens, queryClient]);

  // Connect unauthorized handler on mount
  useEffect(() => {
    setOnUnauthorizedHandler(async () => {
      const newToken = await refreshTokens();
      if (!newToken) {
        await logout();
      }
      return newToken;
    });
  }, [refreshTokens, logout]);

  // Initial authentication check on application boot
  useEffect(() => {
    let isMounted = true;

    async function initAuth() {
      const storedRefresh = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (!storedRefresh) {
        if (isMounted) setIsLoading(false);
        return;
      }

      try {
        const res = await api.auth.refresh({ refresh_token: storedRefresh });
        if (!isMounted) return;
        updateTokens(res.access_token, res.refresh_token);

        const me = await api.auth.me();
        if (isMounted) setUser(me);
      } catch {
        if (isMounted) {
          clearTokens();
          setUser(null);
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    initAuth();

    return () => {
      isMounted = false;
    };
  }, [clearTokens, updateTokens]);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await api.auth.login({ email, password });
      updateTokens(res.access_token, res.refresh_token);
      setUser(res.user);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user && !!token,
        isLoading,
        login,
        logout,
        token: getMemoryAccessToken(),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

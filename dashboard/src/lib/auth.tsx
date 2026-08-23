/**
 * Authentication context and role resolution.
 *
 * Permissions held here drive *navigation and affordances only*. Authorization
 * is enforced by the backend on every request — hiding a button is a courtesy,
 * not a security boundary.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, ApiError, onUnauthorized, tokenStore } from "./api";
import type { AuthenticatedUser, LoginResponse, RoleName } from "./types";

interface AuthState {
  user: AuthenticatedUser | null;
  status: "loading" | "authenticated" | "anonymous";
  login: (email: string, password: string) => Promise<AuthenticatedUser>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
  hasRole: (role: RoleName) => boolean;
  primaryRole: RoleName | null;
  refreshIdentity: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

/** Role precedence when an account holds more than one role. */
const ROLE_PRECEDENCE: RoleName[] = ["admin", "doctor", "health_worker", "patient"];

export function resolvePrimaryRole(roles: RoleName[]): RoleName | null {
  return ROLE_PRECEDENCE.find((role) => roles.includes(role)) ?? roles[0] ?? null;
}

/** The landing route for each role — each portal is a separate workspace. */
export const ROLE_HOME: Record<RoleName, string> = {
  admin: "/admin/dashboard",
  health_worker: "/user/dashboard",
  doctor: "/doctor/dashboard",
  patient: "/patient/home",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  const loadIdentity = useCallback(async () => {
    if (!tokenStore.access) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    try {
      const identity = await api.get<AuthenticatedUser>("/auth/me");
      setUser(identity);
      setStatus("authenticated");
    } catch {
      tokenStore.clear();
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void loadIdentity();
  }, [loadIdentity]);

  // The API client signals when a session can no longer be recovered.
  useEffect(
    () =>
      onUnauthorized(() => {
        setUser(null);
        setStatus("anonymous");
      }),
    [],
  );

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.anonymousPost<LoginResponse>("/auth/login", {
      email,
      password,
    });
    tokenStore.set(response.tokens);
    setUser(response.user);
    setStatus("authenticated");
    return response.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout", { refresh_token: tokenStore.refresh });
    } catch (error) {
      // Signing out must always succeed locally, even if the server is
      // unreachable — otherwise a user on a shared device cannot get out.
      if (!(error instanceof ApiError)) throw error;
    } finally {
      tokenStore.clear();
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      status,
      login,
      logout,
      hasPermission: (permission) => user?.permissions.includes(permission) ?? false,
      hasRole: (role) => user?.roles.includes(role) ?? false,
      primaryRole: user ? resolvePrimaryRole(user.roles) : null,
      refreshIdentity: loadIdentity,
    }),
    [user, status, login, logout, loadIdentity],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider.");
  return context;
}

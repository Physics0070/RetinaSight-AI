/**
 * Role resolution, route guarding and the client's error/offline handling.
 *
 * Note these guards are UX, not security — the corresponding backend tests
 * (tests/test_rbac.py) prove enforcement happens server-side.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RequireRole, RoleLanding } from "@/app/RouteGuards";
import { ApiError, tokenStore } from "@/lib/api";
import { AuthProvider, ROLE_HOME, resolvePrimaryRole } from "@/lib/auth";
import type { AuthenticatedUser, RoleName } from "@/lib/types";

function makeUser(roles: RoleName[], permissions: string[] = []): AuthenticatedUser {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    email: "user@example.com",
    full_name: "Test User",
    status: "active",
    roles,
    permissions,
    clinic_id: null,
    patient_id: null,
  };
}

function mockIdentity(user: AuthenticatedUser | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      user
        ? new Response(JSON.stringify(user), {
            status: 200,
            headers: { "content-type": "application/json" },
          })
        : new Response("{}", { status: 401, headers: { "content-type": "application/json" } }),
    ),
  );
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("role resolution", () => {
  it("gives every role its own separate workspace route", () => {
    const homes = Object.values(ROLE_HOME);
    expect(new Set(homes).size).toBe(homes.length);
    expect(ROLE_HOME.admin).toMatch(/^\/admin/);
    expect(ROLE_HOME.health_worker).toMatch(/^\/user/);
    expect(ROLE_HOME.doctor).toMatch(/^\/doctor/);
    expect(ROLE_HOME.patient).toMatch(/^\/patient/);
  });

  it("applies a stable precedence when an account holds several roles", () => {
    expect(resolvePrimaryRole(["patient", "admin"])).toBe("admin");
    expect(resolvePrimaryRole(["patient", "doctor"])).toBe("doctor");
    expect(resolvePrimaryRole(["patient", "health_worker"])).toBe("health_worker");
    expect(resolvePrimaryRole(["patient"])).toBe("patient");
  });

  it("returns null when the account has no role", () => {
    expect(resolvePrimaryRole([])).toBeNull();
  });
});

describe("route guards", () => {
  function renderAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/doctor/*"
              element={
                <RequireRole role="doctor">
                  <p>Doctor workspace</p>
                </RequireRole>
              }
            />
            <Route path="/patient/home" element={<p>Patient home</p>} />
            <Route path="/login" element={<p>Sign in</p>} />
            <Route path="*" element={<RoleLanding />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
  }

  it("admits a doctor to the doctor workspace", async () => {
    tokenStore.set({ access_token: "t", refresh_token: "r" });
    mockIdentity(makeUser(["doctor"]));

    renderAt("/doctor/dashboard");

    expect(await screen.findByText("Doctor workspace")).toBeInTheDocument();
  });

  it("redirects a patient away from the doctor workspace to their own home", async () => {
    tokenStore.set({ access_token: "t", refresh_token: "r" });
    mockIdentity(makeUser(["patient"]));

    renderAt("/doctor/dashboard");

    expect(await screen.findByText("Patient home")).toBeInTheDocument();
    expect(screen.queryByText("Doctor workspace")).not.toBeInTheDocument();
  });

  it("sends an anonymous visitor to sign in", async () => {
    mockIdentity(null);

    renderAt("/doctor/dashboard");

    expect(await screen.findByText("Sign in")).toBeInTheDocument();
  });

  it("routes an authenticated user to the workspace for their role", async () => {
    tokenStore.set({ access_token: "t", refresh_token: "r" });
    mockIdentity(makeUser(["patient"]));

    renderAt("/");

    expect(await screen.findByText("Patient home")).toBeInTheDocument();
  });

  it("clears a rejected session rather than leaving a stale token", async () => {
    tokenStore.set({ access_token: "expired", refresh_token: "expired" });
    mockIdentity(null);

    renderAt("/doctor/dashboard");

    await waitFor(() => expect(tokenStore.access).toBeNull());
  });
});

describe("API error handling", () => {
  it("marks a lost connection distinctly so offline UX can respond", () => {
    const offline = new ApiError(0, "network_unavailable", "You appear to be offline.");
    const rejected = new ApiError(403, "permission_denied", "Not allowed.");

    expect(offline.isOffline).toBe(true);
    expect(rejected.isOffline).toBe(false);
  });

  it("carries a human-readable message, never a raw status code", () => {
    const error = new ApiError(500, "internal_error", "Something went wrong on our side.");

    expect(error.message).not.toMatch(/500|Error:|Exception/);
    expect(error.message).toMatch(/something went wrong/i);
  });
});

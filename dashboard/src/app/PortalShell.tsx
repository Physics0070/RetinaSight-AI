/**
 * Portal shell.
 *
 * Sets the role theme on the document (driving the contextual morphism in
 * tokens.css) and renders the navigation appropriate to that role. Each portal
 * gets its own information hierarchy — this is not one dashboard with items
 * hidden.
 */

import { useEffect, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { Button, cx } from "@/design-system/components/primitives";
import { useAuth } from "@/lib/auth";
import type { RoleName } from "@/lib/types";
import { ConnectivityBanner, useConnectivity } from "@/app/Connectivity";

export interface NavItem {
  to: string;
  label: string;
  /** Short glyph used in the compact/mobile bar. */
  glyph: string;
}

interface Props {
  role: RoleName;
  /** Shown beside the product name, e.g. "Field Screening". */
  workspaceName: string;
  navItems: NavItem[];
  children: ReactNode;
  /** Mobile-first roles get a bottom bar instead of a sidebar. */
  layout?: "sidebar" | "bottom-bar";
}

export function PortalShell({
  role,
  workspaceName,
  navItems,
  children,
  layout = "sidebar",
}: Props) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const online = useConnectivity();

  // Drive the role theme from the document root.
  useEffect(() => {
    document.documentElement.setAttribute("data-role", role);
    return () => document.documentElement.removeAttribute("data-role");
  }, [role]);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const isBottomBar = layout === "bottom-bar";

  return (
    <div
      className={cx("min-h-full", isBottomBar ? "flex flex-col" : "lg:flex")}
      style={{ background: "var(--rs-surface)", color: "var(--rs-ink)" }}
    >
      <a href="#main" className="rs-skip-link">
        Skip to main content
      </a>

      {!isBottomBar && (
        <aside
          className="hidden w-64 shrink-0 flex-col gap-6 border-r p-5 lg:flex"
          style={{ borderColor: "var(--rs-line)", background: "var(--rs-surface-sunken)" }}
        >
          <Brand workspaceName={workspaceName} />
          <nav aria-label={`${workspaceName} navigation`} className="flex flex-col gap-1">
            {navItems.map((item) => (
              <SidebarLink key={item.to} item={item} />
            ))}
          </nav>
          <div className="mt-auto flex flex-col gap-3">
            <UserCard name={user?.full_name} email={user?.email} />
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Sign out
            </Button>
          </div>
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className={cx(
            "flex items-center justify-between gap-4 border-b px-4 py-3",
            !isBottomBar && "lg:px-6",
          )}
          style={{ borderColor: "var(--rs-line)", background: "var(--rs-surface-raised)" }}
        >
          <div className={cx(!isBottomBar && "lg:hidden")}>
            <Brand workspaceName={workspaceName} compact />
          </div>
          <div className="ml-auto flex items-center gap-3">
            <ConnectivityPill online={online} />
            {isBottomBar && (
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                Sign out
              </Button>
            )}
          </div>
        </header>

        {!online && <ConnectivityBanner />}

        <main id="main" className="min-w-0 flex-1 p-4 lg:p-6">
          {children}
        </main>

        {isBottomBar && (
          <nav
            aria-label={`${workspaceName} navigation`}
            className="sticky bottom-0 flex items-stretch justify-around border-t"
            style={{ borderColor: "var(--rs-line)", background: "var(--rs-surface-raised)" }}
          >
            {navItems.map((item) => (
              <BottomLink key={item.to} item={item} />
            ))}
          </nav>
        )}

        {/* Mobile nav for sidebar layouts. */}
        {!isBottomBar && (
          <nav
            aria-label={`${workspaceName} navigation`}
            className="sticky bottom-0 flex items-stretch justify-around border-t lg:hidden"
            style={{ borderColor: "var(--rs-line)", background: "var(--rs-surface-raised)" }}
          >
            {navItems.slice(0, 5).map((item) => (
              <BottomLink key={item.to} item={item} />
            ))}
          </nav>
        )}
      </div>
    </div>
  );
}

function Brand({ workspaceName, compact }: { workspaceName: string; compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <RetinaMark />
      <div className="flex flex-col leading-tight">
        <span className={cx("font-bold", compact ? "text-[var(--rs-text-sm)]" : "text-[var(--rs-text-base)]")}>
          RetinaSight AI
        </span>
        <span className="rs-label">{workspaceName}</span>
      </div>
    </div>
  );
}

/** Concentric retinal mark — fundus disc with macula, not a generic logo. */
function RetinaMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" role="presentation">
      <circle cx="15" cy="15" r="14" fill="var(--rs-retina-deep)" />
      <circle cx="15" cy="15" r="10.5" fill="var(--rs-retina)" />
      <circle cx="18.5" cy="13" r="3.6" fill="var(--rs-retina-glow)" opacity="0.85" />
      <circle cx="11.5" cy="16.5" r="2.4" fill="var(--rs-vitreous)" opacity="0.5" />
      <path
        d="M4 15c4 -4 9 3 13 -1"
        stroke="var(--rs-retina-deep)"
        strokeWidth="1.2"
        fill="none"
        opacity="0.65"
      />
    </svg>
  );
}

function SidebarLink({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      className="rounded-[var(--rs-radius-md)] px-3 py-2 text-[var(--rs-text-sm)] font-medium transition-colors"
      style={({ isActive }) => ({
        background: isActive ? "var(--rs-accent)" : "transparent",
        color: isActive ? "var(--rs-accent-ink)" : "var(--rs-ink-muted)",
      })}
    >
      {item.label}
    </NavLink>
  );
}

function BottomLink({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      className="flex flex-1 flex-col items-center gap-0.5 px-1 py-2 text-[var(--rs-text-2xs)] font-semibold"
      style={({ isActive }) => ({
        color: isActive ? "var(--rs-accent)" : "var(--rs-ink-subtle)",
      })}
    >
      <span aria-hidden="true" className="text-[var(--rs-text-base)]">
        {item.glyph}
      </span>
      <span className="text-center leading-tight">{item.label}</span>
    </NavLink>
  );
}

function UserCard({ name, email }: { name?: string; email?: string }) {
  return (
    <div className="rs-inset flex flex-col gap-0.5 p-3">
      <span className="truncate text-[var(--rs-text-sm)] font-semibold">{name ?? "—"}</span>
      <span className="truncate text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
        {email ?? ""}
      </span>
    </div>
  );
}

function ConnectivityPill({ online }: { online: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 text-[var(--rs-text-2xs)] font-semibold uppercase tracking-[var(--rs-tracking-caps)]"
      style={{ color: online ? "var(--rs-ok)" : "var(--rs-warn)" }}
    >
      <span aria-hidden="true">{online ? "●" : "◍"}</span>
      {online ? "Online" : "Offline"}
    </span>
  );
}

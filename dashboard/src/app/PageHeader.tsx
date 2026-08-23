import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** Consistent page heading with an optional back affordance and actions. */
export function PageHeader({
  title,
  subtitle,
  actions,
  backTo,
  backLabel = "Back",
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  backTo?: string;
  backLabel?: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex flex-col gap-1">
        {backTo && (
          <Link
            to={backTo}
            className="text-[var(--rs-text-xs)] font-semibold"
            style={{ color: "var(--rs-ink-subtle)" }}
          >
            ← {backLabel}
          </Link>
        )}
        <h1 className="text-[var(--rs-text-2xl)] font-bold">{title}</h1>
        {subtitle && (
          <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

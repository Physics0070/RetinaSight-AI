/**
 * Core UI primitives.
 *
 * These carry no colour literals: everything resolves to design tokens, so a
 * single component renders correctly in all four role themes.
 */

import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* -------------------------------------------------------------------------- */
/* Panel                                                                       */
/* -------------------------------------------------------------------------- */
interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  inset?: boolean;
  padded?: boolean;
}

export function Panel({ children, inset, padded = true, className, ...rest }: PanelProps) {
  return (
    <div
      className={cx(inset ? "rs-inset" : "rs-panel", padded && "p-5", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Button                                                                      */
/* -------------------------------------------------------------------------- */
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-[var(--rs-text-xs)]",
  md: "px-4 py-2.5 text-[var(--rs-text-sm)]",
  // Large targets for gloved, one-handed field use.
  lg: "px-6 py-4 text-[var(--rs-text-base)]",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  children,
  className,
  disabled,
  style,
  ...rest
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-[var(--rs-radius-md)] font-semibold " +
    "transition-all duration-[var(--rs-duration-fast)] disabled:opacity-50 disabled:cursor-not-allowed";

  // `rs-neu` gives the raised-by-default / pressed-in-on-:active neumorphic key
  // behaviour (see global.css). Ghost has no elevation, so it opts out.
  const variants: Record<ButtonVariant, string> = {
    primary: "rs-neu hover:brightness-110",
    secondary: "rs-neu hover:brightness-105",
    ghost: "hover:opacity-80",
    danger: "rs-neu hover:brightness-110",
  };

  // Fills only — elevation comes from the `rs-neu` class so the :active press
  // can override the box-shadow (an inline boxShadow would win over the class
  // and defeat the depress). Primary/danger keep a faint accent ring via
  // `--rs-glow`, layered under the class shadow through the ring only.
  const variantStyle: Record<ButtonVariant, Record<string, string>> = {
    primary: {
      background:
        "linear-gradient(140deg, color-mix(in srgb, var(--rs-accent) 92%, white), var(--rs-accent))",
      // Set here rather than via a Tailwind arbitrary class: `text-[var(--x)]`
      // is ambiguous between colour and font-size, so it silently did not
      // apply and the button inherited body ink — near-white on a bright
      // accent, which is unreadable.
      color: "var(--rs-accent-ink)",
    },
    secondary: {
      background: "var(--rs-surface-raised)",
      color: "var(--rs-ink)",
    },
    ghost: { background: "transparent", color: "var(--rs-ink-muted)" },
    danger: {
      background:
        "linear-gradient(140deg, color-mix(in srgb, var(--rs-danger) 90%, white), var(--rs-danger))",
      // Dark ink on the light danger tone; white would fail contrast here too.
      color: "#2a0508",
    },
  };

  return (
    <button
      className={cx(base, BUTTON_SIZES[size], variants[variant], className)}
      style={{ ...variantStyle[variant], ...style }}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Field                                                                       */
/* -------------------------------------------------------------------------- */
interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}

export function Field({ label, htmlFor, hint, error, required, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="rs-label">
        {label}
        {required && (
          <span aria-hidden="true" style={{ color: "var(--rs-danger)" }}>
            {" *"}
          </span>
        )}
      </label>
      {children}
      {hint && !error && (
        <p className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
          {hint}
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="text-[var(--rs-text-xs)] font-medium"
          style={{ color: "var(--rs-danger)" }}
        >
          {error}
        </p>
      )}
    </div>
  );
}

/* Inputs read as pressed INTO the surface — the neumorphic inset shadow
   replaces the old border, so the whole form language stays soft. */
const CONTROL_CLASS =
  "w-full rounded-[var(--rs-radius-md)] px-3.5 py-2.5 text-[var(--rs-text-sm)] outline-none";
const CONTROL_STYLE: Record<string, string> = {
  background: "var(--rs-surface-sunken)",
  color: "var(--rs-ink)",
  boxShadow: "var(--rs-shadow-sunken)",
};

export function Input({ className, style, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(CONTROL_CLASS, "transition-shadow duration-[var(--rs-duration-fast)]", className)}
      style={{ ...CONTROL_STYLE, ...style }}
      {...rest}
    />
  );
}

export function Select({
  className,
  style,
  children,
  ...rest
}: InputHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select className={cx(CONTROL_CLASS, className)} style={{ ...CONTROL_STYLE, ...style }} {...rest}>
      {children}
    </select>
  );
}

export function Textarea({
  className,
  style,
  ...rest
}: InputHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(CONTROL_CLASS, className)}
      style={{ ...CONTROL_STYLE, minHeight: "7rem", resize: "vertical", ...style }}
      {...rest}
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Badge                                                                       */
/* -------------------------------------------------------------------------- */
export function Badge({
  children,
  tone = "neutral",
  icon,
}: {
  children: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger" | "info";
  icon?: ReactNode;
}) {
  const toneColor: Record<string, string> = {
    neutral: "var(--rs-ink-subtle)",
    ok: "var(--rs-ok)",
    warn: "var(--rs-warn)",
    danger: "var(--rs-danger)",
    info: "var(--rs-info)",
  };
  const color = toneColor[tone];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-[var(--rs-radius-xs)] px-2 py-0.5 text-[var(--rs-text-2xs)] font-semibold uppercase tracking-[var(--rs-tracking-caps)]"
      style={{
        color,
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
      }}
    >
      {icon}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Feedback states                                                             */
/* -------------------------------------------------------------------------- */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <p className="text-[var(--rs-text-lg)] font-semibold">{title}</p>
      {description && (
        <p className="max-w-md text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
          {description}
        </p>
      )}
      {action}
    </div>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div
      className="flex items-center justify-center gap-3 px-6 py-14"
      role="status"
      aria-live="polite"
    >
      <Spinner />
      <span className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
        {label}…
      </span>
    </div>
  );
}

/**
 * Error display. Never renders a status code or stack trace — the API supplies
 * a human-readable message, and technical detail stays in the server logs.
 */
export function ErrorState({
  message,
  onRetry,
  offline,
}: {
  message: string;
  onRetry?: () => void;
  offline?: boolean;
}) {
  return (
    <div
      className="flex flex-col items-start gap-3 rounded-[var(--rs-radius-md)] border p-4"
      role="alert"
      style={{
        borderColor: `color-mix(in srgb, var(--rs-${offline ? "warn" : "danger"}) 40%, transparent)`,
        background: `color-mix(in srgb, var(--rs-${offline ? "warn" : "danger"}) 8%, transparent)`,
      }}
    >
      <p className="text-[var(--rs-text-sm)] font-medium">{message}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Metric tile                                                                 */
/* -------------------------------------------------------------------------- */
export function Metric({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "neutral" | "ok" | "warn" | "danger";
}) {
  const toneColor =
    tone && tone !== "neutral" ? `var(--rs-${tone === "ok" ? "ok" : tone})` : "var(--rs-ink)";
  return (
    <Panel className="rs-panel-interactive flex flex-col gap-1">
      <span className="rs-label">{label}</span>
      <span className="rs-readout text-[var(--rs-text-2xl)] font-bold" style={{ color: toneColor }}>
        {value}
      </span>
      {hint && (
        <span className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
          {hint}
        </span>
      )}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* Table                                                                       */
/* -------------------------------------------------------------------------- */
export function Table({ children, caption }: { children: ReactNode; caption?: string }) {
  return (
    <div className="rs-scroll-x">
      <table className="w-full border-collapse text-left text-[var(--rs-text-sm)]">
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}

export function Th({ children, scope = "col" }: { children: ReactNode; scope?: "col" | "row" }) {
  return (
    <th
      scope={scope}
      className="whitespace-nowrap border-b px-3 py-2.5 text-[var(--rs-text-2xs)] font-semibold uppercase tracking-[var(--rs-tracking-caps)]"
      style={{ borderColor: "var(--rs-line)", color: "var(--rs-ink-subtle)" }}
    >
      {children}
    </th>
  );
}

export function Td({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <td
      className={cx("border-b px-3 py-3 align-middle", className)}
      style={{ borderColor: "var(--rs-line)" }}
    >
      {children}
    </td>
  );
}

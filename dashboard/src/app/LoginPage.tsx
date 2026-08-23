/**
 * Sign-in.
 *
 * Deliberately not a marketing page: it states what the product is, signs the
 * user in, and routes them to the workspace their role grants.
 */

import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button, Field, Input, Panel } from "@/design-system/components/primitives";
import { ApiError } from "@/lib/api";
import { ROLE_HOME, resolvePrimaryRole, useAuth } from "@/lib/auth";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await login(email, password);
      const role = resolvePrimaryRole(user.roles);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? (role ? ROLE_HOME[role] : "/"), { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "We couldn't sign you in. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="flex min-h-full items-center justify-center p-4"
      style={{
        background:
          "radial-gradient(circle at 22% 28%, #1a2430 0%, #0d131b 55%, #06090d 100%)",
      }}
    >
      <div className="grid w-full max-w-4xl gap-8 lg:grid-cols-[1.1fr_1fr] lg:items-center">
        <section className="hidden flex-col gap-5 lg:flex">
          <FundusIllustration />
          <h1 className="text-[var(--rs-text-3xl)] font-bold" style={{ color: "#e8eef5" }}>
            Retinal screening,
            <br />
            wherever the patient is.
          </h1>
          <p className="max-w-md text-[var(--rs-text-sm)]" style={{ color: "#93a3b6" }}>
            Smartphone-based retinal capture with an automated quality gate,
            offline-first AI screening, explainable results, risk-based referral
            and clinician review.
          </p>
          <p className="text-[var(--rs-text-xs)]" style={{ color: "#6d7d91" }}>
            AI-assisted screening support — not an autonomous diagnostic device.
          </p>
        </section>

        <Panel className="flex flex-col gap-5" style={{ background: "#f6f8fa" }}>
          <div className="flex flex-col gap-1">
            <h2 className="text-[var(--rs-text-xl)] font-bold" style={{ color: "#10151c" }}>
              Sign in
            </h2>
            <p className="text-[var(--rs-text-sm)]" style={{ color: "#4a5563" }}>
              You'll be taken to the workspace for your role.
            </p>
          </div>

          <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
            <Field label="Email" htmlFor="email" required>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{ background: "#ffffff", borderColor: "#d3dae2", color: "#10151c" }}
              />
            </Field>

            <Field label="Password" htmlFor="password" required>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ background: "#ffffff", borderColor: "#d3dae2", color: "#10151c" }}
              />
            </Field>

            {error && (
              <p
                role="alert"
                className="rounded-[var(--rs-radius-sm)] px-3 py-2 text-[var(--rs-text-sm)]"
                style={{ background: "#fee2e2", color: "#991b1b" }}
              >
                {error}
              </p>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={submitting}
              style={{ background: "#0e7490" }}
            >
              Sign in
            </Button>
          </form>
        </Panel>
      </div>
    </div>
  );
}

/** Stylised fundus: optic disc, macula and vessel arcades. */
function FundusIllustration() {
  return (
    <svg viewBox="0 0 220 150" width="200" height="136" aria-hidden="true" role="presentation">
      <defs>
        <radialGradient id="fundus" cx="50%" cy="50%">
          <stop offset="0%" stopColor="#e8813f" />
          <stop offset="55%" stopColor="#b8420f" />
          <stop offset="100%" stopColor="#5c1f06" />
        </radialGradient>
      </defs>
      <ellipse cx="110" cy="75" rx="72" ry="68" fill="url(#fundus)" />
      <circle cx="148" cy="68" r="15" fill="#f7b267" opacity="0.9" />
      <circle cx="148" cy="68" r="7" fill="#fde3c0" opacity="0.7" />
      <circle cx="92" cy="82" r="11" fill="#6b2508" opacity="0.55" />
      {[
        "M148 68 C 120 40, 90 34, 58 44",
        "M148 68 C 122 96, 92 112, 60 108",
        "M148 68 C 128 66, 104 60, 74 62",
        "M148 68 C 130 76, 106 92, 78 96",
      ].map((d, index) => (
        <path
          key={index}
          d={d}
          stroke="#7c2d12"
          strokeWidth="2.4"
          fill="none"
          opacity="0.72"
          strokeLinecap="round"
        />
      ))}
      <ellipse
        cx="110"
        cy="75"
        rx="72"
        ry="68"
        fill="none"
        stroke="#22d3ee"
        strokeWidth="1.4"
        opacity="0.4"
        strokeDasharray="4 7"
      />
    </svg>
  );
}

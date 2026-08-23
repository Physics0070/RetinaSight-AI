/**
 * Runtime configuration.
 *
 * Every environment-specific value comes from Vite env vars — no API host,
 * clinic, or threshold is ever written into the source.
 */

interface AppConfig {
  apiBaseUrl: string;
  appName: string;
  /** Standing disclaimer shown wherever AI output is presented. */
  aiDisclaimer: string;
}

function requireEnv(key: string): string {
  const value = import.meta.env[key as keyof ImportMetaEnv] as string | undefined;
  if (value && value.trim()) return value.trim();
  throw new Error(
    `Missing required environment variable ${key}. Copy .env.example to .env and set it.`,
  );
}

export const config: AppConfig = {
  // No fallback literal here on purpose. Outside production builds, vite.config
  // supplies development defaults from .env.example at the lowest precedence,
  // so `npm run dev` needs no setup while this file carries no API address. A
  // production build with VITE_API_BASE_URL unset fails loudly instead of
  // shipping a bundle silently pointed at localhost.
  apiBaseUrl: requireEnv("VITE_API_BASE_URL"),
  // Not environment-specific: the product name and the standing disclaimer are
  // the same in every deployment, and the disclaimer is a safety requirement
  // that must not be switchable by configuration.
  appName: "RetinaSight AI",
  aiDisclaimer:
    "AI-assisted screening support. This is not a diagnosis. Clinical review by a qualified clinician is required.",
};

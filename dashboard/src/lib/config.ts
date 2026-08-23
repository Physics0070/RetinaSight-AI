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

function requireEnv(key: string, fallback?: string): string {
  const value = import.meta.env[key as keyof ImportMetaEnv] as string | undefined;
  if (value && value.trim()) return value.trim();
  if (fallback !== undefined) return fallback;
  throw new Error(
    `Missing required environment variable ${key}. Copy .env.example to .env and set it.`,
  );
}

export const config: AppConfig = {
  // Defaults to the local dev API so `npm run dev` works with no setup;
  // production builds must set VITE_API_BASE_URL.
  apiBaseUrl: requireEnv("VITE_API_BASE_URL", "http://localhost:8000/api/v1"),
  appName: "RetinaSight AI",
  aiDisclaimer:
    "AI-assisted screening support. This is not a diagnosis. Clinical review by a qualified clinician is required.",
};

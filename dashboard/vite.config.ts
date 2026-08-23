import fs from "node:fs";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/** Variables a production bundle cannot be built without. */
const REQUIRED_IN_PRODUCTION = ["VITE_API_BASE_URL"];

/**
 * Parse a dotenv-style file into a plain object. Only `KEY=value` lines are
 * read; comments and blanks are ignored, and inline trailing comments are
 * stripped because the example file uses them to document each setting.
 */
function readEnvFile(file: string): Record<string, string> {
  if (!fs.existsSync(file)) return {};
  const values: Record<string, string> = {};
  for (const raw of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const index = line.indexOf("=");
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1).split("#")[0].trim();
    if (key && value) values[key] = value;
  }
  return values;
}

export default defineConfig(({ mode }) => {
  const root = __dirname;

  // `.env.example` supplies development defaults at the LOWEST precedence.
  //
  // This is what lets src/lib/config.ts declare no fallback URL of its own:
  // the dev API address lives in the example file, where it is documentation
  // rather than compiled-in source, and `npm run dev` still works on a fresh
  // clone with no setup step. A real `.env` — which Vite loads itself — wins
  // over it, as does anything already in the process environment.
  //
  // Production builds are excluded: shipping a bundle that quietly points at
  // localhost because VITE_API_BASE_URL was forgotten is worse than failing
  // the build, and config.ts throws when the value is missing.
  const isProduction = mode === "production";
  const example = isProduction ? {} : readEnvFile(path.resolve(root, ".env.example"));
  const actual = loadEnv(mode, root, "VITE_");

  // Fail the BUILD, not the browser. Without this the bundle is produced
  // happily and config.ts throws on first load at the user's end — a broken
  // artefact that looks like a successful deploy.
  if (isProduction) {
    const missing = REQUIRED_IN_PRODUCTION.filter((key) => !actual[key]?.trim());
    if (missing.length > 0) {
      throw new Error(
        `Refusing to build: ${missing.join(", ")} not set.\n` +
          "Set it in the environment or in dashboard/.env (see .env.example).",
      );
    }
  }

  const define: Record<string, string> = {};
  for (const [key, value] of Object.entries(example)) {
    if (key.startsWith("VITE_") && actual[key] === undefined) {
      define[`import.meta.env.${key}`] = JSON.stringify(value);
    }
  }

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(root, "./src") },
    },
    define,
    server: {
      port: 5173,
      strictPort: false,
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  } as never;
});

import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { config as loadDotEnv } from "dotenv";

const webRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
loadDotEnv({ path: resolve(webRoot, "../.env.local"), override: false, quiet: true });

const read = (name) => (process.env[name] || "").trim();
const supabaseUrl = read("SUPABASE_URL");
const publishableKey = read("SUPABASE_PUBLISHABLE_KEY");
const apiUrl = read("AUDIT_API_URL");
const workshopId = read("WORKSHOP_ID");

function requireUrl(value, name, allowLocal = false) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be an absolute URL`);
  }
  if (parsed.protocol !== "https:" && !(allowLocal && parsed.hostname === "localhost")) {
    throw new Error(`${name} must use HTTPS`);
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error(`${name} must not contain credentials, query, or fragment`);
  }
  return parsed.toString().replace(/\/$/, "");
}

const publicConfig = {
  supabase_url: requireUrl(supabaseUrl, "SUPABASE_URL"),
  supabase_publishable_key: publishableKey,
  api_url: requireUrl(apiUrl, "AUDIT_API_URL", true),
  workshop_id: workshopId,
};
if (!publishableKey.startsWith("sb_publishable_")) {
  throw new Error("SUPABASE_PUBLISHABLE_KEY must be a publishable key");
}
if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(workshopId)) {
  throw new Error("WORKSHOP_ID must be a UUID");
}

await mkdir(resolve(webRoot, "public"), { recursive: true });
await writeFile(
  resolve(webRoot, "public/config.json"),
  `${JSON.stringify(publicConfig, null, 2)}\n`,
  { mode: 0o644 },
);
console.log("Public workshop configuration generated (secrets excluded)");

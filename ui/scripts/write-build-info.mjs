#!/usr/bin/env node
/**
 * Write a single build identity for this next build/dev start.
 * next.config.ts reads ui/.mina-build.json so client + server share one id.
 */
import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
// Repo root is parent of ui/ (write-build-info lives in ui/scripts/).
const repoRoot = join(root, "..");

let git = "unknown";
try {
  git = execSync("git rev-parse --short HEAD", {
    encoding: "utf8",
    cwd: repoRoot,
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();
} catch {
  try {
    git = execSync("git rev-parse --short HEAD", {
      encoding: "utf8",
      cwd: root,
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    /* not a git checkout */
  }
}

const builtAt = new Date().toISOString();
const nonce = Date.now().toString(36);
const info = {
  id: `${git}-${nonce}`,
  git,
  builtAt,
};

const out = join(root, ".mina-build.json");
writeFileSync(out, `${JSON.stringify(info, null, 2)}\n`, "utf8");
console.log(`mina build id: ${info.id}`);

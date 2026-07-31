/**
 * server.js — Local HTTPS dev server for Agent Ochuko Excel Add-in
 *
 * Office Add-ins MUST be served over HTTPS (even locally).
 * This script generates dev certs on first run (via office-addin-dev-certs)
 * and serves the add-in files on https://localhost:3000.
 *
 * Usage:
 *   npm install
 *   node server.js
 */

const https = require("https");
const fs = require("fs");
const path = require("path");

const PORT = 3000;
const ROOT = __dirname;

/* ── MIME types ─────────────────────────────────────────────────────────── */
const MIME = {
  ".html": "text/html",
  ".css": "text/css",
  ".js": "application/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".xml": "application/xml",
  ".ico": "image/x-icon",
};

/* ── Cert paths (office-addin-dev-certs stores them here) ───────────────── */
const CERT_DIR = path.join(
  process.env.LOCALAPPDATA || process.env.HOME,
  "office-addin-dev-certs"
);
const KEY_PATH = path.join(CERT_DIR, "localhost.key");
const CERT_PATH = path.join(CERT_DIR, "localhost.crt");
const CA_PATH = path.join(CERT_DIR, "ca.crt");

async function ensureCerts() {
  if (!fs.existsSync(KEY_PATH) || !fs.existsSync(CERT_PATH)) {
    console.log("Certificate: Generating dev certificates (requires admin/sudo once)...");
    const { execSync } = require("child_process");
    execSync("npx office-addin-dev-certs install --days 365", {
      stdio: "inherit",
    });
  }
}

async function start() {
  await ensureCerts();

  const options = {
    key: fs.readFileSync(KEY_PATH),
    cert: fs.readFileSync(CERT_PATH),
    ca: fs.existsSync(CA_PATH) ? fs.readFileSync(CA_PATH) : undefined,
  };

  const server = https.createServer(options, (req, res) => {
    // Strip query string
    let urlPath = req.url.split("?")[0];
    if (urlPath === "/" || urlPath === "") urlPath = "/src/taskpane/taskpane.html";

    const filePath = path.join(ROOT, urlPath);
    const ext = path.extname(filePath).toLowerCase();
    const mime = MIME[ext] || "application/octet-stream";

    // Security: prevent path traversal
    if (!filePath.startsWith(ROOT)) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end(`404 Not Found: ${urlPath}`);
        return;
      }
      res.writeHead(200, {
        "Content-Type": mime,
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache",
      });
      res.end(data);
    });
  });

  server.listen(PORT, () => {
    console.log(`\nSuccess: Agent Ochuko Add-in server running at https://localhost:${PORT}`);
    console.log(`\nSideload steps:`);
    console.log(`   1. Open Excel`);
    console.log(`   2. Insert -> Add-ins -> My Add-ins -> Upload My Add-in`);
    console.log(`   3. Browse to: ${path.join(ROOT, "manifest.xml")}`);
    console.log(`   4. Click "Open Ochuko" in the Home ribbon\n`);
  });
}

start().catch((err) => {
  console.error("Error: Failed to start server:", err);
  process.exit(1);
});

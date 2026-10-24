'use strict';
/*
 * Tender Tiger helper service v2  (runs on YOUR machine, called by the n8n workflow over HTTP)
 *   GET  /health[?deep=1]  -> checks Postgres (+ Chrome when deep=1)
 *   POST /collect          -> {email,password,maxViewMore}  logs in, loads dashboard + View More, returns [{tid,url}]
 *   POST /done-tids        -> {}                            TIDs already downloaded AND saved with the current data format
 *   POST /tender           -> {url,tid,email,password}      opens a tender, downloads, unzips, flattens, saves to Postgres
 * Every request except /health must send header  x-token: <TT_TOKEN>.
 * Up to TT_CONCURRENCY tenders are processed at the same time inside ONE shared Chrome.
 */
const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const os = require('os');
const { execFileSync } = require('child_process');

// optional service.env next to this file (KEY=VALUE per line)
try {
  fs.readFileSync(path.join(__dirname, 'service.env'), 'utf8').split('\n').forEach((l) => {
    const m = l.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
  });
} catch (e) { /* no service.env */ }

const ENV = process.env;
const PORT = Number(ENV.TT_PORT || 8787);
const HOST = ENV.TT_HOST || '0.0.0.0';
const TOKEN = ENV.TT_TOKEN || '';
const BASE = (ENV.TT_DOCS_DIR || '/home/xenovex/Tendo_Docs').replace(/[\\/]+$/, '');
const SITE = (ENV.TT_SITE_URL || 'https://www.tendertiger.com').replace(/\/+$/, '');
const HEADLESS = ENV.TT_HEADLESS !== 'false';
const CONCURRENCY = Math.max(1, Number(ENV.TT_CONCURRENCY || 4));
const STORE_MODE = ['all', 'zip', 'off'].includes(String(ENV.TT_STORE_IN_DB || 'all').toLowerCase()) ? String(ENV.TT_STORE_IN_DB || 'all').toLowerCase() : 'all'; // all = zip + every file, zip = only the downloaded zip, off = nothing
const DB_MAX_BYTES = Math.round(Number(ENV.TT_DB_MAX_MB || 200) * 1048576); // files larger than this stay on disk only
const META_VERSION = 3; // bump when the saved data format changes (older rows are refreshed automatically)
const LOGIN_URL = SITE + '/User/Account';
const DASH_URL = SITE + '/Dashboard/Dashboard';
const CARD_LINK = 'a[href*="TenderDetail/Tenderinformation"]';
const DEBUG_DIR = path.join(__dirname, 'debug');

const { Pool } = require('pg');
const pool = new Pool({
  host: ENV.PGHOST || 'localhost',
  port: Number(ENV.PGPORT || 5432),
  database: ENV.PGDATABASE || 'zynex',
  user: ENV.PGUSER || 'zynex',
  password: ENV.PGPASSWORD || 'zynex',
  max: 10,
});

const log = (...a) => console.log(new Date().toISOString(), ...a);
const firstLine = (e) => String((e && e.message) || e).split('\n')[0];

/* ======================= pure helpers ======================= */

function slug(s, n) {
  return String(s || '').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, n);
}

function isoDate(s) {
  const m = String(s || '').match(/(\d{1,2})-([A-Za-z]{3})[a-z]*-(\d{4})/);
  if (!m) return '';
  const mon = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 }[m[2].toLowerCase()];
  if (!mon) return '';
  return m[3] + '-' + String(mon).padStart(2, '0') + '-' + String(m[1]).padStart(2, '0');
}

const clean = (v) => { v = String(v || '').replace(/\s+/g, ' ').trim(); return v === '-' ? '' : v; };

// Reads the visible text of a Tender Tiger tender page
function parseDetail(text) {
  text = String(text || '').replace(/\r/g, '').replace(/\u00a0/g, ' ');
  const L = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const pick = (re) => { const m = text.match(re); return m ? m[1] : ''; };
  const d = {};

  const iTid = L.findIndex((l) => /^TID\s*:?\s*\d{5,}/.test(l));
  d.tid = pick(/TID\s*:?\s*(\d{5,})/);
  d.organization = iTid > 0 ? clean(L[iTid - 1]) : '';
  d.dept_tender_number = clean(pick(/Dept\.?\s*Tender\s*Number\s*:?\s*([^\n]+)/i));

  // title: GeM pages have "Tender Invited For ..."; other pages put the title on the line(s) right under the TID line
  const iProd = L.findIndex((l, i) => i > iTid && /^Product Description$/i.test(l));
  const head = iTid >= 0 ? L.slice(iTid + 1, iProd > iTid ? iProd : iTid + 6) : [];
  const meta = /^(Startup Relaxation|Quantity\s*:|Tender Invited For)/i;
  const cands = head.filter((l) => !meta.test(l));
  const invited = clean(pick(/Tender Invited For\s*:?\s*([^\n]+)/i));
  if (invited) { d.tender_title = invited; d.tender_description = clean(cands.join(' ')); }
  else { d.tender_title = clean((cands[0] || '').replace(/\s+\.$/, '')); d.tender_description = clean(cands.slice(1).join(' ')); }
  d.startup_relaxation = clean(pick(/Startup Relaxation[^:\n]*:\s*([^\n]+)/i));

  // product description / location / department (department can span several lines; "Gem Tender" marks GeM)
  const iKL = L.findIndex((l) => /^Key Location$/i.test(l));
  const iKV = L.findIndex((l, i) => i > iKL && /^Key Value$/i.test(l));
  d.product_description = iProd >= 0 && iKL > iProd ? clean(L.slice(iProd + 1, iKL).join(' ')) : '';
  d.key_location = iKL >= 0 ? clean(L[iKL + 1]) : '';
  let dep = iKL >= 0 && iKV > iKL ? L.slice(iKL + 2, iKV) : [];
  d.tender_type = '';
  if (dep.some((l) => /^gem tender$/i.test(l))) { d.tender_type = 'GeM Tender'; dep = dep.filter((l) => !/^gem tender$/i.test(l)); }
  d.department = clean(dep.join(' | '));

  d.worth = clean(pick(/Worth\s*:\s*([^\n]+)/i));
  d.emd = clean(pick(/EMD\s*:\s*([^\n]+)/i));
  d.doc_fees = clean(pick(/Doc Fees\s*:\s*([^\n]+)/i));
  const iQ = L.findIndex((l) => /^Quantity$/i.test(l));
  d.quantity = clean(iQ >= 0 ? L[iQ + 1] : pick(/Quantity\s*:\s*(\d[^\n]*)/i));
  d.due_date = isoDate(pick(/Due on\s*\n*\s*(\d{1,2}-[A-Za-z]{3,9}-\d{4})/i));
  d.days_to_go = clean(pick(/Days to go\s*:\s*(\d+)/i));
  d.opening_date = isoDate(pick(/Opening on\s*:\s*(\d{1,2}-[A-Za-z]{3,9}-\d{4})/i));
  d.published_date = isoDate(pick(/Published on\s*:\s*(\d{1,2}-[A-Za-z]{3,9}-\d{4})/i));

  // list of documents shown on the page: "NIT / Document 2 / ZIP"
  const iDoc = L.findIndex((l) => /^Documents\s*\(\d+\)/i.test(l));
  d.documents_listed = [];
  d.doc_count = '';
  if (iDoc >= 0) {
    d.doc_count = clean(pick(/Documents\s*\((\d+)\)/i));
    const iEnd = L.findIndex((l, i) => i > iDoc && /^(Download All|CONTACT US)/i.test(l));
    const blk = L.slice(iDoc + 1, iEnd > iDoc ? iEnd : iDoc + 40);
    blk.forEach((l, i) => {
      if (/^Document\s+\d+$/i.test(l)) d.documents_listed.push({ name: l, kind: blk[i - 1] || '', type: blk[i + 1] || '' });
    });
  }

  const iEndAll = L.findIndex((l, i) => i > iTid && /^CONTACT US/i.test(l));
  d.raw_detail = L.slice(Math.max(0, iTid - 1), iEndAll > iTid ? iEndAll : undefined).join('\n').slice(0, 6000);
  return d;
}

function makeFolderName(d) {
  const parts = [slug(d.tid, 20), slug(d.organization, 35), slug(d.tender_title || d.product_description, 55)].filter(Boolean);
  return parts.join('_') || ('tender_' + Date.now());
}

function listFiles(root) {
  const res = [];
  if (!fs.existsSync(root)) return res;
  (function walk(dir) {
    for (const n of fs.readdirSync(dir)) {
      const p = path.join(dir, n);
      const st = fs.statSync(p);
      if (st.isDirectory()) walk(p);
      else res.push({ name: path.relative(root, p), size: st.size });
    }
  })(root);
  return res;
}

// folder for this TID that already has downloaded files
function findExisting(tid) {
  if (!tid || !fs.existsSync(BASE)) return '';
  for (const n of fs.readdirSync(BASE)) {
    if (n.indexOf(tid + '_') === 0 || n === tid) {
      const p = path.join(BASE, n);
      if (fs.statSync(p).isDirectory() && listFiles(p).length > 0) return p;
    }
  }
  return '';
}

function isZip(file) {
  const fd = fs.openSync(file, 'r');
  const b = Buffer.alloc(4);
  fs.readSync(fd, b, 0, 4, 0);
  fs.closeSync(fd);
  return b[0] === 0x50 && b[1] === 0x4b;
}

function unzipOne(zipFile, destDir) {
  fs.mkdirSync(destDir, { recursive: true });
  // Linux/Mac: unzip.  Windows 10/11: the built-in tar.exe (bsdtar) can read zip files.  Last resort: Python's zipfile module.
  const tools = [
    ['unzip', ['-o', '-q', zipFile, '-d', destDir]],
    ['tar', ['-xf', zipFile, '-C', destDir]],
    ['python3', ['-m', 'zipfile', '-e', zipFile, destDir]],
    ['python', ['-m', 'zipfile', '-e', zipFile, destDir]],
    ['py', ['-m', 'zipfile', '-e', zipFile, destDir]],
  ];
  let lastErr = '';
  for (const t of tools) {
    try {
      execFileSync(t[0], t[1], { stdio: ['ignore', 'ignore', 'pipe'] });
      return;
    } catch (e) {
      if (t[0] === 'unzip' && e.status === 1) return; // unzip exit 1 = finished with warnings only
      if (e.code !== 'ENOENT') lastErr = t[0] + ': ' + String(e.stderr || e.message).trim().split('\n')[0];
      // GNU tar cannot read zip files, a missing tool is normal: try the next one
    }
  }
  throw new Error('Could not unzip ' + path.basename(zipFile) + ' - no unzip tool worked (install unzip, or use Windows 10/11 tar, or Python 3). ' + lastErr);
}

// unzip, then keep unzipping any zip found inside (any depth); nested zips are removed after extraction
function unzipRecursive(zipFile, destDir, depth) {
  depth = depth || 0;
  if (depth > 6) return;
  unzipOne(zipFile, destDir);
  const found = [];
  (function walk(dir) {
    for (const n of fs.readdirSync(dir)) {
      const p = path.join(dir, n);
      if (fs.statSync(p).isDirectory()) walk(p);
      else if (/\.zip$/i.test(n) && isZip(p)) found.push(p);
    }
  })(destDir);
  for (const z of found) {
    unzipRecursive(z, z.replace(/\.zip$/i, ''), depth + 1);
    fs.unlinkSync(z);
  }
}

// move EVERY file found anywhere under srcRoot into ONE flat folder (names get the TID prefix; clashes get _2, _3 ...)
function flattenInto(srcRoot, destDir, tid) {
  fs.mkdirSync(destDir, { recursive: true });
  (function walk(dir) {
    for (const n of fs.readdirSync(dir)) {
      const p = path.join(dir, n);
      if (fs.statSync(p).isDirectory()) { walk(p); continue; }
      const ext = path.extname(n);
      const stem = ext ? n.slice(0, -ext.length) : n;
      const base = (tid && !n.startsWith(tid) ? tid + '_' : '') + stem;
      let target = path.join(destDir, base + ext);
      for (let i = 2; fs.existsSync(target); i++) target = path.join(destDir, base + '_' + i + ext);
      fs.renameSync(p, target);
    }
  })(srcRoot);
}

// folders made by the old version have a "documents/" tree: convert them to the flat "files/" layout
function ensureFlat(folder, tid) {
  const filesDir = path.join(folder, 'files');
  const oldDir = path.join(folder, 'documents');
  if (!fs.existsSync(filesDir) && fs.existsSync(oldDir)) {
    flattenInto(oldDir, filesDir, tid);
    fs.rmSync(oldDir, { recursive: true, force: true });
  }
  return filesDir;
}

function zipOf(folder) {
  if (!fs.existsSync(folder)) return '';
  const z = fs.readdirSync(folder).find((n) => /\.zip$/i.test(n));
  return z ? path.join(folder, z) : '';
}

/* ======================= database ======================= */

const NEW_COLUMNS = [
  ['dept_tender_link', 'TEXT'], ['tender_description', 'TEXT'], ['department', 'TEXT'], ['opening_date', 'DATE'],
  ['published_date', 'DATE'], ['tender_link', 'TEXT'], ['files_path', 'TEXT'], ['zip_path', 'TEXT'],
  ['file_count', 'INTEGER'], ['files_in_db', 'INTEGER'], ['documents_listed', 'JSONB'], ['meta_version', 'INTEGER'],
  ['first_seen_at', 'TIMESTAMPTZ DEFAULT now()'],
];

const SCHEMA_SQL = `CREATE TABLE IF NOT EXISTS tt_tenders (
  id SERIAL PRIMARY KEY,
  tid TEXT UNIQUE NOT NULL,
  organization TEXT,
  dept_tender_number TEXT,
  tender_title TEXT,
  product_description TEXT,
  key_location TEXT,
  tender_type TEXT,
  worth TEXT,
  emd TEXT,
  doc_fees TEXT,
  quantity TEXT,
  due_date DATE,
  days_to_go INTEGER,
  startup_relaxation TEXT,
  folder_name TEXT,
  path TEXT,
  files JSONB,
  download_status TEXT,
  raw_detail TEXT,
  scraped_at TIMESTAMPTZ DEFAULT now()
);
${NEW_COLUMNS.map((c) => 'ALTER TABLE tt_tenders ADD COLUMN IF NOT EXISTS ' + c[0] + ' ' + c[1] + ';').join('\n')}
CREATE INDEX IF NOT EXISTS tt_tenders_status_idx ON tt_tenders (download_status);
CREATE TABLE IF NOT EXISTS tt_tender_files (
  id SERIAL PRIMARY KEY,
  tid TEXT NOT NULL,
  file_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  size BIGINT,
  sha256 TEXT,
  content BYTEA,
  stored_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tid, kind, file_name)
);
CREATE INDEX IF NOT EXISTS tt_tender_files_tid_idx ON tt_tender_files (tid);`;

const UPSERT_SQL = `INSERT INTO tt_tenders (
  tid, organization, dept_tender_number, dept_tender_link, tender_title, tender_description, product_description,
  key_location, department, tender_type, worth, emd, doc_fees, quantity,
  due_date, days_to_go, opening_date, published_date, startup_relaxation,
  tender_link, folder_name, path, files_path, zip_path, file_count,
  files, documents_listed, download_status, raw_detail, meta_version, files_in_db
) VALUES (
  $1, NULLIF($2,''), NULLIF($3,''), NULLIF($4,''), NULLIF($5,''), NULLIF($6,''), NULLIF($7,''),
  NULLIF($8,''), NULLIF($9,''), NULLIF($10,''), NULLIF($11,''), NULLIF($12,''), NULLIF($13,''), NULLIF($14,''),
  NULLIF($15,'')::date, NULLIF($16,'')::int, NULLIF($17,'')::date, NULLIF($18,'')::date, NULLIF($19,''),
  NULLIF($20,''), NULLIF($21,''), NULLIF($22,''), NULLIF($23,''), NULLIF($24,''), NULLIF($25,'')::int,
  $26::jsonb, $27::jsonb, $28, NULLIF($29,''), $30::int, NULLIF($31,'')::int
)
ON CONFLICT (tid) DO UPDATE SET
  organization = EXCLUDED.organization, dept_tender_number = EXCLUDED.dept_tender_number, dept_tender_link = EXCLUDED.dept_tender_link,
  tender_title = EXCLUDED.tender_title, tender_description = EXCLUDED.tender_description, product_description = EXCLUDED.product_description,
  key_location = EXCLUDED.key_location, department = EXCLUDED.department, tender_type = EXCLUDED.tender_type,
  worth = EXCLUDED.worth, emd = EXCLUDED.emd, doc_fees = EXCLUDED.doc_fees, quantity = EXCLUDED.quantity,
  due_date = EXCLUDED.due_date, days_to_go = EXCLUDED.days_to_go, opening_date = EXCLUDED.opening_date,
  published_date = EXCLUDED.published_date, startup_relaxation = EXCLUDED.startup_relaxation,
  tender_link = EXCLUDED.tender_link,
  folder_name = EXCLUDED.folder_name, path = EXCLUDED.path, files_path = EXCLUDED.files_path, zip_path = EXCLUDED.zip_path,
  file_count = EXCLUDED.file_count, files = EXCLUDED.files, documents_listed = EXCLUDED.documents_listed,
  download_status = EXCLUDED.download_status, raw_detail = EXCLUDED.raw_detail, meta_version = EXCLUDED.meta_version, files_in_db = EXCLUDED.files_in_db,
  scraped_at = now()
RETURNING tid, path, download_status`;

// a tender counts as finished only when saved in the CURRENT data format (older rows get refreshed once, without re-downloading)
const DONE_SQL = `SELECT COALESCE(array_agg(tid), ARRAY[]::text[]) AS tids FROM tt_tenders
WHERE COALESCE(meta_version, 1) >= ${META_VERSION}
  AND (download_status = 'done' OR (download_status = 'no_documents' AND scraped_at > now() - interval '24 hours'))`;

async function ensureSchema() { await pool.query(SCHEMA_SQL); }

async function saveTender(r) {
  const s = (v) => (v === undefined || v === null ? '' : String(v));
  await pool.query(UPSERT_SQL, [
    s(r.tid), s(r.organization), s(r.dept_tender_number), s(r.dept_tender_link), s(r.tender_title), s(r.tender_description), s(r.product_description),
    s(r.key_location), s(r.department), s(r.tender_type), s(r.worth), s(r.emd), s(r.doc_fees), s(r.quantity),
    s(r.due_date), s(r.days_to_go), s(r.opening_date), s(r.published_date), s(r.startup_relaxation),
    s(r.tender_link), s(r.folder_name), s(r.path), s(r.files_path), s(r.zip_path), s((r.files || []).length),
    JSON.stringify(r.files || []), JSON.stringify(r.documents_listed || []), s(r.status || 'done'), s(r.raw_detail), String(META_VERSION), s(r.files_in_db),
  ]);
}

const UPSERT_FILE_SQL = `INSERT INTO tt_tender_files (tid, file_name, kind, size, sha256, content) VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (tid, kind, file_name) DO UPDATE SET size = EXCLUDED.size, sha256 = EXCLUDED.sha256, content = EXCLUDED.content, stored_at = now()`;

// copy the downloaded zip (+ every extracted file) into Postgres; unchanged files (same sha256) are not written again
async function storeFilesInDb(r) {
  r.files_in_db = 0;
  if (STORE_MODE === 'off' || !r.path) return;
  const items = [];
  if (r.zip_path && fs.existsSync(r.zip_path)) items.push({ kind: 'zip', name: path.basename(r.zip_path), file: r.zip_path });
  if (STORE_MODE === 'all' && r.files_path && fs.existsSync(r.files_path)) {
    for (const f of fs.readdirSync(r.files_path)) { const p = path.join(r.files_path, f); if (fs.statSync(p).isFile()) items.push({ kind: 'file', name: f, file: p }); }
  }
  const have = new Map((await pool.query('SELECT kind, file_name, sha256 FROM tt_tender_files WHERE tid = $1', [r.tid])).rows.map((x) => [x.kind + '/' + x.file_name, x.sha256]));
  let n = 0;
  for (const it of items) {
    if (fs.statSync(it.file).size > DB_MAX_BYTES) { log('tender', r.tid, 'file too large for the database, kept on disk only:', it.name); continue; }
    const buf = fs.readFileSync(it.file);
    const sha = crypto.createHash('sha256').update(buf).digest('hex');
    if (have.get(it.kind + '/' + it.name) !== sha) await pool.query(UPSERT_FILE_SQL, [r.tid, it.name, it.kind, buf.length, sha, buf]);
    n++;
  }
  r.files_in_db = n;
}

/* ======================= browser (ONE shared Chrome, many tabs) ======================= */

async function launch() {
  const { chromium } = require('playwright-core');
  const opts = { headless: HEADLESS, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'] };
  try {
    return await chromium.launch(Object.assign({ channel: 'chrome' }, opts));
  } catch (e) {
    log('Google Chrome not usable (' + firstLine(e) + '), trying bundled Chromium');
    return await chromium.launch(opts);
  }
}

let browserP = null;
let inflight = 0;
let idleTimer = null;
function getBrowser() {
  if (!browserP) {
    browserP = launch()
      .then((b) => { b.on('disconnected', () => { browserP = null; }); return b; })
      .catch((e) => { browserP = null; throw e; });
  }
  return browserP;
}
async function withBrowser(fn) {
  inflight++;
  clearTimeout(idleTimer);
  try {
    return await fn(await getBrowser());
  } finally {
    inflight--;
    if (inflight === 0) {
      idleTimer = setTimeout(async () => { // free the RAM when idle
        if (inflight === 0 && browserP) { const p = browserP; browserP = null; (await p).close().catch(() => {}); }
      }, 60000);
    }
  }
}

function makeSem(n) {
  let free = n;
  const q = [];
  return {
    async acquire() { if (free > 0) { free--; return; } await new Promise((r) => q.push(r)); },
    release() { const r = q.shift(); if (r) r(); else free++; },
  };
}
const tenderSlots = makeSem(CONCURRENCY);

const stateFile = (cred) => path.join(__dirname, 'session_' + crypto.createHash('sha1').update(String(cred.email)).digest('hex').slice(0, 10) + '.json');

async function newContext(browser, cred, light, fresh) {
  const major = String(browser.version()).split('.')[0];
  const o = {
    acceptDownloads: true, viewport: { width: 1500, height: 1000 },
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/' + major + '.0.0.0 Safari/537.36',
  };
  if (!fresh && fs.existsSync(stateFile(cred))) o.storageState = stateFile(cred);
  const ctx = await browser.newContext(o);
  await ctx.addInitScript(() => { try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); } catch (e) { /* ignore */ } });
  ctx.setDefaultTimeout(45000);
  if (light) { // tender pages only need text: skip images / fonts / video
    await ctx.route('**/*', (route) => {
      const t = route.request().resourceType();
      return (t === 'image' || t === 'media' || t === 'font') ? route.abort() : route.continue();
    });
  }
  return ctx;
}

async function snap(page, tag) {
  try {
    if (!page) return;
    fs.mkdirSync(DEBUG_DIR, { recursive: true });
    await page.screenshot({ path: path.join(DEBUG_DIR, tag + '.png') });
  } catch (e) { /* ignore */ }
}

// true if at least one element matching the locator is really visible (sites often hide a duplicate "mobile" copy first)
async function anyVisible(locator) {
  const all = await locator.all().catch(() => []);
  for (const el of all) { if (await el.isVisible().catch(() => false)) return true; }
  return false;
}

async function isLoggedIn(page) {
  if (/User\/Account/i.test(page.url())) return false;
  if (await anyVisible(page.locator('input[placeholder="Enter Password"]'))) return false;
  if (await anyVisible(page.getByText(/Login\s*\/\s*Sign\s*Up/i))) return false;
  return true;
}

// type into a field robustly: click first (unlocks "read-only until focused" boxes), then fill; fall back to key presses, then to setting the value directly
async function typeInto(page, locator, value, label) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  await locator.click({ timeout: 5000 }).catch(() => {});
  try {
    await locator.fill(value, { timeout: 5000 });
  } catch (e) {
    log(label + ': fill() not possible (' + firstLine(e) + ') - typing with the keyboard instead');
    await locator.click({ force: true, timeout: 5000 }).catch(() => {});
    await page.keyboard.press('Control+A');
    await page.keyboard.press('Delete');
    await page.keyboard.type(value, { delay: 30 });
  }
  let got = await locator.inputValue().catch(() => null);
  if (got !== value) {
    log(label + ': value did not stick, setting it directly');
    await locator.evaluate((el, v) => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, value).catch(() => {});
    got = await locator.inputValue().catch(() => null);
  }
  if (got !== value) throw new Error('Could not type into the ' + label + ' box');
}

async function describeInputs(page) {
  return await page.evaluate(() => Array.from(document.querySelectorAll('input,button')).map((i) => ({
    tag: i.tagName, type: i.type, placeholder: i.placeholder || '', name: i.name || '', id: i.id || '',
    readonly: !!i.readOnly, disabled: !!i.disabled, visible: !!(i.offsetWidth || i.offsetHeight), text: (i.innerText || '').slice(0, 30),
  })).filter((x) => x.visible)).catch(() => []);
}

// any visible message on the page that explains a failed login (wrong password, captcha, OTP, locked ...)
async function loginMessage(page) {
  return await page.evaluate(() => {
    const re = /invalid|incorrect|wrong|not (registered|found|valid)|failed|locked|captcha|otp|too many|blocked|try again|expired|already (logged|in use)|another (device|session)|deactivat|suspend|verify/i;
    const els = Array.from(document.querySelectorAll('div,span,p,li,small,label,b,strong,h4,h5')).filter((e) => e.offsetParent !== null && e.children.length === 0);
    for (const e of els) {
      const t = (e.innerText || '').trim();
      if (t.length >= 4 && t.length <= 200 && re.test(t)) return t;
    }
    return '';
  }).catch(() => '');
}

// "logged in" = no visible password box and no visible "Login / Sign Up" button (URL is not used: the site may stay on the same page)
async function looksLoggedIn(page) {
  if (await anyVisible(page.locator('input[type="password"], input[placeholder="Enter Password"]'))) return false;
  if (await anyVisible(page.getByText(/Login\s*\/\s*Sign\s*Up/i))) return false;
  return true;
}

async function loginAttempt(page, context, cred, attempt) {
  log('logging in as', cred.email, attempt > 1 ? '(attempt ' + attempt + ')' : '');
  await context.clearCookies().catch(() => {});
  await page.goto(LOGIN_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const email = page.locator('input[placeholder*="Email" i]:visible, input[type="email"]:visible, input[name*="email" i]:visible').first();
  const pass = page.locator('input[type="password"]:visible, input[placeholder*="Password" i]:visible').first();
  try {
    await email.waitFor({ state: 'visible', timeout: 30000 });
    await pass.waitFor({ state: 'visible', timeout: 15000 });
    await page.waitForTimeout(1000);
    await snap(page, 'login_form');
    await typeInto(page, email, cred.email, 'email');
    await typeInto(page, pass, cred.password, 'password');
  } catch (e) {
    await snap(page, 'login_form_problem');
    log('login form problem. Visible inputs/buttons on the page:', JSON.stringify(await describeInputs(page)));
    throw new Error('Login form problem: ' + firstLine(e) + ' Screenshot: ' + path.join(DEBUG_DIR, 'login_form_problem.png'));
  }
  let clicked = false;
  try {
    await page.getByText(/win Tenders/i).first().click({ timeout: 8000 });
    clicked = true;
  } catch (e) { /* fall back to Enter key */ }
  if (!clicked) await pass.press('Enter');

  // wait for the REAL outcome (slow server = just wait): logged in, or the site shows a message, or give up after 25 s
  let message = '';
  let ok = false;
  const deadline = Date.now() + 25000;
  await page.waitForTimeout(1500);
  while (Date.now() < deadline) {
    if (await looksLoggedIn(page)) { ok = true; break; }
    message = await loginMessage(page);
    if (message) break;
    await page.waitForTimeout(700);
  }
  if (!ok) {
    await snap(page, 'login_after_click');
    log('login did not complete. site message:', JSON.stringify(message), '| page:', page.url(), '| visible:', JSON.stringify(await describeInputs(page)));
    return { ok: false, message: message };
  }
  await page.goto(DASH_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2500);
  if (!/Dashboard/i.test(page.url()) || !(await isLoggedIn(page))) {
    await snap(page, 'login_dashboard_redirect');
    log('login looked ok, but the dashboard sent us to', page.url());
    return { ok: false, message: '' };
  }
  await context.storageState({ path: stateFile(cred) });
  log('login ok');
  return { ok: true, message: '' };
}

async function login(page, context, cred) {
  let message = '';
  for (let attempt = 1; attempt <= 2; attempt++) {
    const r = await loginAttempt(page, context, cred, attempt);
    if (r.ok) return;
    message = r.message;
    if (message) break; // the site gave a reason (wrong password, captcha ...): do not hammer the account
    log('login attempt', attempt, 'failed without any message from the site' + (attempt < 2 ? ' - trying once more' : ''));
  }
  await snap(page, 'login_failed');
  throw new Error(message
    ? 'Login failed - the site says: "' + message + '". Check the email/password in the n8n Config node. Screenshots: ' + DEBUG_DIR
    : 'Login failed - no message from the site (captcha/OTP or a blocked browser?). Screenshots: ' + DEBUG_DIR);
}

// one login at a time per account; parallel tenders that find the session expired wait for it and reuse the saved session
const loginInflight = new Map();
async function ensureSession(browser, cred) {
  const key = String(cred.email);
  if (!loginInflight.has(key)) {
    const p = (async () => {
      try { fs.unlinkSync(stateFile(cred)); } catch (e) { /* none */ }
      const ctx = await newContext(browser, cred, false);
      try { await login(await ctx.newPage(), ctx, cred); } finally { await ctx.close().catch(() => {}); }
    })();
    loginInflight.set(key, p);
    p.then(() => loginInflight.delete(key), () => loginInflight.delete(key));
  }
  return loginInflight.get(key);
}

async function openDashboard(page, context, cred) {
  await page.goto(DASH_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3000);
  // the site may show its public home page (not redirect) when logged out
  if (!/Dashboard/i.test(page.url()) || !(await isLoggedIn(page))) await login(page, context, cred);
  try {
    await page.waitForFunction(() => /TID\s*:\s*\d{5,}/.test(document.body.innerText), null, { timeout: 120000 });
  } catch (e) {
    await snap(page, 'dashboard_no_tenders');
    throw new Error('Logged in, but the dashboard showed no tenders within 2 minutes (page: ' + page.url() + '). Screenshot: ' + path.join(DEBUG_DIR, 'dashboard_no_tenders.png'));
  }
  await page.waitForTimeout(1500);
}

async function loadAll(page, maxClicks) {
  let clicks = 0;
  while (clicks < maxClicks) {
    const before = await page.locator(CARD_LINK).count();
    const btn = page.getByText(/^\s*View More\s*$/i).first();
    if (!(await btn.isVisible().catch(() => false))) break;
    await btn.scrollIntoViewIfNeeded().catch(() => {});
    await btn.click();
    clicks++;
    const grew = await page
      .waitForFunction((a) => document.querySelectorAll(a.sel).length > a.n, { sel: CARD_LINK, n: before }, { timeout: 90000 })
      .then(() => true)
      .catch(() => false);
    log('View More click', clicks, 'links before:', before, 'grew:', grew);
    if (!grew) break;
    await page.waitForTimeout(800);
  }
  return clicks;
}

async function extractCards(page) {
  return await page.evaluate((sel) => {
    const res = [];
    const seen = new Set();
    for (const a of Array.from(document.querySelectorAll(sel))) {
      const url = a.href;
      let tid = '';
      let el = a;
      for (let i = 0; i < 10 && el; i++, el = el.parentElement) {
        const t = el.innerText || '';
        const m = t.match(/TID\s*:\s*(\d{5,})/);
        if (m) {
          if ((t.match(/TID\s*:/g) || []).length === 1) tid = m[1];
          break;
        }
      }
      const key = tid || url;
      if (seen.has(key)) continue;
      seen.add(key);
      res.push({ tid: tid, url: url });
    }
    return res;
  }, CARD_LINK);
}

async function collect(cred, maxViewMore) {
  return await withBrowser(async (browser) => {
    let context;
    let page;
    try {
      context = await newContext(browser, cred, false);
      page = await context.newPage();
      await openDashboard(page, context, cred);
      const clicks = await loadAll(page, Number(maxViewMore) || 5);
      const tenders = await extractCards(page);
      await context.storageState({ path: stateFile(cred) });
      if (!tenders.length) {
        await snap(page, 'collect_no_links');
        throw new Error('Dashboard loaded but no tender links were found. Screenshot: ' + path.join(DEBUG_DIR, 'collect_no_links.png'));
      }
      return { ok: true, clicks: clicks, count: tenders.length, tenders: tenders };
    } catch (e) {
      await snap(page, 'collect_error');
      throw e;
    } finally {
      if (context) await context.close().catch(() => {});
    }
  });
}

/* ----- the link behind the "Dept Tender Number" (original portal / GeM / IREPS page) ----- */

async function findDeptLink(page, deptNo) {
  if (!deptNo) return { link: '', how: '', clickable: false };
  const info = await page.evaluate((num) => {
    const cand = Array.from(document.querySelectorAll('a,span,b,strong,u,label,td,p,div,li,button')).filter((e) => (e.textContent || '').includes(num) && e.offsetParent !== null);
    let best = null;
    let bl = 1e9;
    for (const e of cand) { const l = (e.textContent || '').trim().length; if (l < bl) { best = e; bl = l; } }
    if (!best) return null;
    const urlIn = (s) => { const m = String(s || '').match(/https?:\/\/[^\s'"<>)]+/); return m ? m[0] : ''; };
    const chain = [best, best.parentElement, best.parentElement && best.parentElement.parentElement].filter(Boolean);
    let a = best.closest('a') || best.querySelector('a');
    if (!a) {
      for (const c of chain.slice(1)) {
        if ((c.textContent || '').length < 300) { const x = c.querySelector('a'); if (x && (x.textContent || '').includes(num)) { a = x; break; } }
      }
    }
    const nodes = [a].concat(chain).filter(Boolean);
    let link = '';
    let how = '';
    for (const n of nodes) {
      const h = n.getAttribute && n.getAttribute('href');
      if (h && !/^(javascript:|#|mailto:|tel:)/i.test(h.trim())) { link = n.href; how = 'href'; break; }
    }
    if (!link) {
      for (const n of nodes) {
        for (const att of ['onclick', 'data-href', 'data-url', 'data-link', 'ng-click']) {
          const u = urlIn(n.getAttribute && n.getAttribute(att));
          if (u) { link = u; how = att; break; }
        }
        if (link) break;
      }
    }
    const clickable = !!(a || best.getAttribute('onclick') || getComputedStyle(best).cursor === 'pointer');
    return { link: link, how: how, clickable: clickable, html: best.outerHTML.slice(0, 160) };
  }, deptNo).catch(() => null);
  if (!info) return { link: '', how: '', clickable: false };
  return info;
}

// last resort: open a second tab, click the number and see where it goes (popup or navigation)
async function clickForLink(context, url, deptNo) {
  let p2;
  try {
    p2 = await context.newPage();
    await p2.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await p2.waitForFunction((n) => (document.body.innerText || '').includes(n), deptNo, { timeout: 20000 });
    const el = p2.getByText(deptNo, { exact: true }).first();
    const popupP = context.waitForEvent('page', { timeout: 7000 }).catch(() => null);
    const before = p2.url();
    await el.click({ timeout: 5000 });
    const popup = await popupP;
    let link = '';
    if (popup) {
      for (let i = 0; i < 20 && (!popup.url() || popup.url() === 'about:blank'); i++) await new Promise((r) => setTimeout(r, 250));
      link = popup.url();
      await popup.close().catch(() => {});
    } else {
      await p2.waitForTimeout(1500);
      if (p2.url() !== before) link = p2.url();
    }
    return /^https?:/i.test(link) ? link : '';
  } catch (e) {
    return '';
  } finally {
    if (p2) await p2.close().catch(() => {});
  }
}

/* ----- one tender ----- */

async function openTender(browser, cred, url, holder) {
  const open = async () => {
    holder.context = await newContext(browser, cred, true);
    holder.page = await holder.context.newPage();
    await holder.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    // wait until the page shows tender data OR a login prompt (no fixed sleeps)
    await holder.page.waitForFunction(() => {
      const t = document.body ? document.body.innerText : '';
      return /TID\s*:?\s*\d{5,}/.test(t) || /Login\s*\/\s*Sign\s*Up/i.test(t) || !!document.querySelector('input[type=password]');
    }, null, { timeout: 45000 }).catch(() => {});
    await holder.page.waitForTimeout(400);
  };
  await open();
  if (!(await isLoggedIn(holder.page))) {
    await holder.context.close().catch(() => {});
    await ensureSession(browser, cred); // shared: only one tab logs in, the rest reuse the session
    await open();
    if (!(await isLoggedIn(holder.page))) throw new Error('Could not open the tender while logged in (session problem)');
  }
}

async function detail(cred, url, tidArg) {
  const res = { ok: false, tid: tidArg || '', url: url };
  const holder = { context: null, page: null };
  let createdFolder = '';
  try {
    return await withBrowser(async (browser) => {
      await openTender(browser, cred, url, holder);
      const page = holder.page;
      await page.waitForFunction(() => /Due on/i.test(document.body.innerText), null, { timeout: 25000 }).catch(() => {});
      const d = parseDetail(await page.evaluate(() => document.body.innerText));
      d.tid = d.tid || tidArg;
      if (!d.tid) throw new Error('TID not found on tender page');
      Object.assign(res, d, { final_url: page.url(), tender_url: url, tender_link: page.url() });
      const folderName = makeFolderName(d);
      res.folder_name = folderName;

      // link behind the Dept Tender Number
      let dl = await findDeptLink(page, d.dept_tender_number);
      let deptLink = dl.link;
      if (!deptLink && d.dept_tender_number && dl.clickable) deptLink = await clickForLink(holder.context, url, d.dept_tender_number);
      res.dept_tender_link = deptLink;
      log('tender', d.tid, 'dept no:', d.dept_tender_number || '-', 'link:', deptLink || '(none)', dl.how ? '[' + dl.how + ']' : '');

      // duplicate guard: folder for this TID already on disk with files -> never download twice (just refresh the data)
      const existing = findExisting(d.tid);
      if (existing) {
        const filesDir = ensureFlat(existing, d.tid);
        res.ok = true;
        res.status = 'done';
        res.skipped = true;
        res.path = existing;
        res.files_path = filesDir;
        res.zip_path = zipOf(existing);
        res.files = listFiles(filesDir);
        res.folder_name = path.basename(existing);
        return res;
      }

      await page.getByText(/^\s*Docs\s*$/).first().click({ timeout: 2000 }).catch(() => {});
      const btn = page.locator('a:has-text("Download All"), button:has-text("Download All")').first();
      // the document area loads by ajax: wait for the button, or for the page to say there are none
      await page.waitForFunction(() => { const t = document.body.innerText; return /Download All/i.test(t) || /Documents\s*\(0\)/i.test(t); }, null, { timeout: 15000 }).catch(() => {});
      const hasDocs = await btn.isVisible().catch(() => false);
      // re-read the page now that the document list has loaded
      const d2 = parseDetail(await page.evaluate(() => document.body.innerText));
      res.documents_listed = d2.documents_listed;
      if (!hasDocs) {
        res.ok = true;
        res.status = 'no_documents';
        res.path = '';
        res.files = [];
        return res;
      }

      const folder = path.join(BASE, folderName);
      fs.mkdirSync(folder, { recursive: true });
      createdFolder = folder;

      let dlFile = null;
      for (let attempt = 1; attempt <= 2 && !dlFile; attempt++) {
        try {
          const dlPromise = new Promise((resolve, reject) => {
            const t = setTimeout(() => reject(new Error('Download did not start in time')), 150000);
            const h = (x) => { clearTimeout(t); resolve(x); };
            page.once('download', h);
            holder.context.on('page', (p) => p.once('download', h));
          });
          await btn.click();
          dlFile = await dlPromise;
        } catch (e) {
          if (attempt === 2) throw e;
          log('tender', d.tid, 'download attempt', attempt, 'failed (' + firstLine(e) + '), retrying');
        }
      }

      // 1) keep the downloaded zip   2) unzip everything (zips inside zips too)   3) put EVERY file into ONE flat folder: files/
      const saved = path.join(folder, folderName + '_AllDocuments.zip');
      await dlFile.saveAs(saved);
      const tmp = path.join(folder, '_unzipping');
      fs.mkdirSync(tmp, { recursive: true });
      if (isZip(saved)) unzipRecursive(saved, tmp);
      else fs.copyFileSync(saved, path.join(tmp, dlFile.suggestedFilename() || (folderName + '.bin')));
      const filesDir = path.join(folder, 'files');
      flattenInto(tmp, filesDir, d.tid);
      fs.rmSync(tmp, { recursive: true, force: true });

      res.ok = true;
      res.status = 'done';
      res.path = folder;
      res.files_path = filesDir;
      res.zip_path = saved;
      res.files = listFiles(filesDir);
      return res;
    });
  } catch (e) {
    await snap(holder.page, 'detail_' + (res.tid || 'x'));
    if (createdFolder) { try { fs.rmSync(createdFolder, { recursive: true, force: true }); } catch (x) { /* ignore */ } }
    res.ok = false;
    res.error = firstLine(e);
    return res;
  } finally {
    if (holder.context) await holder.context.close().catch(() => {});
  }
}

/* ======================= API discovery (optional): records which web requests the site makes, secrets masked ======================= */

const SENSITIVE_KEY = /pass|pwd|token|secret|otp|auth|csrf|verification/i;

// every way a secret can appear in a request: plain, JSON-escaped, URL-encoded (also with + for spaces)
function variants(v) {
  v = String(v || '');
  if (!v) return [];
  const set = new Set([v, JSON.stringify(v).slice(1, -1), encodeURIComponent(v), encodeURIComponent(v).replace(/%20/g, '+'), encodeURI(v)]);
  return Array.from(set).filter((x) => x.length > 0).sort((a, b) => b.length - a.length);
}
function maskText(txt, cred) {
  let t = String(txt || '');
  for (const v of variants(cred.password)) t = t.split(v).join('<PASSWORD>');
  for (const v of variants(cred.email)) t = t.split(v).join('<EMAIL>');
  return t;
}
function maskObj(o, cred) {
  if (Array.isArray(o)) return o.slice(0, 5).map((x) => maskObj(x, cred));
  if (o && typeof o === 'object') { const r = {}; for (const k of Object.keys(o)) r[k] = SENSITIVE_KEY.test(k) ? '***' : maskObj(o[k], cred); return r; }
  if (typeof o === 'string') { const m = maskText(o, cred || {}); return m.length > 100 ? m.slice(0, 100) + '...' : m; }
  return o;
}
function maskPost(s, cred) {
  s = maskText(s, cred);
  if (!s) return '';
  try { return JSON.stringify(maskObj(JSON.parse(s), cred)).slice(0, 1500); } catch (e) { /* not JSON */ }
  return s.split('&').map((kv) => { const i = kv.indexOf('='); const k = i < 0 ? kv : kv.slice(0, i); const v = i < 0 ? '' : kv.slice(i + 1); let dk = k; try { dk = decodeURIComponent(k); } catch (e2) { /* keep */ } return SENSITIVE_KEY.test(dk) ? k + '=***' : k + '=' + (v.length > 60 ? v.slice(0, 60) + '...' : v); }).join('&').slice(0, 1500);
}
function shape(v, depth) {
  depth = depth || 0;
  if (Array.isArray(v)) return v.length ? ['array(' + v.length + ') of', shape(v[0], depth + 1)] : 'array(0)';
  if (v && typeof v === 'object') { if (depth > 3) return 'object'; const r = {}; for (const k of Object.keys(v).slice(0, 40)) r[k] = shape(v[k], depth + 1); return r; }
  return typeof v === 'string' ? 'string(' + v.length + ')' : typeof v;
}

async function discover(cred) {
  return await withBrowser(async (browser) => {
    const ctx = await newContext(browser, cred, false, true); // fresh context: no saved session, so the login is recorded too
    const page = await ctx.newPage();
    const events = [];
    const jobs = [];
    const host = new URL(SITE).hostname;
    let phase = 'start';
    page.on('response', (resp) => {
      jobs.push((async () => {
        try {
          const req = resp.request();
          const type = req.resourceType();
          if (!['xhr', 'fetch', 'document', 'other'].includes(type)) return;
          const u = new URL(resp.url());
          if (u.hostname !== host) return;
          const rh = resp.headers();
          const ct = String(rh['content-type'] || '');
          const hdr = req.headers();
          const e = {
            phase: phase, method: req.method(), type: type, status: resp.status(),
            url: maskText(resp.url(), cred).slice(0, 600),
            request_headers: Object.keys(hdr).filter((k) => /^(content-type|x-requested-with|accept|referer|origin)$/i.test(k) || SENSITIVE_KEY.test(k)).reduce((a, k) => { a[k] = SENSITIVE_KEY.test(k) ? '<present, masked>' : hdr[k]; return a; }, {}),
            post_data: maskPost(req.postData(), cred),
            response_type: ct, response_disposition: rh['content-disposition'] || '', response_length: rh['content-length'] || '',
            sets_cookies: String(rh['set-cookie'] || '').split('\n').map((c) => c.split('=')[0]).filter(Boolean),
          };
          if (/json/i.test(ct)) { const body = await resp.text().catch(() => ''); e.body_sample = maskText(body, cred).slice(0, 2500); try { e.json_shape = shape(JSON.parse(body)); } catch (x) { /* ignore */ } }
          else if (/html|text|xml/i.test(ct) && type !== 'document') e.body_sample = maskText(await resp.text().catch(() => ''), cred).slice(0, 800);
          events.push(e);
        } catch (e) { /* page navigated away: ignore */ }
      })());
    });
    const out = { ok: false, note: 'secrets (password, cookies, tokens) are masked; review the file before sharing' };
    try {
      phase = 'login_page';
      await page.goto(LOGIN_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForTimeout(2500);
      out.login_forms = await page.evaluate(() => Array.from(document.forms).map((f) => ({ action: f.action, method: f.method, id: f.id }))).catch(() => []);
      out.hidden_inputs = await page.evaluate(() => Array.from(document.querySelectorAll('input[type=hidden]')).map((i) => ({ name: i.name, id: i.id, value_length: (i.value || '').length }))).catch(() => []);
      phase = 'login';
      await login(page, ctx, cred);
      out.cookies_after_login = (await ctx.cookies()).map((c) => ({ name: c.name, domain: c.domain, httpOnly: c.httpOnly, secure: c.secure, session: c.expires === -1 }));
      phase = 'dashboard';
      await openDashboard(page, ctx, cred);
      phase = 'view_more';
      await loadAll(page, 1);
      const cards = await extractCards(page);
      out.dashboard_links_found = cards.length;
      if (cards.length) {
        phase = 'tender';
        await page.goto(cards[0].url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForFunction(() => /Due on/i.test(document.body.innerText), null, { timeout: 25000 }).catch(() => {});
        out.first_tender_url = cards[0].url;
        phase = 'download';
        const btn = page.locator('a:has-text("Download All"), button:has-text("Download All")').first();
        if (await btn.isVisible().catch(() => false)) {
          const dl = new Promise((resolve) => { const t = setTimeout(() => resolve(null), 60000); page.once('download', (d) => { clearTimeout(t); resolve(d); }); });
          await btn.click();
          const d = await dl;
          if (d) { out.download = { url: maskText(d.url(), cred).slice(0, 600), suggested_filename: d.suggestedFilename() }; await d.delete().catch(() => {}); }
        }
      }
      out.ok = true;
    } catch (e) {
      out.error = firstLine(e);
      await snap(page, 'discover_error');
    }
    await Promise.allSettled(jobs);
    out.events = events;
    try { fs.mkdirSync(DEBUG_DIR, { recursive: true }); out.file = path.join(DEBUG_DIR, 'network_capture.json'); fs.writeFileSync(out.file, JSON.stringify(out, null, 2)); } catch (e) { /* ignore */ }
    await ctx.close().catch(() => {});
    return out;
  });
}

/* ======================= http server ======================= */

function allowedUrl(u) {
  try {
    const x = new URL(u);
    const site = new URL(SITE);
    return x.origin === site.origin || /(^|\.)tendertiger\.com$/i.test(x.hostname);
  } catch (e) { return false; }
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let b = '';
    req.on('data', (d) => { b += d; if (b.length > 5e6) { reject(new Error('body too large')); req.destroy(); } });
    req.on('end', () => { try { resolve(b ? JSON.parse(b) : {}); } catch (e) { reject(new Error('invalid JSON body')); } });
    req.on('error', reject);
  });
}

function send(res, code, obj) {
  const s = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(s) });
  res.end(s);
}

/* ======================= tender library: web page + downloads (files come from Postgres, or disk if not stored) ======================= */

const esc = (v) => String(v === undefined || v === null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtSize = (n) => { n = Number(n) || 0; return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n > 1024 ? Math.round(n / 1024) + ' KB' : n + ' B'; };

function zipFiles(out, paths) {
  try {
    execFileSync('zip', ['-q', '-j', out].concat(paths), { stdio: ['ignore', 'ignore', 'pipe'] });
  } catch (e) {
    if (e.code !== 'ENOENT') throw e;
    execFileSync('python3', ['-c', 'import zipfile,sys,os\nz=zipfile.ZipFile(sys.argv[1],"w",zipfile.ZIP_DEFLATED)\nfor p in sys.argv[2:]: z.write(p,os.path.basename(p))\nz.close()', out].concat(paths), { stdio: ['ignore', 'ignore', 'pipe'] });
  }
}

async function listTenders(q, limit) {
  const like = '%' + String(q || '').trim() + '%';
  const r = await pool.query(
    `SELECT tid, organization, tender_title, department, dept_tender_number, dept_tender_link, tender_link, due_date, download_status,
            file_count, files_in_db, files, zip_path, scraped_at
       FROM tt_tenders
      WHERE $1 = '' OR tid ILIKE $2 OR tender_title ILIKE $2 OR organization ILIKE $2 OR department ILIKE $2 OR dept_tender_number ILIKE $2 OR key_location ILIKE $2
      ORDER BY scraped_at DESC LIMIT $3`, [String(q || '').trim(), like, Math.min(Number(limit) || 100, 500)]);
  return r.rows;
}

function renderLibrary(rows, q) {
  const body = rows.map((t) => {
    const files = (Array.isArray(t.files) ? t.files : []);
    const due = t.due_date ? new Date(t.due_date).toISOString().slice(0, 10) : '';
    const links = [
      t.tender_link ? '<a href="' + esc(t.tender_link) + '" target="_blank" rel="noopener">Tender page</a>' : '',
      t.dept_tender_link ? '<a href="' + esc(t.dept_tender_link) + '" target="_blank" rel="noopener">' + esc(t.dept_tender_number || 'Dept link') + '</a>' : esc(t.dept_tender_number || ''),
    ].filter(Boolean).join(' &middot; ');
    const dl = files.length || t.zip_path
      ? '<a class="btn" href="/d/' + esc(t.tid) + '/all.zip">All files (zip)</a> <a class="btn alt" href="/d/' + esc(t.tid) + '/original.zip">Original zip</a>'
      : '<span class="muted">' + esc(t.download_status || 'no files') + '</span>';
    const list = files.length
      ? '<details><summary>' + files.length + ' file' + (files.length > 1 ? 's' : '') + (t.files_in_db ? ' &middot; stored in Postgres' : '') + '</summary><ul>' +
        files.map((f) => '<li><a href="/d/' + esc(t.tid) + '/f/' + encodeURIComponent(path.basename(f.name)) + '">' + esc(path.basename(f.name)) + '</a> <span class="muted">' + fmtSize(f.size) + '</span></li>').join('') + '</ul></details>'
      : '';
    return '<tr><td class="tid">' + esc(t.tid) + '<div class="muted">' + esc(due ? 'due ' + due : '') + '</div></td><td><b>' + esc(t.tender_title || '(no title)') + '</b><div class="muted">' +
      esc(t.organization) + (t.department ? ' &middot; ' + esc(t.department) : '') + '</div><div class="links">' + links + '</div></td><td>' + dl + list + '</td></tr>';
  }).join('');
  return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tender library</title><style>' +
    ':root{color-scheme:light dark}body{font:15px system-ui,sans-serif;margin:0;padding:24px;max-width:1200px;margin-inline:auto}h1{margin:0 0 4px}.muted{color:#888;font-size:13px}' +
    'form{margin:16px 0}input[type=text]{padding:8px 10px;width:320px;max-width:70%}button,.btn{padding:7px 12px;border:1px solid #888;border-radius:6px;background:#2d6cdf;color:#fff;text-decoration:none;cursor:pointer;font-size:14px;display:inline-block;margin:2px 4px 2px 0}' +
    '.alt{background:transparent;color:inherit}table{border-collapse:collapse;width:100%}td{border-top:1px solid #8884;padding:10px 8px;vertical-align:top}.tid{white-space:nowrap;font-variant-numeric:tabular-nums}.links{font-size:13px;margin-top:4px}details{margin-top:6px}li{margin:2px 0}' +
    '</style></head><body><h1>Tender library</h1><div class="muted">' + rows.length + ' tender' + (rows.length === 1 ? '' : 's') + (q ? ' matching "' + esc(q) + '"' : ' (newest first)') + '</div>' +
    '<form method="get" action="/"><input type="text" name="q" value="' + esc(q) + '" placeholder="Search TID, title, organization, department, number..."> <button type="submit">Search</button></form>' +
    '<table>' + (body || '<tr><td>No tenders yet.</td></tr>') + '</table></body></html>';
}

const MIME = { '.pdf': 'application/pdf', '.zip': 'application/zip', '.xls': 'application/vnd.ms-excel', '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.doc': 'application/msword', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.txt': 'text/plain', '.xml': 'application/xml', '.jpg': 'image/jpeg', '.png': 'image/png' };

function sendFile(res, name, buf) {
  const ascii = String(name).replace(/[^\x20-\x7e]/g, '_').replace(/"/g, '');
  res.writeHead(200, {
    'Content-Type': MIME[path.extname(name).toLowerCase()] || 'application/octet-stream',
    'Content-Length': buf.length,
    'Content-Disposition': 'attachment; filename="' + ascii + '"; filename*=UTF-8\'\'' + encodeURIComponent(name),
  });
  res.end(buf);
}

// returns true when the request was a library/download GET and has been answered
async function handleLibrary(req, res, u, authed) {
  const send404 = (msg) => { res.writeHead(404, { 'Content-Type': 'text/plain' }); res.end(msg || 'not found'); return true; };
  if (u.pathname === '/') {
    if (!authed) {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end('<!doctype html><meta charset="utf-8"><title>Tender library</title><body style="font:16px system-ui;padding:40px"><h2>Tender library</h2><form method="get" action="/">Token: <input type="password" name="token" size="40" autofocus> <button>Open</button></form></body>');
      return true;
    }
    if (u.searchParams.get('token')) { // remember the token in a cookie, then drop it from the address bar
      res.writeHead(302, { 'Set-Cookie': 'tt_token=' + encodeURIComponent(TOKEN) + '; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000', Location: '/' });
      res.end();
      return true;
    }
    const q = u.searchParams.get('q') || '';
    const html = renderLibrary(await listTenders(q, 200), q);
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
    return true;
  }
  if (u.pathname === '/api/tenders') {
    if (!authed) { send(res, 401, { ok: false, error: 'bad or missing token' }); return true; }
    send(res, 200, { ok: true, tenders: await listTenders(u.searchParams.get('q'), u.searchParams.get('limit')) });
    return true;
  }
  const m = u.pathname.match(/^\/d\/(\d{3,})\/(original\.zip|all\.zip|f\/(.+))$/);
  if (!m) return false;
  if (!authed) { send(res, 401, { ok: false, error: 'bad or missing token' }); return true; }
  const tid = m[1];
  const t = (await pool.query('SELECT folder_name, path, files_path, zip_path FROM tt_tenders WHERE tid = $1', [tid])).rows[0];
  if (!t) return send404('unknown tender');

  if (m[2] === 'original.zip') {
    const db = (await pool.query("SELECT file_name, content FROM tt_tender_files WHERE tid = $1 AND kind = 'zip' LIMIT 1", [tid])).rows[0];
    if (db) { sendFile(res, db.file_name, db.content); return true; }
    if (t.zip_path && fs.existsSync(t.zip_path)) { sendFile(res, path.basename(t.zip_path), fs.readFileSync(t.zip_path)); return true; }
    return send404('no zip stored for this tender');
  }
  if (m[2] === 'all.zip') {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ttz-'));
    try {
      let paths = [];
      if (t.files_path && fs.existsSync(t.files_path)) paths = fs.readdirSync(t.files_path).map((f) => path.join(t.files_path, f)).filter((f) => fs.statSync(f).isFile());
      if (!paths.length) {
        const rows = (await pool.query("SELECT file_name, content FROM tt_tender_files WHERE tid = $1 AND kind = 'file' ORDER BY file_name", [tid])).rows;
        paths = rows.map((x) => { const f = path.join(tmp, path.basename(x.file_name)); fs.writeFileSync(f, x.content); return f; });
      }
      if (!paths.length) return send404('no files stored for this tender');
      const out = path.join(tmp, 'all.zip');
      zipFiles(out, paths);
      sendFile(res, (t.folder_name || tid) + '_files.zip', fs.readFileSync(out));
      return true;
    } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
  }
  const name = path.basename(decodeURIComponent(m[3]));
  const db = (await pool.query("SELECT content FROM tt_tender_files WHERE tid = $1 AND kind = 'file' AND file_name = $2", [tid, name])).rows[0];
  if (db) { sendFile(res, name, db.content); return true; }
  const disk = t.files_path ? path.join(t.files_path, name) : '';
  if (disk && fs.existsSync(disk)) { sendFile(res, name, fs.readFileSync(disk)); return true; }
  return send404('file not found');
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  try {
    if (req.method === 'GET' && u.pathname === '/health') {
      const out = { ok: true, service: 'tt_service', version: 2, docs_dir: BASE, site: SITE, concurrency: CONCURRENCY, store_in_db: STORE_MODE };
      try { await ensureSchema(); const r = await pool.query('SELECT count(*)::int AS n FROM tt_tenders'); out.db = true; out.tenders_in_db = r.rows[0].n; const f = await pool.query('SELECT count(*)::int AS n, COALESCE(sum(size),0)::bigint AS bytes FROM tt_tender_files'); out.files_in_db = f.rows[0].n; out.files_in_db_size = fmtSize(f.rows[0].bytes); }
      catch (e) { out.ok = false; out.db = false; out.db_error = e.message; }
      if (u.searchParams.get('deep')) {
        try { const b = await launch(); out.chrome = b.version(); await b.close(); }
        catch (e) { out.ok = false; out.chrome = false; out.chrome_error = firstLine(e); }
      }
      return send(res, out.ok ? 200 : 500, out);
    }
    const cookieTok = decodeURIComponent((String(req.headers.cookie || '').match(/(?:^|;\s*)tt_token=([^;]*)/) || [])[1] || '');
    const authed = !TOKEN || req.headers['x-token'] === TOKEN || u.searchParams.get('token') === TOKEN || (req.method === 'GET' && cookieTok === TOKEN);
    if (req.method === 'GET' && (await handleLibrary(req, res, u, authed))) return;
    if (!authed || (req.method === 'POST' && TOKEN && req.headers['x-token'] !== TOKEN)) return send(res, 401, { ok: false, error: 'bad or missing x-token' });
    if (req.method !== 'POST') return send(res, 404, { ok: false, error: 'not found' });
    const body = await readBody(req);
    if (typeof body.email === 'string') body.email = body.email.trim();
    if (typeof body.password === 'string') body.password = body.password.trim();

    if (u.pathname === '/done-tids') {
      const r = await pool.query(DONE_SQL);
      return send(res, 200, { ok: true, tids: r.rows[0].tids || [] });
    }
    if (u.pathname === '/discover') {
      if (!body.email || !body.password) return send(res, 400, { ok: false, error: 'email and password are required' });
      log('discover requested (recording web requests)');
      const r = await discover(body);
      log('discover done:', (r.events || []).length, 'requests recorded ->', r.file || '');
      return send(res, 200, { ok: r.ok, error: r.error, file: r.file, requests_recorded: (r.events || []).length });
    }
    if (u.pathname === '/collect') {
      if (!body.email || !body.password) return send(res, 400, { ok: false, error: 'email and password are required' });
      log('collect requested');
      const r = await collect(body, body.maxViewMore);
      log('collect done:', r.count, 'links');
      return send(res, 200, r);
    }
    if (u.pathname === '/tender') {
      if (!body.email || !body.password) return send(res, 400, { ok: false, error: 'email and password are required' });
      if (!allowedUrl(body.url)) return send(res, 400, { ok: false, error: 'url must be a tendertiger.com link' });
      await tenderSlots.acquire();
      const t0 = Date.now();
      try {
        log('tender start', body.tid || body.url);
        const r = await detail(body, body.url, body.tid || '');
        if (r.ok) {
          try { await storeFilesInDb(r); } catch (e) { r.files_in_db = 0; r.db_files_error = firstLine(e); log('tender', r.tid, 'could not store files in Postgres:', firstLine(e)); }
          try { await saveTender(r); r.db_saved = true; }
          catch (e) { r.db_saved = false; r.db_error = e.message; r.ok = false; r.error = 'Downloaded but could not save to Postgres: ' + e.message; }
        }
        delete r.raw_detail;
        r.seconds = Math.round((Date.now() - t0) / 100) / 10;
        log('tender finished', r.tid, r.status || '', r.ok ? 'ok' : 'FAILED ' + (r.error || ''), r.seconds + 's');
        return send(res, 200, r);
      } finally {
        tenderSlots.release();
      }
    }
    return send(res, 404, { ok: false, error: 'not found' });
  } catch (e) {
    log('error', e.message);
    return send(res, 500, { ok: false, error: firstLine(e) });
  }
});
server.requestTimeout = 0;      // jobs can run for many minutes
server.headersTimeout = 60000;
server.timeout = 0;

if (require.main === module) {
  if (!TOKEN) { console.error('TT_TOKEN is not set (see service.env)'); process.exit(1); }
  ensureSchema()
    .then(() => log('postgres ok, table "tt_tenders" ready'))
    .catch((e) => log('WARNING postgres not reachable:', e.message))
    .then(() => server.listen(PORT, HOST, () => log('tt_service v2 listening on ' + HOST + ':' + PORT + ', docs dir ' + BASE + ', ' + CONCURRENCY + ' tenders at a time')));
} else {
  module.exports = { slug, isoDate, parseDetail, makeFolderName, findExisting, listFiles, unzipRecursive, flattenInto, ensureFlat, isZip, server, pool, ensureSchema };
}

"""
SORA Video Organizer — Desktop Edition
=======================================
Browser-based tool for organizing SORA video clips by creator account.
Powered by Gemini AI for automatic video description and naming.

QUICK START:
  1. pip install flask opencv-python
  2. Edit the CONFIG section below
  3. Double-click run_sora_organizer.bat
"""

import os, sys, shutil, zipfile, logging, webbrowser, threading, time
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_file, Response

# ════════════════════════════════════════════════════════════════
#  CONFIG  —  Edit everything in this section before running
# ════════════════════════════════════════════════════════════════

# ── Gemini API Key ───────────────────────────────────────────────
# Get a free key at: aistudio.google.com/app/apikey
GEMINI_API_KEY = "AQ.Ab8RN6Jj5JK887rFGBT6pqy8ECjEO-P5KlFAkZk28NVjwG-tlg"

# ── Gemini Model ─────────────────────────────────────────────────
# "gemini-2.0-flash"      → fast, cheap, current default (recommended)
# "gemini-2.5-flash"      → newer, may be more accurate
# If you get a 404 "model not found" error, run list_gemini_models.py
# (in this folder) to see exactly which models your API key can use.
GEMINI_MODEL = "gemini-2.0-flash"

# ── File Paths ──────────────────────────────────────────────────
# Root folder where your creator subfolders will live
WATCH_PATH = r"C:\Users\Admin\iCloudDrive\iCloudDrive\Multiverse\Earth-SORA1"

# Drop video clips here to organize them
INBOX_FOLDER = "_inbox"

# ── Export Mode ─────────────────────────────────────────────────
# "move" → clips moved directly into creator subfolders (default)
# "zip"  → clips packaged into a ZIP file for download
EXPORT_MODE = "move"

# ZIP output path (only used when EXPORT_MODE = "zip")
ZIP_OUTPUT_PATH = r"C:\Users\Admin\Desktop\SORA-Organized.zip"

# ── Video File Types ─────────────────────────────────────────────
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}

# ── Creator / Account Categories ────────────────────────────────
# Format: "number": ("PREFIX-", "Subfolder Name")
# Files will be named: PREFIX-description.mp4
CATEGORIES = {
    "1": ("IlGoticoCreep-", "IlGoticoCreep"),
    "2": ("MoMoms-",        "MoMoms"),
    "3": ("AudreyBlush-",   "AudreyBlush"),
    "4": ("Playground-",    "Playground"),
    "5": ("UGA_irls-",      "UGA_irls"),
    "6": ("WerBinIch-",     "Wer.bin.ich"),
    "7": ("ChasWatkins67-", "ChasWatkins67"),
}

# ════════════════════════════════════════════════════════════════
#  END OF CONFIG  —  No need to edit below this line
# ════════════════════════════════════════════════════════════════

LOG_FILE = Path(__file__).parent / "sora_organizer_log.txt"

logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)

def log(msg):
    print(msg)
    logging.info(msg)

# ── Global State ────────────────────────────────────────────────

files       = []
current_idx = 0
stats       = {"moved": 0, "skipped": 0, "errors": 0}
zip_queue   = []
ugc_root    = Path(WATCH_PATH)
inbox       = ugc_root / INBOX_FOLDER

# ── Gemini Video Analysis ────────────────────────────────────────

def extract_video_frame(video_path: Path) -> bytes:
    """Extract a representative JPEG frame from a video using OpenCV."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open video file")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    target_frame = max(1, int(total_frames * 0.15))  # ~15% into the clip
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        raise RuntimeError("Could not extract a frame from video")

    # Resize if too large
    h, w = frame.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("Could not encode frame as JPEG")
    return buf.tobytes()


def analyze_video_gemini(video_path: Path):
    """Extract a frame from the video and analyze it with Gemini's
    standard generateContent endpoint (no file upload required).
    Returns (suggestion, error_message)."""
    if not GEMINI_API_KEY or "YOUR-GEMINI-KEY" in GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        return None, "No Gemini key — add GEMINI_API_KEY to config"

    try:
        import cv2
    except ImportError:
        msg = "Missing library — run: pip install opencv-python"
        log(f"  ⚠  {msg}")
        return None, msg

    try:
        import urllib.request, json as json_mod, base64 as b64_mod

        log(f"  ↑ Extracting frame from {video_path.name}…")
        frame_bytes = extract_video_frame(video_path)
        b64_frame   = b64_mod.standard_b64encode(frame_bytes).decode("utf-8")

        log(f"  ↑ Sending frame to Gemini…")
        # New "AQ." auth keys must be passed as a header, NOT a query param.
        # Old "AIza" standard keys work with either method, so the header
        # approach below works for both key formats.
        generate_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models"
            f"/{GEMINI_MODEL}:generateContent"
        )
        payload = json_mod.dumps({
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_frame}},
                    {"text": (
                        "Analyze this video frame. Return ONLY a short descriptive filename: "
                        "2-4 words, all lowercase, hyphen-separated, no file extension, no extra text. "
                        "Focus on what is visually happening — subject, action, setting. "
                        "Examples: woman-dancing-rooftop, aerial-city-night, "
                        "fashion-runway-close-up, ocean-waves-sunset."
                    )}
                ]
            }]
        }).encode()

        req = urllib.request.Request(
            generate_url, data=payload,
            headers={
                "Content-Type":  "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            gen_result = json_mod.loads(resp.read())

        raw    = gen_result["candidates"][0]["content"]["parts"][0]["text"].strip().lower()
        result = raw.replace(" ", "-").replace("_", "-")[:60] or None
        if result:
            log(f"  ✓ Gemini: {result}")
            return result, None
        return None, "Gemini returned empty response"

    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        msg  = f"HTTP {e.code}: {body}"
        log(f"  ✕ Gemini error: {msg}")
        return None, msg
    except Exception as e:
        msg = str(e)[:150]
        log(f"  ✕ Gemini error: {msg}")
        return None, msg

# ── Flask Setup ─────────────────────────────────────────────────

app = Flask(__name__)

def load_files():
    global files, current_idx, zip_queue
    if not inbox.exists():
        inbox.mkdir(parents=True)
    files       = sorted([
        f for f in inbox.iterdir()
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    ])
    current_idx = 0
    zip_queue   = []
    log(f"  Found {len(files)} video clip(s) in {INBOX_FOLDER}.")

# ── Routes ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return build_page()

@app.route("/api/status")
def api_status():
    return jsonify({
        "export_mode":    EXPORT_MODE,
        "has_gemini_key": bool(GEMINI_API_KEY and len(GEMINI_API_KEY) > 10 and "YOUR-GEMINI-KEY" not in GEMINI_API_KEY),
        "gemini_model":   GEMINI_MODEL,
    })

@app.route("/api/current")
def api_current():
    if current_idx >= len(files):
        return jsonify({"done": True, "stats": stats, "export_mode": EXPORT_MODE})
    f = files[current_idx]
    return jsonify({
        "done":     False,
        "index":    current_idx,
        "total":    len(files),
        "filename": f.name,
        "stats":    stats,
    })

@app.route("/api/video")
def api_video():
    """Serve current video with range request support for seeking."""
    if current_idx >= len(files):
        return ("", 204)
    f         = files[current_idx]
    file_size = f.stat().st_size
    ext       = f.suffix.lower().lstrip(".")
    mime_map  = {
        "mp4": "video/mp4", "mov": "video/quicktime",
        "m4v": "video/mp4", "webm": "video/webm",
        "avi": "video/avi", "mkv": "video/x-matroska",
    }
    mime_type = mime_map.get(ext, "video/mp4")

    range_hdr = request.headers.get("Range")
    if range_hdr:
        # Parse range header
        byte_range = range_hdr.replace("bytes=", "").split("-")
        byte_start = int(byte_range[0])
        byte_end   = int(byte_range[1]) if byte_range[1] else file_size - 1
        length     = byte_end - byte_start + 1
        with open(f, "rb") as fh:
            fh.seek(byte_start)
            data = fh.read(length)
        return Response(
            data, 206,
            headers={
                "Content-Range":  f"bytes {byte_start}-{byte_end}/{file_size}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(length),
                "Content-Type":   mime_type,
            }
        )
    return send_file(str(f), mimetype=mime_type)

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    if current_idx >= len(files):
        return jsonify({"suggestion": ""})
    suggestion, error = analyze_video_gemini(files[current_idx])
    if suggestion:
        return jsonify({"suggestion": suggestion})
    return jsonify({"suggestion": "", "error": error or "Could not analyze — type a name"})

@app.route("/api/move", methods=["POST"])
def api_move():
    global current_idx
    data     = request.get_json()
    name     = (data.get("name") or "unnamed").strip().lower().replace(" ", "-")
    choice   = str(data.get("category", ""))
    if choice not in CATEGORIES:
        return jsonify({"error": "Invalid category"}), 400

    f                 = files[current_idx]
    prefix, subfolder = CATEGORIES[choice]
    final_name        = f"{prefix}{name}{f.suffix.lower()}"
    dest_dir          = ugc_root / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file         = dest_dir / final_name

    if dest_file.exists():
        ts        = datetime.now().strftime("%H%M%S")
        dest_file = dest_dir / f"{prefix}{name}_{ts}{f.suffix.lower()}"

    try:
        if EXPORT_MODE == "zip":
            zip_queue.append({"src": str(f), "dest": f"{subfolder}/{dest_file.name}"})
            log(f"QUEUED  {f.name}  →  {subfolder}/{dest_file.name}")
        else:
            shutil.move(str(f), str(dest_file))
            log(f"MOVED   {f.name}  →  {subfolder}/{dest_file.name}")
        stats["moved"] += 1
        current_idx    += 1
        return jsonify({"success": True, "dest": dest_file.name})
    except Exception as e:
        log(f"ERROR   {f.name}  --  {e}")
        stats["errors"] += 1
        return jsonify({"error": str(e)}), 500

@app.route("/api/reset", methods=["POST"])
def api_reset():
    global stats
    load_files()
    stats = {"moved": 0, "skipped": 0, "errors": 0}
    count = len(files)
    if count > 0:
        return jsonify({"success": True, "count": count})
    return jsonify({"success": False, "count": 0,
                    "error": f"No video clips found in {INBOX_FOLDER} — drop clips in and try again"})

@app.route("/api/skip", methods=["POST"])
def api_skip():
    global current_idx
    if current_idx < len(files):
        log(f"SKIP    {files[current_idx].name}")
        stats["skipped"] += 1
        current_idx += 1
    return jsonify({"success": True})

@app.route("/api/export-zip")
def api_export_zip():
    if not zip_queue:
        return jsonify({"error": "Nothing queued"}), 400
    zip_path = Path(ZIP_OUTPUT_PATH)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            for item in zip_queue:
                src = Path(item["src"])
                if src.exists():
                    zf.write(src, item["dest"])
                    src.unlink()
        log(f"ZIP  Saved {len(zip_queue)} clips to {zip_path}")
        return send_file(str(zip_path), as_attachment=True, download_name=zip_path.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── HTML Builder ─────────────────────────────────────────────────

def build_page():
    cat_buttons = ""
    for num, (prefix, folder) in CATEGORIES.items():
        cat_buttons += (
            f'<button class="cat-btn" id="cat-{num}" '
            f'onclick="selectCat(\'{num}\')">{folder}</button>\n'
        )
    cats_js = "{\n"
    for num, (prefix, folder) in CATEGORIES.items():
        cats_js += f'  "{num}": "{folder}",\n'
    cats_js += "}"
    html = HTML_TEMPLATE.replace("__CAT_BUTTONS__", cat_buttons)
    html = html.replace("__CATS_JS__", cats_js)
    return html

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SORA Video Organizer</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:     #07070f;
  --panel:  #0d0d1c;
  --border: #1c1c35;
  --accent: #7c3aed;
  --glow:   #a78bfa;
  --text:   #cccce0;
  --muted:  #4a4a62;
  --teal:   #2dd4a0;
  --amber:  #fbbf24;
  --r:      8px;
}
html, body {
  height: 100%; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 13px; overflow: hidden;
}

/* ── Top bar ── */
#topbar {
  position: fixed; top: 0; left: 0; right: 0; height: 44px;
  background: var(--panel); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 18px; gap: 12px; z-index: 10;
}
#app-title {
  font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--accent); white-space: nowrap;
}
#gemini-badge {
  font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px;
  background: rgba(124,58,237,.2); border: 1px solid var(--accent);
  color: var(--accent); letter-spacing: 0.05em; white-space: nowrap;
}
#mode-badge {
  font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px;
  background: rgba(251,191,36,.1); border: 1px solid var(--amber);
  color: var(--amber); letter-spacing: 0.05em; white-space: nowrap;
  display: none;
}
#progress-wrap { flex: 1; height: 3px; background: var(--border); border-radius: 2px; overflow: hidden; }
#progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--glow)); width: 0%; transition: width .4s; }
#topbar-counter { font-size: 11px; color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }
#topbar-stats   { font-size: 11px; color: var(--muted); white-space: nowrap; }

/* ── Layout ── */
#layout { display: grid; grid-template-columns: 1fr 340px; height: 100vh; padding-top: 44px; }

/* ── Video pane ── */
#vid-pane {
  background: #000; display: flex; align-items: center;
  justify-content: center; position: relative; overflow: hidden;
}
#video-player {
  max-width: 100%; max-height: 100%; object-fit: contain;
  display: none; background: #000;
}
#vid-loading {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px; color: var(--muted);
}
.spinner-ring {
  width: 36px; height: 36px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Side panel ── */
#side {
  background: var(--panel); border-left: 1px solid var(--border);
  display: flex; flex-direction: column; overflow-y: auto;
}
.s-section { padding: 14px 16px; border-bottom: 1px solid var(--border); }
.s-label {
  font-size: 10px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 8px;
}
#fname-tag {
  font-size: 11px; color: var(--muted);
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  word-break: break-all;
}

/* ── Suggestion box ── */
#suggest-box {
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--r);
  padding: 10px 12px; min-height: 48px;
}
#suggest-status { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
.pulse {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent); animation: pulse .9s ease-in-out infinite;
  vertical-align: middle; margin-right: 5px;
}
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.7)} }
#suggest-text {
  font-size: 13px; color: var(--teal);
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  word-break: break-all;
}

/* ── Name input ── */
#name-input {
  width: 100%; background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--r); color: var(--text); font-size: 13px;
  padding: 10px 12px; outline: none;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
}
#name-input:focus { border-color: var(--accent); }
.hint { font-size: 10px; color: var(--muted); margin-top: 5px; }
kbd { background: var(--border); border-radius: 3px; padding: 1px 5px; font-size: 10px; }

/* ── Category grid ── */
#cat-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.cat-btn {
  background: var(--bg); border: 1px solid var(--border); border-radius: 7px;
  color: var(--text); font-size: 11px; font-weight: 600; padding: 11px 6px;
  text-align: center; cursor: pointer; letter-spacing: .02em;
  transition: background .12s, border-color .12s;
}
.cat-btn:hover  { border-color: var(--accent); color: #fff; }
.cat-btn.active { background: var(--accent); border-color: var(--glow); color: #fff; }

/* ── Actions ── */
#actions { display: grid; grid-template-columns: 1fr 2fr; gap: 8px; }
#btn-skip {
  background: transparent; border: 1px solid var(--border); border-radius: var(--r);
  color: var(--muted); font-size: 13px; padding: 12px; cursor: pointer;
}
#btn-skip:hover { border-color: #f87171; color: #f87171; }
#btn-confirm {
  background: var(--border); border: none; border-radius: var(--r);
  color: var(--muted); font-size: 13px; font-weight: 700; padding: 12px;
  cursor: default; transition: background .2s, color .2s;
}
#btn-confirm.ready { background: var(--accent); color: #fff; cursor: pointer; }
#btn-confirm.ready:hover { background: var(--glow); }

/* ── Done screen ── */
#done-screen {
  display: none; position: fixed; inset: 0; background: var(--bg);
  flex-direction: column; align-items: center; justify-content: center;
  gap: 16px; text-align: center;
}
#done-glyph { font-size: 48px; opacity: .15; letter-spacing: -2px; }
#done-screen h2 { font-size: 22px; font-weight: 800; color: #fff; }
.pill {
  display: inline-block; background: var(--panel); border: 1px solid var(--border);
  border-radius: 20px; padding: 5px 14px; font-size: 12px; margin: 3px;
}
#btn-zip {
  margin-top: 8px; background: var(--teal); color: #000;
  font-size: 14px; font-weight: 800; padding: 14px 32px;
  border: none; border-radius: var(--r); cursor: pointer; display: none;
}
#btn-zip:hover { opacity: .88; }
.done-note { font-size: 11px; color: var(--muted); max-width: 360px; line-height: 1.6; }
</style>
</head>
<body>

<div id="topbar">
  <span id="app-title">SORA Organizer</span>
  <span id="gemini-badge">Gemini</span>
  <span id="mode-badge">ZIP MODE</span>
  <div id="progress-wrap"><div id="progress-fill"></div></div>
  <span id="topbar-counter">— / —</span>
  <span id="topbar-stats"></span>
</div>

<div id="layout">
  <div id="vid-pane">
    <video id="video-player" controls autoplay muted loop>
      Your browser does not support HTML5 video.
    </video>
    <div id="vid-loading">
      <div class="spinner-ring"></div>
      <span>Loading clip…</span>
    </div>
  </div>

  <div id="side">
    <div class="s-section">
      <div class="s-label">Current Clip</div>
      <div id="fname-tag">—</div>
    </div>

    <div class="s-section">
      <div class="s-label">Gemini Description</div>
      <div id="suggest-box">
        <div id="suggest-status">—</div>
        <div id="suggest-text">—</div>
      </div>
    </div>

    <div class="s-section">
      <div class="s-label">File Name</div>
      <input id="name-input" type="text" placeholder="descriptive-name-here"
             autocomplete="off" spellcheck="false">
      <div class="hint"><kbd>Enter</kbd> to confirm &nbsp;·&nbsp; <kbd>S</kbd> to skip</div>
    </div>

    <div class="s-section" style="flex:1">
      <div class="s-label">Creator / Account</div>
      <div id="cat-grid">
        __CAT_BUTTONS__
      </div>
    </div>

    <div class="s-section">
      <div id="actions">
        <button id="btn-skip"    onclick="skipFile()">Skip →</button>
        <button id="btn-confirm" onclick="submitFile()">Move Clip →</button>
      </div>
    </div>
  </div>
</div>

<div id="done-screen">
  <div id="done-glyph">▶ ∅ ◀</div>
  <h2>All Clips Organized</h2>
  <p id="done-stats"></p>
  <button id="btn-zip" onclick="downloadZip()">⬇ Download ZIP</button>
  <button id="btn-rescan" onclick="rescanInbox()"
    style="margin-top:4px;background:var(--panel);border:1px solid var(--border);
    border-radius:var(--r);color:var(--text);font-size:13px;font-weight:600;
    padding:12px 28px;cursor:pointer;">
    ↺ Scan Inbox Again
  </button>
  <p class="done-note" id="done-note">
    Drop more clips into <code style="color:#555">_inbox</code>,
    then tap <strong>Scan Inbox Again</strong> — no restart needed.
  </p>
</div>

<script>
const CATS = __CATS_JS__;
let selectedCat = null;
let exportMode  = 'move';

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  const s = await (await fetch('/api/status')).json();
  exportMode = s.export_mode;

  if (exportMode === 'zip') {
    document.getElementById('mode-badge').style.display = 'inline-block';
    document.getElementById('btn-confirm').textContent  = 'Queue Clip →';
  }

  const badge = document.getElementById('gemini-badge');
  badge.textContent = s.has_gemini_key
    ? `Gemini ✓  ${s.gemini_model}`
    : 'No Gemini Key';
  if (!s.has_gemini_key) badge.style.color = '#f87171';

  loadCurrent();
}

// ── Load current clip ─────────────────────────────────────────────

async function loadCurrent() {
  const res  = await fetch('/api/current');
  const data = await res.json();

  if (data.done) { showDone(data.stats, data.export_mode); return; }

  const pct = data.total > 0 ? (data.index / data.total * 100).toFixed(1) : 0;
  document.getElementById('progress-fill').style.width  = pct + '%';
  document.getElementById('topbar-counter').textContent = (data.index + 1) + ' / ' + data.total;
  updateStats(data.stats);

  document.getElementById('fname-tag').textContent = data.filename;
  document.getElementById('name-input').value      = '';
  resetCat();
  setReady(false);

  loadVideo();
}

// ── Video player ──────────────────────────────────────────────────

function loadVideo() {
  const player  = document.getElementById('video-player');
  const loading = document.getElementById('vid-loading');

  player.style.display  = 'none';
  loading.style.display = 'flex';

  player.oncanplay = () => {
    loading.style.display = 'none';
    player.style.display  = 'block';
  };

  player.src = '/api/video?' + Date.now();
  player.load();

  // Analyze in parallel while video loads
  analyzeClip();
}

async function analyzeClip() {
  setSuggestion('Uploading to Gemini…', true);
  const res  = await fetch('/api/analyze', { method: 'POST' });
  const data = await res.json();
  const s    = (data.suggestion || '').trim();
  if (s) {
    setSuggestion(s, false, true);
    document.getElementById('name-input').value = s;
    checkReady();
  } else {
    setSuggestion(data.error || 'No suggestion — type a name below', false, false);
    document.getElementById('name-input').focus();
  }
}

function setSuggestion(text, loading, success) {
  const status = document.getElementById('suggest-status');
  const disp   = document.getElementById('suggest-text');
  if (loading) {
    status.innerHTML = '<span class="pulse"></span> Uploading to Gemini…';
    disp.style.color = 'var(--muted)';
    disp.textContent = text;
  } else if (success) {
    status.innerHTML = '<span style="color:var(--teal)">✓</span> Description ready';
    disp.style.color = 'var(--teal)';
    disp.textContent = text;
  } else {
    status.innerHTML = '<span style="color:var(--red)">✕</span> Analysis failed';
    disp.style.color = 'var(--red)';
    disp.textContent = text;
  }
}

// ── Categories ────────────────────────────────────────────────────

function selectCat(num) {
  if (selectedCat) document.getElementById('cat-' + selectedCat)?.classList.remove('active');
  selectedCat = num;
  document.getElementById('cat-' + num)?.classList.add('active');
  checkReady();
}

function resetCat() {
  if (selectedCat) document.getElementById('cat-' + selectedCat)?.classList.remove('active');
  selectedCat = null;
}

// ── Move / Skip ───────────────────────────────────────────────────

function checkReady() {
  const name = document.getElementById('name-input').value.trim();
  setReady(!!(name && selectedCat));
}

function setReady(r) {
  document.getElementById('btn-confirm').classList.toggle('ready', r);
}

async function submitFile() {
  const name = document.getElementById('name-input').value.trim();
  if (!name || !selectedCat) return;
  const res  = await fetch('/api/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ name, category: selectedCat }),
  });
  const data = await res.json();
  if (data.success) loadCurrent();
  else alert('Error: ' + (data.error || 'unknown'));
}

async function skipFile() {
  await fetch('/api/skip', { method: 'POST' });
  loadCurrent();
}

// ── Done ──────────────────────────────────────────────────────────

function showDone(s) {
  document.getElementById('layout').style.display  = 'none';
  document.getElementById('topbar').style.display  = 'none';
  const d = document.getElementById('done-screen');
  d.style.display = 'flex';
  document.getElementById('done-stats').innerHTML =
    '<span class="pill">▶ ' + s.moved   + ' organized</span>' +
    '<span class="pill">→ ' + s.skipped + ' skipped</span>'   +
    '<span class="pill">✕ ' + s.errors  + ' errors</span>';
  if (exportMode === 'zip' && s.moved > 0) {
    document.getElementById('btn-zip').style.display = 'block';
    document.getElementById('done-note').textContent =
      'Click Download ZIP to get all organized clips in one file.';
  }
}

async function rescanInbox() {
  const btn = document.getElementById('btn-rescan');
  btn.textContent = 'Scanning…';
  btn.disabled    = true;
  try {
    const res  = await fetch('/api/reset', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      // Reset local state and return to organize screen
      document.getElementById('done-screen').style.display  = 'none';
      document.getElementById('layout').style.display       = '';
      document.getElementById('topbar').style.display       = '';
      selectedCat = null;
      loadCurrent();
    } else {
      alert(data.error || 'No clips found in inbox. Add clips and try again.');
      btn.textContent = '↺ Scan Inbox Again';
      btn.disabled    = false;
    }
  } catch(e) {
    alert('Reset failed: ' + e.message);
    btn.textContent = '↺ Scan Inbox Again';
    btn.disabled    = false;
  }
}

async function downloadZip() {
  const btn = document.getElementById('btn-zip');
  btn.textContent = 'Building ZIP…';
  btn.disabled    = true;
  window.location.href = '/api/export-zip';
  setTimeout(() => { btn.textContent = '⬇ Download ZIP'; btn.disabled = false; }, 4000);
}

// ── Stats / Progress ──────────────────────────────────────────────

function updateStats(s) {
  document.getElementById('topbar-stats').innerHTML =
    '▶ ' + s.moved + '  →  ' + s.skipped + '  ✕  ' + s.errors;
}

// ── Keyboard ──────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  if (document.activeElement.tagName === 'INPUT') {
    if (e.key === 'Enter') submitFile();
    return;
  }
  if (e.key === 's' || e.key === 'S') { skipFile(); return; }
  if (e.key === 'Enter')              { submitFile(); return; }
  const n = parseInt(e.key);
  if (!isNaN(n) && n >= 1 && n <= 7)  { selectCat(String(n)); }
});

document.getElementById('name-input').addEventListener('input', checkReady);

init();
</script>
</body>
</html>"""

# ── Launch ───────────────────────────────────────────────────────

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:5175")

def main():
    print("\n" + "═" * 55)
    print("  SORA Video Organizer — Desktop Edition")
    print(f"  Gemini Model : {GEMINI_MODEL}")
    print(f"  Export Mode  : {EXPORT_MODE.upper()}")
    print("═" * 55)

    if not GEMINI_API_KEY or "YOUR-GEMINI-KEY" in GEMINI_API_KEY or len(GEMINI_API_KEY) < 10:
        print("\n  ⚠  No Gemini API key set.")
        print("     Edit GEMINI_API_KEY at the top of this file.")
        print("     Get a free key at: aistudio.google.com/app/apikey\n")

    if not ugc_root.exists():
        print(f"\n  ✕  Folder not found: {ugc_root}")
        print("     Edit WATCH_PATH at the top of this file.\n")
        input("Press Enter to exit...")
        return

    load_files()

    if not files:
        print(f"\n  Inbox is empty — no video clips found.")
        print(f"  Drop clips into: {inbox}\n")
        input("Press Enter to exit...")
        return

    print(f"\n  ✓  {len(files)} clip(s) ready in inbox")
    print(f"  ✓  Opening at http://127.0.0.1:5175")
    print(f"  ✗  Press Ctrl+C to stop\n")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        app.run(host="127.0.0.1", port=5175, debug=False, use_reloader=False)
    except OSError:
        print("\n  Port 5175 is in use. Close the previous session and retry.\n")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()

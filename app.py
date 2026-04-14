from __future__ import annotations

import hashlib
import html
import math
import os
import random
import sqlite3
import sys
import textwrap
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import urlencode, urlparse
from uuid import uuid4

import requests
from flask import Flask, redirect, render_template, request, session, url_for, Response, make_response
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from src.config import DATA_RAW, ROOT, UPLOAD_DIR
from src.predict import compare_thumbnails, predict_thumbnail
from src.utils import ensure_dirs

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# When __name__ is "__main__", Flask defaults template/static roots to CWD — wrong if you
# start the server from another folder. Pin paths to this file's directory.
_APP_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(_APP_DIR / "templates"),
    static_folder=str(_APP_DIR / "static"),
    static_url_path="/static",
)
app.secret_key = os.getenv("APP_SECRET", "change-me-local-secret")


def _load_embedded_ui_css() -> str:
    """Ship UI CSS inline so the app looks correct even if /static is blocked or mis-pathed."""
    path = _APP_DIR / "static" / "css" / "app.css"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return (
            ":root{--accent:#6366f1;--bg-app:#0f172a;--text:#f8fafc;}"
            "body{margin:0;font-family:system-ui,sans-serif;background:var(--bg-app);color:var(--text);}"
            ".auth-page{min-height:100vh;display:grid;grid-template-columns:1fr 1fr;}"
            ".auth-brand{background:linear-gradient(135deg,#1e1b4b,#4f46e5);padding:2rem;color:#fff;}"
            ".auth-forms{padding:2rem;}"
        )


EMBEDDED_UI_CSS = _load_embedded_ui_css()
UI_ASSET_VERSION = "20260431"


def _safe_next_url(candidate: str | None) -> str | None:
    """Allow only same-origin relative paths (avoid open redirects)."""
    if not candidate:
        return None
    c = candidate.strip()
    if not c.startswith("/") or c.startswith("//"):
        return None
    if any(ch in c for ch in ("\n", "\r", "\\")):
        return None
    parsed = urlparse(c)
    if parsed.scheme or parsed.netloc:
        return None
    return c


def _auth_next_for_template() -> str | None:
    if session.get("user_email"):
        return None
    return _safe_next_url(request.form.get("next")) or _safe_next_url(request.args.get("next"))


def _guest_active_nav(auth_next: str | None) -> str:
    if not auth_next:
        return ""
    if auth_next.startswith("/feature/"):
        name = auth_next[9:].split("?")[0].strip("/")
        if name in FEATURE_PAGES:
            return name
    if auth_next.startswith("/dashboard"):
        return "dashboard"
    return ""


def _load_static_text(*relative_parts: str) -> str:
    path = _APP_DIR.joinpath("static", *relative_parts)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


# Inlined into thumbnail_studio.html so the page works even when /static is blocked.
STUDIO_PAGE_CSS = _load_static_text("css", "thumbnail-studio.css")
STUDIO_PAGE_JS = _load_static_text("js", "thumbnail-studio.js")


@app.after_request
def _security_and_cache_headers(response: Response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    if app.debug and response.mimetype and "html" in response.mimetype:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


RECENT_RESULTS: dict[str, list[dict]] = {}
DB_PATH = ROOT / "app.db"
CREATED_DIR = DATA_RAW / "created"
DOWNLOAD_DIR = DATA_RAW / "downloads"


# Feature panel HTML (reused after POST so the page is never blank).
FEATURE_PAGES: dict[str, str] = {
    "rater": """
        <div class="ts-card">
        <h3>Thumbnail rater</h3>
        <p class="lead">Upload a frame, add optional metadata, and get an instant model score.</p>
        <form method="post" action="/predict" enctype="multipart/form-data">
          <label class="ts-label" for="predict-file">Image</label>
          <input class="ts-input" id="predict-file" name="image_file" type="file" accept=".jpg,.jpeg,.png,.webp" required />
          <img id="predict-preview" class="preview" alt="" />
          <label class="ts-label" for="predict-title">Video title</label>
          <input class="ts-input" id="predict-title" name="title" placeholder="Video title" />
          <label class="ts-label" for="predict-dur">Duration (seconds)</label>
          <input class="ts-input" id="predict-dur" name="duration_seconds" type="number" min="0" value="0" />
          <button class="ts-btn ts-btn--primary" type="submit">Rate thumbnail</button>
        </form></div>
        """,
    "ab": """
        <div class="ts-card">
        <h3>A/B tester</h3>
        <p class="lead">Compare your live thumbnail against a candidate and see which the model favors.</p>
        <form method="post" action="/compare" enctype="multipart/form-data">
          <label class="ts-label" for="current-file">Current thumbnail</label>
          <input class="ts-input" id="current-file" name="current_image_file" type="file" accept=".jpg,.jpeg,.png,.webp" required />
          <img id="current-preview" class="preview" alt="" />
          <label class="ts-label" for="candidate-file">Candidate thumbnail</label>
          <input class="ts-input" id="candidate-file" name="candidate_image_file" type="file" accept=".jpg,.jpeg,.png,.webp" required />
          <img id="candidate-preview" class="preview" alt="" />
          <label class="ts-label" for="ab-title">Video title</label>
          <input class="ts-input" id="ab-title" name="title" placeholder="Video title" />
          <label class="ts-label" for="ab-dur">Duration (seconds)</label>
          <input class="ts-input" id="ab-dur" name="duration_seconds" type="number" min="0" value="0" />
          <button class="ts-btn ts-btn--primary" type="submit">Run A/B test</button>
        </form></div>
        """,
    "creator": """
        <div class="ts-card">
        <h3>AI creator <span class="ts-badge">New</span></h3>
        <p class="lead">Free sources only: <strong>Wikimedia Commons</strong> (keyword match) → <strong>Lorem Picsum</strong> fallback → abstract if offline. No API keys. Check Commons license before commercial use.</p>
        <form method="post" action="/creator">
          <label class="ts-label" for="creator-text">Headline / hook</label>
          <input class="ts-input" id="creator-text" name="creator_text" placeholder="e.g. Tokyo street food at midnight" required />
          <label class="ts-label" for="creator-style">Background</label>
          <select class="ts-select" id="creator-style" name="creator_style">
            <option value="photo">Photo + headline (recommended)</option>
            <option value="abstract">Abstract only (100% offline)</option>
          </select>
          <label class="ts-label" for="creator-source">Photo source (when using photo)</label>
          <select class="ts-select" id="creator-source" name="creator_source">
            <option value="auto">Smart: Commons search, then Picsum</option>
            <option value="commons">Wikimedia Commons only</option>
            <option value="picsum">Random themed Picsum only</option>
          </select>
          <label class="ts-label" for="creator-mood">Color mood</label>
          <select class="ts-select" id="creator-mood" name="creator_mood">
            <option value="original">Original colors</option>
            <option value="cinematic">Cinematic (darker, muted)</option>
            <option value="vibrant">Vibrant (punchy)</option>
            <option value="clean">Clean + contrast</option>
          </select>
          <button class="ts-btn ts-btn--secondary" type="submit">Generate thumbnail</button>
        </form></div>
        """,
    "ideas": """
        <div class="ts-card">
        <h3>Title hooks</h3>
        <p class="lead">Turn a topic into starter headlines you can refine for your channel.</p>
        <form method="post" action="/ideas">
          <label class="ts-label" for="ideas-topic">Topic</label>
          <input class="ts-input" id="ideas-topic" name="topic" placeholder="Topic" required />
          <button class="ts-btn ts-btn--secondary" type="submit">Generate ideas</button>
        </form></div>
        """,
    "downloader": """
        <div class="ts-card">
        <h3>Downloader</h3>
        <p class="lead">Save an image from a direct URL into your local project folder.</p>
        <form method="post" action="/downloader">
          <label class="ts-label" for="dl-url">Image URL</label>
          <input class="ts-input" id="dl-url" name="image_url" placeholder="https://…" required />
          <button class="ts-btn ts-btn--secondary" type="submit">Download</button>
        </form></div>
        """,
    "projects": """
        <div class="ts-card">
        <h3>Projects / workspaces</h3>
        <p class="lead">Lightweight labels for batches of work — stored in your local database.</p>
        <form method="post" action="/projects/create">
          <label class="ts-label" for="proj-name">Workspace name</label>
          <input class="ts-input" id="proj-name" name="name" placeholder="Workspace name" required />
          <label class="ts-label" for="proj-notes">Notes</label>
          <textarea class="ts-textarea" id="proj-notes" name="notes" placeholder="Notes"></textarea>
          <button class="ts-btn ts-btn--primary" type="submit">Create workspace</button>
        </form></div>
        """,
    "reports": """
        <div class="ts-card">
        <h3>Reports</h3>
        <p class="lead">Export recent rater and A/B activity from this session.</p>
        <div class="row-actions">
          <a class="ts-btn ts-btn--secondary" href="/reports/download?format=csv" style="text-decoration:none">Download CSV</a>
          <a class="ts-btn ts-btn--secondary" href="/reports/download?format=txt" style="text-decoration:none">Download TXT</a>
        </div></div>
        """,
}


def _predict_result_card(view: dict) -> str:
    v = view.get("verdict", "")
    cls = "good" if v == "likely_good" else "weak"
    pct = float(view.get("probability_percent", 0))
    pct = min(100.0, max(0.0, pct))
    return f"""
        <div class="ts-card"><h3>Rater result</h3>
        <div class="grid-2">
          <div class="metric-box"><div class="lbl">Score</div><div class="val">{pct}%</div>
            <div class="bar-wrap"><div class="bar" style="width: {pct}%"></div></div>
          </div>
          <div class="metric-box"><div class="lbl">Verdict</div><div class="val"><span class="pill {cls}">{v}</span></div></div>
        </div></div>
        """


def _compare_result_card(view: dict) -> str:
    rec = view.get("recommendation", "")
    cls = "good" if rec == "use_candidate" else "weak"
    return f"""
        <div class="ts-card"><h3>A/B result</h3>
        <div class="grid-2">
          <div class="metric-box"><div class="lbl">Current</div><div class="val">{view.get("current_percent", 0)}%</div></div>
          <div class="metric-box"><div class="lbl">Candidate</div><div class="val">{view.get("candidate_percent", 0)}%</div></div>
          <div class="metric-box"><div class="lbl">Delta</div><div class="val">{view.get("delta_percent", 0)}%</div></div>
          <div class="metric-box"><div class="lbl">Pick</div><div class="val"><span class="pill {cls}">{rec}</span></div></div>
        </div></div>
        """


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              password_hash TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_email TEXT NOT NULL,
              name TEXT NOT NULL,
              notes TEXT DEFAULT ''
            )
            """
        )


def _require_login():
    if "user_email" not in session:
        return redirect(url_for("home"))
    return None


def _parse_duration(value: str | None) -> int:
    try:
        return max(int(value or "0"), 0)
    except Exception:
        return 0


def _save_uploaded_image(file_key: str) -> Path:
    ensure_dirs(UPLOAD_DIR)
    uploaded = request.files.get(file_key)
    if uploaded is None or not uploaded.filename:
        raise ValueError("Please upload an image file.")
    filename = secure_filename(uploaded.filename)
    ext = Path(filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Unsupported file type. Use jpg, jpeg, png, or webp.")
    out_path = UPLOAD_DIR / f"{uuid4().hex}{ext}"
    uploaded.save(out_path)
    return out_path


def _predict_view(result: dict) -> dict:
    return {
        "type": "predict",
        "probability_percent": round(float(result.get("probability_good", 0.0)) * 100, 1),
        "verdict": result.get("verdict", "likely_weak"),
        "model_mode": result.get("model_mode", "global_baseline"),
        "channel_model_weight": result.get("channel_model_weight", 0.0),
    }


def _compare_view(result: dict) -> dict:
    current = float(result.get("current", {}).get("probability_good", 0.0))
    candidate = float(result.get("candidate", {}).get("probability_good", 0.0))
    delta = float(result.get("probability_delta", 0.0))
    return {
        "type": "compare",
        "current_percent": round(current * 100, 1),
        "candidate_percent": round(candidate * 100, 1),
        "delta_percent": round(delta * 100, 1),
        "recommendation": result.get("recommendation", "keep_current"),
    }


def _render(result=None, error=None, success=None, creator_image=None, ideas=None, downloaded=None):
    if session.pop("signup_success", None):
        success = success or "Account created. Sign in below to open your workspace."
    user = session.get("user_email")
    history = RECENT_RESULTS.get(user, [])[:8] if user else []
    nav_items = [
        {"id": "studio", "label": "Create your thumbnail", "url": "/studio", "requires_auth": False},
        {"id": "dashboard", "label": "Dashboard", "url": "/dashboard", "requires_auth": True},
        {"id": "rater", "label": "Thumbnail Rater", "url": "/feature/rater", "requires_auth": True},
        {"id": "ab", "label": "A/B Tester", "url": "/feature/ab", "requires_auth": True},
        {"id": "creator", "label": "AI Creator (New)", "url": "/feature/creator", "requires_auth": True},
        {"id": "ideas", "label": "Thumbnail Ideas", "url": "/feature/ideas", "requires_auth": True},
        {"id": "downloader", "label": "Downloader", "url": "/feature/downloader", "requires_auth": True},
        {"id": "projects", "label": "Projects / Workspaces", "url": "/feature/projects", "requires_auth": True},
        {"id": "reports", "label": "Reports", "url": "/feature/reports", "requires_auth": True},
    ]
    auth_next = _auth_next_for_template()
    if user:
        active = session.get("active_feature", "dashboard")
    else:
        active = _guest_active_nav(auth_next)
    content = session.pop("page_content", "")
    google_ready = bool(
        os.getenv("GOOGLE_CLIENT_ID")
        and os.getenv("GOOGLE_CLIENT_SECRET")
        and os.getenv("GOOGLE_REDIRECT_URI")
    )
    return render_template(
        "layout.html",
        user=user,
        result=result,
        error=error,
        success=success,
        creator_image=creator_image,
        ideas=ideas or [],
        downloaded=downloaded,
        history=history,
        nav_items=nav_items,
        active=active,
        content=content,
        google_ready=google_ready,
        auth_next=auth_next or "",
        asset_v=UI_ASSET_VERSION,
        embedded_stylesheet=EMBEDDED_UI_CSS,
    )


@app.get("/")
def home() -> str:
    return _render()


@app.post("/signup")
def signup() -> str:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_after = _safe_next_url(request.form.get("next"))
    if not email or not password:
        return _render(error="Email and password are required.")
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO users(email, password_hash) VALUES(?, ?)",
                (email, generate_password_hash(password)),
            )
        session["signup_success"] = True
        if next_after:
            return redirect(url_for("home", next=next_after))
        return redirect(url_for("home"))
    except sqlite3.IntegrityError:
        return _render(error="Email already registered.")


@app.post("/login")
def login() -> str:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    with _db() as conn:
        row = conn.execute("SELECT email, password_hash FROM users WHERE email=?", (email,)).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        session["user_email"] = row["email"]
        nxt = _safe_next_url(request.form.get("next"))
        return redirect(nxt or url_for("dashboard"))
    return _render(error="Invalid credentials.")


@app.get("/login/google")
def google_login():
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    redirect_uri = (os.getenv("GOOGLE_REDIRECT_URI") or "").strip()
    if not client_id or not redirect_uri:
        return _render(
            error="Google login is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI to your .env file."
        )
    state = uuid4().hex
    session["oauth_state"] = state
    oauth_next = _safe_next_url(request.args.get("next"))
    if oauth_next:
        session["oauth_next"] = oauth_next
    else:
        session.pop("oauth_next", None)
    session.permanent = True
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account consent",
        "include_granted_scopes": "true",
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.get("/auth/google/callback")
def google_callback():
    if request.args.get("error"):
        desc = request.args.get("error_description") or request.args.get("error") or "unknown"
        return _render(error=f"Google sign-in did not complete: {desc}")

    if request.args.get("state") != session.get("oauth_state"):
        return _render(error="Invalid or expired sign-in session. Please try Google login again.")

    code = request.args.get("code")
    if not code:
        return _render(error="Missing authorization code from Google.")

    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("GOOGLE_REDIRECT_URI") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        return _render(error="Google OAuth is missing client id, secret, or redirect URI in environment.")

    try:
        token_res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=25,
        )
        token_json = token_res.json()
        if token_res.status_code != 200:
            err = token_json.get("error_description") or token_json.get("error") or token_res.text[:200]
            return _render(error=f"Google token exchange failed: {err}")
        access_token = token_json.get("access_token")
        if not access_token:
            return _render(error="Google did not return an access token. Check client secret and redirect URI.")

        profile_res = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            params={"alt": "json"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if profile_res.status_code != 200:
            return _render(error="Could not read your Google profile. Try again.")
        profile = profile_res.json()
        email = (profile.get("email") or "").strip().lower()
        if not email:
            return _render(error="Google did not share an email. Use an account with email visible to this app.")
    except requests.RequestException as exc:
        return _render(error=f"Network error talking to Google: {exc}")

    with _db() as conn:
        row = conn.execute("SELECT email FROM users WHERE email=?", (email,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users(email, password_hash) VALUES(?, ?)",
                (email, generate_password_hash(uuid4().hex)),
            )
    session["user_email"] = email
    session.pop("oauth_state", None)
    nxt = session.pop("oauth_next", None)
    return redirect(nxt or url_for("dashboard"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/build-info")
def build_info() -> dict:
    """JSON probe for debugging deployments; also useful in README demos."""
    rules = {r.rule for r in app.url_map.iter_rules()}
    return {
        "app": "thumbnail-studio",
        "ui_version": UI_ASSET_VERSION,
        "embedded_css_chars": len(EMBEDDED_UI_CSS),
        "templates": str(_APP_DIR / "templates"),
        "static": str(_APP_DIR / "static"),
        "has_route_studio": "/studio" in rules,
        "has_route_health": "/health" in rules,
    }


def _require_login_redirect():
    if "user_email" not in session:
        nxt = request.full_path
        if nxt.endswith("?"):
            nxt = nxt[:-1]
        return redirect(url_for("home", next=nxt))
    return None


def _set_content(html: str, feature: str) -> None:
    session["page_content"] = html
    session["active_feature"] = feature


@app.get("/dashboard")
def dashboard():
    if (resp := _require_login_redirect()) is not None:
        return resp
    _set_content("", "dashboard")
    return _render()


@app.get("/studio")
def thumbnail_studio():
    """Interactive 16:9 manual thumbnail composer (Canvas + client-side export).

    Public route so the canvas works without signing in (avoids confusing redirects).
    CSS/JS are inlined in HTML so a single request loads the full tool.
    """
    studio_css = _load_static_text("css", "thumbnail-studio.css")
    studio_js = _load_static_text("js", "thumbnail-studio.js")
    html = render_template(
        "thumbnail_studio.html",
        user=session.get("user_email"),
        asset_v=UI_ASSET_VERSION,
        studio_css=studio_css,
        studio_js=studio_js,
    )
    resp = make_response(html)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/studio/")
def thumbnail_studio_trailing_slash():
    return redirect(url_for("thumbnail_studio"), code=308)


@app.get("/generator")
@app.get("/thumbnail-generator")
def thumbnail_studio_alias():
    """Alternate URLs so the tool is easy to find if /studio is forgotten."""
    return redirect(url_for("thumbnail_studio"))


@app.get("/feature/<name>")
def feature_page(name: str):
    if (resp := _require_login_redirect()) is not None:
        return resp
    body = FEATURE_PAGES.get(name, "")
    _set_content(body, name if name in FEATURE_PAGES else "dashboard")
    return _render()


@app.post("/predict")
def predict_route() -> str:
    if (resp := _require_login_redirect()) is not None:
        return resp
    try:
        title = request.form.get("title", "").strip()
        duration_seconds = _parse_duration(request.form.get("duration_seconds"))
        image_path = _save_uploaded_image("image_file")
        result = predict_thumbnail(str(image_path), title=title, duration_seconds=duration_seconds)
        view = _predict_view(result)
        RECENT_RESULTS.setdefault(session["user_email"], []).insert(
            0, {"label": "Rater run", "score": view["probability_percent"]}
        )
        _set_content(FEATURE_PAGES["rater"] + _predict_result_card(view), "rater")
        return _render(success="Rated successfully.")
    except Exception as exc:
        return _render(error=str(exc))


@app.post("/compare")
def compare_route() -> str:
    if (resp := _require_login_redirect()) is not None:
        return resp
    try:
        title = request.form.get("title", "").strip()
        duration_seconds = _parse_duration(request.form.get("duration_seconds"))
        current_path = _save_uploaded_image("current_image_file")
        candidate_path = _save_uploaded_image("candidate_image_file")
        result = compare_thumbnails(str(current_path), str(candidate_path), title=title, duration_seconds=duration_seconds)
        view = _compare_view(result)
        RECENT_RESULTS.setdefault(session["user_email"], []).insert(
            0, {"label": "A/B test", "score": view["candidate_percent"]}
        )
        _set_content(FEATURE_PAGES["ab"] + _compare_result_card(view), "ab")
        return _render(success="A/B test complete.")
    except Exception as exc:
        return _render(error=str(exc))


@app.post("/ideas")
def ideas_route() -> str:
    if (resp := _require_login_redirect()) is not None:
        return resp
    topic = request.form.get("topic", "").strip()
    if not topic:
        return _render(error="Topic is required for ideas.")
    ideas = [
        f"{topic}: 3 mistakes nobody talks about",
        f"I tested {topic} for 7 days (real results)",
        f"How to get better at {topic} fast",
        f"{topic} in 2026: What actually works",
        f"Beginner to pro roadmap for {topic}",
    ]
    card = (
        "<div class='ts-card'><h3>Generated ideas</h3><p class='lead'>Starter hooks — edit to match your voice.</p>"
        + "".join([f"<div class='history-row'><span>{idea}</span></div>" for idea in ideas])
        + "</div>"
    )
    _set_content(FEATURE_PAGES["ideas"] + card, "ideas")
    return _render(success="Ideas generated.")


@app.post("/downloader")
def downloader_route() -> str:
    if (resp := _require_login_redirect()) is not None:
        return resp
    try:
        ensure_dirs(DOWNLOAD_DIR)
        image_url = request.form.get("image_url", "").strip()
        if not image_url:
            return _render(error="Image URL is required.")
        response = requests.get(image_url, timeout=20)
        response.raise_for_status()
        ext = ".jpg"
        if ".png" in image_url.lower():
            ext = ".png"
        elif ".webp" in image_url.lower():
            ext = ".webp"
        out_path = DOWNLOAD_DIR / f"downloaded_{uuid4().hex}{ext}"
        out_path.write_bytes(response.content)
        note = (
            f"<div class='ts-card'><p class='lead' style='margin:0'>Saved to "
            f"<code style='font-size:0.85em'>{html.escape(str(out_path))}</code></p></div>"
        )
        _set_content(FEATURE_PAGES["downloader"] + note, "downloader")
        return _render(success="Thumbnail downloaded.")
    except Exception as exc:
        return _render(error=str(exc))


def _load_font(size: int):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ]
    for fp in candidates:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_gradient_background(width: int, height: int) -> Image.Image:
    palettes = [
        ((26, 32, 44), (37, 99, 235), (236, 72, 153)),
        ((15, 23, 42), (16, 185, 129), (59, 130, 246)),
        ((30, 27, 75), (239, 68, 68), (249, 115, 22)),
    ]
    c1, c2, c3 = random.choice(palettes)
    base = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(base)

    for y in range(height):
        t = y / max(height - 1, 1)
        r = int((1 - t) * c1[0] + t * c2[0])
        g = int((1 - t) * c1[1] + t * c2[1])
        b = int((1 - t) * c1[2] + t * c2[2])
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse([width * 0.52, -height * 0.15, width * 1.2, height * 0.65], fill=(*c3, 120))
    od.rectangle([0, int(height * 0.7), width, height], fill=(0, 0, 0, 100))
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def _text_seed(text: str) -> str:
    # Stable across runs (unlike built-in hash()).
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]


_HTTP_UA = (
    "ThumbnailStudio/1.0 (local thumbnail tool; "
    "https://meta.wikimedia.org/wiki/User-Agent_policy)"
)


def _http_headers() -> dict[str, str]:
    return {"User-Agent": _HTTP_UA, "Accept": "application/json, image/*, */*"}


def _cover_crop_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Scale to cover target box, then center-crop (YouTube-style framing)."""
    img = img.convert("RGB")
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        raise ValueError("Invalid image size")
    scale = max(target_w / iw, target_h / ih)
    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - target_w) // 2
    top = (nh - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _apply_mood(image: Image.Image, mood: str) -> Image.Image:
    if mood == "cinematic":
        out = ImageEnhance.Brightness(image).enhance(0.88)
        out = ImageEnhance.Color(out).enhance(0.78)
        return ImageEnhance.Contrast(out).enhance(1.12)
    if mood == "vibrant":
        out = ImageEnhance.Color(image).enhance(1.35)
        return ImageEnhance.Contrast(out).enhance(1.18)
    if mood == "clean":
        out = ImageEnhance.Brightness(image).enhance(1.06)
        return ImageEnhance.Contrast(out).enhance(1.12)
    return image


def _fetch_commons_photo(query: str) -> Image.Image | None:
    """Topic-related photos from Wikimedia Commons — free, no API key."""
    clean = " ".join(query.strip().split()[:10])[:120]
    if len(clean) < 2:
        return None
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": clean,
        "gsrnamespace": "6",
        "gsrlimit": "12",
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": "1280",
    }
    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params=params,
            timeout=28,
            headers=_http_headers(),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None
    pages = payload.get("query", {}).get("pages") or {}
    ok_mimes = {"image/jpeg", "image/png", "image/webp"}
    for _pid, page in pages.items():
        try:
            if int(_pid) < 0:
                continue
        except (TypeError, ValueError):
            continue
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = (info.get("mime") or "").lower()
        if mime not in ok_mimes:
            continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        try:
            ir = requests.get(url, timeout=35, headers=_http_headers())
            ir.raise_for_status()
            return Image.open(BytesIO(ir.content)).convert("RGB")
        except Exception:
            continue
    return None


def _download_picsum_photo(text: str) -> Image.Image | None:
    """Free stock photos — Lorem Picsum, no API key."""
    seed = _text_seed(text)
    url = f"https://picsum.photos/seed/{seed}/1280/720"
    try:
        response = requests.get(
            url,
            timeout=30,
            allow_redirects=True,
            headers=_http_headers(),
        )
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGB")
        return _cover_crop_resize(img, 1280, 720)
    except Exception:
        return None


def _apply_bottom_vignette(rgb_img: Image.Image) -> Image.Image:
    w, h = rgb_img.size
    base = rgb_img.convert("RGBA")
    grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(h):
        if y < int(h * 0.32):
            alpha = 0
        else:
            t = (y - h * 0.32) / max(h * 0.68, 1.0)
            alpha = int(min(235, 40 + t * t * 220))
        gd.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(base, grad).convert("RGB")


def _draw_abstract_decorations(image: Image.Image) -> None:
    w, h = image.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for _ in range(8):
        cx = random.randint(0, w)
        cy = random.randint(0, h)
        r = random.randint(40, 220)
        color = (
            random.randint(80, 255),
            random.randint(80, 255),
            random.randint(80, 255),
            random.randint(25, 70),
        )
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=18))
    blended = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    image.paste(blended, (0, 0))
    draw = ImageDraw.Draw(image)
    for _ in range(12):
        x1, y1 = random.randint(0, w), random.randint(0, h)
        x2, y2 = random.randint(0, w), random.randint(0, h)
        draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255), width=2)
    cx, cy = w // 2, h // 3
    for angle in range(0, 360, 18):
        rad = math.pi * angle / 180.0
        x2 = int(cx + 400 * math.cos(rad))
        y2 = int(cy + 400 * math.sin(rad))
        draw.line([(cx, cy), (x2, y2)], fill=(255, 255, 255), width=3)


def _draw_text_line(
    target: Image.Image,
    xy: tuple[int, int],
    line: str,
    font,
    *,
    stroke: int,
) -> None:
    draw = ImageDraw.Draw(target)
    if stroke > 0:
        try:
            draw.text(
                xy,
                line,
                fill=(255, 255, 255),
                font=font,
                stroke_width=stroke,
                stroke_fill=(15, 23, 42),
            )
        except Exception:
            draw.text(xy, line, fill=(255, 255, 255), font=font)
    else:
        draw.text(xy, line, fill=(255, 255, 255), font=font)


def _draw_title_block(image: Image.Image, text: str, *, placement: str = "top") -> None:
    width, height = image.size
    title = " ".join((text or "").strip().upper().split())
    if not title:
        title = "YOUR NEXT VIDEO WILL BLOW UP"

    wrap_w = 14 if placement == "bottom" else 15
    max_lines = 2 if placement == "bottom" else 3
    lines = textwrap.wrap(title[:100], width=wrap_w)[:max_lines]
    font_size = 76 if placement == "bottom" else (92 if len(lines) <= 2 else 78)
    font = _load_font(font_size)

    if placement == "bottom":
        line_h = 96
        y = height - 120 - line_h * len(lines)
        x = 48
    else:
        line_h = 108
        y = int(height * 0.14)
        x = 56

    for i, line in enumerate(lines):
        ly = y + i * line_h
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        try:
            gd.text(
                (x + 2, ly + 2),
                line,
                fill=(250, 204, 21, 200),
                font=font,
                stroke_width=10,
                stroke_fill=(0, 0, 0, 220),
            )
        except Exception:
            gd.text((x + 2, ly + 2), line, fill=(250, 204, 21, 200), font=font)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=5))
        image.paste(glow, (0, 0), glow)
        _draw_text_line(image, (x, ly), line, font, stroke=6 if placement == "bottom" else 6)

    draw = ImageDraw.Draw(image)
    badge_h = 56
    by = height - 52 - badge_h
    draw.rounded_rectangle([x, by, x + 360, by + badge_h], radius=14, fill=(234, 88, 12))
    badge_font = _load_font(32)
    _draw_text_line(image, (x + 22, by + 12), "WATCH NOW", badge_font, stroke=0)


@app.post("/creator")
def creator_route() -> str:
    if (resp := _require_login_redirect()) is not None:
        return resp
    try:
        ensure_dirs(CREATED_DIR)
        text = request.form.get("creator_text", "").strip()
        if not text:
            return _render(error="Creator text is required.")
        style = request.form.get("creator_style", "photo").strip().lower()
        source = request.form.get("creator_source", "auto").strip().lower()
        mood = request.form.get("creator_mood", "original").strip().lower()
        if mood not in {"cinematic", "vibrant", "clean", "original"}:
            mood = "original"

        def _finish_photo_base(base: Image.Image) -> Image.Image:
            img = _cover_crop_resize(base, 1280, 720)
            if mood != "original":
                img = _apply_mood(img, mood)
            img = _apply_bottom_vignette(img)
            _draw_title_block(img, text, placement="bottom")
            return img

        def _finish_abstract() -> Image.Image:
            img = _draw_gradient_background(1280, 720)
            _draw_abstract_decorations(img)
            if mood != "original":
                img = _apply_mood(img, mood)
            _draw_title_block(img, text, placement="top")
            return img

        note = ""
        if style == "abstract":
            image = _finish_abstract()
        elif style == "photo":
            image = None
            if source == "auto":
                image = _fetch_commons_photo(text) or _download_picsum_photo(text)
                if image is None:
                    image = _finish_abstract()
                    note = "Used abstract backup (Commons + Picsum unavailable or no match)."
                else:
                    image = _finish_photo_base(image)
            elif source == "commons":
                image = _fetch_commons_photo(text)
                if image is None:
                    return _render(
                        error="No suitable Wikimedia Commons image for that phrase. "
                        "Try different keywords or use Smart / Picsum."
                    )
                image = _finish_photo_base(image)
                note = "Photo from Wikimedia Commons — check license on the file page before commercial use."
            else:
                image = _download_picsum_photo(text)
                if image is None:
                    return _render(
                        error="Could not reach Lorem Picsum. Check your internet connection."
                    )
                image = _finish_photo_base(image)
        else:
            image = _finish_abstract()

        out_path = CREATED_DIR / f"created_{uuid4().hex}.jpg"
        image.save(out_path, "JPEG", quality=92)
        rel = "/" + str(out_path.relative_to(ROOT)).replace("\\", "/")
        card = f"<div class='ts-card'><h3>Generated thumbnail</h3><img class='ts-thumb-preview' src='{rel}' alt='Generated thumbnail'/><p class='lead muted'>Same headline → same Picsum seed. Commons uses your words as a search. {note}</p></div>"
        _set_content(FEATURE_PAGES["creator"] + card, "creator")
        success_msg = "Thumbnail generated."
        if note:
            success_msg += " " + note
        return _render(success=success_msg)
    except Exception as exc:
        return _render(error=str(exc))


@app.post("/projects/create")
def projects_create():
    if (resp := _require_login_redirect()) is not None:
        return resp
    name = request.form.get("name", "").strip()
    notes = request.form.get("notes", "").strip()
    if not name:
        return _render(error="Project name is required.")
    with _db() as conn:
        conn.execute(
            "INSERT INTO projects(user_email, name, notes) VALUES(?, ?, ?)",
            (session["user_email"], name, notes),
        )
    rows_html = _projects_html(session["user_email"])
    _set_content(FEATURE_PAGES["projects"] + rows_html, "projects")
    return _render(success="Workspace created.")


def _projects_html(email: str) -> str:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, name, notes FROM projects WHERE user_email=? ORDER BY id DESC",
            (email,),
        ).fetchall()
    body = "<div class='ts-card'><h3>Your workspaces</h3><p class='lead'>Recently created on this account.</p>"
    for row in rows:
        body += f"<div class='history-row'><span><strong>{row['name']}</strong> — {row['notes'] or 'No notes'}</span></div>"
    body += "</div>"
    return body


@app.get("/reports/download")
def download_report():
    if (resp := _require_login_redirect()) is not None:
        return resp
    fmt = request.args.get("format", "csv").lower()
    rows = RECENT_RESULTS.get(session["user_email"], [])
    if fmt == "txt":
        text = "\n".join([f"{idx+1}. {r['label']} - {r['score']}%" for idx, r in enumerate(rows)])
        if not text:
            text = "No activity yet."
        return Response(
            text,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=thumbnail_report.txt"},
        )
    sio = StringIO()
    sio.write("label,score\n")
    for r in rows:
        sio.write(f"{r['label']},{r['score']}\n")
    return Response(
        sio.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=thumbnail_report.csv"},
    )


@app.get("/data/raw/<path:subpath>")
def serve_raw(subpath: str):
    # Lightweight local static serving for generated previews.
    from flask import send_from_directory

    target = (DATA_RAW).resolve()
    return send_from_directory(target, subpath)


if __name__ == "__main__":
    import errno

    ensure_dirs(UPLOAD_DIR, CREATED_DIR, DOWNLOAD_DIR)
    _init_db()
    # 127.0.0.1 is most reliable on Windows for local browser access.
    # Set APP_HOST=0.0.0.0 only if you need other devices on your LAN.
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8080"))
    print(f"\n{'='*50}")
    print("  Thumbnail Studio is running")
    print(f"  UI templates:  {_APP_DIR / 'templates'}")
    print(f"  UI static:     {_APP_DIR / 'static'}")
    print(f"  UI CSS:        embedded in HTML ({len(EMBEDDED_UI_CSS)} chars from static/css/app.css)")
    print(f"  Open in browser:  http://127.0.0.1:{port}/")
    print(f"  Thumbnail tool:   http://127.0.0.1:{port}/studio  (also /generator)")
    print(f"  Health check:     http://127.0.0.1:{port}/health")
    print("  Leave this window OPEN - closing it stops the server.")
    print(f"{'='*50}\n")
    # use_reloader=False avoids Windows "connection refused" during reloader restarts
    try:
        app.run(host=host, port=port, debug=True, use_reloader=False)
    except OSError as exc:
        win = getattr(exc, "winerror", None)
        in_use = exc.errno == errno.EADDRINUSE or win == 10048
        if in_use or "address already in use" in str(exc).lower():
            alt = 8765 if port == 8080 else 8080
            print(
                "\n*** Port %s is already in use — close the other app or use another port. ***\n"
                "Fix: run run-local.bat (it picks a free port), or try:\n"
                "     set APP_PORT=%s\n"
                "     python app.py\n" % (port, alt),
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
        raise

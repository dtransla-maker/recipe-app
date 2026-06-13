import os
import json
import re
import subprocess
import tempfile
import traceback
import urllib.request
import urllib.parse
import uuid
from datetime import datetime, timezone
from flask import Flask, g, request, jsonify, render_template
from flask_limiter import Limiter
import anthropic
from supabase import create_client, Client
from dotenv import load_dotenv

from auth import require_user, rate_limit_key

load_dotenv()

app = Flask(__name__)

# Burst protection per user (real daily quotas are enforced via extraction_log).
# Memory storage is per-gunicorn-worker; good enough at beta scale.
limiter = Limiter(key_func=rate_limit_key, app=app, storage_uri="memory://")

# Daily quotas protecting Anthropic/AssemblyAI credits
USER_DAILY_EXTRACTIONS = int(os.environ.get("USER_DAILY_EXTRACTIONS", "20"))
GLOBAL_DAILY_EXTRACTIONS = int(os.environ.get("GLOBAL_DAILY_EXTRACTIONS", "200"))


@app.after_request
def set_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.context_processor
def inject_supabase_config():
    # The anon/publishable key is safe to expose to the browser.
    return {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", ""),
    }


@app.errorhandler(429)
def handle_rate_limit(e):
    return jsonify({"error": "Too many requests. Please wait a bit and try again."}), 429

# ─── Platform detection ───────────────────────────────────────────────────────

def detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    if "tiktok.com" in u:
        return "TikTok"
    if "instagram.com" in u or "instagr.am" in u:
        return "Instagram"
    if "facebook.com" in u or "fb.watch" in u or "fb.com" in u:
        return "Facebook"
    return "Unknown"

def is_valid_url(url: str) -> bool:
    return url.startswith("http") and detect_platform(url) != "Unknown"

def expand_short_url(url: str) -> str:
    try:
        req = urllib.request.Request(
            url, method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            final = resp.url
            if final != url:
                print(f"[normalize] Expanded {url} -> {final}")
            return final
    except Exception:
        return url

def normalize_url(url: str) -> str:
    if "fb.watch" in url:
        url = expand_short_url(url)
    m = re.search(r'facebook\.com/reels?/(\d+)', url)
    if m:
        normalized = f"https://www.facebook.com/watch/?v={m.group(1)}"
        print(f"[normalize] Facebook Reel -> {normalized}")
        return normalized
    if re.search(r'facebook\.com/share/', url):
        expanded = expand_short_url(url)
        if expanded != url:
            return normalize_url(expanded)
    return url

def get_cookies_args() -> list:
    here = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(here, "cookies.txt")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        print(f"[cookies] Found cookies.txt ({os.path.getsize(file_path)} bytes)")
        return ["--cookies", file_path]
    raw = os.environ.get("COOKIES_CONTENT", "").strip()
    if raw:
        import base64
        tmp = "/tmp/yt_cookies.txt"
        try:
            content = base64.b64decode(raw).decode()
        except Exception:
            content = raw
        with open(tmp, "w") as f:
            f.write(content)
        print(f"[cookies] Loaded cookies from COOKIES_CONTENT env var ({len(content)} chars)")
        return ["--cookies", tmp]
    print("[cookies] No cookies file found -- Facebook/Instagram downloads may fail")
    return []

# ─── API clients ─────────────────────────────────────────────────────────────

def get_anthropic():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[config] ANTHROPIC_API_KEY is not set")
        raise ValueError("The AI service is not configured. Please contact the administrator.")
    return anthropic.Anthropic(api_key=key)

def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("[config] SUPABASE_URL / SUPABASE_KEY is not set")
        raise ValueError("The database is not configured. Please contact the administrator.")
    return create_client(url, key)

# ─── YouTube helpers ──────────────────────────────────────────────────────────

def get_youtube_video_id(url: str) -> str:
    patterns = [
        r'[?&]v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return ""

def extract_youtube_transcript(url: str) -> dict:
    from youtube_transcript_api import (
        YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
    )
    video_id = get_youtube_video_id(url)
    if not video_id:
        raise ValueError("Could not extract a video ID from this YouTube URL.")
    title = ""
    thumbnail_url = ""
    try:
        oembed = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json"
        with urllib.request.urlopen(oembed, timeout=10) as resp:
            data          = json.loads(resp.read().decode())
            title         = data.get("title", "")
            thumbnail_url = data.get("thumbnail_url", "")
        print(f"[youtube] title={title[:60]!r}")
    except Exception as e:
        print(f"[youtube] oEmbed fetch failed (non-fatal): {e}")
    print(f"[youtube] Fetching transcript for video_id={video_id!r}...")
    segments = None
    try:
        segments = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["en", "en-US", "en-GB"]
        )
    except TranscriptsDisabled:
        print("[youtube] Captions disabled -- falling back to yt-dlp + AssemblyAI...")
    except NoTranscriptFound:
        try:
            tlist    = YouTubeTranscriptApi.list_transcripts(video_id)
            segments = next(iter(tlist)).fetch()
        except Exception:
            print("[youtube] No transcript found -- falling back to yt-dlp + AssemblyAI...")
    except Exception as e:
        print(f"[youtube] Transcript API error ({e}) -- falling back to yt-dlp + AssemblyAI...")
    if segments is not None:
        text = " ".join(seg["text"] for seg in segments)
        print(f"[youtube] Got {len(text)} chars from {len(segments)} caption segments")
        return {
            "platform":      "YouTube",
            "title":         title,
            "thumbnail_url": thumbnail_url,
            "transcript":    text,
            "description":   "",
        }
    return extract_via_assemblyai(
        url, platform="YouTube", title=title, thumbnail_url=thumbnail_url
    )

# ─── yt-dlp + AssemblyAI ──────────────────────────────────────────────────────

def extract_via_assemblyai(url, platform, title="", thumbnail_url=""):
    description = ""
    cookies_args = get_cookies_args()
    base_args = [
        "yt-dlp",
        "--no-playlist",
        "--no-check-certificate",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    ] + cookies_args

    if not title:
        print(f"[yt-dlp] Fetching metadata for {platform}...")
        meta_proc = subprocess.run(
            base_args + ["--skip-download", "--print-json", url],
            capture_output=True, text=True, timeout=30
        )
        if meta_proc.returncode == 0 and meta_proc.stdout.strip():
            try:
                lines = [l for l in meta_proc.stdout.strip().split("\n") if l.strip()]
                info          = json.loads(lines[-1])
                title         = info.get("title", "") or ""
                description   = (info.get("description", "") or "")[:3000]
                thumbnail_url = info.get("thumbnail", "") or ""
                print(f"[yt-dlp] title={title[:60]!r}")
                print(f"[yt-dlp] description={len(description)} chars")
            except Exception as e:
                print(f"[yt-dlp] Metadata parse error (non-fatal): {e}")
        else:
            stderr = (meta_proc.stderr or "").strip()
            print(f"[yt-dlp] Metadata fetch failed (exit {meta_proc.returncode}): {stderr[:300]}")

    transcript_text = ""
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        audio_path_raw = os.path.join(tmpdir, "audio.%(ext)s")
        print(f"[yt-dlp] Downloading audio for {platform}...")

        # Try with MP3 conversion first (requires ffmpeg)
        dl_proc = subprocess.run(
            base_args + [
                "--extract-audio", "--audio-format", "mp3",
                "--audio-quality", "5",
                "-o", audio_path,
                url,
            ],
            capture_output=True, text=True, timeout=300
        )

        # If ffmpeg not found, fall back to raw audio download (m4a/webm/etc.)
        if dl_proc.returncode != 0 and (
            "ffprobe" in (dl_proc.stderr or "") or "ffmpeg" in (dl_proc.stderr or "")
        ):
            print("[yt-dlp] ffmpeg not found -- retrying without audio conversion...")
            dl_proc = subprocess.run(
                base_args + [
                    "--format", "bestaudio/best",
                    "-o", audio_path_raw,
                    url,
                ],
                capture_output=True, text=True, timeout=300
            )
            # Find whatever file was actually downloaded
            import glob
            found = glob.glob(os.path.join(tmpdir, "audio.*"))
            if found:
                audio_path = found[0]
                print(f"[yt-dlp] Downloaded raw audio: {os.path.basename(audio_path)}")

        if dl_proc.returncode != 0 or not os.path.exists(audio_path):
            stderr_raw = (dl_proc.stderr or dl_proc.stdout or "").strip()
            print(f"[yt-dlp] DOWNLOAD FAILED (exit {dl_proc.returncode}):")
            print(stderr_raw[:800])

            if description or title:
                print("[yt-dlp] Download failed -- falling back to description-only extraction.")
                return {
                    "platform":      platform,
                    "title":         title,
                    "thumbnail_url": thumbnail_url,
                    "transcript":    "",
                    "description":   description,
                }

            err = stderr_raw.lower()
            if "private" in err:
                raise RuntimeError("This video is private. Please use a public video.")
            if "login" in err or "sign in" in err or "cookies" in err:
                raise RuntimeError(
                    f"{platform} blocked automatic processing for this video. "
                    "Try a YouTube or TikTok link, or paste the transcript manually."
                )
            if "not available" in err or "removed" in err or "404" in err:
                raise RuntimeError("This video is not available or has been removed.")
            raise RuntimeError(
                f"Could not download the {platform} video. "
                "Try another video, or paste the transcript manually."
            )

        file_kb = os.path.getsize(audio_path) // 1024
        print(f"[yt-dlp] Audio ready: {file_kb} KB")

        aai_key = os.environ.get("ASSEMBLYAI_API_KEY")
        if not aai_key:
            print("[config] ASSEMBLYAI_API_KEY is not set")
            raise ValueError("The transcription service is not configured. Please contact the administrator.")

        import assemblyai as aai
        aai.settings.api_key = aai_key

        print(f"[assemblyai] Transcribing {file_kb} KB audio...")
        config = aai.TranscriptionConfig(speech_models=["universal-2"])
        transcriber = aai.Transcriber()
        result      = transcriber.transcribe(audio_path, config=config)

        if result.status == aai.TranscriptStatus.error:
            raise RuntimeError(f"Transcription failed: {result.error}")

        transcript_text = (result.text or "").strip()
        print(f"[assemblyai] Got {len(transcript_text)} chars")

    if not transcript_text and not description and not title:
        raise RuntimeError("Could not extract any content from this video.")

    return {
        "platform":      platform,
        "title":         title,
        "thumbnail_url": thumbnail_url,
        "transcript":    transcript_text,
        "description":   description,
    }

# ─── Transcript extraction router ────────────────────────────────────────────

def extract_transcript(url: str) -> dict:
    platform = detect_platform(url)
    if platform == "Unknown":
        raise ValueError(
            "Unsupported platform. Please use a YouTube, TikTok, Instagram, or Facebook URL."
        )
    if platform == "YouTube":
        return extract_youtube_transcript(url)
    return extract_via_assemblyai(url, platform)

# ─── Recipe extraction via Claude ────────────────────────────────────────────

RECIPE_PROMPT = """You are a recipe extraction assistant. Given a video transcript and/or post description from a cooking video, extract the recipe and return it as valid JSON. If both a transcript and a description are provided, combine them.

If the content does not appear to contain a recipe, return: {"error": "No recipe found in this video"}

Otherwise return JSON in EXACTLY this format:
{
  "title": "Recipe name",
  "description": "1-2 sentence description of the dish",
  "servings": "e.g. 4 servings",
  "prep_time": "e.g. 15 minutes",
  "cook_time": "e.g. 30 minutes",
  "total_time": "e.g. 45 minutes",
  "difficulty": "Easy / Medium / Hard",
  "ingredients": ["amount + ingredient", "..."],
  "instructions": ["Step description", "..."],
  "tips": "Any tips or notes from the video (empty string if none)",
  "tags": ["tag1", "tag2"]
}

Return ONLY the JSON -- no markdown, no explanation, no code fences."""

def extract_recipe(transcript: str, title: str, description: str = "") -> dict:
    client = get_anthropic()
    parts = []
    if title:
        parts.append(f"Video title: {title}")
    if description:
        parts.append(f"Post description:\n{description[:1500]}")
    if transcript:
        parts.append(f"Transcript:\n{transcript[:5000]}")
    content = "\n\n".join(parts).strip()
    if not content:
        return {"error": "No content to extract recipe from"}
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": f"{RECIPE_PROMPT}\n\n---\n\n{content}"}],
    )
    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {"error": "Could not parse recipe from AI response"}

# ─── Quota helpers ────────────────────────────────────────────────────────────

def _today_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False

def check_extraction_quota(sb) -> str:
    """Return an error message if the user or the service is over quota, else ''."""
    start = _today_start_iso()
    user_count = (
        sb.table("extraction_log").select("id", count="exact")
        .eq("user_id", g.user_id).gte("created_at", start).execute().count or 0
    )
    if user_count >= USER_DAILY_EXTRACTIONS:
        return "You've reached your daily extraction limit. Try again tomorrow."
    total_count = (
        sb.table("extraction_log").select("id", count="exact")
        .gte("created_at", start).execute().count or 0
    )
    if total_count >= GLOBAL_DAILY_EXTRACTIONS:
        return "The service is at capacity for today. Please try again tomorrow."
    return ""

def log_extraction(sb, url: str, platform: str, status: str, error: str = ""):
    try:
        sb.table("extraction_log").insert({
            "user_id":  g.user_id,
            "url":      url[:500],
            "platform": platform,
            "status":   status,
            "error":    error[:500],
        }).execute()
    except Exception:
        traceback.print_exc()

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/library")
def library():
    return render_template("library.html")

@app.route("/recipe/<recipe_id>")
def recipe_detail(recipe_id):
    return render_template("recipe.html", recipe_id=recipe_id)

# ─── API endpoints ────────────────────────────────────────────────────────────

@app.route("/api/extract", methods=["POST"])
@require_user
@limiter.limit("10 per hour")
def api_extract():
    data = request.get_json()
    url  = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "Please provide a video URL."}), 400
    if not url.startswith("http"):
        return jsonify({"error": "Please provide a valid URL starting with http."}), 400
    if not is_valid_url(url):
        return jsonify({"error": "Please use a YouTube, Facebook, Instagram, or TikTok URL."}), 400
    try:
        sb = get_supabase()
        quota_error = check_extraction_quota(sb)
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
    if quota_error:
        return jsonify({"error": quota_error}), 429
    try:
        normalized = normalize_url(url)
        video = extract_transcript(normalized)
        recipe = extract_recipe(
            transcript=video["transcript"],
            title=video["title"],
            description=video.get("description", ""),
        )
        if "error" in recipe:
            log_extraction(sb, url, video["platform"], "no_recipe", recipe["error"])
            return jsonify({"error": recipe["error"]}), 422
        recipe["source_url"]    = url
        recipe["platform"]      = video["platform"]
        recipe["thumbnail_url"] = video["thumbnail_url"]
        if not recipe.get("title") and video["title"]:
            recipe["title"] = video["title"]
        log_extraction(sb, url, video["platform"], "success")
        return jsonify({"success": True, "recipe": recipe})
    except (ValueError, RuntimeError) as e:
        # Intentionally raised with user-friendly messages
        traceback.print_exc()
        log_extraction(sb, url, detect_platform(url), "failed", str(e))
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        traceback.print_exc()
        log_extraction(sb, url, detect_platform(url), "failed", str(e))
        return jsonify({"error": "Something went wrong processing this video. Please try again."}), 500


@app.route("/api/extract-text", methods=["POST"])
@require_user
@limiter.limit("10 per hour")
def api_extract_text():
    """Manual fallback: extract a recipe from pasted transcript/description text."""
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    url  = (data.get("url") or "").strip()
    if not text:
        return jsonify({"error": "Please paste some text to extract a recipe from."}), 400
    platform = detect_platform(url) if url else "Manual"
    if platform == "Unknown":
        platform = "Manual"
    try:
        sb = get_supabase()
        quota_error = check_extraction_quota(sb)
        if quota_error:
            return jsonify({"error": quota_error}), 429
        recipe = extract_recipe(transcript=text[:8000], title="", description="")
        if "error" in recipe:
            log_extraction(sb, url, platform, "no_recipe", recipe["error"])
            return jsonify({"error": recipe["error"]}), 422
        recipe["source_url"]    = url
        recipe["platform"]      = platform
        recipe["thumbnail_url"] = ""
        log_extraction(sb, url, platform, "success")
        return jsonify({"success": True, "recipe": recipe})
    except ValueError as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 422
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong extracting the recipe. Please try again."}), 500


@app.route("/api/recipes", methods=["GET"])
@require_user
def api_list_recipes():
    try:
        sb = get_supabase()
        res = (
            sb.table("recipes").select("*")
            .eq("user_id", g.user_id)
            .order("created_at", desc=True).execute()
        )
        return jsonify({"recipes": res.data})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Could not load your recipes. Please try again."}), 500


@app.route("/api/recipes", methods=["POST"])
@require_user
def api_save_recipe():
    data = request.get_json() or {}
    if not data.get("title"):
        return jsonify({"error": "Missing recipe title"}), 400
    record = {
        "user_id":       g.user_id,
        "title":         data.get("title", ""),
        "description":   data.get("description", ""),
        "servings":      data.get("servings", ""),
        "prep_time":     data.get("prep_time", ""),
        "cook_time":     data.get("cook_time", ""),
        "total_time":    data.get("total_time", ""),
        "difficulty":    data.get("difficulty", ""),
        "ingredients":   data.get("ingredients", []),
        "instructions":  data.get("instructions", []),
        "tips":          data.get("tips", ""),
        "tags":          data.get("tags", []),
        "source_url":    data.get("source_url", ""),
        "platform":      data.get("platform", ""),
        "thumbnail_url": data.get("thumbnail_url", ""),
    }
    try:
        sb  = get_supabase()
        res = sb.table("recipes").insert(record).execute()
        return jsonify({"success": True, "recipe": res.data[0]})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Could not save the recipe. Please try again."}), 500


@app.route("/api/recipes/<recipe_id>", methods=["GET"])
@require_user
def api_get_recipe(recipe_id):
    if not _is_valid_uuid(recipe_id):
        return jsonify({"error": "Recipe not found"}), 404
    try:
        sb  = get_supabase()
        res = (
            sb.table("recipes").select("*")
            .eq("id", recipe_id).eq("user_id", g.user_id)
            .limit(1).execute()
        )
        if not res.data:
            return jsonify({"error": "Recipe not found"}), 404
        return jsonify({"recipe": res.data[0]})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Could not load the recipe. Please try again."}), 500


@app.route("/api/recipes/<recipe_id>", methods=["DELETE"])
@require_user
def api_delete_recipe(recipe_id):
    if not _is_valid_uuid(recipe_id):
        return jsonify({"error": "Recipe not found"}), 404
    try:
        sb  = get_supabase()
        res = (
            sb.table("recipes").delete()
            .eq("id", recipe_id).eq("user_id", g.user_id)
            .execute()
        )
        if not res.data:
            return jsonify({"error": "Recipe not found"}), 404
        return jsonify({"success": True})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Could not delete the recipe. Please try again."}), 500

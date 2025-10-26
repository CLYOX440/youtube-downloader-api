from flask import Flask, request, jsonify
import yt_dlp, os, base64, tempfile, time

app = Flask(__name__)

_COOKIES_PATH = None

def cookies_file():
    """Create a temp cookies.txt from Base64 env once per process."""
    global _COOKIES_PATH
    if _COOKIES_PATH:
        return _COOKIES_PATH
    b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64)
        fd, path = tempfile.mkstemp(prefix="cookies_", suffix=".txt")
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        _COOKIES_PATH = path
        return path
    except Exception:
        return None

def normalize(raw):
    if not raw:
        return None
    if raw.startswith("http"):
        if "/shorts/" in raw and "watch?v=" not in raw:
            vid = raw.split("/shorts/")[1].split("?")[0].split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}"
        return raw
    return f"https://www.youtube.com/watch?v={raw}"

def pick_stream(info):
    fmts = info.get("formats") or []

    # Prefer progressive MP4 with audio (<=1080p)
    mp4_prog = [f for f in fmts
                if f.get("ext") == "mp4"
                and f.get("vcodec") != "none"
                and f.get("acodec") != "none"
                and (f.get("height") or 0) <= 1080]
    mp4_prog.sort(key=lambda f: f.get("height") or 0)
    if mp4_prog:
        return mp4_prog[-1]

    # Fallback: any single-file with audio (WEBM, etc.)
    single = [f for f in fmts if f.get("vcodec") != "none" and f.get("acodec") != "none"]
    single.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
    return single[-1] if single else None

@app.route("/download", methods=["GET"])
def download():
    raw = request.args.get("videoId") or request.args.get("url")
    url = normalize(raw)
    if not url:
        return jsonify({"error": "Missing videoId or url"}), 400

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "retries": 3,
        "extractor_retries": 2,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.youtube.com/",
        },
        "extractor_args": {
            "youtube": {
                # try several clients; one often works when others don't
                "player_client": ["android", "web", "ios"]
            }
        },
    }
    cfile = cookies_file()
    if cfile:
        ydl_opts["cookiefile"] = cfile

    last_err = None
    for attempt in range(1, 4):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                chosen = pick_stream(info)
                if not chosen or not chosen.get("url"):
                    return jsonify({"error": "No suitable stream found"}), 404
                return jsonify({
                    "title": info.get("title"),
                    "duration": info.get("duration"),
                    "download_url": chosen["url"],
                    "ext": chosen.get("ext"),
                    "vcodec": chosen.get("vcodec"),
                    "acodec": chosen.get("acodec"),
                    "height": chosen.get("height"),
                    "cookies_used": bool(cfile),
                })
        except Exception as e:
            last_err = str(e)
            time.sleep(2 * attempt)

    return jsonify({"error": "yt-dlp failed", "details": last_err, "cookies_used": bool(cfile)}), 500

@app.route("/debug")
def debug():
    path = cookies_file()
    return jsonify({
        "cookies_loaded": bool(path),
        "cookies_path": path if path else None,
        "env_present": bool(os.environ.get("YOUTUBE_COOKIES_B64"))
    })

@app.route("/")
def home():
    return "YouTube Downloader API is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

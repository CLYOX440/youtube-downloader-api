from flask import Flask, request, jsonify
import yt_dlp, os, base64, tempfile, time

app = Flask(__name__)

COOKIES_FILE = None

def ensure_cookies_file():
    """Create a temp cookies.txt from Base64 env, once per process."""
    global COOKIES_FILE
    if COOKIES_FILE is not None:
        return COOKIES_FILE
    b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
    if not b64:
        return None
    try:
        raw = base64.b64decode(b64)
        fd, path = tempfile.mkstemp(prefix="cookies_", suffix=".txt")
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        COOKIES_FILE = path
        return path
    except Exception:
        return None

def pick_best_mp4(formats):
    # Prefer <=1080p MP4 with video+audio; fallback to best MP4
    candidates = [f for f in formats if f.get("ext") == "mp4" and f.get("vcodec") != "none"]
    if not candidates:
        return None
    # Prefer progressive (has audio) when possible
    def key(f):
        return (f.get("acodec") != "none", f.get("height") or 0)
    return sorted(candidates, key=key)[-1]

def normalize_watch_url(raw):
    # Accept full URL or videoId
    if raw.startswith("http"):
        # handle shorts links
        if "/shorts/" in raw and "watch?v=" not in raw:
            vid = raw.split("/shorts/")[1].split("?")[0].split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}"
        return raw
    return f"https://www.youtube.com/watch?v={raw}"

@app.route("/download", methods=["GET"])
def download():
    raw = request.args.get("videoId") or request.args.get("url")
    if not raw:
        return jsonify({"error": "Missing videoId or url"}), 400

    url = normalize_watch_url(raw)
    cookies_path = ensure_cookies_file()

    # Shared options
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "mp4[height<=1080]/mp4/best",  # try 1080p then fallback
        "http_headers": {  # look like a real browser
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.youtube.com/",
        },
        # Try different player clients (helps in some regions)
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "android", "ios"]
            }
        }
    }
    if cookies_path:
        ydl_opts["cookiefile"] = cookies_path

    # Light retry for transient 429s
    last_err = None
    for attempt in range(1, 4):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                fmts = info.get("formats", []) or []
                best = pick_best_mp4(fmts)
                if not best:
                    return jsonify({"error": "No suitable MP4 stream found"}), 404
                return jsonify({
                    "title": info.get("title"),
                    "duration": info.get("duration"),
                    "download_url": best.get("url")
                })
        except Exception as e:
            last_err = str(e)
            # Backoff a bit before retrying
            time.sleep(2 * attempt)

    return jsonify({"error": "yt-dlp failed", "details": last_err}), 500

@app.route("/")
def home():
    return "YouTube Downloader API is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

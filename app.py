from flask import Flask, request, jsonify
import yt_dlp, os, base64, tempfile, time

app = Flask(__name__)

_COOKIES_PATH = None

def _cookies_file():
    """Create a temp cookies.txt from Base64 env once per process."""
    global _COOKIES_PATH
    if _COOKIES_PATH:
        return _COOKIES_PATH
    b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
    if not b64:
        return None
    raw = base64.b64decode(b64)
    fd, path = tempfile.mkstemp(prefix="cookies_", suffix=".txt")
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    _COOKIES_PATH = path
    return path

def _normalize(raw):
    if not raw:
        return None
    if raw.startswith("http"):
        if "/shorts/" in raw and "watch?v=" not in raw:
            vid = raw.split("/shorts/")[1].split("?")[0].split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}"
        return raw
    return f"https://www.youtube.com/watch?v={raw}"

def _pick_best_mp4(formats):
    # Prefer mp4 with audio, then highest height
    cands = [f for f in (formats or []) if f.get("ext") == "mp4" and f.get("vcodec") != "none"]
    if not cands:
        return None
    cands.sort(key=lambda f: ((f.get("acodec") != "none"), f.get("height") or 0))
    return cands[-1]

@app.route("/download", methods=["GET"])
def download():
    raw = request.args.get("videoId") or request.args.get("url")
    url = _normalize(raw)
    if not url:
        return jsonify({"error": "Missing videoId or url"}), 400

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "mp4[height<=1080]/mp4/best",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.youtube.com/",
        },
        "extractor_args": {
            "youtube": {
                # Try multiple clients; helps when one path is blocked.
                "player_client": ["web", "android", "ios"]
            }
        },
    }
    cookies = _cookies_file()
    if cookies:
        ydl_opts["cookiefile"] = cookies

    last_err = None
    for attempt in range(1, 4):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                best = _pick_best_mp4(info.get("formats"))
                if not best or not best.get("url"):
                    return jsonify({"error": "No suitable MP4 stream found"}), 404
                return jsonify({
                    "title": info.get("title"),
                    "duration": info.get("duration"),
                    "download_url": best["url"],
                })
        except Exception as e:
            last_err = str(e)
            time.sleep(2 * attempt)  # simple backoff

    return jsonify({"error": "yt-dlp failed", "details": last_err}), 500

@app.route("/")
def home():
    return "YouTube Downloader API is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

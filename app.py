from flask import Flask, request, jsonify
import yt_dlp, os, base64, tempfile, time

app = Flask(__name__)

_COOKIES_PATH = None
def cookies_file():
    global _COOKIES_PATH
    if _COOKIES_PATH: return _COOKIES_PATH
    b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
    if not b64: return None
    raw = base64.b64decode(b64)
    fd, path = tempfile.mkstemp(prefix="cookies_", suffix=".txt")
    with os.fdopen(fd, "wb") as f: f.write(raw)
    _COOKIES_PATH = path
    return path

def normalize(raw):
    if raw.startswith("http"):
        if "/shorts/" in raw and "watch?v=" not in raw:
            vid = raw.split("/shorts/")[1].split("?")[0].split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}"
        return raw
    return f"https://www.youtube.com/watch?v={raw}"

@app.route("/download")
def download():
    raw = request.args.get("videoId") or request.args.get("url")
    url = normalize(raw) if raw else None
    if not url:
        return jsonify({"error": "Missing videoId or url"}), 400

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.youtube.com/",
        },
        "extractor_args": {"youtube": {"player_client": ["web","android","ios"]}},
    }
    c = cookies_file()
    if c: ydl_opts["cookiefile"] = c

    last_err = None
    for attempt in range(1, 4):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                fmts = info.get("formats") or []

                # 1) Prefer progressive MP4 with audio, <=1080p
                mp4_prog = [f for f in fmts
                            if f.get("ext")=="mp4" and f.get("vcodec")!="none"
                            and f.get("acodec")!="none" and (f.get("height") or 0) <= 1080]
                mp4_prog.sort(key=lambda f: f.get("height") or 0)

                chosen = mp4_prog[-1] if mp4_prog else None

                # 2) Fallback: any single-file with audio (WEBM etc.)
                if not chosen:
                    single = [f for f in fmts if f.get("vcodec")!="none" and f.get("acodec")!="none"]
                    single.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
                    chosen = single[-1] if single else None

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
                    "width": chosen.get("width"),
                })
        except Exception as e:
            last_err = str(e)
            time.sleep(2 * attempt)

    return jsonify({"error": "yt-dlp failed", "details": last_err}), 500

@app.route("/")
def home():
    return "YouTube Downloader API is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

from flask import Flask, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route("/download", methods=["GET"])
def download():
    video_id = request.args.get("videoId")
    if not video_id:
        return jsonify({"error": "Missing videoId"}), 400

    url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'format': 'mp4[height<=1080]',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            best = next((f for f in formats if f.get("ext") == "mp4" and f.get("height", 0) <= 1080), None)
            if not best:
                return jsonify({"error": "No suitable format"}), 404

            return jsonify({
                "title": info.get("title"),
                "duration": info.get("duration"),
                "download_url": best["url"]
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return "YouTube Downloader API is running!"
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

import datetime as dt
import html
import json
import os
import subprocess
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

APP_DIR = Path(__file__).resolve().parent
KIT_DIR = APP_DIR / "animation-kit"
DATA_DIR = Path(os.environ.get("DATA_DIR", str(APP_DIR / "data"))) / "videos"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOPICS = json.loads((APP_DIR / "topics.json").read_text(encoding="utf-8"))
TZ = ZoneInfo("Asia/Jakarta")
SCHEDULE_HOURS = {7, 12, 17, 21}

render_lock = threading.Lock()
last_status = "Idle (siap render)"


def pick_next_topic():
    existing = {p.stem for p in DATA_DIR.glob("*.mp4")}
    for idx, t in enumerate(TOPICS):
        slug = t["slug"]
        if not any(name.endswith(slug) for name in existing):
            return t
    return TOPICS[len(existing) % len(TOPICS)]


def render_one():
    global last_status
    if not render_lock.acquire(blocking=False):
        return None, "Render lain sedang berjalan"
    try:
        now = dt.datetime.now(TZ)
        topic = pick_next_topic()
        base = f"{now.strftime('%Y-%m-%d-%H%M')}-{topic['slug']}"
        spec_path = DATA_DIR / f"{base}.spec.json"
        mp4_path = DATA_DIR / f"{base}.mp4"
        txt_path = DATA_DIR / f"{base}.txt"

        spec = dict(topic["spec"])
        spec["out"] = str(mp4_path)
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

        build_py = KIT_DIR / "skills" / topic["skill"] / "build.py"
        env = os.environ.copy()
        env.setdefault("PRODUCER_EXPERIMENTAL_FAST_CAPTURE", "false")
        last_status = f"Merender {base}.mp4 ({topic['skill']})..."
        res = subprocess.run(
            ["python3", str(build_py), str(spec_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if res.returncode != 0 or not mp4_path.exists():
            err = (res.stdout + "\n" + res.stderr)[-1200:]
            last_status = f"Gagal render {base}: {err}"
            return None, last_status

        txt_path.write_text(
            f"Judul: {topic['title']}\n\n"
            f"Caption:\n{topic['caption']}\n\n"
            f"Hashtags:\n{topic['hashtags']}\n",
            encoding="utf-8",
        )
        last_status = f"Sukses render {base}.mp4 pada {now.strftime('%H:%M:%S WIB')}"
        return base, last_status
    finally:
        render_lock.release()


def scheduler_loop():
    ran_slots = set()
    while True:
        now = dt.datetime.now(TZ)
        slot = (now.date().isoformat(), now.hour)
        if now.hour in SCHEDULE_HOURS and now.minute == 0 and slot not in ran_slots:
            ran_slots.add(slot)
            threading.Thread(target=render_one, daemon=True).start()
        time.sleep(20)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(self.path.split("?")[0])
        if path == "/health":
            self._send(200, "text/plain", b"OK")
            return
        if path.startswith("/files/"):
            fname = Path(path.removeprefix("/files/")).name
            fpath = DATA_DIR / fname
            if not fpath.is_file():
                self._send(404, "text/plain", b"Not found")
                return
            ctype = "video/mp4" if fname.endswith(".mp4") else "image/jpeg" if fname.endswith(".jpg") else "text/plain; charset=utf-8"
            self._send(200, ctype, fpath.read_bytes())
            return
        if path == "/":
            items = []
            for mp4 in sorted(DATA_DIR.glob("*.mp4"), reverse=True):
                stem = mp4.stem
                txt_file = DATA_DIR / f"{stem}.txt"
                txt_content = txt_file.read_text(encoding="utf-8") if txt_file.exists() else ""
                size_mb = mp4.stat().st_size / (1024 * 1024)
                items.append(
                    f"<div class='card'>"
                    f"<h3>{html.escape(stem)} ({size_mb:.1f} MB)</h3>"
                    f"<a class='btn' href='/files/{html.escape(mp4.name)}' download>Download MP4</a> "
                    f"<pre>{html.escape(txt_content)}</pre>"
                    f"</div>"
                )
            body = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>Daily Motion Graphics Cloud</title>"
                "<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;background:#0f172a;color:#f8fafc}"
                ".card{background:#1e293b;padding:16px;border-radius:12px;margin:14px 0}"
                ".btn{display:inline-block;background:#eab308;color:#0f172a;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:700;border:0;cursor:pointer}"
                "pre{white-space:pre-wrap;background:#0f172a;padding:12px;border-radius:8px;font-size:13px}</style></head><body>"
                "<h1>Daily Motion Graphics (Cloud 24/7)</h1>"
                "<p>Jadwal otomatis: <b>07:00, 12:00, 17:00, 21:00 WIB</b></p>"
                f"<p>Status: <b>{html.escape(last_status)}</b></p>"
                "<form method='post' action='/render'><button class='btn' type='submit'>Render 1 Video Sekarang</button></form>"
                + ("".join(items) if items else "<p>Belum ada video. Klik tombol di atas untuk test render pertama!</p>")
                + "</body></html>"
            ).encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)
            return
        self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/render":
            threading.Thread(target=render_one, daemon=True).start()
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return
        self._send(404, "text/plain", b"Not found")

    def _send(self, code, ctype, data):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    threading.Thread(target=scheduler_loop, daemon=True).start()
    port = int(os.environ.get("PORT", "8080"))
    print(f"Serving on 0.0.0.0:{port}, data={DATA_DIR}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

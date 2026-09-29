#!/usr/bin/env python3
"""yt-dlp dashboard: a local web UI to download from every site yt-dlp supports.

Run:  python3 server.py [--port 8080] [--host 127.0.0.1] [--dir downloads]

The supported-site list is built live from yt-dlp's extractor registry, so it
always matches the installed yt-dlp version (upgrade yt-dlp to get new sites).
"""
import argparse
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    import yt_dlp
    from yt_dlp.extractor import gen_extractor_classes
except ImportError:
    raise SystemExit("yt-dlp is not installed. Run:  pip install -U yt-dlp")

HERE = Path(__file__).parent
DOWNLOAD_DIR = HERE / "downloads"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
CANCELLED: set[str] = set()
SLOTS = threading.BoundedSemaphore(3)  # max simultaneous downloads (--concurrent)
URL_RE = re.compile(r"(?:https?://|ytsearch\d*:)\S+", re.I)


def parse_urls(text: str) -> list[str]:
    """Extract unique URLs from free text / .txt / .csv, ignoring #-comment lines."""
    seen, out = set(), []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for u in URL_RE.findall(line):
            u = u.rstrip(",;)\"'>")
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- site catalog
_CATALOG = None


def catalog():
    """One entry per service (IE_NAME prefix), aggregating its sub-extractors."""
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    services: dict[str, dict] = {}
    for ie in gen_extractor_classes():
        name = ie.IE_NAME
        if name == "generic":
            continue
        base = name.split(":")[0]
        s = services.setdefault(base, {
            "name": base, "description": "", "types": [], "working": False,
            "age_limit": 0, "login": False, "search": False,
        })
        s["types"].append(name)
        desc = getattr(ie, "IE_DESC", None)
        if desc is False:  # yt-dlp marks internal/hidden extractors this way
            pass
        elif desc and not s["description"]:
            s["description"] = desc
        try:
            if ie.working():
                s["working"] = True
        except Exception:
            s["working"] = True
        s["age_limit"] = max(s["age_limit"], getattr(ie, "age_limit", 0) or 0)
        s["login"] = s["login"] or bool(getattr(ie, "_NETRC_MACHINE", None))
        s["search"] = s["search"] or bool(getattr(ie, "SEARCH_KEY", None))
    out = sorted(services.values(), key=lambda s: s["name"].lower())
    for s in out:
        s["count"] = len(s["types"])
    _CATALOG = out
    return out


def match_url(url: str):
    hits = []
    for ie in gen_extractor_classes():
        if ie.IE_NAME == "generic":
            continue
        try:
            if ie.suitable(url):
                hits.append(ie.IE_NAME)
        except Exception:
            continue
    return hits


# ------------------------------------------------------------------ extraction
def summarize_info(info: dict) -> dict:
    formats = []
    for f in info.get("formats") or []:
        formats.append({
            "id": f.get("format_id"),
            "ext": f.get("ext"),
            "res": f.get("resolution") or (f"{f.get('height')}p" if f.get("height") else "audio"),
            "fps": f.get("fps"),
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "size": f.get("filesize") or f.get("filesize_approx"),
            "note": f.get("format_note"),
            "tbr": f.get("tbr"),
        })
    entries = info.get("entries")
    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "extractor": info.get("extractor_key"),
        "webpage_url": info.get("webpage_url"),
        "is_playlist": entries is not None,
        "entry_count": (info.get("playlist_count") or len(list(entries))) if entries is not None else None,
        "formats": formats,
    }


def build_opts(req: dict, job_id: str | None = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": not req.get("playlist", False),
        "outtmpl": str(DOWNLOAD_DIR / "%(extractor)s" / "%(title).150B [%(id)s].%(ext)s"),
        "restrictfilenames": False,
        "windowsfilenames": True,
    }
    if req.get("cookies_browser"):
        opts["cookiesfrombrowser"] = (req["cookies_browser"],)
    if req.get("username"):
        opts["username"] = req["username"]
        opts["password"] = req.get("password") or ""
    if req.get("proxy"):
        opts["proxy"] = req["proxy"]
    if req.get("subtitles"):
        opts.update(writesubtitles=True, writeautomaticsub=True, subtitleslangs=["all", "-live_chat"])
    if req.get("thumbnail"):
        opts["writethumbnail"] = True
    mode = req.get("mode", "best")
    fmt = req.get("format_id")
    ff = bool(shutil.which("ffmpeg"))
    if fmt:
        opts["format"] = fmt if ff else re.sub(r"\+.*", "", fmt)  # a "137+140" pick can't merge without ffmpeg
    elif not ff and mode == "audio":
        opts["format"] = "bestaudio/best"  # raw audio stream, no conversion
    elif not ff:
        h = int(mode[:-1]) if mode.endswith("p") and mode[:-1].isdigit() else 99999
        opts["format"] = f"b[height<={h}]/b"  # pre-merged single file only
    elif mode == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": req.get("audio_format", "mp3"),
            "preferredquality": "0",
        }]
    elif mode.endswith("p") and mode[:-1].isdigit():
        h = int(mode[:-1])
        opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/b"
    else:
        opts["format"] = "bv*+ba/b"
    if req.get("merge") in ("mp4", "mkv", "webm"):
        opts["merge_output_format"] = req["merge"]
    if job_id:
        opts["progress_hooks"] = [lambda d: on_progress(job_id, d)]
        opts["postprocessor_hooks"] = [lambda d: on_pp(job_id, d)]
    return opts


def on_progress(job_id, d):
    if job_id in CANCELLED:
        raise Cancelled()
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if not j:
            return
        st = d.get("status")
        if st == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            j.update(status="downloading",
                     percent=round(done / total * 100, 1) if total else 0,
                     speed=d.get("speed"), eta=d.get("eta"),
                     file=os.path.basename(d.get("filename") or ""))
        elif st == "finished":
            j.update(percent=100, speed=None, eta=0)
            fn = d.get("filename")
            if fn:
                j["_files"].add(fn)


def on_pp(job_id, d):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j and d.get("status") == "started":
            j["status"] = "processing"


def run_job(job_id, req):
    SLOTS.acquire()  # jobs wait here as "queued" until a slot frees up
    try:
        if job_id in CANCELLED:
            raise Cancelled()
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "downloading"
        with yt_dlp.YoutubeDL(build_opts(req, job_id)) as ydl:
            info = ydl.extract_info(req["url"], download=True)
            files = set()
            for entry in (info.get("entries") or [info]) if info else []:
                for rd in (entry or {}).get("requested_downloads") or []:
                    if rd.get("filepath"):
                        files.add(rd["filepath"])
        with JOBS_LOCK:
            j = JOBS[job_id]
            j["title"] = (info or {}).get("title") or j["title"]
            j["extractor"] = (info or {}).get("extractor_key") or j.get("extractor")
            j["files"] = sorted(os.path.relpath(f, DOWNLOAD_DIR) for f in files if os.path.exists(f))
            j.update(status="done", percent=100, finished=time.time())
    except Cancelled:
        with JOBS_LOCK:
            JOBS[job_id].update(status="cancelled", finished=time.time())
    except Exception as e:  # yt_dlp raises DownloadError with ANSI codes
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", error=msg, finished=time.time())
    finally:
        CANCELLED.discard(job_id)
        SLOTS.release()


def start_job(req):
    job_id = uuid.uuid4().hex[:10]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "url": req["url"], "title": req["url"], "status": "queued",
            "percent": 0, "speed": None, "eta": None, "files": [], "error": None,
            "created": time.time(), "mode": req.get("mode", "best"), "_files": set(),
        }
    threading.Thread(target=run_job, args=(job_id, req), daemon=True).start()
    return job_id


def public_jobs():
    with JOBS_LOCK:
        return sorted(({k: v for k, v in j.items() if not k.startswith("_")} for j in JOBS.values()),
                      key=lambda j: -j["created"])


# ----------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "ytdlp-dashboard"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            data = (HERE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/sites":
            self._json(catalog())
        elif path == "/api/jobs":
            self._json(public_jobs())
        elif path == "/api/version":
            self._json({"yt_dlp": yt_dlp.version.__version__, "download_dir": str(DOWNLOAD_DIR),
                        "ffmpeg": bool(shutil.which("ffmpeg"))})
        elif path.startswith("/files/"):
            self._serve_file(unquote(path[len("/files/"):]))
        else:
            self._json({"error": "not found"}, 404)

    def _serve_file(self, rel):
        target = (DOWNLOAD_DIR / rel).resolve()
        if DOWNLOAD_DIR.resolve() not in target.parents or not target.is_file():
            return self._json({"error": "not found"}, 404)
        size = target.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + __import__("urllib.parse").parse.quote(target.name))
        self.end_headers()
        with open(target, "rb") as f:
            while chunk := f.read(1 << 20):
                self.wfile.write(chunk)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            req = self._body()
        except Exception:
            return self._json({"error": "bad json"}, 400)
        url = (req.get("url") or "").strip()
        if path == "/api/match":
            return self._json({"matches": match_url(url) if url else []})
        if path == "/api/info":
            if not url:
                return self._json({"error": "url required"}, 400)
            try:
                opts = build_opts(req)
                opts["noplaylist"] = not req.get("playlist", False)
                opts["extract_flat"] = "in_playlist"
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                return self._json(summarize_info(info))
            except Exception as e:
                return self._json({"error": re.sub(r"\x1b\[[0-9;]*m", "", str(e))}, 400)
        if path == "/api/download":
            if not url:
                return self._json({"error": "url required"}, 400)
            req["url"] = url
            return self._json({"id": start_job(req)})
        if path == "/api/batch":
            urls = parse_urls(req.get("text") or "")
            if not urls:
                return self._json({"error": "no URLs found"}, 400)
            ids = [start_job({**req, "url": u}) for u in urls[:2000]]
            return self._json({"ids": ids, "count": len(ids), "skipped": max(0, len(urls) - 2000)})
        if path == "/api/jobs/cancel_all":
            with JOBS_LOCK:
                for k, j in JOBS.items():
                    if j["status"] in ("queued", "downloading", "processing"):
                        CANCELLED.add(k)
                        if j["status"] == "queued":
                            j["status"] = "cancelled"
            return self._json({"ok": True})
        m = re.fullmatch(r"/api/jobs/(\w+)/cancel", path)
        if m:
            CANCELLED.add(m.group(1))
            with JOBS_LOCK:
                j = JOBS.get(m.group(1))
                if j and j["status"] == "queued":
                    j["status"] = "cancelled"
            return self._json({"ok": True})
        if path == "/api/jobs/clear":
            with JOBS_LOCK:
                for k in [k for k, j in JOBS.items() if j["status"] in ("done", "error", "cancelled")]:
                    del JOBS[k]
            return self._json({"ok": True})
        self._json({"error": "not found"}, 404)


def main():
    global DOWNLOAD_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--dir", default=str(DOWNLOAD_DIR))
    ap.add_argument("--concurrent", type=int, default=3, help="simultaneous downloads")
    a = ap.parse_args()
    global SLOTS
    SLOTS = threading.BoundedSemaphore(max(1, a.concurrent))
    DOWNLOAD_DIR = Path(a.dir).resolve()
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"yt-dlp {yt_dlp.version.__version__} | {len(catalog())} services | downloads -> {DOWNLOAD_DIR}")
    print(f"Dashboard: http://{a.host}:{a.port}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

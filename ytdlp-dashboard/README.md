# yt-dlp Dashboard

A local web dashboard for [yt-dlp](https://github.com/yt-dlp/yt-dlp) covering every service it supports.

- **Download**: paste any URL, see which extractor matches, inspect formats, pick quality/audio-only/container, subtitles, thumbnails, playlists, cookies-from-browser, login and proxy.
- **Queue**: live progress, speed, ETA, cancel, and download links for finished files.
- **Supported sites**: searchable, filterable (working/broken, login, search, 18+), A–Z browsing. The list is generated from yt-dlp's extractor registry, so it always matches the installed version.

## Run

```bash
pip install -U yt-dlp        # ffmpeg is needed for merging and audio extraction
python3 server.py            # http://127.0.0.1:8080
python3 server.py --port 9000 --dir ~/Videos
```

Only Python 3.10+ and yt-dlp are required; the server uses the standard library. It binds to localhost by default and has no authentication, so don't expose it publicly. Only download content you have the right to download.

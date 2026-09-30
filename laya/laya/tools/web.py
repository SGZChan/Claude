"""Web tools. Everything here is network=True, so offline mode switches it all off."""
from __future__ import annotations

import urllib.parse
import urllib.request

from .helpers import Ctx, strip_html, summarize
from .registry import CONFIRM, ToolError


def fetch(ctx: Ctx, url: str) -> str:
    u = urllib.parse.urlparse(str(url))
    if u.scheme != "https" or u.hostname not in ctx.settings.web_allowlist:
        raise ToolError(f"host not allow-listed: {u.hostname}")
    with urllib.request.urlopen(str(url), timeout=15) as r:  # noqa: S310 (scheme+host checked above)
        return r.read(200_000).decode("utf-8", "replace")


def install(ctx: Ctx) -> None:
    reg = ctx.reg

    @reg.register("web_fetch", "fetch raw text of an allow-listed web page", {"url": "https URL"}, tier=CONFIRM, feature="web_digest", network=True)
    def web_fetch(url: str) -> str:
        return fetch(ctx, url)[:2000]

    @reg.register("web_digest", "fetch an allow-listed page, summarise it and remember the summary (research, read article)", {"url": "https URL"},
                  tier=CONFIRM, feature="web_digest", network=True)
    def web_digest(url: str) -> str:
        text = strip_html(fetch(ctx, url))
        summary = summarize(text, 3)
        ctx.store.add_fact("digest", f"{url}: {summary}"[:500])
        return summary or "(page had no readable text)"

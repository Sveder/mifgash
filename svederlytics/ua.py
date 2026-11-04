"""User-agent parsing with a few regexes. No dependency. Stores families only, never the raw string."""
import re

BOT_RE = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|archiver|curl/|wget/|python-requests|python-urllib|httpx|aiohttp|"
    r"go-http-client|java/|okhttp|libwww|headless|phantomjs|lighthouse|pagespeed|preview|facebookexternalhit|"
    r"whatsapp|telegram|discord|slack|embedly|monitor|uptime|pingdom|scan|feedfetcher|validator|"
    r"googleother|bingpreview|yandex|baidu|semrush|ahrefs|petal|bytespider|gptbot|claude|perplexity",
    re.I)


def parse(ua):
    ua = ua or ""
    if not ua.strip() or BOT_RE.search(ua):
        return {"browser": "bot", "os": "", "device": "bot", "is_bot": True}
    if "Edg/" in ua or "EdgA/" in ua or "EdgiOS/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "SamsungBrowser/" in ua:
        browser = "Samsung"
    elif "Firefox/" in ua or "FxiOS/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "Other"
    if "Windows" in ua:
        os_ = "Windows"
    elif "Android" in ua:
        os_ = "Android"
    elif re.search(r"iPhone|iPad|iPod", ua):
        os_ = "iOS"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os_ = "macOS"
    elif "CrOS" in ua:
        os_ = "ChromeOS"
    elif "Linux" in ua:
        os_ = "Linux"
    else:
        os_ = "Other"
    if "iPad" in ua or "Tablet" in ua or (os_ == "Android" and "Mobile" not in ua):
        device = "tablet"
    elif re.search(r"Mobi|iPhone|iPod", ua):
        device = "mobile"
    else:
        device = "desktop"
    return {"browser": browser, "os": os_, "device": device, "is_bot": False}

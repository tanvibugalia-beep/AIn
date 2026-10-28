"""
Web scraping and URL ingestion utility for Daksh Intelligence Knowledge Base.
Replicates /api/knowledge/fetch-url from server.ts.
"""

import re
import html
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any

def fetch_url_content(url: str, timeout: int = 8) -> Dict[str, Any]:
    """
    Fetches the content of a web page URL, strips scripts/styles/HTML tags,
    and returns clean text with title and metadata.
    """
    target_url = url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = f"https://{target_url}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DakshIntelligence/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        req = urllib.request.Request(target_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw_html = response.read().decode(charset, errors="replace")

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = html.unescape(title_match.group(1).strip())
        else:
            title = urllib.parse.urlparse(target_url).hostname or target_url

        # Strip scripts, styles, noscript, svg
        clean_text = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", " ", raw_html, flags=re.IGNORECASE)
        clean_text = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>", " ", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"<noscript\b[^<]*(?:(?!<\/noscript>)<[^<]*)*<\/noscript>", " ", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"<svg\b[^<]*(?:(?!<\/svg>)<[^<]*)*<\/svg>", " ", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"<[^>]+>", " ", clean_text)
        clean_text = html.unescape(clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        # Truncate if excessively long (keep first ~15,000 characters)
        if len(clean_text) > 15000:
            clean_text = clean_text[:15000] + "... [Content truncated for ingestion]"

        words = len(clean_text.split())

        return {
            "title": title,
            "url": target_url,
            "content": clean_text,
            "wordCount": words,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "success": True,
            "error": None,
        }

    except urllib.error.HTTPError as e:
        return {
            "title": target_url,
            "url": target_url,
            "content": "",
            "wordCount": 0,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "error": f"HTTP Error {e.code}: {e.reason}",
        }
    except Exception as e:
        return {
            "title": target_url,
            "url": target_url,
            "content": "",
            "wordCount": 0,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "error": str(e),
        }

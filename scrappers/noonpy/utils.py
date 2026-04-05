"""
Noon URL helpers.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlparse


def parse_noon_product_url(url: str, locale: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """
    Parse Noon product URL and return (base_url, product_id).
    Noon product URLs usually look like:
      https://www.noon.com/<locale>/<product_id>/p/
    """
    if not url:
        return None

    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if not parsed.netloc or "noon.com" not in parsed.netloc.lower():
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    locale_from_url = path_parts[0] if path_parts else None
    active_locale = locale or locale_from_url or "egypt-en"

    product_match = re.search(r"/([A-Za-z0-9_-]{6,})/p(?:/|\?|$)", parsed.path + ("?" if parsed.query else ""))
    if not product_match:
        return None

    product_id = product_match.group(1)
    base_url = f"https://www.noon.com/{active_locale}/"
    return base_url, product_id


def format_noon_product_url(product_id: str, locale: str = "egypt-en") -> str:
    return f"https://www.noon.com/{locale}/{product_id}/p/"


"""
Jumia URL helpers.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

COUNTRY_TO_DOMAIN = {
    "eg": "com.eg",
    "dz": "dz",
    "ci": "ci",
    "gh": "com.gh",
    "ke": "co.ke",
    "ma": "ma",
    "ng": "com.ng",
    "sn": "sn",
    "ug": "ug",
    "tn": "com.tn",
}

_PRODUCT_HTML_ID_PATTERN = re.compile(r"-([0-9]{5,})\.html/?$", flags=re.IGNORECASE)
_SKU_PATH_PATTERN = re.compile(r"/catalog/productspecifications/sku/([A-Za-z0-9_-]{6,})(?:/|$)", flags=re.IGNORECASE)
_SKU_TOKEN_PATTERN = re.compile(r"\b([A-Z0-9]{8,}FAMZ)\b", flags=re.IGNORECASE)


def normalize_jumia_domain(country_or_domain: Optional[str] = None) -> str:
    """
    Resolve user input to a valid Jumia domain suffix.

    Examples:
      eg -> com.eg
      com.eg -> com.eg
      jumia.com.eg -> com.eg
    """
    default_domain = "com.eg"
    if not country_or_domain:
        return default_domain

    value = country_or_domain.strip().lower()
    if not value:
        return default_domain

    value = value.replace("https://", "").replace("http://", "").strip("/")
    if value.startswith("www."):
        value = value[4:]
    if value.startswith("jumia."):
        value = value[len("jumia.") :]

    if value in COUNTRY_TO_DOMAIN:
        return COUNTRY_TO_DOMAIN[value]
    if value in COUNTRY_TO_DOMAIN.values():
        return value
    if "." in value:
        return value
    if re.fullmatch(r"[a-z]{2}", value):
        return f"com.{value}"
    return default_domain


def parse_jumia_product_url(url: str, default_domain: str = "com.eg") -> Optional[Tuple[str, str]]:
    """
    Parse Jumia product URL and return (base_url, product_id).
    product_id is numeric listing ID or SKU (e.g. ...FAMZ).
    """
    if not url:
        return None

    parsed = urlparse(url.strip())
    domain = _domain_from_host(parsed.netloc) or normalize_jumia_domain(default_domain)
    if "jumia." not in parsed.netloc.lower():
        return None

    product_id = extract_jumia_product_id(url)
    if not product_id:
        return None

    return f"https://www.jumia.{domain}/", product_id


def extract_jumia_product_id(url: str) -> Optional[str]:
    if not url:
        return None

    parsed = urlparse(url.strip())
    path = parsed.path or ""

    sku_match = _SKU_PATH_PATTERN.search(path)
    if sku_match:
        return sku_match.group(1).upper()

    query = parse_qs(parsed.query)
    sku_query = query.get("sku")
    if sku_query and sku_query[0].strip():
        return sku_query[0].strip().upper()

    id_match = _PRODUCT_HTML_ID_PATTERN.search(path.rstrip("/"))
    if id_match:
        return id_match.group(1)

    sku_token_match = _SKU_TOKEN_PATTERN.search(path)
    if sku_token_match:
        return sku_token_match.group(1).upper()

    return None


def canonicalize_jumia_product_url(url: str, default_domain: str = "com.eg") -> Optional[str]:
    if not url:
        return None

    parsed = urlparse(url.strip())
    if "jumia." not in parsed.netloc.lower():
        return None

    domain = _domain_from_host(parsed.netloc) or normalize_jumia_domain(default_domain)
    path = parsed.path or ""

    sku_match = _SKU_PATH_PATTERN.search(path)
    if sku_match:
        return format_jumia_sku_url(sku_match.group(1), domain=domain)

    query = parse_qs(parsed.query)
    sku_query = query.get("sku")
    if sku_query and sku_query[0].strip():
        return format_jumia_sku_url(sku_query[0], domain=domain)

    if _PRODUCT_HTML_ID_PATTERN.search(path.rstrip("/")):
        clean_path = path.rstrip("/")
        if not clean_path.startswith("/"):
            clean_path = f"/{clean_path}"
        return f"https://www.jumia.{domain}{clean_path}"

    return None


def format_jumia_sku_url(sku: str, domain: str = "com.eg") -> str:
    clean_sku = (sku or "").strip().upper()
    return f"https://www.jumia.{normalize_jumia_domain(domain)}/catalog/productspecifications/sku/{clean_sku}/"


def _domain_from_host(host: str) -> Optional[str]:
    if not host:
        return None

    value = host.lower().strip()
    if value.startswith("www."):
        value = value[4:]
    if ":" in value:
        value = value.split(":", 1)[0]
    if "jumia." not in value:
        return None

    return value.split("jumia.", 1)[1] or None

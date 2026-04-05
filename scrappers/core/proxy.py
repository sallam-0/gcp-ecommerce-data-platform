"""
Shared proxy utilities for all scraper modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

SUPPORTED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


def normalize_proxy_url(value: str, default_scheme: str = "http") -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Empty proxy URL")

    if "://" not in cleaned:
        cleaned = f"{default_scheme}://{cleaned}"

    parsed = urlparse(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        allowed = ", ".join(sorted(SUPPORTED_PROXY_SCHEMES))
        raise ValueError(f"Unsupported proxy scheme '{scheme}'. Supported: {allowed}")

    if not parsed.hostname:
        raise ValueError(f"Invalid proxy URL (missing hostname): {value}")

    return cleaned


def normalize_proxy_dict(proxy: Dict[str, str], default_scheme: str = "http") -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in proxy.items():
        normalized_value = normalize_proxy_url(str(value), default_scheme=default_scheme)
        key_name = str(key).strip().lower()

        if key_name == "all":
            normalized["http"] = normalized_value
            normalized["https"] = normalized_value
        elif key_name in {"http", "https"}:
            normalized[key_name] = normalized_value

    if not normalized:
        raise ValueError(f"Invalid proxy entry: {proxy}")

    if "http" not in normalized and "https" in normalized:
        normalized["http"] = normalized["https"]
    if "https" not in normalized and "http" in normalized:
        normalized["https"] = normalized["http"]

    return normalized


def parse_proxy_entry(raw: str, default_scheme: str = "http") -> Dict[str, str]:
    value = raw.strip()
    if not value:
        raise ValueError("Empty proxy entry")

    if value.startswith("{"):
        parsed = json.loads(value)
        if not isinstance(parsed, dict) or not parsed:
            raise ValueError(f"Invalid JSON proxy entry: {raw}")
        return normalize_proxy_dict(parsed, default_scheme=default_scheme)

    if value.lower().startswith(("http=", "https=", "all=")):
        proxy_dict: Dict[str, str] = {}
        for item in value.split(","):
            if "=" not in item:
                raise ValueError(f"Invalid key=value proxy entry: {raw}")
            key, val = item.split("=", 1)
            proxy_dict[key.strip()] = val.strip()
        return normalize_proxy_dict(proxy_dict, default_scheme=default_scheme)

    normalized = normalize_proxy_url(value, default_scheme=default_scheme)
    return {"http": normalized, "https": normalized}


def load_proxy_pool(
    proxy_args: Optional[Iterable[str]] = None,
    proxy_file: Optional[str] = None,
    default_scheme: str = "http",
) -> List[Dict[str, str]]:
    pool: List[Dict[str, str]] = []

    if proxy_args:
        for entry in proxy_args:
            pool.append(parse_proxy_entry(entry, default_scheme=default_scheme))

    if proxy_file:
        path = Path(proxy_file)
        if not path.exists():
            raise FileNotFoundError(f"Proxy file not found: {proxy_file}")

        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            pool.append(parse_proxy_entry(stripped, default_scheme=default_scheme))

    return pool


def mask_proxy_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return url

        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"

        if parsed.username:
            user_part = "***"
            if parsed.password:
                user_part += ":***"
            netloc = f"{user_part}@{host}"
        else:
            netloc = host

        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return url


def proxy_label(proxy_cfg: Dict[str, str]) -> str:
    candidate = proxy_cfg.get("https") or proxy_cfg.get("http") or ""
    return mask_proxy_url(candidate)

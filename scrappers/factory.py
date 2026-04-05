"""
Factory helpers for creating site scrapers from one shared entrypoint.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from .amzpy.scraper import AmazonScraper
from .jumiapy.scraper import JumiaScraper
from .noonpy.scraper import NoonScraper

SUPPORTED_SITES = ("amazon", "noon", "jumia")


def create_scraper(
    site: str,
    impersonate: Optional[str] = None,
    proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
    country_code: str = "eg",
    locale: str = "egypt-en",
):
    site_name = (site or "").strip().lower()
    if site_name == "amazon":
        return AmazonScraper(
            country_code=country_code,
            impersonate=impersonate,
            proxies=proxies,
        )
    if site_name == "noon":
        return NoonScraper(
            locale=locale,
            impersonate=impersonate,
            proxies=proxies,
        )
    if site_name == "jumia":
        return JumiaScraper(
            country_code=country_code,
            impersonate=impersonate,
            proxies=proxies,
        )

    supported = ", ".join(SUPPORTED_SITES)
    raise ValueError(f"Unsupported site '{site}'. Supported values: {supported}")


def get_scraper(site: str, **kwargs):
    """
    Backward-compatible alias for older code paths that imported get_scraper.
    """
    return create_scraper(site=site, **kwargs)

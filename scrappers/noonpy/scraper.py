"""
Noon Product Scraper Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Main Noon scraper built on shared reusable scraping primitives.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote_plus

from ..core.scraper import BaseEcommerceScraper
from .parser import parse_pagination_url, parse_product_page, parse_search_page
from .session import DEFAULT_CONFIG, NoonSession
from .utils import format_noon_product_url, parse_noon_product_url


class NoonScraper(BaseEcommerceScraper):
    """
    High-level scraper for Noon product and search data.
    """

    def __init__(
        self,
        locale: str = "egypt-en",
        impersonate: Optional[str] = None,
        proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
    ):
        self.locale = locale
        session = NoonSession(
            locale=locale,
            impersonate=impersonate,
            proxies=proxies,
        )
        super().__init__(country_code=locale, session=session, default_config=DEFAULT_CONFIG)
        print(f"NoonScraper initialized for noon.com/{locale}")

    def site_base_url(self) -> str:
        return f"https://www.noon.com/{self.locale}"

    def build_search_url(self, query: str) -> str:
        return f"{self.site_base_url()}/search?q={quote_plus(query)}"

    def normalize_product_url(self, url: str) -> Optional[str]:
        parsed_info = parse_noon_product_url(url, locale=self.locale)
        if not parsed_info:
            return None
        _, product_id = parsed_info
        return format_noon_product_url(product_id, locale=self.locale)

    def parse_product_html(self, html_content: str, url: str) -> Optional[Dict[str, Any]]:
        return parse_product_page(html_content=html_content, url=url, locale=self.locale)

    def parse_search_html(self, html_content: str) -> List[Dict[str, Any]]:
        return parse_search_page(
            html_content,
            self.site_base_url(),
            locale=self.locale,
        )

    def parse_next_page_url(self, html_content: str) -> Optional[str]:
        return parse_pagination_url(html_content, self.site_base_url())


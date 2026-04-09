"""
Jumia Product Scraper Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Main Jumia scraper built on shared reusable scraping primitives.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from urllib.parse import quote_plus

from ..core.scraper import BaseEcommerceScraper
from .parser import parse_pagination_url, parse_product_page, parse_search_page
from .session import DEFAULT_CONFIG, JumiaSession
from .utils import (
    canonicalize_jumia_product_url,
    format_jumia_sku_url,
    normalize_jumia_domain,
    parse_jumia_product_url,
)


class JumiaScraper(BaseEcommerceScraper):
    """
    High-level scraper for Jumia product and search data.
    """

    def __init__(
        self,
        country_code: str = "eg",
        impersonate: Optional[str] = None,
        proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
    ):
        self.domain = normalize_jumia_domain(country_code)
        session = JumiaSession(
            country_code=country_code,
            impersonate=impersonate,
            proxies=proxies,
        )
        super().__init__(country_code=self.domain, session=session, default_config=DEFAULT_CONFIG)
        print(f"JumiaScraper initialized for jumia.{self.domain}")

    def site_base_url(self) -> str:
        return f"https://www.jumia.{self.domain}"

    def build_search_url(self, query: str) -> str:
        return f"{self.site_base_url()}/catalog/?q={quote_plus(query)}"

    def normalize_product_url(self, url: str) -> Optional[str]:
        canonical = canonicalize_jumia_product_url(url, default_domain=self.domain)
        if canonical:
            return canonical

        parsed_info = parse_jumia_product_url(url, default_domain=self.domain)
        if not parsed_info:
            return None

        _, product_id = parsed_info
        if product_id.isdigit():
            cleaned = (url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
            return cleaned if cleaned else None
        return format_jumia_sku_url(product_id, domain=self.domain)

    def parse_product_html(self, html_content: str, url: str) -> Optional[Dict[str, Any]]:
        return parse_product_page(html_content=html_content, url=url, domain=self.domain)

    def parse_search_html(self, html_content: str, max_products: Optional[int] = None) -> List[Dict[str, Any]]:
        return parse_search_page(
            html_content,
            self.site_base_url(),
            domain=self.domain,
            max_products=max_products,
        )

    def parse_next_page_url(self, html_content: str) -> Optional[str]:
        return parse_pagination_url(html_content, self.site_base_url())

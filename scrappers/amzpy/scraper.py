"""
Amazon Product Scraper Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Main Amazon scraper built on shared reusable scraping primitives.
"""

from __future__ import annotations

from urllib.parse import quote_plus
from typing import Any, Dict, List, Optional, Union

from ..core.scraper import BaseEcommerceScraper
from .parser import parse_pagination_url, parse_product_page, parse_search_page
from .session import DEFAULT_CONFIG, AmzSession
from .utils import parse_amazon_url


class AmazonScraper(BaseEcommerceScraper):
    """
    High-level scraper for Amazon product and search data.
    """

    def __init__(
        self,
        country_code: str = "com",
        impersonate: str = None,
        proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
    ):
        session = AmzSession(
            country_code=country_code,
            impersonate=impersonate,
            proxies=proxies,
        )
        super().__init__(country_code=country_code, session=session, default_config=DEFAULT_CONFIG)
        print(f"AmazonScraper initialized for amazon.{country_code}")

    def site_base_url(self) -> str:
        return f"https://www.amazon.{self.country_code}"

    def build_search_url(self, query: str) -> str:
        return f"{self.site_base_url()}/s?k={quote_plus(query)}"

    def normalize_product_url(self, url: str) -> Optional[str]:
        parsed_info = parse_amazon_url(url)
        if not parsed_info:
            return None

        base_url, product_id = parsed_info
        return f"{base_url}dp/{product_id}"

    def parse_product_html(self, html_content: str, url: str) -> Optional[Dict[str, Any]]:
        return parse_product_page(html_content=html_content, url=url, country_code=self.country_code)

    def parse_search_html(self, html_content: str, max_products: Optional[int] = None) -> List[Dict[str, Any]]:
        return parse_search_page(
            html_content,
            self.site_base_url(),
            country_code=self.country_code,
            max_products=max_products,
        )

    def parse_next_page_url(self, html_content: str) -> Optional[str]:
        return parse_pagination_url(html_content, self.site_base_url())

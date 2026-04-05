"""
Shared scraper flow for ecommerce websites.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from ast import literal_eval
from typing import Any, Dict, List, Optional


class BaseEcommerceScraper(ABC):
    """
    Base class that encapsulates common product/detail/search flow.
    """

    def __init__(self, country_code: str, session: Any, default_config: Dict[str, Any]):
        self.country_code = country_code
        self.session = session
        self.user_config = default_config.copy()

    def config(self, config_str: str = None, **kwargs: Any) -> Dict[str, Any]:
        if config_str:
            try:
                parts = config_str.split(",")
                for part in parts:
                    key, value = part.split("=", 1)
                    self.user_config[key.strip()] = literal_eval(value.strip())
            except Exception as exc:
                print(f"Error parsing configuration string: {exc}")
                print("Format should be: 'PARAM1 = value1, PARAM2 = value2'")

        if kwargs:
            self.user_config.update(kwargs)

        self.session.update_config(**self.user_config)
        return self.user_config

    def get_product_details(self, url: str) -> Optional[Dict[str, Any]]:
        product_url = self.normalize_product_url(url)
        if not product_url:
            print(f"Invalid product URL: {url}")
            return None

        print(f"Fetching product data: {product_url}")
        response = self.session.get(product_url)
        if not response or not response.text:
            print(f"Failed to fetch product page for: {product_url}")
            return None

        product_data = self.parse_product_html(response.text, product_url)
        if not product_data:
            print(f"Failed to extract product data from: {product_url}")
            return None

        print(f"Successfully extracted data for: {product_data.get('title', 'Unknown Product')[:50]}...")
        return product_data

    def search_products(
        self,
        query: str = None,
        search_url: str = None,
        max_pages: int = 1,
        max_products: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not query and not search_url:
            print("Error: Either a search query or search URL must be provided")
            return []

        if not search_url and query:
            search_url = self.build_search_url(query)

        print(f"Starting product search: {search_url}")

        all_products: List[Dict[str, Any]] = []
        current_url = search_url
        current_page = 1

        while current_url and current_page <= max_pages:
            print(f"\nScraping search page {current_page}/{max_pages}: {current_url}")

            response = self.session.get(current_url)
            if not response or not response.text:
                print(f"Failed to fetch search page: {current_url}")
                break

            products = self.parse_search_html(response.text)
            if not products:
                print(f"No products found on page {current_page} (or page was blocked)")
                break

            print(f"Found {len(products)} products on page {current_page}")
            all_products.extend(products)

            if max_products and max_products > 0 and len(all_products) >= max_products:
                all_products = all_products[:max_products]
                print(f"Reached max products limit ({max_products}). Stopping early.")
                break

            if current_page >= max_pages:
                break

            next_url = self.parse_next_page_url(response.text)
            if not next_url:
                print("No next page found. End of results.")
                break

            current_url = next_url
            current_page += 1

        print(f"\nSearch completed. Total products found: {len(all_products)}")
        return all_products

    @abstractmethod
    def site_base_url(self) -> str:
        """Return site base URL."""

    @abstractmethod
    def build_search_url(self, query: str) -> str:
        """Build a site-specific search URL from query text."""

    @abstractmethod
    def normalize_product_url(self, url: str) -> Optional[str]:
        """Return canonical product URL or None if invalid."""

    @abstractmethod
    def parse_product_html(self, html_content: str, url: str) -> Optional[Dict[str, Any]]:
        """Parse product page HTML."""

    @abstractmethod
    def parse_search_html(self, html_content: str) -> List[Dict[str, Any]]:
        """Parse search page HTML."""

    @abstractmethod
    def parse_next_page_url(self, html_content: str) -> Optional[str]:
        """Extract next-page URL from search HTML."""

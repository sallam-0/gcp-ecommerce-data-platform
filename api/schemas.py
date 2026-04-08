from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    site: Optional[Literal["amazon", "jumia", "noon"]] = Field(
        default=None,
        description="Target site. Optional when using product_url/search_url because it can be inferred.",
    )
    query: Optional[str] = Field(default=None, description="Search query text mode.")
    search_url: Optional[str] = Field(default=None, description="Direct search URL mode.")
    product_url: Optional[str] = Field(default=None, description="Single product URL mode.")

    country_code: str = Field(default="eg", description="Amazon TLD / Jumia country hint.")
    locale: str = Field(default="egypt-en", description="Noon locale.")
    impersonate: str = Field(default="chrome120", description="curl_cffi browser fingerprint.")

    max_pages: int = Field(default=1, ge=1, description="Max search pages to scrape.")
    max_products: int = Field(default=50, ge=1, description="Max products to keep.")

    proxy: List[str] = Field(default_factory=list, description="Proxy entries (repeatable style).")
    proxy_file: Optional[str] = Field(default=None, description="Path to proxy file.")
    proxy_scheme: str = Field(default="http", description="Default scheme for host:port proxy entries.")
    rotate_every: int = Field(default=1, ge=1, description="Rotate proxy every N requests.")
    max_proxy_attempts: int = Field(default=3, ge=1, description="Retries with different entry proxies.")

    max_retries: int = Field(default=3, ge=0, description="HTTP retries inside site session.")
    request_timeout: int = Field(default=25, ge=1, description="Request timeout in seconds.")
    min_delay: float = Field(default=2.5, gt=0, description="Minimum delay between requests.")
    max_delay: float = Field(default=4.0, gt=0, description="Maximum delay between requests.")
    fast_mode: bool = Field(default=False, description="Reduce retries and delays for faster responses.")


class SearchResponse(BaseModel):
    job_id: str
    status: str
    message: str
    best_match: Optional[Dict[str, Any]] = None

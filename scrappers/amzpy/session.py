"""
Amazon session implementation built on top of shared core session logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from ..core.session import BaseSession, DEFAULT_SESSION_CONFIG

DEFAULT_CONFIG = DEFAULT_SESSION_CONFIG.copy()

AMAZON_BLOCK_MARKERS = (
    "captcha",
    "api-services-support@amazon.com",
    "enter the characters you see below",
)


class AmzSession(BaseSession):
    """
    Amazon-specific session wrapper around BaseSession.
    """

    def __init__(
        self,
        country_code: str = "com",
        impersonate: Optional[str] = None,
        proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.country_code = country_code
        self.base_url = f"https://www.amazon.{self.country_code}/"

        super().__init__(
            base_url=self.base_url,
            site_label=f"amazon.{country_code}",
            impersonate=impersonate,
            proxies=proxies,
            config=config,
            block_markers=AMAZON_BLOCK_MARKERS,
        )

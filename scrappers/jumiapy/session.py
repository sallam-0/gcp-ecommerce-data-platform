"""
Jumia session implementation built on shared core session logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from ..core.session import BaseSession, DEFAULT_SESSION_CONFIG
from .utils import normalize_jumia_domain

DEFAULT_CONFIG = DEFAULT_SESSION_CONFIG.copy()

JUMIA_BLOCK_MARKERS = (
    "captcha",
    "verify you are human",
    "access denied",
    "security check",
    "attention required",
    "cloudflare",
    "blocked",
)


class JumiaSession(BaseSession):
    """
    Jumia-specific session wrapper around BaseSession.
    """

    def __init__(
        self,
        country_code: str = "eg",
        impersonate: Optional[str] = None,
        proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.domain = normalize_jumia_domain(country_code)
        self.base_url = f"https://www.jumia.{self.domain}/"

        super().__init__(
            base_url=self.base_url,
            site_label=f"jumia.{self.domain}",
            impersonate=impersonate,
            proxies=proxies,
            config=config,
            block_markers=JUMIA_BLOCK_MARKERS,
        )

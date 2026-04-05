"""
Noon session implementation built on shared core session logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from ..core.session import BaseSession, DEFAULT_SESSION_CONFIG

DEFAULT_CONFIG = DEFAULT_SESSION_CONFIG.copy()

NOON_BLOCK_MARKERS = (
    "captcha",
    "verify you are human",
    "access denied",
    "security check",
)


class NoonSession(BaseSession):
    """
    Noon-specific session wrapper around BaseSession.
    """

    def __init__(
        self,
        locale: str = "egypt-en",
        impersonate: Optional[str] = None,
        proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.locale = locale
        self.base_url = f"https://www.noon.com/{self.locale}/"

        super().__init__(
            base_url=self.base_url,
            site_label=f"noon.{locale}",
            impersonate=impersonate,
            proxies=proxies,
            config=config,
            block_markers=NOON_BLOCK_MARKERS,
        )


"""
Shared HTTP session primitives for scraper implementations.
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import curl_cffi.requests
from curl_cffi.requests.errors import RequestsError
from fake_useragent import UserAgent

from .proxy import normalize_proxy_dict, proxy_label

DEFAULT_SESSION_CONFIG: Dict[str, Any] = {
    "MAX_RETRIES": 3,
    "REQUEST_TIMEOUT": 25,
    "DELAY_BETWEEN_REQUESTS": (2, 5),
    "DEFAULT_IMPERSONATE": "chrome120",
}

DEFAULT_BROWSER_HEADERS: Dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

DEFAULT_BLOCK_MARKERS: Tuple[str, ...] = (
    "captcha",
    "verify you are human",
    "access denied",
    "bot check",
)

FALLBACK_USER_AGENTS: Tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
)


class BaseSession:
    """
    Reusable session manager for ecommerce scrapers.
    """

    def __init__(
        self,
        base_url: str,
        site_label: str,
        impersonate: Optional[str] = None,
        proxies: Optional[Union[Dict[str, str], List[Dict[str, str]]]] = None,
        config: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        block_markers: Optional[Sequence[str]] = None,
    ):
        self.base_url = base_url
        self.site_label = site_label

        self.config = DEFAULT_SESSION_CONFIG.copy()
        if config:
            self.config.update(config)

        self.block_markers = tuple(marker.lower() for marker in (block_markers or DEFAULT_BLOCK_MARKERS))

        try:
            self.ua_generator: Optional[UserAgent] = UserAgent(browsers=["Chrome"], os=["Windows", "Mac OS X"])
        except Exception:
            self.ua_generator = None

        self.session = curl_cffi.requests.Session()
        self.session.impersonate = impersonate or self.config["DEFAULT_IMPERSONATE"]

        self.proxy_pool: List[Dict[str, str]] = []
        self.proxy_rotate_every = 1
        self.proxy_request_counter = 0
        self.current_proxy_label: Optional[str] = None

        self.stats: Dict[str, Any] = {
            "requests_total": 0,
            "responses_ok": 0,
            "responses_non_200": 0,
            "network_errors": 0,
            "captcha_blocks": 0,
            "last_status_code": None,
            "proxy_stats": {},
        }

        merged_headers = DEFAULT_BROWSER_HEADERS.copy()
        if headers:
            merged_headers.update(headers)
        merged_headers["User-Agent"] = self._random_user_agent()
        self.session.headers = merged_headers

        if proxies:
            if isinstance(proxies, list):
                self.set_proxy_pool(proxies, rotate_every=1, start_random=True)
            else:
                normalized = normalize_proxy_dict(proxies)
                self.session.proxies = normalized
                self.current_proxy_label = proxy_label(normalized)
                self.proxy_pool = [normalized]

        try:
            self.session.get(self.base_url, headers=merged_headers, timeout=self.config["REQUEST_TIMEOUT"])
        except Exception as exc:
            print(f"Warning: failed to prefetch cookies from {self.base_url}: {exc}")

        print(f"Session initialized for {self.site_label}")
        print(f"Impersonating: {self.session.impersonate}")
        print(f"User-Agent: {merged_headers['User-Agent'][:70]}...")
        if self.current_proxy_label:
            print(f"Initial proxy: {self.current_proxy_label}")

    def set_proxy_pool(
        self,
        proxies: Iterable[Dict[str, str]],
        rotate_every: int = 1,
        start_random: bool = True,
    ) -> None:
        normalized_pool = [normalize_proxy_dict(entry) for entry in proxies]
        if not normalized_pool:
            return

        self.proxy_pool = normalized_pool
        self.proxy_rotate_every = max(1, int(rotate_every))
        self.proxy_request_counter = 0

        index = random.randrange(len(self.proxy_pool)) if start_random and len(self.proxy_pool) > 1 else 0
        self.session.proxies = self.proxy_pool[index]
        self.current_proxy_label = proxy_label(self.proxy_pool[index])
        print(f"Proxy pool loaded: {len(self.proxy_pool)} proxies, rotate every {self.proxy_rotate_every} request(s)")

    def update_config(self, **kwargs: Any) -> None:
        self.config.update(kwargs)
        print(f"Updated session configuration: {kwargs}")

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> Optional[curl_cffi.requests.Response]:
        if not url.startswith("http"):
            if url.startswith("/"):
                url = f"{self.base_url.rstrip('/')}{url}"
            else:
                url = f"{self.base_url}{url}"

        max_retries = int(self.config["MAX_RETRIES"])
        timeout = int(self.config["REQUEST_TIMEOUT"])
        min_delay, max_delay = self._validate_delay_range(self.config["DELAY_BETWEEN_REQUESTS"])

        for attempt in range(max_retries + 1):
            self._maybe_rotate_proxy()
            merged_headers = self.session.headers.copy()
            merged_headers["User-Agent"] = self._random_user_agent()
            if headers:
                merged_headers.update(headers)

            delay_factor = 1 + (attempt * 0.5)
            delay = random.uniform(min_delay * delay_factor, max_delay * delay_factor)
            print(f"Request attempt {attempt + 1}/{max_retries + 1}: GET {url} (delay: {delay:.2f}s)")
            time.sleep(delay)

            self.stats["requests_total"] += 1
            self._touch_proxy_stats("requests")

            try:
                response = self.session.get(
                    url,
                    headers=merged_headers,
                    timeout=timeout,
                    allow_redirects=True,
                )

                self.stats["last_status_code"] = response.status_code

                if response.status_code != 200:
                    self.stats["responses_non_200"] += 1
                    self._touch_proxy_stats("non_200")
                    print(f"Warning: Received HTTP {response.status_code} for {url}")
                    if 500 <= response.status_code < 600 and attempt < max_retries:
                        continue

                if self.is_blocked_response(response.text):
                    self.stats["captcha_blocks"] += 1
                    self._touch_proxy_stats("captcha_blocks")
                    print("CAPTCHA or anti-bot measure detected in response")
                    if attempt < max_retries:
                        block_delay = delay * 3
                        print(f"Waiting {block_delay:.2f}s before retry...")
                        time.sleep(block_delay)
                        continue
                    return response

                self.stats["responses_ok"] += 1
                self._touch_proxy_stats("successes")
                print(f"Request successful: {url} (Status: {response.status_code})")
                return response

            except RequestsError as exc:
                self.stats["network_errors"] += 1
                self._touch_proxy_stats("network_errors")
                print(f"Network error on attempt {attempt + 1}: {exc}")
                if attempt == max_retries:
                    print(f"Max retries reached. Network error: {exc}")
                    return None
                time.sleep(delay * 2)

            except Exception as exc:
                self.stats["network_errors"] += 1
                self._touch_proxy_stats("network_errors")
                print(f"Unexpected error on attempt {attempt + 1}: {exc}")
                if attempt == max_retries:
                    print(f"Max retries reached. Error: {exc}")
                    return None
                time.sleep(delay * 2)

        return None

    def is_blocked_response(self, text: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        return any(marker in lower for marker in self.block_markers)

    def get_stats(self) -> Dict[str, Any]:
        total = self.stats["requests_total"]
        successes = self.stats["responses_ok"]
        captcha_blocks = self.stats["captcha_blocks"]

        snapshot = {
            "requests_total": total,
            "responses_ok": successes,
            "responses_non_200": self.stats["responses_non_200"],
            "network_errors": self.stats["network_errors"],
            "captcha_blocks": captcha_blocks,
            "last_status_code": self.stats["last_status_code"],
            "success_rate": round(successes / total, 4) if total else 0.0,
            "captcha_rate": round(captcha_blocks / total, 4) if total else 0.0,
            "proxy_stats": {},
        }

        for proxy_name, values in self.stats["proxy_stats"].items():
            proxy_total = values.get("requests", 0)
            proxy_successes = values.get("successes", 0)
            proxy_captcha = values.get("captcha_blocks", 0)
            snapshot["proxy_stats"][proxy_name] = {
                **values,
                "success_rate": round(proxy_successes / proxy_total, 4) if proxy_total else 0.0,
                "captcha_rate": round(proxy_captcha / proxy_total, 4) if proxy_total else 0.0,
            }

        return snapshot

    def _maybe_rotate_proxy(self) -> None:
        if not self.proxy_pool:
            return

        if self.proxy_request_counter % self.proxy_rotate_every == 0:
            chosen = self.proxy_pool[0] if len(self.proxy_pool) == 1 else random.choice(self.proxy_pool)
            self.session.proxies = chosen
            self.current_proxy_label = proxy_label(chosen)
            print(f"[proxy-rotation] Using proxy: {self.current_proxy_label}")

        self.proxy_request_counter += 1

    def _touch_proxy_stats(self, metric: str) -> None:
        label = self.current_proxy_label or "direct"
        if label not in self.stats["proxy_stats"]:
            self.stats["proxy_stats"][label] = {
                "requests": 0,
                "successes": 0,
                "non_200": 0,
                "network_errors": 0,
                "captcha_blocks": 0,
            }
        self.stats["proxy_stats"][label][metric] += 1

    def _random_user_agent(self) -> str:
        if self.ua_generator:
            try:
                return self.ua_generator.random
            except Exception:
                pass
        return random.choice(FALLBACK_USER_AGENTS)

    @staticmethod
    def _validate_delay_range(raw_delay: Union[Tuple[Any, Any], List[Any]]) -> Tuple[float, float]:
        if not isinstance(raw_delay, (list, tuple)) or len(raw_delay) != 2:
            return 2.0, 5.0
        try:
            min_delay = float(raw_delay[0])
            max_delay = float(raw_delay[1])
            if min_delay <= 0 or max_delay <= 0 or min_delay > max_delay:
                return 2.0, 5.0
            return min_delay, max_delay
        except Exception:
            return 2.0, 5.0

"""Shared HTTP helpers with retries."""
from __future__ import annotations

import logging
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from etl.config import REQUEST_TIMEOUT, USER_AGENT

log = logging.getLogger(__name__)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


class HttpError(RuntimeError):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.RequestException, HttpError)),
)
def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    log.info("GET %s params=%s", url, params)
    resp = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code >= 400:
        raise HttpError(f"{resp.status_code} for {url}: {resp.text[:300]}")
    return resp.json()


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(requests.RequestException),
)
def get_text(url: str, params: dict[str, Any] | None = None) -> str:
    resp = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from subprocess import CompletedProcess
from typing import Any

from .product_research import ProductContext


class LocalChromeError(RuntimeError):
    pass


CHROME_EXTRACT_SCRIPT = """
(() => JSON.stringify({
  title: document.title || "",
  h1: document.querySelector("h1")?.textContent?.trim() || "",
  prodTitle: document.querySelector(".prod-buy-header__title")?.textContent?.trim() || "",
  ogTitle: document.querySelector('meta[property="og:title"]')?.getAttribute("content") || "",
  twitterTitle: document.querySelector('meta[name="twitter:title"]')?.getAttribute("content") || "",
  imageUrl: document.querySelector('meta[property="og:image"]')?.getAttribute("content") || "",
  url: location.href,
  bodyHead: (document.body?.innerText || "").slice(0, 800)
}))()
""".strip()

CHROME_APPLESCRIPT = """
on run argv
  set targetUrl to item 1 of argv
  set extractionScript to item 2 of argv
  tell application "Google Chrome"
    activate
    if (count of windows) = 0 then make new window
    set targetWindow to front window
    set targetTab to make new tab at end of tabs of targetWindow with properties {URL:targetUrl}
    set active tab index of targetWindow to (count of tabs of targetWindow)
    repeat with i from 1 to 80
      delay 0.25
      try
        tell targetTab to set readyState to execute javascript "document.readyState"
        if readyState is "interactive" or readyState is "complete" then exit repeat
      end try
    end repeat
    delay 2
    tell targetTab to return execute javascript extractionScript
  end tell
end run
""".strip()


def fetch_chrome_product_context(
    product_url: str,
    *,
    timeout: float = 30.0,
    runner: Callable[..., CompletedProcess[str]] | None = None,
) -> ProductContext:
    clean_url = product_url.strip()
    if not clean_url:
        raise LocalChromeError("쿠팡 URL을 입력해 주세요.")
    run = runner or subprocess.run
    if runner is None and shutil.which("osascript") is None:
        raise LocalChromeError("로컬 Chrome 확인은 macOS Google Chrome에서만 사용할 수 있습니다.")
    try:
        completed = run(
            ["osascript", "-e", CHROME_APPLESCRIPT, clean_url, CHROME_EXTRACT_SCRIPT],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalChromeError("Chrome에서 상품 페이지 확인 시간이 초과되었습니다.") from exc
    except OSError as exc:
        raise LocalChromeError("Chrome을 실행하거나 제어하지 못했습니다.") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        message = "Chrome에서 상품 정보를 읽지 못했습니다."
        if detail:
            message = f"{message} {detail}"
        raise LocalChromeError(message)
    return _context_from_payload(clean_url, completed.stdout)


def _context_from_payload(product_url: str, raw_payload: str) -> ProductContext:
    try:
        payload = json.loads(raw_payload.strip())
    except json.JSONDecodeError as exc:
        raise LocalChromeError("Chrome 응답을 해석하지 못했습니다.") from exc
    if not isinstance(payload, dict):
        raise LocalChromeError("Chrome 응답 형식이 올바르지 않습니다.")
    title = _best_product_title(payload)
    if not title:
        raise LocalChromeError("Chrome에서 상품명을 찾지 못했습니다.")
    resolved_url = _clean_text(payload.get("url")) or product_url
    return ProductContext(
        source_url="chrome",
        resolved_url=resolved_url,
        page_title=title,
        image_url=_normalize_url(_clean_text(payload.get("imageUrl"))),
        facts=["Chrome에서 확인한 상품명"],
    )


def _best_product_title(payload: dict[str, Any]) -> str:
    for key in ("h1", "prodTitle", "ogTitle", "twitterTitle", "title"):
        title = _clean_product_title(payload.get(key))
        if _is_useful_title(title):
            return title
    return ""


def _clean_product_title(value: Any) -> str:
    text = _clean_text(value)
    text = re.sub(r"\s+-\s+[^|]+?\|\s*쿠팡\s*$", "", text)
    text = re.sub(r"\s+\|\s*쿠팡\s*$", "", text)
    return text.strip()


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    return value


def _is_useful_title(title: str) -> bool:
    lower_title = title.lower()
    if not title or title == "쿠팡":
        return False
    return "access denied" not in lower_title and "permission" not in lower_title

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


BridgeTransport = Callable[
    [str, str],
    dict[str, Any] | list[dict[str, Any]],
]

BRIDGE_USER_AGENT = "ThreadsCopasBridge/1.0 (+https://sinabro-ai.com)"
DEFAULT_BRIDGE_TIMEOUT = 20
PUBLISH_BRIDGE_TIMEOUT = 120


class ThreadsBridgeError(RuntimeError):
    pass


class ThreadsBridgeClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        transport: Callable[..., dict[str, Any] | list[dict[str, Any]]] | None = None,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.api_key = api_key.strip()
        self._transport = transport or _urlopen_json_transport
        if not self.base_url:
            raise ThreadsBridgeError("Threads service URL is required")

    def list_profiles(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/api/threads/profiles")
        if not isinstance(response, list):
            raise ThreadsBridgeError("Threads service returned an unexpected profiles response")
        return response

    def list_publish_records(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/api/threads/publish-records")
        if not isinstance(response, list):
            raise ThreadsBridgeError("Threads service returned an unexpected records response")
        return response

    def refresh_record_insights(self, job_id: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/threads/publish-records/{quote(job_id, safe='')}/insights",
        )
        return _ensure_dict(response)

    def upsert_profile(self, profile_key: str, display_name: str, notes: str = "") -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/threads/profiles",
            data={
                "profile_key": profile_key,
                "display_name": display_name,
                "notes": notes,
            },
        )
        return _ensure_dict(response)

    def start_auth(self, profile_key: str) -> dict[str, str]:
        response = self._request(
            "GET",
            "/api/threads/auth/start",
            params={"profile_key": profile_key},
        )
        return _string_dict(response)

    def start_import(self) -> dict[str, str]:
        response = self._request("GET", "/api/threads/auth/import/start")
        return _string_dict(response)

    def upload_media(self, *, filename: str, content_type: str, image_base64: str) -> dict[str, str]:
        response = self._request(
            "POST",
            "/api/threads/media",
            data={
                "filename": filename,
                "content_type": content_type,
                "image_base64": image_base64,
            },
        )
        return _string_dict(response)

    def publish(
        self,
        *,
        profile_key: str,
        product_url: str,
        product_name: str,
        image_url: str,
        text: str,
        comment_text: str = "",
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/threads/remote-publish",
            data={
                "profile_key": profile_key,
                "product_url": product_url,
                "product_name": product_name,
                "image_url": image_url,
                "text": text,
                "comment_text": comment_text,
            },
            timeout=PUBLISH_BRIDGE_TIMEOUT,
        )
        return _ensure_dict(response)

    def refresh_profile(self, profile_key: str) -> dict[str, Any]:
        response = self._request("POST", f"/api/threads/profiles/{quote(profile_key, safe='')}/refresh")
        return _ensure_dict(response)

    def disconnect_profile(self, profile_key: str) -> dict[str, Any]:
        response = self._request("POST", f"/api/threads/profiles/{quote(profile_key, safe='')}/disconnect")
        return _ensure_dict(response)

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_BRIDGE_TIMEOUT,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {
            "Accept": "application/json",
            "User-Agent": BRIDGE_USER_AGENT,
        }
        if self.api_key:
            headers["X-Threads-Bridge-Key"] = self.api_key
        return self._transport(method, url, data=data, headers=headers, timeout=timeout)


def _urlopen_json_transport(
    method: str,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_BRIDGE_TIMEOUT,
) -> dict[str, Any] | list[dict[str, Any]]:
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method.upper())
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ThreadsBridgeError(f"Threads service HTTP {exc.code}: {_extract_error_detail(detail)}") from exc
    except (OSError, URLError) as exc:
        raise ThreadsBridgeError(f"Threads service request failed: {exc}") from exc
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ThreadsBridgeError("Threads service returned invalid JSON") from exc
    if not isinstance(parsed, (dict, list)):
        raise ThreadsBridgeError("Threads service returned an unexpected response")
    return parsed


def _extract_error_detail(detail: str) -> str:
    try:
        parsed = json.loads(detail)
    except json.JSONDecodeError:
        return detail
    if isinstance(parsed, dict):
        return str(parsed.get("detail") or parsed)
    return detail


def _ensure_dict(response: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ThreadsBridgeError("Threads service returned an unexpected response")
    return response


def _string_dict(response: dict[str, Any] | list[dict[str, Any]]) -> dict[str, str]:
    raw = _ensure_dict(response)
    return {key: str(value) for key, value in raw.items()}

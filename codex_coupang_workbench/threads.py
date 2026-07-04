from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


Transport = Callable[
    [str, str],
    dict[str, Any],
]


class ThreadsApiError(RuntimeError):
    pass


class ThreadsApiClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        redirect_uri: str,
        *,
        transport: Callable[..., dict[str, Any]] | None = None,
        auth_base_url: str = "https://graph.threads.net",
        api_base_url: str = "https://graph.threads.net/v1.0",
    ) -> None:
        self.app_id = app_id.strip()
        self.app_secret = app_secret.strip()
        self.redirect_uri = redirect_uri.strip()
        self.auth_base_url = auth_base_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/")
        self._transport = transport or _urlopen_transport

    def build_authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self.app_id,
                "redirect_uri": self.redirect_uri,
                "scope": "threads_basic,threads_content_publish",
                "response_type": "code",
                "state": state,
            }
        )
        return f"https://threads.net/oauth/authorize?{query}"

    def exchange_code_for_short_token(self, code: str) -> dict[str, Any]:
        return self._transport(
            "POST",
            f"{self.auth_base_url}/oauth/access_token",
            data={
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code": code,
            },
        )

    def exchange_for_long_lived_token(self, short_lived_token: str) -> dict[str, Any]:
        return self._transport(
            "GET",
            f"{self.auth_base_url}/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": self.app_secret,
                "access_token": short_lived_token,
            },
        )

    def refresh_long_lived_token(self, access_token: str) -> dict[str, Any]:
        return self._transport(
            "GET",
            f"{self.auth_base_url}/refresh_access_token",
            params={
                "grant_type": "th_refresh_token",
                "access_token": access_token,
            },
        )

    def fetch_me(self, access_token: str) -> dict[str, Any]:
        return self._transport(
            "GET",
            f"{self.api_base_url}/me",
            params={
                "fields": "id,username,name,threads_profile_picture_url",
                "access_token": access_token,
            },
        )

    def publish_text(self, threads_user_id: str, access_token: str, text: str) -> dict[str, Any]:
        return self._publish_text_container(
            threads_user_id=threads_user_id,
            access_token=access_token,
            text=text,
        )

    def publish_reply(
        self,
        threads_user_id: str,
        access_token: str,
        text: str,
        reply_to_id: str,
    ) -> dict[str, Any]:
        return self._publish_text_container(
            threads_user_id=threads_user_id,
            access_token=access_token,
            text=text,
            reply_to_id=reply_to_id,
        )

    def _publish_text_container(
        self,
        threads_user_id: str,
        access_token: str,
        text: str,
        reply_to_id: str = "",
    ) -> dict[str, Any]:
        data = {
            "media_type": "TEXT",
            "text": text,
            "access_token": access_token,
        }
        if reply_to_id.strip():
            data["reply_to_id"] = reply_to_id.strip()
        container = self._transport(
            "POST",
            f"{self.api_base_url}/{threads_user_id}/threads",
            data=data,
        )
        creation_id = str(container.get("id", "")).strip()
        if not creation_id:
            raise ThreadsApiError("Threads container response did not include an id")
        return self._transport(
            "POST",
            f"{self.api_base_url}/{threads_user_id}/threads_publish",
            data={
                "creation_id": creation_id,
                "access_token": access_token,
            },
        )


def _urlopen_transport(
    method: str,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    clean_url = url
    if params:
        clean_url = f"{clean_url}?{urlencode(params)}"
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        body = urlencode(data).encode("utf-8")
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(clean_url, data=body, headers=request_headers, method=method.upper())
    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ThreadsApiError(f"Threads API HTTP {exc.code}: {detail}") from exc
    except (OSError, URLError) as exc:
        raise ThreadsApiError(f"Threads API request failed: {exc}") from exc
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ThreadsApiError("Threads API returned invalid JSON") from exc
    if isinstance(parsed, dict) and parsed.get("error"):
        raise ThreadsApiError(str(parsed["error"]))
    if not isinstance(parsed, dict):
        raise ThreadsApiError("Threads API returned an unexpected response")
    return parsed

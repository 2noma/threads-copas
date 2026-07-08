import pytest
from httpx import ASGITransport, AsyncClient

from codex_coupang_workbench.threads_api import create_threads_api_app


class FakeThreadsClient:
    published = []
    replies = []

    def __init__(self, app_id, app_secret, redirect_uri):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri

    def build_authorization_url(self, state):
        return f"https://threads.net/oauth/authorize?client_id={self.app_id}&state={state}"

    def exchange_code_for_short_token(self, code):
        assert code == "oauth-code"
        return {"access_token": "short-token", "user_id": "12345"}

    def exchange_for_long_lived_token(self, short_lived_token):
        assert short_lived_token == "short-token"
        return {"access_token": "long-token", "expires_in": 5_184_000}

    def fetch_me(self, access_token):
        assert access_token == "long-token"
        return {"id": "12345", "username": "tesla_daily", "name": "Tesla Daily"}

    def refresh_long_lived_token(self, access_token):
        assert access_token == "long-token"
        return {"access_token": "refreshed-token", "expires_in": 5_184_000}

    def publish_image(self, threads_user_id, access_token, text, image_url):
        self.published.append(
            {
                "threads_user_id": threads_user_id,
                "access_token": access_token,
                "media_type": "IMAGE",
                "text": text,
                "image_url": image_url,
            }
        )
        return {"id": "post_123"}

    def publish_reply(self, threads_user_id, access_token, text, reply_to_id):
        self.replies.append(
            {
                "threads_user_id": threads_user_id,
                "access_token": access_token,
                "text": text,
                "reply_to_id": reply_to_id,
            }
        )
        return {"id": "reply_123"}


@pytest.mark.anyio
async def test_threads_api_server_exposes_only_bridge_api(tmp_path, monkeypatch):
    monkeypatch.setenv("THREADS_BRIDGE_API_KEY", "bridge-key")
    monkeypatch.setenv("THREADS_APP_ID", "env-app-id")
    monkeypatch.setenv("THREADS_APP_SECRET", "env-secret")
    monkeypatch.setenv("THREADS_REDIRECT_URI", "https://sinabro-ai.com/threads-copas/api/threads/auth/callback")

    app = create_threads_api_app(tmp_path / "threads-api.sqlite3")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/")).status_code == 404
        assert (await client.get("/api/settings")).status_code == 404
        assert (await client.post("/api/coupang/product-preview", json={"product_url": "x"})).status_code == 404
        assert (await client.post("/api/threads/draft", json={"product_url": "x"})).status_code == 404

        blocked = await client.get("/api/threads/profiles")
        allowed = await client.get("/api/threads/profiles", headers={"X-Threads-Bridge-Key": "bridge-key"})

        assert blocked.status_code == 401
        assert allowed.status_code == 200
        assert allowed.json() == []


@pytest.mark.anyio
async def test_threads_api_server_uses_env_settings_for_auth_and_publish(tmp_path, monkeypatch):
    FakeThreadsClient.published = []
    FakeThreadsClient.replies = []
    monkeypatch.setenv("THREADS_BRIDGE_API_KEY", "bridge-key")
    monkeypatch.setenv("THREADS_APP_ID", "env-app-id")
    monkeypatch.setenv("THREADS_APP_SECRET", "env-secret")
    monkeypatch.setenv("THREADS_REDIRECT_URI", "https://sinabro-ai.com/threads-copas/api/threads/auth/callback")
    monkeypatch.setattr("codex_coupang_workbench.threads_api.ThreadsApiClient", FakeThreadsClient)

    app = create_threads_api_app(tmp_path / "threads-api.sqlite3")
    transport = ASGITransport(app=app)
    headers = {"X-Threads-Bridge-Key": "bridge-key"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        profile = await client.post(
            "/api/threads/profiles",
            json={"profile_key": "tesla", "display_name": "테슬라 용품"},
            headers=headers,
        )
        auth_start = await client.get("/api/threads/auth/start", params={"profile_key": "tesla"}, headers=headers)
        callback = await client.get(
            "/api/threads/auth/callback",
            params={"code": "oauth-code", "state": "tesla"},
        )
        published = await client.post(
            "/api/threads/remote-publish",
            json={
                "profile_key": "tesla",
                "product_url": "https://link.coupang.com/a/tesla",
                "product_name": "테슬라 수납함",
                "image_url": "https://image.example/tesla.jpg",
                "text": "본문",
                "comment_text": "댓글",
            },
            headers=headers,
        )
        records = await client.get("/api/threads/publish-records", headers=headers)

        assert profile.status_code == 200
        assert auth_start.status_code == 200
        assert "client_id=env-app-id" in auth_start.json()["auth_url"]
        assert callback.status_code == 200
        assert published.status_code == 200
        assert published.json()["threads_post_id"] == "post_123"
        assert published.json()["threads_reply_id"] == "reply_123"
        assert FakeThreadsClient.published[0]["image_url"] == "https://image.example/tesla.jpg"
        assert records.json()[0]["product_name"] == "테슬라 수납함"


@pytest.mark.anyio
async def test_threads_api_server_disconnects_connected_profile(tmp_path, monkeypatch):
    FakeThreadsClient.published = []
    FakeThreadsClient.replies = []
    monkeypatch.setenv("THREADS_BRIDGE_API_KEY", "bridge-key")
    monkeypatch.setenv("THREADS_APP_ID", "env-app-id")
    monkeypatch.setenv("THREADS_APP_SECRET", "env-secret")
    monkeypatch.setenv("THREADS_REDIRECT_URI", "https://sinabro-ai.com/threads-copas/api/threads/auth/callback")
    monkeypatch.setattr("codex_coupang_workbench.threads_api.ThreadsApiClient", FakeThreadsClient)

    app = create_threads_api_app(tmp_path / "threads-api.sqlite3")
    transport = ASGITransport(app=app)
    headers = {"X-Threads-Bridge-Key": "bridge-key"}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/threads/profiles",
            json={"profile_key": "tesla", "display_name": "테슬라 용품"},
            headers=headers,
        )
        await client.get(
            "/api/threads/auth/callback",
            params={"code": "oauth-code", "state": "tesla"},
        )

        connected_profiles = await client.get("/api/threads/profiles", headers=headers)
        disconnected = await client.post("/api/threads/profiles/tesla/disconnect", headers=headers)
        disconnected_profiles = await client.get("/api/threads/profiles", headers=headers)
        published = await client.post(
            "/api/threads/remote-publish",
            json={
                "profile_key": "tesla",
                "product_url": "https://link.coupang.com/a/tesla",
                "product_name": "테슬라 수납함",
                "image_url": "https://image.example/tesla.jpg",
                "text": "본문",
                "comment_text": "댓글",
            },
            headers=headers,
        )

        assert connected_profiles.json()[0]["is_connected"] is True
        assert disconnected.status_code == 200
        assert disconnected.json()["is_connected"] is False
        assert disconnected.json()["token_preview"] == ""
        assert disconnected_profiles.json()[0]["is_connected"] is False
        assert published.status_code == 400
        assert published.json()["detail"] == "Threads profile is not connected"
        assert FakeThreadsClient.published == []

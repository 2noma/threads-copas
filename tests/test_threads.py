from codex_coupang_workbench.threads import ThreadsApiClient


class FakeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, *, data=None, params=None, headers=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "data": data or {},
                "params": params or {},
                "headers": headers or {},
            }
        )
        if url.endswith("/oauth/access_token"):
            return {"access_token": "short-token", "user_id": "12345"}
        if url.endswith("/access_token"):
            return {"access_token": "long-token", "token_type": "bearer", "expires_in": 5_184_000}
        if url.endswith("/refresh_access_token"):
            return {"access_token": "refreshed-token", "token_type": "bearer", "expires_in": 5_184_000}
        if url.endswith("/me"):
            return {"id": "12345", "username": "tesla_daily", "name": "Tesla Daily"}
        if url.endswith("/12345/threads"):
            return {"id": "container_123"}
        if url.endswith("/12345/threads_publish"):
            return {"id": "post_123"}
        raise AssertionError(f"Unexpected URL: {url}")


def test_build_authorization_url_includes_profile_state_and_scopes():
    client = ThreadsApiClient(app_id="app-id", app_secret="secret", redirect_uri="https://example.com/callback")

    auth_url = client.build_authorization_url("tesla")

    assert auth_url.startswith("https://threads.net/oauth/authorize?")
    assert "client_id=app-id" in auth_url
    assert "scope=threads_basic%2Cthreads_content_publish" in auth_url
    assert "state=tesla" in auth_url


def test_exchange_refresh_profile_and_publish_text_request_shapes():
    transport = FakeTransport()
    client = ThreadsApiClient(
        app_id="app-id",
        app_secret="secret",
        redirect_uri="https://example.com/callback",
        transport=transport,
    )

    short = client.exchange_code_for_short_token("returned-code")
    long_token = client.exchange_for_long_lived_token(short["access_token"])
    refreshed = client.refresh_long_lived_token(long_token["access_token"])
    profile = client.fetch_me(long_token["access_token"])
    published = client.publish_text(
        threads_user_id="12345",
        access_token=long_token["access_token"],
        text="테스트 글",
    )

    assert short["access_token"] == "short-token"
    assert long_token["access_token"] == "long-token"
    assert refreshed["access_token"] == "refreshed-token"
    assert profile["username"] == "tesla_daily"
    assert published["id"] == "post_123"
    assert transport.calls[-2]["data"]["media_type"] == "TEXT"
    assert transport.calls[-2]["data"]["text"] == "테스트 글"
    assert transport.calls[-1]["data"]["creation_id"] == "container_123"

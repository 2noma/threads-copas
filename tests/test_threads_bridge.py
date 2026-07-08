from codex_coupang_workbench.threads_bridge import BRIDGE_USER_AGENT, ThreadsBridgeClient


class FakeBridgeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, *, data=None, headers=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "data": data or {},
                "headers": headers or {},
            }
        )
        if url.endswith("/api/threads/profiles"):
            return [{"profile_key": "tesla", "display_name": "Tesla", "is_connected": True}]
        if url.endswith("/api/threads/auth/import/start"):
            return {"auth_url": "https://threads.net/oauth/authorize?state=import"}
        if url.endswith("/api/threads/remote-publish"):
            return {"threads_post_id": "post_123", "threads_reply_id": "reply_123", "job": {"id": "remote-job"}}
        if url.endswith("/api/threads/profiles/tesla%2Fdaily/refresh"):
            return {"profile_key": "tesla/daily", "is_connected": True}
        if url.endswith("/api/threads/profiles/tesla%2Fdaily/disconnect"):
            return {"profile_key": "tesla/daily", "is_connected": False}
        raise AssertionError(f"Unexpected URL: {url}")


def test_threads_bridge_client_sends_api_key_and_json_payload():
    transport = FakeBridgeTransport()
    client = ThreadsBridgeClient(
        "https://sinabro-ai.com/threads-copas/",
        api_key="bridge-key",
        transport=transport,
    )

    profiles = client.list_profiles()
    published = client.publish(
        profile_key="tesla",
        product_url="https://link.coupang.com/a/example",
        product_name="테슬라 수납함",
        image_url="https://image.example/tesla.jpg",
        text="본문",
        comment_text="댓글",
    )
    refreshed = client.refresh_profile("tesla/daily")
    disconnected = client.disconnect_profile("tesla/daily")

    assert profiles[0]["profile_key"] == "tesla"
    assert published["threads_post_id"] == "post_123"
    assert refreshed["profile_key"] == "tesla/daily"
    assert disconnected["is_connected"] is False
    assert transport.calls[0]["headers"]["X-Threads-Bridge-Key"] == "bridge-key"
    assert transport.calls[0]["headers"]["User-Agent"] == BRIDGE_USER_AGENT
    assert transport.calls[1]["url"] == "https://sinabro-ai.com/threads-copas/api/threads/remote-publish"
    assert transport.calls[1]["data"]["product_name"] == "테슬라 수납함"
    assert transport.calls[3]["url"] == "https://sinabro-ai.com/threads-copas/api/threads/profiles/tesla%2Fdaily/disconnect"

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from secrets import compare_digest
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from .schemas import ThreadsMediaUploadPayload, ThreadsProfilePayload, ThreadsRemotePublishPayload
from .storage import WorkbenchStore
from .threads import ThreadsApiClient, ThreadsApiError

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PACKAGE_DIR.parent / "workbench_data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "threads_api.sqlite3"
THREADS_IMPORT_STATE_PREFIX = "import-current-profile:"
THREADS_BRIDGE_API_KEY_ENV = "THREADS_BRIDGE_API_KEY"
THREADS_APP_ID_ENV = "THREADS_APP_ID"
THREADS_APP_SECRET_ENV = "THREADS_APP_SECRET"
THREADS_REDIRECT_URI_ENV = "THREADS_REDIRECT_URI"
THREADS_PUBLIC_BASE_URL_ENV = "THREADS_PUBLIC_BASE_URL"
ALLOWED_MEDIA_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_MEDIA_BYTES = 8 * 1024 * 1024


def create_threads_api_app(db_path: str | Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="Threads Coupang API")
    store = WorkbenchStore(db_path)
    media_dir = Path(db_path).parent / "public_media"

    def get_store() -> WorkbenchStore:
        return store

    def require_bridge_access(request: Request) -> None:
        expected_api_key = os.environ.get(THREADS_BRIDGE_API_KEY_ENV, "").strip()
        if not expected_api_key:
            raise HTTPException(status_code=500, detail="THREADS_BRIDGE_API_KEY is required")
        provided_api_key = request.headers.get("X-Threads-Bridge-Key", "").strip()
        if not provided_api_key or not compare_digest(provided_api_key, expected_api_key):
            raise HTTPException(status_code=401, detail="Threads bridge API key is required")

    def get_threads_client() -> ThreadsApiClient:
        app_id = os.environ.get(THREADS_APP_ID_ENV, "").strip()
        app_secret = os.environ.get(THREADS_APP_SECRET_ENV, "").strip()
        redirect_uri = os.environ.get(THREADS_REDIRECT_URI_ENV, "").strip()
        if not app_id or not app_secret or not redirect_uri:
            raise HTTPException(status_code=500, detail="Threads API env settings are required")
        return ThreadsApiClient(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
        )

    def public_base_url(request: Request) -> str:
        configured = os.environ.get(THREADS_PUBLIC_BASE_URL_ENV, "").strip().rstrip("/")
        if configured:
            return configured
        return str(request.base_url).rstrip("/")

    def decode_image_payload(payload: ThreadsMediaUploadPayload) -> tuple[bytes, str]:
        content_type = payload.content_type.strip().lower()
        if content_type not in ALLOWED_MEDIA_TYPES:
            allowed = ", ".join(sorted(ALLOWED_MEDIA_TYPES))
            raise HTTPException(status_code=400, detail=f"content_type must be one of: {allowed}")
        raw_base64 = payload.image_base64.strip()
        if raw_base64.startswith("data:") and "," in raw_base64:
            header, raw_base64 = raw_base64.split(",", 1)
            data_content_type = header.removeprefix("data:").split(";", 1)[0].strip().lower()
            if data_content_type:
                content_type = data_content_type
            if content_type not in ALLOWED_MEDIA_TYPES:
                allowed = ", ".join(sorted(ALLOWED_MEDIA_TYPES))
                raise HTTPException(status_code=400, detail=f"content_type must be one of: {allowed}")
        compact_base64 = "".join(raw_base64.split())
        try:
            image_bytes = base64.b64decode(compact_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="image_base64 must be valid base64") from exc
        if not image_bytes:
            raise HTTPException(status_code=400, detail="image_base64 is empty")
        if len(image_bytes) > MAX_MEDIA_BYTES:
            raise HTTPException(status_code=400, detail="image is too large")
        if content_type == "image/png" and not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=400, detail="image_base64 is not a valid PNG image")
        if content_type == "image/jpeg" and not image_bytes.startswith(b"\xff\xd8\xff"):
            raise HTTPException(status_code=400, detail="image_base64 is not a valid JPEG image")
        if content_type == "image/webp" and not (image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP"):
            raise HTTPException(status_code=400, detail="image_base64 is not a valid WEBP image")
        return image_bytes, content_type

    def publish_threads_job(
        *,
        job: dict[str, Any],
        profile_key: str,
        text: str,
        comment_text: str,
        store: WorkbenchStore,
    ) -> dict[str, Any]:
        profile = store.get_threads_profile(profile_key, include_token=True)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        if not profile.get("is_connected"):
            raise HTTPException(status_code=400, detail="Threads profile is not connected")
        client = get_threads_client()
        image_url = str(job.get("image_url") or "").strip()
        try:
            if image_url:
                published = client.publish_image(
                    threads_user_id=profile["threads_user_id"],
                    access_token=profile["access_token"],
                    text=text,
                    image_url=image_url,
                )
            else:
                published = client.publish_text(
                    threads_user_id=profile["threads_user_id"],
                    access_token=profile["access_token"],
                    text=text,
                )
        except ThreadsApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        post_id = str(published.get("id", "")).strip()
        if not post_id:
            raise HTTPException(status_code=400, detail="Threads publish response did not include an id")
        clean_comment = comment_text.strip()
        reply_id = ""
        if clean_comment:
            try:
                reply = client.publish_reply(
                    threads_user_id=profile["threads_user_id"],
                    access_token=profile["access_token"],
                    text=clean_comment,
                    reply_to_id=post_id,
                )
            except ThreadsApiError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            reply_id = str(reply.get("id", "")).strip()
        updated_job = store.mark_threads_published(
            job_id=job["id"],
            profile_key=profile_key,
            threads_post_id=post_id,
            threads_reply_id=reply_id,
            published_text=f"본문:\n{text.strip()}\n\n댓글:\n{clean_comment}" if clean_comment else text,
        )
        return {
            "status": "THREADS_PUBLISHED",
            "threads_post_id": post_id,
            "threads_reply_id": reply_id,
            "job": updated_job,
        }

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "threads-api"}

    @app.get("/media/{filename}")
    def get_media(filename: str) -> FileResponse:
        if "/" in filename or "\\" in filename:
            raise HTTPException(status_code=404, detail="Media not found")
        path = media_dir / filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Media not found")
        suffix = path.suffix.lower()
        media_type = next((item for item, ext in ALLOWED_MEDIA_TYPES.items() if ext == suffix), "application/octet-stream")
        return FileResponse(path, media_type=media_type)

    @app.post("/api/threads/media")
    def upload_media(
        payload: ThreadsMediaUploadPayload,
        request: Request,
    ) -> dict[str, str]:
        require_bridge_access(request)
        image_bytes, content_type = decode_image_payload(payload)
        media_dir.mkdir(parents=True, exist_ok=True)
        extension = ALLOWED_MEDIA_TYPES[content_type]
        filename = f"{uuid4().hex}{extension}"
        path = media_dir / filename
        path.write_bytes(image_bytes)
        return {
            "image_url": f"{public_base_url(request)}/media/{filename}",
            "filename": filename,
            "content_type": content_type,
        }

    @app.get("/api/threads/profiles")
    def list_threads_profiles(
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> list[dict[str, Any]]:
        require_bridge_access(request)
        return store.list_threads_profiles()

    @app.get("/api/threads/publish-records")
    def list_threads_publish_records(
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> list[dict[str, Any]]:
        require_bridge_access(request)
        return store.list_threads_publish_records()

    @app.post("/api/threads/profiles")
    def upsert_threads_profile(
        payload: ThreadsProfilePayload,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        require_bridge_access(request)
        try:
            return store.upsert_threads_profile(
                profile_key=payload.profile_key,
                display_name=payload.display_name,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.get("/api/threads/auth/start")
    def start_threads_auth(
        profile_key: str,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, str]:
        require_bridge_access(request)
        clean_profile_key = profile_key.strip()
        profile = store.get_threads_profile(clean_profile_key)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        return {"auth_url": get_threads_client().build_authorization_url(clean_profile_key)}

    @app.get("/api/threads/auth/import/start")
    def start_threads_profile_import(request: Request) -> dict[str, str]:
        require_bridge_access(request)
        state = f"{THREADS_IMPORT_STATE_PREFIX}{uuid4().hex}"
        return {"auth_url": get_threads_client().build_authorization_url(state)}

    @app.get("/api/threads/auth/callback", response_class=HTMLResponse)
    def threads_auth_callback(
        code: str,
        state: str,
        store: WorkbenchStore = Depends(get_store),
    ) -> str:
        callback_state = state.strip()
        is_import = callback_state.startswith(THREADS_IMPORT_STATE_PREFIX)
        if not callback_state:
            raise HTTPException(status_code=400, detail="Missing profile state")
        if not is_import and store.get_threads_profile(callback_state) is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        client = get_threads_client()
        try:
            short_token = client.exchange_code_for_short_token(code)
            long_token = client.exchange_for_long_lived_token(short_token["access_token"])
            profile = client.fetch_me(long_token["access_token"])
        except (KeyError, ThreadsApiError) as exc:
            raise HTTPException(status_code=400, detail=f"Threads auth failed: {exc}") from None
        username = str(profile.get("username") or profile.get("name") or "")
        threads_user_id = str(profile.get("id") or short_token.get("user_id") or "")
        profile_key = callback_state
        if is_import:
            profile_key = username.strip() or threads_user_id.strip()
            display_name = str(profile.get("name") or username or profile_key)
            store.upsert_threads_profile(
                profile_key=profile_key,
                display_name=display_name,
            )
        store.save_threads_profile_token(
            profile_key=profile_key,
            threads_user_id=threads_user_id,
            username=username,
            access_token=str(long_token["access_token"]),
            expires_in=int(long_token.get("expires_in") or 0),
        )
        return """
        <!doctype html>
        <html lang="ko">
          <head><meta charset="utf-8"><title>Threads 연결 완료</title></head>
          <body>
            <h1>Threads 연결 완료</h1>
            <p>이 창을 닫고 로컬 화면으로 돌아가도 됩니다.</p>
          </body>
        </html>
        """

    @app.post("/api/threads/remote-publish")
    def publish_remote_threads_post(
        payload: ThreadsRemotePublishPayload,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        require_bridge_access(request)
        job = store.add_job(
            product_url=payload.product_url,
            product_name=payload.product_name,
            image_url=payload.image_url,
        )
        job = store.update_job_threads_draft(
            job["id"],
            text=payload.text,
            comment_text=payload.comment_text,
            title=f"{payload.product_name} Threads",
            tags=["쿠팡파트너스", "Threads"],
            image_url=payload.image_url or None,
        )
        return publish_threads_job(
            job=job,
            profile_key=payload.profile_key,
            text=payload.text,
            comment_text=payload.comment_text,
            store=store,
        )

    @app.post("/api/threads/profiles/{profile_key}/refresh")
    def refresh_threads_profile_token(
        profile_key: str,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        require_bridge_access(request)
        profile = store.get_threads_profile(profile_key, include_token=True)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        if not profile.get("is_connected"):
            raise HTTPException(status_code=400, detail="Threads profile is not connected")
        try:
            refreshed = get_threads_client().refresh_long_lived_token(profile["access_token"])
        except ThreadsApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        return store.save_threads_profile_token(
            profile_key=profile_key,
            threads_user_id=profile["threads_user_id"],
            username=profile.get("username", ""),
            access_token=str(refreshed["access_token"]),
            expires_in=int(refreshed.get("expires_in") or 0),
        )

    @app.post("/api/threads/profiles/{profile_key}/disconnect")
    def disconnect_threads_profile(
        profile_key: str,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        require_bridge_access(request)
        disconnected = store.disconnect_threads_profile(profile_key)
        if disconnected is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        return disconnected

    return app


app = create_threads_api_app()

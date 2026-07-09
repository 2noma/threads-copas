from __future__ import annotations

import os
from pathlib import Path
from secrets import compare_digest
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .codex_image import CodexImageError, generate_codex_hook_image
from .coupang_partners import (
    CoupangPartnerProduct,
    CoupangPartnersClient,
    CoupangPartnersError,
    extract_coupang_ids,
    fetch_partner_product_context,
    resolve_coupang_redirect,
)
from .codex_threads import CodexThreadsError, DEFAULT_CODEX_MODEL, generate_codex_threads_post
from .local_chrome import LocalChromeError, fetch_chrome_product_context
from .naver import publish_handoff_message
from .product_research import fetch_best_product_context
from .schemas import (
    CoupangDeeplinkPayload,
    CoupangProductPreviewPayload,
    GeneratedImagePayload,
    JobCreatePayload,
    MediaCandidatePayload,
    PublishHandoff,
    SettingsPayload,
    ThreadsAutoHookImagePayload,
    ThreadsDraftPayload,
    ThreadsMediaUploadPayload,
    ThreadsProfilePayload,
    ThreadsPublishPayload,
    ThreadsRemotePublishPayload,
)
from .storage import WorkbenchStore
from .threads import ThreadsApiClient, ThreadsApiError
from .threads_bridge import ThreadsBridgeClient, ThreadsBridgeError
from .writer import generate_campaign, generate_draft, generate_threads_comment, generate_threads_post

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = PACKAGE_DIR.parent / "workbench_data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "workbench.sqlite3"
STATIC_DIR = PACKAGE_DIR / "static"
ICON_PATH = PACKAGE_DIR.parent / "assets" / "appicon.ico"
THREADS_IMPORT_STATE_PREFIX = "import-current-profile:"
SECRET_SETTING_KEYS = {
    "coupang_access_key",
    "coupang_secret_key",
    "threads_app_secret",
    "threads_service_api_key",
}
REMOVED_SETTING_KEYS = {"coupang_proxy_url"}
SECRET_MASK = "********"
THREADS_BRIDGE_API_KEY_ENV = "THREADS_BRIDGE_API_KEY"


def public_settings(settings: dict[str, str]) -> dict[str, str]:
    visible = {key: value for key, value in settings.items() if key not in REMOVED_SETTING_KEYS}
    for key in SECRET_SETTING_KEYS:
        if key in visible and visible[key]:
            visible[key] = SECRET_MASK
    return visible


def settings_to_store(payload: SettingsPayload, current_settings: dict[str, str]) -> dict[str, str]:
    settings = payload.model_dump()
    for key in settings:
        if key not in payload.model_fields_set and current_settings.get(key):
            settings[key] = current_settings[key]
    for key in SECRET_SETTING_KEYS:
        if settings.get(key) == SECRET_MASK and current_settings.get(key):
            settings[key] = current_settings[key]
        if not settings.get(key) and current_settings.get(key):
            settings[key] = current_settings[key]
    return settings


def threads_service_url(settings: dict[str, str]) -> str:
    return settings.get("threads_service_url", "").strip().rstrip("/")


def uses_remote_threads_service(settings: dict[str, str]) -> bool:
    return bool(threads_service_url(settings))


def fetch_coupang_partner_product(
    product_url: str,
    settings: dict[str, str],
    product_keyword: str = "",
    sub_id: str = "",
) -> tuple[CoupangPartnerProduct, str]:
    access_key = settings.get("coupang_access_key", "").strip()
    secret_key = settings.get("coupang_secret_key", "").strip()
    if not access_key or not secret_key:
        raise CoupangPartnersError("쿠팡 파트너스 API 키를 저장한 뒤 다시 시도해 주세요.")
    selected_sub_id = sub_id.strip() or settings.get("coupang_sub_id", "")
    partner_product, resolved_url = fetch_partner_product_context(
        product_url,
        access_key=access_key,
        secret_key=secret_key,
        sub_id=selected_sub_id,
        product_keyword=product_keyword,
    )
    return partner_product, resolved_url


def create_coupang_deeplink(product_url: str, settings: dict[str, str], sub_id: str = "") -> dict[str, str]:
    access_key = settings.get("coupang_access_key", "").strip()
    secret_key = settings.get("coupang_secret_key", "").strip()
    if not access_key or not secret_key:
        raise CoupangPartnersError("쿠팡 파트너스 API 키를 저장한 뒤 다시 시도해 주세요.")
    clean_url = product_url.strip()
    if not clean_url:
        raise CoupangPartnersError("쿠팡 URL을 입력해 주세요.")
    selected_sub_id = sub_id.strip() or settings.get("coupang_sub_id", "")
    client = CoupangPartnersClient(
        access_key,
        secret_key,
        sub_id=selected_sub_id,
    )
    resolved_url = resolve_coupang_redirect(clean_url) or clean_url
    partner_url = client.create_deeplink(resolved_url)
    if not partner_url and resolved_url != clean_url:
        partner_url = client.create_deeplink(clean_url)
    if not partner_url:
        raise CoupangPartnersError("쿠팡 파트너스 API에서 딥링크를 만들지 못했습니다.")
    return {
        "partner_url": partner_url,
        "product_url": resolved_url,
        "resolved_url": resolved_url,
        "original_url": clean_url,
        "sub_id": selected_sub_id.strip(),
    }


def resolve_coupang_partner_product(
    product_url: str,
    settings: dict[str, str],
) -> tuple[CoupangPartnerProduct, str]:
    partner_product, resolved_url = fetch_coupang_partner_product(product_url, settings)
    if not partner_product.product_name:
        raise CoupangPartnersError("쿠팡 파트너스 API에서 상품 정보를 찾지 못했습니다.")
    return partner_product, resolved_url


def product_preview_response(
    product: CoupangPartnerProduct,
    *,
    original_url: str,
    resolved_url: str,
    fallback_product_name: str = "",
) -> dict[str, Any]:
    product_ids = extract_coupang_ids(resolved_url) + extract_coupang_ids(original_url)
    product_id = product.product_id or (product_ids[0] if product_ids else "")
    product_name = product.product_name or fallback_product_name.strip()
    return {
        "product_name": product_name,
        "product_id": product_id,
        "item_id": product_ids[1] if len(product_ids) > 1 else "",
        "image_url": product.image_url,
        "partner_url": product.partner_url,
        "product_url": product.product_url,
        "resolved_url": resolved_url,
        "original_url": original_url,
        "facts": list(product.facts),
        "needs_product_name": not bool(product_name),
    }


def enrich_partner_product_with_local_context(
    product: CoupangPartnerProduct,
    *,
    original_url: str,
    resolved_url: str,
    product_name: str = "",
) -> CoupangPartnerProduct:
    if product.product_name and product.image_url and product.facts:
        return product
    context = fetch_best_product_context(resolved_url or original_url, product_name or product.product_name)
    return CoupangPartnerProduct(
        product_name=product.product_name or product_name.strip() or context.page_title,
        product_url=product.product_url or resolved_url or context.resolved_url,
        partner_url=product.partner_url,
        image_url=product.image_url or context.image_url,
        facts=product.facts or tuple(context.facts or ()),
        product_id=product.product_id,
    )


def approved_threads_hook_image_url(job: dict[str, Any], store: WorkbenchStore) -> str:
    job_image_url = str(job.get("image_url") or "").strip()
    if not job_image_url:
        return ""
    for candidate in store.list_media_candidates(job["id"]):
        if (
            candidate.get("review_status") == "APPROVED"
            and str(candidate.get("image_url") or "").strip() == job_image_url
            and not candidate.get("product_visible")
            and candidate.get("permission_reviewed")
        ):
            return job_image_url
    return ""


def create_app(db_path: str | Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="Codex Coupang Workbench")
    store = WorkbenchStore(db_path)

    def get_store() -> WorkbenchStore:
        return store

    def get_threads_client(settings: dict[str, str]) -> ThreadsApiClient:
        app_id = settings.get("threads_app_id", "").strip()
        app_secret = settings.get("threads_app_secret", "").strip()
        redirect_uri = settings.get("threads_redirect_uri", "").strip()
        if not app_id or not app_secret or not redirect_uri:
            raise HTTPException(status_code=400, detail="Threads app settings are required")
        return ThreadsApiClient(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=redirect_uri,
        )

    def get_threads_bridge_client(settings: dict[str, str]) -> ThreadsBridgeClient:
        try:
            return ThreadsBridgeClient(
                threads_service_url(settings),
                api_key=settings.get("threads_service_api_key", ""),
            )
        except ThreadsBridgeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    def refresh_threads_record_insights(
        job_id: str,
        settings: dict[str, str],
        store: WorkbenchStore,
    ) -> dict[str, Any]:
        job = store.get_job(job_id)
        if job is None or job.get("status") != "THREADS_PUBLISHED":
            raise HTTPException(status_code=404, detail="Threads publish record not found")
        post_id = str(job.get("threads_post_id") or "").strip()
        profile_key = str(job.get("threads_profile_key") or "").strip()
        if not post_id or not profile_key:
            raise HTTPException(status_code=400, detail="Threads publish record is missing post or profile data")
        profile = store.get_threads_profile(profile_key, include_token=True)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        if not profile.get("is_connected"):
            raise HTTPException(status_code=400, detail="Threads profile is not connected")
        try:
            insights = get_threads_client(settings).fetch_media_insights(post_id, profile["access_token"])
        except ThreadsApiError as exc:
            store.update_threads_insights(job_id, {}, error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from None
        store.update_threads_insights(job_id, insights)
        record = store.get_threads_publish_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Threads publish record not found")
        return record

    def fetch_threads_permalink(
        client: ThreadsApiClient,
        post_id: str,
        access_token: str,
        job_id: str,
        store: WorkbenchStore,
    ) -> str:
        try:
            return client.fetch_media_permalink(post_id, access_token)
        except ThreadsApiError as exc:
            store.add_log(job_id, "ERROR", f"Threads permalink refresh failed: {exc}")
            return ""

    def refresh_threads_record_permalink(
        job_id: str,
        settings: dict[str, str],
        store: WorkbenchStore,
    ) -> dict[str, Any]:
        record = store.get_threads_publish_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Threads publish record not found")
        if record.get("threads_permalink"):
            return record
        post_id = str(record.get("threads_post_id") or "").strip()
        profile_key = str(record.get("profile_key") or "").strip()
        if not post_id or not profile_key:
            raise HTTPException(status_code=400, detail="Threads publish record is missing post or profile data")
        profile = store.get_threads_profile(profile_key, include_token=True)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        if not profile.get("is_connected"):
            raise HTTPException(status_code=400, detail="Threads profile is not connected")
        permalink = fetch_threads_permalink(
            get_threads_client(settings),
            post_id,
            profile["access_token"],
            job_id,
            store,
        )
        if not permalink:
            raise HTTPException(status_code=400, detail="Threads permalink was not returned")
        store.update_threads_permalink(job_id, permalink)
        refreshed = store.get_threads_publish_record(job_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Threads publish record not found")
        return refreshed

    def delete_threads_record(job_id: str, store: WorkbenchStore) -> dict[str, Any]:
        if not store.delete_threads_publish_record(job_id):
            raise HTTPException(status_code=404, detail="Threads publish record not found")
        return {"deleted": True, "job_id": job_id}

    def require_threads_bridge_access(settings: dict[str, str], request: Request) -> None:
        expected_api_key = os.environ.get(THREADS_BRIDGE_API_KEY_ENV, "").strip()
        if not expected_api_key:
            return
        provided_api_key = request.headers.get("X-Threads-Bridge-Key", "").strip()
        if not provided_api_key or not compare_digest(provided_api_key, expected_api_key):
            raise HTTPException(status_code=401, detail="Threads bridge API key is required")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    generated_dir = Path(db_path).parent / "generated"
    if generated_dir.exists():
        app.mount("/generated", StaticFiles(directory=generated_dir), name="generated")

    @app.get("/")
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend has not been built")
        return FileResponse(index_path)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        if not ICON_PATH.exists():
            raise HTTPException(status_code=404, detail="Icon not found")
        return FileResponse(ICON_PATH)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/settings")
    def get_settings(store: WorkbenchStore = Depends(get_store)) -> dict[str, str]:
        return public_settings(store.get_settings())

    @app.put("/api/settings")
    def set_settings(
        payload: SettingsPayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, str]:
        settings = settings_to_store(payload, store.get_settings())
        return public_settings(store.set_settings(settings))

    @app.get("/api/jobs")
    def list_jobs(store: WorkbenchStore = Depends(get_store)) -> list[dict[str, Any]]:
        return store.list_jobs()

    @app.post("/api/coupang/product-preview")
    def preview_coupang_product(
        payload: CoupangProductPreviewPayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        product_url = payload.product_url.strip()
        product_name = payload.product_name.strip()
        try:
            product, resolved_url = fetch_coupang_partner_product(
                product_url,
                store.get_settings(),
                product_keyword=product_name,
                sub_id=payload.sub_id,
            )
        except CoupangPartnersError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        if not product.product_name and not product.partner_url:
            raise HTTPException(status_code=400, detail="쿠팡 파트너스 API에서 상품 정보를 찾지 못했습니다.") from None
        if product.partner_url and not product.product_name:
            product = enrich_partner_product_with_local_context(
                product,
                original_url=product_url,
                resolved_url=resolved_url or product_url,
                product_name=product_name,
            )
        return product_preview_response(
            product,
            original_url=product_url,
            resolved_url=resolved_url or product_url,
            fallback_product_name=product_name if product.partner_url else "",
        )

    @app.post("/api/coupang/chrome-product-context")
    def chrome_coupang_product_context(payload: CoupangProductPreviewPayload) -> dict[str, Any]:
        product_url = payload.product_url.strip()
        try:
            context = fetch_chrome_product_context(product_url)
        except LocalChromeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        product = CoupangPartnerProduct(
            product_name=context.page_title,
            product_url=context.resolved_url or product_url,
            image_url=context.image_url,
            facts=tuple(context.facts or ()),
        )
        return product_preview_response(
            product,
            original_url=product_url,
            resolved_url=context.resolved_url or product_url,
        )

    @app.post("/api/coupang/deeplink")
    def create_coupang_deeplink_endpoint(
        payload: CoupangDeeplinkPayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, str]:
        try:
            return create_coupang_deeplink(payload.product_url, store.get_settings(), sub_id=payload.sub_id)
        except CoupangPartnersError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/jobs")
    def create_job(
        payload: JobCreatePayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        product_name = payload.product_name.strip()
        image_url = payload.image_url.strip()
        if not product_name or not image_url:
            known_context = store.get_known_product_context(payload.product_url)
            product_name = product_name or known_context.get("product_name", "")
            image_url = image_url or known_context.get("image_url", "")
        if not product_name or not image_url:
            product_context = fetch_best_product_context(
                payload.product_url,
                product_name,
            )
            product_name = product_name or product_context.page_title
            image_url = image_url or product_context.image_url
        return store.add_job(
            product_url=payload.product_url,
            product_name=product_name or "상품명 자동 확인 필요",
            image_url=image_url,
            memo=payload.memo,
        )

    @app.post("/api/jobs/{job_id}/draft")
    def draft_job(job_id: str, store: WorkbenchStore = Depends(get_store)) -> dict[str, Any]:
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        settings = store.get_settings()
        image_url = job.get("image_url", "").strip()
        draft = generate_draft(
            product_name=job["product_name"],
            product_url=job["product_url"],
            memo=job["memo"],
            persona=settings.get("writer_persona", ""),
            image_url=image_url,
        )
        return store.update_job_draft(
            job_id,
            title=draft.title,
            draft=draft.body,
            tags=draft.tags,
        )

    @app.post("/api/jobs/{job_id}/campaign")
    def campaign_job(job_id: str, store: WorkbenchStore = Depends(get_store)) -> dict[str, Any]:
        job = store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        settings = store.get_settings()
        product_context = fetch_best_product_context(
            job["product_url"],
            job["product_name"],
        )
        if not (product_context.facts or product_context.description.strip()):
            known_campaign = store.get_known_campaign_context(job["product_url"])
            if known_campaign:
                return store.update_job_campaign(
                    job_id,
                    sns_draft=known_campaign["sns_draft"],
                    image_brief=known_campaign["image_brief"],
                    blog_final=known_campaign["blog_final"],
                    sns_final=known_campaign["sns_final"],
                    title=known_campaign["title"],
                    tags=known_campaign["tags"],
                    image_url=job.get("image_url", "").strip() or known_campaign.get("image_url", ""),
                )
        reference_image_url = job.get("image_url", "").strip() or product_context.image_url
        product_name = job["product_name"] or product_context.page_title
        campaign = generate_campaign(
            product_name=product_name,
            product_url=job["product_url"],
            memo=job["memo"],
            reference_image_url=reference_image_url,
            persona=settings.get("writer_persona", ""),
            product_facts=product_context.facts or [],
            product_page_title=product_name,
            product_description=product_context.description,
        )
        return store.update_job_campaign(
            job_id,
            sns_draft=campaign.sns_draft,
            image_brief=campaign.image_brief,
            blog_final=campaign.blog_final,
            sns_final=campaign.sns_final,
            title=campaign.title,
            tags=campaign.tags,
            image_url=reference_image_url if reference_image_url else None,
        )

    @app.patch("/api/jobs/{job_id}/generated-image")
    def update_generated_image(
        job_id: str,
        payload: GeneratedImagePayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        try:
            return store.update_job_generated_image(job_id, payload.generated_image_url)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None

    @app.get("/api/jobs/{job_id}/media")
    def list_media_candidates(
        job_id: str,
        store: WorkbenchStore = Depends(get_store),
    ) -> list[dict[str, Any]]:
        if store.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return store.list_media_candidates(job_id)

    @app.post("/api/jobs/{job_id}/media")
    def create_media_candidate(
        job_id: str,
        payload: MediaCandidatePayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        try:
            return store.add_media_candidate(job_id=job_id, **payload.model_dump())
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None

    @app.post("/api/media/{candidate_id}/approve")
    def approve_media_candidate(
        candidate_id: str,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        try:
            return store.approve_media_candidate(candidate_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Media candidate not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/api/media/{candidate_id}/reject")
    def reject_media_candidate(
        candidate_id: str,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        try:
            return store.reject_media_candidate(candidate_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Media candidate not found") from None

    @app.post("/api/jobs/{job_id}/publish")
    def publish_job(
        job_id: str,
        store: WorkbenchStore = Depends(get_store),
    ) -> PublishHandoff:
        if store.get_job(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        message = publish_handoff_message()
        store.mark_publish_handoff(job_id, message)
        return PublishHandoff(status="NEEDS_BROWSER_REVIEW", message=message)

    @app.get("/api/threads/profiles")
    def list_threads_profiles(
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> list[dict[str, Any]]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).list_profiles()
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        return store.list_threads_profiles()

    @app.get("/api/threads/publish-records")
    def list_threads_publish_records(
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> list[dict[str, Any]]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).list_publish_records()
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        return store.list_threads_publish_records()

    @app.post("/api/threads/publish-records/{job_id}/insights")
    def refresh_threads_publish_record_insights(
        job_id: str,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).refresh_record_insights(job_id)
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        return refresh_threads_record_insights(job_id, settings, store)

    @app.post("/api/threads/publish-records/{job_id}/permalink")
    def refresh_threads_publish_record_permalink(
        job_id: str,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).get_record_permalink(job_id)
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        return refresh_threads_record_permalink(job_id, settings, store)

    @app.delete("/api/threads/publish-records/{job_id}")
    def delete_threads_publish_record(
        job_id: str,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).delete_publish_record(job_id)
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        return delete_threads_record(job_id, store)

    @app.post("/api/threads/media")
    def upload_threads_media(
        payload: ThreadsMediaUploadPayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, str]:
        settings = store.get_settings()
        if not uses_remote_threads_service(settings):
            raise HTTPException(status_code=400, detail="Threads Service URL is required to host generated images")
        try:
            return get_threads_bridge_client(settings).upload_media(
                filename=payload.filename,
                content_type=payload.content_type,
                image_base64=payload.image_base64,
            )
        except ThreadsBridgeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None

    @app.post("/api/threads/auto-hook-image")
    def generate_auto_threads_hook_image(
        payload: ThreadsAutoHookImagePayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, str]:
        settings = store.get_settings()
        if not uses_remote_threads_service(settings):
            raise HTTPException(status_code=400, detail="Threads Service URL is required to host generated images")
        product_name = payload.product_name.strip()
        if not product_name:
            raise HTTPException(status_code=400, detail="상품명을 확인한 뒤 후킹 이미지를 만들 수 있습니다.")
        try:
            hook_image = generate_codex_hook_image(
                model=settings.get("codex_model", "").strip() or DEFAULT_CODEX_MODEL,
                product_name=product_name,
                product_url=payload.product_url,
                product_facts=payload.facts,
                variant=payload.variant,
                prompt=payload.prompt,
            )
        except CodexImageError as exc:
            raise HTTPException(status_code=502, detail=f"Codex image generation failed: {exc}") from None
        try:
            uploaded = get_threads_bridge_client(settings).upload_media(
                filename=hook_image.filename,
                content_type=hook_image.content_type,
                image_base64=hook_image.image_base64,
            )
        except ThreadsBridgeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None
        return {
            "image_url": uploaded.get("image_url", ""),
            "content_type": hook_image.content_type,
            "image_base64": hook_image.image_base64,
            "variant": str(max(0, payload.variant)),
        }

    @app.post("/api/threads/profiles")
    def upsert_threads_profile(
        payload: ThreadsProfilePayload,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).upsert_profile(
                    profile_key=payload.profile_key,
                    display_name=payload.display_name,
                    notes=payload.notes,
                )
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
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
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).start_auth(profile_key.strip())
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        profile = store.get_threads_profile(profile_key)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        client = get_threads_client(settings)
        return {"auth_url": client.build_authorization_url(profile_key.strip())}

    @app.get("/api/threads/auth/import/start")
    def start_threads_profile_import(
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, str]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).start_import()
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        client = get_threads_client(settings)
        state = f"{THREADS_IMPORT_STATE_PREFIX}{uuid4().hex}"
        return {"auth_url": client.build_authorization_url(state)}

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
        client = get_threads_client(store.get_settings())
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
            <p>이 창을 닫고 워크벤치로 돌아가도 됩니다.</p>
          </body>
        </html>
        """

    @app.post("/api/threads/draft")
    def create_threads_draft(
        payload: ThreadsDraftPayload,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        settings = store.get_settings()
        product_name = payload.product_name.strip()
        image_url = ""
        product_url = payload.product_url.strip()
        product_context = None
        partner_url = payload.partner_url.strip()
        hook_image_url = "" if payload.skip_hook_image else payload.hook_image_url.strip() or payload.image_url.strip()
        if hook_image_url and not payload.hook_image_permission_reviewed:
            raise HTTPException(status_code=400, detail="후킹 이미지 권한 검토가 필요합니다.")
        if hook_image_url and not payload.hook_image_no_product:
            raise HTTPException(status_code=400, detail="후킹 이미지는 상품이 보이지 않는 이미지만 사용할 수 있습니다.")
        api_error = ""
        if settings.get("coupang_access_key", "").strip() and settings.get("coupang_secret_key", "").strip():
            try:
                partner_product, resolved_url = fetch_coupang_partner_product(
                    product_url,
                    settings,
                    product_keyword=product_name,
                    sub_id=payload.coupang_channel_id,
                )
                if partner_product.partner_url and not partner_product.product_name and not product_name:
                    partner_product = enrich_partner_product_with_local_context(
                        partner_product,
                        original_url=product_url,
                        resolved_url=resolved_url or product_url,
                    )
                if partner_product.product_name:
                    product_context = partner_product.to_product_context(
                        source_url=product_url,
                        resolved_url=resolved_url or product_url,
                    )
                    product_name = partner_product.product_name
                    partner_url = partner_url or partner_product.partner_url
                elif product_name and partner_product.partner_url:
                    partner_url = partner_url or partner_product.partner_url
                    product_context = CoupangPartnerProduct(
                        product_name=product_name,
                        product_url=resolved_url or product_url,
                        partner_url=partner_url,
                        image_url=partner_product.image_url,
                        facts=partner_product.facts,
                        product_id=partner_product.product_id,
                    ).to_product_context(
                        source_url=product_url,
                        resolved_url=resolved_url or product_url,
                    )
                else:
                    api_error = "상품명으로 쿠팡 API에서 정확한 상품을 확인하지 못했습니다."
            except CoupangPartnersError as exc:
                api_error = str(exc)
        if (
            settings.get("coupang_access_key", "").strip()
            and settings.get("coupang_secret_key", "").strip()
            and product_context is None
        ):
            detail = api_error or "쿠팡 파트너스 API에서 상품 정보를 먼저 확인해 주세요."
            raise HTTPException(status_code=400, detail=detail)
        if product_context is None:
            product_context = fetch_best_product_context(
                product_url,
                product_name,
            )
        if not product_name:
            known_context = store.get_known_product_context(product_url)
            product_name = known_context.get("product_name", "") or product_context.page_title
        if not product_name:
            detail = (
                "쿠팡 파트너스 API에서 상품 정보를 찾지 못했습니다."
                if settings.get("coupang_access_key", "").strip() and settings.get("coupang_secret_key", "").strip()
                else "쿠팡 파트너스 API 키를 저장한 뒤 다시 시도해 주세요."
            )
            if api_error:
                detail = f"{detail} ({api_error})"
            raise HTTPException(
                status_code=400,
                detail=detail,
            )
        final_product_url = partner_url or product_url
        job = store.add_job(
            product_url=final_product_url,
            product_name=product_name or "상품명 자동 확인 필요",
            image_url=image_url,
            memo=payload.memo,
        )
        if hook_image_url:
            candidate = store.add_media_candidate(
                job_id=job["id"],
                source="hook-image",
                source_url=hook_image_url,
                image_url=hook_image_url,
                title=f"{job['product_name']} 후킹 이미지",
                notes="발행 전 확인한 무료/오픈 상황 후킹 이미지",
                no_captions=True,
                no_tts=True,
                product_visible=False,
                permission_reviewed=True,
            )
            store.approve_media_candidate(candidate["id"])
            job = store.get_job(job["id"]) or job
        threads_text = generate_threads_post(
            product_name=job["product_name"],
            product_url=job["product_url"],
            product_facts=product_context.facts or [],
            memo=payload.memo,
            persona=settings.get("writer_persona", ""),
        )
        comment_text = generate_threads_comment(job["product_url"])
        try:
            threads_text = generate_codex_threads_post(
                model=settings.get("codex_model", "").strip() or DEFAULT_CODEX_MODEL,
                product_name=job["product_name"],
                product_url=job["product_url"],
                product_facts=product_context.facts or [],
                memo=payload.memo,
                persona=settings.get("writer_persona", ""),
                prompt=payload.codex_threads_prompt,
            )
        except CodexThreadsError:
            pass
        updated_job = store.update_job_threads_draft(
            job["id"],
            text=threads_text,
            comment_text=comment_text,
            title=f"{job['product_name']} Threads",
            tags=["쿠팡파트너스", "Threads"],
            image_url=hook_image_url or image_url or None,
        )
        return {
            "job": updated_job,
            "text": threads_text,
            "comment_text": comment_text,
            "publish_image_url": approved_threads_hook_image_url(updated_job, store),
        }

    def publish_threads_job(
        *,
        job: dict[str, Any],
        profile_key: str,
        text: str,
        comment_text: str,
        store: WorkbenchStore,
        image_url_override: str = "",
    ) -> dict[str, Any]:
        profile = store.get_threads_profile(profile_key, include_token=True)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        if not profile.get("is_connected"):
            raise HTTPException(status_code=400, detail="Threads profile is not connected")
        client = get_threads_client(store.get_settings())
        image_url = image_url_override.strip() or approved_threads_hook_image_url(job, store)
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
        permalink = fetch_threads_permalink(client, post_id, profile["access_token"], job["id"], store)
        comment_text = comment_text.strip()
        reply_id = ""
        if comment_text:
            try:
                reply = client.publish_reply(
                    threads_user_id=profile["threads_user_id"],
                    access_token=profile["access_token"],
                    text=comment_text,
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
            threads_permalink=permalink,
            published_text=f"본문:\n{text.strip()}\n\n댓글:\n{comment_text}" if comment_text else text,
        )
        return {
            "status": "THREADS_PUBLISHED",
            "threads_post_id": post_id,
            "threads_reply_id": reply_id,
            "threads_permalink": permalink,
            "job": updated_job,
        }

    @app.post("/api/threads/publish")
    def publish_threads_post(
        payload: ThreadsPublishPayload,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        job = store.get_job(payload.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                remote_result = get_threads_bridge_client(settings).publish(
                    profile_key=payload.profile_key,
                    product_url=job["product_url"],
                    product_name=job["product_name"],
                    image_url=approved_threads_hook_image_url(job, store),
                    text=payload.text,
                    comment_text=payload.comment_text,
                )
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
            post_id = str(remote_result.get("threads_post_id", "")).strip()
            reply_id = str(remote_result.get("threads_reply_id", "")).strip()
            permalink = str(
                remote_result.get("threads_permalink")
                or (remote_result.get("job") or {}).get("threads_permalink")
                or ""
            ).strip()
            if not post_id:
                raise HTTPException(status_code=502, detail="Threads service did not return a post id")
            updated_job = store.mark_threads_published(
                job_id=payload.job_id,
                profile_key=payload.profile_key,
                threads_post_id=post_id,
                threads_reply_id=reply_id,
                threads_permalink=permalink,
                published_text=(
                    f"본문:\n{payload.text.strip()}\n\n댓글:\n{payload.comment_text.strip()}"
                    if payload.comment_text.strip()
                    else payload.text
                ),
            )
            return {
                "status": "THREADS_PUBLISHED",
                "threads_post_id": post_id,
                "threads_reply_id": reply_id,
                "threads_permalink": permalink,
                "job": updated_job,
                "remote_job": remote_result.get("job", {}),
            }
        require_threads_bridge_access(settings, request)
        return publish_threads_job(
            job=job,
            profile_key=payload.profile_key,
            text=payload.text,
            comment_text=payload.comment_text,
            store=store,
        )

    @app.post("/api/threads/remote-publish")
    def publish_remote_threads_post(
        payload: ThreadsRemotePublishPayload,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        settings = store.get_settings()
        require_threads_bridge_access(settings, request)
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
            image_url_override=payload.image_url,
        )

    @app.post("/api/threads/profiles/{profile_key}/refresh")
    def refresh_threads_profile_token(
        profile_key: str,
        request: Request,
        store: WorkbenchStore = Depends(get_store),
    ) -> dict[str, Any]:
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).refresh_profile(profile_key)
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        profile = store.get_threads_profile(profile_key, include_token=True)
        if profile is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        if not profile.get("is_connected"):
            raise HTTPException(status_code=400, detail="Threads profile is not connected")
        client = get_threads_client(settings)
        try:
            refreshed = client.refresh_long_lived_token(profile["access_token"])
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
        settings = store.get_settings()
        if uses_remote_threads_service(settings):
            try:
                return get_threads_bridge_client(settings).disconnect_profile(profile_key)
            except ThreadsBridgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from None
        require_threads_bridge_access(settings, request)
        disconnected = store.disconnect_threads_profile(profile_key)
        if disconnected is None:
            raise HTTPException(status_code=404, detail="Threads profile not found")
        return disconnected

    @app.get("/api/logs")
    def list_logs(store: WorkbenchStore = Depends(get_store)) -> list[dict[str, Any]]:
        return store.list_logs()

    return app


app = create_app()

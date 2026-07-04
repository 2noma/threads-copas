from codex_coupang_workbench.storage import WorkbenchStore


def test_settings_round_trip(tmp_path):
    store = WorkbenchStore(tmp_path / "workbench.sqlite3")
    store.set_settings({"naver_blog_id": "myblog", "coupang_sub_id": "sub-1"})

    assert store.get_settings()["naver_blog_id"] == "myblog"
    assert store.get_settings()["coupang_sub_id"] == "sub-1"


def test_job_lifecycle(tmp_path):
    store = WorkbenchStore(tmp_path / "workbench.sqlite3")

    job = store.add_job(
        product_url="https://link.coupang.com/a/example",
        product_name="테스트 상품",
        memo="가벼운 설명",
        image_url="https://image.example/test.jpg",
    )
    jobs = store.list_jobs()

    assert len(jobs) == 1
    assert jobs[0]["id"] == job["id"]
    assert jobs[0]["status"] == "READY"
    assert jobs[0]["image_url"] == "https://image.example/test.jpg"

    updated = store.update_job_draft(job["id"], title="테스트 제목", draft="본문")

    assert updated["status"] == "DRAFTED"
    assert updated["title"] == "테스트 제목"
    assert updated["draft"] == "본문"


def test_media_candidate_approval_updates_job_image(tmp_path):
    store = WorkbenchStore(tmp_path / "workbench.sqlite3")
    job = store.add_job(
        product_url="https://link.coupang.com/a/example",
        product_name="키보드",
    )

    candidate = store.add_media_candidate(
        job_id=job["id"],
        source="youtube",
        source_url="https://www.youtube.com/watch?v=abc123",
        image_url="https://image.example/frame.jpg",
        timestamp_label="01:24",
        title="키보드 사용 영상",
        creator="리뷰 채널",
        notes="제품 상단 각인이 선명함",
        no_captions=True,
        no_tts=True,
        product_visible=True,
        permission_reviewed=True,
    )

    candidates = store.list_media_candidates(job["id"])
    assert len(candidates) == 1
    assert candidates[0]["id"] == candidate["id"]
    assert candidates[0]["review_status"] == "CANDIDATE"

    approved = store.approve_media_candidate(candidate["id"])
    updated_job = store.get_job(job["id"])

    assert approved["review_status"] == "APPROVED"
    assert approved["approved_at"]
    assert updated_job["image_url"] == "https://image.example/frame.jpg"


def test_campaign_fields_are_saved_on_job(tmp_path):
    store = WorkbenchStore(tmp_path / "workbench.sqlite3")
    job = store.add_job(
        product_url="https://link.coupang.com/a/example",
        product_name="광고 상품",
    )

    updated = store.update_job_campaign(
        job["id"],
        sns_draft="SNS 초안",
        image_brief="imagegen 실사 광고 이미지 브리프",
        blog_final="블로그 최종본",
        sns_final="SNS 최종본",
        title="광고 상품 캠페인",
        tags=["광고상품", "쿠팡파트너스"],
    )

    assert updated["status"] == "CAMPAIGN_READY"
    assert updated["sns_draft"] == "SNS 초안"
    assert updated["image_brief"] == "imagegen 실사 광고 이미지 브리프"
    assert updated["blog_final"] == "블로그 최종본"
    assert updated["sns_final"] == "SNS 최종본"
    assert updated["title"] == "광고 상품 캠페인"

    with_image = store.update_job_generated_image(job["id"], "https://image.example/ad.jpg")
    assert with_image["generated_image_url"] == "https://image.example/ad.jpg"


def test_threads_profile_lifecycle_and_publish_metadata(tmp_path):
    store = WorkbenchStore(tmp_path / "workbench.sqlite3")

    created = store.upsert_threads_profile(
        profile_key="tesla",
        display_name="테슬라 용품",
        notes="차량용품 전용",
    )

    assert created["profile_key"] == "tesla"
    assert created["display_name"] == "테슬라 용품"
    assert created["is_connected"] is False
    assert "access_token" not in created

    connected = store.save_threads_profile_token(
        profile_key="tesla",
        threads_user_id="12345",
        username="tesla_daily",
        access_token="secret-token",
        expires_in=5_184_000,
    )

    assert connected["is_connected"] is True
    assert connected["username"] == "tesla_daily"
    assert "access_token" not in connected

    private_profile = store.get_threads_profile("tesla", include_token=True)
    assert private_profile is not None
    assert private_profile["access_token"] == "secret-token"

    listed = store.list_threads_profiles()
    assert listed[0]["profile_key"] == "tesla"
    assert "access_token" not in listed[0]

    job = store.add_job(
        product_url="https://link.coupang.com/a/example",
        product_name="테슬라 수납 트레이",
    )
    published = store.mark_threads_published(
        job_id=job["id"],
        profile_key="tesla",
        threads_post_id="post_123",
    )

    assert published["status"] == "THREADS_PUBLISHED"
    assert published["threads_profile_key"] == "tesla"
    assert published["threads_post_id"] == "post_123"
    assert published["threads_published_at"]

    records = store.list_threads_publish_records()
    assert records[0]["product_name"] == "테슬라 수납 트레이"
    assert records[0]["product_url"] == "https://link.coupang.com/a/example"
    assert records[0]["profile_key"] == "tesla"
    assert records[0]["display_name"] == "테슬라 용품"
    assert records[0]["threads_post_id"] == "post_123"

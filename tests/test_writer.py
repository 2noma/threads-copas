from codex_coupang_workbench.writer import generate_campaign, generate_draft, generate_threads_post


def test_generate_draft_contains_coupang_disclosure_and_product_url():
    draft = generate_draft(
        product_name="무선 키보드",
        product_url="https://link.coupang.com/a/example",
        memo="조용한 타건감, 재택근무용",
        persona="실사용 경험을 중시하는 블로그 에디터",
        image_url="https://image.example/keyboard.jpg",
    )

    assert "쿠팡 파트너스" in draft.body
    assert "https://link.coupang.com/a/example" in draft.body
    assert "![무선 키보드](https://image.example/keyboard.jpg)" in draft.body
    assert "무선 키보드" in draft.title
    assert len(draft.sections) >= 3
    assert "무선 키보드" in draft.tags


def test_generate_draft_omits_internal_metadata_and_uses_natural_korean():
    draft = generate_draft(
        product_name="키크론 C2 Pro 8K RGB 핫스왑 유선 기계식 키보드",
        product_url="https://link.coupang.com/a/example",
        memo="풀배열, 유선 연결, 핫스왑 지원",
        persona="실사용 관점의 블로그 에디터",
    )

    assert "작성 톤:" not in draft.body
    assert "상품 링크:" not in draft.body
    assert "키보드은" not in draft.body
    assert "키보드는" in draft.body
    assert "구매 전 체크 포인트\n\n•" in draft.body


def test_generate_campaign_builds_ad_ready_package():
    campaign = generate_campaign(
        product_name="키크론 C2 Pro 기계식 키보드",
        product_url="https://link.coupang.com/a/example",
        memo="재택근무 책상, 풀배열, RGB, 핫스왑",
        reference_image_url="https://image.example/keychron.jpg",
        persona="실사용 관점의 블로그 에디터",
    )

    assert "키크론 C2 Pro 기계식 키보드" in campaign.sns_draft
    assert "https://link.coupang.com/a/example" in campaign.blog_final
    assert "쿠팡 파트너스" in campaign.blog_final
    assert "쿠팡 파트너스" in campaign.sns_final
    assert "imagegen" in campaign.image_brief.lower()
    assert "실사" in campaign.image_brief
    assert "광고" in campaign.image_brief
    assert "https://image.example/keychron.jpg" in campaign.image_brief
    assert "인포그래픽" not in campaign.image_brief
    assert "설명형 카드" not in campaign.image_brief
    assert "키보드은" not in campaign.blog_final
    assert "키보드는" in campaign.blog_final


def test_generate_campaign_uses_product_facts_instead_of_generic_fillers():
    campaign = generate_campaign(
        product_name="키크론 C2 Pro 기계식 키보드",
        product_url="https://link.coupang.com/a/example",
        memo="재택근무 책상에 올릴 풀배열 키보드",
        reference_image_url="https://image.example/keychron.jpg",
        product_facts=[
            "8K 폴링레이트",
            "RGB 백라이트",
            "핫스왑 스위치",
            "유선 USB-C 연결",
        ],
    )

    for fact in ["8K 폴링레이트", "RGB 백라이트", "핫스왑 스위치", "유선 USB-C 연결"]:
        assert fact in campaign.sns_draft
        assert fact in campaign.blog_final
        assert fact in campaign.image_brief
    assert "현재 판매가와 쿠폰 적용 여부" not in campaign.blog_final
    assert "최근 리뷰에서 반복되는 장점" not in campaign.blog_final


def test_generate_campaign_does_not_pretend_product_details_were_found():
    campaign = generate_campaign(
        product_name="로지텍 MX MASTER 4 무선 마우스",
        product_url="https://link.coupang.com/a/example",
    )

    combined = "\n".join(
        [
            campaign.sns_draft,
            campaign.image_brief,
            campaign.blog_final,
            campaign.sns_final,
        ]
    )
    assert "상품 상세 정보를 확인한 뒤 핵심 장점을 선별해 소개합니다" not in combined
    assert "상품 페이지에서 확인되는 핵심 사양과 사용 장면" not in combined
    assert "상품 상세의 사양과 사용 목적" not in combined
    assert "상품 상세를 자동으로 충분히 읽지 못했습니다" in combined


def test_generate_campaign_does_not_duplicate_official_description_when_facts_exist():
    campaign = generate_campaign(
        product_name="MX Master 4 무선 마우스 | Logitech",
        product_url="https://link.coupang.com/a/example",
        product_facts=["햅틱 피드백", "MagSpeed 스크롤", "8K DPI 및 Logi Options+ 커스터마이징"],
        product_description="MX Master 4로 워크플로를 업그레이드하세요. 햅틱 피드백, MagSpeed 스크롤, 8K DPI 및 Logi Options+ 커스터마이징. 지금 구매하기!",
    )

    combined = "\n".join([campaign.blog_final, campaign.sns_final, campaign.sns_draft])
    assert "지금 구매하기" not in combined
    assert "업그레이드하세요" not in combined
    assert "MX Master 4로 워크플로를 업그레이드하세요. 햅틱 피드백" not in combined


def test_generate_campaign_filters_price_and_coupang_source_phrasing_from_public_copy():
    campaign = generate_campaign(
        product_name="로지텍 MX MASTER 4 무선 마우스",
        product_url="https://link.coupang.com/a/example",
        product_facts=[
            "쿠팡 상품 페이지 기준 현재 판매가 170,050원",
            "정상가 179,000원에서 쿠폰할인 8,950원 적용 표시",
            "햅틱 피드백",
            "MagSpeed 스크롤",
        ],
    )

    combined = "\n".join([campaign.blog_final, campaign.sns_final, campaign.sns_draft, campaign.image_brief])
    assert "햅틱 피드백" in combined
    assert "MagSpeed 스크롤" in combined
    assert "쿠팡 상품 페이지 기준" not in combined
    assert "현재 판매가" not in combined
    assert "정상가" not in combined
    assert "170,050원" not in combined
    assert "179,000원" not in combined
    assert "8,950원" not in combined
    assert "• 050원" not in combined


def test_generate_campaign_filters_delivery_or_installation_dates_from_public_copy():
    campaign = generate_campaign(
        product_name="세라믹 식탁 세트",
        product_url="https://link.coupang.com/a/example",
        product_facts=[
            "설치일 지정 가능, 6/17부터 설치 가능",
            "식탁 + 의자 4p 구성",
        ],
    )

    combined = "\n".join([campaign.blog_final, campaign.sns_final, campaign.sns_draft])
    assert "식탁 + 의자 4p 구성" in combined
    assert "6/17부터 설치 가능" not in combined
    assert "설치일 지정 가능" not in combined
    assert " 6 같은 특징" not in combined
    assert "• 17부터 설치 가능" not in combined


def test_generate_campaign_filters_purchase_cta_fragments_from_facts():
    campaign = generate_campaign(
        product_name="Apple 정품 아이폰 맥세이프 투명 케이스",
        product_url="https://link.coupang.com/a/example",
        product_facts=[
            "com에서 구입하세요",
            "투명 계열의 프로스트 색상 BAR형 휴대폰 케이스",
            "맥세이프 링이 보이는 아이폰용 투명 케이스",
        ],
    )

    combined = "\n".join([campaign.blog_final, campaign.sns_final, campaign.sns_draft])
    assert "com에서 구입하세요" not in combined
    assert "투명 계열의 프로스트 색상" in combined


def test_generate_campaign_uses_natural_object_marker_and_specs_for_furniture():
    campaign = generate_campaign(
        product_name="세라믹 식탁 세트",
        product_url="https://link.coupang.com/a/example",
        product_facts=[
            "포세린 세라믹 1400 식탁과 일반의자 4개 구성의 4인용 식탁 세트",
            "설치일 지정 가능, 6/17부터 설치 가능",
            "색상 옵션은 상판 화이트와 의자 화이트 구성",
            "사이즈는 식탁 1400 x 800 x 730 mm",
        ],
    )

    usage_section = campaign.blog_final.split("활용 장면", 1)[1].split("https://", 1)[0]
    assert "세트을" not in campaign.blog_final
    assert "세트를 먼저 확인" in campaign.blog_final
    assert "색상 옵션" in usage_section
    assert "사이즈는 식탁" in usage_section
    assert "설치일 지정 가능" not in usage_section


def test_generate_campaign_uses_product_specs_for_usage_scene_before_commerce_facts():
    campaign = generate_campaign(
        product_name="로지텍 MX MASTER 4 무선 마우스",
        product_url="https://link.coupang.com/a/example",
        product_facts=[
            "쿠팡 상품 페이지 기준 현재 판매가 170,050원",
            "별점 4.8점과 리뷰 647개가 표시된 상품",
            "햅틱 피드백",
            "MagSpeed 스크롤",
            "8K DPI 센서 지원",
        ],
    )

    usage_section = campaign.blog_final.split("활용 장면", 1)[1].split("https://", 1)[0]
    assert "햅틱 피드백" in usage_section
    assert "MagSpeed 스크롤" in usage_section
    assert "현재 판매가" not in usage_section


def test_generate_campaign_keeps_review_copy_away_from_prices_and_coupang_source_terms():
    campaign = generate_campaign(
        product_name="Apple 정품 아이폰 맥세이프 투명 케이스",
        product_url="https://link.coupang.com/a/example",
        product_facts=[
            "투명 계열의 프로스트 색상 BAR형 휴대폰 케이스",
            "맥세이프 링이 보이는 아이폰용 투명 케이스",
            "쿠팡 상품 페이지 기준 할인가 22,500원",
            "현재 별점 4.8점 / 리뷰 23,046개",
            "무료배송 및 6/16 도착 예정",
        ],
    )

    combined = "\n".join([campaign.blog_final, campaign.sns_final, campaign.sns_draft, campaign.image_brief])
    assert "투명 계열의 프로스트 색상" in combined
    assert "맥세이프 링" in combined
    assert "쿠팡 상품" not in combined
    assert "쿠팡 확인 기준" not in combined
    assert "할인가" not in combined
    assert "22,500원" not in combined
    assert "별점" not in combined
    assert "리뷰" not in combined


def test_generate_threads_post_builds_short_disclosure_safe_copy():
    text = generate_threads_post(
        product_name="테슬라 파노라마 선루프 썬쉐이드 차광 커버",
        product_url="https://link.coupang.com/a/example",
        product_facts=[
            "파노라마 선루프용 차광 커버",
            "모델Y 호환",
            "현재 판매가 29,900원",
            "무료배송 및 내일 도착 예정",
        ],
    )

    assert text.startswith("이 포스팅은 쿠팡 파트너스 활동의 일환으로")
    assert "테슬라 파노라마 선루프 썬쉐이드 차광 커버" in text
    assert "파노라마 선루프용 차광 커버" in text
    assert "모델Y 호환" in text
    assert "https://link.coupang.com/a/example" in text
    assert "#쿠팡파트너스" in text
    assert "29,900원" not in text
    assert "내일 도착" not in text

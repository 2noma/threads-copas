from codex_coupang_workbench.product_research import (
    ProductContext,
    fetch_best_product_context,
    parse_official_search_results,
    parse_product_html,
)


def test_parse_product_html_extracts_product_metadata():
    html = """
    <html>
      <head>
        <title>키크론 C2 Pro 유선 기계식 키보드 | Coupang</title>
        <meta property="og:title" content="키크론 C2 Pro 8K RGB 핫스왑 기계식 키보드" />
        <meta property="og:description" content="풀배열 레이아웃, 8K 폴링레이트, RGB 백라이트, 핫스왑 스위치를 갖춘 유선 기계식 키보드" />
        <meta property="og:image" content="https://image.example/keychron.jpg" />
      </head>
    </html>
    """

    context = parse_product_html(html, "https://www.coupang.com/vp/products/example")

    assert context.page_title == "키크론 C2 Pro 8K RGB 핫스왑 기계식 키보드"
    assert "8K 폴링레이트" in context.description
    assert "핫스왑 스위치" in context.facts
    assert context.image_url == "https://image.example/keychron.jpg"


def test_parse_product_html_excludes_official_page_cta_from_facts():
    html = """
    <html>
      <head>
        <meta property="og:title" content="MX Master 4 무선 마우스 | Logitech" />
        <meta property="og:description" content="MX Master 4로 워크플로를 업그레이드하세요. 햅틱 피드백, MagSpeed 스크롤, 8K DPI 및 Logi Options+ 커스터마이징. 지금 구매하기!" />
      </head>
    </html>
    """

    context = parse_product_html(html, "https://www.logitech.com/ko-kr/shop/p/mx-master-4")

    assert "햅틱 피드백" in context.facts
    assert "MagSpeed 스크롤" in context.facts
    assert all("지금 구매하기" not in fact for fact in context.facts)


def test_parse_product_html_excludes_domain_purchase_cta_fragments():
    html = """
    <html>
      <head>
        <meta property="og:title" content="Apple 정품 아이폰 맥세이프 투명 케이스" />
        <meta property="og:description" content="apple.com에서 구입하세요." />
      </head>
    </html>
    """

    context = parse_product_html(html, "https://www.apple.com/kr/shop/product/example")

    assert context.facts == []
    assert all("com에서 구입하세요" not in fact for fact in context.facts)


def test_parse_product_html_prefers_gallery_product_image_over_brand_og_image():
    html = """
    <html>
      <head>
        <meta property="og:title" content="MX Master 4 무선 마우스 | Logitech" />
        <meta property="og:image" content="https://resource.logitech.com/content/dam/logitech/en/homepage/delorean-hp/logitech-global-og-image.png" />
      </head>
      <body>
        <img src="https://resource.logitech.com/content/dam/logitech/en/products/mice/mx-master-4/gallery/mx-master-4-graphite-top-angle-gallery-1.png" />
      </body>
    </html>
    """

    context = parse_product_html(html, "https://www.logitech.com/ko-kr/shop/p/mx-master-4")

    assert "gallery/mx-master-4-graphite-top-angle-gallery-1.png" in context.image_url
    assert "logitech-global-og-image" not in context.image_url


def test_parse_official_search_results_prefers_brand_official_pages():
    html = """
    <html>
      <body>
        <a class="result__a" href="https://www.coupang.com/vp/products/1">쿠팡 상품</a>
        <a class="result__a" href="/l/?uddg=https%3A%2F%2Fwww.logitech.com%2Fen-us%2Fshop%2Fp%2Fmx-master-4">Logitech MX Master 4</a>
        <a class="result__a" href="https://blog.example.com/mx-master-4-review">개인 리뷰</a>
      </body>
    </html>
    """

    links = parse_official_search_results(html, "로지텍 MX MASTER 4 무선 마우스")

    assert links == ["https://www.logitech.com/en-us/shop/p/mx-master-4"]


def test_fetch_best_product_context_uses_official_context_when_store_page_is_sparse(monkeypatch):
    monkeypatch.setattr(
        "codex_coupang_workbench.product_research.fetch_product_context",
        lambda url, timeout=8.0, proxy_url="": ProductContext(source_url=url, resolved_url=url, facts=[]),
    )
    monkeypatch.setattr(
        "codex_coupang_workbench.product_research.fetch_official_product_context",
        lambda product_name, timeout=8.0: ProductContext(
            source_url="official-search",
            resolved_url="https://www.logitech.com/en-us/shop/p/mx-master-4",
            page_title="Logitech MX Master 4",
            description="Haptic feedback, Actions Ring shortcuts, MagSpeed scroll wheel, 8K DPI tracking",
            image_url="https://resource.logitech.com/mx-master-4.png",
            facts=["Haptic feedback", "Actions Ring shortcuts", "MagSpeed scroll wheel", "8K DPI tracking"],
        ),
    )

    context = fetch_best_product_context(
        product_url="https://link.coupang.com/a/example",
        product_name="로지텍 MX MASTER 4 무선 마우스",
    )

    assert context.resolved_url == "https://www.logitech.com/en-us/shop/p/mx-master-4"
    assert "Actions Ring shortcuts" in context.facts


def test_fetch_best_product_context_passes_proxy_to_store_page_fetch(monkeypatch):
    calls = []

    def fake_fetch_product_context(url, timeout=8.0, proxy_url=""):
        calls.append({"url": url, "proxy_url": proxy_url})
        return ProductContext(source_url=url, resolved_url=url, page_title="쿠팡 상품", facts=["상품 설명"])

    monkeypatch.setattr("codex_coupang_workbench.product_research.fetch_product_context", fake_fetch_product_context)

    context = fetch_best_product_context(
        product_url="https://www.coupang.com/vp/products/example",
        product_name="테스트 상품",
        proxy_url="http://proxy.example:8080",
    )

    assert context.page_title == "쿠팡 상품"
    assert calls == [
        {
            "url": "https://www.coupang.com/vp/products/example",
            "proxy_url": "http://proxy.example:8080",
        }
    ]


def test_fetch_official_product_context_tries_brand_direct_url_before_search(monkeypatch):
    attempted: list[str] = []

    def fake_fetch_product_context(url, timeout=8.0):
        attempted.append(url)
        if url == "https://www.logitech.com/ko-kr/shop/p/mx-master-4":
            return ProductContext(
                source_url=url,
                resolved_url=url,
                page_title="MX Master 4 무선 마우스 | Logitech",
                facts=["햅틱 피드백", "MagSpeed 스크롤", "8K DPI"],
            )
        return ProductContext(source_url=url, resolved_url=url, facts=[])

    monkeypatch.setattr("codex_coupang_workbench.product_research.fetch_product_context", fake_fetch_product_context)

    from codex_coupang_workbench.product_research import fetch_official_product_context

    context = fetch_official_product_context("로지텍 MX MASTER 4 무선 마우스")

    assert attempted[0] == "https://www.logitech.com/ko-kr/shop/p/mx-master-4"
    assert context.page_title == "MX Master 4 무선 마우스 | Logitech"

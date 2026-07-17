from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ProductContext:
    source_url: str
    resolved_url: str = ""
    page_title: str = ""
    description: str = ""
    image_url: str = ""
    facts: list[str] | None = None
    detail_images: list[str] | None = None


class _ProductMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.image_candidates: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self.in_title = True
            return
        if tag.lower() in {"img", "source"}:
            self._collect_image_attrs(attrs)
            return
        if tag.lower() != "meta":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        key = (attr_map.get("property") or attr_map.get("name") or "").lower()
        content = attr_map.get("content", "")
        if key and content:
            self.meta[key] = _clean_text(content)
            if key in {"og:image", "twitter:image", "og:image:url"}:
                self._add_image_candidate(content)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    def _collect_image_attrs(self, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        for key in ("src", "data-src", "data-lazy-src"):
            self._add_image_candidate(attr_map.get(key, ""))
        srcset = attr_map.get("srcset") or attr_map.get("data-srcset") or ""
        for part in srcset.split(","):
            self._add_image_candidate(part.strip().split(" ")[0] if part.strip() else "")

    def _add_image_candidate(self, url: str) -> None:
        clean_url = html.unescape(url).strip()
        if clean_url and clean_url not in self.image_candidates:
            self.image_candidates.append(clean_url)


class _SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        href = attr_map.get("href", "")
        if href:
            self.links.append(href)


class _ProductSearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._active_href = ""
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._active_href:
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        href = attr_map.get("href", "")
        if href:
            self._active_href = href
            self._active_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_href:
            return
        text = _clean_text(" ".join(self._active_text))
        self.results.append((self._active_href, text))
        self._active_href = ""
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href:
            self._active_text.append(data)


BRAND_ALIASES = {
    "로지텍": "logitech",
    "키크론": "keychron",
    "애플": "apple",
    "삼성": "samsung",
    "LG": "lg",
    "엘지": "lg",
    "소니": "sony",
    "샤오미": "xiaomi",
}

BLOCKED_SOURCE_DOMAINS = (
    "coupang.",
    "naver.",
    "google.",
    "youtube.",
    "instagram.",
    "facebook.",
    "tiktok.",
    "amazon.",
    "11st.",
    "gmarket.",
    "auction.",
    "danawa.",
    "enuri.",
    "blog.",
)


def fetch_best_product_context(
    product_url: str,
    product_name: str,
    timeout: float = 8.0,
) -> ProductContext:
    store_context = fetch_product_context(product_url, timeout=timeout)
    if _has_enough_product_detail(store_context):
        return store_context
    official_context = fetch_official_product_context(product_name, timeout=timeout)
    if _has_enough_product_detail(official_context):
        return _merge_contexts(store_context, official_context)
    search_context = fetch_product_search_context(product_url, timeout=timeout)
    if search_context.page_title:
        return _merge_contexts(store_context, search_context)
    return store_context


def fetch_product_context(product_url: str, timeout: float = 8.0) -> ProductContext:
    clean_url = product_url.strip()
    if not clean_url:
        return ProductContext(source_url="")
    request = Request(
        clean_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000)
            charset = response.headers.get_content_charset() or "utf-8"
            text = body.decode(charset, errors="replace")
            resolved_url = response.geturl()
    except (OSError, URLError, ValueError):
        return ProductContext(source_url=clean_url, resolved_url=clean_url)
    return parse_product_html(text, clean_url, resolved_url=resolved_url)


def fetch_official_product_context(product_name: str, timeout: float = 8.0) -> ProductContext:
    clean_name = product_name.strip()
    if not clean_name:
        return ProductContext(source_url="official-search")
    for candidate_url in _official_direct_urls(clean_name):
        context = fetch_product_context(candidate_url, timeout=timeout)
        if _has_enough_product_detail(context):
            return context
    for search_url in _official_search_urls(clean_name):
        search_html = _fetch_text(search_url, timeout=timeout)
        for candidate_url in parse_official_search_results(search_html, clean_name):
            context = fetch_product_context(candidate_url, timeout=timeout)
            if _has_enough_product_detail(context):
                return context
    return ProductContext(source_url="official-search")


def parse_official_search_results(search_html: str, product_name: str) -> list[str]:
    parser = _SearchResultParser()
    parser.feed(search_html)
    product_terms = _product_search_terms(product_name)
    candidates: list[str] = []
    for raw_link in parser.links:
        link = _resolve_search_link(raw_link)
        if not link or link in candidates:
            continue
        if _is_official_candidate(link, product_terms):
            candidates.append(link)
    return candidates[:5]


def fetch_product_search_context(product_url: str, timeout: float = 8.0) -> ProductContext:
    product_ids = _extract_product_ids(product_url)
    if not product_ids:
        return ProductContext(source_url="product-search")
    for search_url in _product_search_urls(product_ids):
        context = parse_product_search_context(_fetch_text(search_url, timeout=timeout), product_ids)
        if context.page_title:
            return context
    return ProductContext(source_url="product-search")


def parse_product_search_context(search_html: str, product_ids: list[str]) -> ProductContext:
    wanted = {product_id for product_id in product_ids if product_id}
    if not search_html or not wanted:
        return ProductContext(source_url="product-search")
    parser = _ProductSearchResultParser()
    parser.feed(search_html)
    for raw_link, raw_title in parser.results:
        link = _resolve_search_link(raw_link)
        title = _clean_title(raw_title)
        if not link or not title:
            continue
        if _link_matches_product_ids(link, wanted) and _looks_like_product_title(title):
            return ProductContext(
                source_url="product-search",
                resolved_url=link,
                page_title=title,
                facts=["검색 결과에서 확인한 상품명"],
            )
    return ProductContext(source_url="product-search")


def parse_product_html(
    html_text: str,
    source_url: str,
    resolved_url: str = "",
) -> ProductContext:
    parser = _ProductMetaParser()
    parser.feed(html_text)
    raw_title = (
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or _clean_text(" ".join(parser.title_parts))
    )
    description = (
        parser.meta.get("og:description")
        or parser.meta.get("description")
        or parser.meta.get("twitter:description")
        or ""
    )
    image_url = _select_product_image(parser.image_candidates)
    page_title = _clean_title(raw_title)
    facts = _extract_facts(description)
    return ProductContext(
        source_url=source_url,
        resolved_url=resolved_url or source_url,
        page_title=page_title,
        description=description,
        image_url=image_url,
        facts=facts,
    )


def _fetch_text(url: str, timeout: float = 8.0) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000)
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="replace")
    except (OSError, URLError, ValueError):
        return ""


def _select_product_image(candidates: list[str]) -> str:
    usable = [candidate for candidate in candidates if _is_usable_image_candidate(candidate)]
    if not usable:
        return candidates[0] if candidates else ""
    return sorted(usable, key=_product_image_score, reverse=True)[0]


def _is_usable_image_candidate(url: str) -> bool:
    lowered = url.lower()
    if any(marker in lowered for marker in ("logo", "global-og", "favicon", "sprite", "icon-")):
        return False
    if not any(ext in lowered for ext in (".png", ".jpg", ".jpeg", ".webp")):
        return False
    return True


def _product_image_score(url: str) -> int:
    lowered = url.lower()
    score = 0
    for marker, weight in (
        ("/gallery/", 50),
        ("/products/", 40),
        ("/product/", 30),
        ("mx-master-4", 30),
        ("top-angle", 10),
        ("graphite", 5),
    ):
        if marker in lowered:
            score += weight
    if "homepage" in lowered:
        score -= 30
    return score


def _official_search_urls(product_name: str) -> list[str]:
    query = quote_plus(f"{product_name} official product")
    return [
        f"https://duckduckgo.com/html/?q={query}",
    ]


def _product_search_urls(product_ids: list[str]) -> list[str]:
    product_id = product_ids[0] if product_ids else ""
    if not product_id:
        return []
    query = quote_plus(f"{product_id} 쿠팡")
    return [f"https://search.naver.com/search.naver?query={query}"]


def _extract_product_ids(product_url: str) -> list[str]:
    parsed = urlparse(product_url.strip())
    ids: list[str] = []
    path_parts = [part for part in parsed.path.split("/") if part]
    for index, part in enumerate(path_parts):
        if part == "products" and index + 1 < len(path_parts):
            ids.append(path_parts[index + 1])
    query = parse_qs(parsed.query)
    for key in ("productId", "itemId", "vendorItemId"):
        ids.extend(query.get(key, []))
    return [item for item in _dedupe(ids) if item.isdigit()]


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        clean = str(item).strip()
        if clean and clean not in deduped:
            deduped.append(clean)
    return deduped


def _official_direct_urls(product_name: str) -> list[str]:
    lowered = product_name.lower()
    urls: list[str] = []
    if "로지텍" in lowered or "logitech" in lowered:
        slug = _slug_from_latin_product_name(product_name)
        if slug:
            urls.append(f"https://www.logitech.com/ko-kr/shop/p/{slug}")
            urls.append(f"https://www.logitech.com/en-us/shop/p/{slug}")
    return urls


def _slug_from_latin_product_name(product_name: str) -> str:
    tokens: list[str] = []
    for token in re.split(r"\s+", product_name):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", token).lower()
        if not cleaned or cleaned in {"logitech"}:
            continue
        if cleaned in {"wireless", "mouse"}:
            continue
        if token in {"무선", "마우스"}:
            continue
        tokens.append(cleaned)
    if len(tokens) < 2:
        return ""
    return "-".join(tokens[:4])


def _resolve_search_link(link: str) -> str:
    clean_link = html.unescape(link).strip()
    if not clean_link:
        return ""
    if clean_link.startswith("//"):
        clean_link = f"https:{clean_link}"
    if clean_link.startswith("/"):
        parsed = urlparse(clean_link)
        query = parse_qs(parsed.query)
        redirected = query.get("uddg", [""])[0]
        return unquote(redirected)
    parsed = urlparse(clean_link)
    query = parse_qs(parsed.query)
    if parsed.netloc.endswith("duckduckgo.com") and query.get("uddg"):
        return unquote(query["uddg"][0])
    return clean_link if parsed.scheme in {"http", "https"} else ""


def _is_official_candidate(link: str, product_terms: list[str]) -> bool:
    parsed = urlparse(link)
    domain = parsed.netloc.lower().removeprefix("www.")
    if not domain:
        return False
    if any(blocked in domain for blocked in BLOCKED_SOURCE_DOMAINS):
        return False
    return any(term and term in domain for term in product_terms)


def _product_search_terms(product_name: str) -> list[str]:
    normalized = product_name.strip()
    terms: list[str] = []
    for korean_brand, official_term in BRAND_ALIASES.items():
        if korean_brand.lower() in normalized.lower() and official_term not in terms:
            terms.append(official_term)
    for token in re.split(r"\s+", normalized):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", token).lower()
        if len(cleaned) >= 3 and cleaned not in terms:
            terms.append(cleaned)
    return terms


def _looks_like_product_title(title: str) -> bool:
    lowered = title.lower()
    if not title or len(title) < 4:
        return False
    return not any(
        marker in lowered
        for marker in (
            "naver",
            "keep",
            "메뉴",
            "바로가기",
            "어학사전",
            "사전",
            "제품후기",
            "review",
            "블로그",
            "www.",
            ".com",
            "›",
        )
    )


def _link_matches_product_ids(link: str, product_ids: set[str]) -> bool:
    parsed = urlparse(link)
    if any(product_id in parsed.path for product_id in product_ids):
        return True
    query = parse_qs(parsed.query)
    for key in ("productId", "itemId", "vendorItemId"):
        if any(value in product_ids for value in query.get(key, [])):
            return True
    return False


def _has_enough_product_detail(context: ProductContext) -> bool:
    facts = context.facts or []
    return len(facts) >= 2 or _has_useful_description(context.description)


def _merge_contexts(store_context: ProductContext, official_context: ProductContext) -> ProductContext:
    return ProductContext(
        source_url=store_context.source_url,
        resolved_url=official_context.resolved_url or official_context.source_url,
        page_title=official_context.page_title or store_context.page_title,
        description=official_context.description or store_context.description,
        image_url=store_context.image_url or official_context.image_url,
        facts=official_context.facts or store_context.facts or [],
    )


def _extract_facts(text: str) -> list[str]:
    normalized = _clean_text(text)
    if not normalized:
        return []
    parts = re.split(r"[,·/|ㆍ\n]+", normalized)
    facts: list[str] = []
    for part in parts:
        fact = _clean_text(part)
        if len(fact) < 2:
            continue
        for candidate in _fact_candidates(fact):
            if not _is_low_value_fact(candidate) and candidate not in facts:
                facts.append(candidate)
    return facts[:8]


def _fact_candidates(text: str) -> list[str]:
    text = _clean_fact_text(text)
    candidates = [text] if text else []
    for marker in ("를 갖춘", "을 갖춘", "가 있는", "이 있는"):
        if marker in text:
            candidates.insert(0, text.split(marker)[0])
    cleaned: list[str] = []
    for candidate in candidates:
        candidate = re.sub(r"(을|를)$", "", candidate.strip())
        if candidate and candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned


def _clean_fact_text(text: str) -> str:
    sentences = [part.strip() for part in re.split(r"[.!?]\s*", text) if part.strip()]
    if sentences:
        useful_sentences = [sentence for sentence in sentences if not _is_cta_sentence(sentence)]
        if useful_sentences:
            text = useful_sentences[-1]
        else:
            return ""
    text = re.sub(r"\b지금\s*구매하기\b", "", text, flags=re.IGNORECASE)
    return text.strip(" .!?\n\t")


def _is_cta_sentence(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "구매하기",
            "구입하세요",
            "업그레이드하세요",
            "확인하세요",
            "자세히 알아보기",
            "shop now",
            "buy now",
        )
    )


def _has_useful_description(text: str) -> bool:
    cleaned = _clean_fact_text(text)
    return bool(cleaned) and not _is_low_value_fact(cleaned) and len(cleaned) >= 12


def _is_low_value_fact(text: str) -> bool:
    cleaned = _clean_text(text).strip(" .!?\n\t")
    lowered = cleaned.lower()
    if not cleaned:
        return True
    if lowered in {"com", "www", "apple", "coupang"}:
        return True
    if re.fullmatch(r"(www\.)?[a-z0-9-]+\.(com|co\.kr|net|kr).*", lowered):
        return True
    return any(
        phrase in lowered
        for phrase in (
            "com에서 구입",
            ".com에서 구입",
            "에서 구입하세요",
            "지금 쿠팡에서",
            "다양한 bar형 제품들을 확인",
        )
    )


def _clean_title(text: str) -> str:
    cleaned = _clean_text(text)
    for separator in ("|", "-", "–"):
        if separator in cleaned and "coupang" in cleaned.lower():
            cleaned = cleaned.split(separator)[0].strip()
    return cleaned


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()

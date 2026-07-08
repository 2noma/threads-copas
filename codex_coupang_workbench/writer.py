from __future__ import annotations

from dataclasses import dataclass
import re


DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


@dataclass(frozen=True)
class DraftPost:
    title: str
    body: str
    sections: list[str]
    tags: list[str]


@dataclass(frozen=True)
class CampaignPackage:
    title: str
    sns_draft: str
    image_brief: str
    blog_final: str
    sns_final: str
    tags: list[str]


def generate_draft(
    product_name: str,
    product_url: str,
    memo: str = "",
    persona: str = "",
    image_url: str = "",
) -> DraftPost:
    clean_name = product_name.strip() or "추천 상품"
    clean_url = product_url.strip()
    clean_memo = memo.strip() or "상품 특징을 확인하고 구매 전 체크할 포인트를 정리했습니다."
    clean_image_url = image_url.strip()
    subject_marker = _subject_marker(clean_name)

    title = f"{clean_name} 구매 전 체크할 점과 추천 포인트"
    sections = [
        "첫인상",
        "구매 전 확인하면 좋은 점",
        "이런 분에게 잘 맞습니다",
        "정리",
    ]
    tags = _build_tags(clean_name)
    parts = [
        DISCLOSURE,
        title,
    ]
    if clean_image_url:
        parts.append(f"![{clean_name}]({clean_image_url})")
    parts.extend(
        [
            "첫인상",
            f"{clean_memo}",
            f"{clean_name}{subject_marker} 가격, 배송 조건, 최근 리뷰 흐름을 함께 보고 판단하는 것이 좋습니다.",
            "구매 전 체크 포인트",
            "• 현재 판매가와 쿠폰 적용 여부",
            "• 배송 방식과 도착 예정일",
            "• 최근 리뷰에서 반복해서 언급되는 장점과 불편점",
            "• 옵션, 색상, 구성품 차이",
            "이런 분에게 잘 맞습니다",
            "구매 전에 핵심 장단점을 빠르게 확인하고 싶은 분, 용도에 맞는 옵션을 비교해 보고 싶은 분에게 잘 맞습니다.",
            "정리",
            f"{clean_name}{subject_marker} 구매 목적이 분명할 때 만족도가 높아지는 제품입니다. 최신 가격과 옵션은 아래 링크에서 한 번 더 확인해 보세요.",
            f"{clean_url}",
        ]
    )
    body = "\n\n".join(parts)
    return DraftPost(title=title, body=body, sections=sections, tags=tags)


def generate_campaign(
    product_name: str,
    product_url: str,
    memo: str = "",
    reference_image_url: str = "",
    persona: str = "",
    product_facts: list[str] | None = None,
    product_page_title: str = "",
    product_description: str = "",
) -> CampaignPackage:
    clean_name = product_page_title.strip() or product_name.strip() or "추천 상품"
    clean_url = product_url.strip()
    clean_memo = memo.strip()
    clean_description = product_description.strip()
    clean_reference = reference_image_url.strip()
    subject_marker = _subject_marker(clean_name)
    tags = _build_tags(clean_name)
    persona_hint = persona.strip() or "실사용 관점의 블로그 에디터"
    title = f"{clean_name} 광고 캠페인"
    facts = _normalize_facts(product_facts or [])
    if clean_memo:
        facts.extend(_normalize_facts([clean_memo]))
    if clean_description and not facts:
        facts.extend(_normalize_facts([clean_description]))
    facts = _dedupe(facts)
    public_facts = _public_content_facts(facts)
    has_product_details = bool(public_facts)
    fact_line = (
        ", ".join(public_facts[:5])
        if has_product_details
        else "상품 상세를 자동으로 충분히 읽지 못했습니다. 강조 포인트를 입력하면 그 내용으로 다시 정리합니다."
    )
    fact_bullets = (
        "\n".join(f"• {fact}" for fact in public_facts[:6])
        if has_product_details
        else "• 상품 상세를 자동으로 충분히 읽지 못했습니다.\n• 상품명과 링크만으로 확인 가능한 범위가 제한적입니다."
    )
    primary_fact = public_facts[0] if has_product_details else "상품 상세를 자동으로 충분히 읽지 못했습니다"

    sns_draft = "\n".join(
        [
            f"{clean_name}",
            (
                f"{primary_fact} 중심으로 보는 상품입니다."
                if has_product_details
                else f"{primary_fact}. 상품 내용 / 강조 포인트를 입력하면 더 정확한 SNS 글로 다시 정리합니다."
            ),
            fact_bullets,
            "상세 옵션과 구성은 링크에서 확인하세요." if has_product_details else "상품 내용 / 강조 포인트를 보강하면 더 정확하게 정리됩니다.",
            f"{clean_url}",
            "#쿠팡추천 #쿠팡파트너스",
        ]
    )

    reference_line = (
        f"참고 이미지 URL: {clean_reference}. 제품 형태와 주요 색감은 이 이미지를 우선 참고한다."
        if clean_reference
        else "참고 이미지가 없으므로 제품명과 확보된 상품 정보를 바탕으로 자연스러운 실사 광고 컷을 구성한다."
    )
    image_brief = "\n".join(
        [
            "imagegen 실사 광고 이미지 브리프",
            f"상품: {clean_name}",
            f"상품에서 반드시 보여줄 요소: {fact_line}",
            reference_line,
            "방향: 제품이 첫눈에 보이는 프리미엄 커머셜 사진. 상품의 실제 용도와 핵심 사양이 시각적으로 느껴지는 사용 장면 또는 제품 단독 컷.",
            "구도: 제품을 화면 중심에 크게 배치하고 주변 소품은 상품의 용도만 암시할 정도로 절제한다.",
            "피해야 할 요소: 정보 나열 그래픽, 표, 긴 문구, 말풍선, 튜토리얼 화면, 과장된 효과, 브랜드가 아닌 임의 로고.",
            "결과물: 블로그와 SNS 광고에 바로 사용할 수 있는 사실적인 제품 광고 이미지.",
        ]
    )

    blog_final_parts = [
        DISCLOSURE,
            f"{clean_name} 핵심 포인트 정리",
        (
            _intro_sentence(clean_name, public_facts, persona_hint)
            if has_product_details
            else f"{clean_name}{subject_marker} 현재 자동 수집된 상세 정보가 부족합니다. 아래 링크에서 옵션과 구성품을 확인한 뒤 강조 포인트를 보강하는 것이 좋습니다."
        ),
        "상품 내용",
        fact_bullets,
        "활용 장면",
        _usage_sentence(clean_name, public_facts),
        (
            f"{clean_name}{subject_marker} 위 요소가 필요한 분에게 우선 비교해볼 만한 상품입니다. 상세 옵션과 구성은 아래 링크에서 확인하세요."
            if has_product_details
            else f"{clean_name}{subject_marker} 상품 상세를 자동으로 충분히 읽지 못했습니다. 정확한 광고 글을 위해 상품 상세의 핵심 사양이나 강조 포인트를 입력해 주세요."
        ),
        clean_url,
    ]
    blog_final = "\n\n".join(blog_final_parts)

    sns_final = "\n".join(
        [
            DISCLOSURE,
            f"{clean_name}",
            f"{fact_line}",
            "필요한 사양과 사용 장면이 맞는지 링크에서 확인하세요.",
            clean_url,
            "#쿠팡파트너스 #쿠팡추천",
        ]
    )

    return CampaignPackage(
        title=title,
        sns_draft=sns_draft,
        image_brief=image_brief,
        blog_final=blog_final,
        sns_final=sns_final,
        tags=tags,
    )


def generate_threads_post(
    product_name: str,
    product_url: str,
    product_facts: list[str] | None = None,
    memo: str = "",
    persona: str = "",
) -> str:
    clean_name = product_name.strip() or "추천 상품"
    clean_url = product_url.strip()
    facts = _normalize_facts(product_facts or [])
    if memo.strip():
        facts.extend(_normalize_facts([memo]))
    public_facts = _public_content_facts(_dedupe(facts))
    detail_line = _threads_detail_sentence(clean_name, public_facts)

    return "\n\n".join(
        [
            _threads_hook_sentence(clean_name),
            clean_name,
            detail_line,
            _threads_usage_sentence(clean_name, public_facts),
            _threads_check_sentence(clean_name),
        ]
    )


def generate_threads_comment(product_url: str) -> str:
    clean_url = product_url.strip()
    return f"{DISCLOSURE}\n\n{clean_url}" if clean_url else DISCLOSURE


def _build_tags(product_name: str) -> list[str]:
    tokens = [part for part in product_name.replace("/", " ").split() if part]
    tags = [product_name]
    tags.extend(tokens[:4])
    tags.extend(["쿠팡추천", "쿠팡파트너스"])
    deduped: list[str] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped


def _threads_hook_sentence(product_name: str) -> str:
    lowered = product_name.lower()
    if any(term in product_name for term in ("강아지", "반려", "펫", "하네스", "물티슈")):
        return "산책이나 외출이 잦으면 작게 챙겨두는 용품이 은근히 편하더라고요."
    if "테슬라" in product_name or "tesla" in lowered:
        return "차 안에서 매일 거슬리는 부분은 작은 용품 하나로 체감이 꽤 달라집니다."
    if any(term in product_name for term in ("우산", "레인", "부츠", "장우산")):
        return "비 오는 날엔 꺼내기 쉽고 바로 쓰기 편한지가 제일 먼저 보이더라고요."
    return "자주 쓰는 생활템은 거창한 기능보다 실제로 손이 자주 가는지가 중요하죠."


def _threads_detail_sentence(product_name: str, facts: list[str]) -> str:
    selected = facts[:3]
    if not selected:
        return f"{product_name}{_topic_marker(product_name)} 상세 페이지에서 구성과 옵션을 확인해보고 고르면 좋습니다."
    if any(term in product_name for term in ("강아지", "반려", "펫", "물티슈")):
        portable = _find_fact(selected, ("소포장", "휴대", "20매", "20매입")) or selected[0]
        quantity = _find_fact(selected, ("구성", "팩", "개입", "20팩"))
        cleanup = _clean_usage_fact(_find_fact(facts, ("산책", "발", "털", "닦")))
        if quantity and cleanup:
            return f"{cleanup}할 때 쓰기 좋고, {portable}에 {quantity}이라 외출용으로 나눠 챙기기 편합니다."
        if cleanup:
            return f"{cleanup}할 때 쓰기 좋고, {portable}이라 외출용으로 챙기기 편합니다."
        return f"{portable}이라 산책 가방이나 외출 파우치에 넣어두기 좋습니다."
    if "테슬라" in product_name or "tesla" in product_name.lower():
        primary = selected[0]
        secondary = selected[1] if len(selected) > 1 else ""
        if secondary:
            return f"{primary} 제품이라 {secondary} 여부를 먼저 보고 고르면 좋습니다."
        return f"{primary} 용도로 필요한 분들이 먼저 비교해볼 만합니다."
    if any(term in product_name for term in ("우산", "레인", "부츠", "장우산")):
        return f"{selected[0]}처럼 비 오는 날 바로 쓰는 요소를 기준으로 보면 좋습니다."
    if len(selected) == 1:
        return f"{product_name}{_topic_marker(product_name)} {selected[0]} 부분을 먼저 볼 만합니다."
    if len(selected) == 2:
        return f"{product_name}{_topic_marker(product_name)} {selected[0]}, {selected[1]} 구성이 눈에 들어옵니다."
    return f"{product_name}{_topic_marker(product_name)} {selected[0]}, {selected[1]}, {selected[2]} 같은 부분을 보고 고르면 좋습니다."


def _threads_usage_sentence(product_name: str, facts: list[str]) -> str:
    joined = ", ".join(facts[:2])
    if any(term in product_name for term in ("강아지", "반려", "펫", "물티슈")):
        return "산책 후 발이나 털을 닦을 때, 외출 가방에 나눠 넣어두기 좋은 쪽으로 보면 됩니다."
    if "하네스" in product_name:
        return "산책할 때 착용감과 사이즈가 맞는지 먼저 보고 고르면 좋습니다."
    if "테슬라" in product_name:
        return "차량 모델 호환 여부와 실제 장착 위치를 먼저 맞춰보고 고르면 실패를 줄일 수 있습니다."
    if any(term in product_name for term in ("우산", "레인", "부츠", "장우산")):
        return "출근길이나 장마철 외출처럼 바로 써야 하는 상황에 맞춰 보면 좋습니다."
    if joined:
        return f"평소 사용 장면에서 {joined} 같은 부분이 필요한지 기준으로 보면 좋습니다."
    return "평소 쓰는 장면에 맞는지 먼저 생각해보고 고르면 좋습니다."


def _threads_check_sentence(product_name: str) -> str:
    if "테슬라" in product_name:
        return "구매 전에는 호환 모델, 장착 위치, 구성품을 꼭 확인해보세요."
    if any(term in product_name for term in ("강아지", "하네스")):
        return "구매 전에는 사이즈, 착용 방식, 반려견 체형에 맞는지 확인해보세요."
    if any(term in product_name for term in ("우산", "레인", "부츠", "장우산")):
        return "구매 전에는 사이즈, 소재, 휴대 방식을 확인해보세요."
    return "구매 전에는 구성, 사이즈, 사용 목적에 맞는지 확인해보세요."


def _find_fact(facts: list[str], terms: tuple[str, ...]) -> str:
    for fact in facts:
        if any(term in fact for term in terms):
            return fact
    return ""


def _clean_usage_fact(fact: str) -> str:
    cleaned = fact.strip()
    cleaned = cleaned.replace("에 사용", "")
    cleaned = cleaned.replace("으로 사용", "")
    return cleaned


def _normalize_facts(facts: list[str]) -> list[str]:
    normalized: list[str] = []
    for fact in facts:
        for part in re.split(r"ㆍ|(?<!\d)/(?!\d)|(?<!\d),(?!\d)", fact):
            cleaned = part.strip(" -•\n\t")
            if cleaned and not _is_low_value_fact(cleaned) and cleaned not in normalized:
                normalized.append(cleaned)
    return normalized


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _public_content_facts(facts: list[str]) -> list[str]:
    public_facts: list[str] = []
    for fact in facts:
        cleaned = _clean_source_phrasing(fact)
        if not cleaned or _is_commerce_fact(cleaned) or _mentions_price(cleaned):
            continue
        if cleaned not in public_facts:
            public_facts.append(cleaned)
    return public_facts


def _usage_sentence(product_name: str, facts: list[str]) -> str:
    marker = _subject_marker(product_name)
    product_specs = [fact for fact in facts if not _is_commerce_fact(fact)]
    selected = product_specs[:3] or facts[:3]
    joined = ", ".join(selected)
    if joined:
        if "마우스" in product_name:
            return f"{product_name}{marker} 문서 작업, 콘텐츠 편집, 긴 페이지 탐색처럼 스크롤과 버튼 조작이 잦은 환경에서 {joined} 같은 장점을 확인해볼 만합니다."
        return f"{product_name}{marker} {joined} 같은 특징을 실제 사용 장면에서 확인하고 선택하는 것이 좋습니다."
    return f"{product_name}{marker} 상품 상세를 자동으로 충분히 읽지 못했습니다. 정확한 활용 장면을 쓰려면 핵심 사양이나 사용 목적을 보강해야 합니다."


def _intro_sentence(product_name: str, facts: list[str], persona_hint: str) -> str:
    marker = _subject_marker(product_name)
    product_specs = [fact for fact in facts if not _is_commerce_fact(fact)]
    if "마우스" in product_name and product_specs:
        return f"{product_name}{marker} 정밀한 포인터 조작, 빠른 스크롤, 업무 흐름 커스터마이징을 중시하는 사용자에게 맞는 프리미엄 무선 마우스입니다."
    first_fact = product_specs[0] if product_specs else facts[0]
    return f"{product_name}{marker} {persona_hint} 기준으로 {first_fact}{_object_marker(first_fact)} 먼저 확인해볼 만한 상품입니다."


def _is_commerce_fact(fact: str) -> bool:
    commerce_terms = (
        "판매가",
        "정상가",
        "할인가",
        "가격",
        "쿠폰",
        "할인",
        "별점",
        "리뷰",
        "구매",
        "도착",
        "배송",
        "설치일",
        "설치 가능",
        "적립",
        "쿠팡캐시",
    )
    return any(term in fact for term in commerce_terms)


def _mentions_price(fact: str) -> bool:
    return bool(re.search(r"\d[\d,]*\s*원", fact))


def _clean_source_phrasing(fact: str) -> str:
    cleaned = fact.strip()
    cleaned = re.sub(r"^(쿠팡\s*)?상품\s*페이지\s*기준\s*", "", cleaned)
    cleaned = re.sub(r"^쿠팡\s*(확인\s*)?기준\s*", "", cleaned)
    cleaned = cleaned.replace("쿠팡 상품", "상품")
    return cleaned.strip(" -•\n\t")


def _is_low_value_fact(fact: str) -> bool:
    cleaned = fact.strip(" .!?\n\t")
    lowered = cleaned.lower()
    if not cleaned:
        return True
    if lowered in {"com", "www", "apple", "coupang"}:
        return True
    return any(
        phrase in lowered
        for phrase in (
            "com에서 구입",
            ".com에서 구입",
            "에서 구입하세요",
            "구입하세요",
            "구매하기",
            "확인하세요",
            "지금 쿠팡에서",
            "다양한 bar형 제품들을 확인",
        )
    )


def _object_marker(text: str) -> str:
    last = _last_korean_syllable(text)
    if last is None:
        return "을"
    return "을" if (ord(last) - 0xAC00) % 28 else "를"


def _subject_marker(text: str) -> str:
    last = _last_korean_syllable(text)
    if last is None:
        return "은"
    return "은" if (ord(last) - 0xAC00) % 28 else "는"


def _topic_marker(text: str) -> str:
    return _subject_marker(text)


def _last_korean_syllable(text: str) -> str | None:
    for char in reversed(text.strip()):
        if 0xAC00 <= ord(char) <= 0xD7A3:
            return char
    return None

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from .writer import DISCLOSURE

DEFAULT_CODEX_MODEL = "gpt-5.6-terra"
THREADS_COPY_MIN_CHARS = 150
THREADS_COPY_MAX_CHARS = 250
THREADS_COPY_MIN_SENTENCES = 3
THREADS_COPY_MAX_SENTENCES = 5
THREAD_REFERENCE_PATTERNS: tuple[str, ...] = ()
PERSONAS = (
    ("result_proof", "결과가 보이는 순간"),
    ("clever_use", "의외의 쓰임"),
    ("visual_desire", "눈에 들어오는 디테일"),
    ("emotional_reaction", "한마디 반응"),
    ("relatable_problem", "현실 불편 공감"),
    ("conversation", "질문과 의견"),
)
THREAD_STYLE_DIRECTIONS = {
    "result_proof": (
        "결과가 보이는 순간",
        "선택 미디어에 변화나 결과가 실제로 보이면 그 장면부터 쓰기. 화면 근거가 없으면 확인된 기능이 줄이는 구체적인 불편으로 안전하게 전환하기.",
    ),
    "clever_use": (
        "의외의 쓰임",
        "처음부터 상품을 설명하지 말고 화면이나 상품 사실에서 확인되는 예상 밖 사용 순간 하나를 바로 보여주기.",
    ),
    "visual_desire": (
        "눈에 들어오는 디테일",
        "모양, 배치, 움직임, 크기처럼 눈으로 확인되는 디테일 하나가 사용 장면에서 왜 탐나는지 짧게 연결하기.",
    ),
    "emotional_reaction": (
        "한마디 반응",
        "귀여움, 신기함, 탐남처럼 화면이나 확인된 상품 특징을 본 직후 나올 법한 짧은 반응으로 시작하되 과장된 감탄은 피하기.",
    ),
    "relatable_problem": (
        "현실 불편 공감",
        "독자가 반복해서 겪는 구체적인 불편 한 장면과 이를 줄이는 쓰임을 바로 붙이기.",
    ),
    "conversation": (
        "질문과 의견",
        "정답을 숨기는 낚시가 아니라 실제 사용 상황을 두고 사람들이 자기 경험이나 취향을 말할 수 있는 질문 또는 의견으로 끝내기.",
    ),
    "curiosity": (
        "호기심",
        "평범한 장면에서 예상 밖으로 불편한 지점 하나를 집어 첫 문장에 남기기.",
    ),
    "relatable": (
        "현실 공감",
        "독자가 겪어봤을 구체적인 불편으로 시작하고 그 상황에 필요한 쓰임으로 자연스럽게 이어가기.",
    ),
    "problem_solution": (
        "문제 해결",
        "자주 반복되는 불편과 이를 줄여주는 한 가지 기능을 원인과 결과가 보이게 연결하기.",
    ),
    "honest_discovery": (
        "솔직한 발견",
        "과장 없이 지나치기 쉬운 기능 하나와 그 기능이 필요한 순간을 짧게 붙이기.",
    ),
    "story": (
        "스토리",
        "누구나 떠올릴 수 있는 생활 장면을 한 컷처럼 보여주되 실제 체험을 지어내지 않기.",
    ),
    "conversion": (
        "구매 전환",
        "직접 사라고 하지 말고 어떤 상황에서 필요한 물건인지 구체적으로 남기기.",
    ),
    "shock": (
        "충격 문장형",
        "사용 장면에서 발견한 의외의 불편을 먼저 보여주기. 리뷰의 맥락과 인과관계는 유지하고 거짓 효과나 억지 반전은 만들지 않기.",
    ),
    "viral": (
        "바이럴 발견형",
        "예상 밖으로 불편한 생활 장면을 먼저 던지고 그 장면에 맞는 쓰임 하나를 강조하기. 유명인 사용, 본인 실사용, 가족 반응, 효능, 가격, 품절이나 희소성은 입력에 있어도 사실처럼 주장하지 않기.",
    ),
}

_PERSONA_FACT_INDEX = {
    key: index for index, (key, _label) in enumerate(PERSONAS)
}
_PERSONA_HOOK_ANGLES = {
    "result_proof": "화면이나 상품 사실에서 확인되는 변화와 결과부터 보여주기",
    "clever_use": "예상 밖 사용 순간 하나를 바로 보여주기",
    "visual_desire": "눈으로 확인되는 모양·배치·움직임 하나를 집어내기",
    "emotional_reaction": "확인된 특징을 본 직후의 짧은 반응으로 시작하기",
    "relatable_problem": "매일 반복되는 불편한 순간으로 시작하기",
    "conversation": "실제 사용 상황에 대한 의견이나 질문을 남기기",
    "curiosity": "의외의 쓰임 하나를 먼저 던지기",
    "relatable": "매일 반복되는 불편한 순간으로 시작하기",
    "problem_solution": "정리하거나 준비하는 과정의 마찰을 보여주기",
    "honest_discovery": "처음엔 지나쳤던 기능이 필요한 이유를 드러내기",
    "story": "누구나 떠올릴 수 있는 짧은 생활 장면으로 시작하기",
    "conversion": "어떤 사람의 어떤 상황에 맞는지 선명하게 남기기",
    "custom": "사용자 지정 페르소나에 맞는 한 가지 사용 장면으로 시작하기",
}
_EXPLANATORY_REVIEW_TONE_PATTERNS = (
    re.compile(r"(?:방식|구조|형태)(?:이|인|였)?(?:네|구나)"),
    re.compile(r"(?:활용|사용)하는\s+(?:제품|상품)"),
    re.compile(r"도움을\s+주는\s+(?:제품|상품)"),
)
_ACTUAL_USE_EXPERIENCE_PATTERN = re.compile(
    r"(?:써|사용해|먹어|입어|발라|신어)\s*봤"
    r"(?:는데|더니|어|고|다|어요|습니다)?"
    r"|사용했(?:는데|더니|어|고|다|어요|습니다)?"
    r"|(?:써|사용해|먹어|입어|발라|신어)\s*보(?:니|니까|았는데|았더니|았어|았다|았어요|았습니다)"
    r"|(?:써|사용해|먹어|입어|발라|신어)\s*본\s+결과"
)
_CANNED_OBSERVATION_PATTERNS = (
    re.compile(r"보니까[^.!?\n]{0,35}(?:거였네|이었네|였네)"),
    re.compile(r"(?:쓰는|찾는)\s*이유가\s*있었네"),
    re.compile(r"눈에\s*들어오(?:네|는지)"),
)


class CodexThreadsError(RuntimeError):
    pass


def _korean_review_style_issues(text: str, *, allow_first_person: bool) -> list[str]:
    """Return concrete reasons why generated copy does not read like a grounded review."""
    issues: list[str] = []
    for pattern in _EXPLANATORY_REVIEW_TONE_PATTERNS:
        match = pattern.search(text)
        if match:
            issues.append(
                f"'{match.group(0)}' 같은 설명체 대신 관찰 뒤 이해가 생기는 리뷰 문장으로 쓸 것"
            )
    for pattern in _CANNED_OBSERVATION_PATTERNS:
        match = pattern.search(text)
        if match:
            issues.append(
                f"'{match.group(0)}' 같은 정형화된 관찰 결론 대신 구체적인 사용 장면으로 끝낼 것"
            )
    if not allow_first_person and _ACTUAL_USE_EXPERIENCE_PATTERN.search(text):
        issues.append("사용자 메모에 실제 사용 경험이 없으므로 1인칭 체험을 주장하지 말 것")
    return issues


def _memo_has_first_person_experience(memo: str) -> bool:
    """Allow personal-use claims only when the memo states a concrete user experience."""
    return bool(_ACTUAL_USE_EXPERIENCE_PATTERN.search(memo.strip()))


def _copy_grounding(product_facts: list[str], style: str) -> tuple[str, str]:
    """Choose one concrete product fact and a non-overlapping hook angle per variant."""
    facts = [fact.strip() for fact in product_facts if fact and fact.strip()]
    angle = _PERSONA_HOOK_ANGLES.get(style, _PERSONA_HOOK_ANGLES["custom"])
    if not facts:
        return "자동 수집된 상세 정보 없음", angle
    media_facts = [fact for fact in facts if fact.startswith("선택 미디어 화면:")]
    if media_facts and style in {
        "result_proof",
        "clever_use",
        "visual_desire",
        "emotional_reaction",
    }:
        index = _PERSONA_FACT_INDEX.get(style, 0) % len(media_facts)
        return media_facts[index], angle
    index = _PERSONA_FACT_INDEX.get(style, len(_PERSONA_FACT_INDEX)) % len(facts)
    return facts[index], angle


def _reference_pattern_lines() -> list[str]:
    if not THREAD_REFERENCE_PATTERNS:
        return ["- 등록된 참고 패턴 없음"]
    return [f"- {pattern}" for pattern in THREAD_REFERENCE_PATTERNS]


def generate_codex_threads_post(
    *,
    product_name: str,
    product_url: str,
    product_facts: list[str] | None = None,
    memo: str = "",
    persona: str = "",
    prompt: str = "",
    style: str = "",
    custom_instruction: str = "",
    model: str = DEFAULT_CODEX_MODEL,
    timeout: float = 90.0,
) -> str:
    if shutil.which("codex") is None:
        raise CodexThreadsError("Codex CLI is not installed")

    temp_dir = Path(tempfile.mkdtemp(prefix="threads-codex-"))
    output_path = temp_dir / "threads-post.txt"
    command = [
        "codex",
        "exec",
        "--config",
        "model_reasoning_effort=medium",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_path),
    ]
    clean_model = model.strip()
    if clean_model:
        command.extend(["--model", clean_model])
    command.append("-")

    base_prompt = _build_codex_prompt(
        product_name=product_name,
        product_url=product_url,
        product_facts=product_facts or [],
        memo=memo,
        persona=persona,
        style=style or "relatable",
        custom_instruction=custom_instruction,
    )
    clean_prompt = prompt.strip()
    input_prompt = base_prompt
    if clean_prompt:
        input_prompt = "\n\n".join(
            [
                base_prompt,
                "사용자 추가 요청:",
                clean_prompt,
                "추가 요청은 위의 필수 제약을 바꾸지 않는 범위에서만 반영해.",
            ]
        )

    allow_first_person = _memo_has_first_person_experience(memo)
    attempt_prompt = input_prompt
    try:
        for attempt in range(2):
            try:
                subprocess.run(
                    command,
                    input=attempt_prompt,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=True,
                    cwd=str(temp_dir),
                )
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or str(exc)).strip()
                raise CodexThreadsError(detail or str(exc)) from exc
            except (OSError, subprocess.SubprocessError) as exc:
                raise CodexThreadsError(str(exc)) from exc

            try:
                text = output_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise CodexThreadsError("Codex output could not be read") from exc
            if not text:
                raise CodexThreadsError("Codex did not return a Threads post")

            normalized = _normalize_generated_post(text, product_url, product_name)
            issues = _korean_review_style_issues(
                normalized,
                allow_first_person=allow_first_person,
            )
            if not issues:
                return normalized
            if attempt == 1:
                raise CodexThreadsError(
                    f"한국어 문체 검사에 실패했습니다: {'; '.join(issues)}"
                )
            attempt_prompt = "\n\n".join(
                [
                    input_prompt,
                    "한국어 문체 교정:",
                    *[f"- {issue}" for issue in issues],
                    "이전 문장을 부분 치환하지 말고, 상품 근거를 유지한 자연스러운 리뷰 문장으로 전부 다시 써.",
                    "이번이 마지막 교정이므로 최종 답변에는 교정된 본문만 출력해.",
                ]
            )
        raise CodexThreadsError("한국어 문체 검사를 완료하지 못했습니다")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _build_codex_prompt(
    *,
    product_name: str,
    product_url: str,
    product_facts: list[str],
    memo: str,
    persona: str,
    style: str = "relatable",
    custom_instruction: str = "",
) -> str:
    facts = "\n".join(f"- {fact}" for fact in product_facts if fact.strip()) or "- 자동 수집된 상세 정보 없음"
    persona_line = persona.strip() or "친근하고 실사용 관점이 있는 한국어 Threads 작성자"
    style_label, style_direction = _style_direction(style, custom_instruction)
    primary_fact, hook_angle = _copy_grounding(product_facts, style)
    opening_direction = f"- 첫 문장 방향: {hook_angle}"
    if _memo_has_first_person_experience(memo):
        first_person_rule = (
            "- 사용자 메모에 실제 사용 경험이 있으므로, 메모에 적힌 경험 범위 안에서만 1인칭 후기를 쓸 수 있음"
        )
    else:
        first_person_rule = (
            "- 사용자 메모에 실제 사용 경험이 없으므로 '써보니', '직접 써봤는데' 같은 1인칭 체험을 지어내지 마"
        )
    media_facts = [
        fact.strip()
        for fact in product_facts
        if fact.strip().startswith("선택 미디어 화면:")
    ]
    media_rule = (
        "- 선택 미디어 근거가 있으므로 화면에서 실제로 확인되는 장면만 묘사하고, 보이지 않는 전후 결과나 감정은 만들지 마"
        if media_facts
        else "- 선택 미디어가 없으므로 화면이나 영상을 봤다고 쓰지 마. 상품 사실과 생활 장면만 사용해"
    )
    return "\n".join(
        [
            "Codex CLI에 로그인된 계정 인증을 사용해 쿠팡 파트너스 Threads 게시글을 작성해줘.",
            "최종 답변에는 게시글 본문만 출력해. 설명, 마크다운 코드블록, 주석은 쓰지 마.",
            "",
            "스타일:",
            "- 상품을 설명하거나 알려주는 사람이 아니라, 구체적인 생활 장면에서 쓰임이 드러나는 글로 쓰기",
            "- 상품의 방식·구조·활용법을 해설하는 설명체나 번역투를 쓰지 않기",
            "- 관찰했다거나 이유를 알았다거나 시선이 간다고 말하는 정형 결론을 쓰지 않기",
            "- 알아챘다는 결론을 말하지 말고, 실제로 불편이 생기는 순간과 쓰임을 붙여서 독자가 스스로 이해하게 하기",
            "- 독자가 겪어봤을 법한 구체적인 불편이나 순간으로 시작하기",
            "- 정보를 일부러 숨기지 말고 불편이 생기는 순간과 쓰임을 바로 이어서 보여주기",
            "- 문장 연결과 인과관계를 우선하고, 억지 반전이나 말장난보다 자연스러운 공감을 살리기",
            "- 짧은 문장과 줄바꿈으로 모바일에서 편하게 읽히는 톤",
            f"- 이번 출력 스타일: {style_label}",
            f"- {style_direction}",
            opening_direction,
            f"- 작성자 톤: {persona_line}",
            "",
            "사용자 요청으로 등록된 참고 Threads 패턴:",
            *_reference_pattern_lines(),
            "- 참고 패턴의 문장이나 표현을 복사하지 말고 첫 문장 유형, 정보 공개 순서, 말투와 리듬만 참고하기",
            "",
            "반드시 지킬 것:",
            "- 링크와 고지 문구는 본문에 쓰지 마. 링크와 고지는 별도 댓글에 들어간다.",
            "- '자세한 건 댓글에 남겨둘게요' 같은 댓글 안내 문장 쓰지 않기",
            "- 해시태그 쓰지 않기",
            "- 가격, 할인율, 배송일, 재고, 리뷰 수는 쓰지 않기",
            "- 입력에 없는 효과, 인증, 성능, 호환 모델은 지어내지 않기",
            media_rule,
            "- 검증된 상품 정보 중 한 가지인 아래 ‘이번 문구의 근거’를 반드시 본문 맥락에 반영하기",
            "- 다른 페르소나 문구와 같은 시작 문장이나 같은 사용 장면을 반복하지 않기",
            "- bullet 목록 금지",
            "- 상품명은 본문에 직접 쓰지 마. 브랜드명, 모델명, 정확한 상품명 노출 금지",
            "- 브랜드·모델·정확한 상품명은 숨기되, 상품 카테고리와 실제 쓰임은 독자가 알 수 있게 쓰기",
            "- 후기 내용은 사실 주장처럼 쓰지 말고 분위기만 참고하기",
            first_person_rule,
            "- 가족의 반응을 지어내지 마",
            "- 설명문처럼 쓰지 마. 사양, 구성, 장점 나열 금지",
            "- 구매 전 같은 표현 쓰지 마. '확인해보세요', '추천', '필요한 분', '비교해볼 만' 같은 문구도 쓰지 마",
            "- 억지 반전, 랜덤 비유, 과장된 결과를 만들지 마",
            "- 3~5개의 짧은 문장, 공백과 문장부호를 포함해 150~250자로 완성하기",
            "- 불편한 상황 → 상품이 쓰이는 장면 → 구체적인 변화나 반응 순서로 자연스럽게 이어가기",
            "- 같은 맥락을 반복해 글자 수만 늘리지 말고 각 문장에 새로운 상황이나 근거를 담기",
            "- 모든 문장은 짧은 해체(반말 구어체)로 쓰고, ~요·~습니다·~세요 같은 높임말 종결은 쓰지 마",
            "- 각 줄은 자연스러운 한국어로 의미를 완결하기",
            "- 마지막 문장은 상품명을 밝히거나 댓글을 안내하지 말고, 앞의 생활 장면과 자연스럽게 이어서 끝내기",
            "",
            f"내부 참고용 상품명: {product_name.strip() or '상품명 자동 확인 필요'}",
            f"쿠팡 URL: {product_url.strip()}",
            f"이번 문구의 근거: {primary_fact}",
            "상품 정보:",
            facts,
            f"사용자 메모: {memo.strip() or '없음'}",
        ]
    )


def edit_codex_threads_post(
    *,
    draft: str,
    product_name: str,
    product_facts: list[str] | None = None,
    memo: str = "",
    model: str = DEFAULT_CODEX_MODEL,
    timeout: float = 90.0,
) -> str:
    if shutil.which("codex") is None:
        raise CodexThreadsError("Codex CLI is not installed")

    facts = "\n".join(
        f"- {fact.strip()}" for fact in (product_facts or []) if fact.strip()
    ) or "- 자동 수집된 상세 정보 없음"
    prompt = "\n".join(
        [
            "아래 Threads 초안을 자연스러운 한국어로 최종 편집해줘.",
            "이 단계는 한국어 최종 편집이며 새로운 상품 정보나 경험을 만드는 단계가 아니야.",
            "최종 답변에는 편집된 본문만 출력해.",
            "초안의 사실과 구체적인 생활 상황은 유지하되 문장은 처음부터 다시 써.",
            "직역한 듯한 단어 조합, 어색한 조사와 어미, 명사만 이어 붙인 표현을 자연스러운 한국어로 고쳐.",
            "앞뒤 문장의 주어와 대상이 자연스럽게 이어지는지 확인하고, 같은 뜻을 표현만 바꿔 반복하지 마.",
            "한 문장에는 한 가지 의미만 담고, 두 가지 상황이나 결과가 섞이면 문장을 나눠.",
            "관찰했다거나 이유를 알았다거나 시선이 간다고 말하는 정형 결론을 쓰지 마.",
            "상품을 해설하지 말고 구체적인 불편이 생기는 순간과 쓰임이 바로 이어지게 써.",
            "사용자 메모에 없는 직접 사용 경험이나 가족 반응을 만들지 마.",
            "상품명, 브랜드, 모델명, 가격, 할인, 링크, 해시태그는 쓰지 마.",
            "3~5개의 짧은 문장, 공백과 문장부호를 포함해 150~250자의 해체 구어체로 완성해.",
            "불편한 상황 → 상품이 쓰이는 장면 → 구체적인 변화나 반응 순서로 자연스럽게 이어가.",
            "서로 밀접한 1~2문장을 한 문단으로 묶고, 새로운 상황·쓰임·결과로 넘어갈 때 빈 줄을 넣어 문단을 구분해.",
            "문장마다 기계적으로 줄바꿈하지 말고, 모바일 화면에서 의미 단위가 한눈에 읽히게 배치해.",
            "사용자 요청으로 등록된 참고 Threads 패턴은 원문을 복사하지 말고 구조와 리듬만 참고해.",
            *_reference_pattern_lines(),
            "",
            f"내부 참고용 상품명: {product_name.strip()}",
            "검증된 상품 정보:",
            facts,
            f"사용자 메모: {memo.strip() or '없음'}",
            "편집할 초안:",
            draft.strip(),
        ]
    )
    temp_dir = Path(tempfile.mkdtemp(prefix="threads-editor-codex-"))
    output_path = temp_dir / "threads-edited.txt"
    command = [
        "codex",
        "exec",
        "--config",
        "model_reasoning_effort=medium",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_path),
    ]
    if model.strip():
        command.extend(["--model", model.strip()])
    command.append("-")
    attempt_prompt = prompt
    try:
        for attempt in range(2):
            try:
                subprocess.run(
                    command,
                    input=attempt_prompt,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=True,
                    cwd=str(temp_dir),
                )
                edited = output_path.read_text(encoding="utf-8").strip()
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or str(exc)).strip()
                raise CodexThreadsError(detail or str(exc)) from exc
            except (OSError, subprocess.SubprocessError) as exc:
                raise CodexThreadsError(f"한국어 최종 편집 결과를 읽지 못했습니다: {exc}") from exc
            normalized = _normalize_generated_post(edited, "", product_name)
            if not normalized:
                raise CodexThreadsError("한국어 최종 편집 결과가 비어 있습니다")
            issues = _korean_review_style_issues(
                normalized,
                allow_first_person=_memo_has_first_person_experience(memo),
            )
            if not issues:
                return normalized
            if attempt == 1:
                raise CodexThreadsError(
                    f"한국어 최종 편집에 실패했습니다: {'; '.join(issues)}"
                )
            attempt_prompt = "\n\n".join(
                [
                    prompt,
                    "1차 한국어 편집에서 남은 문제:",
                    *[f"- {issue}" for issue in issues],
                    "문제 표현만 바꾸지 말고 전체 문장을 다시 편집해.",
                    "자연스러운 문장 연결과 1~2문장 단위 문단, 상황이 바뀌는 곳의 빈 줄까지 다시 확인해.",
                    "최종 답변에는 다시 편집한 본문만 출력해.",
                ]
            )
        raise CodexThreadsError("한국어 최종 편집을 완료하지 못했습니다")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def edit_codex_threads_posts(
    *,
    drafts: dict[str, str],
    product_name: str,
    product_facts: list[str] | None = None,
    memo: str = "",
    model: str = DEFAULT_CODEX_MODEL,
    timeout: float = 120.0,
) -> dict[str, str]:
    """Edit all persona drafts in one Codex request while preserving their keys."""
    clean_drafts = {
        str(key).strip(): str(draft).strip()
        for key, draft in drafts.items()
        if str(key).strip() and str(draft).strip()
    }
    if not clean_drafts:
        return {}
    if shutil.which("codex") is None:
        raise CodexThreadsError("Codex CLI is not installed")

    facts = "\n".join(
        f"- {fact.strip()}" for fact in (product_facts or []) if fact.strip()
    ) or "- 자동 수집된 상세 정보 없음"
    draft_json = json.dumps(clean_drafts, ensure_ascii=False, indent=2)
    prompt = "\n".join(
        [
            "아래 Threads 초안들을 자연스러운 한국어로 한꺼번에 최종 편집해줘.",
            "새로운 상품 정보나 사용 경험은 만들지 말고 각 초안의 사실과 페르소나 차이를 유지해.",
            "최종 답변에는 입력과 똑같은 키를 가진 JSON 객체 하나만 출력해. 설명이나 코드블록은 쓰지 마.",
            "각 값은 완성된 Threads 본문 문자열이어야 해.",
            "직역투, 어색한 조사와 어미, 명사 나열, 설명체, 정형화된 관찰 결론을 자연스럽게 다시 써.",
            "상품을 해설하지 말고 구체적인 불편이 생기는 순간과 쓰임이 바로 이어지게 써.",
            "각 본문은 3~5개의 짧은 문장과 150~250자의 해체 구어체로 완성해.",
            "서로 밀접한 1~2문장을 한 문단으로 묶고 상황·쓰임·결과가 바뀌는 곳에는 빈 줄을 넣어.",
            "문장마다 기계적으로 줄바꿈하지 말고 모바일에서 의미 단위가 한눈에 읽히게 배치해.",
            "상품명, 브랜드, 모델명, 가격, 할인, 링크, 해시태그는 쓰지 마.",
            "사용자 메모에 없는 직접 사용 경험이나 가족 반응은 만들지 마.",
            "각 키의 첫 문장과 사용 장면이 서로 겹치지 않게 유지해.",
            "",
            f"내부 참고용 상품명: {product_name.strip()}",
            "검증된 상품 정보:",
            facts,
            f"사용자 메모: {memo.strip() or '없음'}",
            "편집할 초안 JSON:",
            draft_json,
        ]
    )
    temp_dir = Path(tempfile.mkdtemp(prefix="threads-batch-editor-codex-"))
    output_path = temp_dir / "threads-edited.json"
    command = [
        "codex",
        "exec",
        "--config",
        "model_reasoning_effort=medium",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_path),
    ]
    if model.strip():
        command.extend(["--model", model.strip()])
    command.append("-")
    attempt_prompt = prompt
    expected_keys = set(clean_drafts)
    try:
        for attempt in range(2):
            try:
                subprocess.run(
                    command,
                    input=attempt_prompt,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=True,
                    cwd=str(temp_dir),
                )
                raw = output_path.read_text(encoding="utf-8").strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
                payload = json.loads(raw)
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or str(exc)).strip()
                raise CodexThreadsError(detail or str(exc)) from exc
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                raise CodexThreadsError(f"한국어 일괄 편집 결과를 읽지 못했습니다: {exc}") from exc
            if not isinstance(payload, dict) or set(payload) != expected_keys:
                raise CodexThreadsError("한국어 일괄 편집 결과의 문구 키가 일치하지 않습니다")

            normalized = {
                key: _normalize_generated_post(str(payload[key]), "", product_name)
                for key in clean_drafts
            }
            if any(not text for text in normalized.values()):
                raise CodexThreadsError("한국어 일괄 편집 결과에 빈 문구가 있습니다")
            issue_map = {
                key: _korean_review_style_issues(
                    text,
                    allow_first_person=_memo_has_first_person_experience(memo),
                )
                for key, text in normalized.items()
            }
            issue_map = {key: issues for key, issues in issue_map.items() if issues}
            if not issue_map:
                return normalized
            if attempt == 1:
                detail = "; ".join(
                    f"{key}: {', '.join(issues)}" for key, issues in issue_map.items()
                )
                raise CodexThreadsError(f"한국어 일괄 편집에 실패했습니다: {detail}")
            attempt_prompt = "\n\n".join(
                [
                    prompt,
                    "1차 한국어 편집에서 남은 문제:",
                    *[
                        f"- {key}: {issue}"
                        for key, issues in issue_map.items()
                        for issue in issues
                    ],
                    "문제 표현만 바꾸지 말고 해당 문구 전체를 다시 편집해.",
                    "최종 답변에는 모든 입력 키를 포함한 JSON 객체 하나만 출력해.",
                ]
            )
        raise CodexThreadsError("한국어 일괄 편집을 완료하지 못했습니다")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _normalize_generated_post(text: str, product_url: str, product_name: str = "") -> str:
    clean_text = unicodedata.normalize("NFKC", text).strip().strip("`")
    clean_url = product_url.strip()
    clean_name = unicodedata.normalize("NFKC", product_name).strip()
    if DISCLOSURE in clean_text:
        clean_text = clean_text.replace(DISCLOSURE, "")
    if clean_url:
        clean_text = clean_text.replace(clean_url, "")
    if clean_name:
        clean_text = re.sub(re.escape(clean_name), "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(
        r"(?im)^.*쿠팡\s*파트너스.*$",
        "",
        clean_text,
    )
    clean_text = re.sub(
        r"(?im)^.*(?:제휴|광고).*(?:수수료|제공받|받을\s*수).*$",
        "",
        clean_text,
    )
    clean_text = re.sub(r"https?://[^\s]+", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"#[^\s#]+", "", clean_text)
    clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", clean_text)
    clean_text = clean_text.replace("#쿠팡파트너스", "")
    clean_text = "\n".join(
        line.rstrip()
        for line in clean_text.splitlines()
        if not _should_drop_generated_line(line)
    )
    return _limit_generated_post(clean_text.strip())


def _limit_generated_post(text: str) -> str:
    compact = _casualize_generated_post(re.sub(r"[ \t]+", " ", text).strip())
    if not compact:
        return ""

    paragraphs = [
        re.sub(r"\s*\n\s*", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n+", compact)
        if paragraph.strip()
    ]
    selected_paragraphs: list[str] = []
    selected_sentence_count = 0
    for paragraph in paragraphs:
        selected_sentences: list[str] = []
        sentences = [
            re.sub(r"\s+", " ", sentence).strip()
            for sentence in re.split(r"(?<=[.!?…])\s+", paragraph)
            if sentence.strip()
        ]
        for sentence in sentences:
            if selected_sentence_count >= THREADS_COPY_MAX_SENTENCES:
                break
            paragraph_candidate = " ".join([*selected_sentences, sentence])
            candidate = "\n\n".join([*selected_paragraphs, paragraph_candidate])
            if len(candidate) > THREADS_COPY_MAX_CHARS:
                break
            selected_sentences.append(sentence)
            selected_sentence_count += 1
        if selected_sentences:
            selected_paragraphs.append(" ".join(selected_sentences))
        if selected_sentence_count >= THREADS_COPY_MAX_SENTENCES:
            break

    if selected_paragraphs:
        return "\n\n".join(selected_paragraphs)
    if len(compact) <= THREADS_COPY_MAX_CHARS:
        return compact

    cutoff = compact.rfind(" ", 0, THREADS_COPY_MAX_CHARS)
    if cutoff < THREADS_COPY_MAX_CHARS // 2:
        cutoff = THREADS_COPY_MAX_CHARS - 1
    return compact[:cutoff].rstrip(" ,.;:!?…") + "…"


def _casualize_generated_post(text: str) -> str:
    sentence_end = r"(?=[.!?…]|$)"
    replacements = (
        (r"있습니다" + sentence_end, "있어"),
        (r"없습니다" + sentence_end, "없어"),
        (r"입니다" + sentence_end, "이야"),
        (r"합니다" + sentence_end, "해"),
        (r"됩니다" + sentence_end, "돼"),
        (r"주세요" + sentence_end, "줘"),
        (r"보세요" + sentence_end, "봐"),
        (r"하세요" + sentence_end, "해"),
        (r"있어요" + sentence_end, "있어"),
        (r"없어요" + sentence_end, "없어"),
        (r"이에요" + sentence_end, "이야"),
        (r"예요" + sentence_end, "야"),
        (r"거든요" + sentence_end, "거든"),
        (r"해요" + sentence_end, "해"),
        (r"돼요" + sentence_end, "돼"),
        (r"봐요" + sentence_end, "봐"),
        (r"여요" + sentence_end, "여"),
        (r"어요" + sentence_end, "어"),
        (r"아요" + sentence_end, "아"),
        (r"나요" + sentence_end, "나"),
        (r"까요" + sentence_end, "까"),
        (r"네요" + sentence_end, "네"),
        (r"군요" + sentence_end, "군"),
        (r"죠" + sentence_end, "지"),
        (r"([가-힣]+)습니다" + sentence_end, r"\1다"),
    )
    casual = text
    for pattern, replacement in replacements:
        casual = re.sub(pattern, replacement, casual)
    return casual


def _should_drop_generated_line(line: str) -> bool:
    clean_line = line.strip()
    if clean_line.startswith("#"):
        return True
    if "댓글" in clean_line and any(term in clean_line for term in ("남겨", "남길", "확인", "링크", "자세한")):
        return True
    if any(term in clean_line for term in ("구매 전", "확인해보세요", "추천", "비교해볼 만", "필요한 분")):
        return True
    return False


def _style_direction(style: str, custom_instruction: str = "") -> tuple[str, str]:
    if style == "custom":
        direction = custom_instruction.strip()
        if not direction:
            direction = "사용자가 지정한 말투로 짧고 자연스럽게 호기심을 유발하기."
        return "커스텀", direction
    return THREAD_STYLE_DIRECTIONS.get(style, THREAD_STYLE_DIRECTIONS["relatable_problem"])

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .writer import DISCLOSURE

DEFAULT_CODEX_MODEL = "gpt-5.5"


class CodexThreadsError(RuntimeError):
    pass


def generate_codex_threads_post(
    *,
    product_name: str,
    product_url: str,
    product_facts: list[str] | None = None,
    memo: str = "",
    persona: str = "",
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

    try:
        subprocess.run(
            command,
            input=_build_codex_prompt(
                product_name=product_name,
                product_url=product_url,
                product_facts=product_facts or [],
                memo=memo,
                persona=persona,
            ),
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
    return _normalize_generated_post(text, product_url)


def _build_codex_prompt(
    *,
    product_name: str,
    product_url: str,
    product_facts: list[str],
    memo: str,
    persona: str,
) -> str:
    facts = "\n".join(f"- {fact}" for fact in product_facts if fact.strip()) or "- 자동 수집된 상세 정보 없음"
    persona_line = persona.strip() or "친근하고 실사용 관점이 있는 한국어 Threads 작성자"
    return "\n".join(
        [
            "Codex CLI에 로그인된 계정 인증을 사용해 쿠팡 파트너스 Threads 게시글을 작성해줘.",
            "최종 답변에는 게시글 본문만 출력해. 설명, 마크다운 코드블록, 주석은 쓰지 마.",
            "",
            "스타일:",
            "- 이전 채팅방에서 링크를 주면 자연스럽게 써주던 느낌으로 작성",
            "- 사람이 직접 골라보는 듯한 짧은 문단",
            "- 광고 티가 과하게 나지 않는 말투",
            f"- 작성자 톤: {persona_line}",
            "",
            "반드시 지킬 것:",
            "- 링크와 고지 문구는 본문에 쓰지 마. 링크와 고지는 별도 댓글에 들어간다.",
            "- '자세한 건 댓글에 남겨둘게요' 같은 댓글 안내 문장 쓰지 않기",
            "- 해시태그 쓰지 않기",
            "- 가격, 할인율, 배송일, 재고, 리뷰 수는 쓰지 않기",
            "- 입력에 없는 효과, 인증, 성능, 호환 모델은 지어내지 않기",
            "- bullet 목록 금지",
            "- 사람들이 해당 상품이 뭔지 궁금해지게 작성하기",
            "- 350자 이내",
            "- 상품명은 필요하면 자연스럽게 한 번만 언급하기",
            "- 사용 장면, 궁금증 유도, 구매 전 확인 포인트 포함",
            "",
            f"상품명: {product_name.strip() or '상품명 자동 확인 필요'}",
            f"쿠팡 URL: {product_url.strip()}",
            "상품 정보:",
            facts,
            f"사용자 메모: {memo.strip() or '없음'}",
        ]
    )


def _normalize_generated_post(text: str, product_url: str) -> str:
    clean_text = text.strip().strip("`")
    clean_url = product_url.strip()
    if DISCLOSURE in clean_text:
        clean_text = clean_text.replace(DISCLOSURE, "")
    if clean_url:
        clean_text = clean_text.replace(clean_url, "")
    clean_text = clean_text.replace("#쿠팡파트너스", "")
    clean_text = "\n".join(
        line.rstrip()
        for line in clean_text.splitlines()
        if not _should_drop_generated_line(line)
    )
    return clean_text.strip()


def _should_drop_generated_line(line: str) -> bool:
    clean_line = line.strip()
    if clean_line.startswith("#"):
        return True
    if "댓글" in clean_line and any(term in clean_line for term in ("남겨", "남길", "확인", "링크", "자세한")):
        return True
    return False

from __future__ import annotations

import base64
from dataclasses import dataclass
import shutil
import subprocess
import tempfile
from pathlib import Path

from .codex_threads import DEFAULT_CODEX_MODEL

MAX_UPLOAD_IMAGE_BYTES = 650 * 1024


class CodexImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeneratedHookImage:
    image_base64: str
    content_type: str
    filename: str


def generate_codex_hook_image_base64(
    *,
    product_name: str,
    product_url: str = "",
    product_facts: list[str] | tuple[str, ...] = (),
    model: str = DEFAULT_CODEX_MODEL,
    variant: int = 0,
    timeout: float = 180.0,
) -> str:
    return generate_codex_hook_image(
        product_name=product_name,
        product_url=product_url,
        product_facts=product_facts,
        model=model,
        variant=variant,
        timeout=timeout,
    ).image_base64


def generate_codex_hook_image(
    *,
    product_name: str,
    product_url: str = "",
    product_facts: list[str] | tuple[str, ...] = (),
    model: str = DEFAULT_CODEX_MODEL,
    variant: int = 0,
    timeout: float = 180.0,
) -> GeneratedHookImage:
    if shutil.which("codex") is None:
        raise CodexImageError("Codex CLI is not installed")

    temp_dir = Path(tempfile.mkdtemp(prefix="threads-codex-image-"))
    output_path = temp_dir / "codex-image-result.txt"
    image_path = temp_dir / "output.png"
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(temp_dir),
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
            input=_build_codex_image_prompt(
                product_name=product_name,
                product_url=product_url,
                product_facts=list(product_facts),
                variant=max(0, int(variant)),
            ),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=True,
            cwd=str(temp_dir),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise CodexImageError(detail or str(exc)) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexImageError(str(exc)) from exc

    if not image_path.exists():
        detail = _read_text(output_path)
        suffix = f": {detail}" if detail else ""
        raise CodexImageError(f"Codex image generation did not create output.png{suffix}")
    image_bytes = image_path.read_bytes()
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise CodexImageError("Codex image generation output.png is not a PNG")
    return _prepare_threads_upload_image(image_path, image_bytes)


def _build_codex_image_prompt(
    *,
    product_name: str,
    product_url: str,
    product_facts: list[str],
    variant: int,
) -> str:
    facts = "\n".join(f"- {fact}" for fact in product_facts if fact.strip()) or "- 자동 수집된 상세 정보 없음"
    return "\n".join(
        [
            "Use the image generation tool to create one Threads hook image.",
            "Save the generated bitmap as output.png in the current directory.",
            "Do not draw the image with code. Do not use stock image search. Use image generation.",
            "",
            "Goal:",
            "- 상품명을 보고 카테고리와 사용 상황을 추론한다.",
            "- 상품 카테고리를 자연스럽게 사용하는 장면을 만든다.",
            "- photorealistic, candid lifestyle photo, natural light, real-world texture.",
            "- 1:1 square composition suitable for Threads preview.",
            "",
            "Must avoid:",
            "- 실제 쿠팡 상품 이미지, 포장, 박스, 쇼핑앱 화면",
            "- 브랜드명, 로고, readable text, 가격표, 워터마크",
            "- 제품을 광고처럼 정면 배치한 카탈로그 컷",
            "- 과장된 만화/일러스트/3D 렌더 스타일",
            "- 입력에 없는 효능이나 성능을 암시하는 장면",
            "",
            "Creative direction:",
            "- 사람이나 생활 공간 중심의 자연스러운 사용 장면",
            "- 상품 자체가 특정 브랜드처럼 보이지 않게 일반적인 카테고리 소품으로만 표현",
            "- 사용자가 '이 상황 뭐지?' 하고 댓글을 열어보고 싶을 정도의 생활감",
            "- 안전하고 일상적인 장면",
            f"- variation seed: {variant}",
            "",
            f"상품명: {product_name.strip() or '상품명 자동 확인 필요'}",
            f"상품 URL: {product_url.strip()}",
            "상품 정보:",
            facts,
        ]
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _prepare_threads_upload_image(image_path: Path, image_bytes: bytes) -> GeneratedHookImage:
    if shutil.which("sips") is None:
        if len(image_bytes) > MAX_UPLOAD_IMAGE_BYTES:
            raise CodexImageError(
                "Codex generated image is too large for the Threads service upload and sips is not available to compress it"
            )
        return GeneratedHookImage(
            image_base64=base64.b64encode(image_bytes).decode("ascii"),
            content_type="image/png",
            filename="threads-auto-hook-image.png",
        )
    converted_path = image_path.with_name("threads-auto-hook-image.jpg")
    for max_dimension, quality in [(1024, 82), (900, 76), (768, 70)]:
        _convert_with_sips(image_path, converted_path, max_dimension=max_dimension, quality=quality)
        converted_bytes = converted_path.read_bytes()
        if len(converted_bytes) <= MAX_UPLOAD_IMAGE_BYTES or (max_dimension, quality) == (768, 70):
            if not converted_bytes.startswith(b"\xff\xd8\xff"):
                raise CodexImageError("Compressed Codex image is not a JPEG")
            if len(converted_bytes) > MAX_UPLOAD_IMAGE_BYTES:
                raise CodexImageError("Compressed Codex image is still too large for the Threads service upload")
            return GeneratedHookImage(
                image_base64=base64.b64encode(converted_bytes).decode("ascii"),
                content_type="image/jpeg",
                filename="threads-auto-hook-image.jpg",
            )
    raise CodexImageError("Codex image could not be prepared for upload")


def _convert_with_sips(image_path: Path, output_path: Path, *, max_dimension: int, quality: int) -> None:
    try:
        subprocess.run(
            [
                "sips",
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                str(quality),
                "-Z",
                str(max_dimension),
                str(image_path),
                "--out",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            timeout=30.0,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise CodexImageError(f"Codex image compression failed: {detail or exc}") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexImageError(f"Codex image compression failed: {exc}") from exc

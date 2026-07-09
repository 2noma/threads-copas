from __future__ import annotations

import base64
from dataclasses import dataclass
import shutil
import subprocess
import tempfile
from pathlib import Path

from .codex_threads import DEFAULT_CODEX_MODEL

MAX_UPLOAD_IMAGE_BYTES = 650 * 1024
AI_ILLUSTRATION_LABEL = "AI 일러스트"
DEFAULT_CODEX_IMAGE_TIMEOUT = 480.0


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
    prompt: str = "",
    timeout: float = DEFAULT_CODEX_IMAGE_TIMEOUT,
) -> str:
    return generate_codex_hook_image(
        product_name=product_name,
        product_url=product_url,
        product_facts=product_facts,
        model=model,
        variant=variant,
        prompt=prompt,
        timeout=timeout,
    ).image_base64


def generate_codex_hook_image(
    *,
    product_name: str,
    product_url: str = "",
    product_facts: list[str] | tuple[str, ...] = (),
    model: str = DEFAULT_CODEX_MODEL,
    variant: int = 0,
    prompt: str = "",
    timeout: float = DEFAULT_CODEX_IMAGE_TIMEOUT,
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
            input=prompt.strip()
            or _build_codex_image_prompt(
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
    labeled_image_path = _add_ai_illustration_label(image_path)
    return _prepare_threads_upload_image(labeled_image_path, labeled_image_path.read_bytes())


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
            "- AI 일러스트임이 분명한 non-photorealistic hook image를 만든다.",
            "- fictional stylized characters only. 실제 인물처럼 보이지 않게 만든다.",
            "- 1:1 square composition suitable for Threads preview.",
            "",
            "Must avoid:",
            "- 실제 쿠팡 상품 이미지, 포장, 박스, 쇼핑앱 화면",
            "- 브랜드명, 로고, readable text, 가격표, 워터마크",
            "- 제품을 광고처럼 정면 배치한 카탈로그 컷",
            "- 실사, 사진, 실제 인플루언서/사용 후기처럼 보이는 연출",
            "- 입력에 없는 효능이나 성능을 암시하는 장면",
            "- No text in the image. 앱이 업로드 전에 AI 일러스트 라벨을 직접 추가한다.",
            "",
            "Creative direction:",
            "- 현대적인 에디토리얼 일러스트, semi-flat digital painting, soft shading",
            "- 사람이나 생활 공간 중심의 자연스러운 사용 장면",
            "- 상품 자체가 특정 브랜드처럼 보이지 않게 일반적인 카테고리 소품으로만 표현",
            "- 사용자가 '이 상황 뭐지?' 하고 댓글을 열어보고 싶을 정도의 생활감",
            "- 안전하고 일상적인 장면, 과장되더라도 성능 주장처럼 보이지 않게",
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


def _add_ai_illustration_label(image_path: Path) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise CodexImageError("Pillow is required to add the AI illustration label") from exc

    labeled_path = image_path.with_name("threads-ai-illustration-labeled.png")
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    font_size = max(24, min(width, height) // 36)
    font = _load_label_font(font_size, ImageFont)
    label = AI_ILLUSTRATION_LABEL
    bbox = draw.textbbox((0, 0), label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    pad_x = max(14, font_size // 2)
    pad_y = max(8, font_size // 3)
    x = max(18, width // 42)
    y = max(18, height // 42)
    rect = [x, y, x + text_width + pad_x * 2, y + text_height + pad_y * 2]
    radius = max(10, font_size // 2)
    draw.rounded_rectangle(rect, radius=radius, fill=(255, 255, 255), outline=(28, 31, 35), width=3)
    draw.text((x + pad_x, y + pad_y - max(1, font_size // 12)), label, fill=(28, 31, 35), font=font)
    image.save(labeled_path, format="PNG")
    return labeled_path


def _load_label_font(font_size: int, image_font_module):
    font_paths = (
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for font_path in font_paths:
        if not Path(font_path).exists():
            continue
        try:
            return image_font_module.truetype(font_path, font_size)
        except OSError:
            continue
    return image_font_module.load_default()


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

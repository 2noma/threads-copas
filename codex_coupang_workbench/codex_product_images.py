from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class CodexProductImageError(RuntimeError):
    pass


def normalize_image_analysis(value: Any) -> list[str]:
    if not isinstance(value, dict) or not isinstance(value.get("facts"), list):
        raise CodexProductImageError("상품 이미지 분석 결과 형식이 올바르지 않습니다.")
    facts: list[str] = []
    for raw in value["facts"]:
        if not isinstance(raw, str):
            continue
        clean = " ".join(raw.split()).strip()[:200]
        if clean and clean not in facts:
            facts.append(clean)
        if len(facts) == 8:
            break
    if not facts:
        raise CodexProductImageError("상세 이미지에서 확인 가능한 상품 특징을 찾지 못했습니다.")
    return facts


def analyze_detail_images(product_name: str, image_urls: list[str], timeout: float = 90.0) -> list[str]:
    if shutil.which("codex") is None:
        raise CodexProductImageError("Codex CLI를 찾을 수 없습니다.")
    urls = [url.strip() for url in image_urls if _safe_image_url(url)][:5]
    if not urls:
        raise CodexProductImageError("분석할 쿠팡 상세 이미지를 찾지 못했습니다.")
    with tempfile.TemporaryDirectory(prefix="coupang-detail-images-") as raw_dir:
        root = Path(raw_dir)
        paths = [_download_image(url, root / f"detail-{index}.jpg") for index, url in enumerate(urls, 1)]
        output = root / "analysis.json"
        prompt = """첨부된 쿠팡 상품 상세 이미지만 보고 상품 특징을 한국어 JSON으로 반환해.
보이지 않는 성능·효능·가격·후기·호환성은 추측하지 마.
형식: {\"facts\":[\"이미지에서 실제로 확인되는 특징\"]}. facts는 1~8개, 짧고 구체적으로."""
        command = ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message", str(output)]
        for path in paths:
            command.append(f"--image={path}")
        command.append("-")
        try:
            subprocess.run(command, input=prompt, text=True, capture_output=True, check=True, timeout=timeout, cwd=root)
            return normalize_image_analysis(json.loads(output.read_text(encoding="utf-8")))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise CodexProductImageError("쿠팡 상세 이미지 분석에 실패했습니다.") from exc


def _safe_image_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def _download_image(url: str, destination: Path) -> Path:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=15) as response:
        content = response.read(8 * 1024 * 1024 + 1)
    if len(content) < 4 or len(content) > 8 * 1024 * 1024:
        raise CodexProductImageError("쿠팡 상세 이미지 크기가 올바르지 않습니다.")
    destination.write_bytes(content)
    return destination

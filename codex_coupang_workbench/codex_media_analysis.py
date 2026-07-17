from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class CodexMediaAnalysisError(RuntimeError):
    pass


def normalize_media_analysis(value: Any) -> list[str]:
    if not isinstance(value, dict) or not isinstance(value.get("facts"), list):
        raise CodexMediaAnalysisError("선택 미디어 분석 결과 형식이 올바르지 않습니다.")
    facts: list[str] = []
    for raw in value["facts"]:
        if not isinstance(raw, str):
            continue
        clean = " ".join(raw.split()).strip()[:180]
        fact = f"선택 미디어 화면: {clean}"
        if clean and fact not in facts:
            facts.append(fact)
        if len(facts) == 6:
            break
    if not facts:
        raise CodexMediaAnalysisError("선택 미디어에서 확인 가능한 장면을 찾지 못했습니다.")
    return facts


def analyze_selected_frames(
    image_paths: list[Path],
    *,
    timeout: float = 90.0,
) -> list[str]:
    if shutil.which("codex") is None:
        raise CodexMediaAnalysisError("Codex CLI를 찾을 수 없습니다.")
    paths: list[Path] = []
    for raw_path in image_paths[:3]:
        path = Path(raw_path)
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            raise CodexMediaAnalysisError("선택 미디어 분석에는 JPG 대표 장면만 사용할 수 있습니다.")
        if not path.is_file():
            raise CodexMediaAnalysisError("선택한 대표 장면 파일을 찾을 수 없습니다.")
        paths.append(path)
    if not paths:
        raise CodexMediaAnalysisError("분석할 JPG 대표 장면이 없습니다.")

    with tempfile.TemporaryDirectory(prefix="threads-media-analysis-") as raw_dir:
        output_path = Path(raw_dir) / "analysis.json"
        prompt = """첨부된 상품 영상의 대표 장면만 보고 Threads 문구에 사용할 수 있는 화면 사실을 한국어 JSON으로 반환해.
보이지 않는 효능, 성능, 가격, 브랜드, 사용 후기, 사람의 감정은 추측하지 마.
장면에서 실제로 보이는 동작, 변화, 배치, 모양, 사용 순간만 짧고 구체적으로 적어.
형식: {\"facts\":[\"화면에서 실제로 확인되는 장면\"]}. facts는 1~6개."""
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(output_path),
        ]
        command.extend(f"--image={path}" for path in paths)
        command.append("-")
        try:
            subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=True,
                timeout=timeout,
                cwd=raw_dir,
            )
            return normalize_media_analysis(
                json.loads(output_path.read_text(encoding="utf-8"))
            )
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise CodexMediaAnalysisError("선택 미디어 장면 분석에 실패했습니다.") from exc

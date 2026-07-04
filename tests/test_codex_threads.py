from codex_coupang_workbench.codex_threads import generate_codex_threads_post


def test_generate_codex_threads_post_uses_codex_exec_auth_and_reads_last_message(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, input, text, capture_output, timeout, check, cwd):
        calls.append(
            {
                "command": command,
                "input": input,
                "cwd": cwd,
                "timeout": timeout,
            }
        )
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(
                "왜 콘솔 정리는 차를 타고 나서야 신경 쓰이기 시작할까요?\n\n"
                "작은 소지품이 자꾸 굴러다닌다면 테슬라 수납함을 한 번 볼 만합니다.\n\n"
                "#테슬라용품"
            )
        return type("Completed", (), {"stdout": "", "stderr": "", "returncode": 0})()

    monkeypatch.setattr("codex_coupang_workbench.codex_threads.subprocess.run", fake_run)
    monkeypatch.setattr("codex_coupang_workbench.codex_threads.tempfile.mkdtemp", lambda prefix: str(tmp_path))

    text = generate_codex_threads_post(
        model="gpt-5.5",
        product_name="테슬라 센터 콘솔 수납함",
        product_url="https://link.coupang.com/a/example",
        product_facts=["모델Y 주니퍼 호환", "센터 콘솔 수납 트레이"],
    )

    assert "테슬라 수납함" in text
    assert "https://link.coupang.com/a/example" not in text
    assert "쿠팡 파트너스" not in text
    command = calls[0]["command"]
    assert command[:2] == ["codex", "exec"]
    assert "--ephemeral" in command
    assert "--skip-git-repo-check" in command
    assert "--output-last-message" in command
    assert command[command.index("--model") + 1] == "gpt-5.5"
    assert "Codex CLI에 로그인된 계정 인증" in calls[0]["input"]
    assert "링크와 고지 문구는 본문에 쓰지 마" in calls[0]["input"]
    assert "모델Y 주니퍼 호환" in calls[0]["input"]

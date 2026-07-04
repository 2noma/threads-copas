# Threads Coupang Publisher

쿠팡 파트너스 링크를 Threads 글로 만들고, 선택한 Threads 프로필에 발행한 뒤 발행 기록을 로컬에 저장하는 웹서비스입니다.

## 바로가기

- 사용 문서: [docs/threads-publisher-guide.md](docs/threads-publisher-guide.md)
- 로컬 주소: `http://127.0.0.1:8765`
- Redirect URI: `http://127.0.0.1:8765/api/threads/auth/callback`

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행

```bash
uvicorn codex_coupang_workbench.main:app --reload --port 8765
```

브라우저에서 엽니다.

```text
http://127.0.0.1:8765
```

## 현재 기능

- Threads App ID, App Secret, Redirect URI 저장
- Threads 프로필 슬롯 추가
- 프로필별 OAuth 연결 및 토큰 저장
- 쿠팡 URL만 입력해서 Threads 글 생성
- 사용자가 미리보기 글을 확인/수정
- `Publish to Threads` 버튼으로 직접 발행
- 발행한 상품, 쿠팡 URL, 발행 프로필, Threads post ID, 발행 시각 저장

## 테스트

```bash
pytest tests -v
```

## 데이터 저장 위치

로컬 SQLite에 저장됩니다.

```text
workbench_data/workbench.sqlite3
```

토큰과 App Secret도 이 로컬 DB에 저장됩니다. 외부에 공유하거나 커밋하지 마세요.


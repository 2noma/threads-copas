# Threads Coupang Publisher

쿠팡 파트너스 링크를 Threads 본문과 댓글로 나눠 만들고, 선택한 Threads 프로필에 발행한 뒤 발행 기록을 로컬에 저장하는 웹서비스입니다.

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

Threads 글 생성은 별도 OpenAI API Key를 저장하지 않고 현재 머신의 Codex CLI 로그인 인증을 사용합니다.

```bash
codex login
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
- 쿠팡 URL만 입력해서 Threads 본문과 댓글 생성
- 쿠팡 상품 조회용 프록시 URL을 저장해 쿠팡 리다이렉트/상품 페이지 조회만 프록시 경유
- 본문은 상품이 궁금해지도록 작성하고, 댓글에는 쿠팡 파트너스 고지와 링크를 자동 배치
- 사용자가 본문/댓글 미리보기를 확인하고 수정
- `Publish to Threads` 버튼으로 본문 발행 후 댓글을 이어서 발행
- 발행한 상품, 쿠팡 URL, 발행 프로필, Threads post ID, reply ID, 발행 시각 저장

본문 예시:

```text
테슬라 타다 보면 센터 콘솔 안이 은근 금방 섞이더라구요.

케이블, 카드, 작은 소품이 굴러다니는 게 신경 쓰였다면 이런 수납함은 한 번쯤 볼 만해요.

#테슬라 #차량용품 #센터콘솔
```

댓글 예시:

```text
이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.

https://link.coupang.com/a/example
```

## 테스트

```bash
pytest tests -v
```

## 데이터 저장 위치

로컬 SQLite에 저장됩니다.

```text
workbench_data/workbench.sqlite3
```

토큰과 App Secret도 이 로컬 DB에 저장됩니다. `workbench_data/`, `.env`, SQLite DB, 로그 파일은 `.gitignore`에 포함되어 있으니 외부에 공유하거나 커밋하지 마세요.

## 쿠팡 조회용 프록시

서버 IP에서 쿠팡 상품 페이지가 차단될 때는 Settings의 `Coupang Proxy URL`에 HTTP/HTTPS 프록시를 저장합니다.

```text
http://user:password@proxy-host:port
```

이 값은 쿠팡 단축 링크 리다이렉트와 상품 페이지 조회에만 사용됩니다. Threads/Meta API와 쿠팡 파트너스 API 호출은 기존 경로를 유지합니다. 프록시 URL은 계정 정보가 포함될 수 있어 화면/API 응답에서는 `********`로 마스킹됩니다.

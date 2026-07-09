# Threads Coupang Publisher

로컬 화면에서 쿠팡 파트너스 링크를 Threads 본문과 댓글로 만들고, AWS의 Threads API 서버를 통해 선택한 Threads 프로필에 발행하는 웹서비스입니다.

## 바로가기

- 사용 문서: [docs/threads-publisher-guide.md](docs/threads-publisher-guide.md)
- 로컬 주소: `http://127.0.0.1:8765`
- AWS Threads API 서버: `uvicorn codex_coupang_workbench.threads_api:app --host 0.0.0.0 --port 8765`
- Meta Redirect URI: `https://sinabro-ai.com/threads-copas/api/threads/auth/callback`

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Threads 글 생성과 후킹 이미지 생성은 현재 머신의 Codex CLI 로그인 인증을 사용합니다.

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

- AWS 전용 Threads API 서버와 로컬 화면 분리
- AWS 서버는 env로 Threads App ID, App Secret, Redirect URI를 읽음
- 로컬 화면에서 AWS Threads API 서버로 OAuth/발행 위임
- `Import Current Account`로 Threads 프로필 연결
- 프로필별 OAuth 토큰 저장
- 쿠팡 URL만 입력해서 Threads 본문과 댓글 생성
- 쿠팡 상세가 서버 요청에서 막히면 `Chrome 확인`으로 로컬 Google Chrome 세션에서 상품명을 읽어옴
- 본문은 상품이 궁금해지도록 작성하고, 댓글에는 쿠팡 파트너스 고지와 링크를 자동 배치
- 사용자가 본문/댓글 미리보기를 확인하고 수정
- 상품 이미지는 Threads 게시 이미지로 기본 사용하지 않음
- AI로 실제 상품처럼 보이는 이미지는 기본 제외
- `Generate Thread` 한 번으로 Codex CLI가 상품 카테고리를 자연스럽게 사용하는 AI 일러스트 후킹 PNG를 자동 생성
- 자동 생성 이미지에는 업로드 전 `AI 일러스트` 라벨을 합성
- 자동 생성 이미지는 업로드 전에 JPEG로 압축한 뒤 AWS에 업로드해 Meta가 접근 가능한 public HTTPS 이미지 URL로 변환
- `이미지 다시 만들기`로 같은 상품의 다른 일러스트 구도를 재생성
- 직접 만든 이미지 Base64를 넣으면 자동 생성 대신 그 이미지를 업로드
- `이미지 없이 글만 만들기`를 켜면 Codex 이미지 생성과 이미지 발행을 모두 건너뜀
- 후킹 이미지는 상품, 브랜드, 로고, 포장, readable text가 보이지 않는 이미지로만 사용
- 후킹 이미지 URL은 발행 전 미리보기로 확인 가능
- `Publish to Threads` 버튼으로 본문 발행 후 댓글을 이어서 발행
- 발행한 상품, 쿠팡 URL, 발행 프로필, Threads post ID, reply ID, 발행 시각 저장
- `Publish Records`에서 Threads 조회수, 좋아요, 댓글, 리포스트, 인용, 공유 지표 새로고침

본문 예시:

```text
테슬라 타다 보면 센터 콘솔 안이 은근 금방 섞이더라구요.

케이블, 카드, 작은 소품이 굴러다니는 게 신경 쓰였다면 이런 수납함은 한 번쯤 볼 만해요.
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

로컬 화면에서 만든 상품/초안 데이터는 로컬 SQLite에 저장됩니다.

```text
workbench_data/workbench.sqlite3
```

AWS Threads API 서버의 Threads 토큰과 발행 기록은 AWS SQLite에 저장됩니다.

```text
workbench_data/threads_api.sqlite3
```

`workbench_data/`, `.env`, SQLite DB, 로그 파일은 `.gitignore`에 포함되어 있으니 외부에 공유하거나 커밋하지 마세요.

## 로컬 화면 + AWS Threads API 분리 운영

AWS는 Threads OAuth callback, 토큰 저장, Threads 발행만 담당하고 로컬은 화면, 쿠팡 상품 조회, 글 생성을 담당합니다.

```text
로컬 화면/API
→ 쿠팡 상품 정보 조회
→ Threads 초안 생성
→ AWS Threads 서비스에 발행 요청
→ AWS가 Threads API로 게시
```

AWS에는 전용 API 서버만 실행합니다. 화면, Settings API, 쿠팡 조회 API, 초안 생성 API는 노출하지 않습니다.

```bash
export THREADS_BRIDGE_API_KEY="긴_랜덤_문자열"
export THREADS_APP_ID="Meta 앱 ID"
export THREADS_APP_SECRET="Meta 앱 시크릿"
export THREADS_REDIRECT_URI="https://sinabro-ai.com/threads-copas/api/threads/auth/callback"
export THREADS_PUBLIC_BASE_URL="https://sinabro-ai.com/threads-copas"
uvicorn codex_coupang_workbench.threads_api:app --host 0.0.0.0 --port 8765
```

systemd로 실행한다면 서비스 파일에 아래 줄을 추가합니다.

```ini
Environment="THREADS_BRIDGE_API_KEY=긴_랜덤_문자열"
Environment="THREADS_APP_ID=Meta 앱 ID"
Environment="THREADS_APP_SECRET=Meta 앱 시크릿"
Environment="THREADS_REDIRECT_URI=https://sinabro-ai.com/threads-copas/api/threads/auth/callback"
Environment="THREADS_PUBLIC_BASE_URL=https://sinabro-ai.com/threads-copas"
```

AWS API 서버에서 열리는 엔드포인트는 Threads 브리지 API만입니다.

```text
GET  /api/health
GET  /api/threads/profiles
POST /api/threads/profiles
GET  /api/threads/auth/start
GET  /api/threads/auth/import/start
GET  /api/threads/auth/callback
GET  /api/threads/publish-records
POST /api/threads/media
POST /api/threads/remote-publish
POST /api/threads/profiles/{profile_key}/refresh
POST /api/threads/profiles/{profile_key}/disconnect
POST /api/threads/publish-records/{job_id}/insights
GET  /media/{filename}
```

Threads 지표 조회에는 Meta 앱 OAuth scope에 `threads_manage_insights`가 필요합니다. 기존에 연결한 프로필은 scope 추가 후 `Import Current Account`로 다시 연결해야 지표 새로고침이 성공합니다.

로컬 화면은 기존 앱을 실행합니다.

```bash
uvicorn codex_coupang_workbench.main:app --reload --port 8765
```

로컬 Settings에는 아래 값만 저장합니다.

```text
Threads Service URL = https://sinabro-ai.com/threads-copas
Threads Service API Key = AWS의 THREADS_BRIDGE_API_KEY 값
Coupang Access Key = 쿠팡 파트너스 Access Key
Coupang Secret Key = 쿠팡 파트너스 Secret Key
Codex Model = gpt-5.5
```

이 모드에서는 로컬의 `Import Current Account`, 프로필 목록, 발행 버튼, 발행 기록 API가 AWS Threads 서비스로 위임됩니다. 쿠팡 상품 확인과 초안 생성은 로컬에서 실행됩니다.

쿠팡 상세 페이지가 `Access Denied`로 막혀 상품명이 비어 있으면 `Chrome 확인`을 누릅니다. 이 기능은 macOS의 로컬 Google Chrome을 열어 현재 Chrome 프로필의 쿠팡 세션으로 상품명만 읽어오며, 처음 실행 시 macOS가 터미널 또는 Python의 Chrome 제어 권한을 물을 수 있습니다.

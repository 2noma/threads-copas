# Threads Coupang Publisher 사용 문서

## 목적

이 웹서비스는 로컬 화면에서 쿠팡 파트너스 링크를 Threads용 글로 만들고, AWS의 Threads API 서버를 통해 선택한 Threads 프로필에 발행한 뒤 기록을 남기는 도구입니다.

기본 흐름은 단순합니다.

```text
로컬 Settings 저장
→ Threads 계정 가져오기
→ 쿠팡 URL 입력
→ 글 생성
→ 본문과 댓글 확인/수정
→ 발행 버튼 클릭
→ 발행 기록 저장
```

## 필요한 것

1. Meta Developers 계정
2. Threads API를 사용하는 Meta 앱
3. Threads App ID
4. Threads App Secret
5. Redirect URI
6. 발행할 Threads 계정
7. Codex CLI 로그인

Meta 앱 설정의 OAuth Redirect URI에는 AWS API 서버 주소를 등록합니다.

```text
https://sinabro-ai.com/threads-copas/api/threads/auth/callback
```

## 서버 실행

AWS 인스턴스에서는 Threads API 서버만 실행합니다. 이 서버는 화면을 제공하지 않고 env 값만 사용합니다.

```bash
export THREADS_BRIDGE_API_KEY="긴_랜덤_문자열"
export THREADS_APP_ID="Meta 앱 ID"
export THREADS_APP_SECRET="Meta 앱 시크릿"
export THREADS_REDIRECT_URI="https://sinabro-ai.com/threads-copas/api/threads/auth/callback"
export THREADS_PUBLIC_BASE_URL="https://sinabro-ai.com/threads-copas"
uvicorn codex_coupang_workbench.threads_api:app --host 0.0.0.0 --port 8765
```

로컬에서는 화면과 쿠팡 조회/초안 생성을 담당하는 앱을 실행합니다.

```bash
uvicorn codex_coupang_workbench.main:app --reload --port 8765
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:8765
```

## 1. 로컬 Settings 저장

로컬 화면의 `API Settings` 영역에 입력합니다.

- `Threads Service URL`: AWS Threads API 서버 주소
- `Threads Service API Key`: AWS의 `THREADS_BRIDGE_API_KEY`와 같은 값
- `Coupang Access Key`: 쿠팡 파트너스 Access Key
- `Coupang Secret Key`: 쿠팡 파트너스 Secret Key
- `Coupang Sub ID`: 필요한 경우 입력
- `Codex Model`: 기본값은 `gpt-5.5`

입력 후 `Save Settings`를 누릅니다.

Threads 글 생성은 별도 OpenAI API Key를 저장하지 않고 현재 머신에 로그인된 Codex CLI 인증을 사용합니다. Codex 로그인이 필요하면 터미널에서 `codex login`을 먼저 실행합니다.

## 로컬 화면 + AWS Threads API 분리 운영

이 방식에서는 로컬 서비스가 화면, 쿠팡 URL 조회, Threads 글 생성을 맡고, AWS 서비스가 Meta OAuth callback, Threads 토큰 저장, 실제 Threads 발행을 맡습니다.

```text
로컬 서비스
→ 쿠팡 URL 조회
→ Threads 본문/댓글 생성
→ AWS Threads 서비스에 발행 요청
→ AWS가 Threads API로 게시
```

AWS 서버에는 아래 환경변수를 넣고 `codex_coupang_workbench.threads_api:app`만 실행합니다.

```bash
export THREADS_BRIDGE_API_KEY="긴_랜덤_문자열"
export THREADS_APP_ID="Meta 앱 ID"
export THREADS_APP_SECRET="Meta 앱 시크릿"
export THREADS_REDIRECT_URI="https://sinabro-ai.com/threads-copas/api/threads/auth/callback"
export THREADS_PUBLIC_BASE_URL="https://sinabro-ai.com/threads-copas"
uvicorn codex_coupang_workbench.threads_api:app --host 0.0.0.0 --port 8765
```

systemd를 쓰면 서비스 파일에 아래 줄을 넣습니다.

```ini
Environment="THREADS_BRIDGE_API_KEY=긴_랜덤_문자열"
Environment="THREADS_APP_ID=Meta 앱 ID"
Environment="THREADS_APP_SECRET=Meta 앱 시크릿"
Environment="THREADS_REDIRECT_URI=https://sinabro-ai.com/threads-copas/api/threads/auth/callback"
Environment="THREADS_PUBLIC_BASE_URL=https://sinabro-ai.com/threads-copas"
```

AWS API 서버는 아래 API만 제공합니다.

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
GET  /media/{filename}
```

로컬 화면의 `API Settings`에는 아래처럼 저장합니다.

```text
Threads Service URL = https://sinabro-ai.com/threads-copas
Threads Service API Key = AWS의 THREADS_BRIDGE_API_KEY 값
Coupang Access Key = 쿠팡 파트너스 Access Key
Coupang Secret Key = 쿠팡 파트너스 Secret Key
Codex Model = gpt-5.5
```

로컬의 `Import Current Account`, 프로필 목록, 토큰 갱신, 발행 버튼, 발행 기록 조회는 AWS Threads API 서버로 위임됩니다. 쿠팡 상품 확인과 초안 생성은 로컬에서 실행됩니다.

## 2. Threads 계정 가져오기

`Profiles` 영역에서 `Import Current Account`를 누릅니다.

그러면 Meta/Threads OAuth 승인 화면이 열립니다. 발행할 Threads 계정으로 승인하면 콜백 페이지에 `Threads 연결 완료`가 표시됩니다. 이 callback은 AWS Redirect URI로 돌아와 AWS DB에 프로필과 토큰을 저장합니다.

연결이 끝나면 원래 웹서비스 화면으로 돌아와 `Refresh`를 누릅니다.

연결된 프로필은 목록에서 `connected`로 표시됩니다.

## 3. 쿠팡 URL로 글 생성

`Draft & Publish` 영역에서:

1. 발행 프로필을 선택합니다.
2. 쿠팡 URL을 붙여넣습니다.
3. 필요한 경우 Image Gen으로 만든 상황 후킹 이미지의 Base64를 `AI 후킹 이미지 Base64`에 붙여넣고 `이미지 URL 만들기`를 누릅니다.
4. `후킹 이미지 URL`에 public HTTPS URL이 자동 입력되고 `발행 이미지` 미리보기에 이미지가 표시되는지 확인합니다.
5. `Generate Thread`를 누릅니다.

상품명과 상품 정보는 URL에서 가능한 범위로 자동 확인합니다. 본문은 사람들이 상품을 궁금해하도록 짧게 작성하고, 댓글에는 쿠팡 파트너스 고지 문구와 링크가 들어갑니다.

`Generate Thread`는 Codex CLI를 비대화형으로 호출해 글을 생성합니다. Codex CLI가 없거나 로그인/호출에 실패하면 로컬 템플릿 생성으로 자동 전환됩니다.

## 이미지 운영 원칙

Threads 게시 이미지는 기본적으로 사용하지 않습니다.

- 쿠팡 상품 이미지는 게시 이미지로 자동 사용하지 않습니다.
- AI로 실제 상품처럼 보이는 이미지는 기본 제외합니다.
- 필요한 경우에만 Image Gen으로 웃기거나 이상한 상황 후킹 이미지를 만듭니다.
- 생성 이미지는 AWS Threads API 서버에 파일로 저장해 Meta가 접근 가능한 public HTTPS URL로 바꿉니다.
- Base64 업로드는 PNG, JPEG, WEBP 이미지를 지원하며 최대 8MB까지 허용합니다.
- 승인된 후킹 이미지는 `발행 이미지` 미리보기에서 실제로 확인한 뒤 발행합니다.
- 승인된 후킹 이미지가 없으면 Threads는 텍스트 본문과 댓글만 발행됩니다.

## 4. 발행 전 확인

생성된 글은 `Threads 본문 미리보기`에 표시됩니다.

댓글은 `댓글 미리보기`에 표시됩니다. 실제 발행에는 두 미리보기 칸에 남아 있는 최종 문구가 사용됩니다.

후킹 이미지가 승인된 경우 `발행 이미지` 미리보기에도 실제 게시될 이미지가 표시됩니다. 이미지가 없으면 텍스트 본문과 댓글만 발행됩니다.

## 5. 발행

글을 확인한 뒤 `Publish to Threads`를 누릅니다.

이때 로컬이 AWS에 발행 요청을 보내고, AWS가 Threads API로 본문을 먼저 게시한 뒤 같은 게시물에 댓글을 답니다. 발행이 성공하면 발행 기록이 저장됩니다.

## 6. 발행 기록 확인

`Publish Records` 영역에서 확인할 수 있습니다.

저장되는 값:

- 발행 시각
- 상품명
- 쿠팡 URL
- 발행 프로필
- Threads username
- Threads post ID
- 실제 발행 본문과 댓글 문구

발행 기록 API:

```text
GET /api/threads/publish-records
```

## 토큰 갱신

프로필 목록에서 `Refresh Token` 버튼을 누르면 해당 프로필의 long-lived token을 갱신합니다.

Threads 토큰은 만료될 수 있으므로 주기적으로 갱신해야 합니다.

## 주의사항

- 발행은 자동으로 실행되지 않습니다. 반드시 `Publish to Threads` 버튼을 눌러야 합니다.
- 쿠팡 파트너스 고지 문구와 링크는 본문이 아니라 댓글에 포함됩니다.
- 가격, 배송일, 리뷰 수처럼 자주 바뀌는 정보는 글에서 제외하도록 생성됩니다.
- Threads App Secret은 AWS 환경변수에만 둡니다.
- Threads Access Token과 발행 기록은 AWS SQLite DB에 저장됩니다.
- AWS 서버에는 반드시 `THREADS_BRIDGE_API_KEY`를 설정하고, 로컬에는 같은 값을 `Threads Service API Key`로 저장하세요.
- `workbench_data/workbench.sqlite3`, `workbench_data/threads_api.sqlite3` 파일을 외부에 공유하지 마세요.

## 로컬 데이터 위치

```text
workbench_data/workbench.sqlite3
```

서버 로그:

```text
workbench_data/server.log
```

## 문제 해결

AWS API 서버에서 `Threads API env settings are required`가 나오면:

- `THREADS_APP_ID`
- `THREADS_APP_SECRET`
- `THREADS_REDIRECT_URI`

세 환경변수가 서버 프로세스에 들어갔는지 확인합니다.

`Threads profile is not connected`가 나오면:

- `Import Current Account`를 눌러 OAuth 연결을 완료해야 합니다.

발행 후 기록이 안 보이면:

- `Refresh`를 누릅니다.
- `/api/threads/publish-records`가 정상 응답하는지 확인합니다.

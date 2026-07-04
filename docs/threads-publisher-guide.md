# Threads Coupang Publisher 사용 문서

## 목적

이 웹서비스는 쿠팡 파트너스 링크를 Threads용 글로 만들고, 선택한 Threads 프로필에 발행한 뒤 기록을 남기는 도구입니다.

기본 흐름은 단순합니다.

```text
Threads 설정 저장
→ 프로필 추가
→ 프로필 연결
→ 쿠팡 URL 입력
→ 글 생성
→ 글 확인/수정
→ 발행 버튼 클릭
→ 발행 기록 저장
```

## 필요한 것

1. Meta Developers 계정
2. Threads API를 사용하는 Meta 앱
3. Threads App ID
4. Threads App Secret
5. Redirect URI
6. 발행할 Threads 프로필

로컬에서 사용할 Redirect URI는 아래 값입니다.

```text
http://127.0.0.1:8765/api/threads/auth/callback
```

Meta 앱 설정의 OAuth Redirect URI에도 같은 값을 등록해야 합니다.

## 서버 실행

프로젝트 폴더에서 실행합니다.

```bash
uvicorn codex_coupang_workbench.main:app --reload --port 8765
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:8765
```

## 1. Threads Settings 저장

화면의 `Threads Settings` 영역에 입력합니다.

- `Threads App ID`: Meta 앱 ID
- `Threads App Secret`: Meta 앱 시크릿
- `Redirect URI`: `http://127.0.0.1:8765/api/threads/auth/callback`

입력 후 `Save Settings`를 누릅니다.

## 2. Profiles 추가

`Profiles` 영역에서 로컬 프로필 슬롯을 만듭니다.

예시:

```text
프로필 키: tesla
표시 이름: 테슬라 용품
```

```text
프로필 키: pet
표시 이름: 반려동물 용품
```

`Save Profile`을 누르면 프로필 목록에 추가됩니다.

## 3. Threads 프로필 연결

프로필 목록에서 `Connect` 버튼을 누릅니다.

그러면 Meta/Threads OAuth 승인 화면이 열립니다. 발행할 Threads 프로필로 승인하면 콜백 페이지에 `Threads 연결 완료`가 표시됩니다.

연결이 끝나면 원래 웹서비스 화면으로 돌아와 `Refresh`를 누릅니다.

연결된 프로필은 목록에서 `connected`로 표시됩니다.

## 4. 쿠팡 URL로 글 생성

`Draft & Publish` 영역에서:

1. 발행 프로필을 선택합니다.
2. 쿠팡 URL을 붙여넣습니다.
3. `Generate Thread`를 누릅니다.

상품명과 상품 정보는 URL에서 가능한 범위로 자동 확인합니다. 생성되는 글에는 쿠팡 파트너스 고지 문구가 포함됩니다.

## 5. 발행 전 확인

생성된 글은 `Threads 미리보기`에 표시됩니다.

여기에서 문구를 직접 수정할 수 있습니다. 실제 발행에는 이 미리보기 칸에 남아 있는 최종 문구가 사용됩니다.

## 6. 발행

글을 확인한 뒤 `Publish to Threads`를 누릅니다.

이때 실제 Threads API로 게시됩니다. 발행이 성공하면 발행 기록이 저장됩니다.

## 7. 발행 기록 확인

`Publish Records` 영역에서 확인할 수 있습니다.

저장되는 값:

- 발행 시각
- 상품명
- 쿠팡 URL
- 발행 프로필
- Threads username
- Threads post ID
- 실제 발행 문구

발행 기록 API:

```text
GET /api/threads/publish-records
```

## 토큰 갱신

프로필 목록에서 `Refresh Token` 버튼을 누르면 해당 프로필의 long-lived token을 갱신합니다.

Threads 토큰은 만료될 수 있으므로 주기적으로 갱신해야 합니다.

## 주의사항

- 발행은 자동으로 실행되지 않습니다. 반드시 `Publish to Threads` 버튼을 눌러야 합니다.
- 쿠팡 파트너스 고지 문구는 생성 글에 포함됩니다.
- 가격, 배송일, 리뷰 수처럼 자주 바뀌는 정보는 글에서 제외하도록 생성됩니다.
- App Secret과 Access Token은 로컬 SQLite DB에 저장됩니다.
- `workbench_data/workbench.sqlite3` 파일을 외부에 공유하지 마세요.

## 로컬 데이터 위치

```text
workbench_data/workbench.sqlite3
```

서버 로그:

```text
workbench_data/server.log
```

## 문제 해결

`Threads app settings are required`가 나오면:

- `Threads App ID`
- `Threads App Secret`
- `Redirect URI`

세 값이 저장되어 있는지 확인합니다.

`Threads profile is not connected`가 나오면:

- 프로필을 만든 뒤 `Connect`를 눌러 OAuth 연결을 완료해야 합니다.

발행 후 기록이 안 보이면:

- `Refresh`를 누릅니다.
- `/api/threads/publish-records`가 정상 응답하는지 확인합니다.


# T02 — 앱 셸과 내비게이션 재구성

> 선행: T01. 기준: `01-design-system.md` 1·4절, 5.9·5.11·5.13·5.14절, `00-context.md` 10.1절.

## 현행 반영 (T00 결과, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- **이미 구현된 것은 다시 만들지 않습니다**: 인증된 GET `/login` → 역할별 화면 리다이렉트, 오류 토스트 자동 소멸 안 함(`portal.js:153–156`),
  숨긴 탭 폴링 생략·다시 보이면 조회(`portal.js:225–253`). 이 동작은 회귀 테스트로 고정하고 누락된 부분만 보완합니다.
  - 남은 보완: 로그인 템플릿이 앱 셸을 상속하지 않게 분리, **POST `/login` 실패 응답도** 앱 셸 없이 렌더, 폴링 4초 → 30초,
    인증 만료 시 401 JSON 처리·폴링 중지(T00B-2에서 구현했다면 재사용).
- **고객 목록은 경로 방식 유지**: `/msp/customers/<environment>`에 `all`을 추가합니다(`/msp/customers/all`). 쿼리 `?env=`로 바꾸지 않으므로 기존 URL 리다이렉트가 필요 없습니다.
  접미사 없는 `/msp/customers`만 `/msp/customers/all`로 302.
- **알림함은 신규 설계**: 현재 알림 저장 테이블·읽음 상태가 없습니다(알림은 `report_jobs`의 시각을 펼친 조회, `webapp/repository.py:3349`).
  본문 6절의 테이블은 `control` 스키마 배치·RLS·고객 범위 검사·POST+CSRF를 포함해 계획에서 **별도 승인**받고, 승인 전에는 셸에 알림함 자리를 만들지 않습니다.
- **역할**: `SYSTEM_ADMIN`을 `MSP_ADMIN`과 자동으로 같게 취급하지 않습니다. 메뉴 권한 필터는 현행 라우트 권한 검사와 같은 규칙을 씁니다.
- **아직 없는 화면으로 가는 링크를 만들지 않습니다**(현재 이슈·리포트 프로필 등). 해당 지시서가 끝날 때 메뉴에 추가합니다.
- 템플릿 경로는 `webapp/templates/`. 메뉴는 기존 `base.html`의 `menu_link` 매크로를 확장합니다.
- **상태 축**: 작업은 `SUCCESS`인데 보고서가 `PARTIAL_SUCCESS`인 경우 현재 알림이 성공으로 보일 수 있습니다. 어느 쪽 기준으로 알릴지 계획에서 제안하고 승인받습니다
  (권장: 보고서 결과 기준으로 "부분 수집" 표시).

## 목표
- 사이드바를 **펼침(≥1280) / 아이콘 레일(768–1279) / 드로어(<768)** 3단계로 전환하고 상단바를 도입합니다.
- 메뉴 정보구조를 목표 사이트맵으로 바꿉니다.
- 브레드크럼·전역 검색(⌘K)·알림함을 셸에 넣습니다.
- 로그인 화면을 앱 셸과 분리합니다(인증된 GET `/login` 리다이렉트는 이미 구현됨 — 유지).

## 현재 문제 (실측)
- 1000px 이하: build-46 `ux.css` 패치로 사이드바가 본문 위 **정적 블록**이 되고 햄버거로 접고 펼침. 펼치면 메뉴 전체가 본문을 아래로 밀어냄(오버레이 아님),
  메뉴는 여전히 2열 그리드. build-44에서는 375px 첫 화면의 55%(446px)가 메뉴였음.
- 1001–1279px: 사이드바 250px 고정 + 본문 좌우 패딩 42px → 1024px 노트북에서 본문 약 690px. 아이콘 레일 단계가 없음.
- 민간 고객 / 공공 고객이 별도 메뉴 2칸.
- (2026-10-01 운영 화면 관찰) 로그인 화면에 사이드바가 함께 렌더링된 사례가 있었음. 코드에는 인증된 GET 리다이렉트가 이미 있으므로
  남은 경로(POST 실패 렌더, 로그인 템플릿의 셸 상속)를 확인해 보완합니다.
- 알림은 토스트뿐이라 다시 볼 곳이 없음(오류 토스트 유지는 이미 구현됨).

## 작업 지시

### 1. 셸 마크업 (`webapp/templates/base.html`)
```
<a class="skip-link" href="#main">본문 바로가기</a>
<div class="app-shell" data-sidebar="expanded|rail">
  <aside class="sidebar" aria-label="주 메뉴"> 로고 · nav 그룹들 · 하단 사용자 영역 · 접기 버튼 </aside>
  <header class="topbar"> [햄버거(<768)] · 브레드크럼 · 검색 버튼(⌘K) · 알림 종(배지) · 사용자 메뉴(테마 토글·로그아웃) </header>
  <main id="main" tabindex="-1"> {% block content %} </main>
</div>
<dialog class="nav-drawer">…</dialog>      <!-- <768 -->
<dialog class="command-palette">…</dialog>
<div popover id="notification-inbox">…</div>   <!-- 알림함 설계 승인 후에만 -->
```
- 사이드바 접힘 상태는 쿠키에 저장해 서버가 첫 렌더부터 올바른 상태로 그리게 합니다(깜빡임 방지).
- 레일 모드: 아이콘만 표시, 각 링크에 `aria-label`과 툴팁(호버·포커스). 그룹 라벨은 구분선으로 대체.
- 드로어: 햄버거 → `showModal()`, 링크 클릭·Esc·배경 클릭으로 닫힘, 포커스 트랩.

### 2. 메뉴 정보구조
```
운영        통합 대시보드 /msp · 현재 이슈 /msp/issues(T09 전까지는 숨김 또는 "준비 중" 없이 생략) · 고객 /msp/customers/all
자동화      실행 일정 /msp/schedules · 리포트 프로필 /msp/profiles(T05 전까지 생략)
보고서      보고서 보관함 /portal · 실행 이력 /history
관리        계정·사용자 /msp/users · 저장공간·보존 /msp/data-cleanup
```
- 현재 위치: 하위 경로도 상위 메뉴를 현재로 표시(예: `/msp/customer/{id}` → "고객"). `aria-current="page"`는 정확히 일치하는 경우,
  상위 일치는 `aria-current="true"`.
- 메뉴 정의는 서버 측 한 곳(리스트 상수)에서 관리하고 권한별로 필터링합니다. 고객 사용자 역할의 메뉴도 같은 구조로 정의.

### 3. 고객 목록 통합
- 기존 경로 방식을 유지해 `GET /msp/customers/<environment>?q=`(`environment` ∈ `all|public|gov`, `all` 신규) — 상단 세그먼트 탭(전체/민간/공공, 개수 표시) + 검색.
- 기존 `/msp/customers/public`, `/msp/customers/gov`는 그대로 동작합니다(리다이렉트 없음). 접미사 없는 `/msp/customers`만 `/msp/customers/all`로 302.
- 기존 카드 목록은 유지하되 T03의 목록 패턴을 적용할 수 있게 표 보기/카드 보기 토글 자리를 남깁니다.
- 신규 고객 등록은 페이지 헤더의 `+ 고객 등록` 버튼 → 사이드 시트(`<dialog>`) 폼. JS가 없으면 현행 `<details>` 등록 폼을 그대로 대체 수단으로 씁니다
  (`/msp/customers/new` 같은 경로는 `GET/POST /msp/customers/<environment>`와 충돌하므로 만들지 않음).
- 등록 제출은 기존 `POST /msp/customers/<environment>`(public|gov)를 씁니다. `all` 탭에서 등록할 때는 폼에서 환경을 고르게 하고, `POST /msp/customers/all`은 400으로 거부합니다.

### 4. 브레드크럼
모든 상세·하위 화면에 01-design-system.md 5.13 형식. 예:
`고객 › 클라비` / `고객 › 클라비 › 보고서 › 2026-09-30 일간` / `실행 일정` / `보고서 보관함 › 소상공인 2026-09-30 일간`.
브레드크럼 데이터는 핸들러가 `breadcrumbs=[(label, url), …]`로 넘깁니다.
≥768px에서는 상단바에, <768px에서는 페이지 헤더 첫 줄에 같은 마크업으로 표시합니다.

### 5. 전역 검색 (⌘K)
- `GET /search?q=` → JSON `{items:[{type:"screen|customer|account|report", label, sublabel, url}]}`, 권한 범위 내, 최대 20건, 응답 200ms 목표.
- 팔레트: 입력 시 200ms 디바운스, 방향키 이동, Enter 이동, 최근 이동 5건 기억(localStorage).
- 상단바 검색 버튼에 단축키 표시(`⌘K` / `Ctrl K`). `/` 키는 현재 페이지의 목록 검색창에 포커스(있을 때).

### 6. 알림함 (신규 설계 — 계획에서 별도 승인 후 구현)
- 서버: 알림을 **새 테이블**에 저장(현재 저장 테이블 없음, `control` 스키마·RLS·고객 범위 검사) —
  `notification(id, category(info|success|warning|error), audience(ALL_MSP|USER|TENANT), user_id, tenant_id, title, message, link, created_at)`
  + 읽음 테이블 `notification_read(user_id, notification_id, read_at)`. 고객 사용자에게는 자기 tenant 알림만 보입니다.
- `GET /notifications?after=` 는 유지(토스트용), `GET /notifications/inbox?page=` 추가, `POST /notifications/{id}/read`, `POST /notifications/read-all`.
- 클라이언트: 폴링 4초 → **30초**. 숨긴 탭 생략·복귀 시 1회 조회·오류 토스트 유지는 이미 구현됨(유지). 경고 토스트도 자동 소멸 안 함으로 변경.
  성공·정보는 6초, 호버·포커스 시 정지. 종 아이콘 배지에 안 읽은 개수.

### 7. `/login` 처리
- 인증된 GET 요청의 역할별 302(MSP → `/msp`, 고객 사용자 → `/portal`)는 이미 구현됨 → 회귀 테스트만 추가. **POST `/login` 실패 응답도 앱 셸 없이** 렌더.
- 로그인 템플릿은 앱 셸을 상속하지 않는 별도 레이아웃(`auth_base.html`). 히어로 문구는 <1000px에서도 제목 한 줄과 로고는 카드 위에 유지.
- 로그인 카드 하단에 "계정 문의: MSP 담당자" 안내(설정값으로 이메일/링크 주입).

## 완료 조건
- [ ] 375 / 768 / 1280 / 1440px에서 셸이 각각 드로어 / 레일 / 펼침 / 펼침으로 동작, 페이지 가로 스크롤 없음
- [ ] 375px 첫 화면에서 본문 시작 y좌표 ≤ 상단바 높이(56px) + 8px
- [ ] 768px에서 본문 가용 폭 ≥ 640px
- [ ] 키보드만으로 드로어 열기→이동→닫기, 팔레트 열기→검색→이동 가능, 포커스 복귀 확인
- [ ] 기존 `/msp/customers/public`·`/gov` URL이 그대로 동작하고, `/msp/customers` → `/msp/customers/all` 302
- [ ] 로그인 상태 GET `/login` → 302(기존 동작 유지), 비로그인 GET 및 POST 실패 `/login`에 사이드바 없음
- [ ] 오류 토스트가 자동으로 사라지지 않음(기존 유지). 알림함이 승인·구현된 경우 알림함에서 다시 볼 수 있음
- [ ] 아직 없는 화면으로 가는 링크 0건
- [ ] 폴링 간격 30초, 탭 숨김 시 요청 없음(네트워크 로그 첨부)

## 검증
- Playwright: 4개 폭 셸 상태 캡처, 드로어/팔레트 키보드 시나리오 테스트, `/login` 리다이렉트 테스트.
- `/search` 권한 테스트: 고객 사용자는 자기 고객 외 결과 0건.

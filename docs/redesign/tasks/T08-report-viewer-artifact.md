# T08 — 보고서 뷰어와 산출물(본문 HTML) 품질

> 선행: T07(버전·매니페스트). 이 작업은 **새로 렌더되는 보고서**에만 적용됩니다. 이미 저장된 산출물은 수정하지 않습니다.
> `RENDERER_VERSION`(T07)을 올리고, 변경 사항을 `CHANGELOG-renderer.md`에 기록하세요.

## 현행 반영 (T00 결과, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- 보고서 본문은 Jinja 템플릿이 아니라 **Python 렌더러**입니다(`app/renderers/html_renderer.py` 5,352줄, 스타일 `html_report_styles.py`). 본문의 "본문 템플릿"은 이 렌더러를 뜻합니다.
- 새 기능은 **새 모듈**(예: `app/renderers/report_charts.py`, `report_labels.py`)에 두고 `html_renderer.py`에는 호출 연결만 추가합니다(AGENTS.md 7절).
- 신규 HTML에는 이미 `HTML_REPORT_STYLES`와 `REPORT_DISPLAY_STYLES` 두 묶음이 인라인됩니다(`html_renderer.py:2722`). 범례·축 문제는 **기본 규칙 자체를 고치고**,
  새로 렌더하는 보고서에서는 같은 문제를 덮어쓰던 중복 보정 규칙을 제거합니다. 기존 산출물은 수정하지 않습니다.
- **CSP**: 인라인 스타일·스크립트를 바꾸면 렌더러의 CSP 해시 상수(`html_renderer.py:678–689`)와 T00B-2 응답 헤더가 함께 맞아야 합니다(해시 일치 테스트).
- **뷰어 인쇄·펼치기**: 현재 `portal.js:44–86`이 같은 출처 iframe의 `contentDocument`·`contentWindow.print()`에 의존합니다. T00B-2에서 미룬 iframe `sandbox`를 이 작업에서 적용하고,
  **`postMessage` 기반**(본문 스크립트가 `print`·`expand-all`·`collapse-all` 메시지를 받아 실행, `event.origin`·`event.source` 검사)으로 바꿉니다. 기존 산출물(메시지 수신 코드 없음)은 "새 창에서 보기"로 대체합니다.
- **지표 단위**: `real_mem` 등의 단위를 추정하지 않습니다. 응답·메타데이터에 단위가 없으면 단위 없이 표시하고 확인 방법을 보고합니다(current-map 8.2).
- 상태 라벨·톤은 T01에서 정한 공용 매핑을 렌더러도 import해서 씁니다(01-design-system.md 5.2 끝 문단).
- 공유 링크 버튼은 T06 공유 링크가 **승인·구현된 경우에만** 노출합니다.
- 뷰어 셸은 T02 앱 셸 안의 일반 flex 자식으로 둡니다(`automation.css:71`의 고정 `inset` 제거). 중단점은 T02 기준(768/1280)이며, T00B-9의 1000px는 T02 이전 임시 조치입니다.
- 생성 시각은 매니페스트 `rendered_at`을 KST로 표시합니다(포맷 규칙은 T01 공용 헬퍼와 같게, 구현은 렌더러 쪽 모듈).

## 목표
고객사에 전달되는 결과물 자체의 완성도를 올립니다: 모바일에서 깨지지 않고, 인쇄/PDF에서 읽히며, 내부 값이 노출되지 않는 보고서.

## 확인된 결함 (실측)
1. 차트 범례 `.chart-legend-item`에 폭 제한이 없어 Kubernetes CSI 볼륨 경로
   (`gbsa-nodepool-w-3026 · /var/lib/kubelet/plugins/kubernetes.io/csi/blk.csi.ncloud.com/27cd…`)가 한 줄로 늘어나
   375px 화면에서 문서 폭이 928px이 됨(페이지 전체 가로 스크롤).
2. 인쇄 CSS의 `.chart-legend{display:none}` → 인쇄물에서 어느 선이 어느 서버인지 알 수 없음.
3. 사용률 차트 4종 Y축이 0–100% 고정 → 값이 1–2%인 고객은 모든 계열이 바닥선에 겹침.
4. "생성 시각"이 ISO 원문(`2026-09-21T09:02:18.301468+09:00`), "보고서 ID"가 기간과 중복(`20260920_20260920`).
5. 차트 제목만 영문(`Memory Utilization Average`).
6. 접이식 `<details>` 31개 전부 닫힌 채 시작(build-46에서 뷰어에 모두 펼치기/접기 버튼 추가됨).
7. Insight 알람 "대상 상세"에 원시 JSON, 조건 단위 표기 의심(`real_mem >= 90 bytes`).

## 작업 지시

### A. 본문 (Python 렌더러)
1. 디자인 토큰: `01-design-system.md` 3절 토큰을 렌더러 패키지 안 정적 파일(예: `app/renderers/assets/report-tokens.css`)로 만들어 렌더 시 인라인(CSP 해시 갱신). 라이트 고정(인쇄 기준) + `prefers-color-scheme: dark` 화면용 변형은 선택.
2. 범례:
   ```css
   .chart-card { container-type: inline-size; }          /* 범례의 컨테이너 쿼리 기준 */
   .chart-legend { display:flex; flex-wrap:wrap; gap:4px 12px; min-width:0; }
   .chart-legend-item { max-width:100%; min-width:0; }
   .chart-legend-item > span { display:block; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
   @container (width < 560px) { .chart-legend-item > span { white-space:normal; overflow-wrap:anywhere; } }
   ```
   라벨은 서버에서 `호스트 · …/마지막 8자` 형태로 축약(`shorten_volume_label()`), 전체 경로는 `title`과 툴팁에.
3. 인쇄: 범례를 숨기지 말고 차트 아래 2열 목록으로. 계열이 8개 초과면 상위 8개 + "외 N개".
4. Y축: 기본 0–100%. 계열 최대값 < 25%면 축 상한을 `max(5, ceil(max × 1.2 / 5) × 5)`(최소 5%)로 자동 조정하고 축 옆에 "자동 축(최대 2.1%)" 표기.
   차트 위에 계열별 `최대 / 평균` 숫자 요약 줄 추가(평평한 그래프여도 정보 전달).
5. 메타 영역: 생성 시각 `fmt_dt`, 보고서 ID는 "기술 상세" 접기 안으로, 버전·스냅샷 해시 앞 8자 표시.
6. 차트·섹션 제목: `메모리 사용률 평균 (Memory Utilization Average)` 형식. 매핑 사전 한 곳.
7. 기본 펼침 규칙: 판정이 `위험`·`주의`인 항목과 "즉시 확인" 섹션은 `open`, 나머지 닫힘.
8. 원시 JSON 출력 금지 → `render_kv(obj)`로 키-값 목록(키는 사람이 읽는 라벨 사전으로 변환, 모르는 키는 원문 키).
9. 지표 단위: Cloud Insight 메타데이터의 단위를 사용. `real_mem` 등 단위가 불명확한 지표는 단위를 붙이지 않습니다(추정 금지).
   원천 응답·메타데이터의 단위 필드로 **확인된 것만** 매핑 표(`docs/redesign/current-map.md` 부록)에 추가합니다.
10. 상태·판정 표시는 `status_badge`와 같은 매핑을 보고서 렌더러에서도 사용(라벨·톤 일치).
11. 데이터 표 대체: 각 차트 아래 `<details><summary>데이터 표로 보기</summary>` — 시간대별 값 표(접근성·인쇄 대안).
12. 문서 맨 위 **요약 카드 4개**(운영 판정, 즉시 확인 건수, 데이터 수집 상태, 기간 비용)를 고정 순서로 — 이미 있는 "오늘의 요약"을 정리하되 문구는 결정적 분석 결과만 사용.

### B. 뷰어(`/reports/{id}`)
1. 툴바: 제목·기간·상태 배지 / 버전 선택기(T07) / `인쇄 · PDF 저장`(primary) / `공유 링크 만들기`(외부용, T06 공유 링크가 승인·구현된 경우만) / `⋯`(주소 복사(내부 URL), 새 창, 모두 펼치기·접기, 출처 패널, 재현 동작) / 위험 동작은 `⋯ › 보고서 삭제`로 이동.
2. iframe 높이: 뷰어 셸이 `100dvh`를 쓰는 현재 방식 유지, 모바일에서는 iframe 대신 **본문으로 직접 이동하는 링크**를 기본 노출(iframe 안 스크롤 이중화 방지).
3. 인쇄 버튼은 iframe에 `postMessage({type: "print"})`를 보내 본문이 `window.print()`를 실행(위 현행 반영 절). iframe 미로드 시 비활성 + 스피너.
4. 키보드: `p` 인쇄, `[`/`]` 이전·다음 버전(포커스가 입력창이 아닐 때).

## 완료 조건
- [ ] 새로 렌더한 보고서가 375px에서 문서 폭 = 뷰포트 폭(가로 스크롤 0), 768/1440도 동일
- [ ] 인쇄 미리보기(A4 가로)에서 모든 차트에 범례 존재, 표가 페이지 경계에서 행 중간이 잘리지 않음
- [ ] 저사용률 고객 보고서에서 자동 축 적용·표기 확인
- [ ] 본문의 **보이는 텍스트**(script·style·속성 제외)에 마이크로초 포함 ISO 시각·원시 JSON·영문 상태 코드 노출 0건(검사 테스트)
- [ ] 결정성 테스트(T07) 계속 통과
- [ ] 과거 버전 산출물은 바이트 변화 없음
- [ ] iframe `sandbox` 적용 후 인쇄·모두 펼치기/접기가 `postMessage`로 동작, 출처 검사 테스트
- [ ] `html_renderer.py` 증가분은 호출 연결뿐(새 로직은 새 모듈), CSP 해시 일치 테스트 통과

## 검증
- 저사용률·고사용률·볼륨 경로 긴 고객 3종 스냅샷으로 렌더 → 375/1440 캡처 + 인쇄 PDF 첨부.

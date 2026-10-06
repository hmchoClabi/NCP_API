# T08 — 보고서 뷰어와 산출물(본문 HTML) 품질

> 선행: T07(버전·매니페스트). 이 작업은 **새로 렌더되는 보고서**에만 적용됩니다. 이미 저장된 산출물은 수정하지 않습니다.
> `RENDERER_VERSION`(T07)을 올리고, 변경 사항을 `CHANGELOG-renderer.md`에 기록하세요.

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

### A. 본문 템플릿
1. 디자인 토큰: `01-design-system.md` 3절 토큰을 `report-tokens.css`로 만들어 렌더 시 인라인. 라이트 고정(인쇄 기준) + `prefers-color-scheme: dark` 화면용 변형은 선택.
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
9. 지표 단위: Cloud Insight 메타데이터의 단위를 사용. `real_mem` 등 단위가 불명확한 지표는 단위를 붙이지 않고, 원천 응답에서 단위 필드를 확인해 매핑 표를 T00 문서에 추가.
10. 상태·판정 표시는 `status_badge`와 같은 매핑을 보고서 렌더러에서도 사용(라벨·톤 일치).
11. 데이터 표 대체: 각 차트 아래 `<details><summary>데이터 표로 보기</summary>` — 시간대별 값 표(접근성·인쇄 대안).
12. 문서 맨 위 **요약 카드 4개**(운영 판정, 즉시 확인 건수, 데이터 수집 상태, 기간 비용)를 고정 순서로 — 이미 있는 "오늘의 요약"을 정리하되 문구는 결정적 분석 결과만 사용.

### B. 뷰어(`/reports/{id}`)
1. 툴바: 제목·기간·상태 배지 / 버전 선택기(T07) / `인쇄 · PDF 저장`(primary) / `공유 링크 만들기`(외부용 서명 링크, T06) / `⋯`(주소 복사(내부 URL), 새 창, 모두 펼치기·접기, 출처 패널, 재현 동작) / 위험 동작은 `⋯ › 보고서 삭제`로 이동.
2. iframe 높이: 뷰어 셸이 `100dvh`를 쓰는 현재 방식 유지, 모바일에서는 iframe 대신 **본문으로 직접 이동하는 링크**를 기본 노출(iframe 안 스크롤 이중화 방지).
3. 인쇄 버튼은 iframe `contentWindow.print()`(동일 출처), iframe 미로드 시 비활성 + 스피너.
4. 키보드: `p` 인쇄, `[`/`]` 이전·다음 버전(포커스가 입력창이 아닐 때).

## 완료 조건
- [ ] 새로 렌더한 보고서가 375px에서 문서 폭 = 뷰포트 폭(가로 스크롤 0), 768/1440도 동일
- [ ] 인쇄 미리보기(A4 가로)에서 모든 차트에 범례 존재, 표가 페이지 경계에서 행 중간이 잘리지 않음
- [ ] 저사용률 고객 보고서에서 자동 축 적용·표기 확인
- [ ] 본문의 **보이는 텍스트**(script·style·속성 제외)에 마이크로초 포함 ISO 시각·원시 JSON·영문 상태 코드 노출 0건(검사 테스트)
- [ ] 결정성 테스트(T07) 계속 통과
- [ ] 과거 버전 산출물은 바이트 변화 없음

## 검증
- 저사용률·고사용률·볼륨 경로 긴 고객 3종 스냅샷으로 렌더 → 375/1440 캡처 + 인쇄 PDF 첨부.

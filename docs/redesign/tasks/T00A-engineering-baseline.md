# T00A — 엔지니어링 기반 정비 (설정·줄바꿈·잠금·CI 스크립트·버전 체계)

> 선행: T00(완료). 근거: 2026-10-06 코드 점검 리포트 07절, `current-map.md` 1절. 이 작업은 **동작을 바꾸지 않습니다.**
> 여러 PR로 나눕니다: A-1 저장소 설정, A-2 포맷 일괄 적용, A-3 의존성 잠금, A-4 CI 스크립트, A-5 릴리스 버전.

## 현행 반영 (T00 결과·결정, 2026-10-07) — 본문과 충돌하면 이 절이 우선
- 추적 파일은 현재 깨끗합니다(수정 표시 0). 다만 작업 트리에 **CRLF 4개·mixed 37개(총 41개)** 가 있습니다.
  A-1의 `git add --renormalize .`는 실행 전에 **대상 파일 목록과 diff 통계를 보여주고 별도 승인**을 받은 뒤, 다른 변경과 섞지 않은 단독 커밋으로만 합니다.
- 미추적 파일 3개(`ClaMax _ 메일.pdf`, `architect-clabi-uiux-audit.html`, `모니터링 report 바라는 점 관련 파일.docx`)는 지우거나 스테이징하지 않습니다.
  `.gitignore`에 `/*.pdf`·`/*.docx`·`/*.html`을 넣으면 이 파일들이 목록에서 숨겨지므로, 추가 전에 사용자에게 알리고 확인받습니다.
- `app/runner.py:2321`의 미사용 변수 `infrastructure_data`는 **결정 D1에 따른 설계**입니다(버그 아님). A-2 포맷 커밋에서는 건드리지 않고,
  별도 소규모 커밋에서 삭제하면서 그 자리에 `# D1 참조: 범주 선택은 표시에만 적용하고 수집·분석·저장은 원본 유지` 주석을 남깁니다(F841 해소).
- **네트워크가 필요한 단계는 실행하지 않습니다**: A-3 `uv pip compile --generate-hashes`, 베이스 이미지 다이제스트 조회, `pip-audit`.
  사용자가 실행할 **명령과 결과 확인 방법**을 준비해 보고하고, 잠금 파일·다이제스트·취약점 결과를 추정으로 채우지 않습니다.
- `requires-python`은 `pip install -r requirements.txt` 설치에서는 **강제되지 않습니다**(프로젝트 설치가 아니므로).
  Python 버전 보장은 `.python-version` + CI·Dockerfile의 실제 버전 검사(예: `python -c "import sys; assert sys.version_info[:2] == (3, 13)"`)로 하고, 완료 조건도 이 검사로 증명합니다.
- 테스트 명령은 AGENTS.md 8절. 현재 기준 620 passed · 5 skipped.
- DB 통합 테스트의 "SKIPPED 0"은 PostgreSQL 서비스가 있는 CI에서만 증명할 수 있습니다. 로컬에서 DB를 띄울 수 없으면 "CI에서 확인 필요"로 보고합니다.

## 현재 문제 (실측)
- `pyproject.toml` 없음. `itertools.batched`(Python 3.12+)를 쓰는데 `requires-python` 미선언 — 3.11에서는 테스트 9개 파일이 import 실패.
- bare `pytest`는 `ModuleNotFoundError: utils`, `python -m pytest`만 동작.
- `.gitattributes`·`.editorconfig` 없음 → 작업 트리에 CRLF/mixed 줄바꿈 파일 41개(현재 Git 수정 표시는 0개지만, 체크아웃·편집 도구에 따라 내용 변경 없이 "수정됨"이 될 수 있음).
- `ruff format` 적용 시 157개 중 114개 파일 변경. 린트·포맷·타입 설정 없음.
- `requirements.txt`는 범위만 있고 잠금 파일·해시 없음. `cryptography>=44,<46` 상한이 보안 패치 13건을 막음(이건 T00B에서 처리).
- `Dockerfile`이 `Dockerfile.runtime` + `Dockerfile.migration` 내용을 중복. 빌드 중 `pip install --upgrade pip`, 베이스 이미지 태그 고정 안 됨.
- 파이프라인 정의가 저장소에 없음(NCP 콘솔 수동 설정). `requirements-dev.txt`는 pytest만.
- DB 통합 테스트 5개(`REPORT_DB_INTEGRATION_TEST=1`)와 JS 테스트 4개(Node 없으면)가 조용히 건너뜀.
- 릴리스 식별자가 git sha·runtime build·migration build·Helm revision 4종. `build-N`은 노트북에서 빌드 이력 개수로 계산.

## 작업 지시

### A-1 저장소 설정
1. `.gitattributes`
   ```
   * text=auto eol=lf
   *.ps1 text eol=crlf
   *.cmd text eol=crlf
   *.png binary
   *.jpg binary
   *.webp binary
   *.pdf binary
   ```
   적용 후 `git add --renormalize .` 커밋 1개(내용 변경 없음을 `git diff --cached --ignore-all-space --ignore-cr-at-eol --stat` 결과로 증명). **실행 전 대상 파일 목록을 보여주고 승인받습니다.**
2. `.editorconfig`(UTF-8, LF, 들여쓰기 4칸, 끝 공백 제거; ps1/cmd는 CRLF).
3. `.gitignore`에 `/*.pdf`, `/*.docx`, `/*.html`, `/.tmp/` 추가(현재 미추적 파일 3개가 숨겨진다는 점을 사용자에게 먼저 알림). 문서(`deploy/*.md`)의 `git add --all` 안내를 `git add -p`로 수정.
4. `pyproject.toml` (패키징은 하지 않고 도구 설정만):
   ```toml
   [project]
   name = "ncp-report"
   requires-python = ">=3.13,<3.14"
   dynamic = ["version"]

   [tool.pytest.ini_options]
   pythonpath = ["."]
   testpaths = ["tests"]
   addopts = "-ra --strict-markers"
   markers = ["integration: PostgreSQL 필요", "js: Node 필요"]

   [tool.ruff]
   target-version = "py313"
   line-length = 100
   [tool.ruff.lint]
   select = ["E4", "E7", "E9", "F", "B", "I"]
   [tool.ruff.lint.per-file-ignores]
   "tests/*" = ["B011"]

   [tool.coverage.run]
   source = ["app", "collectors", "normalizers", "ncp_api", "webapp", "database", "utils", "config"]
   ```
5. `.python-version`(`3.13`), `requirements-dev.txt`에 `ruff`, `pytest-cov`, `pip-audit` 추가.
6. 기존 skip 조건을 마커로 바꿉니다: DB 통합 테스트 → `@pytest.mark.integration`, JS 테스트 → `@pytest.mark.js`. 환경변수 확인 로직은 `conftest.py`의 마커 처리로 옮기고,
   로컬에서는 조건이 없으면 건너뛰되, CI에서는 `CI=1`일 때 조건 미충족을 **실패**로 처리해 전부 실행되게 합니다(아래 A-4).
7. `pre-commit` 설정: ruff, ruff-format, check-yaml, end-of-file-fixer, detect-private-key.

### A-2 포맷 일괄 적용 (별도 PR, 동작 변경 없음)
- `ruff check --fix`(위 규칙만) + `ruff format` 한 번에 적용한 커밋 1개. 커밋 해시를 `.git-blame-ignore-revs`에 기록.
- 이 PR에서는 **어떤 로직도 바꾸지 않습니다.** 테스트 전체 통과로 증명.
- `app/runner.py:2321`의 사용되지 않는 `infrastructure_data` 변수는 이 포맷 커밋에서 건드리지 않습니다. 결정 D1에 따라 별도 소규모 커밋에서 삭제하고 `D1 참조` 주석을 남깁니다(위 현행 반영 절).

### A-3 의존성 잠금과 이미지
1. `requirements.in`(현재 requirements.txt 내용) → `uv pip compile --generate-hashes -o requirements.txt`. 개발용도 동일하게. **(네트워크 필요 — 명령만 준비, 사용자가 실행)**
2. Dockerfile들은 `pip install --require-hashes -r requirements.txt`, `pip install --upgrade pip` 제거.
3. 베이스 이미지를 다이제스트로 고정(`python:3.13-slim@sha256:…`, `postgres:16@sha256:…`). 업데이트는 월 1회 수동 또는 Renovate. **(다이제스트 조회는 네트워크 필요 — 사용자가 조회한 값을 받아 반영)**
4. 중복된 루트 `Dockerfile`을 삭제하고, 이를 참조하는 곳(compose, 스크립트, 문서, `tests/test_deployment_assets.py`)을 `Dockerfile.runtime`/`Dockerfile.migration`으로 수정.
5. `Dockerfile.runtime`에 `ARG GIT_SHA`, `ARG APP_VERSION` + `LABEL org.opencontainers.image.revision=$GIT_SHA org.opencontainers.image.version=$APP_VERSION`, `ENV APP_VERSION=$APP_VERSION`.

### A-4 CI 스크립트 (어디서 돌리든 같은 명령)
`ci/check.sh` 하나를 만들고 PR 검사(GitHub Actions 등)와 NCP SourceBuild가 **같은 스크립트를 호출**하게 합니다.
```bash
set -euo pipefail
ruff check .
ruff format --check .
pip-audit -r requirements.txt
# PostgreSQL 16 서비스가 떠 있다는 전제 (CI 서비스 컨테이너)
CI=1 REPORT_DB_INTEGRATION_TEST=1 python -m pytest --cov --cov-fail-under=73
helm lint deploy/helm/ncp-report -f deploy/helm/ncp-report/values-pilot.yaml
helm template t deploy/helm/ncp-report -f deploy/helm/ncp-report/values-pilot.yaml --set image.tag=ci > /tmp/rendered.yaml
```
- 건너뛴 테스트가 있으면 실패하게 합니다(`-ra` 출력에서 SKIPPED 검사 또는 `pytest --strict` 플러그인).
- CI 정의 파일(`.github/workflows/ci.yml`)과 SourceBuild 명령 문서(`deploy/SOURCEBUILD_SETUP.md`)를 이 스크립트 호출로 갱신.
- JS 테스트를 위해 CI 이미지에 Node 20+ 설치.

### A-5 브랜치·릴리스 버전 (문서와 스크립트만)
- 기본 브랜치를 `main`으로 통일하는 **절차서**를 `docs/runbooks/branch-and-release.md`로 작성(원격·SourceCommit·스크립트 수정 지점 목록 포함). 실제 브랜치 이름 변경은 사용자가 수행.
- 릴리스 버전 하나로 통일: CalVer `vYYYY.MM.N` 주석 태그 → 이미지 태그(+ sha 태그) → Helm `appVersion` → `APP_VERSION`. `run-sourcebuild.ps1`의 빌드 이력 개수 계산 대신 태그에서 읽기.
- `CHANGELOG.md` 시작(git-cliff 설정 포함), 백업 브랜치를 `archive/*` 태그로 바꾸는 명령을 런북에 기록.
- `README.md` 재작성: 목적, 구조(00-context 10.2 그림), 로컬 실행, 테스트, 릴리스 절차 링크.

## 완료 조건
- [ ] Windows에서 체크아웃 후 `git status` 깨끗(CRLF 변경 0건). 정규화 커밋은 승인 후 단독 커밋
- [ ] bare `pytest`와 `python -m pytest` 모두 동작, Python 3.13이 아니면 CI·Docker 빌드의 버전 검사 단계에서 명확히 실패
- [ ] A-2 PR이 로직 변경 0이고 테스트 전체 통과
- [ ] `pip install --require-hashes`로 이미지 빌드 성공, 루트 `Dockerfile` 삭제 후 참조 0
- [ ] `ci/check.sh` 로컬 실행 결과 첨부, 통합·JS 테스트가 **실제로 실행**됨(SKIPPED 0 — DB가 없는 로컬에서는 CI 결과로 대체)
- [ ] `infrastructure_data` 삭제가 별도 커밋이고 `D1 참조` 주석이 있음, 동작·테스트 결과 변화 없음
- [ ] 런북·README·CHANGELOG 작성

## 검증
- `ci/check.sh` 전체 출력, `git status` 출력, 이미지 라벨(`docker inspect`) 결과 첨부.

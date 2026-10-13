# 브랜치·릴리스 운영 런북

## 첫 push 체크리스트

A-3의 해시 잠금 파일을 처음 SourceCommit에 반영할 때 사용합니다.
이 절차는 사용자가 수행하며, 체크리스트 작성 자체가 push·빌드·배포를
실행하지는 않습니다.

- [ ] 로컬 변경을 검토하고 테스트·Ruff 검사가 통과한 커밋을 준비합니다.
- [ ] SourceBuild가 읽는 저장소와 브랜치를 확인합니다. 현재 문서 기준은
  `architect_report` / `master`입니다.
- [ ] 자동 빌드 또는 SourcePipeline 트리거가 있다면 전환 중 빌드가 시작되지
  않도록 사용자가 일시 중지합니다. 기존 상태를 기록해 전환 후 복구합니다.
- [ ] **해시 잠금 파일이 포함된 새 커밋을 먼저 SourceCommit에 push합니다.**
  콘솔 설치 명령은 이 시점까지 기존 값으로 유지합니다.
- [ ] 원격 브랜치의 전체 SHA가 push한 커밋과 같은지 확인합니다. 이전 커밋에는
  해시가 없어 콘솔 명령을 먼저 바꾸면 `--require-hashes` 설치가 실패합니다.
- [ ] **원격 커밋 확인 후** runtime 프로젝트의 빌드 전 명령 두 줄
  (`python -m pip install --upgrade pip`,
  `python -m pip install -r requirements-dev.txt`)을 아래 한 줄로 교체하고 저장합니다.

  ```sh
  python -m pip install --require-hashes -r requirements-dev.txt
  ```

- [ ] 저장된 runtime Dockerfile 경로가 `Dockerfile.runtime`인지 다시 확인합니다.
  빌드 명령 `python -m pytest -q`와 빌드 후 `compileall` 명령은 유지합니다.
- [ ] migration의 `Dockerfile.migration` 경로와 `test -f` / `test -d` / `echo`
  명령은 유지합니다.
- [ ] 콘솔 저장과 원격 커밋이 확인된 뒤 트리거를 복구합니다. 이후 빌드를
  진행한다면 해당 새 커밋을 사용하고 소스 SHA·테스트 결과를 기록합니다.

2026-10-13 사용자 콘솔 확인 결과 두 프로젝트에는 빌드 인수 입력란과
환경 변수가 없습니다. SourceBuild 이미지의 OCI revision 라벨은 빈 값,
version 라벨은 `local`로 남습니다. 실제 애플리케이션 버전 표시는 Helm이
주입하는 `APP_VERSION`을 따릅니다. OCI 라벨을 채우는 작업은 A-5 후속 항목입니다.

## 월간 베이스 이미지 다이제스트 갱신

월 1회 `python:3.13-slim`과 `postgres:16` 태그의 멀티 플랫폼 인덱스
다이제스트를 조회하고 현재 고정값과 비교합니다. 조회와 검토는 사용자가
수행합니다. 태그의 Python 3.13·PostgreSQL 16 범위는 유지합니다.

### Docker가 없는 Windows PowerShell 5.1

다음은 사용자가 2026-10-13에 실행한 조회 명령입니다. `cmd`에서
`powershell`을 실행한 뒤 붙여 넣을 수 있습니다. Docker 설치나 로그인,
저장된 인증정보가 필요하지 않습니다.

```powershell
foreach ($ref in @("library/python:3.13-slim", "library/postgres:16")) {
  $repo, $tag = $ref.Split(":")
  $token = (Invoke-RestMethod "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${repo}:pull").token
  $headers = @{
    Authorization = "Bearer $token"
    Accept = "application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json"
  }
  $r = Invoke-WebRequest -Method Head -UseBasicParsing -Headers $headers -Uri "https://registry-1.docker.io/v2/$repo/manifests/$tag"
  "$ref  " + ($r.Headers["Docker-Content-Digest"] -join "")
}
```

Docker Hub의 익명 pull 토큰은 각 이미지의 manifest HEAD 요청에만
사용합니다. 스크립트는 토큰 값을 출력하거나 파일에 저장하지 않고,
이미지 레이어를 내려받지 않습니다. 조회 후 PowerShell 세션을 종료합니다.
Accept 헤더는 OCI 인덱스와 Docker manifest list를 요청합니다.

### Docker가 있는 환경의 대안

```powershell
docker buildx imagetools inspect docker.io/library/python:3.13-slim
docker buildx imagetools inspect docker.io/library/postgres:16
```

최상위 `Digest:`를 기록합니다. 개별 플랫폼 항목의 다이제스트를
인덱스 다이제스트 대신 사용하지 않습니다.

### 조회 기록과 적용 절차

다음 값은 사용자가 2026-10-13에 레지스트리 메타데이터로 조회한
멀티 플랫폼 인덱스 다이제스트입니다. 이 작업에서 별도로 재조회하지 않았습니다.

| 이미지 태그 | 인덱스 다이제스트 |
|---|---|
| `python:3.13-slim` | `sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f` |
| `postgres:16` | `sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d` |

1. 조회 일자, 태그, `sha256:` 뒤의 64자리 다이제스트를 기록합니다.
   헤더가 없거나 조회가 실패하면 기존 고정값을 유지하고 원인을 확인합니다.
2. 값이 바뀌면 Python 값은 `Dockerfile.runtime`, PostgreSQL 값은
   `Dockerfile.migration`의 `FROM`에 반영합니다.
3. 요구사항 입력의 버전 범위와 해시 잠금 파일은 이 갱신에서 변경하지 않습니다.
   `PYTHON_DOTENV_DISABLED=1`로 기존 테스트를 실행하고 Ruff 린트·포맷 및
   최종 diff를 확인합니다.
4. 다이제스트 갱신을 별도 커밋으로 검토합니다. 실제 이미지 빌드·푸시·배포는
   별도로 승인된 릴리스 작업에서 수행하고, 해당 결과를 갱신 기록에 남깁니다.

2026-10-13 사용자 확인으로 두 SourceBuild 프로젝트 모두 전용 Dockerfile을
사용하며 루트 Dockerfile 참조가 없는 것을 확인했습니다. 빌드 인수 전달
방식을 추가한다면 A-5에서 콘솔 지원 여부와 실제 이미지 라벨을 검증합니다.

# 브랜치·릴리스 운영 런북

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
   `Dockerfile.migration`의 `FROM`에 반영합니다. 루트 `Dockerfile`이
   남아 있다면 해당 두 스테이지에도 같은 값을 적용합니다.
3. 요구사항 입력의 버전 범위와 해시 잠금 파일은 이 갱신에서 변경하지 않습니다.
   `PYTHON_DOTENV_DISABLED=1`로 기존 테스트를 실행하고 Ruff 린트·포맷 및
   최종 diff를 확인합니다.
4. 다이제스트 갱신을 별도 커밋으로 검토합니다. 실제 이미지 빌드·푸시·배포는
   별도로 승인된 릴리스 작업에서 수행하고, 해당 결과를 갱신 기록에 남깁니다.

SourceBuild의 실제 Dockerfile 경로와 빌드 인수 전달 방식은 콘솔에서
확인해야 합니다. 콘솔과 저장소에서 루트 Dockerfile 사용이 끝난 것을
확인하기 전에는 루트 파일을 삭제하지 않습니다.

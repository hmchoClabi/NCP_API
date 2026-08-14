# NCP 보고서 최소 조회 권한

이 문서는 현재 보고서 수집 코드가 실제로 호출하는 API를 기준으로 한다. 모든
정책은 `View/*`만 허용하며 `Change/*`, `Execute/*`, `*_MANAGER`,
`NCP_INFRA_MANAGER`, `NCP_ADMINISTRATOR`는 부여하지 않는다.

## 권장 구성

가장 엄격한 구성은 서비스별 User Created 정책을 만드는 방식이다. Sub Account
콘솔이 자동으로 선택하는 연관 `View/*` 액션은 유지하되, 저장 전에
`Change/*`가 0개인지 확인한다.

| 수집 범위 | 필요한 User Created View 액션 | 관리형 대안 |
| --- | --- | --- |
| Resource Manager 기반 목록·생성 시각 | `View/getResourceList` | `NCP_RESOURCE_MANAGER_VIEWER` |
| Cloud Insight 그래프 | `View/getMetric`, `View/getProductSchema`, `View/getSystemSchemaKeyList` | `NCP_CLOUD_INSIGHT_VIEWER` |
| Cloud Insight 이벤트 | `View/getEventList` | `NCP_CLOUD_INSIGHT_VIEWER` |
| Server·NIC·Block Storage·Public IP | `View/getServerInstanceList`, `View/getServerInstanceDetail`, `View/getPlacementGroupList`, `View/getNetworkInterfaceList`, `View/getNetworkInterfaceDetail`, `View/getBlockStorageInstanceList`, `View/getPublicIPInstanceList` | `NCP_VPC_SERVER_VIEWER` |
| Block Storage Snapshot·Server Image | `View/getBlockStorageSnapshotInstanceList`, `View/getMemberServerImageList` | `NCP_VPC_SERVER_VIEWER` |
| Load Balancer·Target Group·Target | `View/getLoadBalancerInstanceList`, `View/getTargetGroupList`, `View/getTargetGroupDetail`, `View/getTargetList` | `NCP_VPC_LOAD_BALANCER_VIEWER` |
| VPC·Subnet·NAT Gateway·VPC Peering | `View/getVPCList`, `View/getSubnetList`, `View/getNATGatewayList`, `View/getVPCPeeringList` | User Created 정책 사용 |
| Route Table·연결 Subnet·Route 규칙 | `View/getRouteTableList`, `View/getRouteTableDetail` 및 콘솔이 자동 추가하는 연관 View 액션 | User Created 정책 사용 |
| Network ACL·규칙 | `View/getNetworkACLList`, `View/getNetworkACLDetail` 및 콘솔이 자동 추가하는 연관 View 액션 | User Created 정책 사용 |
| ACG·규칙 | `View/getACGList`, `View/getACGDetail` | `NCP_VPC_SERVER_VIEWER` |
| VPC NAS | `View/getNASVolumeInstanceList` | `NCP_VPC_NAS_VIEWER` |
| NKS | `View/getClusterList`, `View/getWorkerNodeList`, `View/getNodePoolList`, `View/getServerInstancesList`, `View/getVPCList`, `View/getSubnetList` | User Created 정책 사용 |
| Global DNS | `View/getDomainList` | `NCP_GLOBAL_DNS_VIEWER` |
| Certificate Manager | `View/getCertificateList` | `NCP_CERTIFICATE_MANAGER_VIEWER` |

Cloud DB는 사용하는 엔진별 서비스에 다음 목록 조회 액션만 추가한다.

| Cloud DB 엔진 | 필요한 액션 | 관리형 대안 |
| --- | --- | --- |
| MySQL | `View/getDBServiceList` | `NCP_VPC_CLOUD_DB_FOR_MYSQL_VIEWER` |
| PostgreSQL | `View/getDBServiceList` | `NCP_VPC_CLOUD_DB_FOR_POSTGRESQL_VIEWER` |
| MSSQL | `View/getDBServiceList` | `NCP_VPC_CLOUD_DB_FOR_MSSQL_VIEWER` |
| MongoDB | `View/getServiceList` | `NCP_VPC_CLOUD_DB_FOR_MONGODB_VIEWER` |
| Cache | `View/getServiceList` | `NCP_VPC_CLOUD_DB_FOR_CACHE_VIEWER` |

현재 수집기는 Cloud DB 범주를 선택하면 위 다섯 엔진의 목록 API를 차례로
호출한다. 수집 경고 없이 모든 엔진을 지원하려면 다섯 서비스의 목록 View를
모두 부여한다.

## 선택 수집기: WMS와 Security Monitoring

WMS 가용성과 Security Monitoring 이벤트 수집은 고객별 **선택 기능이며 기본값은
비활성**이다. 사용하지 않는 고객에게는 아래 권한을 부여하지 않는다. 비활성
상태는 이벤트 0건이나 정상 상태가 아니라 `수집 대상 아님`으로 처리한다.

| 선택 수집기 | 실제 조회 범위 | 엄격한 최소 조회 권한 | 관리형 대안 |
| --- | --- | --- | --- |
| Web service Monitoring System | 시나리오 목록과 보고 기간의 시나리오 결과 | WMS 서비스의 `모든 조회` | `NCP_WMS_VIEWER` |
| Security Monitoring(VPC) | Anti-Virus, Anti-DDoS, IDS, IPS, WAF 이벤트 목록 | `View/getAVList`, `View/getDDoSList`, `View/getIDSList`, `View/getIPSList`, `View/getWAFList` | `NCP_VPC_SECURITY_MONITORING_VIEWER` |

WMS는 공식 서비스별 권한표에서 부여 가능한 최소 단위가 `모든 조회 또는 모든
변경`으로 정의되어 있고, WMS 권한 관리 문서도 조회 전용 관리형 정책
`NCP_WMS_VIEWER`를 제공한다. 세부 조회 액션 이름은 해당 공식 문서에 공개되어
있지 않으므로 `View/get...` 형태의 액션명을 임의로 만들지 않는다. 정책 구성 시
`NCP_WMS_VIEWER`를 사용하거나 WMS 서비스의 `모든 조회`만 선택하고,
`NCP_WMS_MANAGER`와 변경 권한은 부여하지 않는다. 수집 전에 WMS 이용 신청과
조회할 시나리오가 별도로 준비되어 있어야 한다.

Security Monitoring은 현재 수집기가 목록 API만 호출하므로 위 다섯 개 User
Created View 액션으로 제한할 수 있다. 이벤트 상세 조회,
`View/getNotificationSetting`, 예외 요청, 통보 대상 관리, 상품 신청을 포함한
모든 `Change/*` 액션은 필요하지 않다. 관리 편의를 위해 관리형 정책을 쓸 때도
`NCP_VPC_SECURITY_MONITORING_MANAGER`가 아닌 조회 전용
`NCP_VPC_SECURITY_MONITORING_VIEWER`를 사용한다. 이 수집기는 VPC 전용이며,
계정·리전에서 신청하지 않았거나 제공되지 않는 보안 상품은 권한으로 활성화되지
않으므로 해당 고객의 선택 수집기를 비활성화한다.

## Resource Manager 하나로 표시하는 범주

다음 범주는 개별 서비스 API를 호출하지 않고 Resource Manager의 결과를
분류해 목록으로 표시한다.

- Object Storage
- Auto Scaling
- Virtual Private Gateway
- IPsec VPN
- Cloud Connect
- Global Edge
- Global Traffic Manager
- API Gateway
- Backup
- Archive Storage
- Search Engine Service
- Cloud Data Streaming Service
- Cloud Hadoop
- Data Stream
- Cloud Functions
- 보안 서비스(WAF·IDS·IPS·DDoS)

따라서 현재 코드에는 위 서비스 각각의 Viewer 권한이 필요하지 않다.
`View/getResourceList`만 사용한다. 다만 Resource Manager가 통합하지 않거나
반환하지 않는 자원과 서비스별 세부 속성은 표시를 보장할 수 없다.

Resource Manager 목록 권한은 계정의 여러 서비스 자원명과 메타데이터를 함께
볼 수 있는 넓은 읽기 권한이다. 이 범위도 허용할 수 없다면 위 범주를 고객의
대표 인프라 선택에서 해제하고 Resource Manager 권한 자체를 제거한다. 이 경우
직접 API 자원의 생성 시각 보강도 제한될 수 있다.

## 모니터링 그래프 권한

서버, Load Balancer, Cloud DB, Kubernetes Service, NAS, Object Storage,
Auto Scaling, Search Engine Service, Cloud Data Streaming Service,
Cloud Hadoop, Data Stream 그래프는 모두 Cloud Insight API로 조회한다. 각
서비스의 네이티브 모니터링 권한은 현재 코드에서 사용하지 않는다.

권한만으로 데이터가 생기지는 않는다. 해당 상품이 Cloud Insight 연동 대상이어야
하고, 계정·리전·플랫폼에 시스템 상품과 metric dimension이 실제로 등록돼 있어야
한다. 서버 Extended Metric은 별도 상세 모니터링 신청이 필요할 수 있다.

## 네트워크 구성 스냅샷의 시간 기준

Route Table, 연결 Subnet, Route 규칙, ACG 규칙, Network ACL 규칙의 목록 API에는
과거 기준 시각을 지정하는 요청 파라미터가 없다. 따라서 보고서가 임의의 과거
기간을 지정해도 NCP API에서 그 당시 설정을 직접 복원할 수 없다.

보고서 생성 과정에서 조회한 구성은 일반 `report_snapshots` JSON에 합치지 않고
`network_configuration_snapshots` 전용 테이블에 실제 `captured_at`과 함께
저장한다. 이후 보고 기간 안에 실제 수집된 스냅샷이 있을 때만 기간 내 단일
시점 데이터로 재사용한다. 없으면 이번 보고서 생성시점의 현재 설정을 별도로
백업하고, 보고서에 **보고 대상 기간의 과거 상태가 아님**을 명시한다.

이 기능은 단일 시점 백업이므로 기간 전체의 변경 이력은 아니다. 변경 이력이
필요하면 Cloud Activity Tracer의 설정 변경 이벤트를 별도로 결합해야 한다.

## 의도적으로 제거한 범주

CDN과 Container Registry 직접 조회는 제거했다. 고객 설정 화면에서도 선택지를
제거했으므로 이 보고서를 위해 Global CDN/CDN+/Container Registry 권한을
부여하지 않는다.

## 주의할 관리형 정책

- Network Interface의 공식 권한표는 `View/getNetworkInterfaceList`의 연관
  액션으로 `Change/setSecondaryIP`를 제시한다. 보고서 수집기는 쓰기 API를
  호출하지 않으므로 이 액션을 자동으로 권고하지 않는다. 콘솔에서 자동 선택된
  쓰기 액션은 그대로 승인하지 말고 보안 검토와 실제 목록 API 테스트를 거친다.
- `NCP_VPC_KUBERNETES_SERVICE_VIEWER`는 공식 설명상 NAS `MANAGER` 권한을
  포함하므로 엄격한 최소 권한 계정에는 사용하지 않는다. NKS User Created
  정책에서 `View/getClusterList`를 선택한다.
- VPC는 선택한 VPC·Subnet·Route Table·Network ACL 범위의 목록/상세 View만
  User Created 정책으로 만든다. 규칙 조회 때문에 `Change/*`는 필요하지 않다.
- Load Balancer/NAS의 네이티브 모니터 액션은 보고서 그래프에 필요하지 않다.
- DB 대시보드, 로그, 백업, 복원 액션은 보고서 수집에 필요하지 않다.

## 보고서의 권한 진단 표시 기준

- NCP 오류 응답이 `View/getDomainList` 같은 액션을 직접 포함하면
  **NCP 응답 확인**으로 표시한다.
- 일반 403처럼 액션이 없는 응답은 실제 **호출 API**와 이 문서의 권한표를
  연결해 **호출 API 기준 권고**로 표시한다. 이는 실제 누락 권한 확정값이
  아니며 서비스 제공 환경, 리전, 접근 가능 소스도 함께 점검한다.
- `Change/*`가 응답에 포함돼도 조회 권한으로 권고하지 않고 쓰기 권한 감지
  경고로 분리한다.
- 과거 스냅샷에 호출 API가 저장되지 않은 경우 `API 미확인 (구형 진단 데이터)`로
  표시하며 권한명을 추측하지 않는다.

## 민간·공공 공통 적용과 접근 소스

민간과 공공 환경은 위 정책명과 View 액션을 동일하게 적용할 수 있다. 단, 공공
환경에서 제공되지 않는 상품은 권한을 부여해도 수집할 수 없다.

VPC 안의 Pod가 API를 호출한다면 Sub Account의 접근 가능 소스에 NAT Gateway
공인 IP만 등록하지 않는다. NCP 공식 안내에 따르면 IP만 접근 소스로 지정하면
VPC Server의 API 접근이 허용되지 않을 수 있으므로 실제 실행 VPC 또는 VPC
Server도 접근 가능 소스로 등록한다.

## 공식 문서

- [Resource Manager 권한 관리](https://guide.ncloud-docs.com/docs/management-rmgr-subaccount)
- [Cloud Insight 권한 관리](https://guide.ncloud-docs.com/docs/cloudinsight-cloudinsightsubaccount)
- [Server 권한 관리](https://guide.ncloud-docs.com/docs/server-subaccount-vpc)
- [Load Balancer 권한 관리](https://guide.ncloud-docs.com/docs/loadbalancer-subaccount-vpc)
- [VPC 권한 관리](https://guide.ncloud-docs.com/docs/networking-vpc-vpcetc)
- [Route Table 목록 API](https://api.ncloud-docs.com/docs/networking-vpc-routetable-getroutetablelist)
- [Route 규칙 목록 API](https://api.ncloud-docs.com/docs/networking-vpc-routetable-getroutelist)
- [Network ACL 목록 API](https://api.ncloud-docs.com/docs/networking-vpc-networkacl-getnetworkacllist)
- [Network ACL 규칙 목록 API](https://api.ncloud-docs.com/docs/networking-vpc-networkacl-getnetworkaclrulelist)
- [ACG 목록 API](https://api.ncloud-docs.com/docs/compute-vserver-acg-getaccesscontrolgrouplist)
- [ACG 규칙 목록 API](https://api.ncloud-docs.com/docs/compute-vserver-acg-getaccesscontrolgrouprulelist)
- [NAS 권한 관리](https://guide.ncloud-docs.com/docs/nas-subaccount)
- [NKS 권한 관리](https://guide.ncloud-docs.com/docs/compute-nks-nks-subaccount)
- [Global DNS 권한 관리](https://guide.ncloud-docs.com/docs/globaldns-subaccount)
- [Certificate Manager 권한 관리](https://guide.ncloud-docs.com/docs/security-security-15-2)
- [Web service Monitoring System 권한 관리](https://guide.ncloud-docs.com/docs/wms-subaccount)
- [서비스별 부여 가능한 최소 권한 단위](https://guide.ncloud-docs.com/docs/subaccount-servicelist)
- [Security Monitoring 권한 관리(VPC)](https://guide.ncloud-docs.com/docs/securitymonitoring-subaccount-vpc)
- [Sub Account 접근 가능 소스 안내](https://guide.ncloud-docs.com/docs/subaccount-use)
- [공공 Resource Manager 권한 관리](https://guide-gov.ncloud-docs.com/docs/management-rmgr-subaccount)
- [공공 Cloud Insight 권한 관리](https://guide-gov.ncloud-docs.com/docs/cloudinsight-cloudinsightsubaccount)

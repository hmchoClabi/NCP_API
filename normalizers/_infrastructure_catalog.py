"""인프라 정규화에 사용하는 고정 분류 및 공급자 매핑 카탈로그입니다.

NCP Resource Manager와 Cloud DB가 반환하는 상품·리소스 식별자는 정규화
계약의 일부이므로 변환 로직과 분리해 한곳에서 관리합니다.
"""

COMMON_FIELDS = (
    "category",
    "category_label",
    "service_name",
    "resource_type",
    "resource_id",
    "resource_name",
    "status",
    "region_code",
    "zone_code",
    "platform",
    "create_time",
    "details",
)
CATEGORY_LABELS = {
    "SERVER": "서버",
    "BLOCK_STORAGE": "블록 스토리지",
    "LOAD_BALANCER": "로드밸런서",
    "TARGET_GROUP": "LB Target Group",
    "NAS": "NAS",
    "CLOUD_DB": "Cloud DB",
    "KUBERNETES": "Kubernetes",
    "CDN": "CDN",
    "OBJECT_STORAGE": "Object Storage",
    "VPC": "VPC",
    "SUBNET": "Subnet",
    "NAT_GATEWAY": "NAT Gateway",
    "PUBLIC_IP": "Public IP",
    "VPC_PEERING": "VPC Peering",
    "VIRTUAL_PRIVATE_GATEWAY": "Virtual Private Gateway",
    "AUTO_SCALING": "Auto Scaling",
    "GLOBAL_EDGE": "Global Edge",
    "GLOBAL_DNS": "Global DNS",
    "GLOBAL_TRAFFIC_MANAGER": "Global Traffic Manager",
    "API_GATEWAY": "API Gateway",
    "CERTIFICATE": "Certificate",
    "BLOCK_STORAGE_SNAPSHOT": "Block Storage Snapshot",
    "SERVER_IMAGE": "Server Image",
    "BACKUP": "Backup",
    "ARCHIVE_STORAGE": "Archive Storage",
    "SEARCH_ENGINE": "Search Engine Service",
    "DATA_STREAMING": "Cloud Data Streaming Service",
    "CLOUD_HADOOP": "Cloud Hadoop",
    "DATA_STREAM": "Data Stream",
    "CLOUD_FUNCTIONS": "Cloud Functions",
    "CONTAINER_REGISTRY": "Container Registry",
    "SECURITY_SERVICE": "Security Service",
    "IPSEC_VPN": "IPsec VPN",
    "CLOUD_CONNECT": "Cloud Connect",
}
CATEGORY_ORDER = {
    category: index
    for index, category in enumerate(CATEGORY_LABELS)
}
CATEGORY_ALIASES = {
    **{category: category for category in CATEGORY_LABELS},
    "CDB": "CLOUD_DB",
    "NKS": "KUBERNETES",
    "LB": "LOAD_BALANCER",
    "NATGW": "NAT_GATEWAY",
    "VPCPEERING": "VPC_PEERING",
    "VGW": "VIRTUAL_PRIVATE_GATEWAY",
    "AUTOSCALING": "AUTO_SCALING",
    "GTM": "GLOBAL_TRAFFIC_MANAGER",
    "APIGW": "API_GATEWAY",
    "SNAPSHOT": "BLOCK_STORAGE_SNAPSHOT",
    "IPSECVPN": "IPSEC_VPN",
    "CLOUDCONNECT": "CLOUD_CONNECT",
}

_SENSITIVE_KEY_FRAGMENTS = (
    "accesskey",
    "apikey",
    "credential",
    "endpoint",
    "login",
    "password",
    "privatekey",
    "raw",
    "secret",
    "signature",
    "token",
)
_EXCLUDED_RESOURCE_MARKERS = (
    "ALARM",
    "EVENT",
    "IAM",
    "POLICY",
    "ROLE",
    "RULE",
    "SUBACCOUNT",
    "USER",
)

_RESOURCE_MANAGER_PRODUCTS = {
    "SERVER": frozenset({"SERVER", "VPCSERVER", "VSERVER"}),
    "BLOCK_STORAGE": frozenset({"SERVER", "VPCSERVER", "VSERVER"}),
    "LOAD_BALANCER": frozenset(
        {"LOADBALANCER", "VPCLOADBALANCER", "VLOADBALANCER"}
    ),
    "TARGET_GROUP": frozenset(),
    "NAS": frozenset({"NAS", "VPCNAS", "VNAS"}),
    "CLOUD_DB": frozenset(
        {
            "CLOUDDB",
            "CDBSERVERLESS",
            "CLOUDDBFORCACHE",
            "CLOUDDBFORMONGODB",
            "CLOUDDBFORMSSQL",
            "CLOUDDBFORMYSQL",
            "CLOUDDBFORPOSTGRESQL",
            "CLOUDDBFORREDIS",
            "VPCCLOUDDBFORCACHE",
            "VPCCLOUDDBFORMONGODB",
            "VPCCLOUDDBFORMSSQL",
            "VPCCLOUDDBFORMYSQL",
            "VPCCLOUDDBFORPOSTGRESQL",
            "VPCCLOUDDBFORREDIS",
            "VCACHE",
            "VMONGODB",
            "VMSSQL",
            "VMYSQL",
            "VPOSTGRESQL",
        }
    ),
    "KUBERNETES": frozenset(
        {
            "KUBERNETESSERVICE",
            "NCLOUDKUBERNETESSERVICE",
            "NKS",
            "VPCKUBERNETESSERVICE",
        }
    ),
    "CDN": frozenset({"CDN", "CDNPLUS", "GCDN", "GLOBALCDN"}),
    "OBJECT_STORAGE": frozenset({"OBJECTSTORAGE"}),
    "VPC": frozenset({"VPC"}),
    "SUBNET": frozenset({"VPC"}),
    "NAT_GATEWAY": frozenset({"VPC"}),
    "PUBLIC_IP": frozenset({"SERVER", "VPCSERVER", "VSERVER"}),
    "VPC_PEERING": frozenset({"VPC"}),
    "VIRTUAL_PRIVATE_GATEWAY": frozenset({"VPC"}),
    "AUTO_SCALING": frozenset({"AUTOSCALING", "VPCAUTOSCALING"}),
    "GLOBAL_EDGE": frozenset({"GLOBALEDGE"}),
    "GLOBAL_DNS": frozenset({"GLOBALDNS"}),
    "GLOBAL_TRAFFIC_MANAGER": frozenset({"GLOBALTRAFFICMANAGER"}),
    "API_GATEWAY": frozenset({"APIGATEWAY"}),
    "CERTIFICATE": frozenset({"CERTIFICATEMANAGER"}),
    "BLOCK_STORAGE_SNAPSHOT": frozenset(
        {"SERVER", "VPCSERVER", "VSERVER"}
    ),
    "SERVER_IMAGE": frozenset({"SERVER", "VPCSERVER", "VSERVER"}),
    "BACKUP": frozenset({"BACKUP", "VPCBACKUP"}),
    "ARCHIVE_STORAGE": frozenset({"ARCHIVESTORAGE"}),
    "SEARCH_ENGINE": frozenset({"SEARCHENGINE", "VPCSEARCHENGINE"}),
    "DATA_STREAMING": frozenset({"CLOUDDATASTREAMINGSERVICE"}),
    "CLOUD_HADOOP": frozenset({"CLOUDHADOOP", "VPCCLOUDHADOOP"}),
    "DATA_STREAM": frozenset({"DATASTREAM", "VPCDATASTREAM"}),
    "CLOUD_FUNCTIONS": frozenset({"CLOUDFUNCTIONS", "VPCCLOUDFUNCTIONS"}),
    "CONTAINER_REGISTRY": frozenset({"CONTAINERREGISTRY"}),
    "SECURITY_SERVICE": frozenset(
        {"SECURITYMONITORING", "VPCSECURITYMONITORING"}
    ),
    "IPSEC_VPN": frozenset({"IPSECVPN", "VPCIPSECVPN"}),
    "CLOUD_CONNECT": frozenset({"CLOUDCONNECT", "VPCCLOUDCONNECT"}),
}
_RESOURCE_MANAGER_TYPES = {
    "SERVER": frozenset(
        {"SERVER", "SERVERINSTANCE", "VSERVER", "VSERVERINSTANCE"}
    ),
    "BLOCK_STORAGE": frozenset(
        {"BLOCKSTORAGE", "BLOCKSTORAGEINSTANCE", "STORAGE"}
    ),
    "LOAD_BALANCER": frozenset(
        {"INSTANCE", "LOADBALANCER", "LOADBALANCERINSTANCE"}
    ),
    "TARGET_GROUP": frozenset(),
    "NAS": frozenset(
        {"NAS", "NASVOLUME", "NASVOLUMEINSTANCE", "VOLUME"}
    ),
    "CLOUD_DB": frozenset(
        {
            "CLOUDCACHEINSTANCE",
            "CLOUDDBINSTANCE",
            "CLOUDMONGODBINSTANCE",
            "CLOUDMSSQLINSTANCE",
            "CLOUDMYSQLINSTANCE",
            "CLOUDPOSTGRESQLINSTANCE",
            "SERVICE",
        }
    ),
    "KUBERNETES": frozenset(
        {"CLUSTER", "KUBERNETESCLUSTER", "NKSCLUSTER"}
    ),
    "CDN": frozenset(
        {
            "CDNINSTANCE",
            "CDNPLUSINSTANCE",
            "GLOBALCDNINSTANCE",
            "SERVICE",
        }
    ),
    "OBJECT_STORAGE": frozenset({"BUCKET", "OBJECTSTORAGEBUCKET"}),
    "VPC": frozenset({"VPC"}),
    "SUBNET": frozenset({"SUBNET"}),
    "NAT_GATEWAY": frozenset({"NATGATEWAY"}),
    "PUBLIC_IP": frozenset({"PUBLICIP"}),
    "VPC_PEERING": frozenset({"VPCPEERING"}),
    "VIRTUAL_PRIVATE_GATEWAY": frozenset({"VIRTUALPRIVATEGATEWAY"}),
    "AUTO_SCALING": frozenset({"AUTOSCALINGGROUP"}),
    "GLOBAL_EDGE": frozenset({"EDGE"}),
    "GLOBAL_DNS": frozenset({"DOMAIN"}),
    "GLOBAL_TRAFFIC_MANAGER": frozenset({"PROFILE"}),
    "API_GATEWAY": frozenset({"API"}),
    "CERTIFICATE": frozenset({"CERTIFICATE"}),
    "BLOCK_STORAGE_SNAPSHOT": frozenset({"SNAPSHOT"}),
    "SERVER_IMAGE": frozenset({"SERVERIMAGE"}),
    "BACKUP": frozenset({"DBINSTANCE", "RESOURCE", "STORAGE"}),
    "ARCHIVE_STORAGE": frozenset({"CONTAINER"}),
    "SEARCH_ENGINE": frozenset({"CLUSTER"}),
    "DATA_STREAMING": frozenset({"CLUSTER"}),
    "CLOUD_HADOOP": frozenset({"CLUSTER"}),
    "DATA_STREAM": frozenset({"TOPIC"}),
    "CLOUD_FUNCTIONS": frozenset({"NAMESPACE"}),
    "CONTAINER_REGISTRY": frozenset({"REGISTRY"}),
    "SECURITY_SERVICE": frozenset({"AV", "DDOS", "IDS", "IPS", "WAF"}),
    "IPSEC_VPN": frozenset({"IPSECVPNGATEWAY"}),
    "CLOUD_CONNECT": frozenset({"CLOUDCONNECT"}),
}

_CDB_SPECS = {
    "MYSQL": {
        "prefix": "cloudMysql",
        "service": "Cloud DB for MySQL",
        "resource_type": "CloudMysqlInstance",
    },
    "POSTGRESQL": {
        "prefix": "cloudPostgresql",
        "service": "Cloud DB for PostgreSQL",
        "resource_type": "CloudPostgresqlInstance",
    },
    "MSSQL": {
        "prefix": "cloudMssql",
        "service": "Cloud DB for MSSQL",
        "resource_type": "CloudMssqlInstance",
    },
    "MONGODB": {
        "prefix": "cloudMongoDb",
        "service": "Cloud DB for MongoDB",
        "resource_type": "CloudMongoDbInstance",
    },
    "CACHE": {
        "prefix": "cloudCache",
        "service": "Cloud DB for Cache",
        "resource_type": "CloudCacheInstance",
    },
}

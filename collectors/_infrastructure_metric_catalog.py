"""인프라 Cloud Insight 수집에 사용하는 고정 메트릭 카탈로그입니다.

공급자 메트릭 이름과 dimension 규칙은 조회 계약의 일부이므로 수집 로직과
분리해 한곳에서 관리합니다. 값의 철자와 순서는 응답 호환성을 위해 유지합니다.
"""

from zoneinfo import ZoneInfo


MAX_QUERY_SIZE = 20
MAX_SERIES = 200
MAX_DISCOVERY_TARGETS = 50
KST = ZoneInfo("Asia/Seoul")

MONITORED_CATEGORIES = (
    "LOAD_BALANCER",
    "TARGET_GROUP",
    "CDB",
    "NKS",
    "NAS",
    "OBJECT_STORAGE",
    "AUTO_SCALING",
    "SEARCH_ENGINE",
    "DATA_STREAMING",
    "CLOUD_HADOOP",
    "DATA_STREAM",
)
OUTPUT_CATEGORIES = {
    "LOAD_BALANCER": "LOAD_BALANCER",
    "TARGET_GROUP": "LOAD_BALANCER",
    "CDB": "CLOUD_DB",
    "NKS": "KUBERNETES",
    "NAS": "NAS",
    "OBJECT_STORAGE": "OBJECT_STORAGE",
    "AUTO_SCALING": "AUTO_SCALING",
    "SEARCH_ENGINE": "SEARCH_ENGINE",
    "DATA_STREAMING": "DATA_STREAMING",
    "CLOUD_HADOOP": "CLOUD_HADOOP",
    "DATA_STREAM": "DATA_STREAM",
}
CATEGORY_ALIASES = {
    "LB": "LOAD_BALANCER",
    "LOADBALANCER": "LOAD_BALANCER",
    "LOAD_BALANCER": "LOAD_BALANCER",
    "TARGETGROUP": "TARGET_GROUP",
    "TARGET_GROUP": "TARGET_GROUP",
    "DATABASE": "CDB",
    "CLOUD_DB": "CDB",
    "CLOUD_DATABASE": "CDB",
    "CDB": "CDB",
    "K8S": "NKS",
    "KUBERNETES": "NKS",
    "KUBERNETES_SERVICE": "NKS",
    "NCLOUD_KUBERNETES_SERVICE": "NKS",
    "NKS": "NKS",
    "NAS": "NAS",
    "OBJECT_STORAGE": "OBJECT_STORAGE",
    "OBJECTSTORAGE": "OBJECT_STORAGE",
    "AUTO_SCALING": "AUTO_SCALING",
    "AUTOSCALING": "AUTO_SCALING",
    "AUTO_SCALING_GROUP": "AUTO_SCALING",
    "SEARCH_ENGINE": "SEARCH_ENGINE",
    "SEARCH_ENGINE_SERVICE": "SEARCH_ENGINE",
    "DATA_STREAMING": "DATA_STREAMING",
    "CLOUD_DATA_STREAMING": "DATA_STREAMING",
    "CLOUD_DATA_STREAMING_SERVICE": "DATA_STREAMING",
    "CDSS": "DATA_STREAMING",
    "CLOUD_HADOOP": "CLOUD_HADOOP",
    "HADOOP": "CLOUD_HADOOP",
    "DATA_STREAM": "DATA_STREAM",
    "DATASTREAM": "DATA_STREAM",
}

INTERVAL_MINUTES = {
    "Min1": 1,
    "Min5": 5,
    "Min30": 30,
    "Hour2": 120,
    "Day1": 1440,
}
AGGREGATION_ORDER = ("AVG", "SUM", "MAX", "MIN", "COUNT")

LB_METRICS = {
    "connections_per_second": {
        "aliases": (
            "connections_per_second",
            "connections_per_second2",
            "connection_per_second",
            "connections_per_sec",
            "conn_cps",
            "cps",
        ),
        "label": "초당 연결 수",
        "unit": "count/s",
        "aggregations": ("AVG", "MAX", "SUM", "MIN", "COUNT"),
    },
    "concurrent_session": {
        "aliases": (
            "concurrent_session",
            "concurrent_sessions",
            "concurrent_session_count",
        ),
        "label": "동시 세션",
        "unit": "count",
        "aggregations": ("AVG", "MAX", "SUM", "MIN", "COUNT"),
    },
    "traffic_in_byte": {
        "aliases": (
            "traffic_in_byte",
            "traffic_in_bytes",
            "bytes_in",
            "inbound_traffic_byte",
        ),
        "label": "유입 트래픽",
        "unit": "bytes/sec",
        "aggregations": ("AVG", "MAX", "MIN", "SUM", "COUNT"),
    },
    "traffic_out_byte": {
        "aliases": (
            "traffic_out_byte",
            "traffic_out_bytes",
            "bytes_out",
            "outbound_traffic_byte",
        ),
        "label": "유출 트래픽",
        "unit": "bytes/sec",
        "aggregations": ("AVG", "MAX", "MIN", "SUM", "COUNT"),
    },
}

TARGET_GROUP_METRICS = {
    "available_host_count": {
        "label": "Ready Target 수 (구간 최소)",
        "unit": "count",
        "force_unit": True,
        "aggregations": ("MIN",),
    },
    "unavailable_host_count": {
        "label": "Unready Target 수 (구간 최대)",
        "unit": "count",
        "force_unit": True,
        "aggregations": ("MAX",),
    },
}

# Cloud DB 지표는 같은 의미군 안에서도 서로 다른 운영 정보를 담는다.
# 예를 들어 전체 연결 수와 실행 중 연결 수를 하나로 축약하지 않고 각각
# 선택한다. SearchMetricList가 실제로 반환한 이름만 이 허용 목록과 대조하므로
# 상품 세대나 계정에서 제공하지 않는 지표를 임의로 조회하지 않는다.
CDB_CATALOG = {
    "mysql": (
        {
            "key": "cpu",
            "aliases": ("cpu_total", "cpu_pct"),
            "label": "CPU 사용률",
        },
        {
            "key": "memory_ratio",
            "aliases": ("mem_pct",),
            "label": "메모리 사용률",
        },
        {
            "key": "memory_used",
            "aliases": ("mem_used",),
            "label": "메모리 사용량",
        },
        {
            "key": "storage_used",
            "aliases": ("disk_mysql_used",),
            "label": "스토리지 사용량",
        },
        {
            "key": "storage_free",
            "aliases": ("disk_mysql_free",),
            "label": "스토리지 여유 공간",
        },
        {
            "key": "connections_total",
            "aliases": ("mysql_totalconn",),
            "label": "전체 연결 수",
            "unit": "count",
            "force_unit": True,
        },
        {
            "key": "connections_active",
            "aliases": ("mysql_runconn",),
            "label": "실행 중 연결 수",
            "unit": "count",
            "force_unit": True,
        },
        {
            "key": "replication_lag",
            "aliases": ("mysql_slavedelay",),
            "label": "복제 지연 (구간 최대)",
            "aggregations": ("MAX", "AVG", "MIN"),
        },
        {
            "key": "slow_query",
            "aliases": ("mysql_slow",),
            "label": "Slow Query",
        },
    ),
    "postgresql": (
        {
            "key": "cpu",
            "aliases": ("cpu_total", "cpu_pct"),
            "label": "CPU 사용률",
        },
        {
            "key": "memory_ratio",
            "aliases": ("mem_pct",),
            "label": "메모리 사용률",
        },
        {
            "key": "memory_used",
            "aliases": ("mem_used",),
            "label": "메모리 사용량",
        },
        {
            "key": "storage_used",
            "aliases": ("disk_usage",),
            "label": "스토리지 사용량",
        },
        {
            "key": "sessions_total",
            "aliases": ("total_session_count",),
            "label": "전체 세션 수",
            "unit": "count",
            "force_unit": True,
        },
        {
            "key": "sessions_active",
            "aliases": ("active_session_count",),
            "label": "활성 세션 수",
            "unit": "count",
            "force_unit": True,
        },
        {
            "key": "replication_lag",
            "aliases": (
                "replication_lag",
                "replication_lag_seconds",
                "replication_delay",
            ),
            "label": "복제 지연 (구간 최대)",
            "aggregations": ("MAX", "AVG", "MIN"),
        },
        {
            "key": "slow_query",
            "aliases": ("slowquery", "slow_query_count"),
            "label": "Slow Query",
        },
    ),
    "cache": (
        {
            "key": "cpu_user",
            "aliases": ("cpu_user",),
            "label": "CPU 사용자 사용률",
        },
        {
            "key": "cpu_system",
            "aliases": ("cpu_sys",),
            "label": "CPU 시스템 사용률",
        },
        {
            "key": "memory_ratio",
            "aliases": (
                "cache_memory_pct",
                "redis_memory_pct",
                "mem_pct",
            ),
            "label": "메모리 사용률",
        },
        {
            "key": "storage_ratio",
            "aliases": ("disk_data_pct",),
            "label": "스토리지 사용률",
        },
        {
            "key": "connections_current",
            "aliases": (
                "cache_connected_clients",
                "redis_connected_clients",
            ),
            "label": "현재 연결 수",
            "unit": "count",
            "force_unit": True,
        },
    ),
    "mssql": (
        {
            "key": "cpu",
            "aliases": ("cpu", "cpu_total"),
            "label": "CPU 사용률",
        },
        {
            "key": "memory_available",
            "aliases": ("memory_available",),
            "label": "가용 메모리",
        },
        {
            "key": "storage_free_ratio",
            "aliases": ("disk_free_percent",),
            "label": "스토리지 여유율",
        },
        {
            "key": "storage_free",
            "aliases": ("disk_free",),
            "label": "스토리지 여유 공간",
        },
        {
            "key": "connections_current",
            "aliases": ("mssql_user_connection",),
            "label": "현재 연결 수",
            "unit": "count",
            "force_unit": True,
        },
    ),
    "mongodb": (
        {
            "key": "cpu",
            "aliases": ("cpu_total", "cpu_pct"),
            "label": "CPU 사용률",
        },
        {
            "key": "memory_ratio",
            "aliases": ("mem_pct",),
            "label": "메모리 사용률",
        },
        {
            "key": "storage_used",
            "aliases": ("disk_mongodb_used",),
            "label": "스토리지 사용량",
        },
        {
            "key": "storage_free",
            "aliases": ("disk_mongodb_free",),
            "label": "스토리지 여유 공간",
        },
        {
            "key": "connections_current",
            "aliases": ("connections_current",),
            "label": "현재 연결 수",
            "unit": "count",
            "force_unit": True,
        },
        {
            "key": "connections_active",
            "aliases": ("connections_active",),
            "label": "활성 연결 수",
            "unit": "count",
            "force_unit": True,
        },
    ),
    "serverless": (
        {
            "key": "unit_utilization",
            "aliases": ("unit_utilization",),
            "label": "DB Unit 사용률",
        },
        {
            "key": "cpu",
            "aliases": ("cpu_total",),
            "label": "CPU 사용량",
        },
        {
            "key": "memory_used",
            "aliases": ("mem_used",),
            "label": "메모리 사용량",
        },
        {
            "key": "storage_used",
            "aliases": ("disk_mysql_used", "disk_used"),
            "label": "스토리지 사용량",
        },
        {
            "key": "connections_total",
            "aliases": ("mysql_totalconn", "mysql_total_connections"),
            "label": "전체 연결 수",
            "unit": "count",
            "force_unit": True,
        },
        {
            "key": "connections_active",
            "aliases": ("mysql_runconn", "mysql_running_threads"),
            "label": "실행 중 연결 수",
            "unit": "count",
            "force_unit": True,
        },
        {
            "key": "slow_query",
            "aliases": ("mysql_slow",),
            "label": "Slow Query",
        },
    ),
}
CDB_LABELS = {
    "cpu": "CPU",
    "memory": "메모리",
    "storage": "스토리지",
    "connection": "연결 수",
}

NKS_METRICS = {
    "node_ready_count": ("Ready 노드 수", "count"),
    "node_not_ready_count": ("Not Ready 노드 수", "count"),
    "node_available_ratio": ("노드 가용률", "%"),
}

# Only documented Cloud Insight metric names are selected. Runtime schema
# discovery still decides which of these metrics and aggregations are
# actually available for an account.
RESOURCE_METRICS = {
    "NAS": {
        "volume_size": {
            "label": "볼륨 전체 용량",
            "unit": "bytes",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "volume_used_size": {
            "label": "볼륨 사용량",
            "unit": "bytes",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "volume_used_ratio": {
            "label": "볼륨 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
    },
    "OBJECT_STORAGE": {
        "bucket_size": {
            "label": "버킷 사용량",
            "unit": "bytes",
            "aggregations": ("AVG",),
        },
        "object_count": {
            "label": "객체 수",
            "unit": "count",
            "aggregations": ("AVG",),
        },
    },
    "AUTO_SCALING": {
        "avg_cpu_used_rto": {
            "label": "평균 CPU 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "mem_usert": {
            "label": "메모리 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "avg_fs_usert": {
            "label": "평균 파일 시스템 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
    },
    "SEARCH_ENGINE": {
        "cluster_node_count": {
            "label": "클러스터 노드 수",
            "unit": "count",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cluster_documents_total": {
            "label": "클러스터 문서 수",
            "unit": "count",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cluster_disk_used": {
            "label": "클러스터 디스크 사용량",
            "unit": "GB",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cpu_total": {
            "label": "CPU 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "mem_usage": {
            "label": "메모리 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "disk_used": {
            "label": "노드 디스크 사용량",
            "unit": "GB",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
    },
    "DATA_STREAMING": {
        "cluster_total_partition": {
            "label": "전체 파티션 수",
            "unit": "count",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cluster_total_topic": {
            "label": "전체 토픽 수",
            "unit": "count",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cluster_total_message": {
            "label": "전체 메시지 수",
            "unit": "count",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cluster_messages_in_sec_mean": {
            "label": "초당 수신 메시지",
            "unit": "count/s",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cluster_bytes_in_sec": {
            "label": "초당 수신 바이트",
            "unit": "bytes/s",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cluster_bytes_out_sec": {
            "label": "초당 송신 바이트",
            "unit": "bytes/s",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "cpu_total": {
            "label": "CPU 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "mem_usage": {
            "label": "메모리 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "disk_used_ratio": {
            "label": "디스크 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
    },
    "CLOUD_HADOOP": {
        "avg_cpu_used_rto": {
            "label": "평균 CPU 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "active_nodes": {
            "label": "활성 노드 수",
            "unit": "count",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "queue_used_memory_percent": {
            "label": "큐 메모리 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "queue_used_v_cores_percent": {
            "label": "큐 vCore 사용률",
            "unit": "%",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
    },
    "DATA_STREAM": {
        "bytes_in_total": {
            "label": "수신 바이트 처리량",
            "unit": "bytes",
            "aggregations": ("AVG", "MAX", "SUM", "MIN"),
        },
        "messages_in_total": {
            "label": "수신 메시지 처리량",
            "unit": "count",
            "aggregations": ("AVG", "MAX", "SUM", "MIN"),
        },
        "bytes_out_total": {
            "label": "송신 바이트 처리량",
            "unit": "bytes",
            "aggregations": ("AVG", "MAX", "SUM", "MIN"),
        },
        "log_size": {
            "label": "토픽 로그 크기",
            "unit": "bytes",
            "aggregations": ("AVG", "MAX", "MIN"),
        },
        "consumer_group_lag": {
            "label": "컨슈머 그룹 지연",
            "unit": "count",
            "aggregations": ("MAX",),
        },
    },
}

PRIMARY_ID_DIMENSIONS = {
    "LOAD_BALANCER": "instanceId",
    "TARGET_GROUP": "targetGroupNo",
    "CDB": "instanceNo",
    "NKS": "clusterUUID",
    "NAS": "instanceNo",
    "OBJECT_STORAGE": "resourceId",
    "AUTO_SCALING": "autoScalingGroupNo",
    "SEARCH_ENGINE": "Svc_group_instance_no",
    "DATA_STREAMING": "instanceNo",
    "CLOUD_HADOOP": "instanceNo",
    "DATA_STREAM": "topicId",
}
CATEGORY_ID_DIMENSIONS = {
    "LOAD_BALANCER": frozenset(
        {
            "instanceid",
            "loadbalancerid",
            "loadbalancerinstanceno",
            "loadbalancerno",
        }
    ),
    "TARGET_GROUP": frozenset({"targetgroupno"}),
    "CDB": frozenset(
        {"instanceno", "dbinstanceno", "clouddbinstanceno"}
    ),
    "NKS": frozenset({"clusteruuid", "clusterid"}),
    "NAS": frozenset({"instanceno", "nasvolumeinstanceno"}),
    "OBJECT_STORAGE": frozenset({"resourceid"}),
    "AUTO_SCALING": frozenset({"autoscalinggroupno"}),
    "SEARCH_ENGINE": frozenset({"svcgroupinstanceno"}),
    "DATA_STREAMING": frozenset({"instanceno"}),
    "CLOUD_HADOOP": frozenset({"instanceno"}),
    "DATA_STREAM": frozenset({"topicid"}),
}
CATEGORY_DETAIL_ID_FIELDS = {
    "LOAD_BALANCER": frozenset(
        {"loadbalancerinstanceno", "loadbalancerid"}
    ),
    "TARGET_GROUP": frozenset({"targetgroupno"}),
    "CDB": frozenset(
        {"serverinstanceno", "serverinstancenos"}
    ),
    "NKS": frozenset(
        {"clusteruuid", "clusterid", "uuid", "clusterno"}
    ),
    "NAS": frozenset({"nasvolumeinstanceno", "instanceno"}),
    "OBJECT_STORAGE": frozenset({"resourceid", "bucketid"}),
    "AUTO_SCALING": frozenset(
        {"autoscalinggroupno", "autoscalinggroupid"}
    ),
    "SEARCH_ENGINE": frozenset(
        {
            "svcgroupinstanceno",
            "servicegroupinstanceno",
            "clusterinstanceno",
        }
    ),
    "DATA_STREAMING": frozenset(
        {"instanceno", "clusterinstanceno"}
    ),
    "CLOUD_HADOOP": frozenset(
        {"instanceno", "clusterinstanceno"}
    ),
    "DATA_STREAM": frozenset({"topicid"}),
}

ID_DIMENSION_HINTS = {
    "instanceid",
    "instanceno",
    "loadbalancerid",
    "loadbalancerinstanceno",
    "loadbalancerno",
    "targetgroupno",
    "dbinstanceno",
    "clouddbinstanceno",
    "serverinstanceno",
    "clusterid",
    "clusteruuid",
    "resourceid",
    "autoscalinggroupno",
    "svcgroupinstanceno",
    "topicid",
}
NAME_DIMENSION_HINTS = {
    "name",
    "resourcename",
    "instancename",
    "loadbalancername",
    "dbname",
    "clustername",
}

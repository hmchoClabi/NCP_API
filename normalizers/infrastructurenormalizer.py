"""Normalize representative infrastructure into a safe common schema."""

from __future__ import annotations

import numbers
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional


class InfrastructureNormalizer:
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
        "NAS": "NAS",
        "CLOUD_DB": "Cloud DB",
        "KUBERNETES": "Kubernetes",
        "CDN": "CDN",
        "OBJECT_STORAGE": "Object Storage",
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
        "MONITORING",
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

    def normalize_servers(
        self,
        servers: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for server in self._dict_items(servers):
            raw_server = self._mapping(server.get("raw_server"))
            result.append(
                self._resource(
                    category="SERVER",
                    service_name="Server",
                    resource_type="ServerInstance",
                    resource_id=self._value(
                        server,
                        "server_id",
                        "serverInstanceNo",
                    ),
                    resource_name=self._value(
                        server,
                        "server_name",
                        "serverName",
                    ),
                    status=self._value(
                        server,
                        "status",
                        "serverInstanceStatusName",
                    ),
                    region_code=self._value(
                        server,
                        "region_code",
                        "regionCode",
                    ),
                    zone_code=self._value(
                        server,
                        "zone_code",
                        "zoneCode",
                    ),
                    platform="VPC",
                    create_time=self._value(
                        server,
                        "create_time",
                        "createDate",
                    )
                    or raw_server.get("createDate"),
                    details={
                        "cpu_count": self._value(
                            server,
                            "cpu_count",
                            "cpuCount",
                        ),
                        "memory_gb": self._value(server, "memory_gb"),
                        "hypervisor_type": self._value(
                            server,
                            "hypervisor_type",
                        ),
                        "vpc_no": self._value(server, "vpc_id", "vpcNo"),
                        "subnet_no": self._value(
                            server,
                            "subnet_id",
                            "subnetNo",
                        ),
                        "termination_protection": self._value(
                            server,
                            "is_protected",
                            "isProtectServerTermination",
                        ),
                        "storage_count": len(
                            self._as_list(server.get("storages"))
                        ),
                    },
                )
            )
        return result

    def normalize_block_storages(
        self,
        storages: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for storage in self._dict_items(storages):
            size_gb = self._value(storage, "size_gb")
            if size_gb is None:
                size_gb = self._bytes_to_gb(storage.get("blockStorageSize"))
            result.append(
                self._resource(
                    category="BLOCK_STORAGE",
                    service_name="Block Storage",
                    resource_type="BlockStorageInstance",
                    resource_id=self._value(
                        storage,
                        "storage_id",
                        "blockStorageInstanceNo",
                    ),
                    resource_name=self._value(
                        storage,
                        "storage_name",
                        "blockStorageName",
                    ),
                    status=self._value(
                        storage,
                        "status",
                        "blockStorageInstanceStatusName",
                    )
                    or self._code_name(
                        storage.get("blockStorageInstanceStatus")
                    ),
                    region_code=self._value(
                        storage,
                        "region_code",
                        "regionCode",
                    ),
                    zone_code=self._value(
                        storage,
                        "zone_code",
                        "zoneCode",
                    ),
                    platform="VPC",
                    create_time=self._value(
                        storage,
                        "create_date",
                        "createDate",
                    ),
                    details={
                        "size_gb": size_gb,
                        "storage_type": self._value(
                            storage,
                            "storage_type_name",
                        )
                        or self._code_name(storage.get("blockStorageType")),
                        "disk_type": self._value(
                            storage,
                            "disk_detail_type_name",
                        )
                        or self._code_name(
                            storage.get("blockStorageDiskDetailType")
                        ),
                        "volume_type": self._value(
                            storage,
                            "volume_type_name",
                        )
                        or self._code_name(
                            storage.get("blockStorageVolumeType")
                        ),
                        "attached_server_id": self._value(
                            storage,
                            "server_id",
                            "serverInstanceNo",
                        ),
                        "encrypted": self._value(
                            storage,
                            "is_encrypted",
                            "isEncryptedVolume",
                        ),
                        "return_protection": self._value(
                            storage,
                            "is_return_protection",
                            "isReturnProtection",
                        ),
                        "iops": storage.get("iops"),
                        "throughput_mbps": self._value(
                            storage,
                            "throughput_mbps",
                        ),
                    },
                )
            )
        return result

    def normalize_load_balancers(
        self,
        load_balancers: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for load_balancer in self._dict_items(load_balancers):
            result.append(
                self._resource(
                    category="LOAD_BALANCER",
                    service_name="Load Balancer",
                    resource_type="LoadBalancerInstance",
                    resource_id=load_balancer.get("loadBalancerInstanceNo"),
                    resource_name=load_balancer.get("loadBalancerName"),
                    status=load_balancer.get("loadBalancerInstanceStatusName")
                    or self._code_name(
                        load_balancer.get("loadBalancerInstanceStatus")
                    ),
                    region_code=load_balancer.get("regionCode"),
                    zone_code=load_balancer.get("zoneCode"),
                    platform="VPC",
                    create_time=load_balancer.get("createDate"),
                    details={
                        "load_balancer_type": self._code_name(
                            load_balancer.get("loadBalancerType")
                            or load_balancer.get("loadBalancerTypeCode")
                        ),
                        "network_type": self._code_name(
                            load_balancer.get("loadBalancerNetworkType")
                            or load_balancer.get(
                                "loadBalancerNetworkTypeCode"
                            )
                        ),
                        "throughput_type": self._code_name(
                            load_balancer.get("throughputType")
                        ),
                        "vpc_no": load_balancer.get("vpcNo"),
                        "subnet_count": len(
                            self._as_list(
                                load_balancer.get("subnetNoList")
                            )
                        ),
                        "idle_timeout_seconds": load_balancer.get(
                            "idleTimeout"
                        ),
                    },
                )
            )
        return result

    def normalize_nas(
        self,
        volumes: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for volume in self._dict_items(volumes):
            result.append(
                self._resource(
                    category="NAS",
                    service_name="NAS",
                    resource_type="NasVolumeInstance",
                    resource_id=volume.get("nasVolumeInstanceNo"),
                    resource_name=volume.get("volumeName"),
                    status=volume.get("nasVolumeInstanceStatusName")
                    or self._code_name(
                        volume.get("nasVolumeInstanceStatus")
                    ),
                    region_code=volume.get("regionCode"),
                    zone_code=volume.get("zoneCode"),
                    platform="VPC",
                    create_time=volume.get("createDate"),
                    details={
                        "size_gb": self._bytes_to_gb(
                            volume.get("volumeTotalSize")
                        ),
                        "protocol": self._code_name(
                            volume.get("volumeAllotmentProtocolType")
                            or volume.get(
                                "volumeAllotmentProtocolTypeCode"
                            )
                        ),
                        "snapshot_configured": volume.get(
                            "isSnapshotConfiguration"
                        ),
                        "encrypted": volume.get("isEncryptedVolume"),
                    },
                )
            )
        return result

    def normalize_cdb(
        self,
        engine: str,
        instances: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized_engine = str(engine).strip().upper()
        spec = self._CDB_SPECS[normalized_engine]
        prefix = spec["prefix"]
        server_list_key = f"{prefix}ServerInstanceList"

        result = []
        for instance in self._dict_items(instances):
            servers = self._dict_items(instance.get(server_list_key, []))
            first_server = servers[0] if servers else {}
            result.append(
                self._resource(
                    category="CLOUD_DB",
                    service_name=spec["service"],
                    resource_type=spec["resource_type"],
                    resource_id=instance.get(f"{prefix}InstanceNo"),
                    resource_name=instance.get(f"{prefix}ServiceName"),
                    status=instance.get(f"{prefix}InstanceStatusName")
                    or self._code_name(
                        instance.get(f"{prefix}InstanceStatus")
                    ),
                    region_code=first_server.get("regionCode")
                    or instance.get("regionCode"),
                    zone_code=first_server.get("zoneCode")
                    or instance.get("zoneCode"),
                    platform=normalized_engine,
                    create_time=instance.get("createDate"),
                    details={
                        "engine": normalized_engine,
                        "server_count": len(servers),
                        "server_instance_nos": [
                            str(server[f"{prefix}ServerInstanceNo"])
                            for server in servers
                            if server.get(f"{prefix}ServerInstanceNo")
                            is not None
                        ],
                        "high_availability": instance.get("isHa"),
                        "generation": instance.get("generationCode"),
                        "vpc_no": first_server.get("vpcNo")
                        or instance.get("vpcNo"),
                        "subnet_no": first_server.get("subnetNo")
                        or instance.get("subnetNo"),
                        "cpu_count_total": self._sum_numbers(
                            server.get("cpuCount") for server in servers
                        ),
                        "memory_gb_total": self._bytes_to_gb(
                            self._sum_numbers(
                                server.get("memorySize")
                                for server in servers
                            )
                        ),
                        "data_storage_gb_total": self._bytes_to_gb(
                            self._sum_numbers(
                                server.get("dataStorageSize")
                                for server in servers
                            )
                        ),
                    },
                )
            )
        return result

    def normalize_nks(
        self,
        clusters: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for cluster in self._dict_items(clusters):
            result.append(
                self._resource(
                    category="KUBERNETES",
                    service_name="Ncloud Kubernetes Service",
                    resource_type="Cluster",
                    resource_id=cluster.get("uuid")
                    or cluster.get("instanceNo"),
                    resource_name=cluster.get("name"),
                    status=cluster.get("status"),
                    region_code=cluster.get("regionCode"),
                    zone_code=cluster.get("zoneCode"),
                    platform="VPC",
                    create_time=cluster.get("createdAt"),
                    details={
                        "instance_no": cluster.get("instanceNo"),
                        "kubernetes_version": cluster.get("k8sVersion"),
                        "cluster_type": cluster.get("clusterType"),
                        "node_count": cluster.get("nodeCount"),
                        "node_max_count": cluster.get("nodeMaxCount"),
                        "node_pool_count": len(
                            self._as_list(cluster.get("nodePool"))
                        ),
                        "vpc_no": cluster.get("vpcNo"),
                        "network_plugin": cluster.get("kubeNetworkPlugin")
                        or cluster.get("kuberNetworkPlugin"),
                        "regional": cluster.get("isRegional"),
                        "public_network": cluster.get("publicNetwork"),
                        "termination_protection": cluster.get(
                            "returnProtection"
                        ),
                    },
                )
            )
        return result

    def normalize_cdn(
        self,
        variant: str,
        instances: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized_variant = str(variant).strip().upper()
        is_plus = normalized_variant == "CDN_PLUS"
        domains_key = (
            "cdnPlusServiceDomainList"
            if is_plus
            else "globalCdnServiceDomainList"
        )
        rule_key = "cdnPlusRule" if is_plus else "globalCdnRule"

        result = []
        for instance in self._dict_items(instances):
            rule = self._mapping(instance.get(rule_key))
            result.append(
                self._resource(
                    category="CDN",
                    service_name="CDN+" if is_plus else "Global CDN",
                    resource_type=(
                        "CdnPlusInstance"
                        if is_plus
                        else "GlobalCdnInstance"
                    ),
                    resource_id=instance.get("cdnInstanceNo"),
                    resource_name=instance.get("serviceName"),
                    status=instance.get("cdnInstanceStatusName")
                    or self._code_name(instance.get("cdnInstanceStatus")),
                    region_code=instance.get("regionCode"),
                    zone_code=None,
                    platform=normalized_variant,
                    create_time=instance.get("createDate"),
                    details={
                        "domain_count": len(
                            self._as_list(instance.get(domains_key))
                        ),
                        "protocol": rule.get("protocolTypeCode"),
                        "service_domain_type": rule.get(
                            "serviceDomainTypeCode"
                        ),
                        "partial_purge_available": instance.get(
                            "isAvailablePartialDomainPurge"
                        ),
                        "access_log_enabled": rule.get("isAccessLogUse"),
                        "gzip_enabled": rule.get("isGzipCompressionUse"),
                    },
                )
            )
        return result

    def normalize_resource_manager(
        self,
        items: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(items):
            category = self._resource_manager_category(item)
            if category is None:
                continue

            product_name = self._string(item.get("productName"))
            resource_type = self._string(item.get("resourceType"))
            platform = self._resource_manager_platform(
                category,
                product_name,
                self._string(item.get("platformType")),
            )
            result.append(
                self._resource(
                    category=category,
                    service_name=self._string(
                        item.get("productDisplayName")
                    )
                    or product_name
                    or self.CATEGORY_LABELS[category],
                    resource_type=resource_type or category,
                    resource_id=item.get("resourceId"),
                    resource_name=item.get("resourceName"),
                    status=None,
                    region_code=item.get("regionCode"),
                    zone_code=None,
                    platform=platform,
                    create_time=item.get("createTime"),
                    details={"inventory_source": "RESOURCE_MANAGER"},
                )
            )
        return result

    def finalize(
        self,
        resources: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        index_by_id: Dict[tuple[str, str], int] = {}
        index_by_name: Dict[tuple[str, str, str, str], int] = {}

        for candidate in self._dict_items(resources):
            candidate_category = self._string(candidate.get("category"))
            category = self.CATEGORY_ALIASES.get(
                str(candidate_category or "").upper()
            )
            if category not in self.CATEGORY_LABELS:
                continue

            resource = {
                field: candidate.get(field)
                for field in self.COMMON_FIELDS
            }
            resource["category"] = category
            resource["category_label"] = self.CATEGORY_LABELS[category]
            resource["resource_id"] = self._string(
                resource.get("resource_id")
            )
            resource["resource_name"] = self._string(
                resource.get("resource_name")
            )
            resource["details"] = self._sanitize_details(
                self._mapping(resource.get("details"))
            )

            if not resource["resource_id"] and not resource["resource_name"]:
                continue

            id_key = None
            if resource["resource_id"]:
                id_key = (category, resource["resource_id"])
            name_key = None
            if resource["resource_name"]:
                name_key = (
                    category,
                    self._string(resource.get("platform")) or "",
                    self._string(resource.get("region_code")) or "",
                    resource["resource_name"].casefold(),
                )

            existing_index = (
                index_by_id.get(id_key) if id_key is not None else None
            )
            if existing_index is None and name_key is not None:
                name_index = index_by_name.get(name_key)
                if name_index is not None:
                    existing_id = result[name_index].get("resource_id")
                    if not (
                        resource["resource_id"]
                        and existing_id
                        and resource["resource_id"] != existing_id
                    ):
                        existing_index = name_index

            if existing_index is not None:
                self._merge_missing(result[existing_index], resource)
                continue

            result.append(resource)
            current_index = len(result) - 1
            if id_key is not None:
                index_by_id[id_key] = current_index
            if name_key is not None:
                index_by_name[name_key] = current_index

        return sorted(
            result,
            key=lambda resource: (
                self.CATEGORY_ORDER[resource["category"]],
                (resource.get("resource_name") or "").casefold(),
                resource.get("resource_id") or "",
            ),
        )

    def _resource_manager_category(
        self,
        item: Mapping[str, Any],
    ) -> Optional[str]:
        product = self._token(item.get("productName"))
        resource_type = self._token(item.get("resourceType"))
        combined = product + resource_type
        if any(marker in combined for marker in self._EXCLUDED_RESOURCE_MARKERS):
            return None

        for category in self.CATEGORY_LABELS:
            if (
                product in self._RESOURCE_MANAGER_PRODUCTS[category]
                and resource_type in self._RESOURCE_MANAGER_TYPES[category]
            ):
                return category
        return None

    def _resource_manager_platform(
        self,
        category: str,
        product_name: Optional[str],
        platform_type: Optional[str],
    ) -> Optional[str]:
        product = self._token(product_name)
        if category == "CLOUD_DB":
            if "SERVERLESS" in product:
                return "SERVERLESS"
            if "REDIS" in product:
                return "CACHE"
            for engine in ("POSTGRESQL", "MONGODB", "MSSQL", "MYSQL", "CACHE"):
                if engine in product:
                    return engine
        if category == "CDN":
            if "GLOBAL" in product or product == "GCDN":
                return "GLOBAL_CDN"
            if "PLUS" in product:
                return "CDN_PLUS"
        return platform_type

    def _resource(
        self,
        *,
        category: str,
        service_name: Any,
        resource_type: Any,
        resource_id: Any,
        resource_name: Any,
        status: Any,
        region_code: Any,
        zone_code: Any,
        platform: Any,
        create_time: Any,
        details: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "category": category,
            "category_label": self.CATEGORY_LABELS[category],
            "service_name": self._string(service_name),
            "resource_type": self._string(resource_type),
            "resource_id": self._string(resource_id),
            "resource_name": self._string(resource_name),
            "status": self._string(status),
            "region_code": self._string(region_code),
            "zone_code": self._string(zone_code),
            "platform": self._string(platform),
            "create_time": create_time,
            "details": self._sanitize_details(details),
        }

    def _sanitize_details(self, value: Mapping[str, Any]) -> Dict[str, Any]:
        sanitized = {}
        for key, item in value.items():
            normalized_key = self._token(key).lower()
            if any(
                fragment in normalized_key
                for fragment in self._SENSITIVE_KEY_FRAGMENTS
            ):
                continue
            if item is None:
                continue
            if isinstance(item, str) and "://" in item:
                continue
            if isinstance(item, (str, bool, int, float)):
                sanitized[str(key)] = item
                continue
            if isinstance(item, (list, tuple)):
                safe_items = [
                    child
                    for child in item[:500]
                    if isinstance(child, (str, bool, int, float))
                    and not (
                        isinstance(child, str)
                        and "://" in child
                    )
                ]
                if safe_items:
                    sanitized[str(key)] = safe_items
        return sanitized

    def _merge_missing(
        self,
        existing: Dict[str, Any],
        fallback: Mapping[str, Any],
    ) -> None:
        for field in self.COMMON_FIELDS:
            if field == "details":
                continue
            if existing.get(field) in (None, "") and fallback.get(field) not in (
                None,
                "",
            ):
                existing[field] = fallback[field]

        existing_details = self._mapping(existing.get("details"))
        fallback_details = self._mapping(fallback.get("details"))
        for key, value in fallback_details.items():
            existing_details.setdefault(key, value)
        existing["details"] = self._sanitize_details(existing_details)

    @staticmethod
    def _mapping(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        return list(value) if isinstance(value, (list, tuple)) else []

    @staticmethod
    def _dict_items(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, Iterable) or isinstance(
            value,
            (str, bytes, Mapping),
        ):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _value(mapping: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            value = mapping.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _string(value: Any) -> Optional[str]:
        if value is None:
            return None
        rendered = str(value).strip()
        return rendered or None

    @staticmethod
    def _token(value: Any) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    @staticmethod
    def _code_name(value: Any) -> Any:
        if isinstance(value, Mapping):
            return value.get("codeName") or value.get("code")
        return value

    @staticmethod
    def _sum_numbers(values: Iterable[Any]) -> Optional[float]:
        numbers_found = [
            value
            for value in values
            if isinstance(value, numbers.Real) and not isinstance(value, bool)
        ]
        if not numbers_found:
            return None
        return sum(numbers_found)

    @staticmethod
    def _bytes_to_gb(value: Any) -> Optional[float]:
        if not isinstance(value, numbers.Real) or isinstance(value, bool):
            return None
        return round(float(value) / (1024 ** 3), 2)


__all__ = ["InfrastructureNormalizer"]

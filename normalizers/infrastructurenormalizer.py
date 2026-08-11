"""Normalize representative infrastructure into a safe common schema."""

from __future__ import annotations

import numbers
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from . import _infrastructure_catalog as infrastructure_catalog


class InfrastructureNormalizer:
    COMMON_FIELDS = infrastructure_catalog.COMMON_FIELDS
    CATEGORY_LABELS = infrastructure_catalog.CATEGORY_LABELS
    CATEGORY_ORDER = infrastructure_catalog.CATEGORY_ORDER
    CATEGORY_ALIASES = infrastructure_catalog.CATEGORY_ALIASES
    _SENSITIVE_KEY_FRAGMENTS = infrastructure_catalog._SENSITIVE_KEY_FRAGMENTS
    _EXCLUDED_RESOURCE_MARKERS = infrastructure_catalog._EXCLUDED_RESOURCE_MARKERS
    _RESOURCE_MANAGER_PRODUCTS = infrastructure_catalog._RESOURCE_MANAGER_PRODUCTS
    _RESOURCE_MANAGER_TYPES = infrastructure_catalog._RESOURCE_MANAGER_TYPES
    _CDB_SPECS = infrastructure_catalog._CDB_SPECS
    _STRUCTURED_DETAIL_FIELDS = frozenset({
        "associated_subnets",
        "routes",
        "rules",
    })

    def normalize_servers(
        self,
        servers: Iterable[Mapping[str, Any]],
        network_interfaces: Iterable[Mapping[str, Any]] = (),
    ) -> List[Dict[str, Any]]:
        nics_by_server: Dict[str, List[Dict[str, Any]]] = {}
        for nic in self._dict_items(network_interfaces):
            server_no = self._string(nic.get("serverInstanceNo"))
            if server_no:
                nics_by_server.setdefault(server_no, []).append(nic)

        result = []
        for server in self._dict_items(servers):
            raw_server = self._mapping(server.get("raw_server"))
            nics = self._dict_items(server.get("nics"))
            server_no = self._string(
                self._value(server, "server_id", "serverInstanceNo")
            )
            known_nic_ids = {
                self._string(self._value(nic, "nic_id", "networkInterfaceNo"))
                for nic in nics
            }
            for nic in nics_by_server.get(server_no or "", []):
                nic_no = self._string(nic.get("networkInterfaceNo"))
                if nic_no and nic_no in known_nic_ids:
                    continue
                nics.append(nic)
                if nic_no:
                    known_nic_ids.add(nic_no)
            all_private_ips = self._unique_values(
                ip
                for nic in nics
                for ip in self._nic_private_ips(nic)
            )
            if not all_private_ips:
                all_private_ips = self._unique_values(
                    [self._value(server, "private_ip", "privateIp")]
                )
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
                        "server_instance_no": self._value(
                            server,
                            "server_id",
                            "serverInstanceNo",
                        ),
                        "private_ip": self._value(
                            server,
                            "private_ip",
                            "privateIp",
                        ),
                        "public_ip": self._value(
                            server,
                            "public_ip",
                            "publicIp",
                        ),
                        "all_private_ips": all_private_ips,
                        "network_interface_no": self._value(
                            server,
                            "nic_id",
                            "networkInterfaceNo",
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
                        "server_instance_no": self._value(
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
        target_groups: Iterable[Mapping[str, Any]] = (),
        targets_by_group: Optional[
            Mapping[str, Iterable[Mapping[str, Any]]]
        ] = None,
    ) -> List[Dict[str, Any]]:
        (
            normalized_groups,
            groups_by_load_balancer,
            group_health,
        ) = self._index_load_balancer_responses(
            target_groups,
            targets_by_group,
        )

        # 기존 결과 계약대로 LB 레코드를 먼저, Target Group을 나중에 배치한다.
        result = [
            self._normalize_load_balancer_record(
                load_balancer,
                groups_by_load_balancer,
                group_health,
            )
            for load_balancer in self._dict_items(load_balancers)
        ]
        for group in normalized_groups:
            normalized_group = self._normalize_target_group_record(
                group,
                group_health,
            )
            if normalized_group is not None:
                result.append(normalized_group)
        return result

    def _index_load_balancer_responses(
        self,
        target_groups: Iterable[Mapping[str, Any]],
        targets_by_group: Optional[
            Mapping[str, Iterable[Mapping[str, Any]]]
        ],
    ) -> tuple[
        List[Dict[str, Any]],
        Dict[str, List[Dict[str, Any]]],
        Dict[str, Dict[str, Any]],
    ]:
        """공급자 ID를 기준으로 Target Group과 상태 응답을 인덱싱한다."""

        normalized_groups = self._dict_items(target_groups)
        groups_by_load_balancer: Dict[str, List[Dict[str, Any]]] = {}
        for group in normalized_groups:
            load_balancer_no = self._string(
                group.get("loadBalancerInstanceNo")
            )
            if load_balancer_no:
                groups_by_load_balancer.setdefault(
                    load_balancer_no,
                    [],
                ).append(group)

        normalized_targets_by_group = (
            targets_by_group if isinstance(targets_by_group, Mapping) else {}
        )
        group_health = {
            str(group.get("targetGroupNo")): self._target_group_health(
                group,
                normalized_targets_by_group,
            )
            for group in normalized_groups
            if self._string(group.get("targetGroupNo"))
        }
        return (
            normalized_groups,
            groups_by_load_balancer,
            group_health,
        )

    def _normalize_load_balancer_record(
        self,
        load_balancer: Mapping[str, Any],
        groups_by_load_balancer: Dict[str, List[Dict[str, Any]]],
        group_health: Mapping[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """VPC Load Balancer 한 건과 공급자가 명시한 대상 정보를 정규화한다."""

        load_balancer_no = self._string(
            load_balancer.get("loadBalancerInstanceNo")
        )
        associated_groups = groups_by_load_balancer.get(
            load_balancer_no or "",
            [],
        )
        target_group_nos = self._unique_values(
            group.get("targetGroupNo") for group in associated_groups
        )
        health_summaries = [
            group_health[str(group.get("targetGroupNo"))]
            for group in associated_groups
            if str(group.get("targetGroupNo")) in group_health
        ]
        health_snapshot_available = all(
            summary["health_snapshot_available"]
            for summary in health_summaries
        ) if health_summaries else True
        subnet_nos = self._unique_values(
            load_balancer.get("subnetNoList") or []
        )
        return self._resource(
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
                    or load_balancer.get("loadBalancerNetworkTypeCode")
                ),
                "throughput_type": self._code_name(
                    load_balancer.get("throughputType")
                ),
                "vpc_no": load_balancer.get("vpcNo"),
                "subnet_nos": subnet_nos,
                "load_balancer_instance_no": load_balancer_no,
                "ip_addresses": self._unique_values(
                    load_balancer.get("loadBalancerIpList") or []
                ),
                "target_group_nos": target_group_nos,
                "target_group_count": len(target_group_nos),
                "target_health_snapshot_available": (
                    health_snapshot_available
                ),
                "registered_target_count": sum(
                    summary["registered_target_count"]
                    for summary in health_summaries
                ),
                "ready_target_count": sum(
                    summary["ready_target_count"]
                    for summary in health_summaries
                    if summary["health_snapshot_available"]
                ),
                "unready_target_count": sum(
                    summary["unready_target_count"]
                    for summary in health_summaries
                    if summary["health_snapshot_available"]
                ),
                "unused_target_count": sum(
                    summary["unused_target_count"]
                    for summary in health_summaries
                    if summary["health_snapshot_available"]
                ),
                "unknown_target_count": sum(
                    summary["unknown_target_count"]
                    for summary in health_summaries
                    if summary["health_snapshot_available"]
                ),
                "subnet_count": len(
                    self._as_list(load_balancer.get("subnetNoList"))
                ),
                "idle_timeout_seconds": load_balancer.get("idleTimeout"),
            },
        )

    def _normalize_target_group_record(
        self,
        group: Mapping[str, Any],
        group_health: Mapping[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Target Group 한 건과 명시된 VServer 대상 관계를 정규화한다."""

        group_no = self._string(group.get("targetGroupNo"))
        if not group_no:
            return None
        health = group_health[group_no]
        target_type = self._code_value(group.get("targetType"))
        status = "UNKNOWN"
        if health["health_snapshot_available"]:
            if health["unready_target_count"]:
                status = "UNREADY"
            elif (
                health["unused_target_count"]
                or health["unknown_target_count"]
            ):
                status = "PARTIAL"
            elif health["registered_target_count"]:
                status = "READY"
            else:
                status = "EMPTY"
        return self._resource(
            category="TARGET_GROUP",
            service_name="Load Balancer",
            resource_type="TargetGroup",
            resource_id=group_no,
            resource_name=group.get("targetGroupName"),
            status=status,
            region_code=group.get("regionCode"),
            zone_code=None,
            platform="VPC",
            create_time=group.get("createDate"),
            details={
                "target_group_no": group_no,
                "load_balancer_instance_no": group.get(
                    "loadBalancerInstanceNo"
                ),
                "vpc_no": group.get("vpcNo"),
                "protocol": self._code_name(
                    group.get("targetGroupProtocolType")
                ),
                "port": group.get("targetGroupPort"),
                "target_type": target_type,
                "health_check_protocol": self._code_name(
                    group.get("healthCheckProtocolType")
                ),
                "health_check_port": group.get("healthCheckPort"),
                "registered_target_count": (
                    health["registered_target_count"]
                ),
                "ready_target_count": health["ready_target_count"],
                "unready_target_count": (
                    health["unready_target_count"]
                ),
                "unused_target_count": health["unused_target_count"],
                "unknown_target_count": (
                    health["unknown_target_count"]
                ),
                "health_snapshot_available": (
                    health["health_snapshot_available"]
                ),
            },
        )

    def _target_group_health(
        self,
        group: Mapping[str, Any],
        targets_by_group: Mapping[str, Iterable[Mapping[str, Any]]],
    ) -> Dict[str, Any]:
        group_no = self._string(group.get("targetGroupNo")) or ""
        snapshot_available = group_no in targets_by_group
        targets = self._dict_items(targets_by_group.get(group_no, []))
        counts = {"UP": 0, "DOWN": 0, "UNUSED": 0, "UNKNOWN": 0}
        target_nos = self._as_list(group.get("targetNoList"))
        if snapshot_available:
            for target in targets:
                target_nos.append(target.get("targetNo"))
                status = self._token(
                    self._code_value(target.get("healthCheckStatus"))
                )
                counts[status if status in counts else "UNKNOWN"] += 1
        return {
            "health_snapshot_available": snapshot_available,
            "registered_target_count": (
                len(targets)
                if snapshot_available
                else len(self._unique_values(target_nos))
            ),
            "ready_target_count": counts["UP"],
            "unready_target_count": counts["DOWN"],
            "unused_target_count": counts["UNUSED"],
            "unknown_target_count": counts["UNKNOWN"],
        }

    def normalize_nas(
        self,
        volumes: Iterable[Mapping[str, Any]],
        platform: str = "VPC",
    ) -> List[Dict[str, Any]]:
        normalized_platform = self._token(platform)
        if normalized_platform not in {"VPC", "CLASSIC"}:
            raise ValueError(f"Unsupported NAS platform: {platform!r}")

        result = []
        for volume in self._dict_items(volumes):
            region = self._mapping(volume.get("region"))
            zone = self._mapping(volume.get("zone"))
            server_instance_nos = self._unique_values([
                *self._as_list(
                    volume.get("nasVolumeServerInstanceNoList")
                ),
                *(
                    server.get("serverInstanceNo")
                    for server in self._dict_items(
                        volume.get("nasVolumeServerInstanceList")
                    )
                ),
            ])
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
                    region_code=volume.get("regionCode")
                    or region.get("regionCode"),
                    zone_code=volume.get("zoneCode")
                    or zone.get("zoneCode"),
                    platform=normalized_platform,
                    create_time=volume.get("createDate"),
                    details={
                        "nas_volume_instance_no": volume.get(
                            "nasVolumeInstanceNo"
                        ),
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
                        "vpc_no": volume.get("vpcNo"),
                        "subnet_no": volume.get("subnetNo"),
                        "server_instance_nos": server_instance_nos,
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
            vpc_nos = self._unique_values(
                [
                    *(server.get("vpcNo") for server in servers),
                    instance.get("vpcNo"),
                ]
            )
            subnet_nos = self._unique_values(
                [
                    *(server.get("subnetNo") for server in servers),
                    instance.get("subnetNo"),
                ]
            )
            server_instance_nos = self._unique_values(
                server.get(f"{prefix}ServerInstanceNo")
                for server in servers
            )
            server_names = self._unique_values(
                server.get(f"{prefix}ServerName") for server in servers
            )
            private_ips = self._unique_values(
                server.get("privateIp") for server in servers
            )
            server_roles = self._unique_values(
                self._code_value(server.get(f"{prefix}ServerRole"))
                for server in servers
            )
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
                        "server_instance_nos": server_instance_nos,
                        "server_names": server_names,
                        "private_ips": private_ips,
                        "server_roles": server_roles,
                        "high_availability": instance.get("isHa"),
                        "generation": instance.get("generationCode"),
                        "vpc_no": first_server.get("vpcNo")
                        or instance.get("vpcNo"),
                        "subnet_no": first_server.get("subnetNo")
                        or instance.get("subnetNo"),
                        "vpc_nos": vpc_nos,
                        "subnet_nos": subnet_nos,
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
            subnet_nos = self._unique_values(
                [
                    *self._as_list(cluster.get("subnetNoList")),
                    cluster.get("subnetNo"),
                    cluster.get("subnetLbNo"),
                ]
            )
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
                        "subnet_nos": subnet_nos,
                        "cluster_uuid": cluster.get("uuid"),
                        "cluster_no": cluster.get("instanceNo"),
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

    def normalize_vpcs(
        self,
        vpcs: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            self._resource(
                category="VPC",
                service_name="VPC",
                resource_type="VPC",
                resource_id=item.get("vpcNo"),
                resource_name=item.get("vpcName"),
                status=self._code_name(item.get("vpcStatus")),
                region_code=item.get("regionCode"),
                zone_code=None,
                platform="VPC",
                create_time=item.get("createDate"),
                details={
                    "vpc_no": item.get("vpcNo"),
                    "ipv4_cidr_block": item.get("ipv4CidrBlock"),
                },
            )
            for item in self._dict_items(vpcs)
        ]

    def normalize_subnets(
        self,
        subnets: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(subnets):
            subnet_no = self._string(item.get("subnetNo"))
            result.append(
                self._resource(
                    category="SUBNET",
                    service_name="VPC",
                    resource_type="Subnet",
                    resource_id=subnet_no,
                    resource_name=item.get("subnetName"),
                    status=self._code_name(item.get("subnetStatus")),
                    region_code=item.get("regionCode"),
                    zone_code=item.get("zoneCode"),
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "subnet_no": subnet_no,
                        "vpc_no": item.get("vpcNo"),
                        "ipv4_cidr_block": item.get("subnet"),
                        "subnet_type": self._code_value(
                            item.get("subnetType")
                        ),
                        "usage_type": self._code_value(
                            item.get("usageType")
                        ),
                        "network_acl_no": item.get("networkAclNo"),
                    },
                )
            )
        return result

    def normalize_route_tables(
        self,
        route_tables: Iterable[Mapping[str, Any]],
        subnets_by_table: Optional[
            Mapping[str, Iterable[Mapping[str, Any]]]
        ] = None,
        routes_by_table: Optional[
            Mapping[str, Iterable[Mapping[str, Any]]]
        ] = None,
    ) -> List[Dict[str, Any]]:
        """Route Table과 조회 시점의 Subnet 연결·Route 규칙을 정규화한다."""

        normalized_subnets = (
            subnets_by_table if isinstance(subnets_by_table, Mapping) else {}
        )
        normalized_routes = (
            routes_by_table if isinstance(routes_by_table, Mapping) else {}
        )
        result = []
        for item in self._dict_items(route_tables):
            route_table_no = self._string(item.get("routeTableNo"))
            associated_subnets = self._dict_items(
                normalized_subnets.get(route_table_no or "", [])
            )
            routes = self._dict_items(
                normalized_routes.get(route_table_no or "", [])
            )
            result.append(
                self._resource(
                    category="ROUTE_TABLE",
                    service_name="VPC",
                    resource_type="RouteTable",
                    resource_id=route_table_no,
                    resource_name=item.get("routeTableName"),
                    status=self._code_name(item.get("routeTableStatus")),
                    region_code=item.get("regionCode"),
                    zone_code=None,
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "route_table_no": route_table_no,
                        "vpc_no": item.get("vpcNo"),
                        "supported_subnet_type": self._code_value(
                            item.get("supportedSubnetType")
                        ),
                        "default": item.get("isDefault"),
                        "description": item.get("routeTableDescription"),
                        "subnet_association_snapshot_available": (
                            route_table_no in normalized_subnets
                        ),
                        "associated_subnet_count": len(associated_subnets),
                        "associated_subnet_nos": self._unique_values(
                            subnet.get("subnetNo")
                            for subnet in associated_subnets
                        ),
                        "associated_subnets": [
                            {
                                "subnet_no": subnet.get("subnetNo"),
                                "subnet_name": subnet.get("subnetName"),
                                "cidr": subnet.get("subnet"),
                                "zone_code": subnet.get("zoneCode"),
                                "subnet_type": self._code_value(
                                    subnet.get("subnetType")
                                ),
                                "status": self._code_value(
                                    subnet.get("subnetStatus")
                                ),
                                "create_time": subnet.get("createDate"),
                                "network_acl_no": subnet.get("networkAclNo"),
                            }
                            for subnet in associated_subnets
                        ],
                        "route_snapshot_available": (
                            route_table_no in normalized_routes
                        ),
                        "route_count": len(routes),
                        "routes": [
                            {
                                "destination_cidr": route.get(
                                    "destinationCidrBlock"
                                ),
                                "target_name": route.get("targetName"),
                                "target_type": self._code_value(
                                    route.get("targetType")
                                ),
                                "target_no": route.get("targetNo"),
                                "default": route.get("isDefault"),
                                "create_time": route.get("createDate"),
                            }
                            for route in routes
                        ],
                        "last_modified_time": self._value(
                            item,
                            "lastModifiedDate",
                            "updateDate",
                        ),
                        "observation_time": self._value(
                            item,
                            "observedAt",
                            "observationTime",
                            "eventTime",
                        ),
                    },
                )
            )
        return result

    def normalize_access_control_groups(
        self,
        groups: Iterable[Mapping[str, Any]],
        rules_by_group: Optional[
            Mapping[str, Iterable[Mapping[str, Any]]]
        ] = None,
    ) -> List[Dict[str, Any]]:
        """ACG와 인바운드·아웃바운드 규칙 스냅샷을 정규화한다."""

        normalized_rules = (
            rules_by_group if isinstance(rules_by_group, Mapping) else {}
        )
        result = []
        for item in self._dict_items(groups):
            group_no = self._string(item.get("accessControlGroupNo"))
            rules = self._dict_items(
                normalized_rules.get(group_no or "", [])
            )
            normalized_rule_rows = [
                {
                    "direction": self._code_value(
                        rule.get("accessControlGroupRuleType")
                    ),
                    "protocol": self._code_value(rule.get("protocolType")),
                    "protocol_number": self._mapping(
                        rule.get("protocolType")
                    ).get("number"),
                    "source_ip_block": rule.get("ipBlock"),
                    "source_access_control_group_no": rule.get(
                        "accessControlGroupSequence"
                    ),
                    "port_range": rule.get("portRange"),
                    "description": rule.get(
                        "accessControlGroupRuleDescription"
                    ),
                    "create_time": rule.get("createDate"),
                }
                for rule in rules
            ]
            result.append(
                self._resource(
                    category="ACCESS_CONTROL_GROUP",
                    service_name="Server",
                    resource_type="AccessControlGroup",
                    resource_id=group_no,
                    resource_name=item.get("accessControlGroupName"),
                    status=self._code_name(
                        item.get("accessControlGroupStatus")
                    ),
                    region_code=item.get("regionCode"),
                    zone_code=None,
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "access_control_group_no": group_no,
                        "vpc_no": item.get("vpcNo"),
                        "default": item.get("isDefault"),
                        "description": item.get(
                            "accessControlGroupDescription"
                        ),
                        "rule_snapshot_available": (
                            group_no in normalized_rules
                        ),
                        "rule_count": len(normalized_rule_rows),
                        "inbound_rule_count": sum(
                            1
                            for rule in normalized_rule_rows
                            if rule.get("direction") == "INBND"
                        ),
                        "outbound_rule_count": sum(
                            1
                            for rule in normalized_rule_rows
                            if rule.get("direction") == "OTBND"
                        ),
                        "rules": normalized_rule_rows,
                        "last_modified_time": self._value(
                            item,
                            "lastModifiedDate",
                            "updateDate",
                        ),
                        "observation_time": self._value(
                            item,
                            "observedAt",
                            "observationTime",
                            "eventTime",
                        ),
                    },
                )
            )
        return result

    def normalize_network_acls(
        self,
        network_acls: Iterable[Mapping[str, Any]],
        rules_by_acl: Optional[
            Mapping[str, Iterable[Mapping[str, Any]]]
        ] = None,
    ) -> List[Dict[str, Any]]:
        """Network ACL과 우선순위가 있는 규칙 스냅샷을 정규화한다."""

        normalized_rules = (
            rules_by_acl if isinstance(rules_by_acl, Mapping) else {}
        )
        result = []
        for item in self._dict_items(network_acls):
            network_acl_no = self._string(item.get("networkAclNo"))
            rules = self._dict_items(
                normalized_rules.get(network_acl_no or "", [])
            )
            normalized_rule_rows = [
                {
                    "priority": rule.get("priority"),
                    "direction": self._code_value(
                        rule.get("networkAclRuleType")
                    ),
                    "protocol": self._code_value(rule.get("protocolType")),
                    "port_range": rule.get("portRange"),
                    "action": self._code_value(rule.get("ruleAction")),
                    "source_ip_block": rule.get("ipBlock"),
                    "deny_allow_group_no": rule.get("denyAllowGroupNo"),
                    "description": rule.get("networkAclRuleDescription"),
                    "create_time": rule.get("createDate"),
                }
                for rule in rules
            ]
            result.append(
                self._resource(
                    category="NETWORK_ACL",
                    service_name="VPC",
                    resource_type="NetworkAcl",
                    resource_id=network_acl_no,
                    resource_name=item.get("networkAclName"),
                    status=self._code_name(item.get("networkAclStatus")),
                    region_code=item.get("regionCode"),
                    zone_code=None,
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "network_acl_no": network_acl_no,
                        "vpc_no": item.get("vpcNo"),
                        "default": item.get("isDefault"),
                        "description": item.get("networkAclDescription"),
                        "rule_snapshot_available": (
                            network_acl_no in normalized_rules
                        ),
                        "rule_count": len(normalized_rule_rows),
                        "inbound_rule_count": sum(
                            1
                            for rule in normalized_rule_rows
                            if rule.get("direction") == "INBND"
                        ),
                        "outbound_rule_count": sum(
                            1
                            for rule in normalized_rule_rows
                            if rule.get("direction") == "OTBND"
                        ),
                        "rules": normalized_rule_rows,
                        "last_modified_time": self._value(
                            item,
                            "lastModifiedDate",
                            "updateDate",
                        ),
                        "observation_time": self._value(
                            item,
                            "observedAt",
                            "observationTime",
                            "eventTime",
                        ),
                    },
                )
            )
        return result

    def normalize_nat_gateways(
        self,
        gateways: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(gateways):
            gateway_ips = self._dict_items(item.get("natGatewayIpList"))
            public_ip_instance_nos = self._unique_values(
                [
                    item.get("publicIpInstanceNo"),
                    *(ip.get("publicIpInstanceNo") for ip in gateway_ips),
                ]
            )
            public_ips = self._unique_values(
                [item.get("publicIp"), *(ip.get("publicIp") for ip in gateway_ips)]
            )
            private_ips = self._unique_values(
                [
                    item.get("privateIp"),
                    *(ip.get("privateIp") for ip in gateway_ips),
                ]
            )
            result.append(
                self._resource(
                    category="NAT_GATEWAY",
                    service_name="VPC",
                    resource_type="NATGateway",
                    resource_id=item.get("natGatewayInstanceNo"),
                    resource_name=item.get("natGatewayName"),
                    status=item.get("natGatewayInstanceStatusName")
                    or self._code_name(item.get("natGatewayInstanceStatus")),
                    region_code=item.get("regionCode"),
                    zone_code=item.get("zoneCode"),
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "nat_gateway_instance_no": item.get(
                            "natGatewayInstanceNo"
                        ),
                        "vpc_no": item.get("vpcNo"),
                        "subnet_no": item.get("subnetNo"),
                        "gateway_type": self._code_value(
                            item.get("natGatewayType")
                        ),
                        "public_ips": public_ips,
                        "private_ips": private_ips,
                        "public_ip_instance_nos": public_ip_instance_nos,
                    },
                )
            )
        return result

    def normalize_vpc_peerings(
        self,
        peerings: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(peerings):
            result.append(
                self._resource(
                    category="VPC_PEERING",
                    service_name="VPC",
                    resource_type="VPCPeering",
                    resource_id=item.get("vpcPeeringInstanceNo"),
                    resource_name=item.get("vpcPeeringName"),
                    status=self._code_name(
                        item.get("vpcPeeringInstanceStatus")
                    ),
                    region_code=item.get("regionCode"),
                    zone_code=None,
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "source_vpc_no": item.get("sourceVpcNo"),
                        "target_vpc_no": item.get("targetVpcNo"),
                    },
                )
            )
        return result

    def normalize_public_ips(
        self,
        public_ips: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(public_ips):
            associated_server = self._mapping(
                item.get("serverInstanceAssociatedWithPublicIp")
            )
            server_instance_no = item.get("serverInstanceNo") or (
                associated_server.get("serverInstanceNo")
            )
            result.append(
                self._resource(
                    category="PUBLIC_IP",
                    service_name="Server",
                    resource_type="PublicIP",
                    resource_id=item.get("publicIpInstanceNo"),
                    resource_name=item.get("publicIp"),
                    status=item.get("publicIpInstanceStatusName")
                    or self._code_name(item.get("publicIpInstanceStatus")),
                    region_code=item.get("regionCode"),
                    zone_code=item.get("zoneCode")
                    or self._mapping(item.get("zone")).get("zoneCode"),
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "public_ip_instance_no": item.get(
                            "publicIpInstanceNo"
                        ),
                        "public_ip": item.get("publicIp"),
                        "private_ip": item.get("privateIp"),
                        "server_instance_no": server_instance_no,
                        "attached_server_id": server_instance_no,
                        "vpc_no": item.get("vpcNo"),
                        "associated": item.get("isAssociated"),
                    },
                )
            )
        return result

    def normalize_snapshots(
        self,
        snapshots: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(snapshots):
            source_storage_no = item.get("originalBlockStorageInstanceNo")
            result.append(
                self._resource(
                    category="BLOCK_STORAGE_SNAPSHOT",
                    service_name="Server",
                    resource_type="Snapshot",
                    resource_id=item.get("blockStorageSnapshotInstanceNo"),
                    resource_name=item.get("blockStorageSnapshotName"),
                    status=item.get("blockStorageSnapshotInstanceStatusName")
                    or self._code_name(
                        item.get("blockStorageSnapshotInstanceStatus")
                    ),
                    region_code=item.get("regionCode"),
                    zone_code=item.get("zoneCode"),
                    platform="VPC",
                    create_time=item.get("createDate"),
                    details={
                        "block_storage_instance_no": source_storage_no,
                        "snapshot_volume_size_gb": self._bytes_to_gb(
                            item.get("blockStorageSnapshotVolumeSize")
                        ),
                        "encrypted": item.get(
                            "isEncryptedOriginalBlockStorageVolume"
                        ),
                        "bootable": item.get("isBootable"),
                    },
                )
            )
        return result

    def normalize_server_images(
        self,
        images: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(images):
            original_server_no = item.get("originalServerInstanceNo")
            result.append(
                self._resource(
                    category="SERVER_IMAGE",
                    service_name="Server",
                    resource_type="ServerImage",
                    resource_id=item.get("memberServerImageInstanceNo"),
                    resource_name=item.get("memberServerImageName"),
                    status=item.get("memberServerImageInstanceStatusName")
                    or self._code_name(
                        item.get("memberServerImageInstanceStatus")
                    ),
                    region_code=item.get("regionCode"),
                    zone_code=item.get("zoneCode"),
                    platform=self._code_value(item.get("platformType"))
                    or "VPC",
                    create_time=item.get("createDate"),
                    details={
                        "server_instance_no": original_server_no,
                        "original_server_instance_no": original_server_no,
                        "block_storage_size_gb": self._bytes_to_gb(
                            item.get("blockStorageSize")
                        ),
                    },
                )
            )
        return result

    def normalize_global_dns(
        self,
        domains: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            self._resource(
                category="GLOBAL_DNS",
                service_name="Global DNS",
                resource_type="Domain",
                resource_id=item.get("id"),
                resource_name=item.get("name"),
                status=item.get("status"),
                region_code=None,
                zone_code=None,
                platform="GLOBAL",
                create_time=item.get("createdDate") or item.get("createDate"),
                details={
                    "domain_id": item.get("id"),
                    "complete": item.get("completeYn"),
                    "dnssec_enabled": item.get("dnssecYn"),
                },
            )
            for item in self._dict_items(domains)
        ]

    def normalize_certificates(
        self,
        certificates: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result = []
        for item in self._dict_items(certificates):
            used_instances = item.get("usedInstanceNoList")
            if isinstance(used_instances, str):
                used_instances = [
                    part.strip()
                    for part in used_instances.split(",")
                    if part.strip()
                ]
            result.append(
                self._resource(
                    category="CERTIFICATE",
                    service_name="Certificate Manager",
                    resource_type="Certificate",
                    resource_id=item.get("certificateNo"),
                    resource_name=item.get("certificateName"),
                    status=item.get("statusName") or item.get("statusCode"),
                    region_code=None,
                    zone_code=None,
                    platform=item.get("domainCode"),
                    create_time=item.get("regDate"),
                    details={
                        "certificate_no": item.get("certificateNo"),
                        "certificate_type": item.get("certificateType"),
                        "domain_address": item.get("domainAddress")
                        or item.get("commonName"),
                        "valid_start_date": item.get("validStartDate"),
                        "valid_end_date": item.get("validEndDate"),
                        "external": item.get("externalYn"),
                        "used_instance_nos": self._unique_values(
                            used_instances or []
                        ),
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
                resource_type,
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
                    resource_id=item.get("resourceId") or item.get("nrn"),
                    resource_name=item.get("resourceName"),
                    status=None,
                    region_code=item.get("regionCode"),
                    zone_code=None,
                    platform=platform,
                    create_time=item.get("createTime"),
                    details={
                        "inventory_source": "RESOURCE_MANAGER",
                        "source_product": product_name,
                        "source_resource_type": resource_type,
                        "source_nrn": item.get("nrn"),
                        "create_time_source": (
                            "RESOURCE_MANAGER"
                            if item.get("createTime") not in (None, "")
                            else None
                        ),
                        "resource_manager_event_time": item.get(
                            "eventTime"
                        ),
                    },
                )
            )
        return result

    def enrich_resource_manager_creation_times(
        self,
        resources: Iterable[Mapping[str, Any]],
        items: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge authoritative Resource Manager creation-time evidence.

        Service APIs remain the inventory source. A resource is enriched only
        when its canonical NRN matches exactly or when its category and
        resource ID identify exactly one Resource Manager record. This avoids
        name-based guesses and cross-service numeric-ID collisions.
        """

        normalized_resources = self._dict_items(resources)
        resource_manager_items = self._dict_items(items)
        by_nrn: Dict[str, List[Dict[str, Any]]] = {}
        by_category_and_id: Dict[
            tuple[str, str],
            List[Dict[str, Any]],
        ] = {}

        for item in resource_manager_items:
            nrn = self._string(item.get("nrn"))
            if nrn:
                by_nrn.setdefault(nrn, []).append(item)

            category = self._resource_manager_category(item)
            resource_id = self._string(item.get("resourceId"))
            if category and resource_id:
                by_category_and_id.setdefault(
                    (category, resource_id),
                    [],
                ).append(item)

        for resource in normalized_resources:
            category = self.CATEGORY_ALIASES.get(
                str(resource.get("category") or "").strip().upper()
            )
            if category not in self.CATEGORY_LABELS:
                continue

            details = self._mapping(resource.get("details"))
            source_nrn = self._string(details.get("source_nrn"))
            resource_id = self._string(resource.get("resource_id"))

            candidates: List[Dict[str, Any]] = []
            match_basis = None
            if source_nrn:
                candidates = by_nrn.get(source_nrn, [])
                if candidates:
                    match_basis = "NRN"
            if not candidates and resource_id and resource_id in by_nrn:
                candidates = by_nrn[resource_id]
                match_basis = "NRN"
            if not candidates and resource_id:
                candidates = by_category_and_id.get(
                    (category, resource_id),
                    [],
                )
                if candidates:
                    match_basis = "RESOURCE_ID"

            if len(candidates) != 1:
                continue

            evidence = candidates[0]
            create_time = evidence.get("createTime")
            if create_time not in (None, ""):
                resource["create_time"] = create_time
                details["create_time_source"] = "RESOURCE_MANAGER"

            evidence_nrn = self._string(evidence.get("nrn"))
            if evidence_nrn:
                details["source_nrn"] = evidence_nrn
            evidence_id = self._string(evidence.get("resourceId"))
            if evidence_id:
                details["resource_manager_resource_id"] = evidence_id
            event_time = evidence.get("eventTime")
            if event_time not in (None, ""):
                details["resource_manager_event_time"] = event_time
            details["resource_manager_match_basis"] = match_basis
            resource["details"] = self._sanitize_details(details)

        return normalized_resources

    def finalize(
        self,
        resources: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        index_by_id: Dict[tuple[str, str, str], int] = {}

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
                id_key = (
                    category,
                    self._string(resource.get("platform")) or "",
                    resource["resource_id"],
                )

            existing_index = (
                index_by_id.get(id_key) if id_key is not None else None
            )

            if existing_index is not None:
                self._merge_missing(result[existing_index], resource)
                continue

            result.append(resource)
            current_index = len(result) - 1
            if id_key is not None:
                index_by_id[id_key] = current_index

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
        resource_type: Optional[str] = None,
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
        if category == "SECURITY_SERVICE":
            return self._string(resource_type) or self._string(platform_type)
        if category in {
            "AUTO_SCALING",
            "CLOUD_FUNCTIONS",
            "IPSEC_VPN",
            "CLOUD_CONNECT",
        }:
            return "VPC" if product.startswith("VPC") else platform_type
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
        normalized_details = dict(details)
        normalized_details.setdefault("inventory_source", "SERVICE_API")
        normalized_details.setdefault("source_product", service_name)
        normalized_details.setdefault("source_resource_type", resource_type)
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
            "details": self._sanitize_details(normalized_details),
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
            if (
                str(key) in self._STRUCTURED_DETAIL_FIELDS
                and isinstance(item, (list, tuple))
            ):
                records = self._sanitize_detail_records(item)
                if records:
                    sanitized[str(key)] = records
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

    def _sanitize_detail_records(
        self,
        value: Iterable[Any],
    ) -> List[Dict[str, Any]]:
        """허용된 상세 레코드에서 민감값과 URL을 제거한다."""

        result: List[Dict[str, Any]] = []
        for candidate in list(value)[:500]:
            if not isinstance(candidate, Mapping):
                continue
            sanitized = {}
            for key, item in candidate.items():
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
            if sanitized:
                result.append(sanitized)
        return result

    def _nic_private_ips(self, nic: Mapping[str, Any]) -> List[Any]:
        normalized = self._as_list(nic.get("all_private_ips"))
        if normalized:
            return normalized
        return [
            self._value(nic, "primary_ip", "ip", "privateIp"),
            *self._as_list(
                self._value(nic, "secondary_ips", "secondaryIpList")
            ),
        ]

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
    def _code_value(value: Any) -> Any:
        if isinstance(value, Mapping):
            return value.get("code") or value.get("codeName")
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

    @staticmethod
    def _unique_values(values: Iterable[Any]) -> List[Any]:
        result = []
        seen = set()
        for value in values:
            if value is None:
                continue
            rendered = str(value).strip()
            if not rendered or rendered in seen:
                continue
            seen.add(rendered)
            result.append(value)
        return result


__all__ = ["InfrastructureNormalizer"]

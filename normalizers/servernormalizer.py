from collections import defaultdict
from typing import Any, Dict, List, Tuple

from utils.common_utils import bytes_to_gb, bytes_to_mb


class ServerNormalizer:
    def normalize(
        self,
        raw_data: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        raw_servers = raw_data.get("servers", [])
        raw_nics = raw_data.get("nics", [])
        raw_storages = raw_data.get("storages", [])

        nic_map = self._build_nic_map(raw_nics)
        storage_map = self._build_storage_map(raw_storages)

        return self._normalize_servers(
            raw_servers=raw_servers,
            nic_map=nic_map,
            storage_map=storage_map,
        )

    def _build_nic_map(
        self,
        raw_nics: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        nic_map = {}

        for nic in raw_nics:
            nic_id = nic.get("networkInterfaceNo")

            if nic_id:
                nic_map[nic_id] = nic

        return nic_map

    def _build_storage_map(
        self,
        raw_storages: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        storage_map = defaultdict(list)

        for storage in raw_storages:
            server_id = storage.get("serverInstanceNo")

            if server_id:
                storage_map[server_id].append(storage)

        return dict(storage_map)

    def _normalize_servers(
        self,
        raw_servers: List[Dict[str, Any]],
        nic_map: Dict[str, Dict[str, Any]],
        storage_map: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        result = []

        for server in raw_servers:
            server_id = server.get("serverInstanceNo")

            raw_nics = self._get_server_raw_nics(
                server=server,
                nic_map=nic_map,
            )

            nics = [
                self._normalize_nic(nic)
                for nic in raw_nics
            ]

            primary_nic = next(
                (nic for nic in nics if nic.get("is_default")),
                nics[0] if nics else {},
            )

            raw_storages = storage_map.get(server_id, [])

            storages = [
                self._normalize_storage(storage)
                for storage in raw_storages
            ]

            os_storages, data_storages = self._split_storages(storages)

            hypervisor_type = server.get("hypervisorType", {})

            result.append(
                {
                    "server_id": server_id,
                    "server_name": server.get("serverName"),
                    "cpu_count": server.get("cpuCount"),
                    "memory_size": server.get("memorySize"),
                    "memory_gb": bytes_to_gb(server.get("memorySize")),
                    "login_key": server.get("loginKeyName"),
                    "public_ip": server.get("publicIp"),

                    "private_ip": primary_nic.get("primary_ip"),
                    "mac_address": primary_nic.get("mac_address"),
                    "nic_id": primary_nic.get("nic_id"),
                    "nics": nics,

                    "os_storages": os_storages,
                    "data_storages": data_storages,
                    "storages": storages,

                    "status": server.get("serverInstanceStatusName"),
                    "uptime": server.get("uptime"),
                    "is_protected": server.get("isProtectServerTermination"),
                    "zone_code": server.get("zoneCode"),
                    "region_code": server.get("regionCode"),
                    "vpc_id": server.get("vpcNo"),
                    "subnet_id": server.get("subnetNo"),
                    "hypervisor_type": hypervisor_type.get("codeName"),
                    "server_image_no": server.get("serverImageNo"),
                    "event_list": server.get("eventList", []),

                    # 원본 보존
                    "raw_server": server,
                    "raw_nics": raw_nics,
                    "raw_storages": raw_storages,
                }
            )

        return result

    def _get_server_raw_nics(
        self,
        server: Dict[str, Any],
        nic_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        nic_ids = server.get("networkInterfaceNoList", [])

        if not nic_ids and server.get("nicInstanceNo"):
            nic_ids = [server.get("nicInstanceNo")]

        result = []

        for nic_id in nic_ids:
            nic = nic_map.get(nic_id)

            if nic:
                result.append(nic)

        return result

    def _normalize_nic(
        self,
        nic: Dict[str, Any],
    ) -> Dict[str, Any]:
        primary_ip = nic.get("ip")
        secondary_ips = nic.get("secondaryIpList", [])

        all_private_ips = []

        if primary_ip:
            all_private_ips.append(primary_ip)

        all_private_ips.extend(secondary_ips)

        return {
            "nic_id": nic.get("networkInterfaceNo"),
            "nic_name": nic.get("networkInterfaceName"),
            "device_name": nic.get("deviceName"),
            "is_default": nic.get("isDefault"),
            "mac_address": nic.get("macAddress"),
            "primary_ip": primary_ip,
            "secondary_ips": secondary_ips,
            "all_private_ips": all_private_ips,
            "subnet_id": nic.get("subnetNo"),
            "acg_ids": nic.get("accessControlGroupNoList", []),
            "raw": nic,
        }

    def _normalize_storage(
        self,
        storage: Dict[str, Any],
    ) -> Dict[str, Any]:
        block_storage_type = storage.get("blockStorageType", {})
        disk_type = storage.get("blockStorageDiskType", {})
        disk_detail_type = storage.get("blockStorageDiskDetailType", {})
        volume_type = storage.get("blockStorageVolumeType", {})
        hypervisor_type = storage.get("hypervisorType", {})

        throughput = storage.get("throughput")

        return {
            "storage_id": storage.get("blockStorageInstanceNo"),
            "server_id": storage.get("serverInstanceNo"),
            "storage_name": storage.get("blockStorageName"),
            "device_name": storage.get("deviceName"),

            "is_os_disk": block_storage_type.get("code") == "BASIC",

            "storage_type_code": block_storage_type.get("code"),
            "storage_type_name": block_storage_type.get("codeName"),

            "size_gb": bytes_to_gb(storage.get("blockStorageSize")),

            "disk_type_code": disk_type.get("code"),
            "disk_type_name": disk_type.get("codeName"),

            "disk_detail_type_code": disk_detail_type.get("code"),
            "disk_detail_type_name": disk_detail_type.get("codeName"),

            "volume_type_code": volume_type.get("code"),
            "volume_type_name": volume_type.get("codeName"),

            "iops": storage.get("iops"),
            "max_iops_throughput": storage.get("maxIopsThroughput"),

            "throughput_bps": throughput,
            "throughput_mbps": bytes_to_mb(throughput),

            "status": storage.get("blockStorageInstanceStatusName"),
            "status_name": storage.get(
                "blockStorageInstanceStatus",
                {},
            ).get("codeName"),

            "is_encrypted": storage.get("isEncryptedVolume"),
            "is_return_protection": storage.get("isReturnProtection"),

            "zone_code": storage.get("zoneCode"),
            "region_code": storage.get("regionCode"),

            "hypervisor_type": hypervisor_type.get("codeName"),
            "product_code": storage.get("blockStorageProductCode"),
            "snapshot_id": storage.get("blockStorageSnapshotInstanceNo"),
            "create_date": storage.get("createDate"),

            "raw": storage,
        }

    def _split_storages(
        self,
        storages: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        os_storages = []
        data_storages = []

        for storage in storages:
            if storage.get("is_os_disk"):
                os_storages.append(storage)
            else:
                data_storages.append(storage)

        return os_storages, data_storages
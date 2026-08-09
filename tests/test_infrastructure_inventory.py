import json
import unittest
from unittest.mock import Mock

import requests

from app.apifactory import APIFactory
from collectors.infrastructurecollector import InfrastructureCollector
from config.endpoints import build_api_endpoints
from ncp_api.cdnAPI import CdnAPI
from ncp_api.clouddbAPI import CloudDbAPI
from normalizers.infrastructurenormalizer import InfrastructureNormalizer


class RecordingClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, **kwargs):
        self.calls.append((endpoint, kwargs))
        return {}


class FakeFactory:
    def __init__(self, **apis):
        self.apis = apis
        self.requests = []

    def get(self, name):
        self.requests.append(name)
        return self.apis[name]


def wrapped(response_key, list_key, items):
    return {
        response_key: {
            "totalRows": len(items),
            list_key: items,
        }
    }


class EmptyCloudDbAPI:
    def get_cloud_mysql_instance_list(self, **kwargs):
        return wrapped(
            "getCloudMysqlInstanceListResponse",
            "cloudMysqlInstanceList",
            [],
        )

    def get_cloud_postgresql_instance_list(self, **kwargs):
        return wrapped(
            "getCloudPostgresqlInstanceListResponse",
            "cloudPostgresqlInstanceList",
            [],
        )

    def get_cloud_mssql_instance_list(self, **kwargs):
        return wrapped(
            "getCloudMssqlInstanceListResponse",
            "cloudMssqlInstanceList",
            [],
        )

    def get_cloud_mongodb_instance_list(self, **kwargs):
        return wrapped(
            "getCloudMongoDbInstanceListResponse",
            "cloudMongoDbInstanceList",
            [],
        )

    def get_cloud_cache_instance_list(self, **kwargs):
        return wrapped(
            "getCloudCacheInstanceListResponse",
            "cloudCacheInstanceList",
            [],
        )


class InventoryCloudDbAPI(EmptyCloudDbAPI):
    def get_cloud_mysql_instance_list(self, **kwargs):
        return wrapped(
            "getCloudMysqlInstanceListResponse",
            "cloudMysqlInstanceList",
            [
                {
                    "cloudMysqlInstanceNo": "db-1",
                    "cloudMysqlServiceName": "orders-db",
                    "cloudMysqlInstanceStatusName": "running",
                    "isHa": True,
                    "generationCode": "G3",
                    "adminPassword": "never-store-this",
                    "cloudMysqlServerInstanceList": [
                        {
                            "cloudMysqlServerInstanceNo": "db-server-1",
                            "regionCode": "KR",
                            "zoneCode": "KR-1",
                            "vpcNo": "vpc-1",
                            "subnetNo": "subnet-1",
                            "cpuCount": 2,
                            "memorySize": 4 * 1024 ** 3,
                            "dataStorageSize": 100 * 1024 ** 3,
                        }
                    ],
                }
            ],
        )


class EmptyLoadBalancerAPI:
    def get_load_balancer_instance_list(self, **kwargs):
        return wrapped(
            "getLoadBalancerInstanceListResponse",
            "loadBalancerInstanceList",
            [],
        )

    def get_target_group_list(self, **kwargs):
        return wrapped(
            "getTargetGroupListResponse",
            "targetGroupList",
            [],
        )

    def get_target_list(self, **kwargs):
        return wrapped("getTargetListResponse", "targetList", [])


class InventoryLoadBalancerAPI(EmptyLoadBalancerAPI):
    def get_load_balancer_instance_list(self, **kwargs):
        return wrapped(
            "getLoadBalancerInstanceListResponse",
            "loadBalancerInstanceList",
            [
                {
                    "loadBalancerInstanceNo": "lb-1",
                    "loadBalancerName": "public-alb",
                    "loadBalancerInstanceStatusName": "running",
                    "regionCode": "KR",
                    "loadBalancerType": {"code": "APPLICATION"},
                    "loadBalancerNetworkType": {"code": "PUBLIC"},
                    "loadBalancerIpList": ["203.0.113.1"],
                }
            ],
        )


class EmptyNasAPI:
    def get_nas_volume_instance_list(self, **kwargs):
        return wrapped(
            "getNasVolumeInstanceListResponse",
            "nasVolumeInstanceList",
            [],
        )


class InventoryNasAPI(EmptyNasAPI):
    def get_nas_volume_instance_list(self, **kwargs):
        return wrapped(
            "getNasVolumeInstanceListResponse",
            "nasVolumeInstanceList",
            [
                {
                    "nasVolumeInstanceNo": "nas-1",
                    "volumeName": "shared-data",
                    "nasVolumeInstanceStatusName": "running",
                    "regionCode": "KR",
                    "zoneCode": "KR-1",
                    "volumeTotalSize": 500 * 1024 ** 3,
                    "volumeAllotmentProtocolType": {"code": "NFS"},
                }
            ],
        )


class InventoryClassicNasAPI(EmptyNasAPI):
    def get_nas_volume_instance_list(self, **kwargs):
        return wrapped(
            "getNasVolumeInstanceListResponse",
            "nasVolumeInstanceList",
            [
                {
                    "nasVolumeInstanceNo": "classic-nas-1",
                    "volumeName": "classic-shared-data",
                    "nasVolumeInstanceStatusName": "created",
                    "region": {"regionNo": "1", "regionCode": "KR"},
                    "zone": {"zoneNo": "3", "zoneCode": "KR-2"},
                    "volumeTotalSize": 100 * 1024 ** 3,
                    "volumeAllotmentProtocolType": {"code": "NFS"},
                    "nasVolumeServerInstanceList": [
                        {"serverInstanceNo": "classic-server-1"}
                    ],
                }
            ],
        )


class EmptyKubernetesAPI:
    def get_nks_cluster_list(self):
        return {"clusters": []}


class InventoryKubernetesAPI:
    def get_nks_cluster_list(self):
        return {
            "clusters": [
                {
                    "uuid": "cluster-uuid",
                    "instanceNo": 100,
                    "name": "production-nks",
                    "status": "RUNNING",
                    "regionCode": "KR",
                    "zoneCode": "KR-1",
                    "nodeCount": 3,
                    "k8sVersion": "1.33",
                    "endpoint": "https://private.example.invalid",
                    "loginKeyName": "never-store-this",
                }
            ]
        }


class EmptyCdnAPI:
    def get_global_cdn_instance_list(self, **kwargs):
        return wrapped(
            "getGlobalCdnInstanceListResponse",
            "globalCdnInstanceList",
            [],
        )

    def get_cdn_plus_instance_list(self, **kwargs):
        return wrapped(
            "getCdnPlusInstanceListResponse",
            "cdnPlusInstanceList",
            [],
        )


class InventoryCdnAPI(EmptyCdnAPI):
    def get_global_cdn_instance_list(self, **kwargs):
        return wrapped(
            "getGlobalCdnInstanceListResponse",
            "globalCdnInstanceList",
            [
                {
                    "cdnInstanceNo": "cdn-1",
                    "serviceName": "static-assets",
                    "cdnInstanceStatusName": "running",
                    "globalCdnServiceDomainList": [
                        {"defaultDomainName": "hidden.example.invalid"}
                    ],
                    "globalCdnRule": {
                        "protocolTypeCode": "HTTPS",
                        "originUrl": "private-origin.example.invalid",
                        "secureTokenPassword": "never-store-this",
                    },
                }
            ],
        )


class EmptyResourceManagerAPI:
    def get_resource_list(self, page, size, region_code=None):
        del region_code
        return {"items": [], "hasMore": False}


class EmptyVpcAPI:
    def get_vpc_list(self, **kwargs):
        return wrapped("getVpcListResponse", "vpcList", [])

    def get_subnet_list(self, **kwargs):
        return wrapped("getSubnetListResponse", "subnetList", [])

    def get_nat_gateway_instance_list(self, **kwargs):
        return wrapped(
            "getNatGatewayInstanceListResponse",
            "natGatewayInstanceList",
            [],
        )

    def get_vpc_peering_instance_list(self, **kwargs):
        return wrapped(
            "getVpcPeeringInstanceListResponse",
            "vpcPeeringInstanceList",
            [],
        )

    def get_route_table_list(self, **kwargs):
        return wrapped(
            "getRouteTableListResponse",
            "routeTableList",
            [],
        )


class EmptyVserverAPI:
    def get_network_interface_instance_list(self, **kwargs):
        return wrapped(
            "getNetworkInterfaceListResponse",
            "networkInterfaceList",
            [],
        )

    def get_block_storage_instance_list(self, **kwargs):
        return wrapped(
            "getBlockStorageInstanceListResponse",
            "blockStorageInstanceList",
            [],
        )

    def get_public_ip_instance_list(self, **kwargs):
        return wrapped(
            "getPublicIpInstanceListResponse",
            "publicIpInstanceList",
            [],
        )

    def get_block_storage_snapshot_instance_list(self, **kwargs):
        return wrapped(
            "getBlockStorageSnapshotInstanceListResponse",
            "blockStorageSnapshotInstanceList",
            [],
        )

    def get_member_server_instance_list(self, **kwargs):
        return wrapped(
            "getMemberServerImageInstanceListResponse",
            "memberServerImageInstanceList",
            [],
        )


class EmptyGlobalDnsAPI:
    def get_domain(self, **kwargs):
        return {"content": [], "last": True}


class EmptyCertificateManagerAPI:
    def get_certificate_list(self):
        return {"totalRows": 0, "sslCertificateList": []}


class EmptyContainerAPI:
    def get_registry_list(self, **kwargs):
        return {"count": 0, "next": None, "results": []}


class InventoryResourceManagerAPI:
    def get_resource_list(self, page, size, region_code=None):
        del region_code
        return {
            "items": [
                {
                    "nrn": "nrn:server:1",
                    "platformType": "VPC",
                    "productName": "VPCServer",
                    "resourceType": "Server",
                    "resourceId": "server-1",
                    "resourceName": "app-server",
                },
                {
                    "nrn": "nrn:object-storage:1",
                    "platformType": "BOTH",
                    "productName": "Object Storage",
                    "resourceType": "Bucket",
                    "resourceId": "bucket-1",
                    "resourceName": "report-archive",
                },
                {
                    "nrn": "nrn:alarm:1",
                    "platformType": "BOTH",
                    "productName": "Cloud Insight",
                    "resourceType": "AlarmRule",
                    "resourceId": "alarm-1",
                    "resourceName": "cpu-alarm",
                },
                {
                    "nrn": "nrn:iam:1",
                    "platformType": "BOTH",
                    "productName": "Sub Account",
                    "resourceType": "IAMUser",
                    "resourceId": "user-1",
                    "resourceName": "operator",
                },
            ],
            "hasMore": False,
        }


def build_factory(**overrides):
    apis = {
        "loadbalancer": EmptyLoadBalancerAPI(),
        "vnas": EmptyNasAPI(),
        "nas_classic": EmptyNasAPI(),
        "cloud_db": EmptyCloudDbAPI(),
        "kubernetes": EmptyKubernetesAPI(),
        "cdn": EmptyCdnAPI(),
        "resource_manager": EmptyResourceManagerAPI(),
        "vpc": EmptyVpcAPI(),
        "vserver": EmptyVserverAPI(),
        "global_dns": EmptyGlobalDnsAPI(),
        "certificate_manager": EmptyCertificateManagerAPI(),
        "container": EmptyContainerAPI(),
    }
    apis.update(overrides)
    return FakeFactory(**apis)


class InfrastructureAPIContractTests(unittest.TestCase):
    def test_cloud_db_wrappers_use_documented_paths_and_paging(self):
        client = RecordingClient()
        api = CloudDbAPI(client=client)
        methods_and_paths = (
            (
                api.get_cloud_mysql_instance_list,
                "/vmysql/v2/getCloudMysqlInstanceList",
            ),
            (
                api.get_cloud_postgresql_instance_list,
                "/vpostgresql/v2/getCloudPostgresqlInstanceList",
            ),
            (
                api.get_cloud_mssql_instance_list,
                "/vmssql/v2/getCloudMssqlInstanceList",
            ),
            (
                api.get_cloud_mongodb_instance_list,
                "/vmongodb/v2/getCloudMongoDbInstanceList",
            ),
            (
                api.get_cloud_cache_instance_list,
                "/vcache/v2/getCloudCacheInstanceList",
            ),
        )

        for method, expected_path in methods_and_paths:
            with self.subTest(path=expected_path):
                method(region_code="KR", page_no=1, page_size=100)
                path, kwargs = client.calls[-1]
                self.assertEqual(path, expected_path)
                self.assertEqual(kwargs["params"]["regionCode"], "KR")
                self.assertEqual(kwargs["params"]["pageNo"], 1)
                self.assertEqual(kwargs["params"]["pageSize"], 100)
                with self.assertRaises(ValueError):
                    method(page_no=1)

    def test_cdn_wrappers_and_factory_registration(self):
        client = RecordingClient()
        api = CdnAPI(client=client)

        api.get_global_cdn_instance_list(page_no=1, page_size=100)
        self.assertEqual(client.calls[-1][0], "/getGlobalCdnInstanceList")
        api.get_cdn_plus_instance_list(page_no=1, page_size=100)
        self.assertEqual(client.calls[-1][0], "/getCdnPlusInstanceList")

        endpoints = build_api_endpoints("public", "KR")
        self.assertEqual(endpoints["clouddb"], endpoints["vserver"])
        self.assertTrue(endpoints["cdn"].endswith("/cdn/v2"))
        self.assertIn("cloud_db", APIFactory().available_apis())
        self.assertIn("cdn", APIFactory().available_apis())


class InfrastructureCollectorTests(unittest.TestCase):
    def test_collects_vpc_and_classic_nas_as_separate_platforms(self):
        collector = InfrastructureCollector(
            build_factory(
                vnas=InventoryNasAPI(),
                nas_classic=InventoryClassicNasAPI(),
            )
        )

        resources = collector.collect([], {}, categories=("NAS",))
        by_id = {resource["resource_id"]: resource for resource in resources}

        self.assertEqual(set(by_id), {"nas-1", "classic-nas-1"})
        self.assertEqual(by_id["nas-1"]["platform"], "VPC")
        classic = by_id["classic-nas-1"]
        self.assertEqual(classic["platform"], "CLASSIC")
        self.assertEqual(classic["region_code"], "KR")
        self.assertEqual(classic["zone_code"], "KR-2")
        self.assertEqual(
            classic["details"]["server_instance_nos"],
            ["classic-server-1"],
        )
        self.assertEqual(
            classic["details"]["explicit_relations"],
            [
                {
                    "type": "ATTACHED_TO",
                    "target_category": "SERVER",
                    "target_id": "classic-server-1",
                    "source_field": "nasVolumeServerInstanceList",
                }
            ],
        )
        self.assertEqual(collector.last_errors, [])
        self.assertEqual(collector.last_warnings, [])

    def test_nas_platform_permission_failure_does_not_block_other_platform(self):
        response = requests.Response()
        response.status_code = 403
        response._content = b'{"error":{"errorCode":"2300"}}'
        response.headers["Content-Type"] = "application/json"

        for failing_key, expected_id, expected_platform in (
            ("vnas", "classic-nas-1", "CLASSIC"),
            ("nas_classic", "nas-1", "VPC"),
        ):
            with self.subTest(failing_key=failing_key):
                failing_api = Mock()
                failing_api.get_nas_volume_instance_list.side_effect = (
                    requests.HTTPError("forbidden", response=response)
                )
                nas_apis = {
                    "vnas": InventoryNasAPI(),
                    "nas_classic": InventoryClassicNasAPI(),
                }
                nas_apis[failing_key] = failing_api
                factory = build_factory(**nas_apis)
                collector = InfrastructureCollector(factory)

                resources = collector.collect([], {}, categories=("NAS",))

                self.assertEqual(len(resources), 1)
                self.assertEqual(resources[0]["resource_id"], expected_id)
                self.assertEqual(resources[0]["platform"], expected_platform)
                self.assertEqual(collector.last_errors, [])
                self.assertEqual(len(collector.last_warnings), 1)
                self.assertEqual(
                    collector.last_warnings[0]["status_code"],
                    403,
                )
                self.assertEqual(
                    collector.last_warnings[0]["error_code"],
                    "2300",
                )

    def test_normalizer_canonicalizes_supported_category_aliases(self):
        resources = InfrastructureNormalizer().finalize(
            [
                {
                    "category": "CDB",
                    "resource_id": "db-1",
                    "resource_name": "database",
                    "details": {},
                },
                {
                    "category": "NKS",
                    "resource_id": "cluster-1",
                    "resource_name": "cluster",
                    "details": {},
                },
            ]
        )

        self.assertEqual(
            [resource["category"] for resource in resources],
            ["CLOUD_DB", "KUBERNETES"],
        )

    def test_same_name_with_different_ids_is_not_deduplicated(self):
        resources = InfrastructureNormalizer().finalize(
            [
                {
                    "category": "SERVER",
                    "resource_id": "server-1",
                    "resource_name": "app",
                    "platform": "VPC",
                    "region_code": "KR",
                    "details": {},
                },
                {
                    "category": "SERVER",
                    "resource_id": "server-2",
                    "resource_name": "app",
                    "platform": "VPC",
                    "region_code": "KR",
                    "details": {},
                },
            ]
        )

        self.assertEqual(
            {resource["resource_id"] for resource in resources},
            {"server-1", "server-2"},
        )

    def test_same_name_without_ids_is_not_heuristically_merged(self):
        resources = InfrastructureNormalizer().finalize([
            {
                "category": "SERVER",
                "resource_name": "duplicate-name",
                "platform": "VPC",
                "region_code": "KR",
                "zone_code": "KR-1",
                "details": {"private_ip": "10.0.0.1"},
            },
            {
                "category": "SERVER",
                "resource_name": "duplicate-name",
                "platform": "VPC",
                "region_code": "KR",
                "zone_code": "KR-2",
                "details": {"private_ip": "10.0.0.2"},
            },
        ])

        self.assertEqual(len(resources), 2)

    def test_resource_manager_preserves_nrn_as_canonical_evidence(self):
        resources = InfrastructureNormalizer().normalize_resource_manager([
            {
                "nrn": "nrn:PUB:Server:KR:123:Server/456",
                "productName": "VPCServer",
                "resourceType": "ServerInstance",
                "resourceId": "456",
                "resourceName": "server",
                "platformType": "VPC",
            }
        ])

        self.assertEqual(resources[0]["resource_id"], "456")
        self.assertEqual(
            resources[0]["details"]["source_nrn"],
            "nrn:PUB:Server:KR:123:Server/456",
        )

    def test_resource_manager_creation_time_enriches_service_inventory(self):
        normalizer = InfrastructureNormalizer()
        resources = normalizer.normalize_servers(
            [
                {
                    "server_id": "456",
                    "server_name": "app-server",
                    "create_time": "2025-01-01T00:00:00+09:00",
                }
            ],
            [],
        )

        enriched = normalizer.enrich_resource_manager_creation_times(
            resources,
            [
                {
                    "nrn": "nrn:PUB:Server:KR:123:Server/456",
                    "productName": "VPCServer",
                    "resourceType": "ServerInstance",
                    "resourceId": "456",
                    "createTime": 1_767_225_600_000,
                    "eventTime": 1_767_312_000_000,
                }
            ],
        )

        self.assertEqual(enriched[0]["create_time"], 1_767_225_600_000)
        self.assertEqual(
            enriched[0]["details"]["inventory_source"],
            "SERVICE_API",
        )
        self.assertEqual(
            enriched[0]["details"]["create_time_source"],
            "RESOURCE_MANAGER",
        )
        self.assertEqual(
            enriched[0]["details"]["source_nrn"],
            "nrn:PUB:Server:KR:123:Server/456",
        )
        self.assertEqual(
            enriched[0]["details"]["resource_manager_match_basis"],
            "RESOURCE_ID",
        )
        self.assertEqual(
            enriched[0]["details"]["resource_manager_event_time"],
            1_767_312_000_000,
        )

    def test_resource_manager_creation_time_requires_unambiguous_id(self):
        normalizer = InfrastructureNormalizer()
        resources = normalizer.normalize_servers(
            [
                {
                    "server_id": "456",
                    "server_name": "app-server",
                    "create_time": "service-api-time",
                }
            ],
            [],
        )
        duplicate_evidence = [
            {
                "nrn": f"nrn:PUB:Server:KR:123:Server/456:{index}",
                "productName": "VPCServer",
                "resourceType": "ServerInstance",
                "resourceId": "456",
                "createTime": index,
            }
            for index in (1, 2)
        ]

        enriched = normalizer.enrich_resource_manager_creation_times(
            resources,
            duplicate_evidence,
        )

        self.assertEqual(enriched[0]["create_time"], "service-api-time")
        self.assertNotIn(
            "create_time_source",
            enriched[0]["details"],
        )

    def test_resource_manager_creation_time_can_match_canonical_nrn(self):
        nrn = "nrn:PUB:Server:KR:123:Server/456"
        enriched = (
            InfrastructureNormalizer()
            .enrich_resource_manager_creation_times(
                [
                    {
                        "category": "SERVER",
                        "resource_id": "service-api-alias",
                        "resource_name": "app-server",
                        "create_time": "service-api-time",
                        "details": {"source_nrn": nrn},
                    }
                ],
                [
                    {
                        "nrn": nrn,
                        "productName": "VPCServer",
                        "resourceType": "ServerInstance",
                        "resourceId": "456",
                        "createTime": 1_767_225_600_000,
                    }
                ],
            )
        )

        self.assertEqual(enriched[0]["create_time"], 1_767_225_600_000)
        self.assertEqual(
            enriched[0]["details"]["resource_manager_match_basis"],
            "NRN",
        )

    def test_resource_manager_platform_aliases_match_direct_inventory(self):
        resources = InfrastructureNormalizer().normalize_resource_manager(
            [
                {
                    "productName": "VPCCloudDBforRedis",
                    "resourceType": "Service",
                    "resourceId": "redis-1",
                    "resourceName": "cache",
                    "platformType": "VPC",
                },
                {
                    "productName": "GCDN",
                    "resourceType": "Service",
                    "resourceId": "cdn-1",
                    "resourceName": "static",
                    "platformType": "VPC",
                },
                {
                    "productName": "CDBServerless",
                    "resourceType": "Service",
                    "resourceId": "serverless-1",
                    "resourceName": "serverless",
                    "platformType": "VPC",
                },
            ]
        )

        self.assertEqual(
            {
                resource["resource_id"]: resource["platform"]
                for resource in resources
            },
            {
                "redis-1": "CACHE",
                "cdn-1": "GLOBAL_CDN",
                "serverless-1": "SERVERLESS",
            },
        )

    def test_target_group_health_is_counted_without_response_payload(self):
        normalizer = InfrastructureNormalizer()
        resources = normalizer.normalize_load_balancers(
            [{
                "loadBalancerInstanceNo": "lb-1",
                "loadBalancerName": "public-alb",
                "vpcNo": "vpc-1",
            }],
            [{
                "targetGroupNo": "tg-1",
                "targetGroupName": "web-targets",
                "loadBalancerInstanceNo": "lb-1",
                "vpcNo": "vpc-1",
                "targetType": {"code": "VSVR"},
                "targetGroupProtocolType": {"code": "HTTP"},
                "targetGroupPort": 8080,
            }],
            {
                "tg-1": [
                    {
                        "targetNo": "server-1",
                        "healthCheckStatus": {"code": "UP"},
                        "healthCheckResponse": "sensitive-response",
                    },
                    {
                        "targetNo": "server-2",
                        "healthCheckStatus": {"code": "DOWN"},
                    },
                    {
                        "targetNo": "server-3",
                        "healthCheckStatus": {"code": "UNUSED"},
                    },
                    {
                        "targetNo": "server-4",
                        "healthCheckStatus": {"code": "NEW_STATUS"},
                    },
                ]
            },
        )

        load_balancer = next(
            resource
            for resource in resources
            if resource["category"] == "LOAD_BALANCER"
        )
        target_group = next(
            resource
            for resource in resources
            if resource["category"] == "TARGET_GROUP"
        )
        details = target_group["details"]

        self.assertEqual(target_group["status"], "UNREADY")
        self.assertEqual(details["registered_target_count"], 4)
        self.assertEqual(details["ready_target_count"], 1)
        self.assertEqual(details["unready_target_count"], 1)
        self.assertEqual(details["unused_target_count"], 1)
        self.assertEqual(details["unknown_target_count"], 1)
        self.assertTrue(details["health_snapshot_available"])
        self.assertEqual(load_balancer["details"]["ready_target_count"], 1)
        self.assertNotIn("healthCheckResponse", str(resources))
        self.assertNotIn("sensitive-response", str(resources))

    def test_target_group_empty_and_failed_health_snapshots_are_distinct(self):
        normalizer = InfrastructureNormalizer()
        groups = [{
            "targetGroupNo": "tg-1",
            "targetGroupName": "web-targets",
            "loadBalancerInstanceNo": "lb-1",
            "targetType": {"code": "VSVR"},
            "targetNoList": ["server-1"],
        }]
        load_balancers = [{"loadBalancerInstanceNo": "lb-1"}]

        empty = normalizer.normalize_load_balancers(
            load_balancers,
            groups,
            {"tg-1": []},
        )
        failed = normalizer.normalize_load_balancers(
            load_balancers,
            groups,
            {},
        )
        empty_group = next(
            item for item in empty if item["category"] == "TARGET_GROUP"
        )
        failed_group = next(
            item for item in failed if item["category"] == "TARGET_GROUP"
        )

        self.assertEqual(empty_group["status"], "EMPTY")
        self.assertTrue(
            empty_group["details"]["health_snapshot_available"]
        )
        self.assertEqual(empty_group["details"]["registered_target_count"], 0)
        self.assertEqual(failed_group["status"], "UNKNOWN")
        self.assertFalse(
            failed_group["details"]["health_snapshot_available"]
        )
        self.assertEqual(failed_group["details"]["registered_target_count"], 1)

    def test_resource_manager_uses_official_parent_resource_codes(self):
        items = [
            ("VPCServer", "Server", "server"),
            ("VPCServer", "Storage", "storage"),
            ("VPCLoadBalancer", "LoadBalancer", "vpc-lb"),
            ("LoadBalancer", "Instance", "classic-lb"),
            ("VPCNAS", "Volume", "vpc-nas"),
            ("NAS", "Volume", "classic-nas"),
            ("VPCCloudDBforMySQL", "Service", "mysql"),
            ("VPCCloudDBforPostgreSQL", "Service", "postgresql"),
            ("VPCKubernetesService", "Cluster", "nks"),
            ("GCDN", "Service", "gcdn"),
            ("ObjectStorage", "Bucket", "bucket"),
        ]
        excluded = [
            ("VPCCloudDBforMySQL", "Server", "db-child"),
            ("VPCKubernetesService", "NodePool", "node-pool"),
            ("ObjectStorage", "LifeCyclePolicy", "lifecycle"),
            ("CloudInsight", "EventRule", "alarm"),
        ]
        raw_resources = [
            {
                "productName": product,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "resourceName": resource_id,
                "platformType": "VPC",
            }
            for product, resource_type, resource_id in items + excluded
        ]

        resources = InfrastructureNormalizer().normalize_resource_manager(
            raw_resources
        )

        self.assertEqual(
            {resource["resource_id"] for resource in resources},
            {resource_id for _, _, resource_id in items},
        )
        self.assertEqual(
            {resource["category"] for resource in resources},
            {
                "SERVER",
                "BLOCK_STORAGE",
                "LOAD_BALANCER",
                "NAS",
                "CLOUD_DB",
                "KUBERNETES",
                "CDN",
                "OBJECT_STORAGE",
            },
        )

    def test_resource_manager_covers_extended_representative_resources(self):
        specs = {
            "vpc": ("VPC", "VPC", "VPC"),
            "subnet": ("VPC", "Subnet", "SUBNET"),
            "nat": ("VPC", "NATGateway", "NAT_GATEWAY"),
            "public-ip": ("VPCServer", "PublicIP", "PUBLIC_IP"),
            "peering": ("VPC", "VPCPeering", "VPC_PEERING"),
            "vgw": (
                "VPC",
                "VirtualPrivateGateway",
                "VIRTUAL_PRIVATE_GATEWAY",
            ),
            "asg": ("VPCAutoScaling", "AutoScalingGroup", "AUTO_SCALING"),
            "edge": ("GlobalEdge", "Edge", "GLOBAL_EDGE"),
            "dns": ("GlobalDNS", "Domain", "GLOBAL_DNS"),
            "gtm": (
                "GlobalTrafficManager",
                "Profile",
                "GLOBAL_TRAFFIC_MANAGER",
            ),
            "api": ("APIGateway", "API", "API_GATEWAY"),
            "certificate": (
                "CertificateManager",
                "Certificate",
                "CERTIFICATE",
            ),
            "snapshot": (
                "VPCServer",
                "Snapshot",
                "BLOCK_STORAGE_SNAPSHOT",
            ),
            "image": ("VPCServer", "ServerImage", "SERVER_IMAGE"),
            "archive": ("ArchiveStorage", "Container", "ARCHIVE_STORAGE"),
            "search": ("VPCSearchEngine", "Cluster", "SEARCH_ENGINE"),
            "streaming": (
                "CloudDataStreamingService",
                "Cluster",
                "DATA_STREAMING",
            ),
            "hadoop": ("VPCCloudHadoop", "Cluster", "CLOUD_HADOOP"),
            "data-stream": ("VPCDataStream", "Topic", "DATA_STREAM"),
            "functions": (
                "VPCCloudFunctions",
                "Namespace",
                "CLOUD_FUNCTIONS",
            ),
            "registry": (
                "ContainerRegistry",
                "Registry",
                "CONTAINER_REGISTRY",
            ),
            "waf": (
                "VPCSecurityMonitoring",
                "WAF",
                "SECURITY_SERVICE",
            ),
            "vpn": ("VPCIPsecVPN", "IPsecVPNGateway", "IPSEC_VPN"),
            "connect": ("VPCCloudConnect", "CloudConnect", "CLOUD_CONNECT"),
        }
        excluded_specs = (
            ("GlobalDNS", "Record", "dns-record"),
            ("GlobalEdge", "Profile", "edge-profile"),
            ("APIGateway", "Stage", "api-stage"),
            ("VPCAutoScaling", "LaunchConfiguration", "launch-config"),
            ("VPCSearchEngine", "Server", "search-child"),
            ("CloudDataStreamingService", "Server", "streaming-child"),
            ("VPCCloudHadoop", "Server", "hadoop-child"),
            ("VPCDataStream", "Connector", "connector"),
            ("VPCCloudFunctions", "Action", "function-action"),
            ("ContainerRegistry", "Image", "container-image"),
            ("VPCBackup", "Job", "backup-job"),
            ("VPCBackup", "Policy", "backup-policy"),
            ("VPCSecurityMonitoring", "Event", "security-event"),
        )
        raw_resources = [
            {
                "productName": product,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "resourceName": resource_id,
                "platformType": "VPC",
            }
            for resource_id, (product, resource_type, _) in specs.items()
        ]
        raw_resources.extend(
            {
                "productName": product,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "resourceName": resource_id,
                "platformType": "VPC",
            }
            for product, resource_type, resource_id in excluded_specs
        )

        resources = InfrastructureNormalizer().normalize_resource_manager(
            raw_resources
        )
        by_id = {resource["resource_id"]: resource for resource in resources}

        self.assertEqual(
            {
                resource_id: resource["category"]
                for resource_id, resource in by_id.items()
            },
            {
                resource_id: category
                for resource_id, (_, _, category) in specs.items()
            },
        )
        for resource in resources:
            self.assertEqual(
                resource["details"]["inventory_source"],
                "RESOURCE_MANAGER",
            )
            self.assertTrue(resource["details"]["source_product"])
            self.assertTrue(resource["details"]["source_resource_type"])
        for _, _, resource_id in excluded_specs:
            self.assertNotIn(resource_id, by_id)

    def test_normalizers_keep_only_api_explicit_topology_evidence(self):
        normalizer = InfrastructureNormalizer()
        server = normalizer.normalize_servers(
            [
                {
                    "server_id": "server-1",
                    "server_name": "app-1",
                    "private_ip": "10.0.1.4",
                    "public_ip": "203.0.113.4",
                    "vpc_id": "vpc-1",
                    "subnet_id": "subnet-1",
                }
            ],
            [
                {
                    "networkInterfaceNo": "nic-1",
                    "serverInstanceNo": "server-1",
                    "subnetNo": "subnet-1",
                    "ip": "10.0.1.4",
                    "secondaryIpList": ["10.0.1.5"],
                }
            ],
        )[0]
        self.assertEqual(
            server["details"]["all_private_ips"],
            ["10.0.1.4", "10.0.1.5"],
        )
        self.assertEqual(server["details"]["network_interface_nos"], ["nic-1"])
        self.assertEqual(
            {
                (relation["target_category"], relation["target_id"])
                for relation in server["details"]["explicit_relations"]
            },
            {
                ("VPC", "vpc-1"),
                ("SUBNET", "subnet-1"),
                ("NETWORK_INTERFACE", "nic-1"),
            },
        )

        load_balancer = normalizer.normalize_load_balancers(
            [
                {
                    "loadBalancerInstanceNo": "lb-1",
                    "loadBalancerName": "public-alb",
                    "vpcNo": "vpc-1",
                    "subnetNoList": ["subnet-1", "subnet-2"],
                }
            ],
            [
                {
                    "targetGroupNo": "tg-1",
                    "loadBalancerInstanceNo": "lb-1",
                    "targetType": {"code": "VSVR"},
                    "targetNoList": ["server-2"],
                }
            ],
            {"tg-1": [{"targetNo": "server-1", "targetIp": "10.0.1.4"}]},
        )[0]
        self.assertEqual(load_balancer["details"]["target_group_nos"], ["tg-1"])
        self.assertEqual(
            load_balancer["details"]["target_server_instance_nos"],
            ["server-2", "server-1"],
        )
        self.assertEqual(
            {
                relation["source_field"]
                for relation in load_balancer["details"]["explicit_relations"]
                if relation["target_category"] == "SERVER"
            },
            {
                "targetGroupList[].targetNoList[]",
                "targetList[].targetNo",
            },
        )

        subnet = normalizer.normalize_subnets(
            [
                {
                    "subnetNo": "subnet-1",
                    "subnetName": "app-subnet",
                    "vpcNo": "vpc-1",
                    "subnet": "10.0.1.0/24",
                }
            ],
            {
                "subnet-1": {
                    "route_table_nos": ["rt-1"],
                    "routes": [
                        {
                            "targetType": {"code": "NATGW"},
                            "targetNo": "nat-1",
                        },
                        {"targetType": {"code": "IGW"}},
                        {
                            "targetType": {"code": "NATGW"},
                            "targetNo": "https://not-an-id.invalid",
                        },
                    ],
                }
            },
        )[0]
        self.assertEqual(
            {
                (relation["target_category"], relation["target_id"])
                for relation in subnet["details"]["explicit_relations"]
            },
            {("VPC", "vpc-1"), ("NAT_GATEWAY", "nat-1")},
        )
        self.assertEqual(
            subnet["details"]["reference_only_route_target_types"],
            ["IGW"],
        )
        self.assertNotIn("not-an-id.invalid", json.dumps(subnet))

        database = normalizer.normalize_cdb(
            "MYSQL",
            [
                {
                    "cloudMysqlInstanceNo": "db-1",
                    "cloudMysqlServiceName": "orders-db",
                    "cloudMysqlServerInstanceList": [
                        {
                            "cloudMysqlServerInstanceNo": "db-server-1",
                            "cloudMysqlServerName": "orders-db-001",
                            "cloudMysqlServerRole": {"code": "M"},
                            "privateIp": "10.0.2.10",
                            "vpcNo": "vpc-1",
                            "subnetNo": "subnet-2",
                        }
                    ],
                }
            ],
        )[0]
        self.assertEqual(database["details"]["server_names"], ["orders-db-001"])
        self.assertEqual(database["details"]["private_ips"], ["10.0.2.10"])

        registry = normalizer.normalize_container_registries(
            [
                {
                    "name": "production-images",
                    "private_id": "private-access-1",
                    "end_point": "registry.example.invalid",
                    "private_end_point": "private.registry.example.invalid",
                    "end_point_enabled": True,
                    "status": "running",
                }
            ]
        )[0]
        self.assertEqual(registry["resource_id"], "production-images")
        self.assertIsNone(registry["platform"])
        self.assertEqual(
            registry["details"]["private_access_id"],
            "private-access-1",
        )
        self.assertTrue(registry["details"]["client_access_enabled"])
        self.assertNotIn("registry.example.invalid", json.dumps(registry))

    def test_selected_category_calls_only_relevant_direct_service(self):
        vpc = Mock()
        vpc.get_vpc_list.return_value = wrapped(
            "getVpcListResponse",
            "vpcList",
            [
                {
                    "vpcNo": "vpc-1",
                    "vpcName": "production",
                    "ipv4CidrBlock": "10.0.0.0/16",
                }
            ],
        )
        factory = build_factory(vpc=vpc)
        collector = InfrastructureCollector(factory)

        resources = collector.collect([], {}, categories=("VPC",))

        self.assertEqual(
            [(resource["category"], resource["resource_id"]) for resource in resources],
            [("VPC", "vpc-1")],
        )
        self.assertEqual(factory.requests, ["vpc", "resource_manager"])
        vpc.get_vpc_list.assert_called_once_with()

        resource_manager_factory = build_factory()
        self.assertEqual(
            InfrastructureCollector(resource_manager_factory).collect(
                [],
                {},
                categories=("OBJECT_STORAGE",),
            ),
            [],
        )
        self.assertEqual(
            resource_manager_factory.requests,
            ["resource_manager"],
        )

        empty_factory = build_factory()
        self.assertEqual(
            InfrastructureCollector(empty_factory).collect(
                [],
                {},
                categories=(),
            ),
            [],
        )
        self.assertEqual(empty_factory.requests, [])

    def test_resource_manager_enriches_but_does_not_replace_server_inventory(
        self,
    ):
        resource_manager = Mock()
        resource_manager.get_resource_list.return_value = {
            "items": [
                {
                    "nrn": "nrn:PUB:Server:KR:123:Server/server-1",
                    "platformType": "VPC",
                    "productName": "VPCServer",
                    "resourceType": "ServerInstance",
                    "resourceId": "server-1",
                    "resourceName": "app-server",
                    "createTime": 1_767_225_600_000,
                },
                {
                    "nrn": "nrn:PUB:Server:KR:123:Server/rm-only",
                    "platformType": "VPC",
                    "productName": "VPCServer",
                    "resourceType": "ServerInstance",
                    "resourceId": "rm-only",
                    "resourceName": "must-not-replace-service-inventory",
                    "createTime": 1_767_225_600_000,
                },
            ],
            "hasMore": False,
        }
        factory = build_factory(resource_manager=resource_manager)
        collector = InfrastructureCollector(factory)

        resources = collector.collect(
            [
                {
                    "server_id": "server-1",
                    "server_name": "app-server",
                    "create_time": "service-api-time",
                }
            ],
            {"nics": [], "storages": []},
            categories=("SERVER",),
        )

        self.assertEqual(
            [resource["resource_id"] for resource in resources],
            ["server-1"],
        )
        self.assertEqual(resources[0]["create_time"], 1_767_225_600_000)
        self.assertEqual(
            resources[0]["details"]["create_time_source"],
            "RESOURCE_MANAGER",
        )
        self.assertEqual(factory.requests, ["resource_manager"])
        resource_manager.get_resource_list.assert_called_once()

    def test_resource_manager_permission_failure_keeps_service_creation_time(
        self,
    ):
        response = requests.Response()
        response.status_code = 403
        response._content = b'{"error":{"errorCode":"2300"}}'
        response.headers["Content-Type"] = "application/json"
        resource_manager = Mock()
        resource_manager.get_resource_list.side_effect = requests.HTTPError(
            "forbidden",
            response=response,
        )
        collector = InfrastructureCollector(
            build_factory(resource_manager=resource_manager)
        )

        resources = collector.collect(
            [
                {
                    "server_id": "server-1",
                    "server_name": "app-server",
                    "create_time": "service-api-time",
                }
            ],
            {"nics": [], "storages": []},
            categories=("SERVER",),
        )

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["create_time"], "service-api-time")
        self.assertEqual(collector.last_errors, [])
        self.assertEqual(len(collector.last_warnings), 1)
        self.assertEqual(collector.last_warnings[0]["status_code"], 403)
        self.assertEqual(collector.last_warnings[0]["error_code"], "2300")

    def test_collects_allowlisted_inventory_and_never_persists_secrets(self):
        factory = build_factory(
            loadbalancer=InventoryLoadBalancerAPI(),
            vnas=InventoryNasAPI(),
            cloud_db=InventoryCloudDbAPI(),
            kubernetes=InventoryKubernetesAPI(),
            cdn=InventoryCdnAPI(),
            resource_manager=InventoryResourceManagerAPI(),
        )
        collector = InfrastructureCollector(factory)
        servers = [
            {
                "server_id": "server-1",
                "server_name": "app-server",
                "status": "running",
                "region_code": "KR",
                "zone_code": "KR-1",
                "cpu_count": 4,
                "memory_gb": 16,
                "login_key": "never-store-this",
                "raw_server": {
                    "createDate": "2026-01-01T00:00:00+0900",
                    "endpoint": "https://private.example.invalid",
                },
            }
        ]
        raw_data = {
            "nics": [],
            "storages": [
                {
                    "blockStorageInstanceNo": "storage-1",
                    "blockStorageName": "data-volume",
                    "blockStorageSize": 100 * 1024 ** 3,
                    "serverInstanceNo": "server-1",
                    "regionCode": "KR",
                    "zoneCode": "KR-1",
                }
            ]
        }

        resources = collector.collect(
            servers,
            raw_data,
            categories=(
                "SERVER",
                "BLOCK_STORAGE",
                "LOAD_BALANCER",
                "NAS",
                "CLOUD_DB",
                "KUBERNETES",
                "CDN",
                "OBJECT_STORAGE",
            ),
        )

        self.assertEqual(
            [resource["category"] for resource in resources],
            [
                "SERVER",
                "BLOCK_STORAGE",
                "LOAD_BALANCER",
                "NAS",
                "CLOUD_DB",
                "KUBERNETES",
                "CDN",
                "OBJECT_STORAGE",
            ],
        )
        self.assertEqual(
            len(
                [
                    resource
                    for resource in resources
                    if resource["category"] == "SERVER"
                ]
            ),
            1,
        )
        cloud_db = next(
            resource
            for resource in resources
            if resource["category"] == "CLOUD_DB"
        )
        self.assertEqual(
            cloud_db["details"]["server_instance_nos"],
            ["db-server-1"],
        )
        for resource in resources:
            self.assertEqual(
                set(resource),
                set(InfrastructureNormalizer.COMMON_FIELDS),
            )

        rendered = json.dumps(resources, ensure_ascii=False).lower()
        for sensitive_value in (
            "never-store-this",
            "private.example.invalid",
            "private-origin.example.invalid",
            "hidden.example.invalid",
        ):
            self.assertNotIn(sensitive_value, rendered)
        for excluded_id in ("alarm-1", "user-1"):
            self.assertNotIn(excluded_id, rendered)
        self.assertEqual(collector.last_errors, [])
        self.assertEqual(collector.last_warnings, [])
        self.assertNotIn("vserver", factory.requests)

    def test_permission_failure_is_warning_and_other_services_continue(self):
        response = requests.Response()
        response.status_code = 403
        response._content = b'{"error":{"errorCode":"2300"}}'
        response.headers["Content-Type"] = "application/json"
        failing_load_balancer = Mock()
        failing_load_balancer.get_load_balancer_instance_list.side_effect = (
            requests.HTTPError("forbidden", response=response)
        )
        factory = build_factory(
            loadbalancer=failing_load_balancer,
            resource_manager=InventoryResourceManagerAPI(),
        )
        collector = InfrastructureCollector(factory)

        resources = collector.collect([], {"storages": []})

        self.assertTrue(
            any(
                resource["category"] == "OBJECT_STORAGE"
                for resource in resources
            )
        )
        self.assertEqual(collector.last_errors, [])
        self.assertEqual(collector.last_warnings[0]["status_code"], 403)
        self.assertEqual(collector.last_warnings[0]["error_code"], "2300")
        self.assertNotIn("forbidden", str(collector.last_warnings))

    def test_fetches_block_storage_only_when_server_data_cannot_be_reused(self):
        vserver = Mock()
        vserver.get_block_storage_instance_list.return_value = wrapped(
            "getBlockStorageInstanceListResponse",
            "blockStorageInstanceList",
            [],
        )
        factory = build_factory(vserver=vserver)
        collector = InfrastructureCollector(factory)

        collector.collect([], None)

        vserver.get_block_storage_instance_list.assert_called_once_with(
            page_no=1,
            page_size=collector.PAGE_SIZE,
        )

    def test_cloud_db_and_cdn_use_documented_zero_based_first_page(self):
        cloud_db = Mock()
        cloud_db_responses = (
            (
                "get_cloud_mysql_instance_list",
                "getCloudMysqlInstanceListResponse",
                "cloudMysqlInstanceList",
            ),
            (
                "get_cloud_postgresql_instance_list",
                "getCloudPostgresqlInstanceListResponse",
                "cloudPostgresqlInstanceList",
            ),
            (
                "get_cloud_mssql_instance_list",
                "getCloudMssqlInstanceListResponse",
                "cloudMssqlInstanceList",
            ),
            (
                "get_cloud_mongodb_instance_list",
                "getCloudMongoDbInstanceListResponse",
                "cloudMongoDbInstanceList",
            ),
            (
                "get_cloud_cache_instance_list",
                "getCloudCacheInstanceListResponse",
                "cloudCacheInstanceList",
            ),
        )
        for method_name, response_key, list_key in cloud_db_responses:
            getattr(cloud_db, method_name).return_value = wrapped(
                response_key,
                list_key,
                [],
            )

        cdn = Mock()
        cdn.get_global_cdn_instance_list.return_value = wrapped(
            "getGlobalCdnInstanceListResponse",
            "globalCdnInstanceList",
            [],
        )
        cdn.get_cdn_plus_instance_list.return_value = wrapped(
            "getCdnPlusInstanceListResponse",
            "cdnPlusInstanceList",
            [],
        )
        factory = build_factory(cloud_db=cloud_db, cdn=cdn)
        factory.credentials = Mock(region="SGN")
        collector = InfrastructureCollector(factory)

        collector.collect([], {"storages": []})

        for method_name, _, _ in cloud_db_responses:
            getattr(cloud_db, method_name).assert_called_once_with(
                page_no=0,
                page_size=collector.PAGE_SIZE,
                region_code="SGN",
            )
        cdn.get_global_cdn_instance_list.assert_called_once_with(
            page_no=0,
            page_size=collector.PAGE_SIZE,
        )
        cdn.get_cdn_plus_instance_list.assert_called_once_with(
            page_no=0,
            page_size=collector.PAGE_SIZE,
        )

    def test_resource_manager_uses_configured_region(self):
        resource_manager = Mock()
        resource_manager.get_resource_list.return_value = {
            "items": [],
            "hasMore": False,
        }
        factory = build_factory(resource_manager=resource_manager)
        factory.credentials = Mock(region="JPN")
        collector = InfrastructureCollector(factory)

        collector.collect([], {"storages": []})

        resource_manager.get_resource_list.assert_called_once_with(
            page=0,
            size=collector.PAGE_SIZE,
            region_code="JPN",
        )


if __name__ == "__main__":
    unittest.main()

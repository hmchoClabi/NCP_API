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
        "cloud_db": EmptyCloudDbAPI(),
        "kubernetes": EmptyKubernetesAPI(),
        "cdn": EmptyCdnAPI(),
        "resource_manager": EmptyResourceManagerAPI(),
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

        resources = collector.collect(servers, raw_data)

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

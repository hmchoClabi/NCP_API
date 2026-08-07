import unittest
from types import SimpleNamespace

from app.apifactory import APIFactory
from ncp_api.claAPI import CloudLogAnalyticsAPI
from ncp_api.cloudactivitytracerAPI import CloudActivityTracerAPI
from ncp_api.cloudinsightAPI import CloudInsightAPI
from ncp_api.globaldnsAPI import GlobaldnsAPI
from ncp_api.loadbalancerAPI import LoadbalancerAPI
from ncp_api.platformAPI import PlatformAPI
from ncp_api.resourcemgrAPI import ResourceManagerAPI
from ncp_api.subaccountAPI import SubAccountAPI
from ncp_api.vnasAPI import VnasAPI
from ncp_api.vpcAPI import VpcAPI
from ncp_api.vserverAPI import VserverAPI
from ncp_api.webservicemonitorAPI import WebServiceMonitorAPI
from utils.credentials import NCPCredentials


class RecordingClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, **kwargs):
        self.calls.append(("GET", endpoint, kwargs))
        return {}

    def post(self, endpoint, **kwargs):
        self.calls.append(("POST", endpoint, kwargs))
        return {}


class NCPAPIContractTests(unittest.TestCase):
    def test_wms_optional_filters_are_omitted_and_detail_type_is_sent(self):
        client = RecordingClient()
        api = WebServiceMonitorAPI(client=client)

        api.get_wms_monitor_result("scenario", 1, 2, "RAW")
        self.assertEqual(
            client.calls[-1][2]["params"],
            {"from": 1, "to": 2, "type": "RAW"},
        )

        api.get_wms_monitor_result_detail("scenario", "result", "MIN5")
        self.assertEqual(client.calls[-1][2]["params"], {"type": "MIN5"})

    def test_read_only_post_wrappers_opt_in_to_safe_retries(self):
        client = RecordingClient()

        insight = CloudInsightAPI(client=client)
        insight.get_search_event(start_time=1, end_time=2)
        self.assertTrue(client.calls[-1][2]["retry_safe"])

        activity = CloudActivityTracerAPI(client=client)
        activity.get_activity_list(fromEventTime=1, toEventTime=2)
        self.assertTrue(client.calls[-1][2]["retry_safe"])

    def test_cloud_insight_required_query_times_and_string_event_id(self):
        client = RecordingClient()
        api = CloudInsightAPI(client=client)

        with self.assertRaises(ValueError):
            api.get_query_data(
                cw_key="product-key",
                metric="cpu",
                dimensions={"instanceNo": "server-1"},
            )

        api.get_query_data(
            cw_key="product-key",
            metric="cpu",
            dimensions={"instanceNo": "server-1"},
            time_start=0,
            time_end=1,
        )
        body = client.calls[-1][2]["json_data"]
        self.assertEqual(body["timeStart"], 0)
        self.assertEqual(body["timeEnd"], 1)

        api.get_search_event_by_id(
            start_time=1,
            end_time=2,
            rule_id=3,
            event_id="event-1",
        )
        self.assertEqual(
            client.calls[-1][2]["json_data"]["eventId"],
            "event-1",
        )

    def test_cloud_insight_sets_configured_region_header(self):
        client = RecordingClient()
        client.session = SimpleNamespace(headers={})

        CloudInsightAPI(
            credentials=NCPCredentials(
                access_key="test-access",
                secret_key="test-secret",
                api_type="public",
                region="SGN",
            ),
            client=client,
        )

        self.assertEqual(
            client.session.headers["x-ncp-region_code"],
            "SGN",
        )

    def test_cla_accepts_documented_mysql_alias_and_sends_aggregation_type(self):
        client = RecordingClient()
        api = CloudLogAnalyticsAPI(client=client)

        api.get_cla_server_list("kr", svr_type="cdb4my")
        self.assertEqual(client.calls[-1][1], "/api/kr-v1/vpc/servers/mysql")

        api.get_cla_log_count_aggregation("kr", type="server")
        self.assertEqual(client.calls[-1][2]["params"], {"type": "server"})

        with self.assertRaises(TypeError):
            api.get_cla_log_count_aggregation("kr")

    def test_resource_manager_uses_documented_pagination_keys(self):
        client = RecordingClient()
        api = ResourceManagerAPI(client=client)

        api.get_group_list(page_index=0, page_size=1)
        self.assertEqual(
            client.calls[-1][2]["params"],
            {"page": 0, "size": 1},
        )

        api.get_group_list(page=2, size=50)
        self.assertEqual(
            client.calls[-1][2]["params"],
            {"page": 2, "size": 50},
        )

        tags = [{"tagKey": "environment", "tagValue": "production"}]
        api.get_resource_list(page=0, size=1, tag=tags)
        self.assertEqual(
            client.calls[-1][2]["json_data"],
            {"page": 0, "size": 1, "tag": tags},
        )

    def test_load_balancer_list_contracts(self):
        client = RecordingClient()
        api = LoadbalancerAPI(client=client)
        api.get_load_balancer_instance_list(
            sortlist_sorted_by=["loadBalancerName"],
        )
        self.assertEqual(
            client.calls[-1][2]["params"]["sortList.1.sortedBy"],
            "loadBalancerName",
        )
        with self.assertRaises(ValueError):
            api.get_load_balancer_instance_list(page_no=1)
        with self.assertRaises(ValueError):
            api.get_target_group_list(page_no=1)

        api.get_target_group_list(page_size=100)
        self.assertEqual(
            client.calls[-1][2]["params"]["pageSize"],
            100,
        )

        api.get_load_balancer_instance_list(
            load_balancer_code="APPLICATION",
        )
        params = client.calls[-1][2]["params"]
        self.assertEqual(
            params["loadBalancerTypeCode"],
            "APPLICATION",
        )
        self.assertNotIn("loadBalancerCode", params)

        api.get_load_balancer_instance_list(
            load_balancer_type_code="NETWORK",
        )
        self.assertEqual(
            client.calls[-1][2]["params"]["loadBalancerTypeCode"],
            "NETWORK",
        )

    def test_subaccount_role_tag_uses_roles_path(self):
        client = RecordingClient()
        api = SubAccountAPI(client=client)

        api.get_role_tag("role-1")
        self.assertEqual(client.calls[-1][1], "/api/v1/roles/role-1/tags")

    def test_global_dns_uses_documented_query_keys(self):
        client = RecordingClient()
        api = GlobaldnsAPI(client=client)

        api.get_dns_domain_query(base_time_unit="MINUTE_5")
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["baseTimeUnit"], "MINUTE_5")
        self.assertNotIn("baseTimeUnix", params)

        api.get_dns_domain_query("HOUR_3")
        self.assertEqual(
            client.calls[-1][2]["params"]["baseTimeUnit"],
            "HOUR_3",
        )

        api.get_record(page=0, size=20, domain_id="domain-1")
        params = client.calls[-1][2]["params"]
        self.assertNotIn("domainId", params)
        self.assertEqual(
            client.calls[-1][1],
            "/ncpdns/record/domain-1",
        )

    def test_vserver_corrected_aliases_keep_existing_api(self):
        client = RecordingClient()
        api = VserverAPI(client=client)

        api.get_server_instance_list(server_instance_no_list=["1", "2"])
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["serverInstanceNoList.1"], "1")
        self.assertEqual(params["serverInstanceNoList.2"], "2")

        api.get_server_instance_list(
            page_no=1,
            page_size=100,
            sorted_by="serverName",
            sort_order="ASC",
        )
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["sortedBy"], "serverName")
        self.assertEqual(params["sortingOrder"], "ASC")
        self.assertNotIn("sortBy", params)
        self.assertNotIn("sortOrder", params)
        with self.assertRaises(ValueError):
            api.get_server_instance_list(page_no=1)

        api.get_member_server_instance_list(
            page_no=1,
            page_size=100,
            sorted_by="memberServerImageName",
        )
        self.assertEqual(
            client.calls[-1][2]["params"]["sortedBy"],
            "memberServerImageName",
        )
        with self.assertRaises(ValueError):
            api.get_member_server_instance_list(page_no=1)

        api.get_fabric_cluster_list(fabric_cluster_no_list=["10", "20"])
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["fabricClusterNoList.1"], "10")
        self.assertEqual(params["fabricClusterNoList.2"], "20")

        api.get_block_storage_volume_type_list()
        self.assertEqual(
            client.calls[-1][1],
            "/vserver/v2/getBlockStorageVolumeTypeList",
        )

        api.get_member_server_image_instance_detail("image-1")
        params = client.calls[-1][2]["params"]
        self.assertEqual(
            params["memberServerImageInstanceNo"],
            "image-1",
        )

        api.get_member_server_instance_detail("image-2")
        params = client.calls[-1][2]["params"]
        self.assertEqual(
            params["memberServerImageInstanceNo"],
            "image-2",
        )
        self.assertNotIn("memberServerInstanceNo", params)

        api.get_network_interface_list(
            subnet_name="subnet-a",
            network_interface_no_list=["nic-1"],
            network_interface_status_code="USED",
            ip="10.0.0.10",
        )
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["subnetName"], "subnet-a")
        self.assertEqual(params["networkInterfaceNoList.1"], "nic-1")
        self.assertEqual(params["networkInterfaceStatusCode"], "USED")
        self.assertEqual(params["ip"], "10.0.0.10")
        self.assertNotIn("subName", params)
        self.assertNotIn("networkInterfaceInstanceStatusCode", params)
        self.assertNotIn("ipAddress", params)

        api.get_network_interface_instance_detail("nic-2")
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["networkInterfaceNo"], "nic-2")
        self.assertNotIn("networkInterfaceInstanceNo", params)

        with self.assertRaises(ValueError):
            api.get_init_script_detail()
        with self.assertRaises(ValueError):
            api.get_flow_log_configuration_list()

    def test_vpc_and_vnas_use_documented_list_keys(self):
        client = RecordingClient()
        vpc = VpcAPI(client=client)

        vpc.get_subnet_list(page=1, page_size=100)
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["pageNo"], 1)
        self.assertNotIn("page", params)
        with self.assertRaises(ValueError):
            vpc.get_subnet_list(page=1)

        vpc.get_vpc_peering_instance_list(
            page_no=1,
            page_size=100,
            sort_order="DESC",
        )
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["sortingOrder"], "DESC")
        self.assertNotIn("sortOrder", params)
        with self.assertRaises(ValueError):
            vpc.get_vpc_peering_instance_list(page_no=1)

        vpc.get_route_table_list(
            page_no=1,
            page_size=100,
            sort_order="ASC",
        )
        self.assertEqual(
            client.calls[-1][2]["params"]["sortingOrder"],
            "ASC",
        )

        vnas = VnasAPI(client=client)
        vnas.get_nas_volume_instance_list(
            page_no=1,
            page_size=100,
            sort_by="volumeName",
            sort_order="ASC",
        )
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["sortedBy"], "volumeName")
        self.assertEqual(params["sortingOrder"], "ASC")
        self.assertNotIn("sortBy", params)
        self.assertNotIn("sortOrder", params)
        with self.assertRaises(ValueError):
            vnas.get_nas_volume_instance_list(page_no=1)

    def test_platform_preserves_documented_member_parameter_shapes(self):
        client = RecordingClient()
        api = PlatformAPI(client=client)

        api.get_contract_demand_cost_list(
            "202601",
            "202601",
            is_parent=True,
            member_no_list=["100", "200"],
        )
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["isPartner"], "true")
        self.assertNotIn("isParent", params)
        self.assertEqual(params["memberNoList"], ["100", "200"])
        self.assertNotIn("memberNoList.1", params)

        api.get_coin_history_list(
            page_no=2,
            page_size=10,
            member_no_list=["100", "200"],
        )
        params = client.calls[-1][2]["params"]
        self.assertEqual(params["pageNo"], 2)
        self.assertEqual(params["pageSize"], 10)
        self.assertEqual(params["memberNoList.1"], "100")
        self.assertEqual(params["memberNoList.2"], "200")
        self.assertFalse(any(key.startswith("discountNoList.") for key in params))

        api.get_credit_history_list()
        self.assertNotIn("startMonth", client.calls[-1][2]["params"])
        self.assertNotIn("endMonth", client.calls[-1][2]["params"])

        api.get_discount_list()
        self.assertNotIn("startMonth", client.calls[-1][2]["params"])
        self.assertNotIn("endMonth", client.calls[-1][2]["params"])

    def test_security_monitoring_is_registered(self):
        self.assertIn("security_monitoring", APIFactory().available_apis())


if __name__ == "__main__":
    unittest.main()

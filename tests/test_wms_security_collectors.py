import json
import unittest

import requests

from collectors.securitymonitoringcollector import SecurityMonitoringCollector
from collectors.wmscollector import WMSCollector


class FakeFactory:
    def __init__(self, **apis):
        self.apis = apis

    def get(self, name):
        return self.apis[name]


class WMSAPI:
    def __init__(self):
        self.calls = []

    def get_wms_monitor_list(self):
        return [
            {
                "scenarioId": 10,
                "name": "homepage",
                "serviceYn": True,
                "methodType": "GET",
                "url": "https://example.com/?token=secret",
                "alarms": {"smsEmailConfigs": [{"email": "secret@example.com"}]},
            }
        ]

    def get_wms_monitor_result(
        self,
        scenario_id,
        from_time,
        to_time,
        aggregation,
    ):
        self.calls.append((scenario_id, from_time, to_time, aggregation))
        return {
            "availability": 99.5,
            "avgLoadTime": 120,
            "avgRunTime": 180,
            "successCount": 199,
            "errorCount": 1,
            "totalCount": 200,
            "results": [
                {
                    "_id": "result-1",
                    "scenarioId": 10,
                    "locationTypeCode": "KR",
                    "resultStatus": "SUCCESS",
                    "collectTime": 1_720_000_000_000,
                    "transactions": [{"request": "sensitive"}],
                }
            ],
        }


class EmptyWMSAPI(WMSAPI):
    def get_wms_monitor_list(self):
        return []


class InvalidWMSAPI(WMSAPI):
    def get_wms_monitor_list(self):
        return ["invalid-scenario"]


class PartialWMSAPI(WMSAPI):
    def get_wms_monitor_list(self):
        return [
            {"scenarioId": 10, "name": "working"},
            {"scenarioId": 20, "name": "failed"},
        ]

    def get_wms_monitor_result(
        self,
        scenario_id,
        from_time,
        to_time,
        aggregation,
    ):
        if scenario_id == "20":
            raise RuntimeError("scenario result unavailable")
        return {"availability": 100, "totalCount": 1, "results": []}


class FailedWMSAPI(PartialWMSAPI):
    def get_wms_monitor_result(
        self,
        scenario_id,
        from_time,
        to_time,
        aggregation,
    ):
        raise RuntimeError("scenario result unavailable")


class EmptyObservationWMSAPI(WMSAPI):
    def get_wms_monitor_result(
        self,
        scenario_id,
        from_time,
        to_time,
        aggregation,
    ):
        return {
            "availability": None,
            "successCount": 0,
            "errorCount": 0,
            "totalCount": 0,
            "results": [],
        }


class SecurityAPI:
    LIST_KEYS = {
        "get_anti_virus_list": "antiVirusDataList",
        "get_ddos_list": "ddosDataList",
        "get_ids_list": "idsDataList",
        "get_ips_list": "ipsDataList",
        "get_waf_list": "wafDataList",
    }

    def __init__(self):
        self.calls = []

    def _empty(self, method_name, **kwargs):
        self.calls.append((method_name, kwargs))
        return {
            "returnCode": 0,
            "totalRows": 0,
            "page": kwargs["page"],
            self.LIST_KEYS[method_name]: [],
        }

    def get_anti_virus_list(self, **kwargs):
        return self._empty("get_anti_virus_list", **kwargs)

    def get_ddos_list(self, **kwargs):
        return self._empty("get_ddos_list", **kwargs)

    def get_ids_list(self, **kwargs):
        return self._empty("get_ids_list", **kwargs)

    def get_ips_list(self, **kwargs):
        return self._empty("get_ips_list", **kwargs)

    def get_waf_list(self, **kwargs):
        return self._empty("get_waf_list", **kwargs)


class PagedSecurityAPI(SecurityAPI):
    def get_ddos_list(self, **kwargs):
        self.calls.append(("get_ddos_list", kwargs))
        page = kwargs["page"]
        if page == 1:
            rows = [
                {
                    "ticketId": str(index),
                    "date": str(1_720_000_000_000 + index),
                    "product": "DDOS_V2",
                    "attackerIp": "198.51.100.1",
                    "targetIp": "203.0.113.1",
                    "attackType": "DDoS",
                    "platForm": "VPC",
                }
                for index in range(100)
            ]
        else:
            rows = [
                {
                    "ticketId": "100",
                    "date": "1720000000100",
                    "product": "DDOS_V2",
                }
            ]
        return {
            "returnCode": 0,
            "totalRows": 101,
            "page": page,
            "ddosDataList": rows,
        }

    def get_anti_virus_list(self, **kwargs):
        self.calls.append(("get_anti_virus_list", kwargs))
        return {
            "returnCode": 0,
            "totalRows": 1,
            "page": 1,
            "antiVirusDataList": [
                {
                    "ticketId": "av-1",
                    "date": "1720000000000",
                    "product": "ANTIVIRUS_V2",
                    "attackType": "Malware",
                    "targetIp": "203.0.113.10",
                    "detectionPath": "/private/customer/path",
                }
            ],
        }


class PartiallyDeniedSecurityAPI(SecurityAPI):
    def get_waf_list(self, **kwargs):
        response = requests.Response()
        response.status_code = 403
        response.url = "https://example.com/path?accessKey=do-not-store"
        response._content = json.dumps(
            {
                "error": {
                    "errorCode": "X00004",
                    "message": "Additional rights [View/getWAFList] required",
                }
            }
        ).encode("utf-8")
        response.headers["Content-Type"] = "application/json"
        raise requests.HTTPError("403 for URL " + response.url, response=response)


class RepeatingSecurityAPI(SecurityAPI):
    def get_ids_list(self, **kwargs):
        row = {"ticketId": "repeat", "date": "1720000000000"}
        return {
            "returnCode": 0,
            "totalRows": 200,
            "page": kwargs["page"],
            "idsDataList": [row] * 100,
        }


class OverlappingSecurityAPI(SecurityAPI):
    def get_ids_list(self, **kwargs):
        page = kwargs["page"]
        if page == 1:
            rows = [{"ticketId": str(index), "date": "1720000000000"} for index in range(100)]
        elif page == 2:
            rows = [
                {"ticketId": "99", "date": "1720000000000"},
                {"ticketId": "100", "date": "1720000000001"},
            ]
        else:
            rows = []
        return {
            "returnCode": 0,
            "totalRows": 102,
            "page": page,
            "idsDataList": rows,
        }


class WMSCollectorTests(unittest.TestCase):
    def test_converts_milliseconds_and_excludes_sensitive_configuration(self):
        api = WMSAPI()
        collector = WMSCollector(FakeFactory(web_service_monitor=api))

        result = collector.collect(1_720_000_000_123, 1_720_000_060_999)

        self.assertEqual(
            api.calls,
            [("10", 1_720_000_000, 1_720_000_060, "MIN5")],
        )
        self.assertEqual(collector.last_dataset_status, "COLLECTED")
        self.assertEqual(result[0]["availability_percent"], 99.5)
        rendered = json.dumps(result)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("transactions", rendered)
        self.assertNotIn("alarms", rendered)
        self.assertNotIn("url", rendered)

    def test_empty_scenario_list_is_collected_empty(self):
        collector = WMSCollector(FakeFactory(web_service_monitor=EmptyWMSAPI()))

        self.assertEqual(collector.collect(1_000, 2_000), [])
        self.assertEqual(collector.last_dataset_status, "COLLECTED_EMPTY")
        self.assertEqual(collector.last_errors, [])

    def test_invalid_scenario_is_not_reported_as_successful_empty(self):
        collector = WMSCollector(FakeFactory(web_service_monitor=InvalidWMSAPI()))

        self.assertEqual(collector.collect(1_000, 2_000), [])
        self.assertEqual(collector.last_dataset_status, "FAILED")

    def test_scenario_failure_is_isolated(self):
        collector = WMSCollector(FakeFactory(web_service_monitor=PartialWMSAPI()))

        result = collector.collect(1_000, 2_000)

        self.assertEqual([item["scenario_id"] for item in result], ["10"])
        self.assertEqual(collector.last_dataset_status, "PARTIAL")
        self.assertEqual(collector.last_errors[0]["target"], "20")

    def test_all_scenario_failures_are_failed(self):
        collector = WMSCollector(FakeFactory(web_service_monitor=FailedWMSAPI()))

        self.assertEqual(collector.collect(1_000, 2_000), [])
        self.assertEqual(collector.last_dataset_status, "FAILED")

    def test_scenario_without_period_observations_is_collected_empty(self):
        collector = WMSCollector(FakeFactory(web_service_monitor=EmptyObservationWMSAPI()))

        result = collector.collect(1_000, 2_000)

        self.assertEqual(len(result), 1)
        self.assertEqual(collector.last_dataset_status, "COLLECTED_EMPTY")


class SecurityMonitoringCollectorTests(unittest.TestCase):
    def test_all_successful_empty_services_are_collected_empty(self):
        collector = SecurityMonitoringCollector(FakeFactory(security_monitoring=SecurityAPI()))

        self.assertEqual(collector.collect(1_000, 2_000), [])
        self.assertEqual(collector.last_dataset_status, "COLLECTED_EMPTY")
        self.assertEqual(
            set(collector.last_service_statuses.values()),
            {"COLLECTED_EMPTY"},
        )

    def test_paginates_normalizes_and_omits_sensitive_path(self):
        api = PagedSecurityAPI()
        collector = SecurityMonitoringCollector(FakeFactory(security_monitoring=api))

        result = collector.collect(1_720_000_000_000, 1_720_086_400_000)

        self.assertEqual(len(result), 102)
        self.assertEqual(collector.last_dataset_status, "COLLECTED")
        self.assertEqual(
            [call[1]["page"] for call in api.calls if call[0] == "get_ddos_list"],
            [1, 2],
        )
        antivirus = next(item for item in result if item["event_id"] == "av-1")
        self.assertEqual(antivirus["service"], "ANTIVIRUS")
        self.assertEqual(antivirus["platform"], "VPC")
        self.assertNotIn("detection_path", antivirus)

    def test_permission_failure_is_partial_and_preserves_safe_codes(self):
        collector = SecurityMonitoringCollector(
            FakeFactory(security_monitoring=PartiallyDeniedSecurityAPI())
        )

        collector.collect(1_000, 2_000)

        self.assertEqual(collector.last_dataset_status, "PARTIAL")
        self.assertEqual(collector.last_service_statuses["WAF"], "FAILED")
        error = collector.last_errors[0]
        self.assertEqual(error["status_code"], 403)
        self.assertEqual(error["error_code"], "X00004")
        self.assertEqual(error["required_actions"], ["View/getWAFList"])
        self.assertNotIn("do-not-store", error["message"])

    def test_repeated_page_guard_stops_without_duplicate_events(self):
        collector = SecurityMonitoringCollector(
            FakeFactory(security_monitoring=RepeatingSecurityAPI())
        )

        result = collector.collect(1_000, 2_000)

        self.assertEqual(
            len([item for item in result if item["service"] == "IDS"]),
            1,
        )
        self.assertEqual(collector.last_service_statuses["IDS"], "PARTIAL")
        self.assertEqual(collector.last_dataset_status, "PARTIAL")

    def test_overlapping_pages_do_not_satisfy_total_rows(self):
        collector = SecurityMonitoringCollector(
            FakeFactory(security_monitoring=OverlappingSecurityAPI())
        )

        result = collector.collect(1_000, 2_000)

        self.assertEqual(
            len([item for item in result if item["service"] == "IDS"]),
            101,
        )
        self.assertEqual(collector.last_service_statuses["IDS"], "PARTIAL")
        self.assertEqual(collector.last_dataset_status, "PARTIAL")


if __name__ == "__main__":
    unittest.main()

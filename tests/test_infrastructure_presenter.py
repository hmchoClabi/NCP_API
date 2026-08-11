import unittest

from app.renderers.infrastructure_presenter import (
    merge_server_details,
    resource_connection_summary,
    resource_size_summary,
    server_spec_summary,
)


class InfrastructurePresenterTests(unittest.TestCase):
    def test_size_summary_uses_category_specific_billing_dimensions(self):
        cases = (
            (
                "SERVER",
                {
                    "server_product_name": "Standard",
                    "cpu_count": 4,
                    "memory_gb": 16,
                },
                ("상품: Standard", "vCPU: 4개", "메모리: 16 GB"),
            ),
            (
                "BLOCK_STORAGE",
                {
                    "volume_type": "SSD",
                    "size_gb": 500,
                    "iops": 4_000,
                    "throughput_mbps": 125,
                },
                (
                    "볼륨 유형: SSD",
                    "용량: 500 GB",
                    "IOPS: 4,000",
                    "처리량: 125 MB/s",
                ),
            ),
            (
                "CLOUD_DB",
                {
                    "engine": "POSTGRESQL",
                    "server_count": 2,
                    "cpu_count_total": 8,
                    "memory_gb_total": 32,
                    "data_storage_gb_total": 500,
                },
                (
                    "엔진: POSTGRESQL",
                    "DB 서버: 2대",
                    "총 vCPU: 8개",
                    "총 메모리: 32 GB",
                    "데이터 용량: 500 GB",
                ),
            ),
            (
                "KUBERNETES",
                {"node_count": 3, "node_max_count": 10},
                ("노드: 3대", "최대 노드: 10대"),
            ),
        )

        for category, details, expected in cases:
            with self.subTest(category=category):
                summary = resource_size_summary(category, details)
                for text in expected:
                    self.assertIn(text, summary)

        self.assertEqual(
            resource_size_summary("OBJECT_STORAGE", {}),
            "수집된 규모 정보 없음",
        )

    def test_server_details_merge_by_resource_id_and_keep_existing_values(self):
        resource = {
            "category": "SERVER",
            "resource_id": "server-1",
            "resource_name": None,
            "status": None,
            "details": {"cpu_count": 8},
        }
        server = {
            "server_id": "server-1",
            "server_name": "web-1",
            "status": "RUN",
            "cpu_count": 4,
            "memory_gb": 16,
            "vpc_id": "vpc-1",
            "subnet_id": "subnet-1",
            "private_ip": "10.0.0.10",
            "storages": [{"size_gb": 50}, {"size_gb": 100}],
            "raw_server": {
                "serverProductCode": "SVR.PRODUCT.1",
                "serverProductName": "Standard 4 vCPU, 16 GB",
                "createDate": "2026-07-01T00:00:00+09:00",
            },
        }

        merged = merge_server_details(resource, [server])

        self.assertEqual(merged["resource_name"], "web-1")
        self.assertEqual(merged["status"], "RUN")
        self.assertEqual(merged["details"]["cpu_count"], 8)
        self.assertEqual(merged["details"]["memory_gb"], 16)
        self.assertEqual(merged["details"]["storage_count"], 2)
        self.assertEqual(merged["details"]["storage_size_gb_total"], 150)
        self.assertEqual(merged["details"]["vpc_no"], "vpc-1")
        self.assertEqual(merged["details"]["subnet_no"], "subnet-1")
        self.assertEqual(
            merged["create_time"],
            "2026-07-01T00:00:00+09:00",
        )
        self.assertEqual(
            resource_connection_summary("SERVER", merged["details"]),
            (
                "Private: 10.0.0.10 · 연결 스토리지: 2개 / 150 GB · "
                "VPC: vpc-1 · Subnet: subnet-1"
            ),
        )
        self.assertEqual(
            server_spec_summary(merged["details"]),
            (
                "상품: Standard 4 vCPU, 16 GB · vCPU: 8개 · "
                "메모리: 16 GB · 연결 스토리지: 2개 / 150 GB"
            ),
        )
        self.assertEqual(
            server_spec_summary({"server_product_code": "SVR.PRODUCT.1"}),
            "SKU: SVR.PRODUCT.1",
        )

    def test_duplicate_server_names_are_not_guessed(self):
        resource = {
            "category": "SERVER",
            "resource_name": "duplicate",
            "details": {},
        }
        servers = [
            {"server_id": "one", "server_name": "duplicate", "cpu_count": 2},
            {"server_id": "two", "server_name": "duplicate", "cpu_count": 4},
        ]

        merged = merge_server_details(resource, servers)

        self.assertEqual(merged["details"], {})


if __name__ == "__main__":
    unittest.main()

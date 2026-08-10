import base64
import tempfile
import unittest
from pathlib import Path

from app.infrastructure_topology import TopologyDisplayOptions
from app.renderers.html_renderer import HtmlReportRenderer
from app.renderers.topology_icons import TopologyIconLibrary


class TopologyIconLibraryTests(unittest.TestCase):
    def test_known_category_is_embedded_as_a_png_data_uri(self):
        data_uri = TopologyIconLibrary().data_uri_for({"category": "SERVER"})

        self.assertIsNotNone(data_uri)
        prefix, encoded = str(data_uri).split(",", 1)
        self.assertEqual(prefix, "data:image/png;base64")
        self.assertTrue(base64.b64decode(encoded).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_service_descriptor_selects_specific_cloud_db_icon(self):
        library = TopologyIconLibrary()

        generic = library.data_uri_for({"category": "CLOUD_DB"})
        postgresql = library.data_uri_for(
            {
                "category": "CLOUD_DB",
                "service_name": "Cloud DB for PostgreSQL",
            }
        )

        self.assertIsNotNone(postgresql)
        self.assertNotEqual(postgresql, generic)

    def test_unknown_or_path_like_category_does_not_access_a_file(self):
        library = TopologyIconLibrary()

        self.assertIsNone(library.data_uri_for({"category": "SUBNET"}))
        self.assertIsNone(
            library.data_uri_for({"category": "../../secrets/access-key"})
        )

    def test_missing_or_invalid_png_uses_the_renderer_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            asset_root = Path(directory)
            icon_path = asset_root / "compute" / "server.png"
            icon_path.parent.mkdir(parents=True)
            icon_path.write_bytes(b"not-a-png")

            data_uri = TopologyIconLibrary(asset_root).data_uri_for(
                {"category": "SERVER"}
            )

        self.assertIsNone(data_uri)

    def test_svg_defines_each_icon_once_and_reuses_its_safe_symbol_id(self):
        nodes = [
            {
                "node_id": "VPC:vpc-1",
                "category": "VPC",
                "category_label": "VPC",
            },
            {
                "node_id": "SERVER:server-1",
                "category": "SERVER",
                "category_label": "서버",
            },
            {
                "node_id": "SERVER:server-2",
                "category": "SERVER",
                "category_label": "서버",
            },
        ]
        edges = [
            {
                "source_node_id": "VPC:vpc-1",
                "target_node_id": "SERVER:server-1",
                "relationship": "CONTAINS",
            },
            {
                "source_node_id": "VPC:vpc-1",
                "target_node_id": "SERVER:server-2",
                "relationship": "CONTAINS",
            },
        ]
        renderer = HtmlReportRenderer()
        server_icon = TopologyIconLibrary().icon_for({"category": "SERVER"})

        svg = renderer._topology_svg(
            nodes,
            edges,
            TopologyDisplayOptions(group_by_vpc=False),
        )

        self.assertIsNotNone(server_icon)
        self.assertEqual(svg.count(str(server_icon.data_uri)), 1)
        self.assertEqual(
            svg.count(f'href="#{server_icon.symbol_id}"'),
            2,
        )


if __name__ == "__main__":
    unittest.main()

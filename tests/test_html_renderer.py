import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.collection_diagnostics import normalize_collection_issue
from app.renderers import HtmlReportRenderer
from app.report_models import ReportResult
from app.report_options import REPORT_OPTIONS_SCHEMA_VERSION


class HtmlReportRendererTests(unittest.TestCase):
    def _sample_report(self):
        return ReportResult(
            period={
                "period_type": "month",
                "start_dt": "2026-06-01 00:00:00",
                "end_dt": "2026-06-30 23:59:59",
                "file_suffix": "20260601_20260630",
            },
            servers=[{"server_id": "server-1"}],
            server_metrics=[
                {
                    "server_name": "web-01",
                    "metric_interval": "Hour2",
                    "cpu_min": 10,
                    "cpu_avg": 20,
                    "cpu_max": 30,
                    "mem_min": 40,
                    "mem_avg": 50,
                    "mem_max": 60,
                    "os_fs_details": [
                        {"mount": "/", "min": 20, "avg": 30, "max": 40}
                    ],
                    "data_fs_details": [
                        {
                            "mount": "/data",
                            "min": 50,
                            "avg": 60,
                            "max": 70,
                        }
                    ],
                    "raw_metrics": {
                        "must": "not leak",
                        "used_rto": {
                            "avg": [
                                {
                                    "dimensions": {"instanceNo": "one"},
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 10],
                                            [1781492400000, 20],
                                        ]
                                    },
                                }
                            ]
                        },
                        "mem_usert": {
                            "avg": [
                                {
                                    "dimensions": {"instanceNo": "one"},
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 40],
                                            [1781492400000, 50],
                                        ]
                                    },
                                }
                            ]
                        },
                        "fs_usert": {
                            "avg": [
                                {
                                    "dimensions": {
                                        "instanceNo": "one",
                                        "mnt_nm": "/",
                                    },
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 30],
                                            [1781492400000, 35],
                                        ]
                                    },
                                },
                                {
                                    "dimensions": {
                                        "instanceNo": "one",
                                        "mnt_nm": "/data",
                                    },
                                    "raw": {
                                        "dps": [
                                            [1781485200000, 60],
                                            [1781492400000, 65],
                                        ]
                                    },
                                },
                            ]
                        },
                    },
                }
            ],
            insight_events=[
                {
                    "event_time": "2026-06-15 12:00:00",
                    "severity": "WARNING",
                    "resource_name": "<server>",
                    "event_type": "CPU",
                    "message": "<script>alert(1)</script>",
                }
            ],
            activity_events={
                "server-1": [
                    {
                        "event_id": "activity-1",
                        "event_time": 1781508312345,
                        "event_time_kst": (
                            "2026-06-15 13:45:12.345 KST"
                        ),
                        "user_name": "customer-admin",
                        "user_type": "Main",
                        "product_display_name": "Server",
                        "resource_type": "Server",
                        "resource_id": "server-123",
                        "resource_name": "web-01",
                        "action_name": "Reboot",
                        "result": "SUCCESS",
                        "source_ip": "127.0.0.1",
                        "product_data": {
                            "userAgent": "Mozilla/5.0",
                            "description": "<target details>",
                            "accessToken": "must-not-be-rendered",
                        },
                    }
                ]
            },
            billing={
                "summary": {"confirmed_total_amount": 12345},
                "service_summary": [
                    {
                        "service_name": "Server",
                        "amount": 12345,
                        "row_count": 1,
                    }
                ],
                "network_usage_summary": [],
                "usage_summary": [],
            },
            collection_errors=[],
        )

    def test_render_produces_standalone_responsive_printable_html(self):
        html = HtmlReportRenderer().render(self._sample_report())

        self.assertIn("<!doctype html>", html)
        self.assertIn('name="viewport"', html)
        self.assertIn("@media print", html)
        self.assertIn("NCP 이용 보고서", html)
        self.assertIn("오늘의 요약", html)
        self.assertIn("운영 위험 판정이 포함되지 않습니다", html)
        self.assertIn(
            '<details class="report-section report-disclosure">',
            html,
        )
        self.assertIn(
            'class="section-title" role="heading" aria-level="2"',
            html,
        )
        self.assertIn(
            ".report-disclosure[open] > summary::after",
            html,
        )
        self.assertIn(".event-details:not([open]) > dl", html)
        self.assertIn("12,345 <small>원</small>", html)
        self.assertIn("Cloud Activity Tracer", html)
        self.assertIn("All Server 사용률 추이", html)
        self.assertIn("KST 2시간 AVG", html)
        self.assertIn(">06-01</text>", html)
        self.assertIn(">06-30</text>", html)
        self.assertIn("Memory Utilization Average", html)
        self.assertIn("CPU Utilization Average", html)
        self.assertIn("File System Utilization Average", html)
        self.assertEqual(html.count("<polyline"), 3)
        self.assertIn('data-chart-toggle="server-chart-1-series-1"', html)
        self.assertEqual(
            html.count('<button type="button" data-chart-download>'),
            3,
        )
        self.assertEqual(html.count("<select data-chart-export-width>"), 3)
        self.assertIn('<option value="1000">1000 × 300</option>', html)
        self.assertIn('<option value="2000" selected>2000 × 600</option>', html)
        self.assertIn('<option value="3000">3000 × 900</option>', html)
        self.assertIn("PNG 저장", html)
        self.assertIn('group.setAttribute("data-chart-export-legend", "")', html)
        self.assertIn("const items = selected.slice(0, 4)", html)
        self.assertIn(
            'series.classList.toggle("chart-series-hidden", !visible)',
            html,
        )
        self.assertIn(
            "const selectedButtons = new Set(",
            html,
        )
        self.assertIn(
            "const visible = selectedButtons.size === 0 || selected;",
            html,
        )
        self.assertIn(
            'data-chart-toggle="server-chart-1-series-1" '
            'aria-controls="server-chart-1-series-1" aria-pressed="false"',
            html,
        )
        self.assertIn("비교할 서버를 여러 대 선택", html)
        self.assertIn("선택이 없으면 전체를 표시", html)
        self.assertIn(
            "grid-template-columns: repeat(2, minmax(0, 1fr))",
            html,
        )
        self.assertIn(".chart-axis-label { fill: #64748b; font-size: 13px; }", html)
        self.assertIn("font:13px Arial,sans-serif", html)
        self.assertIn(
            ".chart-series-hidden { display: inline !important; }",
            html,
        )
        self.assertNotIn('data-chart-series tabindex=', html)
        self.assertNotIn('series.setAttribute("aria-pressed"', html)
        self.assertNotIn('document.addEventListener("keydown"', html)
        self.assertEqual(
            HtmlReportRenderer.CHART_COLORS[:3],
            ("#15803d", "#2563eb", "#c2410c"),
        )
        self.assertIn("파일시스템 평균</th>", html)
        self.assertIn("45.00%</td>", html)
        self.assertNotIn("CPU 최소</th>", html)
        cpu_chart = html.split(
            "<h3>CPU Utilization Average</h3>", 1
        )[1].split(
            "</article>",
            1,
        )[0]
        self.assertIn(">25%</text>", cpu_chart)
        self.assertIn(">100%</text>", cpu_chart)
        self.assertIn("발생 시각 (KST)", html)
        self.assertIn("2026-06-15 13:45:12.345 KST", html)
        self.assertIn("수행 계정", html)
        self.assertIn("customer-admin (Main)", html)
        self.assertIn("대상 객체", html)
        self.assertIn("Server: web-01", html)
        self.assertIn("출처 상태", html)
        self.assertIn("OBSERVED (관측)", html)
        self.assertIn("상세 2개", html)
        self.assertIn("&lt;target details&gt;", html)
        self.assertNotIn("must-not-be-rendered", html)

        script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        script_hash = base64.b64encode(
            hashlib.sha256(script.encode("utf-8")).digest()
        ).decode("ascii")
        self.assertEqual(
            HtmlReportRenderer.INTERACTION_SCRIPT_CSP_SOURCE,
            f"'sha256-{script_hash}'",
        )

    def test_collapsed_sections_expose_escaped_decision_summaries(self):
        renderer = HtmlReportRenderer()
        html = renderer.render(self._sample_report())

        self.assertIn(
            "<strong>핵심</strong> · 합계 12,345원 · "
            "최대 Server 12,345원",
            html,
        )
        self.assertIn("<strong>핵심</strong> · 경고 1건", html)
        self.assertIn("<strong>핵심</strong> · 성공 1건", html)
        self.assertIn(
            ".section-summary { color: var(--brand-dark); font-weight: 650; }",
            html,
        )
        collapsed_headers = [
            fragment.split("</summary>", 1)[0]
            for fragment in html.split(
                '<details class="report-section report-disclosure'
            )[1:]
        ]
        self.assertTrue(collapsed_headers)
        self.assertTrue(all(
            'class="section-description section-summary"' in header
            for header in collapsed_headers
        ))
        self.assertEqual(
            renderer._counted_values_summary(
                [
                    {"severity": "CRITICAL"},
                    {"severity": "FATAL"},
                    {"severity": "WARNING"},
                    {"severity": "ERROR"},
                    *([{"severity": "INFO"}] * 5),
                ],
                "severity",
                {
                    "CRITICAL": "위험",
                    "FATAL": "위험",
                    "WARNING": "경고",
                    "ERROR": "오류",
                    "INFO": "정보",
                },
                priority_labels=("위험", "오류", "경고", "정보"),
            ),
            "위험 2건 · 오류 1건 · 경고 1건 · 기타 5건",
        )
        self.assertEqual(
            renderer._numeric_rows_summary(
                [{
                    "service_name": "Network",
                    "name": "Internet Outbound",
                    "usage_gb": 2,
                }],
                "usage_gb",
                unit="GB",
                decimals=3,
                empty="없음",
            ),
            "합계 2.000GB · 최대 Internet Outbound 2.000GB",
        )
        self.assertEqual(
            renderer._server_metric_summary(
                self._sample_report().display_server_metrics
            ),
            "평균 90% 이상 0대 · 기간 평균 최고 web-01 "
            "메모리 50.00%",
        )
        many_servers = self._sample_report()
        metric = many_servers.server_metrics[0]
        many_servers.server_metrics = [
            {**metric, "server_name": f"web-{index:02d}", "raw_metrics": {}}
            for index in range(1, 22)
        ]
        utilization = renderer.render(many_servers).split(
            "서버 이용 현황", 1
        )[1].split("</summary>", 1)[0]
        self.assertIn(
            "평균 90% 이상 0대 · 기간 평균 최고 web-01 메모리 50.00%",
            utilization,
        )
        organization = renderer._organization_cost_sections([{
            "display_name": "Member",
            "member_no": "member-1",
            "cost_facts": [{
                "cost_type": "CURRENT_PROVISIONAL",
                "total_amount": 1000,
            }],
        }])
        self.assertIn(
            "현재월 예상 합계(VAT 전) 1,000원",
            organization.split("</summary>", 1)[0],
        )
        section = renderer._section(
            "제목",
            "설명",
            "본문",
            1,
            collapsed=True,
            collapsed_summary="<script>alert(1)</script>",
        )
        self.assertIn(
            "&lt;script&gt;alert(1)&lt;/script&gt;",
            section,
        )
        self.assertNotIn("<script>alert(1)</script>", section)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_chart_script_multi_selects_series_and_uses_export_size(self):
        html = HtmlReportRenderer().render(self._sample_report())
        script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]
        harness = f"""
const assert = require("assert");
const handlers = {{}};
class ClassList {{
  constructor() {{ this.values = new Set(); }}
  toggle(name, enabled) {{
    if (enabled) this.values.add(name); else this.values.delete(name);
  }}
}}
let chart;
class ChartNode {{
  constructor(kind, id = "") {{
    this.kind = kind;
    this.id = id;
    this.dataset = {{}};
    this.attributes = new Map();
    this.classList = new ClassList();
    this.disabled = false;
    this.label = "";
    this.color = "";
  }}
  getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
  setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
  querySelector(selector) {{
    if (selector === "span" && this.kind === "button") {{
      return {{textContent: this.label}};
    }}
    if (selector === ".chart-line" && this.kind === "series") {{
      return {{getAttribute: (name) => name === "stroke" ? this.color : null}};
    }}
    return null;
  }}
  closest(selector) {{
    if (selector === ".chart") return chart;
    if (selector === "[data-chart-toggle]" && this.kind === "button") return this;
    if (selector === "[data-chart-series]" && this.kind === "series") return this;
    if (selector === "[data-chart-download]" && this.kind === "download") return this;
    return null;
  }}
}}
const colors = ["#15803d", "#2563eb", "#c2410c", "#8b5cf6", "#0891b2"];
const series = [1, 2, 3, 4, 5].map((number, index) => {{
  const item = new ChartNode("series", `chart-series-${{number}}`);
  item.color = colors[index];
  return item;
}});
const buttons = series.map((item, index) => {{
  const button = new ChartNode("button");
  button.dataset.chartToggle = item.id;
  button.setAttribute("aria-pressed", "false");
  button.label = `server-${{index + 1}}`;
  return button;
}});
const exportSize = {{value: "3000"}};
const exportedSvgAttributes = new Map();
let copiedSvg;
class SvgElement {{
  constructor(name) {{
    this.name = name;
    this.attributes = new Map();
    this.children = [];
    this.textContent = "";
  }}
  setAttribute(name, value) {{
    this.attributes.set(name, String(value));
    if (this.name === "svg") exportedSvgAttributes.set(name, String(value));
  }}
  appendChild(child) {{ this.children.push(child); return child; }}
}}
const svg = {{
  viewBox: {{baseVal: {{width: 1000, height: 300}}}},
  cloneNode() {{
    copiedSvg = new SvgElement("svg");
    return copiedSvg;
  }},
}};
const canvas = {{
  width: 0,
  height: 0,
  getContext() {{
    return {{fillStyle: "", fillRect() {{}}, drawImage() {{}}}};
  }},
  toDataURL() {{ return "data:image/png;base64,test"; }},
}};
let downloaded = false;
const link = {{href: "", download: "", click() {{ downloaded = true; }}}};
const download = new ChartNode("download");
chart = {{
  id: "chart",
  getAttribute(name) {{ return name === "aria-label" ? "CPU graph" : null; }},
  querySelectorAll(selector) {{
    return selector === "[data-chart-toggle]" ? buttons : [];
  }},
  querySelector(selector) {{
    if (selector === "svg") return svg;
    if (selector === "[data-chart-export-width]") return exportSize;
    return null;
  }},
  contains(item) {{ return series.includes(item); }},
}};
global.document = {{
  getElementById(id) {{ return series.find((item) => item.id === id) || null; }},
  addEventListener(name, handler) {{ handlers[name] = handler; }},
  createElement(name) {{ return name === "canvas" ? canvas : link; }},
  createElementNS(namespace, name) {{ return new SvgElement(name); }},
}};
global.XMLSerializer = class {{ serializeToString() {{ return "<svg/>"; }} }};
global.URL = {{createObjectURL() {{ return "blob:test"; }}, revokeObjectURL() {{}}}};
global.Blob = class {{}};
global.Image = class {{ set src(value) {{ this.onload(); }} }};
eval({json.dumps(script)});
const click = (target) => handlers.click({{target}});
const hidden = () => series.map(
  (item) => item.classList.values.has("chart-series-hidden")
);
click(buttons[0]);
assert.deepStrictEqual(
  hidden(),
  [false, true, true, true, true]
);
click(buttons[1]);
assert.deepStrictEqual(
  hidden(),
  [false, false, true, true, true]
);
click(series[0]);
assert.deepStrictEqual(
  hidden(),
  [true, false, true, true, true]
);
click(series[1]);
assert.deepStrictEqual(
  hidden(),
  [false, false, false, false, false]
);
assert.deepStrictEqual(
  buttons.map((item) => item.getAttribute("aria-pressed")),
  ["false", "false", "false", "false", "false"]
);
click(download);
assert(!copiedSvg.children.some(
  (item) => item.attributes.get("data-chart-export-legend") === ""
));
downloaded = false;
click(buttons[0]);
click(buttons[1]);
click(download);
assert.strictEqual(canvas.width, 3000);
assert.strictEqual(canvas.height, 900);
assert.strictEqual(exportedSvgAttributes.get("width"), "3000");
assert.strictEqual(exportedSvgAttributes.get("height"), "900");
assert.strictEqual(downloaded, true);
const legend = copiedSvg.children.find(
  (item) => item.attributes.get("data-chart-export-legend") === ""
);
assert(legend);
const legendTexts = legend.children
  .filter((item) => item.name === "text")
  .map((item) => item.textContent);
assert.deepStrictEqual(legendTexts, ["server-1", "server-2"]);
const legendColors = legend.children
  .filter((item) => item.name === "rect")
  .map((item) => item.attributes.get("fill"));
assert(legendColors.includes("#15803d"));
assert(legendColors.includes("#2563eb"));
assert(!legendColors.includes("#c2410c"));
exportSize.value = "999999";
click(buttons[2]);
click(buttons[3]);
click(buttons[4]);
click(download);
assert.strictEqual(canvas.width, 2000);
assert.strictEqual(canvas.height, 600);
assert.strictEqual(exportedSvgAttributes.get("width"), "2000");
assert.strictEqual(exportedSvgAttributes.get("height"), "600");
const cappedLegend = copiedSvg.children.find(
  (item) => item.attributes.get("data-chart-export-legend") === ""
);
assert.deepStrictEqual(
  cappedLegend.children
    .filter((item) => item.name === "text")
    .map((item) => item.textContent),
  ["server-1", "server-2", "server-3", "server-4", "외 1개 선택"]
);
"""

        completed = subprocess.run(
            [shutil.which("node"), "-e", harness],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )

    def test_operational_report_leads_with_actions_and_folds_details(self):
        report = self._sample_report()
        report.analysis = {
            "source_state": "CALCULATED",
            "period_type": "DAILY",
            "data_quality": {
                "overall_status": "COMPLETE",
                "source_state": "CALCULATED",
                "datasets": [{
                    "label": "서버",
                    "status": "AVAILABLE",
                    "status_label": "수집 완료",
                    "record_count": 1,
                    "error_count": 0,
                    "warning_count": 0,
                    "source_state": "OBSERVED",
                }],
            },
            "findings": [{
                "rule_id": "METRIC_CPU",
                "severity": "WARNING",
                "category": "PERFORMANCE",
                "title": "CPU 확인 필요",
                "impact": "응답 지연 가능",
                "recommendation": "부하 원인을 확인하세요.",
                "resource": {"name": "web-01"},
                "evidence": [{
                    "label": "threshold",
                    "value": 90,
                    "unit": "%",
                }],
                "source_state": "CALCULATED",
            }],
            "metrics": {"summaries": []},
            "availability": {},
            "security": {},
            "costs": {},
        }

        html = HtmlReportRenderer().render(report)
        email_html = HtmlReportRenderer().render_email_summary(report)

        self.assertIn("오늘의 요약", html)
        self.assertIn("우선 확인 및 조치", html)
        self.assertIn('class="finding-card warning priority"', html)
        self.assertIn('class="technical-appendix"', html)
        self.assertIn("데이터 수집 상태", html)
        self.assertIn("오늘의 요약", email_html)
        self.assertIn("CPU 확인 필요", email_html)
        self.assertIn("첨부된 HTML 보고서", email_html)

    def test_monthly_resource_changes_render_as_information_not_warning(self):
        report = self._sample_report()
        report.analysis = {
            "source_state": "CALCULATED",
            "period_type": "MONTHLY",
            "data_quality": {
                "overall_status": "COMPLETE",
                "source_state": "CALCULATED",
                "datasets": [],
            },
            "findings": [],
            "metrics": {"summaries": []},
            "availability": {},
            "security": {},
            "costs": {},
            "resource_changes": {
                "status": "AVAILABLE",
                "source_state": "CALCULATED",
                "created_count": 1,
                "removed_count": 1,
                "spec_changed_count": 1,
                "lifecycle_compared_categories": [
                    "SERVER",
                    "NAS",
                    "OBJECT_STORAGE",
                ],
                "spec_compared_categories": ["SERVER", "NAS"],
                "lifecycle_only_categories": ["OBJECT_STORAGE"],
                "items": [
                    {
                        "change_type": "CREATED",
                        "category_label": "서버",
                        "resource_name": "<new-server>",
                        "platform": "VPC",
                        "changed_fields": [],
                    },
                    {
                        "change_type": "REMOVED",
                        "category_label": "NAS",
                        "resource_name": "old-nas",
                        "platform": "VPC",
                        "changed_fields": [],
                    },
                    {
                        "change_type": "SPEC_CHANGED",
                        "category_label": "서버",
                        "resource_name": "web-01",
                        "platform": "VPC",
                        "changed_fields": [{
                            "field": "cpu_count",
                            "label": "vCPU",
                            "before": 2,
                            "after": "<4>",
                        }],
                    },
                ],
            },
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("생성 1 · 제거 1 · 스펙 변경 1", html)
        self.assertIn("전월 대비 자원 변화", html)
        self.assertIn("스펙 변경 비교 제외: Object Storage.", html)
        self.assertIn('class="change-badge created">생성</span>', html)
        self.assertIn('class="change-badge removed">제거</span>', html)
        self.assertIn(
            'class="change-badge spec-changed">스펙 변경</span>',
            html,
        )
        self.assertIn("&lt;new-server&gt;", html)
        self.assertIn("vCPU: 2 → &lt;4&gt;", html)
        self.assertNotIn("<new-server>", html)
        self.assertNotIn('report-section warning', html.split(
            "전월 대비 자원 변화", 1
        )[0][-200:])

    def test_unavailable_resource_change_does_not_render_zero_counts(self):
        report = self._sample_report()
        report.analysis = {
            "source_state": "CALCULATED",
            "period_type": "MONTHLY",
            "data_quality": {
                "overall_status": "COMPLETE",
                "source_state": "CALCULATED",
                "datasets": [],
            },
            "findings": [],
            "metrics": {"summaries": []},
            "availability": {},
            "security": {},
            "costs": {},
            "resource_changes": {
                "status": "UNAVAILABLE",
                "source_state": "UNAVAILABLE",
                "reason_code": "BASELINE_UNAVAILABLE",
                "message": "비교할 이전 월 보고서가 없습니다.",
                "created_count": None,
                "removed_count": None,
                "spec_changed_count": None,
                "items": [],
            },
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("비교 불가", html)
        self.assertIn("비교할 이전 월 보고서가 없습니다.", html)
        self.assertNotIn("생성 0 · 제거 0 · 변경 0", html)

    def test_infrastructure_inventory_renders_only_allowed_categories(self):
        report = self._sample_report()
        report.infrastructure = [
            {
                "category": category,
                "category_label": label,
                "service_name": label,
                "resource_type": f"{category}Resource",
                "resource_id": f"resource-{index}",
                "resource_name": f"allowed-{index}",
                "status": "RUN",
                "region_code": "KR",
                "zone_code": "KR-1",
                "create_time": 0 if index == 1 else None,
                "details": {},
            }
            for index, (category, label) in enumerate(
                (
                    ("SERVER", "서버"),
                    ("LOAD_BALANCER", "Load Balancer"),
                    ("BLOCK_STORAGE", "Block Storage"),
                    ("OBJECT_STORAGE", "Object Storage"),
                    ("NAS", "NAS"),
                    ("CLOUD_DB", "Cloud DB"),
                    ("KUBERNETES", "Kubernetes"),
                ),
                start=1,
            )
        ] + [
            {
                "category": "CDN",
                "category_label": "CDN",
                "resource_name": "excluded-cdn",
            },
            {
                "category": "ALARM",
                "category_label": "Alarm",
                "resource_name": "excluded-alarm-instance",
            },
            {
                "category": "IAM",
                "category_label": "IAM",
                "resource_name": "excluded-sub-account",
            },
        ]

        html = HtmlReportRenderer().render(report)
        server_inventory = html.split(
            ">서버 현황</span>", 1
        )[1].split(
            "</details>",
            1,
        )[0]
        resource_inventory = html.split(
            ">기타 자원 현황</span>",
            1,
        )[1].split("</details>", 1)[0]

        self.assertIn("allowed-1", server_inventory)
        self.assertNotIn("allowed-1", resource_inventory)
        for index in range(2, 8):
            with self.subTest(index=index):
                self.assertIn(f"allowed-{index}", resource_inventory)
                self.assertNotIn(f"allowed-{index}", server_inventory)
        self.assertIn("1건", server_inventory)
        self.assertIn("6건", resource_inventory)
        self.assertIn("1970-01-01 09:00 KST", server_inventory)
        self.assertNotIn("excluded-cdn", html)
        self.assertNotIn("excluded-alarm-instance", html)
        self.assertNotIn("excluded-sub-account", html)
        self.assertIn("규모 / 과금 관련 지표", resource_inventory)
        self.assertIn("주소 / 연결", resource_inventory)

        details = HtmlReportRenderer()._infrastructure_details_text({
            "kubernetes_version": "1.32",
            "high_availability": True,
            "encrypted": False,
        })
        self.assertIn("Kubernetes: 1.32", details)
        self.assertIn("HA: 사용", details)
        self.assertIn("암호화: 미사용", details)

    def test_server_inventory_has_dedicated_columns_and_network_names(self):
        report = self._sample_report()
        report.report_options = {
            "sections": ["infrastructure_inventory"],
            "resource_categories": ["SERVER", "VPC", "SUBNET"],
            "monitoring_categories": [],
        }
        report.servers = [{
            "server_id": "server-1",
            "server_name": "web-01",
            "cpu_count": 4,
            "memory_gb": 16,
            "private_ip": "10.0.1.10",
            "public_ip": "203.0.113.10",
            "vpc_id": "vpc-1",
            "subnet_id": "subnet-1",
            "nics": [{
                "all_private_ips": ["10.0.1.10", "10.0.1.11"],
            }],
            "storages": [{"size_gb": 50}, {"size_gb": 100}],
            "raw_server": {
                "serverProductCode": "SVR.VSVR.STAND.C002.M008.NET.SSD.B050.G002",
                "serverProductName": "Standard 4 vCPU, 16 GB",
                "createDate": "2026-07-01T00:00:00+09:00",
            },
        }]
        report.infrastructure = [
            {
                "category": "SERVER",
                "category_label": "서버",
                "service_name": "Server",
                "resource_type": "ServerInstance",
                "resource_id": "server-1",
                "resource_name": "web-01",
                "status": "RUN",
                "region_code": "KR",
                "zone_code": "KR-1",
                "details": {},
            },
            {
                "category": "VPC",
                "category_label": "VPC",
                "resource_id": "vpc-1",
                "resource_name": "production-vpc",
                "details": {},
            },
            {
                "category": "SUBNET",
                "category_label": "Subnet",
                "resource_id": "subnet-1",
                "resource_name": "private-a",
                "details": {},
            },
        ]

        html = HtmlReportRenderer().render(report)
        server_inventory = html.split(
            ">서버 현황</span>", 1
        )[1].split(
            "</section>",
            1,
        )[0]
        resource_inventory = html.split(
            ">기타 자원 현황</span>",
            1,
        )[1].split("</section>", 1)[0]

        for heading in (
            "서버명",
            "서버 상태",
            "서버 스펙",
            "소속 VPC",
            "소속 Subnet",
            "Public IP",
            "Private IP",
            "생성 시각 (KST)",
        ):
            self.assertIn(f">{heading}</th>", server_inventory)
        self.assertIn("상품: Standard 4 vCPU, 16 GB", server_inventory)
        self.assertNotIn("SKU:", server_inventory)
        self.assertIn("vCPU: 4개", server_inventory)
        self.assertIn("메모리: 16 GB", server_inventory)
        self.assertIn("연결 스토리지: 2개 / 150 GB", server_inventory)
        self.assertIn("production-vpc (vpc-1)", server_inventory)
        self.assertIn("private-a (subnet-1)", server_inventory)
        self.assertIn("203.0.113.10", server_inventory)
        self.assertIn("10.0.1.10, 10.0.1.11", server_inventory)
        self.assertIn("2026-07-01 00:00 KST", server_inventory)
        self.assertNotIn("web-01", resource_inventory)
        self.assertIn("production-vpc", resource_inventory)
        self.assertIn("private-a", resource_inventory)

    def test_server_only_inventory_omits_empty_other_resource_section(self):
        report = self._sample_report()
        report.report_options = {
            "sections": ["infrastructure_inventory"],
            "resource_categories": ["SERVER"],
            "monitoring_categories": [],
        }
        report.infrastructure = [{
            "category": "SERVER",
            "category_label": "서버",
            "resource_id": "server-1",
            "resource_name": "server-only",
            "status": "RUN",
            "details": {},
        }]

        html = HtmlReportRenderer().render(report)

        self.assertIn(">서버 현황</span>", html)
        self.assertNotIn(">기타 자원 현황</span>", html)

    def test_server_only_inventory_uses_collected_network_names(self):
        report = self._sample_report()
        report.report_options = {
            "sections": ["infrastructure_inventory"],
            "resource_categories": ["SERVER"],
            "monitoring_categories": [],
        }
        report.servers = [{
            "server_id": "server-1",
            "server_name": "web-01",
            "vpc_id": "vpc-1",
            "subnet_id": "subnet-1",
        }]
        report.infrastructure = [
            {
                "category": "SERVER",
                "resource_id": "server-1",
                "resource_name": "web-01",
                "details": {},
            },
            {
                "category": "VPC",
                "resource_id": "vpc-1",
                "resource_name": "production-vpc",
                "details": {},
            },
            {
                "category": "SUBNET",
                "resource_id": "subnet-1",
                "resource_name": "private-a",
                "details": {},
            },
        ]

        html = HtmlReportRenderer().render(report)
        server_inventory = html.split(
            ">서버 현황</span>", 1
        )[1].split(
            "</section>",
            1,
        )[0]

        self.assertIn("production-vpc (vpc-1)", server_inventory)
        self.assertIn("private-a (subnet-1)", server_inventory)
        self.assertNotIn(">기타 자원 현황</span>", html)

    def test_non_server_only_inventory_omits_empty_server_section(self):
        report = self._sample_report()
        report.report_options = {
            "sections": ["infrastructure_inventory"],
            "resource_categories": ["BLOCK_STORAGE"],
            "monitoring_categories": [],
        }
        report.infrastructure = [{
            "category": "BLOCK_STORAGE",
            "category_label": "Block Storage",
            "resource_id": "storage-1",
            "resource_name": "data-volume",
            "status": "ATTACHED",
            "details": {"size_gb": 100},
        }]

        html = HtmlReportRenderer().render(report)

        self.assertNotIn(">서버 현황</span>", html)
        self.assertIn(">기타 자원 현황</span>", html)

    def test_network_snapshot_marks_generation_time_and_renders_rules(self):
        report = self._sample_report()
        report.report_options = {
            "sections": ["infrastructure_inventory"],
            "resource_categories": [
                "ROUTE_TABLE",
                "ACCESS_CONTROL_GROUP",
                "NETWORK_ACL",
            ],
            "monitoring_categories": [],
        }
        report.collection_metadata = {
            "network_configuration": {
                "source": "REPORT_GENERATION_SNAPSHOT",
                "time_basis": (
                    "REPORT_GENERATION_TIME_NOT_REPORT_PERIOD"
                ),
                "captured_at": "2026-08-10T09:30:00+09:00",
                "backup_captured_at": "2026-08-10T09:30:00+09:00",
                "capture_trigger": "REPORT_GENERATION",
                "is_point_in_time_snapshot": True,
                "is_report_period_snapshot": False,
                "report_period_start": "2026-06-01 00:00:00",
                "report_period_end": "2026-06-30 23:59:59",
            }
        }
        report.infrastructure = [
            {
                "category": "ROUTE_TABLE",
                "category_label": "Route Table",
                "resource_id": "rt-1",
                "resource_name": "private-routes",
                "status": "RUN",
                "details": {
                    "vpc_no": "vpc-1",
                    "associated_subnet_count": 1,
                    "associated_subnets": [{
                        "subnet_no": "subnet-1",
                        "subnet_name": "private-a",
                    }],
                    "route_count": 1,
                    "routes": [{
                        "destination_cidr": "0.0.0.0/0",
                        "target_type": "NATGW",
                        "target_name": "nat-main",
                    }],
                },
            },
            {
                "category": "ACCESS_CONTROL_GROUP",
                "category_label": "ACG",
                "resource_id": "acg-1",
                "resource_name": "web-acg",
                "status": "RUN",
                "details": {
                    "vpc_no": "vpc-1",
                    "rule_count": 1,
                    "rules": [{
                        "direction": "INBND",
                        "protocol": "TCP",
                        "source_ip_block": "10.0.0.0/8",
                        "port_range": "443",
                        "description": "HTTPS from private network",
                    }],
                },
            },
            {
                "category": "NETWORK_ACL",
                "category_label": "Network ACL",
                "resource_id": "nacl-1",
                "resource_name": "private-nacl",
                "status": "RUN",
                "details": {
                    "vpc_no": "vpc-1",
                    "rule_count": 1,
                    "rules": [{
                        "priority": 10,
                        "direction": "INBND",
                        "protocol": "TCP",
                        "source_ip_block": "10.0.0.0/8",
                        "port_range": "443",
                        "action": "ALLOW",
                    }],
                },
            },
            {
                "category": "ACCESS_CONTROL_GROUP",
                "category_label": "ACG",
                "resource_id": "acg-2",
                "resource_name": "empty-acg",
                "status": "RUN",
                "details": {
                    "vpc_no": "vpc-1",
                    "rule_snapshot_available": True,
                    "rule_count": 0,
                    "rules": [],
                },
            },
            {
                "category": "NETWORK_ACL",
                "category_label": "Network ACL",
                "resource_id": "nacl-2",
                "resource_name": "empty-nacl",
                "status": "RUN",
                "details": {
                    "vpc_no": "vpc-1",
                    "rule_snapshot_available": True,
                    "rule_count": 0,
                    "rules": [],
                },
            },
        ]

        html = HtmlReportRenderer().render(report)
        section = html.split(
            ">네트워크 구성 스냅샷</span>",
            1,
        )[1].split("</section>", 1)[0]

        self.assertIn("단일 시점 구성 백업", section)
        self.assertIn("실제 수집 시각", section)
        self.assertIn("2026-08-10 09:30 KST", section)
        self.assertIn("보고 기간 외 · 생성시점 현재 상태", section)
        self.assertIn("수집 계기", section)
        self.assertIn("보고서 생성 과정", section)
        self.assertIn(
            "보고 대상 기간의 과거 상태가 아닙니다.",
            section,
        )
        self.assertIn("Route 규칙", section)
        self.assertIn("private-routes", section)
        self.assertIn("private-a", section)
        self.assertIn("0.0.0.0/0", section)
        self.assertIn("NATGW", section)
        self.assertIn("ACG 규칙", section)
        self.assertIn("web-acg", section)
        self.assertIn("10.0.0.0/8", section)
        self.assertIn("Network ACL 규칙", section)
        self.assertIn("private-nacl", section)
        self.assertIn("ALLOW", section)
        self.assertIn("empty-acg", section)
        self.assertIn("empty-nacl", section)
        self.assertIn("ACG 수집 완료, 명시 규칙 0건", section)
        self.assertIn("NACL 수집 완료, 명시 규칙 0건", section)
        self.assertIn(
            "실제 규칙 Route 1건 · ACG 1건 · NACL 1건",
            section,
        )

    def test_infrastructure_charts_preserve_metric_units(self):
        report = self._sample_report()
        report.infrastructure = [
            {
                "category": "LOAD_BALANCER",
                "resource_name": "lb-1",
            },
            {
                "category": "CLOUD_DB",
                "resource_name": "mysql-1",
            },
            {
                "category": "KUBERNETES",
                "resource_name": "cluster-1",
            },
            {
                "category": "NAS",
                "resource_name": "nas-1",
            },
        ]
        report.infrastructure_metrics = [
            {
                "category": "LOAD_BALANCER",
                "product_name": "System/Load Balancer(VPC)",
                "metric": "traffic_in_byte",
                "metric_label": "수신 트래픽",
                "unit": "bytes/sec",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "lb-1",
                    "resource_name": "lb-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 1048576],
                        [1780272300000, 2097152],
                    ],
                }],
            },
            {
                "category": "CLOUD_DB",
                "product_name": "System/Cloud DB for MySQL(VPC)",
                "metric": "cpu_used_rto",
                "metric_label": "CPU 사용률",
                "unit": "%",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "mysql-1",
                    "resource_name": "mysql-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 25],
                        [1780272300000, 50],
                    ],
                }],
            },
            {
                "category": "KUBERNETES",
                "product_name": "System/Ncloud Kubernetes Service",
                "metric": "node_ready_count",
                "metric_label": "Ready 노드",
                "unit": "count",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "cluster-1",
                    "resource_name": "cluster-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 2],
                        [1780272300000, 3],
                    ],
                }],
            },
            {
                "category": "NAS",
                "product_name": "System/NAS(VPC)",
                "metric": "volume_used_ratio",
                "metric_label": "볼륨 사용률",
                "unit": "%",
                "interval": "Min5",
                "aggregation": "AVG",
                "series": [{
                    "resource_id": "nas-1",
                    "resource_name": "nas-1",
                    "dimensions": {},
                    "points": [
                        [1780272000000, 40],
                        [1780272300000, 45],
                    ],
                }],
            },
        ]

        html = HtmlReportRenderer().render(report)
        monitoring = html.split("<h2>주요 인프라 모니터링</h2>", 1)[1]
        self.assertIn("비교할 자원을 여러 개 선택", monitoring)
        lb_chart = monitoring.split(
            "<h3>Load Balancer · 수신 트래픽</h3>",
            1,
        )[1].split("</article>", 1)[0]
        cdb_chart = monitoring.split(
            "<h3>Cloud DB for MySQL · CPU 사용률</h3>",
            1,
        )[1].split("</article>", 1)[0]
        nks_chart = monitoring.split(
            "<h3>Kubernetes · Ready 노드</h3>",
            1,
        )[1].split("</article>", 1)[0]
        nas_chart = monitoring.split(
            "<h3>NAS · 볼륨 사용률</h3>",
            1,
        )[1].split("</article>", 1)[0]

        self.assertIn("1.0 MiB/s", lb_chart)
        self.assertNotIn("%", lb_chart)
        self.assertIn("25%", cdb_chart)
        self.assertIn("50%", cdb_chart)
        self.assertIn("cluster-1", nks_chart)
        self.assertNotIn("2%", nks_chart)
        self.assertNotIn("3%", nks_chart)
        self.assertIn("40%", nas_chart)
        self.assertIn("45%", nas_chart)

    def test_cdb_chart_does_not_repeat_node_role_in_legend(self):
        report = self._sample_report()
        report.infrastructure = [{
            "category": "CLOUD_DB",
            "resource_name": "postgres-service",
        }]
        report.infrastructure_metrics = [{
            "category": "CLOUD_DB",
            "product_name": "System/Cloud DB for PostgreSQL(VPC)",
            "metric": "active_session_count",
            "metric_label": "활성 세션 수",
            "unit": "count",
            "interval": "Min5",
            "aggregation": "AVG",
            "series": [{
                "resource_id": "db-1",
                "resource_name": "postgres-service · pg-node-1 (1001) · PRIMARY",
                "dimensions": {"role": "PRIMARY"},
                "points": [[1780272000000, 3]],
            }],
        }]

        html = HtmlReportRenderer().render(report)
        monitoring = html.split("<h2>주요 인프라 모니터링</h2>", 1)[1]

        self.assertIn(
            "<h3>Cloud DB for PostgreSQL · 활성 세션 수</h3>",
            monitoring,
        )
        self.assertIn(
            "postgres-service · pg-node-1 (1001) · PRIMARY",
            monitoring,
        )
        self.assertNotIn("PRIMARY · PRIMARY", monitoring)

    def test_target_group_ready_data_is_integrated_with_load_balancer(self):
        report = self._sample_report()
        report.collection_metadata = {
            "infrastructure": {
                "completed_at": "2026-07-01T00:05:00+09:00",
            }
        }
        report.infrastructure = [
            {
                "category": "LOAD_BALANCER",
                "resource_id": "lb-1",
                "resource_name": "public-alb",
                "details": {
                    "target_group_count": 1,
                    "target_health_snapshot_available": True,
                    "registered_target_count": 4,
                    "ready_target_count": 2,
                    "unready_target_count": 1,
                    "unused_target_count": 1,
                    "unknown_target_count": 0,
                },
            },
            {
                "category": "TARGET_GROUP",
                "resource_id": "tg-1",
                "resource_name": "web-targets",
                "details": {
                    "target_group_no": "tg-1",
                    "load_balancer_instance_no": "lb-1",
                    "protocol": "HTTP",
                    "port": 8080,
                    "registered_target_count": 4,
                    "ready_target_count": 2,
                    "unready_target_count": 1,
                    "unused_target_count": 1,
                    "unknown_target_count": 0,
                    "health_snapshot_available": True,
                },
            },
        ]
        report.infrastructure_metrics = [{
            "category": "LOAD_BALANCER",
            "metric_scope": "TARGET_GROUP",
            "resource_type": "TargetGroup",
            "product_name": "System/Load Balancer Target Group(VPC)",
            "metric": "available_host_count",
            "metric_label": "Ready Target 수 (구간 최소)",
            "unit": "count",
            "interval": "Min5",
            "aggregation": "MIN",
            "series": [{
                "resource_id": "tg-1",
                "resource_name": "web-targets",
                "dimensions": {"targetGroupNo": "tg-1"},
                "points": [[1780272000000, 2]],
            }],
        }]

        html = HtmlReportRenderer().render(report)

        self.assertNotIn("LB Target Group 상태", html)
        self.assertIn("Target Group: 1", html)
        self.assertIn("등록 Target: 4", html)
        self.assertIn("Ready: 2", html)
        self.assertIn("Unready: 1", html)
        self.assertIn(
            "Load Balancer · Ready Target 수 (구간 최소)",
            html,
        )
        self.assertNotIn("LB Target Group ·", html)
        self.assertIn("MIN", html)

    def test_insight_event_detail_fields_are_rendered_and_escaped(self):
        report = self._sample_report()
        report.insight_events = [
            {
                "event_id": "event-1",
                "start_time": 1781508312345,
                "start_time_kst": "2026-06-15 13:45:12.345 KST",
                "level": "CRITICAL",
                "resource_name": "web-01",
                "rule_name": "CPU high",
                "metric": "cpu_used_rto",
                "operator_symbol": ">=",
                "criteria": "80",
                "detect_value": "91.5",
                "unit": "%",
                "calc": "AVG",
                "interval": "Min5",
                "dimension": {"instanceNo": "<server-1>"},
            }
        ]

        html = HtmlReportRenderer().render(report)

        self.assertIn("2026-06-15 13:45:12.345 KST", html)
        self.assertIn("cpu_used_rto &gt;= 80 / 감지 91.5%", html)
        self.assertIn("집계 함수", html)
        self.assertIn("Min5", html)
        self.assertIn("&lt;server-1&gt;", html)

    def test_partial_period_uses_estimated_cost_instead_of_zero_demand(self):
        report = self._sample_report()
        report.period["is_closed_month"] = False
        report.billing = {
            "summary": {
                "confirmed_total_amount": 0,
                "expected_total_amount": 4321,
            },
            "service_summary": [
                {"service_name": "Server", "amount": 0, "row_count": 1}
            ],
            "expected_by_service": [
                {
                    "service_name": "Server",
                    "expected_amount": 4321,
                    "row_count": 2,
                }
            ],
            "network_usage_summary": [],
            "usage_summary": [],
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("서비스별 예상 비용", html)
        self.assertIn("4,321", html)
        self.assertIn("미확정 예상 비용", html)

    def test_month_to_date_ncp_cost_replaces_duplicate_period_card(self):
        report = self._sample_report()
        report.period["is_closed_month"] = False
        report.billing = {
            "summary": {"expected_total_amount": 9999},
            "period_estimate": {
                "cost_type": "PERIOD_ESTIMATE",
                "status": "NOT_APPLICABLE",
            },
            "month_to_date_estimate": {
                "cost_type": "MONTH_TO_DATE_ESTIMATE",
                "status": "AVAILABLE",
                "period_start": "2026-08-01",
                "period_end": "2026-08-16",
                "coverage_start": "2026-08-01",
                "coverage_end": "2026-08-16",
                "total_amount": 4321,
                "amount_basis": "NCP_PRODUCT_DEMAND_USE_AMOUNT",
                "confidence": "PARTIAL",
                "includes_discount": False,
                "includes_vat": False,
            },
            "target_service_summary": [
                {
                    "service_name": "Server",
                    "use_amount": 4321,
                    "row_count": 2,
                }
            ],
            "network_usage_summary": [],
            "usage_summary": [],
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("4,321", html)
        self.assertNotIn("9,999", html)
        self.assertIn("NCP 서비스별 누적 사용금액", html)
        self.assertNotIn("보고 기간 추정 데이터", html)

    def test_operational_summary_uses_only_report_period_cost(self):
        report = self._sample_report()
        report.period.update({
            "period_type": "month",
            "start_dt": "2026-08-01 00:00:00",
            "end_dt": "2026-08-31 23:59:59",
            "use_start_date": "20260801",
            "use_end_date": "20260831",
        })
        report.analysis = {
            "period_type": "MONTHLY",
            "overall_status": "NORMAL",
            "overall_status_label": "정상",
            "report_generation": {
                "status": "SUCCESS",
                "status_label": "성공",
            },
            "data_quality": {
                "overall_status": "COMPLETE",
                "datasets": [],
            },
            "key_findings": [],
            "metrics": {},
            "events": {"status": "COLLECTED_EMPTY"},
            "changes": {"status": "COLLECTED_EMPTY"},
            "availability": {},
            "security": {},
            "costs": {
                "facts": [
                    {
                        "name": "invoice_summary",
                        "period_start": "2026-07-01",
                        "period_end": "2026-07-31",
                        "total_amount": 825000,
                    },
                    {
                        "name": "month_end_projection",
                        "period_start": "2026-08-01",
                        "period_end": "2026-08-31",
                        "total_amount": 9999,
                    },
                ],
                "comparison": {
                    "status": "AVAILABLE",
                    "current_amount": 9999,
                    "baseline_amount": 8888,
                    "amount_change": 1111,
                    "rate_change": 12.5,
                    "amount_basis": "PROJECTED_USAGE_RERATED",
                    "current_period_start": "2026-08-01",
                    "current_period_end": "2026-08-31",
                    "current_coverage_start": "2026-08-01",
                    "current_coverage_end": "2026-08-06",
                    "baseline_period_start": "2026-07-01",
                    "baseline_period_end": "2026-07-31",
                    "baseline_coverage_start": "2026-07-01",
                    "baseline_coverage_end": "2026-07-06",
                    "reason": "동일 기준 비교",
                },
            },
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn(
            "월말 추정 금액 · 2026-08-01~2026-08-31",
            html,
        )
        self.assertNotIn(
            "확정 청구 금액 · 2026-07-01~2026-07-31",
            html,
        )
        self.assertIn(
            "대상 2026-08-01 ~ 2026-08-31 · 수집 "
            "2026-08-01 ~ 2026-08-06",
            html,
        )
        self.assertIn(
            "대상 2026-07-01 ~ 2026-07-31 · 수집 "
            "2026-07-01 ~ 2026-07-06",
            html,
        )
        comparison_section = html.split(
            "<h2>비용 전기 비교</h2>", 1
        )[1].split("</section>", 1)[0]
        self.assertNotIn("이벤트·변경·비용 비교", html)
        self.assertNotIn("Critical 이벤트", comparison_section)
        self.assertNotIn("미종료 이벤트", comparison_section)
        self.assertNotIn("전체 활동", comparison_section)
        self.assertNotIn("실패 활동", comparison_section)
        self.assertIn("현재 금액", comparison_section)
        self.assertIn("이전 금액", comparison_section)

    def test_operational_analysis_displays_source_states(self):
        report = self._sample_report()
        report.period.update({
            "period_type": "day",
            "start_dt": "2026-08-12 00:00:00",
            "end_dt": "2026-08-12 23:59:59",
            "use_start_date": "20260812",
            "use_end_date": "20260812",
        })
        report.analysis = {
            "source_state": "CALCULATED",
            "period_type": "DAILY",
            "overall_status": "CAUTION",
            "overall_status_label": "주의",
            "report_generation": {
                "status": "SUCCESS",
                "status_label": "성공",
                "source_state": "OBSERVED",
            },
            "data_quality": {
                "overall_status": "PARTIAL",
                "source_state": "CALCULATED",
                "datasets": [{
                    "label": "보안 이벤트",
                    "status": "FAILED",
                    "status_label": "수집 실패",
                    "source_state": "COLLECTION_FAILED",
                    "record_count": 0,
                    "error_count": 1,
                    "warning_count": 0,
                    "reason": "API 호출 실패",
                }],
            },
            "key_findings": [
                {
                    "severity": "WARNING",
                    "category": "PERFORMANCE",
                    "title": "CPU 임계치 확인 필요",
                    "source_state": "CALCULATED",
                    "resource": {"name": "web-1"},
                    "evidence": [],
                },
                {
                    "severity": "WARNING",
                    "category": "DATA_QUALITY",
                    "title": "수집 상태 확인 필요",
                    "source_state": "CALCULATED",
                    "resource": {"name": "보안 이벤트"},
                    "evidence": [],
                },
            ],
            "metrics": {
                "source_state": "CALCULATED",
                "summaries": [{
                    "category": "SERVER",
                    "resource_name": "web-1",
                    "metric_label": "CPU 사용률",
                    "source_state": "CALCULATED",
                    "average": 10,
                    "p95": 20,
                    "maximum": 30,
                }],
            },
            "events": {
                "status": "COLLECTED_EMPTY",
                "source_state": "CALCULATED",
            },
            "changes": {
                "status": "COLLECTED_EMPTY",
                "source_state": "CALCULATED",
            },
            "availability": {
                "source_state": "CALCULATED",
                "items": [{
                    "name": "homepage",
                    "source_state": "OBSERVED",
                    "availability_percent": 100,
                }],
            },
            "security": {
                "source_state": "COLLECTION_FAILED",
                "items": [],
            },
            "costs": {
                "source_state": "CALCULATED",
                "facts": [{
                    "name": "period_estimate",
                    "source_state": "CALCULATED",
                    "period_start": "2026-08-12",
                    "period_end": "2026-08-12",
                    "total_amount": 100,
                }],
                "comparison": {
                    "status": "UNAVAILABLE",
                    "source_state": "UNAVAILABLE",
                    "reason": "이전 보고서 없음",
                },
            },
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("출처 상태", html)
        self.assertIn("OBSERVED (관측)", html)
        self.assertIn("CALCULATED (계산)", html)
        self.assertIn("COLLECTION_FAILED (수집 실패)", html)
        self.assertIn("UNAVAILABLE (미수집)", html)
        self.assertIn("즉시 확인</span><strong>1건", html)
        self.assertIn("CPU 임계치 확인 필요", html)
        self.assertNotIn("수집 상태 확인 필요", html)

    def test_operational_metric_table_only_shows_sustained_90_percent_alerts(self):
        report = self._sample_report()
        report.analysis = {
            "source_state": "CALCULATED",
            "period_type": "DAILY",
            "overall_status": "CAUTION",
            "data_quality": {
                "overall_status": "COMPLETE",
                "source_state": "CALCULATED",
                "datasets": [],
            },
            "findings": [],
            "metrics": {
                "source_state": "CALCULATED",
                "summaries": [
                    {
                        "category": "SERVER",
                        "resource_name": "cpu-alert",
                        "metric_label": "CPU 사용률",
                        "metric_kind": "CPU",
                        "source_state": "CALCULATED",
                        "average": 91,
                        "p95": 92,
                        "maximum": 92,
                        "alert_severity": "WARNING",
                        "alert_duration_seconds": 900,
                    },
                    {
                        "category": "NAS",
                        "resource_name": "nas-alert",
                        "metric_label": "볼륨 사용률",
                        "metric_kind": "FILESYSTEM",
                        "source_state": "CALCULATED",
                        "average": 95,
                        "p95": 96,
                        "maximum": 96,
                        "alert_severity": "CRITICAL",
                        "alert_duration_seconds": 900,
                    },
                    {
                        "category": "SERVER",
                        "resource_name": "below-90",
                        "metric_label": "메모리 사용률",
                        "metric_kind": "MEMORY",
                        "source_state": "CALCULATED",
                        "maximum": 89.9,
                        "alert_severity": "WARNING",
                    },
                    {
                        "category": "SERVER",
                        "resource_name": "not-sustained",
                        "metric_label": "CPU 사용률",
                        "metric_kind": "CPU",
                        "source_state": "CALCULATED",
                        "maximum": 99,
                    },
                    {
                        "category": "CLOUD_DB",
                        "resource_name": "free-or-absolute",
                        "metric_label": "디스크 여유 용량",
                        "metric_kind": None,
                        "source_state": "CALCULATED",
                        "maximum": 999,
                        "alert_severity": "CRITICAL",
                    },
                ],
            },
            "events": {},
            "changes": {},
            "availability": {},
            "security": {},
            "costs": {},
        }

        html = HtmlReportRenderer().render(report)
        metric_section = html.split(
            "<h2>90% 이상 지속 사용 자원</h2>", 1
        )[1].split("</section>", 1)[0]

        self.assertIn("cpu-alert", metric_section)
        self.assertIn("nas-alert", metric_section)
        self.assertIn(">주의</td>", metric_section)
        self.assertIn(">위험</td>", metric_section)
        self.assertNotIn("below-90", metric_section)
        self.assertNotIn("not-sustained", metric_section)
        self.assertNotIn("free-or-absolute", metric_section)

    def test_operational_metric_table_labels_top_ten_and_total_count(self):
        report = self._sample_report()
        report.analysis = {
            "source_state": "CALCULATED",
            "period_type": "DAILY",
            "overall_status": "CAUTION",
            "data_quality": {
                "overall_status": "COMPLETE",
                "source_state": "CALCULATED",
                "datasets": [],
            },
            "findings": [],
            "metrics": {
                "source_state": "CALCULATED",
                "summaries": [
                    {
                        "category": "SERVER",
                        "resource_name": f"alert-{index:02d}",
                        "metric_label": "CPU 사용률",
                        "metric_kind": "CPU",
                        "source_state": "CALCULATED",
                        "average": 90 + index / 10,
                        "p95": 90 + index / 10,
                        "maximum": 90 + index / 10,
                        "alert_severity": "WARNING",
                        "alert_duration_seconds": 900,
                    }
                    for index in range(11)
                ],
            },
            "events": {},
            "changes": {},
            "availability": {},
            "security": {},
            "costs": {},
        }

        html = HtmlReportRenderer().render(report)
        metric_section = html.split(
            "<h2>90% 이상 지속 사용 자원</h2>", 1
        )[1].split("</section>", 1)[0]

        self.assertIn("상위 10건", metric_section)
        self.assertIn('<span class="count">11건</span>', metric_section)
        self.assertEqual(metric_section.count("<tr>"), 11)
        self.assertNotIn(">alert-00<", metric_section)
        self.assertIn(">alert-10<", metric_section)

    def test_historical_governance_only_snapshot_recalculates_visible_status(self):
        report = self._sample_report()
        report.analysis = {
            "version": "1.1",
            "source_state": "CALCULATED",
            "period_type": "DAILY",
            "overall_status": "CAUTION",
            "overall_status_label": "주의",
            "data_quality": {
                "overall_status": "COMPLETE",
                "source_state": "CALCULATED",
                "datasets": [],
            },
            "key_findings": [{
                "severity": "WARNING",
                "category": "GOVERNANCE",
                "title": "블록 스토리지가 암호화되지 않았습니다.",
                "source_state": "CALCULATED",
                "resource": {"name": "disk-1"},
                "evidence": [],
            }],
            "metrics": {"summaries": []},
            "events": {},
            "changes": {},
            "availability": {},
            "security": {},
            "costs": {},
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn(
            "클라우드 운영 판정</span><strong>수집·검사 범위 내 정상",
            html,
        )
        self.assertIn("즉시 확인</span><strong>0건", html)
        self.assertNotIn("블록 스토리지가 암호화되지 않았습니다.", html)

    def test_historical_metric_finding_below_90_is_hidden(self):
        report = self._sample_report()
        report.analysis = {
            "version": "1.1",
            "source_state": "CALCULATED",
            "period_type": "DAILY",
            "overall_status": "CAUTION",
            "overall_status_label": "주의",
            "data_quality": {
                "overall_status": "COMPLETE",
                "source_state": "CALCULATED",
                "datasets": [],
            },
            "key_findings": [{
                "rule_id": "METRIC_CPU_SUSTAINED",
                "severity": "WARNING",
                "category": "PERFORMANCE",
                "title": "web-1의 CPU 사용률 80% 초과가 지속되었습니다.",
                "status": "OPEN",
                "source_state": "CALCULATED",
                "resource": {"name": "web-1"},
                "evidence": [{
                    "label": "임계치",
                    "value": 80,
                    "unit": "%",
                }],
            }],
            "metrics": {"summaries": []},
            "events": {},
            "changes": {},
            "availability": {},
            "security": {},
            "costs": {},
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn(
            "클라우드 운영 판정</span><strong>수집·검사 범위 내 정상",
            html,
        )
        self.assertIn("즉시 확인</span><strong>0건", html)
        self.assertNotIn("CPU 사용률 80% 초과", html)

    def test_unavailable_daily_billing_uses_labeled_month_to_date_tables(self):
        report = self._sample_report()
        report.period.update({
            "period_type": "day",
            "start_dt": "2026-08-12 00:00:00",
            "end_dt": "2026-08-12 23:59:59",
            "is_closed_month": False,
            "calculated_at": "2026-08-13T00:20:20+09:00",
        })
        report.billing = {
            "summary": {"expected_total_amount": 0},
            "period_estimate": {
                "status": "UNAVAILABLE",
                "total_amount": 0,
            },
            "month_to_date_estimate": {
                "status": "AVAILABLE",
                "coverage_start": "2026-08-01",
                "coverage_end": "2026-08-11",
                "total_amount": 4321,
                "amount_basis": "PRE_DISCOUNT_LIST_PRICE",
            },
            "daily_usage_rows": [],
            "month_to_date_usage_rows": [{"usage": {}}],
            "month_to_date_by_service": [{
                "service_name": "Server",
                "expected_amount": 4321,
                "row_count": 2,
            }],
            "month_to_date_network_usage_summary": [{
                "service_name": "Server",
                "direction": "Outbound",
                "name": "Internet Outbound",
                "usage_gb": 12.5,
                "row_count": 1,
            }],
            "month_to_date_usage_summary": [{
                "service_name": "Server",
                "item_name": "Network Outbound",
                "usage_quantity": 12.5,
                "unit_code": "GBYTE",
                "row_count": 1,
            }],
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("월 누적 서비스별 예상 비용", html)
        self.assertIn("월 누적 네트워크 사용량", html)
        self.assertIn("월 누적 서비스별 사용량", html)
        self.assertIn("2026-08-01 ~ 2026-08-11", html)
        self.assertIn("4,321", html)
        self.assertIn("12.500", html)
        self.assertIn("실제 사용량 0이거나 아직 반영 전일 수 있어", html)

    def test_past_zero_usage_does_not_use_unrelated_month_to_date_data(self):
        report = self._sample_report()
        report.period.update({
            "period_type": "day",
            "start_dt": "2026-08-05 00:00:00",
            "end_dt": "2026-08-05 23:59:59",
            "is_closed_month": False,
            "calculated_at": "2026-08-13T09:00:00+09:00",
        })
        report.billing = {
            "summary": {"expected_total_amount": 0},
            "period_estimate": {"status": "UNAVAILABLE"},
            "month_to_date_estimate": {
                "status": "AVAILABLE",
                "coverage_start": "2026-08-01",
                "coverage_end": "2026-08-11",
                "total_amount": 4321,
            },
            "daily_usage_rows": [],
            "month_to_date_usage_rows": [{"usage": {}}],
            "month_to_date_by_service": [{
                "service_name": "Server",
                "expected_amount": 4321,
                "row_count": 2,
            }],
            "month_to_date_usage_summary": [{
                "service_name": "Server",
                "item_name": "CPU",
                "usage_quantity": 100,
                "unit_code": "HOUR",
                "row_count": 1,
            }],
        }

        html = HtmlReportRenderer().render(report)
        billing_display = HtmlReportRenderer()._prepare_billing_display(
            report.period,
            report.billing,
        )

        self.assertNotIn("월 누적 서비스별 예상 비용", html)
        self.assertNotIn("월 누적 서비스별 사용량", html)
        self.assertIn("NCP가 선택 기간의 일별 사용량 데이터를", html)
        self.assertEqual(billing_display.service_summary, [])
        self.assertIsNone(billing_display.card_amount)
        self.assertIn("조회 불가", html)

    def test_month_end_daily_delay_can_use_previous_month_to_date_data(self):
        renderer = HtmlReportRenderer()
        use_fallback = renderer._use_delayed_month_to_date_usage(
            period={
                "period_type": "day",
                "start_dt": "2026-08-31 00:00:00",
                "end_dt": "2026-08-31 23:59:59",
                "is_closed_month": False,
                "calculated_at": "2026-09-01T00:20:20+09:00",
            },
            period_usage_rows=[],
            month_to_date_usage_rows=[{"usage": {}}],
            month_to_date_estimate={
                "status": "AVAILABLE",
                "coverage_end": "2026-08-30",
            },
            daily_usage_failed=False,
        )

        self.assertTrue(use_fallback)

    def test_daily_usage_error_does_not_use_month_to_date_fallback(self):
        report = self._sample_report()
        report.period.update({
            "period_type": "day",
            "start_dt": "2026-08-12 00:00:00",
            "end_dt": "2026-08-12 23:59:59",
            "is_closed_month": False,
            "calculated_at": "2026-08-13T00:20:20+09:00",
        })
        report.billing = {
            "summary": {"expected_total_amount": 0},
            "period_estimate": {"status": "UNAVAILABLE"},
            "month_to_date_estimate": {
                "status": "AVAILABLE",
                "coverage_start": "2026-08-01",
                "coverage_end": "2026-08-11",
                "total_amount": 4321,
            },
            "daily_usage_rows": [],
            "month_to_date_usage_rows": [{"usage": {}}],
            "month_to_date_by_service": [{
                "service_name": "Server",
                "expected_amount": 4321,
                "row_count": 2,
            }],
        }
        report.collection_errors = [{
            "source": "daily_usage",
            "api": "daily_usage",
        }]

        html = HtmlReportRenderer().render(report)
        billing_display = HtmlReportRenderer()._prepare_display_data(
            report
        ).billing

        self.assertNotIn("월 누적 서비스별 예상 비용", html)
        self.assertIn("getContractUsageListByDaily 수집 오류", html)
        self.assertEqual(billing_display.service_summary, [])
        self.assertIsNone(billing_display.card_amount)
        self.assertIn("조회 불가", html)

    def test_monthly_header_uses_inclusive_last_day(self):
        report = self._sample_report()
        report.period = {
            "period_type": "month",
            "start_dt": "2026-07-01 00:00:00",
            "end_dt": "2026-08-01 00:00:00",
            "end_exclusive": True,
            "file_suffix": "20260701_20260731",
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn("2026-07-01", html)
        self.assertIn("2026-07-31", html)
        self.assertNotIn("2026-08-01", html)

    def test_single_day_report_uses_full_day_axis_and_hourly_average(self):
        report = self._sample_report()
        report.period = {
            "period_type": "day",
            "start_dt": "2026-06-15 00:00:00",
            "end_dt": "2026-06-15 23:59:59",
            "file_suffix": "20260615_20260615",
        }
        for metric in report.server_metrics:
            metric["metric_interval"] = "Min5"

        html = HtmlReportRenderer().render(report)

        self.assertIn("KST 5분 AVG", html)
        self.assertIn("CPU 5분 AVG 사용률", html)
        self.assertIn(">00:00</text>", html)
        self.assertIn(">23:59</text>", html)
        self.assertNotIn("2026-06-16 KST", html)

    def test_report_omits_empty_metric_chart_section(self):
        report = self._sample_report()
        for metric in report.server_metrics:
            metric.pop("raw_metrics", None)

        html = HtmlReportRenderer().render(report)

        self.assertNotIn("보고 기간 메트릭 변화", html)

    def test_chart_splits_lines_across_missing_intervals(self):
        renderer = HtmlReportRenderer()
        two_hours = 2 * 60 * 60 * 1000
        points = [
            (0, 1.0),
            (two_hours, 2.0),
            (10 * two_hours, 3.0),
        ]

        segments = renderer._split_chart_points(
            points,
            expected_interval=two_hours,
        )

        self.assertEqual(segments, [points[:2], points[2:]])

    def test_chart_downsampling_bounds_svg_points_and_keeps_extrema(self):
        renderer = HtmlReportRenderer()
        points = [(index, float(index % 17)) for index in range(10_000)]
        points[5_000] = (5_000, 999.0)

        sampled = renderer._downsample_chart_points(points, max_points=600)

        self.assertLessEqual(len(sampled), 600)
        self.assertEqual(sampled[0], points[0])
        self.assertEqual(sampled[-1], points[-1])
        self.assertIn((5_000, 999.0), sampled)

    def test_event_tables_are_sorted_oldest_first(self):
        renderer = HtmlReportRenderer()
        insight_html = renderer._event_table(
            [
                {
                    "event_id": "late",
                    "start_time": 1781508600000,
                    "message": "insight-late",
                },
                {
                    "event_id": "early",
                    "start_time": 1781505000000,
                    "message": "insight-early",
                },
            ]
        )
        activity_rows = renderer._flatten_grouped(
            {
                "late-group": [
                    {
                        "event_id": "late",
                        "event_time": 1781508600000,
                    }
                ],
                "early-group": [
                    {
                        "event_id": "early",
                        "event_time": 1781505000000,
                    }
                ],
            }
        )

        self.assertLess(
            insight_html.index("insight-early"),
            insight_html.index("insight-late"),
        )
        self.assertEqual(
            [row["event_id"] for row in activity_rows],
            ["early", "late"],
        )

    def test_render_escapes_collected_values_and_omits_raw_metrics(self):
        html = HtmlReportRenderer().render(self._sample_report())

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("must", html)

    def test_customer_report_sections_follow_configured_order(self):
        report = self._sample_report()
        report.billing["account_costs"] = [{
            "display_name": "Member account",
            "member_no": "member-1",
        }]
        report.report_options = {
            "schema_version": REPORT_OPTIONS_SCHEMA_VERSION,
            "sections": [
                "billing",
                "organization_billing",
                "insight_events",
                "activity_history",
                "collection_diagnostics",
            ],
            "section_order": [
                "collection_diagnostics",
                "organization_billing",
                "activity_history",
                "billing",
                "insight_events",
            ],
            "resource_categories": [],
            "monitoring_categories": [],
        }

        html = HtmlReportRenderer().render(report)
        positions = [
            html.index(heading)
            for heading in (
                ">수집 진단</span>",
                ">Organization 계정별 비용</span>",
                ">Cloud Activity Tracer</span>",
                "<h2>과금 데이터 기준</h2>",
                ">Cloud Insight 이벤트</span>",
            )
        ]

        self.assertEqual(positions, sorted(positions))

    def test_customer_report_options_hide_unselected_sections(self):
        report = self._sample_report()
        report.analysis = {
            "data_quality": {"overall_status": "COMPLETE", "datasets": []},
            "metrics": {"summaries": []},
            "costs": {},
            "availability": {},
            "security": {},
        }
        report.report_options = {
            "sections": ["activity_history"],
            "resource_categories": [],
            "monitoring_categories": [],
        }

        html = HtmlReportRenderer().render(report)

        self.assertIn(">Cloud Activity Tracer</span>", html)
        self.assertNotIn(">서버 현황</span>", html)
        self.assertNotIn(">기타 자원 현황</span>", html)
        self.assertNotIn("<h2>과금 데이터 기준</h2>", html)
        self.assertNotIn(">Cloud Insight 이벤트</span>", html)
        self.assertNotIn("<h2>수집 오류</h2>", html)
        self.assertNotIn("<h2>비용 전기 비교</h2>", html)
        self.assertNotIn('aria-label="운영 판단 요약"', html)

    def test_collection_diagnostics_merge_warnings_and_errors_with_targets(self):
        report = self._sample_report()
        report.report_options = {
            "sections": ["collection_diagnostics"],
            "resource_categories": [],
            "monitoring_categories": [],
        }
        report.collection_warnings = [{
            "collector": "InfrastructureCollector",
            "stage": "collection",
            "target_type": "cdb_postgresql",
            "api": "get_cloud_postgresql_instance_list",
            "status_code": 403,
            "error_code": "2300",
            "message": "권한이 없습니다.",
        }]
        report.collection_errors = [{
            "collector": "ServerCollector",
            "stage": "pagination",
            "target_type": "server",
            "target_id": "server-123",
            "api": "get_server_instance_list",
            "status_code": 500,
            "message": "수집에 실패했습니다.",
        }]

        html = HtmlReportRenderer().render(report)
        diagnostics = html.split(">수집 진단</span>", 1)[1].split(
            "</section>",
            1,
        )[0]

        self.assertEqual(html.count(">수집 진단</span>"), 1)
        self.assertIn(
            "<strong>핵심</strong> · 오류 1건 · 경고 1건",
            diagnostics,
        )
        self.assertNotIn("<h2>수집 경고</h2>", html)
        self.assertNotIn("<h2>수집 오류</h2>", html)
        for heading in (
            "구분",
            "NCP 상품 / 대상",
            "수집기",
            "단계",
            "호출 API",
            "HTTP 상태",
            "코드",
            "확인할 권한 / 근거",
            "메시지",
        ):
            self.assertIn(f">{heading}</th>", diagnostics)
        self.assertIn(">경고</td>", diagnostics)
        self.assertIn("Cloud DB for PostgreSQL", diagnostics)
        self.assertIn("get_cloud_postgresql_instance_list", diagnostics)
        self.assertIn("View/getDBServiceList", diagnostics)
        self.assertIn("호출 API 기준 권고", diagnostics)
        self.assertIn(
            "NCP_VPC_CLOUD_DB_FOR_POSTGRESQL_VIEWER",
            diagnostics,
        )
        self.assertIn(">오류</td>", diagnostics)
        self.assertIn("Server · server-123", diagnostics)
        self.assertIn("get_server_instance_list", diagnostics)
        self.assertIn(">-</td>", diagnostics)

    def test_permission_cell_separates_provider_and_catalog_evidence(self):
        row = normalize_collection_issue({
            "target_type": "server",
            "api": "get_server_instance_list",
            "status_code": 400,
            "error_code": "X00004",
            "required_actions": ["View/getServerInstanceList"],
        })

        cell = HtmlReportRenderer._diagnostic_permission(row)

        self.assertEqual(cell.count("NCP 응답 확인"), 1)
        self.assertIn("View/getServerInstanceList (NCP 응답 확인)", cell)
        self.assertIn("연관 권한(공식 권한표 기준)", cell)
        self.assertIn("관리형 대안(공식 권한표 기준)", cell)

    def test_permission_cell_warns_instead_of_recommending_write_action(self):
        row = normalize_collection_issue({
            "target_type": "network_interface",
            "api": "get_network_interface_instance_list",
            "status_code": 400,
            "error_code": "X00004",
            "required_actions": ["Change/setSecondaryIP"],
        })

        cell = HtmlReportRenderer._diagnostic_permission(row)

        self.assertIn("NCP 응답 쓰기 권한 감지", cell)
        self.assertIn("Change/setSecondaryIP", cell)
        self.assertIn("부여 권고 안 함", cell)

    def test_write_creates_utf8_html_file(self):
        report = self._sample_report()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "report.html"
            result = HtmlReportRenderer().write(report, path)

            self.assertEqual(result, path)
            self.assertTrue(path.exists())
            self.assertIn(
                "NCP 이용 보고서",
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()

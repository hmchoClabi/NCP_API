"""독립형 HTML 보고서의 정적 스타일 정의."""


HTML_REPORT_STYLES = """
:root {
  color-scheme: light;
  --ink: #14213d;
  --muted: #64748b;
  --line: #dbe4ee;
  --surface: #ffffff;
  --canvas: #f3f6fa;
  --brand: #03c75a;
  --brand-dark: #008f43;
  --warning: #b45309;
  font-family: Inter, Pretendard, "Noto Sans KR", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--canvas);
  line-height: 1.55;
}
.report-shell {
  width: min(1440px, calc(100% - 32px));
  margin: 32px auto;
}
.report-header {
  display: flex;
  justify-content: space-between;
  gap: 32px;
  padding: 36px;
  color: #fff;
  background: linear-gradient(135deg, #0f172a, #164e3b);
  border-radius: 20px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, .16);
}
.report-identity {
  display: flex;
  align-items: center;
  gap: 24px;
  min-width: 0;
}
.customer-logo-plate {
  display: grid;
  place-items: center;
  flex: 0 0 184px;
  width: 184px;
  height: 104px;
  padding: 16px;
  overflow: hidden;
  color: #0f5132;
  background: #f8fafc;
  border: 1px solid rgba(255, 255, 255, .6);
  border-radius: 14px;
}
.customer-logo-plate img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.customer-logo-plate span {
  font-size: 2rem;
  font-weight: 900;
  letter-spacing: -.05em;
}
.report-heading { min-width: 0; }
.eyebrow {
  margin: 0 0 8px;
  color: #86efac;
  font-size: .78rem;
  font-weight: 800;
  letter-spacing: .14em;
}
h1 { margin: 0; font-size: clamp(2rem, 4vw, 3.4rem); line-height: 1.1; }
.subtitle { margin: 18px 0 0; color: #d1fae5; }
.report-meta {
  display: grid;
  grid-template-columns: auto;
  align-content: end;
  min-width: 210px;
}
.report-meta span { color: #a7f3d0; font-size: .75rem; }
.report-meta strong { margin-bottom: 10px; font-size: .88rem; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 20px 0;
}
.summary-card {
  padding: 22px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
}
.summary-card span { display: block; color: var(--muted); font-size: .84rem; }
.summary-card strong { display: block; margin-top: 8px; font-size: 1.75rem; }
.summary-card small { color: var(--muted); font-size: .8rem; font-weight: 600; }
.summary-card.warning { border-color: #fed7aa; }
.summary-card.warning strong { color: var(--warning); }
.operational-overview { margin-top: 20px; }
.operational-overview > .report-section { margin-top: 14px; }
.operational-status-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.operational-status {
  padding: 18px;
  background: #fff;
  border: 1px solid var(--line);
  border-top: 4px solid #94a3b8;
  border-radius: 12px;
}
.operational-status span { display: block; color: var(--muted); font-size: .78rem; }
.operational-status strong { display: block; margin-top: 5px; font-size: 1.35rem; }
.source-state {
  display: block;
  margin-top: 5px;
  color: #64748b;
  font-size: .66rem;
  font-weight: 800;
  letter-spacing: .02em;
}
.operational-status.normal,
.operational-status.complete,
.operational-status.generation-success { border-top-color: var(--brand); }
.operational-status.caution,
.operational-status.partial { border-top-color: #f59e0b; }
.operational-status.risk,
.operational-status.failed { border-top-color: #dc2626; }
.finding-list { display: grid; gap: 10px; }
.finding-card {
  padding: 15px 17px;
  background: #f8fafc;
  border: 1px solid var(--line);
  border-left: 5px solid #64748b;
  border-radius: 10px;
}
.finding-card.critical { border-left-color: #dc2626; background: #fff7f7; }
.finding-card.warning { border-left-color: #f59e0b; background: #fffbeb; }
.finding-heading { display: flex; align-items: baseline; gap: 10px; }
.finding-heading span { color: var(--muted); font-size: .7rem; font-weight: 900; }
.finding-card > p { margin: 4px 0 10px; color: var(--muted); font-size: .78rem; }
.finding-card dl { display: grid; gap: 5px; margin: 0; }
.finding-card dl div { display: grid; grid-template-columns: 52px 1fr; gap: 8px; }
.finding-card dt { color: var(--muted); font-size: .74rem; }
.finding-card dd { margin: 0; font-size: .78rem; }
.infra-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}
.infra-summary-card {
  padding: 14px 16px;
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 10px;
}
.infra-summary-card span { display: block; color: var(--muted); font-size: .76rem; }
.infra-summary-card strong { display: block; margin-top: 3px; font-size: 1.2rem; }
.report-section {
  margin-top: 20px;
  padding: 26px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
}
.report-section.warning { border-color: #fed7aa; }
.network-snapshot-basis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 22px;
}
.network-snapshot-basis div {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 10px;
}
.network-snapshot-basis span { color: var(--muted); font-size: .76rem; }
.network-snapshot-basis strong { font-size: .86rem; }
.network-config-group + .network-config-group { margin-top: 22px; }
.network-config-group h3 { margin: 0 0 9px; font-size: .98rem; }
.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}
h2 { margin: 0; font-size: 1.22rem; }
.section-heading p { margin: 5px 0 0; color: var(--muted); font-size: .88rem; }
.count {
  flex: none;
  padding: 5px 10px;
  color: var(--brand-dark);
  background: #dcfce7;
  border-radius: 999px;
  font-size: .78rem;
  font-weight: 800;
}
.billing-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.billing-fact {
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f8fafc;
}
.billing-fact h3 { margin: 0; font-size: 1rem; }
.billing-amount { display: block; margin: 8px 0 14px; font-size: 1.45rem; }
.billing-fact ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.billing-fact li { display: flex; justify-content: space-between; gap: 16px; font-size: .82rem; }
.billing-fact li span { color: var(--muted); }
.billing-fact li strong { text-align: right; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .84rem; }
th {
  padding: 11px 12px;
  color: #475569;
  background: #f8fafc;
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
td {
  padding: 11px 12px;
  border-bottom: 1px solid #edf2f7;
  vertical-align: top;
}
tbody tr:hover { background: #f8fffb; }
.numeric { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.chart-card {
  min-width: 0;
  padding: 18px;
  background: #fbfdff;
  border: 1px solid var(--line);
  border-radius: 12px;
}
.chart-heading h3 { margin: 0; font-size: 1rem; }
.chart-heading p { margin: 3px 0 12px; color: var(--muted); font-size: .78rem; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart-grid-line { stroke: #e2e8f0; stroke-width: 1; }
.chart-axis-label { fill: #64748b; font-size: 11px; }
.chart-line {
  fill: none;
  stroke-width: 2.4;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 6px;
}
.chart-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: .72rem;
}
.chart-legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.chart-empty { min-height: 180px; align-content: center; }
.event-details { min-width: 160px; }
.event-details summary {
  color: var(--brand-dark);
  cursor: pointer;
  font-weight: 700;
  white-space: nowrap;
}
.event-details dl { margin: 10px 0 0; }
.event-details dl div {
  display: grid;
  grid-template-columns: minmax(90px, .8fr) minmax(140px, 1.4fr);
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid #edf2f7;
}
.event-details dt { color: var(--muted); font-size: .74rem; overflow-wrap: anywhere; }
.event-details dd { margin: 0; font-size: .74rem; overflow-wrap: anywhere; }
.detail-more { margin: 8px 0 0; color: var(--muted); font-size: .72rem; }
.empty-state {
  margin: 0;
  padding: 28px;
  color: var(--muted);
  background: #f8fafc;
  border-radius: 10px;
  text-align: center;
}
footer { padding: 22px 4px; color: var(--muted); font-size: .78rem; text-align: center; }
@media (max-width: 900px) {
  .report-header { flex-direction: column; padding: 28px; }
  .report-identity { width: 100%; }
  .report-meta { grid-template-columns: auto 1fr; gap: 4px 14px; }
  .summary-grid, .billing-facts, .infra-summary-grid, .network-snapshot-basis,
  .operational-status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .chart-grid { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  .report-shell { width: min(100% - 20px, 1440px); margin: 10px auto; }
  .report-header, .report-section { border-radius: 12px; }
  .summary-grid, .billing-facts, .infra-summary-grid, .network-snapshot-basis,
  .operational-status-grid { grid-template-columns: 1fr; gap: 10px; }
  .section-heading { flex-direction: column; gap: 10px; }
  .report-identity { align-items: flex-start; flex-direction: column; }
  .customer-logo-plate { width: min(100%, 220px); height: 100px; }
}
@media print {
  @page { size: A4 landscape; margin: 12mm; }
  body { background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .report-shell { width: 100%; margin: 0; }
  .report-header { box-shadow: none; break-after: avoid; }
  .customer-logo-plate { flex-basis: 150px; width: 150px; height: 84px; }
  .summary-grid, .report-section { break-inside: avoid; }
  .metric-trends { break-inside: auto; }
  .chart-card { break-inside: avoid; }
  .report-section { padding: 18px; }
  table { font-size: 8pt; }
  tr { break-inside: avoid; }
}
"""

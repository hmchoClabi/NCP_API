"""독립형 HTML 보고서의 정적 스타일 정의."""


HTML_REPORT_STYLES = """
:root {
  color-scheme: light;
  --ink: #111827;
  --muted: #667085;
  --line: #d9e1e8;
  --surface: #ffffff;
  --canvas: #eef2f5;
  --brand: #16a34a;
  --brand-dark: #047857;
  --warning: #b45309;
  --danger: #dc2626;
  --info: #2563eb;
  font-family: Inter, Pretendard, "Noto Sans KR", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--canvas);
  font-size: 15px;
  line-height: 1.65;
}
.report-shell {
  width: min(1120px, calc(100% - 32px));
  margin: 28px auto;
}
.report-header {
  position: relative;
  display: flex;
  justify-content: space-between;
  gap: 32px;
  padding: 34px;
  overflow: hidden;
  color: var(--ink);
  background:
    radial-gradient(circle at 84% 8%, rgba(59, 130, 246, .13), transparent 34%),
    radial-gradient(circle at 8% 100%, rgba(22, 163, 74, .11), transparent 32%),
    #fff;
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: 0 14px 36px rgba(15, 23, 42, .08);
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
  flex: 0 0 154px;
  width: 154px;
  height: 86px;
  padding: 14px;
  overflow: hidden;
  color: #0f5132;
  background: rgba(255, 255, 255, .9);
  border: 1px solid #dce5ec;
  border-radius: 12px;
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
  color: var(--brand-dark);
  font-size: .75rem;
  font-weight: 800;
  letter-spacing: .14em;
}
h1 { margin: 0; font-size: clamp(2rem, 4vw, 2.9rem); line-height: 1.15; letter-spacing: -.04em; }
.subtitle { margin: 14px 0 0; color: #475569; font-weight: 650; }
.report-meta {
  display: grid;
  grid-template-columns: auto;
  align-content: end;
  min-width: 210px;
  padding: 14px 16px;
  background: rgba(255, 255, 255, .7);
  border: 1px solid rgba(203, 213, 225, .75);
  border-radius: 12px;
}
.report-meta span { color: var(--muted); font-size: .75rem; }
.report-meta strong { margin-bottom: 9px; color: #334155; font-size: .85rem; }
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
  border-radius: 12px;
  box-shadow: 0 5px 16px rgba(15, 23, 42, .04);
}
.summary-card span { display: block; color: var(--muted); font-size: .84rem; }
.summary-card strong { display: block; margin-top: 8px; font-size: 1.75rem; }
.summary-card small { color: var(--muted); font-size: .8rem; font-weight: 600; }
.summary-card.warning { border-color: #fed7aa; }
.summary-card.warning strong { color: var(--warning); }
.operational-overview { margin-top: 20px; }
.operational-overview > .report-section { margin-top: 14px; }
.daily-summary {
  padding: 28px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, .05);
}
.summary-heading h2 { margin: 2px 0 0; font-size: 1.4rem; }
.summary-heading > p:last-child { margin: 5px 0 0; color: var(--muted); font-size: .9rem; }
.section-eyebrow {
  margin: 0;
  color: var(--brand-dark);
  font-size: .72rem;
  font-weight: 850;
  letter-spacing: .13em;
}
.summary-narrative {
  margin: 18px 0;
  color: #1f2937;
  font-size: 1.05rem;
  font-weight: 700;
}
.legacy-overview .summary-grid { margin-bottom: 14px; }
.legacy-summary-note { margin: 0; color: var(--muted); font-size: .78rem; }
.operational-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
}
.operational-status {
  padding: 16px 18px;
  background: #f8fafc;
  border: 1px solid var(--line);
  border-left: 4px solid #94a3b8;
  border-radius: 10px;
}
.operational-status span { display: block; color: var(--muted); font-size: .8rem; }
.operational-status strong { display: block; margin-top: 5px; font-size: 1.35rem; }
.source-state {
  display: block;
  margin-top: 5px;
  color: #64748b;
  font-size: .75rem;
  font-weight: 800;
  letter-spacing: .02em;
}
.operational-status.normal,
.operational-status.complete,
.operational-status.generation-success { border-left-color: var(--brand); }
.operational-status.caution,
.operational-status.partial { border-left-color: #f59e0b; }
.operational-status.risk,
.operational-status.failed { border-left-color: var(--danger); }
.summary-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}
.summary-fact {
  display: grid;
  grid-template-columns: auto auto;
  align-items: baseline;
  gap: 3px 10px;
  min-width: 230px;
  padding: 11px 14px;
  background: #eff6ff;
  border-radius: 9px;
}
.summary-fact span { color: #475569; font-size: .78rem; }
.summary-fact strong { justify-self: end; color: #1d4ed8; font-size: .9rem; }
.summary-fact small { grid-column: 1 / -1; color: var(--muted); font-size: .72rem; }
.finding-list { display: grid; gap: 10px; }
.finding-card {
  padding: 17px 19px;
  background: #fff;
  border: 1px solid var(--line);
  border-left: 4px solid #64748b;
  border-radius: 10px;
}
.finding-card.critical { border-left-color: #dc2626; background: #fff7f7; }
.finding-card.warning { border-left-color: #f59e0b; background: #fffbeb; }
.finding-card.priority { padding: 20px; border-width: 1px 1px 1px 5px; }
.priority-label {
  display: inline-block;
  margin-bottom: 9px;
  color: var(--warning);
  font-size: .75rem;
  font-weight: 850;
}
.finding-heading { display: flex; align-items: baseline; gap: 10px; }
.finding-heading span { color: var(--muted); font-size: .75rem; font-weight: 850; }
.finding-card > p { margin: 5px 0 12px; color: var(--muted); font-size: .82rem; }
.finding-card dl { display: grid; gap: 5px; margin: 0; }
.finding-card dl div { display: grid; grid-template-columns: 52px 1fr; gap: 8px; }
.finding-card dt { color: var(--muted); font-size: .78rem; }
.finding-card dd { margin: 0; font-size: .83rem; }
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
  padding: 24px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: 0 5px 18px rgba(15, 23, 42, .035);
}
.report-section.warning { border-color: #fed7aa; }
.technical-appendix {
  margin-top: 18px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
}
.technical-appendix > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 17px 20px;
  cursor: pointer;
  color: #334155;
  font-weight: 800;
  list-style: none;
}
.technical-appendix > summary::-webkit-details-marker,
.report-disclosure > summary::-webkit-details-marker { display: none; }
.technical-appendix-copy { display: grid; gap: 2px; }
.technical-appendix-title { font-size: .92rem; }
.technical-appendix > summary:hover { background: #f8fafc; }
.technical-appendix > summary small { color: var(--muted); font-size: .78rem; font-weight: 500; }
.technical-appendix-body { padding: 0 14px 16px; }
.technical-appendix-body > .report-section:first-child { margin-top: 0; }
.report-disclosure { padding: 0; overflow: hidden; }
.report-disclosure > summary {
  margin: 0;
  padding: 20px 24px;
  cursor: pointer;
  list-style: none;
}
.section-heading-copy { flex: 1; min-width: 0; }
.section-title { display: block; font-size: 1.22rem; font-weight: 800; }
.section-description {
  display: block;
  margin-top: 5px;
  max-width: 780px;
  color: var(--muted);
  font-size: .88rem;
}
.section-summary { color: var(--brand-dark); font-weight: 650; }
.report-disclosure > summary .count { margin-left: auto; }
.technical-appendix > summary::after,
.report-disclosure > summary::after {
  width: 8px;
  height: 8px;
  flex: none;
  margin: 7px 3px 0 4px;
  border-right: 2px solid #64748b;
  border-bottom: 2px solid #64748b;
  content: "";
  transform: rotate(-45deg);
  transition: transform .15s ease;
}
.technical-appendix[open] > summary::after,
.report-disclosure[open] > summary::after { transform: rotate(45deg); }
.technical-appendix > summary:focus-visible,
.report-disclosure > summary:focus-visible {
  outline: 3px solid rgba(37, 99, 235, .35);
  outline-offset: -3px;
}
.report-disclosure > summary:hover { background: #f8fafc; }
.report-disclosure-body { padding: 0 24px 24px; }
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
.section-heading p { margin: 5px 0 0; max-width: 780px; color: var(--muted); font-size: .88rem; }
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
.table-wrap { overflow-x: auto; border: 1px solid #e5eaf0; border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: .87rem; }
th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 11px 12px;
  color: #475569;
  background: #f1f5f9;
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
td {
  padding: 11px 12px;
  border-bottom: 1px solid #edf2f7;
  vertical-align: top;
}
table:not(.table-with-details) tbody tr:nth-child(even),
.table-with-details > .table-record:nth-of-type(even) > tr {
  background: #fbfcfd;
}
table:not(.table-with-details) tbody tr:hover,
.table-with-details > .table-record:hover > tr { background: #f0fdf4; }
.table-record.has-detail .table-data-row td { padding-bottom: 6px; border-bottom: 0; }
.table-detail-row td { padding: 0 12px 11px; }
.numeric { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.change-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: .75rem;
  font-weight: 850;
  white-space: nowrap;
}
.change-badge.created { color: #166534; background: #dcfce7; }
.change-badge.removed { color: #b91c1c; background: #fee2e2; }
.change-badge.spec-changed { color: #92400e; background: #fef3c7; }
.change-badge.unknown { color: #475569; background: #e2e8f0; }
.resource-change-name { color: #0f172a; font-weight: 850; }
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.chart-card {
  min-width: 0;
  padding: 18px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
}
.chart-heading h3 { margin: 0; font-size: 1rem; }
.chart-heading p { margin: 3px 0 12px; color: var(--muted); font-size: .82rem; }
.chart-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  margin: -4px 0 6px;
}
.chart-toolbar label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--muted);
  font-size: .75rem;
}
.chart-toolbar button, .chart-toolbar select {
  padding: 6px 10px;
  color: #1d4ed8;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 7px;
  cursor: pointer;
  font: inherit;
  font-size: .75rem;
  font-weight: 750;
}
.chart-toolbar button:hover, .chart-toolbar select:hover { background: #dbeafe; }
.chart-toolbar button:disabled { cursor: wait; opacity: .55; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart-grid-line { stroke: #e2e8f0; stroke-width: 1; }
.chart-axis-label { fill: #64748b; font-size: 13px; }
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
  padding: 3px 5px;
  color: #475569;
  background: transparent;
  border: 0;
  border-radius: 5px;
  cursor: pointer;
  font: inherit;
  font-size: .76rem;
}
.chart-legend-item:hover { background: #f1f5f9; }
.chart-legend-item[aria-pressed="true"] { color: #1d4ed8; background: #eff6ff; }
.chart-legend-item.is-muted { opacity: .42; text-decoration: line-through; }
.chart-legend-item:focus-visible,
.chart-toolbar button:focus-visible,
.chart-toolbar select:focus-visible { outline: 3px solid rgba(37, 99, 235, .35); }
[data-chart-series] { cursor: pointer; }
.chart-legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.chart-empty { min-height: 180px; align-content: center; }
.event-details {
  width: min(960px, 80vw);
  max-width: 100%;
  min-width: 0;
}
.event-details summary {
  color: var(--brand-dark);
  cursor: pointer;
  font-weight: 700;
  white-space: nowrap;
}
.event-details dl { margin: 10px 0 0; }
.event-details dl div {
  display: grid;
  grid-template-columns: minmax(120px, 200px) minmax(0, 1fr);
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid #edf2f7;
}
.event-details dt { color: var(--muted); font-size: .78rem; overflow-wrap: anywhere; }
.event-details dd { margin: 0; font-size: .78rem; overflow-wrap: anywhere; }
.detail-more { margin: 8px 0 0; color: var(--muted); font-size: .76rem; }
.empty-state {
  margin: 0;
  padding: 28px;
  color: var(--muted);
  background: #f8fafc;
  border-radius: 10px;
  text-align: center;
}
footer { padding: 24px 4px; color: var(--muted); font-size: .8rem; text-align: center; }
@media (max-width: 900px) {
  .report-header { flex-direction: column; padding: 28px; }
  .report-identity { width: 100%; }
  .report-meta { grid-template-columns: auto 1fr; gap: 4px 14px; }
  .summary-grid, .billing-facts, .infra-summary-grid, .network-snapshot-basis,
  .operational-status-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .chart-grid { grid-template-columns: 1fr; }
}
@media (max-width: 560px) {
  body { font-size: 14px; }
  .report-shell { width: min(100% - 20px, 1120px); margin: 10px auto; }
  .report-header, .report-section { border-radius: 12px; }
  .report-header, .daily-summary { padding: 21px; }
  .summary-grid, .billing-facts, .infra-summary-grid, .network-snapshot-basis,
  .operational-status-grid { grid-template-columns: 1fr; gap: 10px; }
  .section-heading { flex-direction: column; gap: 10px; }
  .report-identity { align-items: flex-start; flex-direction: column; }
  .customer-logo-plate { width: min(100%, 220px); height: 100px; }
  .summary-fact { width: 100%; min-width: 0; }
  .event-details dl div { grid-template-columns: 1fr; gap: 2px; }
  .technical-appendix > summary,
  .report-disclosure > summary { align-items: flex-start; flex-direction: row; }
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
  .chart-toolbar, .chart-legend { display: none; }
  .chart-series-hidden { display: inline !important; }
  .report-section { padding: 18px; }
  .technical-appendix { border: 0; }
  .technical-appendix > summary { display: none; }
  .technical-appendix:not([open]) > .technical-appendix-body { display: block !important; }
  .technical-appendix-body { padding: 0; }
  .report-disclosure > summary { padding: 18px; cursor: default; }
  .report-disclosure > summary::after { display: none; }
  .report-disclosure:not([open]) > .report-disclosure-body { display: block !important; }
  .report-disclosure-body { padding: 0 18px 18px; }
  .event-details > summary { display: none; }
  .event-details { width: auto; max-width: none; }
  .event-details:not([open]) > dl,
  .event-details:not([open]) > .detail-more { display: block !important; }
  .table-wrap-with-details { overflow: visible; }
  .table-with-details { table-layout: fixed; }
  .table-with-details th { white-space: normal; overflow-wrap: anywhere; }
  .table-with-details td { overflow-wrap: anywhere; }
  .table-detail-row { break-inside: auto; }
  th { position: static; }
  table { font-size: 8.5pt; }
  tr { break-inside: avoid; }
}
"""

import base64
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple
from zoneinfo import ZoneInfo

from app.collection_diagnostics import (
    diagnostic_service_name,
    normalize_collection_issue,
)
from app.renderers.html_styles import HTML_REPORT_STYLES, REPORT_DISPLAY_STYLES
from app.renderers.html_view_models import (
    BillingDisplayData,
    ReportDisplayData,
)
from app.renderers.infrastructure_presenter import (
    merge_server_details,
    resource_connection_summary,
    resource_size_summary,
    server_spec_summary,
)
from app.report_branding import normalize_customer_logo_data_uri
from app.report_analysis.changes import (
    group_activity_events,
    summarize_activity_events,
)
from app.report_analysis.provenance import (
    CALCULATED,
    OBSERVED,
    SOURCE_STATE_LABELS,
    UNAVAILABLE,
    dataset_source_state,
    historical_source_state,
)
from app.report_analysis.support import date_value
from app.report_options import (
    MONITORING_CATEGORY_OPTIONS,
    NETWORK_CONFIGURATION_CATEGORY_OPTIONS,
    RESOURCE_CATEGORY_LABELS,
    UTILIZATION_ALERT_MIN_PERCENT,
)
from app.report_models import ReportResult
from utils.event_sort import event_timestamp_millis, sort_event_records


REPORT_INTERACTION_SCRIPT = r"""(() => {
  const buttonForSeries = (series) => Array.from(
    series.closest(".chart").querySelectorAll("[data-chart-toggle]")
  ).find((button) => button.dataset.chartToggle === series.id);

  const hideChartTooltip = (chart) => {
    const tooltip = chart && chart.querySelector("[data-chart-tooltip]");
    if (tooltip) tooltip.hidden = true;
  };

  const chartPointCache = new WeakMap();
  const chartPoints = (line) => {
    if (chartPointCache.has(line)) return chartPointCache.get(line);
    try {
      const points = JSON.parse(line.dataset.chartPoints || "[]").filter(
        (point) => Array.isArray(point)
          && Number.isFinite(Number(point[0]))
          && Number.isFinite(Number(point[1]))
          && Number.isFinite(Number(point[2]))
      );
      chartPointCache.set(line, points);
      return points;
    } catch (error) {
      chartPointCache.set(line, []);
      return [];
    }
  };

  const exactChartValue = (value, unit) => {
    const number = Number(value);
    const text = Number.isFinite(number)
      ? number.toLocaleString("ko-KR", {maximumFractionDigits: 20})
      : String(value);
    const suffix = String(unit || "").trim();
    if (!suffix) return text;
    return suffix === "%" ? `${text}%` : `${text} ${suffix}`;
  };

  const kstDateTime = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });

  const chartTime = (timestamp) => {
    const parts = Object.fromEntries(
      kstDateTime.formatToParts(new Date(Number(timestamp))).map(
        (part) => [part.type, part.value]
      )
    );
    return `${parts.year}-${parts.month}-${parts.day} `
      + `${parts.hour}:${parts.minute} KST`;
  };

  const showChartTooltip = (line, point, event) => {
    const series = line.closest("[data-chart-series]");
    const chart = line.closest(".chart");
    if (
      !chart
      || !series
      || series.classList.contains("chart-series-hidden")
    ) {
      hideChartTooltip(chart);
      return;
    }
    const tooltip = chart.querySelector("[data-chart-tooltip]");
    if (!tooltip) return;
    const chartBounds = chart.getBoundingClientRect();
    const hasPointer = event && Number.isFinite(Number(event.clientX));
    const x = hasPointer
      ? Number(event.clientX) - chartBounds.left
      : chartBounds.width / 2;
    const y = hasPointer
      ? Number(event.clientY) - chartBounds.top
      : chartBounds.height / 2;
    tooltip.style.left = `${Math.max(8, Math.min(x, chartBounds.width - 8))}px`;
    tooltip.style.top = `${Math.max(8, Math.min(y, chartBounds.height - 8))}px`;
    const translateX = x > chartBounds.width / 2
      ? "calc(-100% - 10px)"
      : "10px";
    const translateY = y < 48 ? "10px" : "calc(-100% - 10px)";
    tooltip.style.transform = `translate(${translateX}, ${translateY})`;
    tooltip.hidden = false;
    tooltip.textContent = [
      line.dataset.chartLabel || "Series",
      chartTime(point[1]),
      exactChartValue(point[2], line.dataset.chartUnit),
    ].join(" · ");
  };

  const nearestChartPoint = (line, event) => {
    const points = chartPoints(line);
    const svg = line.ownerSVGElement;
    if (!points.length || !svg) return null;
    const bounds = svg.getBoundingClientRect();
    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    const width = viewBox && viewBox.width ? viewBox.width : 1000;
    const origin = viewBox && Number.isFinite(viewBox.x) ? viewBox.x : 0;
    const x = origin + (
      (Number(event.clientX) - bounds.left) / Math.max(bounds.width, 1)
      * width
    );
    return points.reduce(
      (nearest, point) => (
        Math.abs(Number(point[0]) - x) < Math.abs(Number(nearest[0]) - x)
          ? point
          : nearest
      ),
      points[0]
    );
  };

  const latestChartPoint = (series) => {
    let latest = null;
    Array.from(series.querySelectorAll("[data-chart-points]")).forEach(
      (line) => chartPoints(line).forEach((point) => {
        if (!latest || Number(point[1]) > Number(latest.point[1])) {
          latest = {line, point};
        }
      })
    );
    return latest;
  };

  const toggleSeries = (button) => {
    const chart = button.closest(".chart");
    const targetSeries = document.getElementById(
      button.dataset.chartToggle || ""
    );
    if (!chart || !targetSeries || !chart.contains(targetSeries)) return;
    const buttons = Array.from(
      chart.querySelectorAll("[data-chart-toggle]")
    );
    const selectedButtons = new Set(
      buttons.filter((item) => item.getAttribute("aria-pressed") === "true")
    );
    if (selectedButtons.has(button)) {
      selectedButtons.delete(button);
    } else {
      selectedButtons.add(button);
    }
    buttons.forEach((item) => {
      const series = document.getElementById(item.dataset.chartToggle || "");
      if (!series || !chart.contains(series)) return;
      const selected = selectedButtons.has(item);
      const visible = selectedButtons.size === 0 || selected;
      item.setAttribute("aria-pressed", String(selected));
      item.classList.toggle("is-muted", !visible);
      series.classList.toggle("chart-series-hidden", !visible);
    });
    hideChartTooltip(chart);
  };

  const appendExportLegend = (chart, copy, viewBox) => {
    const selected = Array.from(
      chart.querySelectorAll("[data-chart-toggle]")
    ).filter(
      (button) => button.getAttribute("aria-pressed") === "true"
    );
    if (!selected.length) return;
    // ponytail: Four labels keep the overlay clear;
    // add export-only space if more are needed.
    const items = selected.slice(0, 4).map((button) => {
      const series = document.getElementById(button.dataset.chartToggle || "");
      const label = button.querySelector("span");
      const labelText = String(
        (label && label.textContent) || button.textContent || "Series"
      ).trim();
      const line = series && series.querySelector(".chart-line");
      return {
        label: labelText.length > 30
          ? `${labelText.slice(0, 14)}…${labelText.slice(-14)}`
          : labelText,
        color: (line && line.getAttribute("stroke")) || "#475569",
      };
    });

    const namespace = "http://www.w3.org/2000/svg";
    const group = document.createElementNS(namespace, "g");
    group.setAttribute("data-chart-export-legend", "");
    const add = (name, attributes, text = "") => {
      const node = document.createElementNS(namespace, name);
      Object.entries(attributes).forEach(
        ([key, value]) => node.setAttribute(key, value)
      );
      node.textContent = text;
      group.appendChild(node);
    };
    const chartWidth = viewBox && viewBox.width ? viewBox.width : 1000;
    const extraCount = selected.length - items.length;
    const rows = items.length + (extraCount ? 1 : 0);
    const legendWidth = 250;
    const startX = Math.max(60, chartWidth - legendWidth - 20);
    add("rect", {
      x: startX,
      y: 10,
      width: legendWidth,
      height: 12 + rows * 18,
      rx: 5,
      fill: "#ffffff",
      "fill-opacity": "0.94",
      stroke: "#cbd5e1",
    });
    items.forEach((item, index) => {
      const x = startX + 10;
      const y = 27 + index * 18;
      add("rect", {
        x,
        y: y - 10,
        width: 9,
        height: 9,
        rx: 2,
        fill: item.color,
      });
      add("text", {
        x: x + 15,
        y,
        fill: "#334155",
        "font-family": "Arial, sans-serif",
        "font-size": "12",
      }, item.label);
    });
    if (extraCount) {
      add("text", {
        x: startX + 10,
        y: 27 + items.length * 18,
        fill: "#64748b",
        "font-family": "Arial, sans-serif",
        "font-size": "11",
      }, `외 ${extraCount}개 선택`);
    }
    copy.appendChild(group);
  };

  const downloadPng = (button) => {
    const chart = button.closest(".chart");
    const svg = chart && chart.querySelector("svg");
    if (!svg) return;
    const size = chart.querySelector("[data-chart-export-width]");
    const requestedWidth = Number(size && size.value);
    const exportWidth = [1000, 2000, 3000].includes(requestedWidth)
      ? requestedWidth
      : 2000;
    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    const aspectRatio = viewBox && viewBox.width
      ? viewBox.height / viewBox.width
      : 0.3;
    const exportHeight = Math.round(exportWidth * aspectRatio);
    button.disabled = true;
    const copy = svg.cloneNode(true);
    copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    copy.setAttribute("width", exportWidth);
    copy.setAttribute("height", exportHeight);
    appendExportLegend(chart, copy, viewBox);
    const source = new XMLSerializer().serializeToString(copy);
    const sourceUrl = URL.createObjectURL(new Blob(
      [source], {type: "image/svg+xml;charset=utf-8"}
    ));
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = exportWidth;
      canvas.height = exportHeight;
      const context = canvas.getContext("2d");
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(sourceUrl);
      const link = document.createElement("a");
      link.href = canvas.toDataURL("image/png");
      link.download = `${chart.id || "monitoring-chart"}.png`;
      link.click();
      button.disabled = false;
    };
    image.onerror = () => {
      URL.revokeObjectURL(sourceUrl);
      button.disabled = false;
    };
    image.src = sourceUrl;
  };

  const prefersReducedChartMotion = Boolean(
    globalThis.matchMedia
    && globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  const chartShiftAnimations = new WeakMap();
  const requestChartFrame = globalThis.requestAnimationFrame
    ? globalThis.requestAnimationFrame.bind(globalThis)
    : (callback) => callback();

  const animateChartShift = (grid, mutation) => {
    const cards = Array.from(grid.children).filter(
      (card) => card.classList
        && card.classList.contains("chart-card")
        && card !== draggedChartCard
    );
    const before = new Map(
      cards.map((card) => [card, card.getBoundingClientRect()])
    );
    cards.forEach((card) => {
      const animation = chartShiftAnimations.get(card);
      if (animation && animation.cancel) animation.cancel();
    });
    mutation();
    if (prefersReducedChartMotion) return;
    cards.forEach((card) => {
      if (!card.animate) return;
      const previous = before.get(card);
      const current = card.getBoundingClientRect();
      const x = previous.left - current.left;
      const y = previous.top - current.top;
      if (Math.abs(x) < 1 && Math.abs(y) < 1) return;
      const animation = card.animate(
        [
          {transform: `translate3d(${x}px, ${y}px, 0)`},
          {transform: "translate3d(0, 0, 0)"},
        ],
        {duration: 220, easing: "cubic-bezier(.22, 1, .36, 1)"}
      );
      chartShiftAnimations.set(card, animation);
      animation.onfinish = () => {
        if (chartShiftAnimations.get(card) === animation) {
          chartShiftAnimations.delete(card);
        }
      };
    });
  };

  const animateChartDrop = (card, previous, current) => {
    if (prefersReducedChartMotion || !card.animate) return;
    const x = previous.left - current.left;
    const y = previous.top - current.top;
    card.animate(
      [
        {
          transform: `translate3d(${x}px, ${y}px, 0) scale(1.012)`,
          opacity: .98,
          boxShadow: "0 24px 54px rgba(15, 23, 42, .24)",
        },
        {
          transform: "translate3d(0, 0, 0) scale(1)",
          opacity: 1,
          boxShadow: "0 0 0 rgba(15, 23, 42, 0)",
        },
      ],
      {duration: 190, easing: "cubic-bezier(.22, 1, .36, 1)"}
    );
  };

  const moveChartCard = (card, direction) => {
    const grid = card && card.parentElement;
    if (!grid || !grid.classList.contains("chart-grid")) return false;
    const sibling = direction === "previous"
      ? card.previousElementSibling
      : card.nextElementSibling;
    if (!sibling || !sibling.classList.contains("chart-card")) return false;
    animateChartShift(grid, () => grid.insertBefore(
      card,
      direction === "previous" ? sibling : sibling.nextElementSibling
    ));
    return true;
  };

  const filterResourceRows = (button) => {
    const section = button.closest(".report-section");
    if (!section) return;
    const buttons = Array.from(
      section.querySelectorAll("[data-resource-filter]")
    );
    const rows = Array.from(
      section.querySelectorAll("[data-resource-category]")
    );
    const requested = button.dataset.resourceFilter || "";
    const active = requested
      && button.getAttribute("aria-pressed") === "true"
      ? ""
      : requested;
    buttons.forEach((item) => {
      const selected = (item.dataset.resourceFilter || "") === active;
      item.setAttribute("aria-pressed", String(selected));
      item.classList.toggle("is-active", selected);
    });
    let visibleCount = 0;
    rows.forEach((row) => {
      const visible = !active || row.dataset.resourceCategory === active;
      row.classList.toggle("resource-filtered-row", !visible);
      if (visible) visibleCount += 1;
    });
    const status = section.querySelector("[data-resource-filter-status]");
    if (!status) return;
    const label = button.querySelector("span");
    status.textContent = active
      ? `${String((label && label.textContent) || active).trim()} `
        + `${visibleCount}건 표시 중 · 다시 누르면 전체 표시`
      : `전체 ${visibleCount}건 표시 중`;
  };

  let pendingChartDrag = null;
  let draggedChartCard = null;
  let chartDropPlaceholder = null;

  const positionDraggedChart = (event) => {
    const state = pendingChartDrag;
    if (!state || !draggedChartCard) return;
    state.latestX = event.clientX;
    state.latestY = event.clientY;
    if (state.framePending) return;
    state.framePending = true;
    requestChartFrame(() => {
      state.framePending = false;
      if (pendingChartDrag !== state || draggedChartCard !== state.card) return;
      const left = state.latestX - state.pointerOffsetX;
      const top = state.latestY - state.pointerOffsetY;
      state.card.style.transform = (
        `translate3d(${left}px, ${top}px, 0) scale(1.012)`
      );
    });
  };

  const beginChartDrag = (event) => {
    const state = pendingChartDrag;
    const card = state.card;
    const bounds = card.getBoundingClientRect();
    const placeholder = document.createElement("div");
    placeholder.classList.add("chart-drop-placeholder");
    placeholder.setAttribute("aria-hidden", "true");
    placeholder.style.height = `${bounds.height}px`;
    state.pointerOffsetX = state.startX - bounds.left;
    state.pointerOffsetY = state.startY - bounds.top;
    state.latestX = event.clientX;
    state.latestY = event.clientY;
    card.style.width = `${bounds.width}px`;
    card.style.height = `${bounds.height}px`;
    card.style.transform = (
      `translate3d(${bounds.left}px, ${bounds.top}px, 0) scale(1.012)`
    );
    card.classList.add("is-dragging");
    state.captureTarget.classList.add("is-chart-dragging");
    state.captureTarget.insertBefore(placeholder, card);
    draggedChartCard = card;
    chartDropPlaceholder = placeholder;
    positionDraggedChart(event);
  };

  const finishChartDrag = (event) => {
    if (
      !pendingChartDrag
      || (
        typeof event.pointerId === "number"
        && event.pointerId !== pendingChartDrag.pointerId
      )
    ) return;
    const {captureTarget, pointerId} = pendingChartDrag;
    pendingChartDrag = null;
    if (
      draggedChartCard
      && chartDropPlaceholder
      && chartDropPlaceholder.parentElement === captureTarget
    ) {
      const previous = draggedChartCard.getBoundingClientRect();
      captureTarget.insertBefore(draggedChartCard, chartDropPlaceholder);
      chartDropPlaceholder.remove();
      draggedChartCard.classList.remove("is-dragging");
      draggedChartCard.style.removeProperty("width");
      draggedChartCard.style.removeProperty("height");
      draggedChartCard.style.removeProperty("transform");
      const current = draggedChartCard.getBoundingClientRect();
      animateChartDrop(draggedChartCard, previous, current);
    } else if (draggedChartCard) {
      draggedChartCard.classList.remove("is-dragging");
      draggedChartCard.style.removeProperty("width");
      draggedChartCard.style.removeProperty("height");
      draggedChartCard.style.removeProperty("transform");
    }
    if (chartDropPlaceholder) chartDropPlaceholder.remove();
    captureTarget.classList.remove("is-chart-dragging");
    draggedChartCard = null;
    chartDropPlaceholder = null;
    if (
      captureTarget.hasPointerCapture
      && captureTarget.hasPointerCapture(pointerId)
    ) captureTarget.releasePointerCapture(pointerId);
  };

  document.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest("[data-chart-drag-handle]");
    const card = handle && handle.closest(".chart-card");
    if (
      pendingChartDrag
      || !card
      || !card.parentElement.classList.contains("chart-grid")
      || event.isPrimary === false
      || (typeof event.button === "number" && event.button !== 0)
    ) return;
    pendingChartDrag = {
      card,
      captureTarget: card.parentElement,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
    };
    if (card.parentElement.setPointerCapture) {
      card.parentElement.setPointerCapture(event.pointerId);
    }
  });

  document.addEventListener("pointermove", (event) => {
    if (
      !pendingChartDrag
      || event.pointerId !== pendingChartDrag.pointerId
    ) return;
    if (!draggedChartCard) {
      const distance = Math.hypot(
        event.clientX - pendingChartDrag.startX,
        event.clientY - pendingChartDrag.startY
      );
      if (distance < 8) return;
      beginChartDrag(event);
    }
    event.preventDefault();
    positionDraggedChart(event);
    const pointed = document.elementFromPoint
      ? document.elementFromPoint(event.clientX, event.clientY)
      : event.target;
    const target = pointed && pointed.closest(".chart-card");
    if (
      !target
      || target === draggedChartCard
      || target.parentElement !== pendingChartDrag.captureTarget
    ) return;
    const bounds = target.getBoundingClientRect();
    const placeholderBounds = chartDropPlaceholder.getBoundingClientRect();
    const sameRow = Math.abs(placeholderBounds.top - bounds.top)
      < Math.min(placeholderBounds.height, bounds.height) / 2;
    const insertBefore = sameRow
      ? event.clientX < bounds.left + bounds.width / 2
      : event.clientY < bounds.top + bounds.height / 2;
    const reference = insertBefore
      ? target
      : target.nextElementSibling;
    if (reference === chartDropPlaceholder) return;
    let currentReference = chartDropPlaceholder.nextElementSibling;
    if (currentReference === draggedChartCard) {
      currentReference = currentReference.nextElementSibling;
    }
    const intendedReference = reference === draggedChartCard
      ? draggedChartCard.nextElementSibling
      : reference;
    if (currentReference === intendedReference) return;
    animateChartShift(
      pendingChartDrag.captureTarget,
      () => pendingChartDrag.captureTarget.insertBefore(
        chartDropPlaceholder,
        reference
      )
    );
  });

  document.addEventListener("pointerup", finishChartDrag);
  document.addEventListener("pointercancel", finishChartDrag);
  document.addEventListener("lostpointercapture", finishChartDrag);

  document.addEventListener("keydown", (event) => {
    const handle = event.target.closest("[data-chart-drag-handle]");
    if (!handle) return;
    const direction = ["ArrowLeft", "ArrowUp"].includes(event.key)
      ? "previous"
      : ["ArrowRight", "ArrowDown"].includes(event.key)
        ? "next"
        : "";
    if (
      direction
      && moveChartCard(handle.closest(".chart-card"), direction)
    ) event.preventDefault();
  });

  if (document.querySelectorAll) {
    document.querySelectorAll("[data-chart-points]").forEach((line) => {
      line.addEventListener("pointermove", (event) => {
        const point = nearestChartPoint(line, event);
        if (point) showChartTooltip(line, point, event);
      });
      line.addEventListener("pointerleave", () => {
        hideChartTooltip(line.closest(".chart"));
      });
    });
  }

  document.addEventListener("focusin", (event) => {
    const button = event.target.closest("[data-chart-toggle]");
    if (!button) return;
    const series = document.getElementById(button.dataset.chartToggle || "");
    const latest = series && latestChartPoint(series);
    if (latest) showChartTooltip(latest.line, latest.point, null);
  });

  document.addEventListener("focusout", (event) => {
    const button = event.target.closest("[data-chart-toggle]");
    if (button) hideChartTooltip(button.closest(".chart"));
  });

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-chart-toggle]");
    if (toggle) {
      toggleSeries(toggle);
      return;
    }
    const series = event.target.closest("[data-chart-series]");
    if (series) {
      const button = buttonForSeries(series);
      if (button) toggleSeries(button);
      return;
    }
    const download = event.target.closest("[data-chart-download]");
    if (download) {
      downloadPng(download);
      return;
    }
    const resourceFilter = event.target.closest("[data-resource-filter]");
    if (resourceFilter) filterResourceRows(resourceFilter);
  });

})();"""
REPORT_INTERACTION_CSP_SOURCE = "'sha256-{}'".format(
    base64.b64encode(
        hashlib.sha256(REPORT_INTERACTION_SCRIPT.encode("utf-8")).digest()
    ).decode("ascii")
)


class HtmlReportRenderer:
    """웹 프레임워크 의존성 없이 독립형 반응형 HTML 보고서를 만든다."""

    KST = ZoneInfo("Asia/Seoul")
    INTERACTION_SCRIPT_CSP_SOURCE = REPORT_INTERACTION_CSP_SOURCE
    MAX_CHART_POINTS_PER_SEGMENT = 600
    CHART_COLORS = (
        "#15803d",
        "#2563eb",
        "#c2410c",
        "#8b5cf6",
        "#0891b2",
        "#dc2626",
        "#65a30d",
        "#db2777",
        "#4f46e5",
        "#0f766e",
        "#a16207",
        "#475569",
    )
    INFRASTRUCTURE_CATEGORIES = tuple(
        RESOURCE_CATEGORY_LABELS.items()
    )

    def render(self, report: ReportResult) -> str:
        display = self._prepare_display_data(report)
        sections = self._render_report_sections(report, display)
        return self._render_document(report, display, sections)

    def render_email_summary(self, report: ReportResult) -> str:
        """메일 본문용 핵심 요약을 외부 자원 없이 렌더링한다."""
        display = self._prepare_display_data(report)
        analysis = self._mapping(report.analysis)
        quality = self._mapping(analysis.get("data_quality"))
        findings = self._active_operational_findings(analysis)
        if analysis:
            status = self._visible_operational_status(findings, quality)
            status_label = {
                "NORMAL": "정상",
                "CAUTION": "확인 필요",
                "RISK": "즉시 대응",
                "UNKNOWN": "판정 불가",
            }[status]
            summary = {
                "NORMAL": "현재 수집·검사 범위에서 활성 운영 경고가 없습니다.",
                "CAUTION": f"확인이 필요한 운영 신호가 {len(findings):,}건 있습니다.",
                "RISK": f"즉시 대응이 필요한 위험 신호가 {len(findings):,}건 있습니다.",
                "UNKNOWN": "일부 데이터가 수집되지 않아 운영 상태를 완전히 판정할 수 없습니다.",
            }[status]
            collection_label = {
                "COMPLETE": "정상",
                "PARTIAL": "일부 누락",
                "FAILED": "실패",
                "UNKNOWN": "판정 불가",
            }.get(str(quality.get("overall_status")), "판정 불가")
        else:
            status = "NORMAL"
            status_label = "생성 완료"
            summary = "NCP 보고서가 생성되었습니다. 아래 핵심 수치와 첨부 보고서를 확인하세요."
            issue_count = len(report.collection_errors) + len(
                report.collection_warnings
            )
            collection_label = "확인 필요" if issue_count else "정상"

        status_color = {
            "NORMAL": "#15803d",
            "CAUTION": "#b45309",
            "RISK": "#dc2626",
            "UNKNOWN": "#64748b",
        }[status]
        priority = findings[0] if findings else None
        priority_html = ""
        if priority:
            resource = self._mapping(priority.get("resource"))
            priority_html = f"""
              <tr><td style="padding:0 28px 24px">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #fed7aa;border-left:5px solid {status_color};border-radius:12px;background:#fffaf0">
                  <tr><td style="padding:18px 20px">
                    <div style="font-size:12px;font-weight:800;color:{status_color};margin-bottom:6px">가장 먼저 확인</div>
                    <div style="font-size:17px;font-weight:800;color:#111827">{self._text(priority.get('title'))}</div>
                    <div style="font-size:13px;color:#64748b;margin:4px 0 12px">{self._text(resource.get('name') or resource.get('id') or '공통')}</div>
                    <div style="font-size:13px;line-height:1.65;color:#374151"><strong>영향</strong> · {self._text(priority.get('impact') or '-')}</div>
                    <div style="font-size:13px;line-height:1.65;color:#1d4ed8"><strong>조치</strong> · {self._text(priority.get('recommendation') or '-')}</div>
                  </td></tr>
                </table>
              </td></tr>"""

        period_text = (
            f"{self._display_period_start(display.period)} ~ "
            f"{self._display_period_end(display.period)}"
        )
        return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;background:#eef2f6;font-family:Pretendard,'Noto Sans KR',Arial,sans-serif;color:#111827">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#eef2f6;padding:24px 12px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:720px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #dbe4ee">
        <tr><td style="padding:18px 28px;border-bottom:1px solid #e5e7eb;font-size:13px;font-weight:800">NCP 운영 리포트</td></tr>
        <tr><td style="padding:32px 28px 24px;background:linear-gradient(135deg,#eff6ff,#ecfdf5)">
          <div style="font-size:12px;font-weight:800;letter-spacing:.08em;color:#047857">NAVER CLOUD PLATFORM</div>
          <h1 style="margin:8px 0 10px;font-size:28px;line-height:1.25;color:#0f172a">{self._text(display.report_title)}</h1>
          <div style="font-size:13px;color:#64748b">{self._text(period_text)}</div>
        </td></tr>
        <tr><td style="padding:26px 28px 14px">
          <h2 style="margin:0 0 6px;font-size:20px">오늘의 요약</h2>
          <p style="margin:0;font-size:14px;line-height:1.7;color:#475569">{self._text(summary)}</p>
        </td></tr>
        <tr><td style="padding:0 22px 24px">
          <table role="presentation" width="100%" cellspacing="6" cellpadding="0"><tr>
            <td width="33%" valign="top" style="padding:15px;border:1px solid #e2e8f0;border-radius:10px"><div style="font-size:11px;color:#64748b">운영 상태</div><div style="margin-top:6px;font-size:17px;font-weight:800;color:{status_color}">{self._text(status_label)}</div></td>
            <td width="33%" valign="top" style="padding:15px;border:1px solid #e2e8f0;border-radius:10px"><div style="font-size:11px;color:#64748b">즉시 확인</div><div style="margin-top:6px;font-size:17px;font-weight:800">{len(findings):,}건</div></td>
            <td width="33%" valign="top" style="padding:15px;border:1px solid #e2e8f0;border-radius:10px"><div style="font-size:11px;color:#64748b">데이터 수집</div><div style="margin-top:6px;font-size:17px;font-weight:800">{self._text(collection_label)}</div></td>
          </tr></table>
        </td></tr>
        {priority_html}
        <tr><td style="padding:18px 28px;background:#f8fafc;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.6;color:#64748b">전체 자원·시계열·이벤트·수집 근거는 첨부된 HTML 보고서에 포함되어 있습니다.</td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""

    def _prepare_display_data(
        self,
        report: ReportResult,
    ) -> ReportDisplayData:
        """보고서 원본과 섹션 옵션을 HTML 표시 모델로 정규화한다.

        각 section option은 여기서 한 번만 판정한다. 이후 조립 단계는 비활성
        섹션을 빈 문자열로 유지하고 저장된 섹션 순서대로 결합한다.
        """
        period = report.period
        report_options = report.selected_report_options
        customer_name = str(report.customer.get("name") or "").strip()
        report_title = (
            f"{customer_name} · NCP 이용 보고서"
            if customer_name
            else "NCP 이용 보고서"
        )
        billing = dict(report.billing or {})
        billing["collection_errors"] = self._records(
            billing.get("collection_errors")
        ) + self._records(report.collection_errors)
        billing_display = self._prepare_billing_display(period, billing)
        activity_events = self._flatten_grouped(report.activity_events)
        infrastructure = report.display_infrastructure
        inventory_enabled = report_options.section_enabled(
            "infrastructure_inventory"
        )
        monitoring_enabled = report_options.section_enabled("monitoring")
        billing_enabled = report_options.section_enabled("billing")
        organization_billing_enabled = report_options.section_enabled(
            "organization_billing"
        )
        collection_metadata = self._mapping(report.collection_metadata)
        network_configuration_metadata = self._mapping(
            collection_metadata.get("network_configuration")
        )
        customer_logo_data_uri = self._safe_customer_logo_data_uri(
            report.customer.get("logo_data_uri")
        )
        return ReportDisplayData(
            period=period,
            report_options=report_options,
            report_title=report_title,
            customer_name=customer_name,
            customer_logo_data_uri=customer_logo_data_uri,
            customer_initials=self._customer_initials(customer_name),
            billing=billing_display,
            activity_events=activity_events,
            infrastructure=infrastructure,
            inventory_enabled=inventory_enabled,
            monitoring_enabled=monitoring_enabled,
            billing_enabled=billing_enabled,
            organization_billing_enabled=organization_billing_enabled,
            network_configuration_metadata=(
                network_configuration_metadata
            ),
        )

    def _prepare_billing_display(
        self,
        period: Dict[str, Any],
        billing: Dict[str, Any],
    ) -> BillingDisplayData:
        """확정 월은 청구액, 진행 중인 기간은 추정액을 표시 기준으로 삼는다.

        미마감 기간에서 기간 추정치가 적용 불가하면 월 누적 추정치를 사용하며,
        금액 basis에 따라 실제 사용액 또는 예상 금액 서비스 집계를 선택한다.
        """
        billing_summary = billing.get("summary", {})
        invoice_summary = self._mapping(billing.get("invoice_summary"))
        period_estimate = self._mapping(billing.get("period_estimate"))
        month_to_date_estimate = self._mapping(
            billing.get("month_to_date_estimate")
        )
        month_end_projection = self._mapping(
            billing.get("month_end_projection")
        )
        cost_facts = [
            {
                **fact,
                "_service_breakdown": self._billing_fact_breakdown(
                    billing,
                    fact,
                ),
            }
            for fact in (
                invoice_summary,
                period_estimate,
                month_to_date_estimate,
                month_end_projection,
            )
            if fact and fact.get("status") != "NOT_APPLICABLE"
        ]
        account_costs = self._records(billing.get("account_costs"))
        confirmed_service_summary = self._records(
            billing.get("service_summary")
        )
        period_usage_rows = self._records(billing.get("daily_usage_rows"))
        month_to_date_usage_rows = self._records(
            billing.get("month_to_date_usage_rows")
        )
        daily_usage_failed = self._billing_source_failed(
            billing,
            "daily_usage",
        )
        month_to_date_usage_summary = self._records(
            billing.get("month_to_date_usage_summary")
        )
        month_to_date_network_summary = self._records(
            billing.get("month_to_date_network_usage_summary")
        )
        month_to_date_reference_available = bool(
            month_to_date_usage_summary
            or month_to_date_network_summary
        )
        delayed_daily_usage = self._use_delayed_month_to_date_usage(
            period=period,
            period_usage_rows=period_usage_rows,
            month_to_date_usage_rows=month_to_date_usage_rows,
            month_to_date_estimate=month_to_date_estimate,
            daily_usage_failed=daily_usage_failed,
        )
        use_month_to_date_usage = (
            delayed_daily_usage and month_to_date_reference_available
        )
        use_estimated_cost = period.get("is_closed_month") is False
        if use_estimated_cost:
            period_estimate_status = period_estimate.get("status")
            month_to_date_service_costs = self._records(
                billing.get("month_to_date_by_service")
            )
            month_to_date_current_costs = self._records(
                billing.get("target_service_summary")
            )
            month_to_date_basis = month_to_date_estimate.get("amount_basis")
            month_to_date_cost_rows_available = bool(
                month_to_date_current_costs
                if month_to_date_basis in {
                    "NCP_PRODUCT_DEMAND_USE_AMOUNT",
                    "NCP_CURRENT_USE_AMOUNT_FALLBACK",
                }
                else month_to_date_service_costs
            )
            use_month_to_date = (
                month_to_date_estimate.get("status") == "AVAILABLE"
                and (
                    period_estimate_status == "NOT_APPLICABLE"
                    or (
                        period_estimate_status == "UNAVAILABLE"
                        and delayed_daily_usage
                        and month_to_date_cost_rows_available
                    )
                )
            )
            if use_month_to_date and month_to_date_estimate.get(
                "amount_basis"
            ) in {
                "NCP_PRODUCT_DEMAND_USE_AMOUNT",
                "NCP_CURRENT_USE_AMOUNT_FALLBACK",
            }:
                service_summary = [
                    {
                        "service_name": row.get("service_name"),
                        "amount": row.get("use_amount"),
                        "row_count": row.get("row_count"),
                    }
                    for row in month_to_date_current_costs
                ]
            elif use_month_to_date:
                service_summary = [
                    {
                        "service_name": row.get("service_name"),
                        "amount": row.get("expected_amount"),
                        "row_count": row.get("row_count"),
                    }
                    for row in month_to_date_service_costs
                ]
            else:
                service_summary = [
                    {
                        "service_name": row.get("service_name"),
                        "amount": row.get("expected_amount"),
                        "row_count": row.get("row_count"),
                    }
                    for row in self._records(billing.get("expected_by_service"))
                ]
            billing_card_title = (
                "보고 기준일까지 누적 추정 비용"
                if use_month_to_date
                else "기간 예상 비용"
            )
            billing_card_amount = (
                month_to_date_estimate.get("total_amount")
                if use_month_to_date
                else period_estimate.get("total_amount")
            )
            if billing_card_amount is None:
                billing_card_amount = billing_summary.get(
                    "expected_total_amount"
                )
            if use_month_to_date:
                billing_section_title = "월 누적 서비스별 예상 비용"
                coverage_text = self._billing_coverage_text(
                    month_to_date_estimate
                )
                if delayed_daily_usage:
                    billing_section_description = (
                        "NCP 일별 사용량 응답이 0건입니다. 실제 사용량 "
                        f"0이거나 아직 반영 전일 수 있어 {coverage_text} "
                        "월 누적 참고 데이터를 표시합니다. 보고 대상일 "
                        "데이터와는 별도 범위입니다."
                    )
                else:
                    billing_section_description = (
                        f"{coverage_text} 월 누적 사용량과 단가로 계산한 "
                        "미확정 예상 비용입니다."
                    )
            else:
                billing_section_title = "서비스별 예상 비용"
                if period_estimate.get("status") == "UNAVAILABLE":
                    billing_card_amount = None
                    billing_section_description = (
                        "getContractUsageListByDaily 수집 오류로 기간 예상 "
                        "비용을 계산할 수 없습니다. 수집 진단을 확인하세요."
                        if daily_usage_failed
                        else "NCP가 선택 기간의 일별 사용량 데이터를 아직 "
                        "반환하지 않아 예상 비용을 계산할 수 없습니다."
                    )
                else:
                    billing_section_description = (
                        "선택한 기간의 사용량과 단가로 계산한 미확정 예상 "
                        "비용입니다. 시간 범위 보고서도 비용 API의 일 단위 "
                        "사용량을 기준으로 합니다."
                    )
        else:
            service_summary = confirmed_service_summary
            billing_card_title = "확정 청구 금액"
            billing_card_amount = invoice_summary.get(
                "total_amount", billing_summary.get("confirmed_total_amount")
            )
            billing_section_title = "서비스별 청구 금액"
            billing_section_description = (
                "NCP 서비스 단위로 집계한 확정 청구 금액입니다."
            )
        if use_month_to_date_usage:
            usage_summary = month_to_date_usage_summary
            network_summary = month_to_date_network_summary
            coverage_start = (
                month_to_date_estimate.get("coverage_start") or "-"
            )
            coverage_end = month_to_date_estimate.get("coverage_end") or "-"
            fallback_description = (
                "NCP 일별 사용량 응답이 0건입니다. 실제 사용량 0이거나 "
                "아직 반영 전일 수 있어 "
                f"{coverage_start} ~ {coverage_end} 월 누적 참고 데이터를 "
                "별도 범위로 표시합니다."
            )
            usage_section_title = "월 누적 서비스별 사용량 (참고)"
            usage_section_description = fallback_description
            network_section_title = "월 누적 네트워크 사용량 (참고)"
            network_section_description = fallback_description
        else:
            empty_usage_description = ""
            if not period_usage_rows:
                empty_usage_description = (
                    "getContractUsageListByDaily 수집 오류로 표시할 수 "
                    "없습니다. 수집 진단을 확인하세요."
                    if daily_usage_failed
                    else "NCP가 선택 기간의 일별 사용량 데이터를 "
                    "반환하지 않았습니다."
                )
            usage_summary = self._records(billing.get("usage_summary"))
            network_summary = self._records(
                billing.get("network_usage_summary")
            )
            usage_section_title = "서비스별 사용량"
            usage_section_description = (
                empty_usage_description
                or "서비스 및 과금 항목별 사용량입니다."
            )
            network_section_title = "네트워크 사용량"
            network_section_description = (
                empty_usage_description
                or "서비스와 전송 방향별 네트워크 사용량입니다."
            )
        return BillingDisplayData(
            cost_facts=cost_facts,
            account_costs=account_costs,
            service_summary=service_summary,
            card_title=billing_card_title,
            card_amount=billing_card_amount,
            section_title=billing_section_title,
            section_description=billing_section_description,
            usage_summary=usage_summary,
            network_summary=network_summary,
            usage_section_title=usage_section_title,
            usage_section_description=usage_section_description,
            network_section_title=network_section_title,
            network_section_description=network_section_description,
        )

    def _use_delayed_month_to_date_usage(
        self,
        *,
        period: Mapping[str, Any],
        period_usage_rows: Sequence[Mapping[str, Any]],
        month_to_date_usage_rows: Sequence[Mapping[str, Any]],
        month_to_date_estimate: Mapping[str, Any],
        daily_usage_failed: bool,
    ) -> bool:
        """객관적인 NCP 일별 반영 지연일 때만 월 누적 표를 대신 쓴다."""
        if (
            period.get("is_closed_month") is not False
            or period.get("period_type") != "day"
            or period_usage_rows
            or not month_to_date_usage_rows
            or daily_usage_failed
            or month_to_date_estimate.get("status") != "AVAILABLE"
        ):
            return False

        report_start = date_value(period.get("start_dt"))
        report_end = date_value(period.get("end_dt"))
        coverage_end = date_value(
            month_to_date_estimate.get("coverage_end")
        )
        calculated_date = date_value(period.get("calculated_at"))
        if (
            not report_start
            or not report_end
            or not coverage_end
            or not calculated_date
        ):
            return False
        report_age_days = (calculated_date - report_start).days
        return (
            report_start == report_end
            and 0 <= report_age_days <= 1
            and (report_start - coverage_end).days == 1
        )

    def _billing_source_failed(
        self,
        billing: Mapping[str, Any],
        source: str,
    ) -> bool:
        expected = str(source).strip().casefold()
        return any(
            str(error.get("source") or error.get("api") or "")
            .strip()
            .casefold()
            == expected
            for error in self._records(billing.get("collection_errors"))
        )

    @staticmethod
    def _billing_coverage_text(fact: Mapping[str, Any]) -> str:
        return (
            f"{fact.get('coverage_start') or '-'} ~ "
            f"{fact.get('coverage_end') or '-'}"
        )

    def _billing_fact_breakdown(
        self,
        billing: Mapping[str, Any],
        fact: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        """카드 금액과 같은 기준의 기존 서비스 집계를 연결한다."""
        total = self._finite_number(fact.get("total_amount"))
        if total is None:
            return []

        cost_type = str(fact.get("cost_type") or "").upper()
        amount_basis = str(fact.get("amount_basis") or "").upper()
        included_statuses = {"OK", "INFERRED"}

        def service_amounts(
            source_key: str,
            amount_key: str,
            *,
            checked: bool = False,
        ) -> Dict[str, Dict[str, Any]]:
            result: Dict[str, Dict[str, Any]] = {}
            for row in self._records(billing.get(source_key)):
                if checked and row.get("calculation_status") not in included_statuses:
                    continue
                amount = self._finite_number(row.get(amount_key))
                if amount is None:
                    continue
                name = str(row.get("service_name") or "서비스 미분류").strip()
                name = name or "서비스 미분류"
                key = "".join(
                    character.casefold()
                    for character in name
                    if character.isalnum()
                ) or "서비스미분류"
                item = result.setdefault(
                    key,
                    {"service_name": name, "amount": 0.0},
                )
                item["amount"] += amount
            return result

        scale_to_total = False
        if cost_type == "CONFIRMED":
            amounts = service_amounts("service_summary", "amount")
        elif amount_basis == "NCP_ACCRUED_PLUS_USAGE_FORECAST":
            amounts = service_amounts("target_service_summary", "use_amount")
            current = service_amounts(
                "month_to_date_cost_summary",
                "expected_amount",
                checked=True,
            )
            projected = service_amounts(
                "projected_cost_summary",
                "expected_amount",
                checked=True,
            )
            accrued_total = sum(item["amount"] for item in amounts.values())
            projected_total = sum(
                item["amount"] for item in projected.values()
            )
            current_total = sum(item["amount"] for item in current.values())
            if not accrued_total:
                amounts = {
                    key: dict(item) for key, item in projected.items()
                }
            elif projected_total > current_total:
                for key in current.keys() | projected.keys():
                    current_amount = current.get(key, {}).get("amount", 0.0)
                    projected_item = projected.get(key, {})
                    projected_amount = projected_item.get("amount", 0.0)
                    item = amounts.setdefault(
                        key,
                        {
                            "service_name": (
                                projected_item.get("service_name")
                                or current.get(key, {}).get("service_name")
                                or "서비스 미분류"
                            ),
                            "amount": 0.0,
                        },
                    )
                    item["amount"] += projected_amount - current_amount
        elif amount_basis == "NCP_CONTRACT_DEMAND_USE_AMOUNT":
            amounts = service_amounts("contract_cost_summary", "use_amount")
        elif amount_basis in {
            "NCP_PRODUCT_DEMAND_USE_AMOUNT",
            "NCP_CURRENT_USE_AMOUNT_FALLBACK",
            "NCP_ACCRUED_LOWER_BOUND",
        }:
            amounts = service_amounts("target_service_summary", "use_amount")
        elif cost_type == "PERIOD_ESTIMATE":
            amounts = service_amounts("expected_by_service", "expected_amount")
        elif cost_type == "MONTH_TO_DATE_ESTIMATE":
            amounts = service_amounts(
                "month_to_date_by_service",
                "expected_amount",
            )
        elif cost_type == "MONTH_END_PROJECTION":
            amounts = service_amounts(
                "projected_cost_summary",
                "expected_amount",
                checked=True,
            )
            if not amounts:
                month_to_date_basis = str(
                    self._mapping(billing.get("month_to_date_estimate")).get(
                        "amount_basis"
                    ) or ""
                ).upper()
                if month_to_date_basis == "NCP_CONTRACT_DEMAND_USE_AMOUNT":
                    amounts = service_amounts(
                        "contract_cost_summary",
                        "use_amount",
                    )
                elif month_to_date_basis in {
                    "NCP_PRODUCT_DEMAND_USE_AMOUNT",
                    "NCP_CURRENT_USE_AMOUNT_FALLBACK",
                }:
                    amounts = service_amounts(
                        "target_service_summary",
                        "use_amount",
                    )
                else:
                    amounts = service_amounts(
                        "month_to_date_by_service",
                        "expected_amount",
                    )
                scale_to_total = True
        else:
            amounts = {}

        if not amounts:
            return []
        source_total = sum(item["amount"] for item in amounts.values())
        if scale_to_total:
            if not source_total:
                return []
            factor = total / source_total
            for item in amounts.values():
                item["amount"] *= factor

        rows = sorted(
            (
                {
                    "service_name": item["service_name"],
                    "amount": round(item["amount"], 2),
                }
                for item in amounts.values()
            ),
            key=lambda item: (
                -abs(item["amount"]),
                str(item["service_name"]).casefold(),
            ),
        )
        if not rows:
            return []

        if cost_type == "CONFIRMED":
            subtotal = self._finite_number(fact.get("subtotal_amount"))
            vat = self._finite_number(fact.get("vat_amount"))
            service_total = sum(row["amount"] for row in rows)
            if subtotal is not None:
                subtotal_adjustment = round(subtotal - service_total, 2)
                if abs(subtotal_adjustment) >= 0.01:
                    rows.append({
                        "service_name": "공급가액 조정",
                        "amount": subtotal_adjustment,
                        "is_adjustment": True,
                    })
            if vat is not None and abs(vat) >= 0.01:
                rows.append({
                    "service_name": "VAT",
                    "amount": round(vat, 2),
                    "is_adjustment": True,
                })

        difference = round(total - sum(row["amount"] for row in rows), 2)
        if abs(difference) >= 0.01:
            rows.append({
                "service_name": (
                    "최종 청구 조정"
                    if cost_type == "CONFIRMED"
                    else "누적·예측 금액 보정"
                ),
                "amount": difference,
                "is_adjustment": True,
            })
        return rows

    def _report_period_cost_fact(
        self,
        period: Mapping[str, Any],
        facts: Sequence[Mapping[str, Any]],
        preferred_names: Sequence[str],
    ) -> Mapping[str, Any]:
        """보고서 대상 기간과 정확히 일치하는 비용 사실만 요약에 사용한다."""
        report_start = date_value(
            period.get("use_start_date") or period.get("start_dt")
        )
        report_end = date_value(
            period.get("use_end_date") or period.get("end_dt")
        )
        if report_start is None or report_end is None:
            return {}
        return next((
            fact
            for name in preferred_names
            for fact in facts
            if fact.get("name") == name
            and date_value(fact.get("period_start")) == report_start
            and date_value(fact.get("period_end")) == report_end
        ), {})

    @staticmethod
    def _operational_cost_label(fact: Mapping[str, Any]) -> str:
        label = {
            "invoice_summary": "확정 청구 금액",
            "period_estimate": "보고 기간 추정 금액",
            "month_to_date_estimate": "월 누적 추정 금액",
            "month_end_projection": "월말 추정 금액",
        }.get(str(fact.get("name") or ""), "보고 기간 비용")
        start = fact.get("period_start")
        end = fact.get("period_end")
        if start or end:
            return f"{label} · {start or '-'}~{end or '-'}"
        return label

    @staticmethod
    def _source_state_text(value: Any) -> str:
        status = str(value or UNAVAILABLE).strip().upper()
        label = SOURCE_STATE_LABELS.get(status, "미확인")
        return f"{status} ({label})"

    @staticmethod
    def _comparison_period_text(
        comparison: Mapping[str, Any], prefix: str
    ) -> str:
        period_start = comparison.get(f"{prefix}_period_start")
        period_end = comparison.get(f"{prefix}_period_end")
        coverage_start = comparison.get(f"{prefix}_coverage_start")
        coverage_end = comparison.get(f"{prefix}_coverage_end")
        if not any((period_start, period_end, coverage_start, coverage_end)):
            return "-"
        return (
            f"대상 {period_start or '-'} ~ {period_end or '-'} · "
            f"수집 {coverage_start or '-'} ~ {coverage_end or '-'}"
        )

    def _render_summary_section(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> str:
        report_options = display.report_options
        if report_options.section_enabled("executive_summary"):
            # 분석이 포함된 새 보고서는 기존 요약 카드를 대체한다.
            if report.analysis:
                return self._render_operational_analysis(
                    report,
                    cost_enabled=(
                        display.billing_enabled
                        or display.organization_billing_enabled
                    ),
                    billing_detail_enabled=display.billing_enabled,
                )
            diagnostic_count = (
                len(report.collection_errors)
                + len(report.collection_warnings)
            )
            summary_cards = []
            if display.inventory_enabled:
                summary_cards.append(
                    self._summary_card(
                        "자원",
                        len(display.infrastructure),
                        "개",
                    )
                )
            if report_options.section_enabled("insight_events"):
                summary_cards.append(
                    self._summary_card(
                        "Cloud Insight 이벤트",
                        len(report.insight_events),
                        "건",
                    )
                )
            if report_options.section_enabled("collection_diagnostics"):
                summary_cards.append(
                    self._summary_card(
                        "수집 진단",
                        diagnostic_count,
                        "건",
                        warning=bool(diagnostic_count),
                    )
                )
            if (
                display.billing_enabled
                or display.organization_billing_enabled
            ):
                billing_card_available = (
                    display.billing.card_amount is not None
                    and display.billing.card_amount != ""
                )
                summary_cards.append(
                    self._summary_card(
                        display.billing.card_title,
                        (
                            self._number(
                                display.billing.card_amount,
                                decimals=0,
                            )
                            if billing_card_available
                            else "조회 불가"
                        ),
                        "원" if billing_card_available else "",
                    )
                )
            event_count = len(report.insight_events)
            if diagnostic_count:
                summary_text = (
                    f"수집 진단이 {diagnostic_count:,}건 있습니다. "
                    "데이터 누락과 필요한 권한을 먼저 확인하세요."
                )
            elif event_count:
                summary_text = (
                    f"Cloud Insight 이벤트가 {event_count:,}건 수집되었습니다. "
                    "영향 범위는 접힌 이벤트 상세에서 확인할 수 있습니다."
                )
            else:
                summary_text = (
                    "보고 기간의 핵심 자원·비용·수집 결과를 요약했습니다. "
                    "필요한 기술 상세만 펼쳐 확인하세요."
                )
            return "".join((
                '<section class="operational-overview legacy-overview" '
                'aria-label="핵심 요약">',
                '<section class="daily-summary">',
                '<div class="summary-heading">',
                '<p class="section-eyebrow">REPORT BRIEF</p>',
                '<h2>오늘의 요약</h2>',
                '<p>핵심 수치를 먼저 확인하세요.</p>',
                '</div>',
                f'<p class="summary-narrative">{self._text(summary_text)}</p>',
                '<section class="summary-grid" aria-label="주요 요약">',
                "".join(summary_cards),
                '</section>',
                '<p class="legacy-summary-note">이전 형식 보고서에는 운영 위험 판정이 포함되지 않습니다.</p>',
                '</section>',
                '</section>',
            ))
        return ""

    def _render_operational_analysis(
        self,
        report: ReportResult,
        *,
        cost_enabled: bool,
        billing_detail_enabled: bool,
    ) -> str:
        analysis = self._mapping(report.analysis)
        if not analysis:
            return ""
        quality = self._mapping(analysis.get("data_quality"))
        datasets = self._records(quality.get("datasets"))
        active_findings = self._active_operational_findings(analysis)
        findings = active_findings[:5]
        costs = self._mapping(analysis.get("costs"))
        availability = self._mapping(analysis.get("availability"))
        status = self._visible_operational_status(active_findings, quality)
        status_label = {
            "NORMAL": "수집·검사 범위 내 정상",
            "CAUTION": "주의",
            "RISK": "위험",
            "UNKNOWN": "판정 불가",
        }[status]
        requested_datasets = [
            item for item in datasets
            if item.get("status") != "NOT_REQUESTED"
        ]
        completed_datasets = [
            item for item in requested_datasets
            if item.get("status") in {"AVAILABLE", "COLLECTED_EMPTY"}
        ]
        collection_label = {
            "COMPLETE": "정상",
            "PARTIAL": "일부 누락",
            "FAILED": "실패",
            "UNKNOWN": "판정 불가",
        }.get(str(quality.get("overall_status")), "판정 불가")
        if requested_datasets:
            collection_label += (
                f" · {len(completed_datasets)}/{len(requested_datasets)}"
            )

        cost_facts = self._records(costs.get("facts"))
        preferred_cost_names = (
            (
                "invoice_summary",
                "period_estimate",
                "month_to_date_estimate",
                "month_end_projection",
            )
            if analysis.get("period_type") == "MONTHLY"
            else (
                "period_estimate",
                "month_to_date_estimate",
                "month_end_projection",
                "invoice_summary",
            )
        )
        current_cost = self._report_period_cost_fact(
            report.period,
            cost_facts,
            preferred_cost_names,
        )
        resource_changes = self._mapping(analysis.get("resource_changes"))
        immediate_status = self._analysis_finding_status(active_findings)
        assessment_detail = self._operational_assessment_detail(
            status,
            active_findings,
            datasets,
        )
        immediate_detail = (
            '<div class="finding-list">'
            + "".join(self._finding_card(item) for item in active_findings)
            + '</div>'
            if active_findings
            else (
                '<p class="status-evidence-copy">현재 수집·검사 범위에서 '
                '활성 운영 경고가 없습니다.</p>'
            )
        )
        status_cards = "".join((
            self._analysis_status_card(
                "클라우드 운영 판정",
                status_label,
                status.casefold(),
                analysis.get("source_state", CALCULATED),
                details_html=assessment_detail,
            ),
            self._analysis_status_card(
                "즉시 확인",
                f"{len(active_findings)}건",
                immediate_status,
                CALCULATED,
                details_html=immediate_detail,
            ),
            self._analysis_status_card(
                "데이터 수집",
                collection_label,
                str(quality.get("overall_status") or "unknown").casefold(),
                quality.get("source_state", CALCULATED),
                details_html=self._collection_status_detail(datasets),
            ),
        ))
        if (
            resource_changes
            and analysis.get("period_type") == "MONTHLY"
            and resource_changes.get("reason_code")
            != "INFRASTRUCTURE_NOT_REQUESTED"
        ):
            if resource_changes.get("status") == "AVAILABLE":
                resource_change_label = (
                    f"생성 {int(resource_changes.get('created_count') or 0)} · "
                    f"제거 {int(resource_changes.get('removed_count') or 0)} · "
                    "스펙 변경 "
                    f"{int(resource_changes.get('spec_changed_count') or 0)}"
                )
            elif resource_changes.get("status") == "NOT_REQUESTED":
                resource_change_label = "비교 대상 없음"
            else:
                resource_change_label = "비교 불가"
            status_cards += self._analysis_status_card(
                "전월 대비 자원",
                resource_change_label,
                (
                    "normal"
                    if resource_changes.get("status") == "AVAILABLE"
                    else "unknown"
                ),
                resource_changes.get("source_state", UNAVAILABLE),
            )

        availability_value = availability.get(
            "overall_availability_percent"
        )
        quick_facts = [
            self._analysis_quick_fact(
                "서비스 가용률",
                (
                    f"{self._number(availability_value, 2)}%"
                    if availability_value is not None
                    else "조회 불가"
                ),
                availability.get("source_state", UNAVAILABLE),
                details_html=self._availability_status_detail(
                    availability,
                    datasets,
                ),
            )
        ]
        if cost_enabled:
            quick_facts.append(
                self._analysis_quick_fact(
                    self._operational_cost_label(current_cost),
                    (
                        f"{self._number(current_cost.get('total_amount'), 0)}원"
                        if current_cost.get("total_amount") is not None
                        else "조회 불가"
                    ),
                    current_cost.get("source_state", UNAVAILABLE),
                    details_html=self._cost_status_detail(
                        current_cost,
                        show_billing_link=billing_detail_enabled,
                    ),
                )
            )

        finding_content = (
            '<div class="finding-list">'
            + self._finding_card(findings[0], priority=True)
            + "".join(self._finding_card(item) for item in findings[1:])
            + "</div>"
            if findings
            else '<p class="empty-state">활성 경고가 없습니다. 단, 수집 불가 데이터는 정상으로 판정하지 않습니다.</p>'
        )

        summary_text = {
            "RISK": (
                f"현재 수집 범위에서 즉시 대응이 필요한 위험 신호가 "
                f"{len(active_findings):,}건 있습니다."
            ),
            "CAUTION": (
                f"현재 수집 범위에서 확인이 필요한 운영 신호가 "
                f"{len(active_findings):,}건 있습니다."
            ),
            "NORMAL": (
                "현재 수집·검사 범위에서 활성 운영 경고가 없습니다."
            ),
            "UNKNOWN": (
                "일부 데이터가 수집되지 않아 운영 상태를 완전히 판정할 수 없습니다."
            ),
        }[status]
        technical_details = self._render_operational_detail_sections(
            analysis,
            datasets=datasets,
            cost_enabled=cost_enabled,
        )
        period_type = analysis.get("period_type")
        if period_type == "MONTHLY":
            brief_eyebrow, brief_title = "MONTHLY BRIEF", "이번 달 요약"
        elif period_type == "WEEKLY":
            brief_eyebrow, brief_title = "WEEKLY BRIEF", "이번 주 요약"
        else:
            brief_eyebrow, brief_title = "DAILY BRIEF", "오늘의 요약"

        return "".join((
            '<section class="operational-overview" aria-label="운영 판단 요약">',
            '<section class="daily-summary">',
            '<div class="summary-heading">',
            f'<p class="section-eyebrow">{brief_eyebrow}</p>',
            f'<h2>{brief_title}</h2>',
            '<p>현재 상태와 우선 조치를 먼저 확인하세요.</p>',
            '</div>',
            f'<p class="summary-narrative">{self._text(summary_text)}</p>',
            f'<div class="operational-status-grid">{status_cards}</div>',
            f'<div class="summary-facts">{"".join(quick_facts)}</div>',
            '</section>',
            self._section(
                "우선 확인 및 조치",
                "위험도 순으로 최대 5건만 표시합니다. 원시 근거와 전체 수집 상태는 아래 기술 부록에서 확인할 수 있습니다.",
                finding_content,
                len(findings),
                warning=bool(findings),
            ),
            '<details class="technical-appendix">',
            '<summary><span class="technical-appendix-copy">'
            '<span class="technical-appendix-title">운영 근거 및 기술 상세</span>'
            '<small>자원 변화·수집 상태·임계치·가용성·보안·비용 비교</small>'
            '</span></summary>',
            f'<div class="technical-appendix-body">{technical_details}</div>',
            '</details>',
            "</section>",
        ))

    def _active_operational_findings(
        self,
        analysis: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        findings = self._records(analysis.get("findings"))
        if not findings:
            # 초기 1.0 분석 스냅샷은 key_findings만 저장할 수 있다.
            findings = self._records(analysis.get("key_findings"))
        return [
            finding
            for finding in findings
            if self._is_visible_operational_finding(finding)
        ]

    def _analysis_quick_fact(
        self,
        label: str,
        value: Any,
        source_state: Any,
        *,
        details_html: str = "",
    ) -> str:
        content = (
            f'<span>{self._text(label)}</span>'
            f'<strong>{self._text(value)}</strong>'
            f'<small>{self._text(self._source_state_text(source_state))}</small>'
        )
        if details_html:
            return (
                '<details class="summary-fact summary-fact-disclosure">'
                f'<summary>{content}<span class="status-card-action">'
                '<span class="disclosure-action-open">근거 보기</span>'
                '<span class="disclosure-action-close">접기</span>'
                '</span></summary>'
                f'<div class="status-card-detail">{details_html}</div>'
                '</details>'
            )
        return (
            '<div class="summary-fact">'
            f'{content}'
            '</div>'
        )

    def _operational_assessment_detail(
        self,
        status: str,
        findings: Sequence[Mapping[str, Any]],
        datasets: Sequence[Mapping[str, Any]],
    ) -> str:
        requested = [
            item for item in datasets
            if item.get("status") != "NOT_REQUESTED"
        ]
        completed = [
            item for item in requested
            if item.get("status") in {"AVAILABLE", "COLLECTED_EMPTY"}
        ]
        if status == "NORMAL" and requested:
            reason = (
                f"요청 데이터셋 {len(requested):,}개 중 {len(completed):,}개가 "
                "수집 완료되었고, 현재 규칙에 해당하는 활성 운영 경고가 없습니다."
            )
        elif status == "NORMAL":
            reason = (
                "저장된 분석 결과가 전체 수집 상태를 정상으로 기록했고, "
                "현재 규칙에 해당하는 활성 운영 경고가 없습니다."
            )
        elif status in {"RISK", "CAUTION"}:
            reason = (
                f"활성 운영 경고 {len(findings):,}건의 최고 위험도를 기준으로 "
                "판정했습니다. 즉시 확인 카드에서 대상·근거·조치를 확인하십시오."
            )
        elif requested:
            reason = (
                f"요청 데이터셋 {len(requested):,}개 중 {len(completed):,}개만 "
                "완료되어 정상 여부를 확정하지 않았습니다."
            )
        else:
            reason = (
                "데이터셋별 수집 상태가 기록되지 않아 정상 여부를 확정하지 않았습니다."
            )
        return (
            '<p class="status-evidence-copy">'
            f'{self._text(reason)} '
            "이 판정은 보고서에 수집되고 규칙으로 검사된 범위에 한정됩니다."
            '</p>'
        )

    def _collection_status_detail(
        self,
        datasets: Sequence[Mapping[str, Any]],
    ) -> str:
        if not datasets:
            return (
                '<p class="status-evidence-copy">데이터셋별 수집 상태가 기록되지 않아 '
                '완료·누락 항목을 구분할 수 없습니다.</p>'
            )
        items = []
        for item in datasets:
            counts = []
            if item.get("record_count") is not None:
                counts.append(
                    f"레코드 {self._number(item.get('record_count'), 0)}건"
                )
            if item.get("error_count"):
                counts.append(
                    f"오류 {self._number(item.get('error_count'), 0)}건"
                )
            if item.get("warning_count"):
                counts.append(
                    f"경고 {self._number(item.get('warning_count'), 0)}건"
                )
            metadata = " · ".join(counts) or "건수 정보 없음"
            items.append(
                '<li><details class="collection-status-item"><summary>'
                '<span class="collection-status-heading"><strong>'
                f"{self._text(item.get('label') or item.get('key') or '데이터셋')}"
                '</strong><span>'
                f"{self._text(item.get('status_label') or item.get('status') or '판정 불가')}"
                '</span></span><small>'
                f"{self._text(metadata)}"
                '</small><span class="collection-detail-action">'
                '<span class="disclosure-action-open">상세 보기</span>'
                '<span class="disclosure-action-close">접기</span>'
                '</span></summary><p class="collection-status-reason">'
                f"{self._text(item.get('reason') or '판정 근거 없음')}"
                '</p></details></li>'
            )
        return '<ul class="status-evidence-list">' + "".join(items) + '</ul>'

    def _availability_status_detail(
        self,
        availability: Mapping[str, Any],
        datasets: Sequence[Mapping[str, Any]],
    ) -> str:
        rows = [
            {
                **item,
                "source_state_text": self._source_state_text(
                    item.get("source_state")
                ),
            }
            for item in self._records(availability.get("items"))
        ]
        if rows:
            return self._table(
                rows,
                (
                    ("name", "시나리오"),
                    ("source_state_text", "출처 상태"),
                    ("availability_percent", "가용률(%)", "number2"),
                    ("total_count", "전체 실행", "number0"),
                    ("success_count", "성공", "number0"),
                    ("error_count", "오류", "number0"),
                ),
            )
        dataset = next(
            (
                item for item in datasets
                if item.get("key") == "service_availability"
                or item.get("label") == "서비스 가용성"
            ),
            {},
        )
        return (
            '<p class="status-evidence-copy">'
            f"{self._text(dataset.get('status_label') or availability.get('status') or '조회 불가')}"
            f" · {self._text(dataset.get('reason') or '수집된 WMS 시나리오가 없습니다.')}"
            '</p>'
        )

    def _cost_status_detail(
        self,
        fact: Mapping[str, Any],
        *,
        show_billing_link: bool,
    ) -> str:
        period_start = fact.get("period_start") or fact.get("coverage_start")
        period_end = fact.get("period_end") or fact.get("coverage_end")
        billing_link = (
            '<p class="status-evidence-copy">'
            '<a href="#billing-cost-basis">과금 데이터 기준과 서비스별 비용 상세로 이동</a>'
            '</p>'
            if show_billing_link else ""
        )
        return (
            '<dl class="status-evidence-dl">'
            '<div><dt>선택 기준</dt><dd>'
            f"{self._text(self._operational_cost_label(fact))}</dd></div>"
            '<div><dt>대상 기간</dt><dd>'
            f"{self._text(period_start or '-')} ~ {self._text(period_end or '-')}</dd></div>"
            '<div><dt>금액 기준</dt><dd>'
            f"{self._text(fact.get('amount_basis') or '-')}</dd></div>"
            '</dl>'
            f'{billing_link}'
        )

    def _render_operational_detail_sections(
        self,
        analysis: Mapping[str, Any],
        *,
        datasets: List[Dict[str, Any]],
        cost_enabled: bool,
    ) -> str:
        metrics = self._mapping(analysis.get("metrics"))
        costs = self._mapping(analysis.get("costs"))
        availability = self._mapping(analysis.get("availability"))
        security = self._mapping(analysis.get("security"))
        resource_changes = self._mapping(analysis.get("resource_changes"))
        dataset_rows = [
            {
                "label": item.get("label"),
                "status": item.get("status_label") or item.get("status"),
                "record_count": item.get("record_count"),
                "error_count": item.get("error_count"),
                "warning_count": item.get("warning_count"),
                "reason": item.get("reason"),
                "source_state_text": self._source_state_text(
                    item.get("source_state")
                ),
            }
            for item in datasets
        ]
        metric_alert_rows = sorted(
            [
                item
                for item in self._records(metrics.get("summaries"))
                if self._is_utilization_alert_summary(item)
            ],
            key=lambda item: (
                item.get("alert_severity") == "CRITICAL",
                float(item.get("maximum") or -1),
            ),
            reverse=True,
        )
        metric_alert_count = len(metric_alert_rows)
        metric_rows = [
            {
                **item,
                "alert_severity_label": (
                    "위험"
                    if item.get("alert_severity") == "CRITICAL"
                    else "주의"
                ),
                "alert_duration_seconds": (
                    item.get("alert_duration_seconds")
                    or item.get("warning_duration_seconds")
                ),
                "source_state_text": self._source_state_text(
                    item.get("source_state")
                ),
            }
            for item in metric_alert_rows[:10]
        ]
        comparison = self._mapping(costs.get("comparison"))
        comparison_rows = [{
            **comparison,
            "source_state_text": self._source_state_text(
                comparison.get("source_state")
            ),
            "current_period_display": self._comparison_period_text(
                comparison, "current"
            ),
            "baseline_period_display": self._comparison_period_text(
                comparison, "baseline"
            ),
        }] if comparison else []
        scenario_rows = [
            {
                **item,
                "source_state_text": self._source_state_text(
                    item.get("source_state")
                ),
            }
            for item in self._records(availability.get("items"))
        ]
        security_rows = [
            {
                **item,
                "source_state_text": self._source_state_text(
                    item.get("source_state")
                ),
            }
            for item in self._records(security.get("items"))[:50]
        ]
        change_labels = {
            "CREATED": ("생성", "created"),
            "REMOVED": ("제거", "removed"),
            "SPEC_CHANGED": ("스펙 변경", "spec-changed"),
        }
        resource_change_rows = []
        for item in self._records(resource_changes.get("items")):
            change_type = str(item.get("change_type") or "").upper()
            label, style = change_labels.get(
                change_type,
                (change_type or "-", "unknown"),
            )
            resource_change_rows.append({
                **item,
                "change_badge": (
                    f'<span class="change-badge {style}">'
                    f"{self._text(label)}</span>"
                ),
                "resource_name_html": (
                    '<strong class="resource-change-name">'
                    f"{self._text(item.get('resource_name') or '-')}</strong>"
                ),
                "change_detail": self._resource_change_detail(
                    item.get("changed_fields"),
                    change_type,
                ),
            })
        resource_change_status = str(
            resource_changes.get("status") or ""
        ).upper()
        raw_lifecycle_only = resource_changes.get(
            "lifecycle_only_categories"
        )
        lifecycle_only_labels = (
            [
                RESOURCE_CATEGORY_LABELS.get(
                    str(category).strip().upper(),
                    str(category).strip(),
                )
                for category in raw_lifecycle_only
                if isinstance(category, str) and category.strip()
            ]
            if isinstance(raw_lifecycle_only, (list, tuple, set))
            else []
        )
        resource_change_description = (
            "생성·제거는 선택한 전체 자원, 스펙 변경은 수집 API가 "
            "비교 필드를 제공하는 자원을 비교 대상으로 합니다."
        )
        if lifecycle_only_labels:
            resource_change_description += (
                " 스펙 변경 비교 제외: "
                + ", ".join(lifecycle_only_labels)
                + "."
            )
        show_resource_changes = (
            bool(resource_changes)
            and resource_change_status != "NOT_APPLICABLE"
            and resource_changes.get("reason_code")
            != "INFRASTRUCTURE_NOT_REQUESTED"
        )
        if resource_change_status == "AVAILABLE":
            resource_change_content = (
                self._table(
                    resource_change_rows,
                    (
                        ("change_badge", "구분", "html"),
                        ("category_label", "자원 유형"),
                        ("resource_name_html", "자원", "html"),
                        ("platform", "플랫폼"),
                        ("change_detail", "변경 내용"),
                    ),
                )
                if resource_change_rows
                else '<p class="empty-state">직전 월 대비 변경된 자원이 없습니다.</p>'
            )
            resource_change_count: int | None = len(resource_change_rows)
        else:
            resource_change_content = (
                f'<p class="empty-state">'
                f"{self._text(resource_changes.get('message') or '비교할 수 없습니다.')}</p>"
            )
            resource_change_count = None
        resource_change_section = (
            self._section(
                "전월 대비 자원 변화",
                resource_change_description,
                resource_change_content,
                resource_change_count,
            )
            if show_resource_changes
            else ""
        )
        return "".join((
            resource_change_section,
            self._section(
                "데이터 수집 상태",
                "수집 완료 0건과 미수집·권한 부족·실패를 분리합니다.",
                self._table(
                    dataset_rows,
                    (
                        ("label", "데이터셋"),
                        ("status", "상태"),
                        ("source_state_text", "출처 상태"),
                        ("record_count", "레코드", "number0"),
                        ("error_count", "오류", "number0"),
                        ("warning_count", "경고", "number0"),
                        ("reason", "판정 근거"),
                    ),
                ),
                len(dataset_rows),
            ),
            self._section(
                "90% 이상 지속 사용 자원",
                "CPU·메모리·스토리지 실제 사용률의 평균(AVG) 또는 최소(MIN) 집계가 90% 이상으로 지속된 자원 중 위험도와 최대 사용률 기준 상위 10건을 표시합니다. 우측 건수는 전체 알람 수이며, 순간 최댓값·할당 용량·암호화·태그 정책은 포함하지 않습니다.",
                self._table(
                    metric_rows,
                    (
                        ("alert_severity_label", "상태"),
                        ("category", "상품"),
                        ("resource_name", "자원"),
                        ("metric_label", "지표"),
                        ("aggregation", "집계"),
                        ("source_state_text", "출처 상태"),
                        ("average", "평균", "number2"),
                        ("p95", "P95", "number2"),
                        ("maximum", "최대", "number2"),
                        ("alert_duration_seconds", "90% 이상 지속(초)", "number0"),
                    ),
                ),
                metric_alert_count,
            ) if metric_rows else "",
            self._section(
                "서비스 가용성(WMS)",
                "가용률과 평균 응답시간입니다. 집계 버킷 통계이며 개별 요청 p95로 해석하지 않습니다.",
                self._table(
                    scenario_rows,
                    (
                        ("name", "시나리오"),
                        ("source_state_text", "출처 상태"),
                        ("availability_percent", "가용률(%)", "number2"),
                        ("avg_load_time_ms", "평균 로드(ms)", "number2"),
                        ("avg_run_time_ms", "평균 실행(ms)", "number2"),
                        ("success_count", "성공", "number0"),
                        ("error_count", "오류", "number0"),
                    ),
                ),
                len(scenario_rows),
            ) if scenario_rows else "",
            self._section(
                "Security Monitoring(VPC)",
                "AV·DDoS·IDS·IPS·WAF 탐지 결과입니다. 미수집은 보안 정상으로 표시하지 않습니다.",
                self._table(
                    security_rows,
                    (
                        ("service", "상품"),
                        ("source_state_text", "출처 상태"),
                        ("detected_at_kst", "탐지 시각"),
                        ("event_name", "이벤트"),
                        ("attack_type", "유형"),
                        ("action_status", "조치"),
                        ("target", "대상"),
                    ),
                ),
                len(security_rows),
                warning=bool(security_rows),
            ) if security_rows else "",
            self._section(
                "비용 전기 비교",
                "현재 보고 기간과 직전 동일 기간의 비용을 같은 기준·신뢰도·할인·VAT 범위일 때만 비교합니다.",
                self._table(
                    comparison_rows,
                    (
                        ("status", "비교 상태"),
                        ("source_state_text", "출처 상태"),
                        ("current_period_display", "현재 대상·수집 기간"),
                        ("baseline_period_display", "이전 대상·수집 기간"),
                        ("current_amount", "현재 금액", "number0"),
                        ("baseline_amount", "이전 금액", "number0"),
                        ("amount_change", "증감액", "number0"),
                        ("rate_change", "증감률(%)", "number2"),
                        ("amount_basis", "금액 기준"),
                        ("reason", "근거"),
                    ),
                ),
                len(comparison_rows),
            ) if cost_enabled else "",
        ))

    def _resource_change_detail(
        self,
        changed_fields: Any,
        change_type: str,
    ) -> str:
        if change_type == "CREATED":
            return "신규 생성"
        if change_type == "REMOVED":
            return "제거됨"

        parts = []
        for item in self._records(changed_fields):
            label = str(item.get("label") or item.get("field") or "스펙")
            values = []
            for key in ("before", "after"):
                value = item.get(key)
                if isinstance(value, (dict, list)):
                    rendered = json.dumps(
                        value,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                else:
                    rendered = "-" if value is None else str(value)
                values.append(rendered)
            parts.append(f"{label}: {values[0]} → {values[1]}")
        return ", ".join(parts) or "-"

    def _analysis_status_card(
        self,
        label: str,
        value: Any,
        status: str,
        source_state: Any = UNAVAILABLE,
        *,
        details_html: str = "",
    ) -> str:
        safe_status = status if status in {
            "normal", "caution", "risk", "unknown", "complete", "partial",
            "failed", "generation-success",
        } else "unknown"
        content = (
            f'<span>{self._text(label)}</span><strong>{self._text(value)}</strong>'
            f'<small class="source-state">{self._text(self._source_state_text(source_state))}</small>'
        )
        if details_html:
            return (
                f'<details class="operational-status {safe_status}">'
                f'<summary>{content}<span class="status-card-action">'
                '<span class="disclosure-action-open">상세 보기</span>'
                '<span class="disclosure-action-close">접기</span>'
                '</span></summary>'
                f'<div class="status-card-detail">{details_html}</div>'
                '</details>'
            )
        return (
            f'<article class="operational-status {safe_status}">'
            f'{content}'
            "</article>"
        )

    @staticmethod
    def _analysis_finding_status(
        findings: Sequence[Mapping[str, Any]],
    ) -> str:
        severities = {
            str(finding.get("severity") or "").upper()
            for finding in findings
        }
        if "CRITICAL" in severities:
            return "risk"
        if "WARNING" in severities:
            return "caution"
        return "normal"

    @staticmethod
    def _visible_operational_status(
        findings: Sequence[Mapping[str, Any]],
        quality: Mapping[str, Any],
    ) -> str:
        severities = {
            str(finding.get("severity") or "").upper()
            for finding in findings
        }
        if "CRITICAL" in severities:
            return "RISK"
        if "WARNING" in severities:
            return "CAUTION"
        if quality.get("overall_status") == "COMPLETE":
            return "NORMAL"
        return "UNKNOWN"

    @staticmethod
    def _is_visible_operational_finding(
        finding: Mapping[str, Any],
    ) -> bool:
        if finding.get("category") in {"DATA_QUALITY", "GOVERNANCE"}:
            return False
        if finding.get("status") == "EXCEPTION":
            return False
        if not str(finding.get("rule_id") or "").startswith("METRIC_"):
            return True

        # 분석 1.1 스냅샷은 80~85% 임계치로 만든 경고를 저장할 수 있다.
        # 원본 시계열을 다시 계산하지 않고도 새 90% 하한을 보장하기 위해
        # 명시적인 임계치 근거가 있는 과거 지표 경고만 선별한다.
        evidence = finding.get("evidence")
        if not isinstance(evidence, (list, tuple)):
            return False
        for item in evidence:
            if not isinstance(item, Mapping):
                continue
            if str(item.get("label") or "").strip().casefold() not in {
                "threshold",
                "임계치",
            }:
                continue
            try:
                return (
                    float(item.get("value"))
                    >= UTILIZATION_ALERT_MIN_PERCENT
                )
            except (TypeError, ValueError):
                return False
        return False

    @staticmethod
    def _is_utilization_alert_summary(
        summary: Mapping[str, Any],
    ) -> bool:
        if summary.get("alert_severity") not in {"WARNING", "CRITICAL"}:
            return False
        if summary.get("metric_kind") not in {
            "CPU", "MEMORY", "FILESYSTEM"
        }:
            return False
        try:
            return (
                float(summary.get("maximum"))
                >= UTILIZATION_ALERT_MIN_PERCENT
            )
        except (TypeError, ValueError):
            return False

    def _finding_card(
        self,
        finding: Mapping[str, Any],
        *,
        priority: bool = False,
    ) -> str:
        resource = self._mapping(finding.get("resource"))
        evidence = self._records(finding.get("evidence"))
        evidence_text = " · ".join(
            f"{item.get('label')}: {item.get('value')}"
            + (f" {item.get('unit')}" if item.get("unit") else "")
            for item in evidence
        )
        severity = str(finding.get("severity") or "INFO").casefold()
        priority_class = " priority" if priority else ""
        priority_label = (
            '<span class="priority-label">가장 먼저 확인</span>'
            if priority
            else ""
        )
        return f"""
        <article class="finding-card {self._text(severity)}{priority_class}">
          {priority_label}
          <div class="finding-heading"><span>{self._text(finding.get('severity'))}</span><span>{self._text(self._source_state_text(finding.get('source_state')))}</span><strong>{self._text(finding.get('title'))}</strong></div>
          <p>{self._text(resource.get('name') or resource.get('id') or '공통')}</p>
          <dl><div><dt>영향</dt><dd>{self._text(finding.get('impact') or '-')}</dd></div><div><dt>조치</dt><dd>{self._text(finding.get('recommendation') or '-')}</dd></div><div><dt>근거</dt><dd>{self._text(evidence_text or '-')}</dd></div></dl>
        </article>"""

    def _render_infrastructure_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> str:
        network_categories = set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
        inventory_resources = [
            resource
            for resource in display.infrastructure
            if str(resource.get("category") or "").upper()
            not in network_categories
        ]
        server_resources = [
            resource
            for resource in inventory_resources
            if str(resource.get("category") or "").upper() == "SERVER"
        ]
        non_server_resources = [
            resource
            for resource in inventory_resources
            if str(resource.get("category") or "").upper() != "SERVER"
        ]
        inventory_html = (
            "".join((
                self._server_section(
                    server_resources,
                    report.servers,
                    report.infrastructure,
                ),
                self._infrastructure_section(non_server_resources),
            ))
            if display.inventory_enabled and inventory_resources else ""
        )
        network_configuration_html = (
            self._network_configuration_section(
                display.infrastructure,
                display.network_configuration_metadata,
            )
            if (
                display.inventory_enabled
                and any(
                    display.report_options.resource_enabled(category)
                    for category in network_categories
                )
            )
            else ""
        )
        return inventory_html + network_configuration_html

    def _render_monitoring_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> str:
        if display.monitoring_enabled:
            monitoring_parts = []
            if display.report_options.monitoring_enabled("SERVER"):
                monitoring_parts.extend((
                    self._section(
                        "서버 이용 현황",
                        "보고 기간의 서버별 CPU·메모리 평균과 마운트/드라이브별 "
                        "파일시스템 평균·최대 사용률입니다.",
                        self._metric_table(report.display_server_metrics),
                        len(report.display_server_metrics),
                        collapsed=len(report.display_server_metrics) > 20,
                        collapsed_summary=self._server_metric_summary(
                            report.display_server_metrics
                        ),
                    ),
                    self._metric_chart_section(
                        report.server_metrics,
                        report.period,
                    ),
                ))
            monitoring_parts.append(
                self._infrastructure_metric_section(
                    report.display_infrastructure_metrics,
                    report.period,
                    display.infrastructure,
                )
            )
            return "".join(monitoring_parts)
        return ""

    def _render_billing_sections(
        self,
        display: ReportDisplayData,
    ) -> Dict[str, str]:
        billing_html = ""
        if display.billing_enabled:
            billing = display.billing
            service_summary = self._numeric_rows_summary(
                billing.service_summary,
                "amount",
                unit="원",
                decimals=0,
                empty="금액 수치 없음",
            )
            network_summary = self._numeric_rows_summary(
                billing.network_summary,
                "usage_gb",
                unit="GB",
                decimals=3,
                empty="네트워크 사용량 수치 없음",
            )
            usage_totals: Dict[str, float] = defaultdict(float)
            for row in billing.usage_summary:
                value = self._finite_number(row.get("usage_quantity"))
                if value is not None:
                    unit = (
                        str(row.get("unit_code") or "").strip()
                        or "단위 미표시"
                    )
                    usage_totals[unit] += value
            usage_parts = [
                f"{unit} {self._number(total, 3)}"
                for unit, total in sorted(usage_totals.items())[:3]
            ]
            usage_summary = (
                "단위별 합계 " + " · ".join(usage_parts)
                if usage_parts else "사용량 수치 없음"
            )
            if len(usage_totals) > 3:
                usage_summary += f" · 기타 {len(usage_totals) - 3:,}개 단위"
            billing_html = "".join((
                self._section(
                    "과금 데이터 기준",
                    "확정·추정 데이터의 대상 기간, 실제 수집 범위와 계산 기준 시점을 구분합니다.",
                    self._billing_fact_cards(billing.cost_facts),
                    len(billing.cost_facts),
                ),
                self._section(
                    billing.section_title,
                    billing.section_description,
                    self._table(
                        billing.service_summary,
                        (
                            ("service_name", "서비스"),
                            ("amount", "금액", "number0"),
                            ("row_count", "항목", "number0"),
                        ),
                    ),
                    len(billing.service_summary),
                    collapsed=True,
                    collapsed_summary=service_summary,
                ),
                self._section(
                    billing.network_section_title,
                    billing.network_section_description,
                    self._table(
                        billing.network_summary,
                        (
                            ("service_name", "서비스"),
                            ("direction", "방향"),
                            ("name", "항목"),
                            ("usage_gb", "사용량(GB)", "number3"),
                            ("row_count", "건수", "number0"),
                        ),
                    ),
                    len(billing.network_summary),
                    collapsed=True,
                    collapsed_summary=network_summary,
                ),
                self._section(
                    billing.usage_section_title,
                    billing.usage_section_description,
                    self._table(
                        billing.usage_summary,
                        (
                            ("service_name", "서비스"),
                            ("item_name", "항목"),
                            ("usage_quantity", "사용량", "number3"),
                            ("unit_code", "단위"),
                            ("row_count", "건수", "number0"),
                        ),
                    ),
                    len(billing.usage_summary),
                    collapsed=True,
                    collapsed_summary=usage_summary,
                ),
            ))

        organization_billing_html = (
            self._organization_cost_sections(display.billing.account_costs)
            if display.organization_billing_enabled else ""
        )
        return {
            "billing": billing_html,
            "organization_billing": organization_billing_html,
        }

    def _render_event_diagnostic_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> Dict[str, str]:
        insight_events_html = (
            self._section(
                "Cloud Insight 이벤트",
                "보고 기간에 수집된 Cloud Insight 이벤트입니다.",
                self._event_table(report.insight_events),
                len(report.insight_events),
                collapsed=True,
                collapsed_summary=self._counted_values_summary(
                    report.insight_events,
                    ("severity", "level", "event_level", "status"),
                    {
                        "CRITICAL": "위험",
                        "FATAL": "위험",
                        "WARNING": "경고",
                        "ERROR": "오류",
                        "INFO": "정보",
                    },
                    empty="심각도 정보 없음",
                    priority_labels=("위험", "오류", "경고", "정보"),
                ),
            )
            if display.report_options.section_enabled("insight_events")
            else ""
        )
        activity_summary_html, activity_collapsed_summary = (
            self._activity_attention_summary(report, display.activity_events)
        )
        activity_html = (
            self._section(
                "Cloud Activity Tracer",
                "보고 기간에 기록된 계정 및 리소스 작업 이력입니다.",
                activity_summary_html
                + self._activity_table(display.activity_events),
                len(display.activity_events),
                collapsed=True,
                collapsed_summary=activity_collapsed_summary,
            )
            if display.report_options.section_enabled("activity_history")
            else ""
        )
        diagnostics_html = ""
        if display.report_options.section_enabled("collection_diagnostics"):
            diagnostics = self._collection_diagnostics(
                warnings=report.collection_warnings,
                errors=report.collection_errors,
            )
            diagnostics_html = self._section(
                "수집 진단",
                (
                    "수집 중 발생한 경고와 오류를 함께 표시합니다. "
                    "NCP 응답에 명시된 권한과 호출 API 기준 권고 권한을 "
                    "구분해 표시합니다. 일반 403의 권고 권한은 지원 환경도 "
                    "함께 확인해야 합니다."
                ),
                self._diagnostic_table(diagnostics),
                len(diagnostics),
                warning=bool(diagnostics),
                collapsed=True,
                collapsed_summary=self._counted_values_summary(
                    diagnostics,
                    "severity",
                    {"ERROR": "오류", "WARNING": "경고"},
                    empty="경고·오류 없음",
                    priority_labels=("오류", "경고"),
                ),
            )
        return {
            "insight_events": insight_events_html,
            "activity_history": activity_html,
            "collection_diagnostics": diagnostics_html,
        }

    def _render_report_sections(
        self,
        report: ReportResult,
        display: ReportDisplayData,
    ) -> str:
        sections = {
            "executive_summary": self._render_summary_section(
                report, display
            ),
            "infrastructure_inventory": (
                self._render_infrastructure_sections(report, display)
            ),
            "monitoring": self._render_monitoring_sections(report, display),
            **self._render_billing_sections(display),
            **self._render_event_diagnostic_sections(report, display),
        }
        return "".join(
            sections.get(name, "")
            for name in display.report_options.ordered_sections
        )

    def _render_document(
        self,
        report: ReportResult,
        display: ReportDisplayData,
        sections: str,
    ) -> str:
        period = display.period
        report_title = display.report_title
        interaction_script = (
            f"<script>{REPORT_INTERACTION_SCRIPT}</script>"
            if (
                "data-chart-" in sections
                or "data-resource-filter" in sections
            )
            else ""
        )
        logo = (
            f'<img src="{self._text(display.customer_logo_data_uri)}" '
            f'alt="{self._text(display.customer_name)} 로고">'
            if display.customer_logo_data_uri
            else (
                f'<span aria-hidden="true">'
                f'{self._text(display.customer_initials)}</span>'
            )
        )

        return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="report-id" content="{self._text(report.report_id)}">
  <title>{self._text(report_title)} · {self._text(report.report_id)}</title>
  <style>{HTML_REPORT_STYLES}{REPORT_DISPLAY_STYLES}</style>
</head>
<body>
  <main class="report-shell">
    <header class="report-header">
      <div class="report-identity">
        <div class="customer-logo-plate">{logo}</div>
        <div class="report-heading">
          <p class="eyebrow">NAVER CLOUD PLATFORM</p>
          <h1>{self._text(report_title)}</h1>
          <p class="subtitle">{self._text(self._display_period_start(period))}
            <span aria-hidden="true">→</span>
            {self._text(self._display_period_end(period))}</p>
        </div>
      </div>
      <div class="report-meta">
        <span>보고서 ID</span>
        <strong>{self._text(report.report_id)}</strong>
        <span>생성 시각</span>
        <strong>{self._text(report.generated_at)}</strong>
      </div>
    </header>

    {sections}

    <footer>
      <p>이 보고서는 구조화된 NCP 수집 결과로부터 생성되었습니다.</p>
    </footer>
  </main>
  {interaction_script}
</body>
</html>
"""

    @staticmethod
    def _safe_customer_logo_data_uri(value: Any) -> str | None:
        try:
            return normalize_customer_logo_data_uri(value)
        except ValueError:
            # 변조되었거나 과거 형식인 스냅샷은 active content 대신 문자 로고로 대체한다.
            return None

    @staticmethod
    def _customer_initials(customer_name: str) -> str:
        words = [
            "".join(character for character in word if character.isalnum())
            for word in customer_name.split()
        ]
        words = [word for word in words if word]
        if len(words) >= 2:
            return "".join(word[0] for word in words[:2]).upper()
        if words:
            return words[0][:2].upper()
        return "NR"

    def write(self, report: ReportResult, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path

    def _summary_card(
        self,
        label: str,
        value: Any,
        unit: str,
        warning: bool = False,
    ) -> str:
        status_class = " warning" if warning else ""
        return f"""
      <article class="summary-card{status_class}">
        <span>{self._text(label)}</span>
        <strong>{self._text(value)} <small>{self._text(unit)}</small></strong>
      </article>"""

    def _section(
        self,
        title: str,
        description: str,
        content: str,
        count: int | None,
        warning: bool = False,
        collapsed: bool = False,
        collapsed_summary: str = "",
    ) -> str:
        status_class = " warning" if warning else ""
        count_html = (
            f'<span class="count">{count:,}건</span>'
            if count is not None
            else ""
        )
        summary_html = (
            '<small class="section-description section-summary">'
            f'<strong>핵심</strong> · {self._text(collapsed_summary)}</small>'
            if collapsed_summary
            else ""
        )
        if collapsed:
            return f"""
    <details class="report-section report-disclosure{status_class}">
      <summary class="section-heading">
        <span class="section-heading-copy">
          <span class="section-title" role="heading" aria-level="2">{self._text(title)}</span>
          {summary_html}
          <small class="section-description">{self._text(description)}</small>
        </span>
        {count_html}
      </summary>
      <div class="report-disclosure-body">{content}</div>
    </details>"""
        return f"""
    <section class="report-section{status_class}">
      <div class="section-heading">
        <div>
          <h2>{self._text(title)}</h2>
          <p>{self._text(description)}</p>
        </div>
        {count_html}
      </div>
      {content}
    </section>"""

    def _counted_values_summary(
        self,
        rows: Sequence[Mapping[str, Any]],
        key: str | Sequence[str],
        labels: Mapping[str, str],
        *,
        empty: str = "상태 정보 없음",
        priority_labels: Sequence[str] = (),
    ) -> str:
        counts: Dict[str, int] = defaultdict(int)
        keys = (key,) if isinstance(key, str) else key
        for row in rows:
            raw_value = self._first_present(
                *(row.get(candidate) for candidate in keys)
            ).strip()
            if not raw_value:
                continue
            normalized = raw_value.upper()
            counts[labels.get(normalized, raw_value)] += 1
        if not counts:
            return empty
        priority = {
            label: index for index, label in enumerate(priority_labels)
        }
        ranked = sorted(
            counts,
            key=lambda value: (
                priority.get(value, len(priority)),
                -counts[value],
                value,
            ),
        )
        parts = [
            f"{value} {counts[value]:,}건"
            for value in ranked[:3]
        ]
        if len(ranked) > 3:
            parts.append(f"기타 {sum(counts[value] for value in ranked[3:]):,}건")
        return " · ".join(parts)

    def _numeric_rows_summary(
        self,
        rows: Sequence[Mapping[str, Any]],
        key: str,
        *,
        unit: str,
        decimals: int,
        empty: str,
    ) -> str:
        values = []
        for row in rows:
            value = self._finite_number(row.get(key))
            if value is not None:
                values.append((value, row))
        if not values:
            return empty
        top_value, top_row = max(values, key=lambda item: item[0])
        top_label = self._first_present(
            top_row.get("item_name"),
            top_row.get("name"),
            top_row.get("service_name"),
        ) or "항목"
        return (
            f"합계 {self._number(sum(value for value, _ in values), decimals)}{unit}"
            f" · 최대 {top_label} {self._number(top_value, decimals)}{unit}"
        )

    def _server_metric_summary(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> str:
        metric_fields = (
            ("cpu_avg", "CPU"),
            ("mem_avg", "메모리"),
        )
        candidates = []
        threshold_count = 0
        for row in rows:
            server_values = []
            for key, label in metric_fields:
                value = self._finite_number(row.get(key))
                if value is None:
                    continue
                candidates.append((value, row, label))
                server_values.append(value)
            for detail_key in ("os_fs_details", "data_fs_details"):
                for detail in self._records(row.get(detail_key)):
                    value = self._finite_number(detail.get("avg"))
                    if value is None:
                        continue
                    mount = self._first_present(detail.get("mount")) or "-"
                    candidates.append(
                        (value, row, f"파일시스템 {mount}")
                    )
                    server_values.append(value)
            if any(
                value >= UTILIZATION_ALERT_MIN_PERCENT
                for value in server_values
            ):
                threshold_count += 1
        if not candidates:
            return "사용률 데이터 없음"
        value, row, label = max(candidates, key=lambda item: item[0])
        server_name = self._first_present(
            row.get("server_name"), row.get("server_id")
        ) or "서버"
        return (
            "평균 "
            f"{self._number(UTILIZATION_ALERT_MIN_PERCENT, 0)}% 이상 "
            f"{threshold_count:,}대 · 기간 평균 최고 "
            f"{server_name} {label} {self._number(value, 2)}%"
        )

    @staticmethod
    def _finite_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _infrastructure_section(
        self,
        resources: List[Dict[str, Any]],
    ) -> str:
        if not resources:
            return ""

        allowed = {
            category for category, _ in self.INFRASTRUCTURE_CATEGORIES
        }
        counts = defaultdict(int)
        prepared = []

        for candidate in self._records(resources):
            resource = candidate
            category = str(resource.get("category") or "").upper()
            if category not in allowed or category == "SERVER":
                continue
            counts[category] += 1
            details = resource.get("details")
            if not isinstance(details, dict):
                details = {}
            region_zone = " / ".join(
                str(value)
                for value in (
                    resource.get("region_code"),
                    resource.get("zone_code"),
                )
                if value
            )
            prepared.append({
                **resource,
                "location": region_zone or "-",
                "details_text": self._infrastructure_details_text(
                    details
                ),
                "size_summary": resource_size_summary(category, details),
                "connection_summary": resource_connection_summary(
                    category,
                    details,
                ),
                "create_time_text": self._infrastructure_create_time(
                    resource.get("create_time")
                ),
                "historical_presence_text": (
                    self._historical_confidence_text(
                        details.get("historical_presence_confidence")
                    )
                ),
                "historical_source_state_text": self._source_state_text(
                    historical_source_state(
                        details.get("historical_presence_confidence")
                    )
                ),
            })

        if not prepared:
            return ""

        summary_categories = [
            (category, label)
            for category, label in self.INFRASTRUCTURE_CATEGORIES
            if counts.get(category)
        ]
        table_id = "other-resource-table"
        summary_cards = f"""
      <button type="button" class="infra-summary-card is-active"
        data-resource-filter="" aria-pressed="true"
        aria-controls="{table_id}" aria-label="전체 {len(prepared):,}건 표시">
        <span>전체</span>
        <strong>{len(prepared):,}</strong>
      </button>""" + "".join(
            f"""
      <button type="button" class="infra-summary-card"
        data-resource-filter="{self._text(category)}" aria-pressed="false"
        aria-controls="{table_id}"
        aria-label="{self._text(label)} {counts.get(category, 0):,}건만 표시">
        <span>{self._text(label)}</span>
        <strong>{counts.get(category, 0):,}</strong>
      </button>"""
            for category, label in summary_categories
        )
        columns = [
            ("category_label", "구분"),
            ("resource_name", "리소스명"),
            ("service_name", "서비스"),
            ("resource_type", "유형"),
            ("status", "상태"),
            ("location", "리전 / Zone"),
            ("size_summary", "규모 / 과금 관련 지표"),
            ("connection_summary", "주소 / 연결"),
            ("details_text", "기타 구성"),
            ("create_time_text", "생성 시각 (KST)"),
        ]
        if any(
            self._mapping(resource.get("details")).get(
                "historical_presence_confidence"
            )
            for resource in prepared
        ):
            columns.append(
                ("historical_presence_text", "기간 존재 판단")
            )
            columns.append(
                ("historical_source_state_text", "출처 상태")
            )
        table = self._table(
            prepared,
            tuple(columns),
            resource_category_key="category",
        )
        summary = (
            f'<div class="infra-summary-grid">{summary_cards}</div>'
            '<p class="resource-filter-status" data-resource-filter-status '
            f'role="status" aria-live="polite">전체 {len(prepared):,}건 표시 중</p>'
            if summary_cards else ""
        )
        content = summary + f'<div id="{table_id}">{table}</div>'
        return self._section(
            "기타 자원 현황",
            (
                "서버를 제외한 선택 자원을 표시합니다. 규모 열은 "
                "NCP 응답에서 확인된 SKU·사양·용량·처리 등급 등 과금 관련 "
                "지표이며 실제 청구 금액을 의미하지 않습니다."
            ),
            content,
            len(prepared),
            collapsed=True,
            collapsed_summary=self._counted_values_summary(
                prepared,
                "category",
                RESOURCE_CATEGORY_LABELS,
                empty="자원 유형 정보 없음",
            ),
        )

    def _server_section(
        self,
        resources: List[Dict[str, Any]],
        servers: List[Dict[str, Any]],
        infrastructure: List[Dict[str, Any]],
    ) -> str:
        """서버 자원을 전용 열 구조로 표시한다."""
        if not resources:
            return ""

        prepared = []
        for candidate in self._records(resources):
            resource = merge_server_details(candidate, servers)
            details = self._mapping(resource.get("details"))
            private_ips = details.get("all_private_ips") or details.get(
                "private_ip"
            )
            prepared.append({
                **resource,
                "server_name": resource.get("resource_name"),
                "server_spec": server_spec_summary(details),
                "vpc": self._resource_membership_label(
                    details.get("vpc_no"),
                    "VPC",
                    infrastructure,
                ),
                "subnet": self._resource_membership_label(
                    details.get("subnet_no"),
                    "SUBNET",
                    infrastructure,
                ),
                "public_ip": self._compact_values(details.get("public_ip")),
                "private_ip": self._compact_values(private_ips),
                "create_time_text": self._infrastructure_create_time(
                    resource.get("create_time")
                ),
                "historical_presence_text": (
                    self._historical_confidence_text(
                        details.get("historical_presence_confidence")
                    )
                ),
                "historical_source_state_text": self._source_state_text(
                    historical_source_state(
                        details.get("historical_presence_confidence")
                    )
                ),
            })

        columns = [
            ("server_name", "서버명"),
            ("status", "서버 상태"),
            ("server_spec", "서버 스펙"),
            ("vpc", "소속 VPC"),
            ("subnet", "소속 Subnet"),
            ("public_ip", "Public IP"),
            ("private_ip", "Private IP"),
            ("create_time_text", "생성 시각 (KST)"),
        ]
        if any(
            self._mapping(resource.get("details")).get(
                "historical_presence_confidence"
            )
            for resource in prepared
        ):
            columns.append(("historical_presence_text", "기간 존재 판단"))
            columns.append(("historical_source_state_text", "출처 상태"))

        return self._section(
            "서버 현황",
            (
                "서버별 상태, NCP 상품·컴퓨팅 사양, 연결 스토리지, "
                "소속 네트워크와 IP를 표시합니다."
            ),
            self._table(prepared, tuple(columns)),
            len(prepared),
            collapsed=True,
            collapsed_summary=self._counted_values_summary(
                prepared,
                "status",
                {
                    "RUN": "운영",
                    "RUNNING": "운영",
                    "STOP": "정지",
                    "STOPPED": "정지",
                    "INIT": "초기화",
                    "CREATING": "생성 중",
                    "TERMINATED": "반납",
                },
                empty="서버 상태 정보 없음",
                priority_labels=(
                    "정지", "반납", "생성 중", "초기화", "운영"
                ),
            ),
        )

    def _resource_membership_label(
        self,
        resource_id: Any,
        category: str,
        resources: List[Dict[str, Any]],
    ) -> str:
        """VPC·Subnet ID를 수집된 자원명과 함께 사람이 읽기 좋게 표시한다."""
        normalized_id = str(resource_id or "").strip()
        if not normalized_id:
            return "-"
        for resource in self._records(resources):
            if str(resource.get("category") or "").upper() != category:
                continue
            if str(resource.get("resource_id") or "").strip() != normalized_id:
                continue
            resource_name = str(resource.get("resource_name") or "").strip()
            if resource_name and resource_name != normalized_id:
                return f"{resource_name} ({normalized_id})"
            break
        return normalized_id

    @staticmethod
    def _compact_values(value: Any) -> str:
        """IP처럼 짧은 복수 값을 중복 없이 쉼표로 연결한다."""
        if isinstance(value, (list, tuple, set)):
            values = []
            seen = set()
            for item in value:
                text = str(item or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                values.append(text)
            return ", ".join(values) or "-"
        text = str(value or "").strip()
        return text or "-"

    def _network_configuration_section(
        self,
        resources: List[Dict[str, Any]],
        metadata: Mapping[str, Any],
    ) -> str:
        """Route Table·ACG·Network ACL을 단일 시점 백업으로 표시한다."""
        categories = set(NETWORK_CONFIGURATION_CATEGORY_OPTIONS)
        configurations = [
            resource
            for resource in self._records(resources)
            if str(resource.get("category") or "").upper() in categories
        ]
        captured_at = self._infrastructure_create_time(
            metadata.get("captured_at")
        )
        backup_captured_at = self._infrastructure_create_time(
            metadata.get("backup_captured_at")
        )
        in_period = metadata.get("is_report_period_snapshot") is True
        period_basis = (
            "보고 기간 내 단일 시점 관측"
            if in_period
            else "보고 기간 외 · 생성시점 현재 상태"
        )
        source_label = {
            "STORED_NETWORK_CONFIGURATION_SNAPSHOT": (
                "별도 저장된 과거 네트워크 스냅샷"
            ),
            "REPORT_GENERATION_SNAPSHOT": (
                "이번 보고서 생성 과정의 네트워크 스냅샷"
            ),
        }.get(str(metadata.get("source") or ""), "네트워크 구성 스냅샷")
        metadata_html = f"""
      <div class="network-snapshot-basis">
        <div><span>데이터 성격</span><strong>단일 시점 구성 백업</strong></div>
        <div><span>실제 수집 시각</span><strong>{self._text(captured_at)}</strong></div>
        <div><span>보고 기간과의 관계</span><strong>{self._text(period_basis)}</strong></div>
        <div><span>수집 계기</span><strong>보고서 생성 과정</strong></div>
        <div><span>표시 데이터 출처</span><strong>{self._text(source_label)}</strong></div>
        <div><span>이번 생성시점 백업 시각</span><strong>{self._text(backup_captured_at)}</strong></div>
      </div>"""

        summary_rows = []
        route_rows = []
        acg_rule_rows = []
        network_acl_rule_rows = []
        acg_rule_count = 0
        network_acl_rule_count = 0
        for resource in configurations:
            category = str(resource.get("category") or "").upper()
            details = self._mapping(resource.get("details"))
            summary_rows.append({
                "category": resource.get("category_label") or category,
                "name": resource.get("resource_name"),
                "id": resource.get("resource_id"),
                "vpc_no": details.get("vpc_no"),
                "status": resource.get("status"),
                "default": "기본" if details.get("default") is True else "-",
                "association_count": details.get(
                    "associated_subnet_count"
                ),
                "rule_count": details.get("rule_count")
                if category != "ROUTE_TABLE"
                else details.get("route_count"),
            })
            if category == "ROUTE_TABLE":
                subnet_names = ", ".join(
                    str(subnet.get("subnet_name") or subnet.get("subnet_no"))
                    for subnet in self._records(
                        details.get("associated_subnets")
                    )
                ) or "-"
                for route in self._records(details.get("routes")):
                    route_rows.append({
                        "route_table": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "subnets": subnet_names,
                        "destination": route.get("destination_cidr"),
                        "target_type": route.get("target_type"),
                        "target": route.get("target_name")
                        or route.get("target_no"),
                        "default": "기본" if route.get("default") is True else "-",
                    })
            elif category == "ACCESS_CONTROL_GROUP":
                rules = self._records(details.get("rules"))
                acg_rule_count += len(rules)
                if not rules:
                    acg_rule_rows.append({
                        "group": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "description": (
                            "ACG 수집 완료, 명시 규칙 0건"
                            if details.get("rule_snapshot_available") is True
                            else "규칙 수집 결과 없음"
                        ),
                    })
                for rule in rules:
                    acg_rule_rows.append({
                        "group": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "direction": rule.get("direction"),
                        "protocol": rule.get("protocol"),
                        "source": rule.get("source_ip_block")
                        or rule.get("source_access_control_group_no"),
                        "port": rule.get("port_range"),
                        "description": rule.get("description"),
                    })
            elif category == "NETWORK_ACL":
                rules = self._records(details.get("rules"))
                network_acl_rule_count += len(rules)
                if not rules:
                    network_acl_rule_rows.append({
                        "network_acl": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "description": (
                            "NACL 수집 완료, 명시 규칙 0건"
                            if details.get("rule_snapshot_available") is True
                            else "규칙 수집 결과 없음"
                        ),
                    })
                for rule in rules:
                    network_acl_rule_rows.append({
                        "network_acl": resource.get("resource_name"),
                        "vpc_no": details.get("vpc_no"),
                        "priority": rule.get("priority"),
                        "direction": rule.get("direction"),
                        "protocol": rule.get("protocol"),
                        "source": rule.get("source_ip_block")
                        or rule.get("deny_allow_group_no"),
                        "port": rule.get("port_range"),
                        "action": rule.get("action"),
                        "description": rule.get("description"),
                    })

        tables = "".join((
            '<div class="network-config-group"><h3>구성 객체</h3>',
            self._table(
                summary_rows,
                (
                    ("category", "구분"),
                    ("name", "이름"),
                    ("id", "ID"),
                    ("vpc_no", "VPC No."),
                    ("status", "상태"),
                    ("default", "기본 여부"),
                    ("association_count", "연결 Subnet", "number0"),
                    ("rule_count", "규칙", "number0"),
                ),
            ),
            '</div><div class="network-config-group"><h3>Route 규칙</h3>',
            self._table(
                route_rows,
                (
                    ("route_table", "Route Table"),
                    ("vpc_no", "VPC No."),
                    ("subnets", "연결 Subnet"),
                    ("destination", "Destination CIDR"),
                    ("target_type", "Target 유형"),
                    ("target", "Target"),
                    ("default", "기본 여부"),
                ),
            ),
            '</div><div class="network-config-group"><h3>ACG 규칙</h3>',
            self._table(
                acg_rule_rows,
                (
                    ("group", "ACG"),
                    ("vpc_no", "VPC No."),
                    ("direction", "방향"),
                    ("protocol", "프로토콜"),
                    ("source", "접근 소스"),
                    ("port", "포트"),
                    ("description", "설명"),
                ),
            ),
            '</div><div class="network-config-group"><h3>Network ACL 규칙</h3>',
            self._table(
                network_acl_rule_rows,
                (
                    ("network_acl", "Network ACL"),
                    ("vpc_no", "VPC No."),
                    ("priority", "우선순위", "number0"),
                    ("direction", "방향"),
                    ("protocol", "프로토콜"),
                    ("source", "IP / Deny-Allow Group"),
                    ("port", "포트"),
                    ("action", "동작"),
                    ("description", "설명"),
                ),
            ),
            "</div>",
        ))
        description = (
            "보고 기간 안에 저장된 단일 시점의 Route Table·ACG·Network ACL "
            "구성입니다. 기간 전체의 변경 이력을 의미하지 않습니다."
            if in_period
            else (
                "보고 기간에 저장된 네트워크 스냅샷이 없어 이번 보고서 생성 "
                "과정에서 조회한 현재 설정을 별도로 백업했습니다. 아래 값은 "
                "보고 대상 기간의 과거 상태가 아닙니다."
            )
        )
        return self._section(
            "네트워크 구성 스냅샷",
            description,
            metadata_html + tables,
            len(configurations),
            warning=not in_period,
            collapsed=True,
            collapsed_summary=(
                f"{period_basis} · "
                + self._counted_values_summary(
                    configurations,
                    "category",
                    RESOURCE_CATEGORY_LABELS,
                    empty="구성 객체 없음",
                )
                + f" · 실제 규칙 Route {len(route_rows):,}건"
                + f" · ACG {acg_rule_count:,}건"
                + f" · NACL {network_acl_rule_count:,}건"
            ),
        )

    def _infrastructure_details_text(self, value: Any) -> str:
        if not isinstance(value, dict):
            return "-"
        labels = (
            ("network_type", "네트워크", ""),
            ("protocol", "프로토콜", ""),
            ("version", "버전", ""),
            ("kubernetes_version", "Kubernetes", ""),
            ("attached_server_name", "연결 서버", ""),
            ("high_availability", "HA", ""),
            ("multi_zone", "Multi Zone", ""),
            ("encrypted", "암호화", ""),
            ("snapshot_configured", "스냅샷", ""),
            ("termination_protection", "반납 보호", ""),
            ("regional", "리전 클러스터", ""),
            ("public_network", "Public Network", ""),
            ("subnet_type", "Subnet 유형", ""),
            ("usage_type", "용도", ""),
        )
        parts = []
        for key, label, suffix in labels:
            item = value.get(key)
            if item is None or item == "":
                continue
            if isinstance(item, bool):
                item = "사용" if item else "미사용"
            parts.append(f"{label}: {item}{suffix}")
            if len(parts) == 5:
                break
        return " · ".join(parts) or "-"

    @staticmethod
    def _historical_confidence_text(value: Any) -> str:
        return {
            "INFERRED_FROM_CREATE_TIME": "생성 시각 기반 추정",
            "UNKNOWN": "생성 시각 미확인",
        }.get(str(value or "").upper(), "-")

    def _infrastructure_create_time(self, value: Any) -> str:
        timestamp = event_timestamp_millis(value)
        if timestamp is not None:
            parsed = datetime.fromtimestamp(timestamp / 1000, tz=self.KST)
            return parsed.strftime("%Y-%m-%d %H:%M KST")
        return (
            str(value).strip()
            if isinstance(value, str) and value.strip()
            else "-"
        )

    def _infrastructure_metric_section(
        self,
        metric_groups: List[Dict[str, Any]],
        period: Dict[str, Any],
        infrastructure: List[Dict[str, Any]],
    ) -> str:
        monitored_categories = {
            category: (
                "Kubernetes"
                if category == "KUBERNETES"
                else RESOURCE_CATEGORY_LABELS.get(
                    category,
                    category.replace("_", " ").title(),
                )
            )
            for category in MONITORING_CATEGORY_OPTIONS
            if category != "SERVER"
        }
        present_categories = {
            str(item.get("category") or "").upper()
            for item in self._records(infrastructure)
        } & set(monitored_categories)
        groups = [
            group for group in self._records(metric_groups)
            if str(group.get("category") or "").upper()
            in monitored_categories
        ]

        if not present_categories and not groups:
            return ""

        cards = []
        rendered_categories = set()
        for chart_index, group in enumerate(groups, start=1):
            category = str(group.get("category") or "").upper()
            series = self._infrastructure_metric_series(group)
            interval = str(group.get("interval") or "Min5")
            aggregation = str(group.get("aggregation") or "AVG")
            unit = str(group.get("unit") or "")
            metric_label = str(
                group.get("metric_label")
                or group.get("metric")
                or "Metric"
            )
            product_name_value = str(group.get("product_name") or "").strip()
            product_name = product_name_value or "Cloud Insight"
            resource_label = (
                "Load Balancer"
                if str(group.get("metric_scope") or "").upper()
                == "TARGET_GROUP"
                else (
                    diagnostic_service_name({
                        "product_name": product_name_value,
                        "category": category,
                    })
                    if category == "CLOUD_DB" and product_name_value
                    else monitored_categories[category]
                )
            )
            title = f"{resource_label} · {metric_label}"
            description = (
                f"{product_name} · {self._metric_interval_label(interval)} "
                f"{aggregation}"
            )
            if unit:
                description += f" · 단위 {unit}"
            y_axis = (
                "fixed"
                if self._is_percent_unit(unit)
                else "auto"
            )
            cards.append(f"""
      <article class="chart-card">
        {self._chart_heading(title, description)}
        {self._line_chart(
            title,
            series,
            period,
            y_axis,
            interval,
            unit=unit,
            chart_id=f"infrastructure-chart-{chart_index}",
        )}
      </article>""")
            rendered_categories.add(category)

        for category in sorted(
            present_categories - rendered_categories,
            key=lambda item: tuple(monitored_categories).index(item),
        ):
            category_title = monitored_categories[category]
            cards.append(f"""
      <article class="chart-card">
        {self._chart_heading(category_title, "Cloud Insight 모니터링 데이터 상태")}
        <p class="empty-state chart-empty">표시할 시계열이 없습니다. 권한, 모니터링 활성화 여부와 데이터 보관 기간을 확인하십시오.</p>
      </article>""")

        return f"""
    <section class="report-section infrastructure-trends">
      <div class="section-heading">
        <div>
          <h2>주요 인프라 모니터링</h2>
          <p>선택한 자원의 보고 기간 Cloud Insight 시계열입니다. 범례나 선을 눌러 비교할 자원을 여러 개 선택할 수 있으며, 선택이 없으면 전체를 표시합니다. 그래프 상단의 ⠿ 영역을 누른 채 원하는 위치로 끌어 놓으면 순서가 자동 배치되며, 키보드에서는 방향키로 이동할 수 있습니다.</p>
        </div>
        <span class="count">{len(groups):,}개 그래프</span>
      </div>
      <div class="chart-grid">{''.join(cards)}</div>
    </section>"""

    def _infrastructure_metric_series(
        self,
        group: Dict[str, Any],
    ) -> Dict[str, List[Tuple[int, float]]]:
        result: Dict[str, List[Tuple[int, float]]] = {}
        for index, item in enumerate(self._records(group.get("series"))):
            points = sorted(self._metric_points(item), key=lambda point: point[0])
            if not points:
                continue
            label = str(
                item.get("resource_name")
                or item.get("resource_id")
                or f"resource-{index + 1}"
            )
            dimensions = item.get("dimensions")
            if isinstance(dimensions, dict):
                qualifier = (
                    dimensions.get("loadBalancerPort")
                    or dimensions.get("instanceName")
                    or dimensions.get("pod")
                    or dimensions.get("podName")
                    or dimensions.get("controller")
                    or dimensions.get("role")
                )
                qualifier_text = str(qualifier or "").strip()
                if (
                    qualifier_text
                    and qualifier_text.casefold() not in label.casefold()
                ):
                    label = f"{label} · {qualifier_text}"
            unique_label = label
            suffix = 2
            while unique_label in result:
                unique_label = f"{label} ({suffix})"
                suffix += 1
            result[unique_label] = points
        return result

    @staticmethod
    def _is_percent_unit(unit: str) -> bool:
        return unit.strip().casefold() in {"%", "percent", "percentage"}

    def _metric_table(self, rows: List[Dict[str, Any]]) -> str:
        prepared = [
            {
                **row,
                "os_fs": self._filesystem_text(
                    row.get("os_fs_details")
                ),
                "data_fs": self._filesystem_text(
                    row.get("data_fs_details")
                ),
            }
            for row in rows
        ]

        return self._table(
            prepared,
            (
                ("server_name", "서버"),
                ("cpu_avg", "CPU 평균", "percent"),
                ("mem_avg", "메모리 평균", "percent"),
                ("os_fs", "OS 드라이브별 사용률"),
                ("data_fs", "DATA 드라이브별 사용률"),
            ),
        )

    def _metric_chart_section(
        self,
        server_metrics: List[Dict[str, Any]],
        period: Dict[str, Any],
    ) -> str:
        interval = self._report_metric_interval(
            server_metrics,
            period,
        )
        aggregation_label = self._metric_interval_label(interval)
        charts = (
            (
                "Memory Utilization Average",
                f"서버별 메모리 {aggregation_label} 사용률",
                self._metric_series(
                    server_metrics,
                    metric_name="mem_usert",
                    period=period,
                ),
                "fixed",
            ),
            (
                "CPU Utilization Average",
                f"서버별 CPU {aggregation_label} 사용률",
                self._metric_series(
                    server_metrics,
                    metric_name="used_rto",
                    period=period,
                ),
                "fixed",
            ),
            (
                "OS Disk File System Utilization Average",
                f"서버·OS 마운트별 {aggregation_label} 평균 사용률",
                self._metric_series(
                    server_metrics,
                    metric_name="fs_usert",
                    period=period,
                    filesystem_group="os",
                ),
                "fixed",
            ),
            (
                "Data Disk File System Utilization Average",
                f"서버·추가 마운트별 데이터 디스크 {aggregation_label} 평균 사용률",
                self._metric_series(
                    server_metrics,
                    metric_name="fs_usert",
                    period=period,
                    filesystem_group="data",
                ),
                "fixed",
            ),
        )
        charts = tuple(chart for chart in charts if chart[2])
        if not charts:
            return ""
        chart_cards = "".join(
            f"""
      <article class="chart-card">
        {self._chart_heading(title, description)}
        {self._line_chart(
            title,
            series,
            period,
            y_axis,
            interval,
            chart_id=f"server-chart-{index}",
        )}
      </article>"""
            for index, (title, description, series, y_axis)
            in enumerate(charts, start=1)
        )

        return f"""
    <section class="report-section metric-trends">
      <div class="section-heading">
        <div>
          <h2>All Server 사용률 추이</h2>
          <p>Cloud Insight 원시 지표로 보고서에서 재구성한 KST {aggregation_label} 그래프입니다. 서버 이름이나 선을 눌러 비교할 서버를 여러 대 선택할 수 있으며, 선택이 없으면 전체를 표시합니다. 그래프 상단의 ⠿ 영역을 누른 채 원하는 위치로 끌어 놓으면 순서가 자동 배치되며, 키보드에서는 방향키로 이동할 수 있습니다.</p>
        </div>
        <span class="count">{len(charts):,}개 그룹</span>
      </div>
      <div class="chart-grid">{chart_cards}</div>
    </section>"""

    def _chart_heading(self, title: str, description: str) -> str:
        safe_title = self._text(title)
        return f"""
        <div class="chart-heading" data-chart-drag-handle tabindex="0"
             role="group"
             aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown"
             aria-label="{safe_title} 그래프 순서 변경. 끌어 놓거나 방향키를 사용하세요"
             title="누른 채 끌어서 그래프 순서 변경">
          <span class="chart-drag-grip" aria-hidden="true">⠿</span>
          <div class="chart-heading-copy">
            <h3>{safe_title}</h3>
            <p>{self._text(description)}</p>
          </div>
        </div>"""

    def _metric_series(
        self,
        server_metrics: List[Dict[str, Any]],
        metric_name: str,
        period: Dict[str, Any],
        filesystem_group: str | None = None,
    ) -> Dict[str, List[Tuple[int, float]]]:
        period_start, period_end = self._period_bounds(period)
        buckets: Dict[str, Dict[int, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        server_name_counts: Dict[str, int] = defaultdict(int)
        for server_metric in server_metrics:
            if isinstance(server_metric, dict):
                server_name_counts[str(
                    server_metric.get("server_name")
                    or server_metric.get("server_id")
                    or "unknown"
                )] += 1

        for server_metric in server_metrics:
            if not isinstance(server_metric, dict):
                continue

            raw_metrics = server_metric.get("raw_metrics")
            if not isinstance(raw_metrics, dict):
                continue

            metric_data = raw_metrics.get(metric_name)
            if not isinstance(metric_data, dict):
                continue

            entries = metric_data.get("avg")
            if not isinstance(entries, list):
                continue

            server_name = str(
                server_metric.get("server_name")
                or server_metric.get("server_id")
                or "unknown"
            )
            server_id = str(server_metric.get("server_id") or "").strip()
            if (
                server_name_counts[server_name] > 1
                and server_id
                and server_id != server_name
            ):
                server_name = f"{server_name} ({server_id})"
            filesystem_mounts = set()
            if filesystem_group:
                filesystem_mounts = {
                    str(detail.get("mount") or "").strip()
                    for detail in self._records(
                        server_metric.get(
                            f"{filesystem_group}_fs_details"
                        )
                    )
                }
            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                dimensions = entry.get("dimensions")
                if not isinstance(dimensions, dict):
                    dimensions = {}
                label = server_name
                if filesystem_group:
                    mount_name = str(
                        dimensions.get("mnt_nm")
                        or dimensions.get("mount")
                        or ""
                    ).strip()
                    if mount_name not in filesystem_mounts:
                        continue
                    label = f"{server_name} · {mount_name}"

                for point_time, point_value in self._metric_points(entry):
                    if (
                        period_start is not None
                        and point_time < period_start
                    ):
                        continue
                    if period_end is not None and point_time > period_end:
                        continue

                    buckets[label][point_time].append(point_value)

        result = {}
        for label, daily_values in buckets.items():
            result[label] = [
                (
                    point_time,
                    sum(values) / len(values),
                )
                for point_time, values in sorted(daily_values.items())
                if values
            ]
        return result

    def _metric_interval_label(self, interval: str) -> str:
        return {
            "Min1": "1분 AVG",
            "Min5": "5분 AVG",
            "Min30": "30분 AVG",
            "Hour2": "2시간 AVG",
            "Day1": "1일 AVG",
        }.get(interval, str(interval or "집계 주기 미상"))

    def _report_metric_interval(
        self,
        server_metrics: List[Dict[str, Any]],
        period: Dict[str, Any],
    ) -> str:
        supported = {"Min1", "Min5", "Min30", "Hour2", "Day1"}
        for metric in server_metrics:
            if not isinstance(metric, dict):
                continue
            interval = metric.get("metric_interval")
            if interval in supported:
                return str(interval)

        # Backward-compatible fallback for results generated before
        # metric_interval became part of the report model.
        start, end = self._period_bounds(period)
        if start is None or end is None:
            return "Day1"

        duration = max(end - start, 0)
        day = 24 * 60 * 60 * 1000
        if duration <= day:
            return "Min5"
        if duration <= 7 * day:
            return "Min30"
        if duration <= 31 * day:
            return "Hour2"
        return "Day1"

    def _metric_interval_millis(self, interval: str) -> int:
        return {
            "Min1": 60 * 1000,
            "Min5": 5 * 60 * 1000,
            "Min30": 30 * 60 * 1000,
            "Hour2": 2 * 60 * 60 * 1000,
            "Day1": 24 * 60 * 60 * 1000,
        }.get(interval, 5 * 60 * 1000)

    def _period_bounds(
        self,
        period: Dict[str, Any],
    ) -> Tuple[int | None, int | None]:
        return (
            event_timestamp_millis(
                period.get("start_time") or period.get("start_dt")
            ),
            event_timestamp_millis(
                period.get("end_time") or period.get("end_dt")
            ),
        )

    def _is_single_day_period(self, period: Dict[str, Any]) -> bool:
        if period.get("period_type") == "day":
            return True
        start, end = self._period_bounds(period)
        if start is None or end is None:
            return False
        start_date = datetime.fromtimestamp(
            start / 1000,
            tz=self.KST,
        ).date()
        end_date = datetime.fromtimestamp(
            end / 1000,
            tz=self.KST,
        ).date()
        return start_date == end_date

    def _metric_points(
        self,
        entry: Dict[str, Any],
    ) -> List[Tuple[int, float]]:
        points = entry.get("points")
        if not isinstance(points, list):
            raw = entry.get("raw")
            points = raw.get("dps") if isinstance(raw, dict) else []

        result = []
        for point in points or []:
            if isinstance(point, dict):
                timestamp = point.get("timestamp")
                value = point.get("value")
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                timestamp, value = point[0], point[1]
            else:
                continue

            try:
                normalized_time = float(timestamp)
                normalized_value = float(value)
            except (TypeError, ValueError):
                continue

            if abs(normalized_time) < 100_000_000_000:
                normalized_time *= 1000
            result.append((int(normalized_time), normalized_value))

        return result

    def _line_chart(
        self,
        title: str,
        series: Dict[str, List[Tuple[int, float]]],
        period: Dict[str, Any],
        y_axis: str,
        interval: str,
        unit: str = "%",
        *,
        chart_id: str,
    ) -> str:
        populated = {
            label: points
            for label, points in series.items()
            if points
        }
        if not populated:
            return (
                '<p class="empty-state chart-empty">'
                "표시할 시계열 데이터가 없습니다."
                "</p>"
            )

        all_times = sorted(
            {
                point_time
                for points in populated.values()
                for point_time, _ in points
            }
        )
        period_start, period_end = self._period_bounds(period)
        first_time = period_start if period_start is not None else all_times[0]
        last_time = period_end if period_end is not None else all_times[-1]
        time_span = max(last_time - first_time, 1)
        single_day = self._is_single_day_period(period)
        aggregation_label = self._metric_interval_label(interval)
        y_max = (
            100.0
            if y_axis == "fixed"
            else self._auto_axis_max(populated)
        )

        width = 1000
        height = 300
        left = 58
        right = 20
        top = 18
        bottom = 42
        plot_width = width - left - right
        plot_height = height - top - bottom

        grid_parts = []
        for tick_index in range(5):
            tick = y_max * tick_index / 4
            y = top + plot_height - (tick / y_max * plot_height)
            tick_label = self._chart_value_text(tick, unit, compact=True)
            grid_parts.append(
                f'<line x1="{left}" y1="{y:.2f}" '
                f'x2="{width - right}" y2="{y:.2f}" '
                'class="chart-grid-line"/>'
                f'<text x="{left - 10}" y="{y + 4:.2f}" '
                'class="chart-axis-label" text-anchor="end">'
                f"{self._text(tick_label)}</text>"
            )

        x_ticks = (first_time, first_time + time_span // 2, last_time)
        for tick_time in x_ticks:
            x = (
                left
                + ((tick_time - first_time) / time_span * plot_width)
            )
            tick_dt = datetime.fromtimestamp(
                tick_time / 1000,
                tz=self.KST,
            )
            tick_label = tick_dt.strftime(
                "%H:%M" if single_day else "%m-%d"
            )
            grid_parts.append(
                f'<text x="{x:.2f}" y="{height - 12}" '
                'class="chart-axis-label" text-anchor="middle">'
                f"{self._text(tick_label)}</text>"
            )

        line_parts = []
        legend_parts = []
        expected_interval = self._metric_interval_millis(interval)
        for index, (label, points) in enumerate(populated.items()):
            color = self.CHART_COLORS[index % len(self.CHART_COLORS)]
            series_id = f"{chart_id}-series-{index + 1}"
            series_parts = []
            for segment in self._split_chart_points(
                points,
                expected_interval=expected_interval,
            ):
                segment = self._downsample_chart_points(
                    segment,
                    max_points=self.MAX_CHART_POINTS_PER_SEGMENT,
                )
                coordinates = []
                circles = []
                tooltip_points = []
                show_markers = len(segment) <= 60
                for point_time, value in segment:
                    x = (
                        left
                        + (
                            (point_time - first_time)
                            / time_span
                            * plot_width
                        )
                    )
                    clamped_value = min(max(value, 0), y_max)
                    y = top + plot_height - (
                        clamped_value / y_max * plot_height
                    )
                    coordinates.append(f"{x:.2f},{y:.2f}")
                    tooltip_points.append([
                        round(x, 2),
                        point_time,
                        value,
                    ])
                    if show_markers:
                        circles.append(
                            f'<circle cx="{x:.2f}" cy="{y:.2f}" '
                            f'r="2.4" fill="{color}"><title>'
                            f"{self._text(label)} · "
                            f"{self._text(self._chart_point_label(point_time))} · "
                            f"{self._text(self._chart_value_text(value, unit))}"
                            "</title></circle>"
                        )

                tooltip_data = self._text(json.dumps(
                    tooltip_points,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ))
                hit_coordinates = (
                    coordinates
                    if len(coordinates) > 1
                    else coordinates * 2
                )
                series_parts.append(
                    f'<polyline points="{" ".join(coordinates)}" '
                    f'stroke="{color}" class="chart-line"><title>'
                    f"{self._text(label)}</title></polyline>"
                    + "".join(circles)
                    + f'<polyline points="{" ".join(hit_coordinates)}" '
                    'class="chart-hit-line" aria-hidden="true" '
                    f'data-chart-points="{tooltip_data}" '
                    f'data-chart-label="{self._text(label)}" '
                    f'data-chart-unit="{self._text(unit)}"/>'
                )
            line_parts.append(
                f'<g id="{series_id}" data-chart-series>'
                + "".join(series_parts)
                + "</g>"
            )
            legend_parts.append(
                '<button type="button" class="chart-legend-item" '
                f'title="{self._text(label)}" '
                f'data-chart-toggle="{series_id}" aria-controls="{series_id}" '
                'aria-pressed="false">'
                f'<i style="background:{color}" aria-hidden="true"></i>'
                f"<span>{self._text(label)}</span></button>"
            )

        return (
            f'<div class="chart" id="{chart_id}" role="group" '
            f'aria-label="{self._text(title)} '
            f'{self._text(aggregation_label)} 변화 그래프">'
            '<div class="chart-toolbar">'
            '<label>PNG 크기 <select data-chart-export-width>'
            '<option value="1000">1000 × 300</option>'
            '<option value="2000" selected>2000 × 600</option>'
            '<option value="3000">3000 × 900</option>'
            '</select></label>'
            '<button type="button" data-chart-download>그래프 PNG 저장</button>'
            '</div>'
            f'<svg viewBox="0 0 {width} {height}" '
            'preserveAspectRatio="xMidYMid meet" role="img" '
            f'aria-label="{self._text(title)}">'
            '<style>.chart-grid-line{stroke:#e2e8f0;stroke-width:1}'
            '.chart-axis-label{fill:#64748b;font:13px Arial,sans-serif}'
            '.chart-line{fill:none;stroke-width:2.4;stroke-linejoin:round;'
            'stroke-linecap:round}.chart-hit-line{fill:none;stroke:transparent;'
            'stroke-width:18;stroke-linecap:round;pointer-events:stroke}'
            '.chart-series-hidden{display:none}</style>'
            + "".join(grid_parts)
            + "".join(line_parts)
            + ('</svg><div class="chart-tooltip" data-chart-tooltip '
               'role="status" aria-live="polite" aria-atomic="true" '
               'hidden></div><div class="chart-legend">')
            + "".join(legend_parts)
            + "</div></div>"
        )

    def _chart_value_text(
        self,
        value: float,
        unit: str,
        compact: bool = False,
    ) -> str:
        unit_text = str(unit or "").strip()
        normalized = unit_text.casefold().replace(" ", "")

        if normalized in {"%", "percent", "percentage"}:
            precision = 0 if compact or abs(value) >= 1 else 1
            return f"{value:.{precision}f}%"

        byte_rate_units = {
            "b/s", "byte/s", "bytes/s", "byte/sec", "bytes/sec",
            "bps",
        }
        byte_units = {"b", "byte", "bytes"}
        if normalized in byte_rate_units or normalized in byte_units:
            suffix = "/s" if normalized in byte_rate_units else ""
            scaled = float(value)
            prefix = "B"
            for candidate in ("KiB", "MiB", "GiB", "TiB"):
                if abs(scaled) < 1024:
                    break
                scaled /= 1024
                prefix = candidate
            precision = 0 if compact and abs(scaled) >= 10 else 1
            return f"{scaled:,.{precision}f} {prefix}{suffix}"

        if compact:
            absolute = abs(value)
            for divisor, suffix in (
                (1_000_000_000, "B"),
                (1_000_000, "M"),
                (1_000, "K"),
            ):
                if absolute >= divisor:
                    return f"{value / divisor:.1f}{suffix}"

        number = (
            f"{value:,.0f}"
            if abs(value) >= 1 or value == 0
            else f"{value:,.2f}"
        )
        if normalized in {"", "num", "number", "count", "ea"}:
            return number
        if normalized in {"num/s", "number/s", "count/s", "count/sec"}:
            return f"{number}/s"
        return f"{number} {unit_text}"

    def _chart_point_label(
        self,
        timestamp: int,
    ) -> str:
        point_dt = datetime.fromtimestamp(
            timestamp / 1000,
            tz=self.KST,
        )
        return point_dt.strftime("%Y-%m-%d %H:%M KST")

    def _auto_axis_max(
        self,
        series: Dict[str, List[Tuple[int, float]]],
    ) -> float:
        maximum = max(
            value
            for points in series.values()
            for _, value in points
        )
        target = max(maximum * 1.1, 1)
        magnitude = 10 ** math.floor(math.log10(target))
        normalized = target / magnitude

        for step in (1, 1.25, 1.5, 2, 2.5, 5, 10):
            if normalized <= step:
                return float(step * magnitude)
        return float(10 * magnitude)

    def _split_chart_points(
        self,
        points: List[Tuple[int, float]],
        expected_interval: int,
    ) -> List[List[Tuple[int, float]]]:
        if not points:
            return []

        segments = [[points[0]]]
        gap_limit = expected_interval * 2.5
        for point in points[1:]:
            if point[0] - segments[-1][-1][0] > gap_limit:
                segments.append([point])
            else:
                segments[-1].append(point)
        return segments

    @staticmethod
    def _downsample_chart_points(
        points: List[Tuple[int, float]],
        max_points: int,
    ) -> List[Tuple[int, float]]:
        """Bound SVG size while preserving the first, last, min and max."""
        if max_points <= 0:
            return []
        if len(points) <= max_points:
            return list(points)
        if max_points == 1:
            return [points[0]]
        if max_points == 2:
            return [points[0], points[-1]]

        bucket_count = max((max_points - 2) // 2, 1)
        interior = points[1:-1]
        bucket_size = max(math.ceil(len(interior) / bucket_count), 1)
        selected = [points[0]]
        for start in range(0, len(interior), bucket_size):
            bucket = interior[start:start + bucket_size]
            extrema = {
                min(range(len(bucket)), key=lambda index: bucket[index][1]),
                max(range(len(bucket)), key=lambda index: bucket[index][1]),
            }
            selected.extend(bucket[index] for index in sorted(extrema))
        selected.append(points[-1])
        if len(selected) <= max_points:
            return selected

        # Rounding can create one extra bucket. Keep the temporal endpoints.
        interior_limit = max_points - 2
        return [selected[0], *selected[1:-1][:interior_limit], selected[-1]]

    def _event_table(self, rows: Any) -> str:
        prepared = []
        sorted_rows = sort_event_records(
            self._records(rows),
            ("event_time", "start_time", "time", "timestamp"),
        )
        for row in sorted_rows:
            prepared.append(
                {
                    "source_state_text": self._source_state_text(OBSERVED),
                    "time": self._first(
                        row,
                        "start_time_kst",
                        "event_time",
                        "time",
                        "timestamp",
                        "start_time",
                    ),
                    "severity": self._first(
                        row,
                        "severity",
                        "level",
                        "event_level",
                        "status",
                    ),
                    "resource": self._first(
                        row,
                        "resource_name",
                        "resource_id",
                        "target_name",
                        "target_id",
                        "nrn",
                    ),
                    "type": self._first(
                        row,
                        "event_type",
                        "type",
                        "rule_name",
                        "metric",
                    ),
                    "message": self._first(
                        row,
                        "message",
                        "description",
                        "reason",
                        "event_message",
                        "condition",
                    ),
                    "condition": self._insight_event_condition(row),
                    "details": self._insight_event_details(row),
                }
            )

        return self._table(
            prepared,
            (
                ("time", "시각"),
                ("source_state_text", "출처 상태"),
                ("severity", "심각도"),
                ("resource", "리소스"),
                ("type", "유형"),
                ("condition", "발생 조건/감지값"),
                ("message", "설명"),
                ("details", "상세", "details"),
            ),
        )

    def _insight_event_condition(self, row: Dict[str, Any]) -> str:
        metric = self._first_present(row.get("metric"))
        detected = self._first_present(row.get("detect_value"))
        operator = self._first_present(
            row.get("operator_symbol"),
            row.get("operator"),
        )
        criteria = self._first_present(row.get("criteria"))
        unit = self._first_present(row.get("unit"))

        condition = " ".join(
            part for part in (metric, operator, criteria) if part
        )
        if detected:
            condition = (
                f"{condition} / 감지 {detected}{unit}"
                if condition
                else f"감지 {detected}{unit}"
            )
        return condition or "-"

    def _insight_event_details(self, row: Dict[str, Any]) -> str:
        fields = (
            ("이벤트 ID", row.get("event_id")),
            ("이벤트 룰", row.get("rule_name")),
            ("룰 ID", row.get("rule_id")),
            ("설명", row.get("description")),
            ("메트릭", row.get("metric")),
            ("메트릭 그룹 항목 ID", row.get("metric_group_item_id")),
            ("이벤트 상세 키", row.get("calc_sliding_group_key")),
            ("집계 함수", row.get("calc")),
            ("집계 주기", row.get("interval")),
            ("발생 시각", row.get("start_time_kst")),
            ("종료 시각", row.get("end_time_kst")),
            ("상품", row.get("prod_name")),
            ("리소스 ID", row.get("resource_id")),
            ("리전", row.get("region_code")),
            ("존", row.get("zone_code")),
            ("차원", row.get("dimension")),
            ("통보 그룹", row.get("notification_groups")),
            ("통보 상태", row.get("notification_status")),
            ("유지보수 중", row.get("in_maintenance")),
            ("삭제된 리소스", row.get("resource_deleted")),
        )
        items = []
        for label, value in fields:
            if value is None or value == "" or value == [] or value == {}:
                continue
            if isinstance(value, (dict, list)):
                rendered_value = json.dumps(
                    value,
                    ensure_ascii=False,
                    default=str,
                )
            elif isinstance(value, bool):
                rendered_value = "예" if value else "아니오"
            else:
                rendered_value = str(value)
            if len(rendered_value) > 300:
                rendered_value = rendered_value[:297] + "..."
            items.append(
                "<div><dt>"
                + self._text(label)
                + "</dt><dd>"
                + self._text(rendered_value)
                + "</dd></div>"
            )

        if not items:
            return "-"
        return (
            '<details class="event-details"><summary>'
            "상세 정보"
            "</summary><dl>"
            + "".join(items)
            + "</dl></details>"
        )

    def _collection_diagnostics(
        self,
        *,
        warnings: Any,
        errors: Any,
    ) -> List[Dict[str, Any]]:
        """구형·신형 스냅샷의 경고와 오류를 하나의 표시 목록으로 합친다."""
        prepared = [
            normalize_collection_issue(row, default_severity="error")
            for row in self._records(errors)
        ]
        prepared.extend(
            normalize_collection_issue(row, default_severity="warning")
            for row in self._records(warnings)
        )
        return prepared

    def _diagnostic_table(self, rows: Any) -> str:
        """수집 진단을 심각도와 NCP 상품/대상 중심으로 표시한다."""
        prepared = []
        for row in self._records(rows):
            prepared.append(
                {
                    "severity": row.get("severity_label"),
                    "target": row.get("target"),
                    "collector": row.get("collector"),
                    "stage": row.get("stage"),
                    "api": row.get("called_api")
                    or row.get("api")
                    or row.get("source")
                    or "API 미확인 (구형 진단 데이터)",
                    "status": row.get("status_code"),
                    "code": row.get("error_code") or row.get("code"),
                    "permission": self._diagnostic_permission(row),
                    "message": row.get("message"),
                }
            )

        return self._table(
            prepared,
            (
                ("severity", "구분"),
                ("target", "NCP 상품 / 대상"),
                ("collector", "수집기"),
                ("stage", "단계"),
                ("api", "호출 API"),
                ("status", "HTTP 상태"),
                ("code", "코드"),
                ("permission", "확인할 권한 / 근거"),
                ("message", "메시지"),
            ),
        )

    @staticmethod
    def _diagnostic_permission(row: Mapping[str, Any]) -> str:
        """확정 응답과 API 카탈로그 권고를 혼동하지 않게 표시한다."""

        source = str(row.get("permission_source") or "not_applicable")
        if source == "not_applicable":
            return "-"
        if source == "unknown" and not row.get("permission_write_actions"):
            return "권한명 미확인 · NCP 응답에 액션 없음"

        actions = row.get("permission_actions")
        safe_actions = (
            [str(action) for action in actions]
            if isinstance(actions, (list, tuple))
            else []
        )
        service_name = str(
            row.get("permission_service_name")
            or row.get("service_name")
            or "NCP"
        )
        if source == "provider_response":
            basis = "NCP 응답 확인"
        else:
            catalog_basis = str(row.get("permission_basis") or "")
            basis_detail = {
                "parent_detail_inference": "부모 상세 권한 추정",
                "operation_semantics": "공식 권한표 기능 대응",
                "official_action_table": "공식 권한표 대응",
            }.get(catalog_basis, "공식 권한표 대응")
            basis = f"호출 API 기준 권고 · {basis_detail}"

        parts = []
        if safe_actions:
            parts.append(f"{service_name}: {', '.join(safe_actions)} ({basis})")

        write_actions = row.get("permission_write_actions")
        if isinstance(write_actions, (list, tuple)) and write_actions:
            parts.append(
                "NCP 응답 쓰기 권한 감지: "
                + ", ".join(str(action) for action in write_actions)
                + " (부여 권고 안 함)"
            )

        related_actions = row.get("permission_related_actions")
        if isinstance(related_actions, (list, tuple)) and related_actions:
            parts.append(
                "연관 권한(공식 권한표 기준): "
                + ", ".join(str(action) for action in related_actions)
            )

        managed_policy = row.get("permission_managed_policy")
        if managed_policy:
            parts.append(
                "관리형 대안(공식 권한표 기준): "
                + str(managed_policy)
            )

        security_note = row.get("permission_security_note")
        if security_note:
            parts.append(f"보안 주의: {security_note}")

        return " · ".join(parts) or "권한명 미확인 · NCP 응답에 액션 없음"

    def _activity_table(self, rows: Any) -> str:
        prepared = []
        sorted_rows = sort_event_records(
            self._records(rows),
            ("event_time", "event_time_kst", "time", "timestamp"),
        )
        for row in sorted_rows:
            prepared.append(
                {
                    **row,
                    "source_state_text": self._source_state_text(OBSERVED),
                    "display_event_time": (
                        row.get("event_time_kst")
                        or row.get("event_time")
                    ),
                    "actor": self._activity_actor(row),
                    "target": self._activity_target(row),
                    "details": self._activity_details(row),
                }
            )

        return self._table(
            prepared,
            (
                ("display_event_time", "발생 시각 (KST)"),
                ("source_state_text", "출처 상태"),
                ("actor", "수행 계정"),
                ("product_display_name", "서비스"),
                ("target", "대상 객체"),
                ("action_name", "작업"),
                ("result", "결과"),
                ("source_ip", "접속 IP"),
                ("details", "상세", "details"),
            ),
        )

    def _activity_attention_summary(
        self,
        report: ReportResult,
        rows: List[Dict[str, Any]],
    ) -> Tuple[str, str]:
        summary = summarize_activity_events(rows)
        groups = group_activity_events(rows)
        changes = self._mapping(
            self._mapping(report.analysis).get("changes")
        )
        collection_status = str(changes.get("status") or "").upper()
        if not collection_status:
            collection_status = (
                "AVAILABLE" if summary["total_count"] else "UNAVAILABLE"
            )

        if not rows and collection_status != "COLLECTED_EMPTY":
            label = {
                "FAILED": "수집 실패 · 판정 불가",
                "PARTIAL": "부분 수집 · 확인된 이력 없음 · 판정 불가",
                "NOT_REQUESTED": "수집 대상 아님 · 판정 불가",
            }.get(
                collection_status,
                "표시할 이력 없음 · 수집 상태 미확인",
            )
            return (
                '<section class="activity-attention-summary" '
                'aria-label="Activity Tracer 담당자 확인 요약">'
                '<h3>담당자 확인 요약</h3>'
                f'<p>{self._text(label)}</p>'
                '<div class="operational-status-grid">'
                + self._analysis_status_card(
                    "Activity Tracer",
                    "판정 불가",
                    {
                        "FAILED": "failed",
                        "PARTIAL": "caution",
                    }.get(collection_status, "unknown"),
                    (
                        dataset_source_state(collection_status)
                        if collection_status == "FAILED"
                        else UNAVAILABLE
                    ),
                    details_html=(
                        '<p class="status-evidence-copy">'
                        f'{self._text(label)}. Activity Tracer 수집 상태와 '
                        '수집 진단을 확인한 뒤 다시 수집하십시오.</p>'
                    ),
                )
                + "</div></section>",
                label,
            )

        source_state = CALCULATED
        cards = [
            self._analysis_status_card(
                label,
                f'{summary[key]:,}건',
                active_status if summary[key] else "normal",
                source_state,
                details_html=self._activity_summary_detail(
                    groups[group_key],
                    criteria,
                ),
            )
            for label, key, group_key, active_status, criteria in (
                (
                    "로그인 실패",
                    "login_failure_count",
                    "login_failure",
                    "risk",
                    "로그인·SignIn 작업 중 결과가 실패·오류·거부인 이벤트입니다.",
                ),
                (
                    "전체 실패·거부 작업",
                    "failure_count",
                    "failure",
                    "risk",
                    "결과가 실패·오류·거부로 명시된 전체 이벤트입니다.",
                ),
                (
                    "생성·추가 성공",
                    "created_success_count",
                    "created_success",
                    "normal",
                    "Create·Add·Attach·Register·Associate·Assign 계열 작업 중 성공 이벤트입니다.",
                ),
                (
                    "삭제·분리 성공",
                    "deleted_success_count",
                    "deleted_success",
                    "caution",
                    "Delete·Remove·Detach·Terminate·Deregister·Disassociate·Unassign 계열 작업 중 성공 이벤트입니다.",
                ),
            )
        ]
        if summary["unknown_result_count"]:
            cards.append(self._analysis_status_card(
                "결과 미확인",
                f'{summary["unknown_result_count"]:,}건',
                "caution",
                source_state,
                details_html=self._activity_summary_detail(
                    groups["unknown_result"],
                    "결과 값이 성공 또는 실패·오류·거부로 식별되지 않은 이벤트입니다.",
                ),
            ))

        status_prefix = {
            "PARTIAL": (
                f'부분 수집 · 확인된 {summary["total_count"]:,}건 기준'
            ),
            "COLLECTED_EMPTY": "수집 완료 · 이력 없음",
            "FAILED": (
                f'수집 실패 · 확인된 {summary["total_count"]:,}건만 표시'
            ),
            "UNAVAILABLE": (
                f'수집 상태 미확인 · 표시된 {summary["total_count"]:,}건 기준'
            ),
        }.get(
            collection_status,
            f'관측 {summary["total_count"]:,}건 기준',
        )
        failure_text = f'전체 실패·거부 {summary["failure_count"]:,}건'
        if summary["login_failure_count"]:
            failure_text += f' (로그인 {summary["login_failure_count"]:,}건)'
        collapsed_parts = [
            status_prefix,
            failure_text,
            f'생성·추가 성공 {summary["created_success_count"]:,}건',
            f'삭제·분리 성공 {summary["deleted_success_count"]:,}건',
        ]
        if summary["unknown_result_count"]:
            collapsed_parts.append(
                f'결과 미확인 {summary["unknown_result_count"]:,}건'
            )
        collapsed_summary = " · ".join(collapsed_parts)
        content = (
            '<section class="activity-attention-summary" '
            'aria-label="Activity Tracer 담당자 확인 요약">'
            '<h3>담당자 확인 요약</h3>'
            '<p>성공으로 기록된 명시적 생성·추가·삭제·분리 작업과 실패 기록을 '
            '요약합니다. 실제 자원 상태는 인벤토리와 함께 확인하십시오.</p>'
            f'<div class="operational-status-grid">{"".join(cards)}</div>'
            '</section>'
        )
        return content, collapsed_summary

    def _activity_summary_detail(
        self,
        rows: Sequence[Mapping[str, Any]],
        criteria: str,
    ) -> str:
        safe_rows = [
            {
                "event_time": row.get("event_time_kst") or row.get("event_time"),
                "product": (
                    row.get("product_display_name")
                    or row.get("product_name")
                    or "-"
                ),
                "target": row.get("resource_name") or row.get("resource_id") or "-",
                "action": row.get("action_name") or "-",
                "result": row.get("result") or "-",
            }
            for row in rows
        ]
        evidence = (
            self._table(
                safe_rows,
                (
                    ("event_time", "발생 시각 (KST)"),
                    ("product", "서비스"),
                    ("target", "대상"),
                    ("action", "작업"),
                    ("result", "결과"),
                ),
            )
            if safe_rows
            else '<p class="empty-state">해당 이벤트가 없습니다.</p>'
        )
        return (
            f'<p class="status-evidence-copy">{self._text(criteria)} '
            '계정·접속 IP·원시 응답은 이 요약에 표시하지 않습니다.</p>'
            f'{evidence}'
        )

    def _activity_actor(self, row: Dict[str, Any]) -> str:
        product_data = row.get("product_data")
        if not isinstance(product_data, dict):
            product_data = {}

        actor = self._first_present(
            row.get("user_name"),
            product_data.get("userName"),
            product_data.get("subAccountId"),
            row.get("sub_account_no"),
            row.get("member_no"),
        )
        user_type = self._first_present(
            row.get("user_type"),
            product_data.get("userType"),
        )

        if actor and user_type:
            return f"{actor} ({user_type})"
        return actor or user_type or "-"

    def _activity_target(self, row: Dict[str, Any]) -> str:
        product_data = row.get("product_data")
        if not isinstance(product_data, dict):
            product_data = {}

        target = self._first_present(
            row.get("resource_name"),
            product_data.get("resourceName"),
            product_data.get("serverName"),
            product_data.get("computeInstanceName"),
            product_data.get("dbServerName"),
            product_data.get("dbServiceName"),
            product_data.get("vpcName"),
            product_data.get("name"),
            row.get("resource_id"),
            row.get("nrn"),
        )
        resource_type = self._first_present(row.get("resource_type"))

        if target and resource_type:
            return f"{resource_type}: {target}"
        return target or resource_type or "-"

    def _activity_details(self, row: Dict[str, Any]) -> str:
        product_data = row.get("product_data")
        if not isinstance(product_data, dict):
            return "-"

        items = []
        for key, value in product_data.items():
            if self._is_sensitive_detail_key(str(key)):
                continue
            if value is None or value == "" or value == [] or value == {}:
                continue

            if isinstance(value, (dict, list)):
                rendered_value = json.dumps(
                    value,
                    ensure_ascii=False,
                    default=str,
                )
            else:
                rendered_value = str(value)

            if len(rendered_value) > 300:
                rendered_value = rendered_value[:297] + "..."

            items.append(
                "<div><dt>"
                + self._text(key)
                + "</dt><dd>"
                + self._text(rendered_value)
                + "</dd></div>"
            )

        if not items:
            return "-"

        visible_items = items[:30]
        remaining = len(items) - len(visible_items)
        remaining_text = (
            f'<p class="detail-more">외 {remaining:,}개 필드</p>'
            if remaining
            else ""
        )
        return (
            '<details class="event-details"><summary>'
            "상세 정보"
            "</summary><dl>"
            + "".join(visible_items)
            + "</dl>"
            + remaining_text
            + "</details>"
        )

    def _is_sensitive_detail_key(self, key: str) -> bool:
        normalized = "".join(
            character
            for character in key.lower()
            if character.isalnum()
        )
        sensitive_terms = (
            "password",
            "secret",
            "token",
            "credential",
            "authorization",
            "cookie",
            "accesskey",
            "apikey",
            "privatekey",
            "mfainfo",
            "otp",
        )
        return any(term in normalized for term in sensitive_terms)

    def _first_present(self, *values: Any) -> str:
        for value in values:
            if value is not None and str(value).strip():
                return str(value)
        return ""

    def _table(
        self,
        rows: List[Dict[str, Any]],
        columns: Sequence[Tuple[str, str] | Tuple[str, str, str]],
        *,
        resource_category_key: str = "",
    ) -> str:
        if not rows:
            return '<p class="empty-state">표시할 데이터가 없습니다.</p>'

        detail_columns = [
            column
            for column in columns
            if len(column) > 2 and column[2] == "details"
        ]
        visible_columns = [
            column for column in columns if column not in detail_columns
        ]
        header = "".join(
            f"<th scope=\"col\">{self._text(column[1])}</th>"
            for column in visible_columns
        )
        body_rows = []

        for row in rows:
            cells = []
            for column in visible_columns:
                key = column[0]
                format_name = column[2] if len(column) > 2 else "text"
                value = self._format_value(row.get(key), format_name)
                numeric_class = (
                    ' class="numeric"'
                    if format_name.startswith("number")
                    or format_name == "percent"
                    else ""
                )
                cells.append(f"<td{numeric_class}>{value}</td>")
            category_attribute = (
                ' data-resource-category="'
                + self._text(row.get(resource_category_key))
                + '"'
                if resource_category_key
                else ""
            )
            row_start = (
                f'<tr class="table-data-row"{category_attribute}>'
                if detail_columns
                else f"<tr{category_attribute}>"
            )
            data_row = row_start + "".join(cells) + "</tr>"
            if not detail_columns:
                body_rows.append(data_row)
                continue

            detail_values = [
                self._format_value(row.get(column[0]), "details")
                for column in detail_columns
                if isinstance(row.get(column[0]), str)
                and str(row.get(column[0])).strip() not in {"", "-"}
            ]
            detail_row = (
                '<tr class="table-detail-row"><td '
                f'colspan="{len(visible_columns)}">'
                + "".join(detail_values)
                + "</td></tr>"
                if detail_values
                else ""
            )
            record_class = (
                "table-record has-detail" if detail_row else "table-record"
            )
            body_rows.append(
                f'<tbody class="{record_class}">{data_row}{detail_row}</tbody>'
            )

        if detail_columns:
            return (
                '<div class="table-wrap table-wrap-with-details">'
                '<table class="table-with-details">'
                "<thead><tr>"
                + header
                + "</tr></thead>"
                + "".join(body_rows)
                + "</table></div>"
            )
        return (
            '<div class="table-wrap"><table><thead><tr>'
            + header
            + "</tr></thead><tbody>"
            + "".join(body_rows)
            + "</tbody></table></div>"
        )

    def _format_value(self, value: Any, format_name: str) -> str:
        if format_name == "number0":
            if value is None or value == "":
                return "-"
            return self._text(self._number(value, decimals=0))
        if format_name == "number3":
            if value is None or value == "":
                return "-"
            return self._text(self._number(value, decimals=3))
        if format_name == "percent":
            if value is None or value == "":
                return "-"
            return self._text(f"{self._number(value, decimals=2)}%")
        if format_name in {"html", "details"}:
            return value if isinstance(value, str) else self._text(value)
        return self._text(value)

    def _filesystem_text(self, value: Any) -> str:
        if not isinstance(value, list):
            return "-"

        items = []
        for entry in value:
            if not isinstance(entry, dict):
                continue
            mount = entry.get("mount") or "-"
            average = self._finite_number(entry.get("avg"))
            maximum = self._finite_number(entry.get("max"))
            average_text = (
                f"{self._number(average, decimals=2)}%"
                if average is not None else "-"
            )
            maximum_text = (
                f"{self._number(maximum, decimals=2)}%"
                if maximum is not None else "-"
            )
            items.append(
                f"{mount} · 평균 {average_text} / 최대 {maximum_text}"
            )
        return ", ".join(items) or "-"

    def _first(self, row: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return value
        return "-"

    @staticmethod
    def _mapping(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _display_period_start(self, period: Dict[str, Any]) -> str:
        value = str(period.get("start_dt") or "-")
        if period.get("period_type") != "datetime_range":
            return value[:10]
        return value

    def _display_period_end(self, period: Dict[str, Any]) -> str:
        value = str(period.get("end_dt") or "-")
        if value == "-":
            return value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if period.get("end_exclusive"):
                parsed -= timedelta(microseconds=1)
            if period.get("period_type") != "datetime_range":
                return parsed.strftime("%Y-%m-%d")
            return parsed.isoformat(sep=" ", timespec="seconds")
        except ValueError:
            return value

    def _billing_fact_cards(self, facts: List[Dict[str, Any]]) -> str:
        labels = {
            "CONFIRMED": "확정 청구 데이터",
            "PERIOD_ESTIMATE": "보고 기간 추정 데이터",
            "MONTH_TO_DATE_ESTIMATE": "보고 기준일까지 누적 추정 데이터",
            "MONTH_END_PROJECTION": "월 전체 금액 (1일~말일)",
        }
        basis_labels = {
            "INVOICE_TOTAL": "NCP 발행 청구서 총액",
            "CURRENT_MONTH_INVOICE_TOTAL": "NCP 해당 월 확정 금액 (VAT 포함)",
            "PRE_DISCOUNT_LIST_PRICE": "사용량 × 단가 (할인·VAT 전)",
            "DAILY_RUN_RATE_PROJECTION": "월 누적 일평균 추세 예측",
            "NCP_PRODUCT_DEMAND_USE_AMOUNT": "NCP 서비스별 누적 사용금액 (할인·VAT 전)",
            "NCP_CONTRACT_DEMAND_USE_AMOUNT": (
                "NCP 계약별 사용금액 fallback (할인·VAT 전)"
            ),
            "NCP_CURRENT_USE_AMOUNT_FALLBACK": (
                "NCP 현재월 반환 사용금액 (복합요금 fallback)"
            ),
            "PROJECTED_USAGE_RERATED": "월말 예상 사용량에 요금제를 다시 적용",
            "NCP_ACCRUED_PLUS_USAGE_FORECAST": "NCP 누적 사용금액 + 월말 사용량 예측",
            "NCP_ACCRUED_LOWER_BOUND": (
                "NCP 현재 누적 사용금액 (복합요금 월말 하한)"
            ),
        }
        cards = []
        for fact in facts:
            status = str(fact.get("status") or "UNAVAILABLE")
            collected_source_state = dataset_source_state(status)
            source_state = (
                collected_source_state
                if collected_source_state != OBSERVED
                else (
                    OBSERVED
                    if str(fact.get("cost_type") or "").upper()
                    == "CONFIRMED"
                    else CALCULATED
                )
            )
            amount = (
                self._number(fact.get("total_amount"), 0) + "원"
                if fact.get("total_amount") is not None else "조회 불가"
            )
            period_text = (
                f"{fact.get('period_start') or '-'} ~ "
                f"{fact.get('period_end') or '-'}"
            )
            coverage_text = (
                f"{fact.get('coverage_start') or '-'} ~ "
                f"{fact.get('coverage_end') or '-'}"
            )
            invoice_breakdown = ""
            if fact.get("cost_type") == "CONFIRMED" and status == "AVAILABLE":
                invoice_breakdown = (
                    "<li><span>공급가액 / VAT</span><strong>"
                    f"{self._number(fact.get('subtotal_amount'), 0)}원 / "
                    f"{self._number(fact.get('vat_amount'), 0)}원"
                    "</strong></li>"
                    "<li><span>할인 내역 합계 (참고)</span><strong>"
                    f"{self._number(fact.get('discount_amount'), 0)}원"
                    "</strong></li>"
                )
            estimate_quality = ""
            if fact.get("cost_type") != "CONFIRMED":
                details = self._mapping(fact.get("details"))
                estimate_quality = (
                    "<li><span>계산 품질</span><strong>"
                    f"제외 {self._number(fact.get('excluded_item_count') or 0, 0)}개 / "
                    f"추론 {self._number(details.get('inferred_item_count') or 0, 0)}개"
                    "</strong></li>"
                )
            included = (
                f"할인 {'포함' if fact.get('includes_discount') else '미포함'}, "
                f"VAT {'포함' if fact.get('includes_vat') else '미포함'}"
            )
            breakdown_rows = self._records(
                fact.get("_service_breakdown")
            )
            service_count = sum(
                not row.get("is_adjustment") for row in breakdown_rows
            )
            breakdown_html = (
                self._table(
                    breakdown_rows,
                    (
                        ("service_name", "서비스·조정 항목"),
                        ("amount", "금액(원)", "number0"),
                    ),
                )
                if breakdown_rows
                else (
                    '<p class="empty-state">이 기준에 연결된 서비스별 '
                    "금액 데이터가 없습니다.</p>"
                )
            )
            cost_type = str(fact.get("cost_type") or "")
            card_id = {
                "CONFIRMED": "billing-cost-confirmed",
                "PERIOD_ESTIMATE": "billing-cost-period-estimate",
                "MONTH_TO_DATE_ESTIMATE": "billing-cost-month-to-date",
                "MONTH_END_PROJECTION": "billing-cost-month-end",
            }.get(cost_type, "")
            id_attribute = f' id="{card_id}"' if card_id else ""
            body_id_attribute = (
                f' id="{card_id}-detail"' if card_id else ""
            )
            controls_attribute = (
                f' aria-controls="{card_id}-detail"' if card_id else ""
            )
            cards.append(
                f'<details class="billing-fact"{id_attribute}>'
                f"<summary{controls_attribute}>"
                '<span class="billing-fact-title" role="heading" aria-level="3">'
                f"{self._text(labels.get(cost_type, cost_type))}</span>"
                f'<strong class="billing-amount">{self._text(amount)}</strong>'
                '<small class="billing-fact-hint">'
                f"서비스 {service_count:,}개 구성 및 산정 근거 보기</small>"
                "</summary>"
                f'<div class="billing-fact-body"{body_id_attribute}>'
                "<ul>"
                f"<li><span>대상 기간</span><strong>{self._text(period_text)}</strong></li>"
                f"<li><span>실제 수집 범위</span><strong>{self._text(coverage_text)}</strong></li>"
                f"<li><span>계산 기준 시각</span><strong>{self._text(fact.get('calculated_at'))}</strong></li>"
                f"<li><span>금액 기준</span><strong>{self._text(basis_labels.get(str(fact.get('amount_basis')), fact.get('amount_basis')))}</strong></li>"
                f"<li><span>포함 범위</span><strong>{self._text(included)}</strong></li>"
                f"<li><span>신뢰도</span><strong>{self._text(fact.get('confidence'))}</strong></li>"
                f"<li><span>출처 상태</span><strong>{self._text(self._source_state_text(source_state))}</strong></li>"
                f"{estimate_quality}"
                f"{invoice_breakdown}"
                "</ul>"
                '<h4>서비스별 금액 구성</h4>'
                f"{breakdown_html}"
                '<p class="billing-fact-total"><span>카드 합계</span>'
                f"<strong>{self._text(amount)}</strong></p>"
                "</div></details>"
            )
        return (
            '<div class="billing-facts" id="billing-cost-basis">'
            + "".join(cards)
            + "</div>"
        )

    def _organization_cost_sections(
        self, accounts: List[Dict[str, Any]]
    ) -> str:
        if not accounts:
            return ""
        articles = []
        cost_totals: Dict[str, float] = defaultdict(float)
        available_cost_types = set()
        for account in accounts:
            facts = {
                str(item.get("cost_type")): item
                for item in self._records(account.get("cost_facts"))
            }
            confirmed = facts.get("CONFIRMED", {})
            current_provisional = facts.get("CURRENT_PROVISIONAL", {})
            projection = facts.get("MONTH_END_PROJECTION", {})
            for cost_type, fact in (
                ("CONFIRMED", confirmed),
                ("CURRENT_PROVISIONAL", current_provisional),
            ):
                amount = self._finite_number(fact.get("total_amount"))
                if amount is not None:
                    cost_totals[cost_type] += amount
                    available_cost_types.add(cost_type)
            confirmed_services = self._records(account.get("service_summary"))
            expected_services = self._records(
                account.get("current_service_summary")
            )
            confirmed_text = (
                self._number(confirmed.get("total_amount"), 0) + "원"
                if confirmed.get("total_amount") is not None else "조회 불가"
            )
            provisional_text = (
                self._number(current_provisional.get("total_amount"), 0) + "원"
                if current_provisional.get("total_amount") is not None
                else "해당 없음"
            )
            projection_text = (
                self._number(projection.get("total_amount"), 0) + "원"
                if projection.get("total_amount") is not None else "해당 없음"
            )
            metrics = (
                f"<li><span>확정 청구액</span><strong>{confirmed_text}</strong></li>"
                f"<li><span>NCP 현재월 누적 예상(VAT 전)</span><strong>{provisional_text}</strong></li>"
                f"<li><span>월말 단순 예측(참고)</span><strong>{projection_text}</strong></li>"
            )
            articles.append(
                '<article class="billing-fact organization-account">'
                f"<h3>{self._text(account.get('display_name') or account.get('member_no'))}"
                f" <small>{self._text(account.get('member_no'))}</small></h3>"
                f"<ul>{metrics}</ul>"
                "<h4>확정 서비스별 비용</h4>"
                + self._table(confirmed_services, (
                    ("service_name", "서비스"), ("amount", "금액", "number0"),
                    ("row_count", "항목", "number0"),
                ))
                + "<h4>NCP 현재월 서비스별 예상 비용</h4>"
                + self._table(expected_services, (
                    ("service_name", "서비스"), ("amount", "금액(VAT 전)", "number0"),
                    ("row_count", "항목", "number0"),
                ))
                + "</article>"
            )
        cost_summary = []
        if "CONFIRMED" in available_cost_types:
            cost_summary.append(
                f"확정 합계 {self._number(cost_totals['CONFIRMED'], 0)}원"
            )
        if "CURRENT_PROVISIONAL" in available_cost_types:
            cost_summary.append(
                "현재월 예상 합계(VAT 전) "
                f"{self._number(cost_totals['CURRENT_PROVISIONAL'], 0)}원"
            )
        return self._section(
            "Organization 계정별 비용",
            "Organization 마스터 계정으로 확인된 경우에만 하위 계정별 비용을 표시합니다.",
            '<div class="billing-facts">' + "".join(articles) + "</div>",
            len(accounts),
            collapsed=True,
            collapsed_summary=" · ".join(cost_summary) or "비용 수치 없음",
        )

    def _records(self, value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict)]

    def _flatten_grouped(self, value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, list):
            return sort_event_records(
                self._records(value),
                ("event_time", "event_time_kst", "time", "timestamp"),
            )
        if not isinstance(value, dict):
            return []

        result = []
        seen = set()
        for rows in value.values():
            for row in self._records(rows):
                identity = (
                    row.get("event_id")
                    or row.get("historyId")
                    or id(row)
                )
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(row)
        return sort_event_records(
            result,
            ("event_time", "event_time_kst", "time", "timestamp"),
        )

    def _number(self, value: Any, decimals: int) -> str:
        try:
            return f"{float(value or 0):,.{decimals}f}"
        except (TypeError, ValueError):
            return "-"

    def _text(self, value: Any) -> str:
        if value is None or value == "":
            return "-"
        return escape(str(value), quote=True)

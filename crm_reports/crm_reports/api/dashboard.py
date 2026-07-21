from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, nowdate

from crm_reports.api.dashboard_report import get_dashboard_report


@frappe.whitelist()
def get_dashboard(
    from_date: str | None = None,
    to_date: str | None = None,
    user: str | None = None,
    source: str | None = None,
    territory: str | None = None,
    status: str | None = None,
    team: str | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    """
    Tự động tạo toàn bộ CRM Dashboard.

    Manager View:
    - Không chọn Sales User.
    - Hiển thị dữ liệu toàn đội.

    Employee View:
    - Manager chọn một Sales User.
    - Sales User bình thường luôn bị backend ép về chính tài khoản đó.
    """

    from_date = from_date or add_days(nowdate(), -29)
    to_date = to_date or nowdate()

    employee = _clean_value(user)

    report = get_dashboard_report(
        from_date=from_date,
        to_date=to_date,
        employee=employee,
        view_mode=None,
        source=_clean_value(source),
        territory=_clean_value(territory),
        status=_clean_value(status),
        team=_clean_value(team),
    )

    if report.get("view_mode") == "employee":
        return _build_employee_dashboard(report)

    return _build_manager_dashboard(report)


def _build_manager_dashboard(
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    overview = report.get("overview") or {}
    risks = report.get("risks") or {}

    currency = _currency_code(report)
    currency_prefix = _currency_prefix(currency)

    top_lost_reason = (
        overview.get("top_lost_reason")
        or _("Not specified")
    )

    items: list[dict[str, Any]] = []

    # =========================================================
    # HÀNG 1 — MANAGER OVERVIEW
    # =========================================================

    items.extend(
        [
            _number_item(
                name="manager_total_leads",
                title=_("Total Leads"),
                tooltip=_(
                    "Total leads created in the selected period"
                ),
                value=overview.get("total_leads", 0),
                x=0,
                y=0,
            ),
            _number_item(
                name="manager_open_deals",
                title=_("Open Deals"),
                tooltip=_("Current open deals"),
                value=overview.get("open_deals", 0),
                x=5,
                y=0,
            ),
            _number_item(
                name="manager_won_deals",
                title=_("Won Deals"),
                tooltip=_(
                    "Deals won in the selected period"
                ),
                value=overview.get("won_deals", 0),
                x=10,
                y=0,
            ),
            _number_item(
                name="manager_lost_deals",
                title=_("Lost Deals"),
                tooltip=_(
                    "Deals lost in the selected period. "
                    "Most common reason: {0}"
                ).format(top_lost_reason),
                value=overview.get("lost_deals", 0),
                x=15,
                y=0,
            ),
        ]
    )

    # =========================================================
    # HÀNG 2 — MANAGER PERFORMANCE
    # =========================================================

    items.extend(
        [
            _number_item(
                name="manager_revenue",
                title=_("Won Revenue"),
                tooltip=_("Revenue from won deals"),
                value=overview.get("total_revenue", 0),
                prefix=currency_prefix,
                x=0,
                y=3,
            ),
            _number_item(
                name="manager_conversion",
                title=_("Conversion Rate"),
                tooltip=_(
                    "Won deals divided by all closed deals"
                ),
                value=overview.get("conversion_rate", 0),
                suffix="%",
                x=5,
                y=3,
            ),
            _number_item(
                name="manager_average_closing",
                title=_("Average Closing Time"),
                tooltip=_(
                    "Average time required to close a deal"
                ),
                value=overview.get(
                    "average_closing_days",
                    0,
                ),
                suffix=_(" days"),
                x=10,
                y=3,
            ),
            _number_item(
                name="manager_average_value",
                title=_("Average Deal Value"),
                tooltip=_("Average value of won deals"),
                value=overview.get(
                    "average_deal_value",
                    0,
                ),
                prefix=currency_prefix,
                x=15,
                y=3,
            ),
        ]
    )

    # =========================================================
    # HÀNG 3 — MANAGER RISKS
    # =========================================================

    stale_deals = risks.get("stale_deals") or []
    overdue_deals = risks.get("overdue_deals") or []
    high_value_closing = (
        risks.get("high_value_closing_soon")
        or []
    )

    items.extend(
        [
            _number_item(
                name="manager_stale_deals",
                title=_("Stale Deals"),
                tooltip=_(
                    "Open deals with no recent activity"
                ),
                value=len(stale_deals),
                x=0,
                y=6,
            ),
            _number_item(
                name="manager_overdue_deals",
                title=_("Overdue Deals"),
                tooltip=_(
                    "Open deals past their expected closing date"
                ),
                value=len(overdue_deals),
                x=5,
                y=6,
            ),
            _number_item(
                name="manager_high_value_closing",
                title=_("High-value Closing Soon"),
                tooltip=_(
                    "High-value deals expected to close soon"
                ),
                value=len(high_value_closing),
                x=10,
                y=6,
            ),
            _number_item(
                name="manager_risk_total",
                title=_("Total Risk Flags"),
                tooltip=_(
                    "Total stale, overdue and high-value "
                    "closing-soon flags"
                ),
                value=(
                    len(stale_deals)
                    + len(overdue_deals)
                    + len(high_value_closing)
                ),
                x=15,
                y=6,
            ),
        ]
    )

    # =========================================================
    # EMPLOYEE RANKING CHART
    # =========================================================

    ranking = report.get("employee_ranking") or []

    ranking_data = [
        {
            "employee": (
                row.get("employee_name")
                or row.get("employee")
                or _("Unassigned")
            ),
            "revenue": row.get("revenue", 0),
            "open_deals": row.get("open_deals", 0),
            "won_deals": row.get("won_deals", 0),
            "lost_deals": row.get("lost_deals", 0),
            "win_rate": row.get("win_rate", 0),
            "stale_deals": row.get("stale_deals", 0),
        }
        for row in ranking[:15]
    ]

    items.append(
        _axis_item(
            name="manager_employee_ranking",
            title=_("Employee Performance Ranking"),
            subtitle=_(
                "Revenue, won deals and stale deals by Sales User"
            ),
            data=ranking_data,
            x_axis_key="employee",
            x_axis_title=_("Sales User"),
            y_axis_title=_("Revenue") + f" ({currency})",
            y2_axis_title=_("Deal count"),
            series=[
                {
                    "name": "revenue",
                    "type": "bar",
                },
                {
                    "name": "won_deals",
                    "type": "line",
                    "axis": "y2",
                    "showDataPoints": True,
                },
                {
                    "name": "stale_deals",
                    "type": "line",
                    "axis": "y2",
                    "showDataPoints": True,
                },
            ],
            x=0,
            y=9,
            w=20,
            h=8,
        )
    )

    # =========================================================
    # SOURCE ANALYSIS
    # =========================================================

    source_analysis = report.get(
        "source_analysis"
    ) or []

    source_data = [
        {
            "source": (
                row.get("source")
                or _("Not specified")
            ),
            "revenue": row.get("revenue", 0),
            "total_deals": row.get("total_deals", 0),
            "won_deals": row.get("won_deals", 0),
            "lost_deals": row.get("lost_deals", 0),
            "conversion_rate": row.get(
                "conversion_rate",
                0,
            ),
        }
        for row in source_analysis[:12]
    ]

    items.append(
        _axis_item(
            name="manager_source_analysis",
            title=_("Lead Source Analysis"),
            subtitle=_(
                "Revenue and conversion rate by lead source"
            ),
            data=source_data,
            x_axis_key="source",
            x_axis_title=_("Lead Source"),
            y_axis_title=_("Revenue") + f" ({currency})",
            y2_axis_title=_("Conversion Rate (%)"),
            series=[
                {
                    "name": "revenue",
                    "type": "bar",
                },
                {
                    "name": "conversion_rate",
                    "type": "line",
                    "axis": "y2",
                    "showDataPoints": True,
                },
            ],
            x=0,
            y=17,
            w=10,
            h=8,
        )
    )

    # =========================================================
    # TERRITORY ANALYSIS
    # =========================================================

    territory_analysis = report.get(
        "territory_analysis"
    ) or []

    territory_data = [
        {
            "territory": (
                row.get("territory")
                or _("Not specified")
            ),
            "revenue": row.get("revenue", 0),
            "total_deals": row.get("total_deals", 0),
            "won_deals": row.get("won_deals", 0),
            "lost_deals": row.get("lost_deals", 0),
            "conversion_rate": row.get(
                "conversion_rate",
                0,
            ),
        }
        for row in territory_analysis[:12]
    ]

    items.append(
        _axis_item(
            name="manager_territory_analysis",
            title=_("Territory Analysis"),
            subtitle=_(
                "Revenue and conversion rate by territory"
            ),
            data=territory_data,
            x_axis_key="territory",
            x_axis_title=_("Territory"),
            y_axis_title=_("Revenue") + f" ({currency})",
            y2_axis_title=_("Conversion Rate (%)"),
            series=[
                {
                    "name": "revenue",
                    "type": "bar",
                },
                {
                    "name": "conversion_rate",
                    "type": "line",
                    "axis": "y2",
                    "showDataPoints": True,
                },
            ],
            x=10,
            y=17,
            w=10,
            h=8,
        )
    )

    # =========================================================
    # FUNNEL + DROP-OFF
    # =========================================================

    funnel_data = [
        {
            "stage": (
                row.get("stage")
                or _("Not specified")
            ),
            "deal_count": row.get("deal_count", 0),
            "drop_off_percent": row.get(
                "drop_off_percent",
                0,
            ),
        }
        for row in (report.get("funnel") or [])
    ]

    items.append(
        _axis_item(
            name="manager_pipeline_funnel",
            title=_("Pipeline Funnel"),
            subtitle=_(
                "Deal count and drop-off rate by pipeline stage"
            ),
            data=funnel_data,
            x_axis_key="stage",
            x_axis_title=_("Stage"),
            y_axis_title=_("Deals"),
            y2_axis_title=_("Drop-off (%)"),
            series=[
                {
                    "name": "deal_count",
                    "type": "bar",
                    "echartOptions": {
                        "colorBy": "data",
                    },
                },
                {
                    "name": "drop_off_percent",
                    "type": "line",
                    "axis": "y2",
                    "showDataPoints": True,
                },
            ],
            swap_xy=False,
            x=0,
            y=25,
            w=10,
            h=8,
        )
    )

    # =========================================================
    # FORECAST
    # =========================================================

    forecast_data = [
        {
            "month": row.get("month"),
            "pipeline_value": row.get(
                "pipeline_value",
                0,
            ),
            "weighted_revenue": row.get(
                "weighted_revenue",
                0,
            ),
            "deal_count": row.get(
                "deal_count",
                0,
            ),
        }
        for row in (report.get("forecast") or [])
    ]

    items.append(
        _axis_item(
            name="manager_forecast",
            title=_("Forecasted Revenue"),
            subtitle=_(
                "Pipeline value and probability-weighted revenue"
            ),
            data=forecast_data,
            x_axis_key="month",
            x_axis_title=_("Month"),
            y_axis_title=_("Revenue") + f" ({currency})",
            y2_axis_title=_("Deal count"),
            series=[
                {
                    "name": "pipeline_value",
                    "type": "bar",
                },
                {
                    "name": "weighted_revenue",
                    "type": "line",
                    "showDataPoints": True,
                },
                {
                    "name": "deal_count",
                    "type": "line",
                    "axis": "y2",
                    "showDataPoints": True,
                },
            ],
            x=10,
            y=25,
            w=10,
            h=8,
        )
    )

    return items


def _build_employee_dashboard(
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    overview = report.get("overview") or {}
    actions = report.get("actions") or {}
    meta = report.get("meta") or {}

    employee = (
        meta.get("effective_employee")
        or (report.get("filters") or {}).get(
            "employee"
        )
        or ""
    )

    employee_name = (
        frappe.db.get_value(
            "User",
            employee,
            "full_name",
        )
        if employee
        else ""
    ) or employee

    currency = _currency_code(report)
    currency_prefix = _currency_prefix(currency)

    rank = overview.get("rank", 0)
    team_size = overview.get("team_size", 0)

    top_lost_reason = (
        overview.get("top_lost_reason")
        or _("Not specified")
    )

    follow_up_due = (
        actions.get("follow_up_due")
        or []
    )

    stale_deals = (
        actions.get("stale_deals")
        or []
    )

    closing_soon = (
        actions.get("closing_soon")
        or []
    )

    items: list[dict[str, Any]] = []

    # =========================================================
    # HÀNG 1 — EMPLOYEE OVERVIEW
    # =========================================================

    items.extend(
        [
            _number_item(
                name="employee_open_deals",
                title=_("My Open Deals"),
                tooltip=_(
                    "Open deals assigned to {0}"
                ).format(employee_name),
                value=overview.get("open_deals", 0),
                x=0,
                y=0,
            ),
            _number_item(
                name="employee_won_deals",
                title=_("My Won Deals"),
                tooltip=_(
                    "Won deals in the selected period"
                ),
                value=overview.get("won_deals", 0),
                x=5,
                y=0,
            ),
            _number_item(
                name="employee_lost_deals",
                title=_("My Lost Deals"),
                tooltip=_(
                    "Lost deals in the selected period. "
                    "Most common reason: {0}"
                ).format(top_lost_reason),
                value=overview.get("lost_deals", 0),
                x=10,
                y=0,
            ),
            _number_item(
                name="employee_revenue",
                title=_("My Revenue"),
                tooltip=_(
                    "Revenue from personal won deals"
                ),
                value=overview.get("revenue", 0),
                prefix=currency_prefix,
                x=15,
                y=0,
            ),
        ]
    )

    # =========================================================
    # HÀNG 2 — EMPLOYEE PERFORMANCE
    # =========================================================

    items.extend(
        [
            _number_item(
                name="employee_win_rate",
                title=_("My Win Rate"),
                tooltip=_(
                    "Won deals divided by personal closed deals"
                ),
                value=overview.get("win_rate", 0),
                suffix="%",
                x=0,
                y=3,
            ),
            _number_item(
                name="employee_average_closing",
                title=_("My Average Closing Time"),
                tooltip=_(
                    "My average time required to close a deal"
                ),
                value=overview.get(
                    "average_closing_days",
                    0,
                ),
                suffix=_(" days"),
                x=5,
                y=3,
            ),
            _number_item(
                name="employee_team_average",
                title=_("Team Average Closing Time"),
                tooltip=_(
                    "Average closing time for the team"
                ),
                value=overview.get(
                    "team_average_closing_days",
                    0,
                ),
                suffix=_(" days"),
                x=10,
                y=3,
            ),
            _number_item(
                name="employee_rank",
                title=_("My Team Rank"),
                tooltip=_(
                    "Personal revenue ranking within the team"
                ),
                value=rank,
                suffix=(
                    f"/{team_size}"
                    if team_size
                    else ""
                ),
                x=15,
                y=3,
            ),
        ]
    )

    # =========================================================
    # HÀNG 3 — EMPLOYEE ACTIONS
    # =========================================================

    items.extend(
        [
            _number_item(
                name="employee_follow_up_due",
                title=_("Follow-up Due"),
                tooltip=_(
                    "Deals requiring follow-up today "
                    "or within the next seven days"
                ),
                value=len(follow_up_due),
                x=0,
                y=6,
            ),
            _number_item(
                name="employee_stale_deals",
                title=_("My Stale Deals"),
                tooltip=_(
                    "My deals with no recent activity"
                ),
                value=len(stale_deals),
                x=5,
                y=6,
            ),
            _number_item(
                name="employee_closing_soon",
                title=_("Closing Soon"),
                tooltip=_(
                    "My deals expected to close soon"
                ),
                value=len(closing_soon),
                x=10,
                y=6,
            ),
            _number_item(
                name="employee_action_flags",
                title=_("Total Action Flags"),
                tooltip=_(
                    "Total follow-up, stale and closing-soon flags"
                ),
                value=(
                    len(follow_up_due)
                    + len(stale_deals)
                    + len(closing_soon)
                ),
                x=15,
                y=6,
            ),
        ]
    )

    # =========================================================
    # EMPLOYEE DEAL TREND
    # =========================================================

    trends = report.get("trends") or []

    trend_data = [
        {
            "month": row.get("month"),
            "opened": row.get("opened", 0),
            "won": row.get("won", 0),
            "lost": row.get("lost", 0),
        }
        for row in trends
    ]

    items.append(
        _axis_item(
            name="employee_deal_trend",
            title=_("Personal Deal Trend"),
            subtitle=employee_name,
            data=trend_data,
            x_axis_key="month",
            x_axis_title=_("Month"),
            y_axis_title=_("Deals"),
            series=[
                {
                    "name": "opened",
                    "type": "bar",
                },
                {
                    "name": "won",
                    "type": "line",
                    "showDataPoints": True,
                },
                {
                    "name": "lost",
                    "type": "line",
                    "showDataPoints": True,
                },
            ],
            x=0,
            y=9,
            w=10,
            h=8,
        )
    )

    # =========================================================
    # EMPLOYEE CLOSING TREND
    # =========================================================

    closing_data = [
        {
            "month": row.get("month"),
            "average_closing_days": row.get(
                "average_closing_days",
                0,
            ),
        }
        for row in trends
    ]

    items.append(
        _axis_item(
            name="employee_closing_time_trend",
            title=_("Closing Time Trend"),
            subtitle=_(
                "Personal average: {0} days — "
                "Team average: {1} days"
            ).format(
                overview.get(
                    "average_closing_days",
                    0,
                ),
                overview.get(
                    "team_average_closing_days",
                    0,
                ),
            ),
            data=closing_data,
            x_axis_key="month",
            x_axis_title=_("Month"),
            y_axis_title=_("Days"),
            series=[
                {
                    "name": "average_closing_days",
                    "type": "line",
                    "showDataPoints": True,
                },
            ],
            x=10,
            y=9,
            w=10,
            h=8,
        )
    )

    # =========================================================
    # EMPLOYEE PIPELINE
    # =========================================================

    pipeline_data = [
        {
            "stage": (
                row.get("stage")
                or _("Not specified")
            ),
            "deal_count": row.get(
                "deal_count",
                0,
            ),
        }
        for row in (report.get("pipeline") or [])
    ]

    items.append(
        _donut_item(
            name="employee_pipeline",
            title=_("Personal Pipeline"),
            subtitle=_(
                "Open deals grouped by stage"
            ),
            data=pipeline_data,
            category_column="stage",
            value_column="deal_count",
            x=0,
            y=17,
            w=20,
            h=8,
        )
    )

    return items


def _number_item(
    *,
    name: str,
    title: str,
    tooltip: str,
    value: Any,
    x: int,
    y: int,
    w: int = 5,
    h: int = 3,
    prefix: str | None = None,
    suffix: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": title,
        "tooltip": tooltip,
        "value": value or 0,
    }

    if prefix:
        data["prefix"] = prefix

    if suffix:
        data["suffix"] = suffix

    return _dashboard_item(
        name=name,
        item_type="number_chart",
        data=data,
        x=x,
        y=y,
        w=w,
        h=h,
    )


def _axis_item(
    *,
    name: str,
    title: str,
    subtitle: str,
    data: list[dict[str, Any]],
    x_axis_key: str,
    x_axis_title: str,
    y_axis_title: str,
    series: list[dict[str, Any]],
    x: int,
    y: int,
    w: int,
    h: int,
    swap_xy: bool = False,
    y2_axis_title: str | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "data": data,
        "title": title,
        "subtitle": subtitle,
        "xAxis": {
            "title": x_axis_title,
            "key": x_axis_key,
            "type": "category",
        },
        "yAxis": {
            "title": y_axis_title,
        },
        "series": series,
    }

    if y2_axis_title:
        config["y2Axis"] = {
            "title": y2_axis_title,
        }

    if swap_xy:
        config["swapXY"] = True

    return _dashboard_item(
        name=name,
        item_type="axis_chart",
        data=config,
        x=x,
        y=y,
        w=w,
        h=h,
    )


def _donut_item(
    *,
    name: str,
    title: str,
    subtitle: str,
    data: list[dict[str, Any]],
    category_column: str,
    value_column: str,
    x: int,
    y: int,
    w: int,
    h: int,
) -> dict[str, Any]:
    return _dashboard_item(
        name=name,
        item_type="donut_chart",
        data={
            "data": data,
            "title": title,
            "subtitle": subtitle,
            "categoryColumn": category_column,
            "valueColumn": value_column,
        },
        x=x,
        y=y,
        w=w,
        h=h,
    )


def _dashboard_item(
    *,
    name: str,
    item_type: str,
    data: dict[str, Any],
    x: int,
    y: int,
    w: int,
    h: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": item_type,
        "layout": {
            "i": name,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
        },
        "data": data,
    }


def _currency_code(
    report: dict[str, Any],
) -> str:
    return (
        str(
            (report.get("meta") or {}).get(
                "currency"
            )
            or "VND"
        )
        .strip()
        .upper()
    )


def _currency_prefix(
    currency: str,
) -> str:
    symbol = frappe.db.get_value(
        "Currency",
        currency,
        "symbol",
    )

    if symbol:
        return f"{symbol} "

    return f"{currency} "


def _clean_value(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()

    if not cleaned:
        return None

    if cleaned.lower() in {
        "null",
        "none",
        "undefined",
    }:
        return None

    return cleaned
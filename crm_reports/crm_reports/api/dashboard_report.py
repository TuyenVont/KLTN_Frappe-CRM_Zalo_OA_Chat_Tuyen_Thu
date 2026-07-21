from __future__ import annotations

from collections import Counter, defaultdict
from types import SimpleNamespace
from typing import Any, Iterable

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_months,
    cint,
    date_diff,
    flt,
    getdate,
    nowdate,
)

from crm_reports.permissions import get_report_context


DEAL_DOCTYPE = "CRM Deal"
LEAD_DOCTYPE = "CRM Lead"
DEAL_STATUS_DOCTYPE = "CRM Deal Status"

PAGE_SIZE = 500
MAX_RECORDS = 10000
MAX_REPORT_DAYS = 366

EMPLOYEE_FIELDS = (
    "deal_owner",
    "sales_person",
    "owner",
)

TEAM_FIELDS = (
    "team",
    "sales_team",
    "sales_team_name",
)

VALUE_FIELDS = (
    "deal_value",
    "expected_deal_value",
    "net_total",
    "total",
    "annual_revenue",
)

CURRENCY_FIELDS = (
    "currency",
    "deal_currency",
)

EXCHANGE_RATE_FIELDS = (
    "exchange_rate",
)

EXPECTED_CLOSING_FIELDS = (
    "expected_closure_date",
    "expected_closing_date",
)

PROBABILITY_FIELDS = (
    "probability",
    "deal_probability",
)

SOURCE_FIELDS = (
    "source",
    "lead_source",
)

TERRITORY_FIELDS = (
    "territory",
    "region",
)

LOST_REASON_FIELDS = (
    "lost_reason",
    "deal_lost_reason",
    "reason_for_loss",
    "reason",
)

CLOSED_DATE_FIELDS = (
    "custom_closed_date",
    "closed_date",
    "modified",
)

LAST_ACTIVITY_FIELDS = (
    "last_activity_date",
    "last_interaction_date",
    "modified",
)

FOLLOW_UP_FIELDS = (
    "next_follow_up_date",
    "follow_up_date",
    "next_contact_date",
    "next_action_date",
)

TITLE_FIELDS = (
    "deal_name",
    "organization_name",
    "organization",
    "lead_name",
    "name",
)

@frappe.whitelist()
def get_dashboard_report(
    from_date: str,
    to_date: str,
    employee: str | None = None,
    view_mode: str | None = None,
    source: str | None = None,
    territory: str | None = None,
    status: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """
    Dashboard mở rộng cho CRM.

    Manager View:
    - Overview toàn team;
    - bảng xếp hạng nhân viên;
    - phân tích nguồn/khu vực/funnel;
    - forecast và danh sách rủi ro.

    Employee View:
    - KPI cá nhân;
    - việc cần xử lý;
    - xu hướng và pipeline cá nhân.
    """

    from_date_obj, to_date_obj = _validate_date_range(
        from_date=from_date,
        to_date=to_date,
    )

    context = get_report_context(
        view_mode=view_mode,
        selected_employee=employee,
    )

    settings = _get_settings()
    schema = _detect_deal_schema()
    lead_schema = _detect_lead_schema()
    status_map, status_order = _get_status_metadata()

    requested_employee = context["employee"] or None

    deals, truncated = _fetch_deals(
        schema=schema,
        to_date=to_date_obj,
        employee=requested_employee,
        source=(source or "").strip() or None,
        territory=(territory or "").strip() or None,
        status=(status or "").strip() or None,
        team=(team or "").strip() or None,
    )

    warnings = _schema_warnings(schema)

    if truncated:
        warnings.append(
            _(
                "The dashboard reached the maximum of {0} Deal records. "
                "Use a shorter period or narrower filters."
            ).format(MAX_RECORDS)
        )

    common = {
        "from_date": from_date_obj,
        "to_date": to_date_obj,
        "settings": settings,
        "schema": schema,
        "lead_schema": lead_schema,
        "status_map": status_map,
        "status_order": status_order,
        "source": (source or "").strip(),
        "territory": (territory or "").strip(),
        "status": (status or "").strip(),
        "team": (team or "").strip(),
        "warnings": warnings,
        "context": context,
    }

    if context["view_mode"] == "employee":
        # Dữ liệu team chỉ dùng để tính benchmark tổng hợp.
        # Response Employee không trả tên hoặc danh sách đồng nghiệp.
        team_deals, team_truncated = _fetch_deals(
            schema=schema,
            to_date=to_date_obj,
            source=common["source"] or None,
            territory=common["territory"] or None,
            status=common["status"] or None,
            team=common["team"] or None,
            ignore_permissions=True,
        )

        if team_truncated:
            common["warnings"].append(
                _(
                    "Team benchmark reached the maximum of {0} "
                    "Deal records."
                ).format(MAX_RECORDS)
            )

        return _build_employee_report(
            deals=deals,
            team_deals=team_deals,
            employee=context["employee"],
            **common,
        )

    return _build_manager_report(
        deals=deals,
        **common,
    )
        # Manager preview cần dữ liệu team để tính benchmark/xếp hạng nhẹ.
        # User thường vẫn bị Frappe permission giới hạn khi get_list.
    team_deals, _ = _fetch_deals(
            schema=schema,
            to_date=to_date_obj,
            source=common["source"] or None,
            territory=common["territory"] or None,
            status=common["status"] or None,
            team=common["team"] or None,
        )

    return _build_employee_report(
            deals=deals,
            team_deals=team_deals,
            employee=context["employee"],
            **common,
        )

    return _build_manager_report(
        deals=deals,
        **common,
    )


def _validate_date_range(*, from_date: str, to_date: str):
    if not from_date or not to_date:
        frappe.throw(
            _("From Date and To Date are required."),
            frappe.ValidationError,
        )

    try:
        from_date_obj = getdate(from_date)
        to_date_obj = getdate(to_date)
    except Exception:
        frappe.throw(
            _("Invalid date. Use YYYY-MM-DD format."),
            frappe.ValidationError,
        )

    if from_date_obj > to_date_obj:
        frappe.throw(
            _("From Date cannot be later than To Date."),
            frappe.ValidationError,
        )

    total_days = date_diff(to_date_obj, from_date_obj) + 1

    if total_days > MAX_REPORT_DAYS:
        frappe.throw(
            _("The report date range cannot exceed {0} days.").format(
                MAX_REPORT_DAYS
            ),
            frappe.ValidationError,
        )

    return from_date_obj, to_date_obj


def _get_settings():
    if frappe.db.exists("DocType", "CRM Reports Settings"):
        return frappe.get_single("CRM Reports Settings")

    return SimpleNamespace(
        stale_deal_days=7,
        closing_soon_days=7,
        high_value_threshold=0,
        report_currency="VND",
        show_employee_ranking=1,
        show_forecast=1,
    )


def _detect_deal_schema() -> dict[str, str | None]:
    meta = frappe.get_meta(DEAL_DOCTYPE)

    return {
        "employee_field": _first_existing_field(
            meta,
            EMPLOYEE_FIELDS,
        ),
        "team_field": _first_existing_field(
            meta,
            TEAM_FIELDS,
        ),
        "value_field": _first_existing_field(
            meta,
            VALUE_FIELDS,
        ),
        "currency_field": _first_existing_field(
            meta,
            CURRENCY_FIELDS,
        ),
        "exchange_rate_field": _first_existing_field(
            meta,
            EXCHANGE_RATE_FIELDS,
        ),
        "expected_closing_field": _first_existing_field(
            meta,
            EXPECTED_CLOSING_FIELDS,
        ),
        "probability_field": _first_existing_field(
            meta,
            PROBABILITY_FIELDS,
        ),
        "source_field": _first_existing_field(
            meta,
            SOURCE_FIELDS,
        ),
        "territory_field": _first_existing_field(
            meta,
            TERRITORY_FIELDS,
        ),
        "lost_reason_field": _first_existing_field(
            meta,
            LOST_REASON_FIELDS,
        ),
        "closed_date_field": _first_existing_field(
            meta,
            CLOSED_DATE_FIELDS,
        ),
        "last_activity_field": _first_existing_field(
            meta,
            LAST_ACTIVITY_FIELDS,
        ),
        "follow_up_field": _first_existing_field(
            meta,
            FOLLOW_UP_FIELDS,
        ),
        "title_field": _first_existing_field(
            meta,
            TITLE_FIELDS,
        ),
    }

def _detect_lead_schema() -> dict[str, str | None]:
    if not frappe.db.exists("DocType", LEAD_DOCTYPE):
        return {
            "employee_field": None,
            "source_field": None,
            "territory_field": None,
        }

    meta = frappe.get_meta(LEAD_DOCTYPE)

    return {
        "employee_field": _first_existing_field(
            meta,
            EMPLOYEE_FIELDS,
        ),
        "source_field": _first_existing_field(
            meta,
            SOURCE_FIELDS,
        ),
        "territory_field": _first_existing_field(
            meta,
            TERRITORY_FIELDS,
        ),
    }


def _first_existing_field(
    meta,
    candidates: Iterable[str],
) -> str | None:
    standard_fields = {
        "name",
        "owner",
        "creation",
        "modified",
        "status",
    }

    for fieldname in candidates:
        if fieldname in standard_fields:
            return fieldname

        if meta.has_field(fieldname):
            return fieldname

    return None


def _schema_warnings(
    schema: dict[str, str | None],
) -> list[str]:
    warnings: list[str] = []

    if not schema["employee_field"]:
        warnings.append(
            _("No employee owner field was found on CRM Deal.")
        )

    if not schema["value_field"]:
        warnings.append(
            _(
                "No Deal value field was found; "
                "revenue is returned as 0."
            )
        )

    if not schema["expected_closing_field"]:
        warnings.append(
            _(
                "No expected closing date field was found; "
                "forecast and closing-soon lists may be empty."
            )
        )

    if not schema["probability_field"]:
        warnings.append(
            _(
                "No probability field was found; weighted forecast "
                "is returned as 0."
            )
        )

    if schema["closed_date_field"] == "modified":
        warnings.append(
            _(
                "Closing time currently uses modified as a fallback. "
                "Create a dedicated closed date field for exact results."
            )
        )

    return warnings


def _get_status_metadata() -> tuple[dict[str, str], list[str]]:
    if not frappe.db.exists("DocType", DEAL_STATUS_DOCTYPE):
        return {}, []

    rows = frappe.get_all(
        DEAL_STATUS_DOCTYPE,
        fields=["name", "type"],
        order_by="creation asc",
    )

    status_map = {
        str(row.get("name") or ""): str(row.get("type") or "")
        for row in rows
    }

    status_order = [
        str(row.get("name") or "")
        for row in rows
        if row.get("name")
    ]

    return status_map, status_order


def _fetch_deals(
    *,
    schema: dict[str, str | None],
    to_date,
    employee: str | None = None,
    source: str | None = None,
    territory: str | None = None,
    status: str | None = None,
    team: str | None = None,
    ignore_permissions: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    fields = [
        "name",
        "creation",
        "modified",
        "status",
    ]

    for fieldname in schema.values():
        if fieldname and fieldname not in fields:
            fields.append(fieldname)

    filters: dict[str, Any] = {
        "creation": [
            "<=",
            f"{to_date} 23:59:59.999999",
        ],
    }

    if employee and schema["employee_field"]:
        filters[schema["employee_field"]] = employee

    if source and schema["source_field"]:
        filters[schema["source_field"]] = source

    if territory and schema["territory_field"]:
        filters[schema["territory_field"]] = territory

    if status:
        filters["status"] = status

    if team and schema["team_field"]:
        filters[schema["team_field"]] = team

    rows: list[dict[str, Any]] = []
    start = 0
    truncated = False

    while len(rows) < MAX_RECORDS:
        page_length = min(
            PAGE_SIZE,
            MAX_RECORDS - len(rows),
        )

        get_rows = (
            frappe.get_all
            if ignore_permissions
            else frappe.get_list
        )

        batch = get_rows(
            DEAL_DOCTYPE,
            fields=fields,
            filters=filters,
            order_by="creation asc, name asc",
            start=start,
            page_length=page_length,
        )

        if not batch:
            break

        rows.extend(
            dict(row)
            for row in batch
        )

        if len(batch) < page_length:
            break

        start += page_length

    if len(rows) >= MAX_RECORDS:
        truncated = True

    return rows, truncated

def _build_manager_report(
    *,
    deals: list[dict[str, Any]],
    from_date,
    to_date,
    settings,
    schema,
    lead_schema,
    status_map,
    status_order,
    source,
    territory,
    status,
    team,
    warnings,
    context,
) -> dict[str, Any]:
    datasets = _split_datasets(
        deals=deals,
        from_date=from_date,
        to_date=to_date,
        schema=schema,
        status_map=status_map,
    )

    overview = _get_manager_overview(
        datasets=datasets,
        from_date=from_date,
        to_date=to_date,
        schema=schema,
        lead_schema=lead_schema,
        source=source,
        territory=territory,
    )

    employee_ranking = (
        _get_employee_ranking(
            deals=deals,
            datasets=datasets,
            from_date=from_date,
            to_date=to_date,
            schema=schema,
            status_map=status_map,
            stale_days=_setting_int(
                settings,
                "stale_deal_days",
                7,
            ),
        )
        if cint(
            getattr(
                settings,
                "show_employee_ranking",
                1,
            )
        )
        else []
    )

    # Forecast không bị giới hạn vào Last 30/60/90 Days.
    # Forecast bắt đầu từ hôm nay và kéo dài 6 tháng.
    forecast_from = max(
        getdate(nowdate()),
        from_date,
    )

    forecast_to = add_months(
        forecast_from,
        6,
    )

    forecast = (
        _get_forecast(
            open_deals=datasets["open_deals"],
            from_date=forecast_from,
            to_date=forecast_to,
            schema=schema,
        )
        if cint(
            getattr(
                settings,
                "show_forecast",
                1,
            )
        )
        else []
    )

    return {
        "success": True,
        "view_mode": "manager",
        "overview": overview,
        "employee_ranking": employee_ranking,
        "source_analysis": _get_dimension_analysis(
            datasets=datasets,
            schema=schema,
            fieldname=schema["source_field"],
            label_key="source",
        ),
        "territory_analysis": _get_dimension_analysis(
            datasets=datasets,
            schema=schema,
            fieldname=schema["territory_field"],
            label_key="territory",
        ),
        "funnel": _get_funnel(
            datasets=datasets,
            status_order=status_order,
        ),
        "forecast": forecast,
        "risks": _get_risks(
            open_deals=datasets["open_deals"],
            schema=schema,
            settings=settings,
        ),
        "filters": {
            "from_date": str(from_date),
            "to_date": str(to_date),
            "employee": None,
            "source": source or None,
            "territory": territory or None,
            "status": status or None,
            "team": team or None,
        },
        "forecast_period": {
            "from_date": str(forecast_from),
            "to_date": str(forecast_to),
        },
        "meta": _build_meta(
            context=context,
            settings=settings,
            schema=schema,
            warnings=warnings,
        ),
    }

def _build_employee_report(
    *,
    deals: list[dict[str, Any]],
    team_deals: list[dict[str, Any]],
    employee: str,
    from_date,
    to_date,
    settings,
    schema,
    lead_schema,
    status_map,
    status_order,
    source,
    territory,
    status,
    team,
    warnings,
    context,
) -> dict[str, Any]:
    datasets = _split_datasets(
        deals=deals,
        from_date=from_date,
        to_date=to_date,
        schema=schema,
        status_map=status_map,
    )

    team_datasets = _split_datasets(
        deals=team_deals,
        from_date=from_date,
        to_date=to_date,
        schema=schema,
        status_map=status_map,
    )

    overview = _get_employee_overview(
        datasets=datasets,
        team_datasets=team_datasets,
        employee=employee,
        schema=schema,
        from_date=from_date,
        to_date=to_date,
        status_map=status_map,
        team_deals=team_deals,
        stale_days=_setting_int(
            settings,
            "stale_deal_days",
            7,
        ),
    )
    actions = _get_employee_actions(
        open_deals=datasets["open_deals"],
        schema=schema,
        settings=settings,
    )

    return {
        "success": True,
        "view_mode": "employee",
        "overview": overview,
        "actions": actions,
        "trends": _get_trends(
            deals=deals,
            from_date=from_date,
            to_date=to_date,
            schema=schema,
            status_map=status_map,
        ),
        "pipeline": _get_personal_pipeline(
            open_deals=datasets["open_deals"],
            status_order=status_order,
        ),
        "filters": {
            "from_date": str(from_date),
            "to_date": str(to_date),
            "employee": employee,
            "source": source or None,
            "territory": territory or None,
            "status": status or None,
            "team": team or None,
        },
        "meta": _build_meta(
            context=context,
            settings=settings,
            schema=schema,
            warnings=warnings,
        ),
    }


def _split_datasets(
    *,
    deals: list[dict[str, Any]],
    from_date,
    to_date,
    schema,
    status_map,
) -> dict[str, list[dict[str, Any]]]:
    period_created: list[dict[str, Any]] = []
    period_won: list[dict[str, Any]] = []
    period_lost: list[dict[str, Any]] = []
    period_closed: list[dict[str, Any]] = []
    open_deals: list[dict[str, Any]] = []

    for deal in deals:
        creation_date = _safe_date(
            deal.get("creation")
        )

        closed_date = _closed_date(
            deal,
            schema,
        )

        status_type = _status_type(
            deal.get("status"),
            status_map,
        )

        if _date_in_period(
            creation_date,
            from_date,
            to_date,
        ):
            period_created.append(deal)

        if (
            status_type == "Won"
            and _date_in_period(
                closed_date,
                from_date,
                to_date,
            )
        ):
            period_won.append(deal)
            period_closed.append(deal)

        elif (
            status_type == "Lost"
            and _date_in_period(
                closed_date,
                from_date,
                to_date,
            )
        ):
            period_lost.append(deal)
            period_closed.append(deal)

        elif status_type not in {"Won", "Lost"}:
            open_deals.append(deal)

    analytics_deals = _unique_deals(
        [
            *period_created,
            *period_closed,
        ]
    )

    return {
        "period_created": period_created,
        "period_won": period_won,
        "period_lost": period_lost,
        "period_closed": period_closed,
        "open_deals": open_deals,
        "analytics_deals": analytics_deals,
    }


def _get_manager_overview(
    *,
    datasets,
    from_date,
    to_date,
    schema,
    lead_schema,
    source,
    territory,
) -> dict[str, Any]:
    won_deals = datasets["period_won"]
    lost_deals = datasets["period_lost"]
    open_deals = datasets["open_deals"]

    revenue_values = [
        _deal_value(
            deal,
            schema,
        )
        for deal in won_deals
    ]

    closing_values = [
        value
        for value in (
            _closing_days(
                deal,
                schema,
            )
            for deal in datasets["period_closed"]
        )
        if value is not None
    ]

    closed_count = (
        len(won_deals)
        + len(lost_deals)
    )

    total_revenue = sum(revenue_values)

    return {
        "total_leads": _count_leads(
            from_date=from_date,
            to_date=to_date,
            lead_schema=lead_schema,
            source=source,
            territory=territory,
        ),
        "open_deals": len(open_deals),
        "won_deals": len(won_deals),
        "won_value": _normal_number(
            total_revenue
        ),
        "lost_deals": len(lost_deals),
        "top_lost_reason": _top_lost_reason(
            lost_deals,
            schema,
        ),
        "total_revenue": _normal_number(
            total_revenue
        ),
        "conversion_rate": _percentage(
            len(won_deals),
            closed_count,
        ),
        "average_closing_days": _average(
            closing_values
        ),
        "average_deal_value": _average(
            revenue_values
        ),
    }


def _get_employee_overview(
    *,
    datasets,
    team_datasets,
    employee,
    schema,
    from_date,
    to_date,
    status_map,
    team_deals,
    stale_days,
) -> dict[str, Any]:
    won_deals = datasets["period_won"]
    lost_deals = datasets["period_lost"]
    closed_deals = datasets["period_closed"]

    revenue_values = [
        _deal_value(
            deal,
            schema,
        )
        for deal in won_deals
    ]

    closing_values = [
        value
        for value in (
            _closing_days(
                deal,
                schema,
            )
            for deal in closed_deals
        )
        if value is not None
    ]

    team_closing_values = [
        value
        for value in (
            _closing_days(
                deal,
                schema,
            )
            for deal in team_datasets["period_closed"]
        )
        if value is not None
    ]

    ranking = _get_employee_ranking(
        deals=team_deals,
        datasets=team_datasets,
        from_date=from_date,
        to_date=to_date,
        schema=schema,
        status_map=status_map,
        stale_days=stale_days,
    )

    # Không tính dòng Unassigned là một nhân viên.
    ranked_employees = [
        row
        for row in ranking
        if row.get("employee")
    ]

    employee_rank = 0

    for index, row in enumerate(
        ranked_employees,
        start=1,
    ):
        if row.get("employee") == employee:
            employee_rank = index
            break

    closed_count = (
        len(won_deals)
        + len(lost_deals)
    )

    personal_average = _average(
        closing_values
    )

    team_average = _average(
        team_closing_values
    )

    closing_vs_team_percent = 0.0

    if team_average:
        closing_vs_team_percent = round(
            (
                personal_average
                - team_average
            )
            / team_average
            * 100,
            2,
        )

    return {
        "open_deals": len(
            datasets["open_deals"]
        ),
        "won_deals": len(won_deals),
        "won_value": _normal_number(
            sum(revenue_values)
        ),
        "lost_deals": len(lost_deals),
        "top_lost_reason": _top_lost_reason(
            lost_deals,
            schema,
        ),
        "revenue": _normal_number(
            sum(revenue_values)
        ),
        "average_closing_days": personal_average,
        "team_average_closing_days": team_average,
        "closing_vs_team_percent": (
            closing_vs_team_percent
        ),
        "win_rate": _percentage(
            len(won_deals),
            closed_count,
        ),
        "rank": employee_rank,
        "team_size": len(ranked_employees),
    }

def _count_leads(
    *,
    from_date,
    to_date,
    lead_schema,
    source,
    territory,
) -> int:
    if not frappe.db.exists(
        "DocType",
        LEAD_DOCTYPE,
    ):
        return 0

    filters: dict[str, Any] = {
        "creation": [
            "between",
            [
                f"{from_date} 00:00:00",
                f"{to_date} 23:59:59.999999",
            ],
        ],
    }

    if (
        source
        and lead_schema["source_field"]
    ):
        filters[
            lead_schema["source_field"]
        ] = source

    if (
        territory
        and lead_schema["territory_field"]
    ):
        filters[
            lead_schema["territory_field"]
        ] = territory

    return frappe.db.count(
        LEAD_DOCTYPE,
        filters=filters,
    )


def _get_employee_ranking(
    *,
    deals,
    datasets,
    from_date,
    to_date,
    schema,
    status_map,
    stale_days,
) -> list[dict[str, Any]]:
    employee_field = schema["employee_field"]

    if not employee_field:
        return []

    current_period = datasets["period_closed"]
    open_deals = datasets["open_deals"]

    period_days = (
        date_diff(
            to_date,
            from_date,
        )
        + 1
    )

    previous_to = add_days(
        from_date,
        -1,
    )

    previous_from = add_days(
        previous_to,
        -(period_days - 1),
    )

    previous_closed = [
        deal
        for deal in deals
        if (
            _status_type(
                deal.get("status"),
                status_map,
            )
            in {"Won", "Lost"}
            and _date_in_period(
                _closed_date(
                    deal,
                    schema,
                ),
                previous_from,
                previous_to,
            )
        )
    ]

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "current_closed": [],
            "previous_closed": [],
            "open_deals": [],
            "all_deals": [],
        }
    )

    for deal in deals:
        employee = str(
            deal.get(employee_field)
            or ""
        )

        grouped[employee][
            "all_deals"
        ].append(deal)

    for deal in current_period:
        employee = str(
            deal.get(employee_field)
            or ""
        )

        grouped[employee][
            "current_closed"
        ].append(deal)

    for deal in previous_closed:
        employee = str(
            deal.get(employee_field)
            or ""
        )

        grouped[employee][
            "previous_closed"
        ].append(deal)

    for deal in open_deals:
        employee = str(
            deal.get(employee_field)
            or ""
        )

        grouped[employee][
            "open_deals"
        ].append(deal)

    employee_names = _get_user_names(
        grouped.keys()
    )

    team_closing_values = [
        value
        for value in (
            _closing_days(
                deal,
                schema,
            )
            for deal in current_period
        )
        if value is not None
    ]

    team_average = _average(
        team_closing_values
    )

    rows: list[dict[str, Any]] = []
    today = getdate(nowdate())

    for employee, data in grouped.items():
        current_closed = data[
            "current_closed"
        ]

        previous_closed_rows = data[
            "previous_closed"
        ]

        current_won = [
            deal
            for deal in current_closed
            if _status_type(
                deal.get("status"),
                status_map,
            )
            == "Won"
        ]

        current_lost = [
            deal
            for deal in current_closed
            if _status_type(
                deal.get("status"),
                status_map,
            )
            == "Lost"
        ]

        previous_won = [
            deal
            for deal in previous_closed_rows
            if _status_type(
                deal.get("status"),
                status_map,
            )
            == "Won"
        ]

        current_revenue = sum(
            _deal_value(
                deal,
                schema,
            )
            for deal in current_won
        )

        previous_revenue = sum(
            _deal_value(
                deal,
                schema,
            )
            for deal in previous_won
        )

        closing_values = [
            value
            for value in (
                _closing_days(
                    deal,
                    schema,
                )
                for deal in current_closed
            )
            if value is not None
        ]

        stale_count = sum(
            1
            for deal in data["open_deals"]
            if _days_without_activity(
                deal,
                schema,
                today=today,
            )
            > stale_days
        )

        representative = (
            data["all_deals"][-1]
            if data["all_deals"]
            else {}
        )

        rows.append(
            {
                "employee": employee,
                "employee_name": (
                    employee_names.get(employee)
                    or (
                        _("Unassigned")
                        if not employee
                        else employee
                    )
                ),
                "team": _field_value(
                    representative,
                    schema["team_field"],
                ),
                "territory": _field_value(
                    representative,
                    schema["territory_field"],
                ),
                "open_deals": len(
                    data["open_deals"]
                ),
                "won_deals": len(
                    current_won
                ),
                "lost_deals": len(
                    current_lost
                ),
                "revenue": _normal_number(
                    current_revenue
                ),
                "win_rate": _percentage(
                    len(current_won),
                    (
                        len(current_won)
                        + len(current_lost)
                    ),
                ),
                "average_closing_days": _average(
                    closing_values
                ),
                "team_average_closing_days": (
                    team_average
                ),
                "trend_percent": _trend_percent(
                    current_revenue,
                    previous_revenue,
                ),
                "stale_deals": stale_count,
            }
        )

    rows.sort(
        key=lambda row: (
            -float(
                row["revenue"]
                or 0
            ),
            -int(
                row["won_deals"]
                or 0
            ),
            str(
                row["employee_name"]
            ),
        )
    )

    return rows


def _get_dimension_analysis(
    *,
    datasets,
    schema,
    fieldname,
    label_key,
) -> list[dict[str, Any]]:
    if not fieldname:
        return []

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for deal in datasets["analytics_deals"]:
        value = str(
            deal.get(fieldname)
            or _("Not specified")
        )

        grouped[value].append(deal)

    rows: list[dict[str, Any]] = []

    for label, deals in grouped.items():
        won = [
            deal
            for deal in deals
            if deal in datasets["period_won"]
        ]

        lost = [
            deal
            for deal in deals
            if deal in datasets["period_lost"]
        ]

        closed_count = (
            len(won)
            + len(lost)
        )

        rows.append(
            {
                label_key: label,
                "total_deals": len(deals),
                "won_deals": len(won),
                "lost_deals": len(lost),
                "conversion_rate": _percentage(
                    len(won),
                    closed_count,
                ),
                "revenue": _normal_number(
                    sum(
                        _deal_value(
                            deal,
                            schema,
                        )
                        for deal in won
                    )
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            -float(
                row["revenue"]
                or 0
            ),
            -int(
                row["total_deals"]
                or 0
            ),
            str(
                row[label_key]
            ),
        )
    )

    return rows


def _get_funnel(
    *,
    datasets,
    status_order,
) -> list[dict[str, Any]]:
    source_deals = (
        datasets["period_created"]
        or datasets["open_deals"]
    )

    counts = Counter(
        str(
            deal.get("status")
            or _("Not specified")
        )
        for deal in source_deals
    )

    ordered_statuses = [
        status
        for status in status_order
        if status in counts
    ]

    ordered_statuses.extend(
        status
        for status in counts
        if status not in ordered_statuses
    )

    rows: list[dict[str, Any]] = []
    previous_count: int | None = None

    for status in ordered_statuses:
        count = counts[status]

        drop_off = (
            round(
                (
                    max(
                        previous_count - count,
                        0,
                    )
                    / previous_count
                    * 100
                ),
                2,
            )
            if previous_count
            else 0
        )

        rows.append(
            {
                "stage": status,
                "deal_count": count,
                "drop_off_percent": drop_off,
            }
        )

        previous_count = count

    return rows


def _get_forecast(
    *,
    open_deals,
    from_date,
    to_date,
    schema,
) -> list[dict[str, Any]]:
    expected_field = schema[
        "expected_closing_field"
    ]

    if not expected_field:
        return []

    grouped: dict[
        str,
        dict[str, Any],
    ] = defaultdict(
        lambda: {
            "deal_count": 0,
            "pipeline_value": 0.0,
            "weighted_revenue": 0.0,
        }
    )

    for deal in open_deals:
        expected_date = _safe_date(
            deal.get(expected_field)
        )

        if not _date_in_period(
            expected_date,
            from_date,
            to_date,
        ):
            continue

        month = expected_date.strftime(
            "%Y-%m"
        )

        value = _deal_value(
            deal,
            schema,
        )

        probability = _deal_probability(
            deal,
            schema,
        )

        grouped[month][
            "deal_count"
        ] += 1

        grouped[month][
            "pipeline_value"
        ] += value

        grouped[month][
            "weighted_revenue"
        ] += (
            value
            * probability
            / 100
        )

    return [
        {
            "month": month,
            "deal_count": values[
                "deal_count"
            ],
            "pipeline_value": _normal_number(
                values["pipeline_value"]
            ),
            "weighted_revenue": _normal_number(
                values["weighted_revenue"]
            ),
        }
        for month, values in sorted(
            grouped.items()
        )
    ]


def _get_risks(
    *,
    open_deals,
    schema,
    settings,
) -> dict[str, list[dict[str, Any]]]:
    today = getdate(nowdate())

    stale_days = _setting_int(
        settings,
        "stale_deal_days",
        7,
    )

    closing_soon_days = _setting_int(
        settings,
        "closing_soon_days",
        7,
    )

    high_value_threshold = flt(
        getattr(
            settings,
            "high_value_threshold",
            0,
        )
        or 0
    )

    stale_deals: list[dict[str, Any]] = []
    overdue_deals: list[dict[str, Any]] = []
    high_value_closing_soon: list[
        dict[str, Any]
    ] = []

    for deal in open_deals:
        days_without_activity = (
            _days_without_activity(
                deal,
                schema,
                today=today,
            )
        )

        expected_date = _expected_date(
            deal,
            schema,
        )

        value = _deal_value(
            deal,
            schema,
        )

        if days_without_activity > stale_days:
            stale_deals.append(
                _action_row(
                    deal=deal,
                    schema=schema,
                    badge=_(
                        "{0} stale days"
                    ).format(
                        days_without_activity
                    ),
                    priority=(
                        days_without_activity
                    ),
                )
            )

        if (
            expected_date
            and expected_date < today
        ):
            overdue_days = date_diff(
                today,
                expected_date,
            )

            overdue_deals.append(
                _action_row(
                    deal=deal,
                    schema=schema,
                    badge=_(
                        "Overdue by {0} days"
                    ).format(
                        overdue_days
                    ),
                    priority=overdue_days,
                )
            )

        if expected_date:
            days_until_close = date_diff(
                expected_date,
                today,
            )

            if (
                0
                <= days_until_close
                <= closing_soon_days
                and value
                >= high_value_threshold
            ):
                high_value_closing_soon.append(
                    _action_row(
                        deal=deal,
                        schema=schema,
                        badge=_(
                            "Closing in {0} days"
                        ).format(
                            days_until_close
                        ),
                        priority=value,
                    )
                )

    stale_deals.sort(
        key=lambda row: -float(
            row.get("priority")
            or 0
        )
    )

    overdue_deals.sort(
        key=lambda row: -float(
            row.get("priority")
            or 0
        )
    )

    high_value_closing_soon.sort(
        key=lambda row: -float(
            row.get("priority")
            or 0
        )
    )

    return {
        "stale_deals": stale_deals,
        "overdue_deals": overdue_deals,
        "high_value_closing_soon": (
            high_value_closing_soon
        ),
    }


def _get_employee_actions(
    *,
    open_deals,
    schema,
    settings,
) -> dict[str, list[dict[str, Any]]]:
    risks = _get_risks(
        open_deals=open_deals,
        schema=schema,
        settings=settings,
    )

    today = getdate(nowdate())
    due_until = add_days(today, 7)

    follow_up_field = schema[
        "follow_up_field"
    ]

    expected_field = schema[
        "expected_closing_field"
    ]

    closing_soon_days = _setting_int(
        settings,
        "closing_soon_days",
        7,
    )

    follow_up_due: list[
        dict[str, Any]
    ] = []

    closing_soon: list[
        dict[str, Any]
    ] = []

    for deal in open_deals:
        if follow_up_field:
            follow_up_date = _safe_date(
                deal.get(follow_up_field)
            )

            if (
                follow_up_date
                and follow_up_date <= due_until
            ):
                follow_up_due.append(
                    _action_row(
                        deal=deal,
                        schema=schema,
                        badge=_(
                            "Follow-up: {0}"
                        ).format(
                            follow_up_date
                        ),
                        priority=-date_diff(
                            follow_up_date,
                            today,
                        ),
                    )
                )

        if expected_field:
            expected_date = _safe_date(
                deal.get(expected_field)
            )

            if expected_date:
                days_until_close = date_diff(
                    expected_date,
                    today,
                )

                if (
                    0
                    <= days_until_close
                    <= closing_soon_days
                ):
                    closing_soon.append(
                        _action_row(
                            deal=deal,
                            schema=schema,
                            badge=_(
                                "Closing in {0} days"
                            ).format(
                                days_until_close
                            ),
                            priority=-days_until_close,
                        )
                    )

    follow_up_due.sort(
        key=lambda row: -float(
            row.get("priority")
            or 0
        )
    )

    closing_soon.sort(
        key=lambda row: -float(
            row.get("priority")
            or 0
        )
    )

    return {
        "follow_up_due": follow_up_due,
        "stale_deals": risks[
            "stale_deals"
        ],
        "closing_soon": closing_soon,
    }


def _get_trends(
    *,
    deals,
    from_date,
    to_date,
    schema,
    status_map,
) -> list[dict[str, Any]]:
    grouped: dict[
        str,
        dict[str, Any],
    ] = defaultdict(
        lambda: {
            "opened": 0,
            "won": 0,
            "lost": 0,
            "revenue": 0.0,
            "closing_days": [],
        }
    )

    for deal in deals:
        creation_date = _safe_date(
            deal.get("creation")
        )

        if _date_in_period(
            creation_date,
            from_date,
            to_date,
        ):
            grouped[
                creation_date.strftime(
                    "%Y-%m"
                )
            ]["opened"] += 1

        closed_date = _closed_date(
            deal,
            schema,
        )

        if not _date_in_period(
            closed_date,
            from_date,
            to_date,
        ):
            continue

        status_type = _status_type(
            deal.get("status"),
            status_map,
        )

        month = closed_date.strftime(
            "%Y-%m"
        )

        if status_type == "Won":
            grouped[month]["won"] += 1

            grouped[month][
                "revenue"
            ] += _deal_value(
                deal,
                schema,
            )

        elif status_type == "Lost":
            grouped[month]["lost"] += 1

        closing_days = _closing_days(
            deal,
            schema,
        )

        if closing_days is not None:
            grouped[month][
                "closing_days"
            ].append(
                closing_days
            )

    return [
        {
            "month": month,
            "opened": values["opened"],
            "won": values["won"],
            "lost": values["lost"],
            "revenue": _normal_number(
                values["revenue"]
            ),
            "average_closing_days": _average(
                values["closing_days"]
            ),
        }
        for month, values in sorted(
            grouped.items()
        )
    ]


def _get_personal_pipeline(
    *,
    open_deals,
    status_order,
) -> list[dict[str, Any]]:
    counts = Counter(
        str(
            deal.get("status")
            or _("Not specified")
        )
        for deal in open_deals
    )

    ordered_statuses = [
        status
        for status in status_order
        if status in counts
    ]

    ordered_statuses.extend(
        status
        for status in counts
        if status not in ordered_statuses
    )

    return [
        {
            "stage": status,
            "deal_count": counts[status],
        }
        for status in ordered_statuses
    ]


def _build_meta(
    *,
    context,
    settings,
    schema,
    warnings,
) -> dict[str, Any]:
    return {
        "current_user": context[
            "current_user"
        ],
        "can_switch_view": context[
            "can_switch_view"
        ],
        "is_manager": context[
            "is_manager"
        ],
        "effective_employee": (
            context["employee"]
            or None
        ),
         "currency": _get_base_currency(),
        "stale_deal_days": _setting_int(
            settings,
            "stale_deal_days",
            7,
        ),
        "closing_soon_days": _setting_int(
            settings,
            "closing_soon_days",
            7,
        ),
        "detected_fields": schema,
        "warnings": warnings,
    }


def _top_lost_reason(
    deals: list[dict[str, Any]],
    schema,
) -> str:
    fieldname = schema[
        "lost_reason_field"
    ]

    if not fieldname:
        return ""

    values = [
        str(
            deal.get(fieldname)
            or ""
        ).strip()
        for deal in deals
    ]

    values = [
        value
        for value in values
        if value
    ]

    if not values:
        return ""

    return Counter(
        values
    ).most_common(1)[0][0]


def _deal_value(
    deal: dict[str, Any],
    schema,
) -> float:
    value_field = schema.get(
        "value_field"
    )

    if not value_field:
        return 0.0

    value = flt(
        deal.get(value_field),
        2,
    )

    currency_field = schema.get(
        "currency_field"
    )

    deal_currency = (
        str(
            deal.get(currency_field)
            or ""
        )
        .strip()
        .upper()
        if currency_field
        else ""
    )

    base_currency = _get_base_currency()

    # Deal đã là VND và báo cáo cũng là VND:
    # không được nhân exchange_rate.
    if (
        not deal_currency
        or deal_currency == base_currency
    ):
        return value

    exchange_rate_field = schema.get(
        "exchange_rate_field"
    )

    if not exchange_rate_field:
        return value

    exchange_rate = flt(
        deal.get(exchange_rate_field),
        6,
    )

    if exchange_rate <= 0:
        return value

    return flt(
        value * exchange_rate,
        2,
    )

def _deal_probability(
    deal: dict[str, Any],
    schema,
) -> float:
    fieldname = schema[
        "probability_field"
    ]

    if not fieldname:
        return 0.0

    probability = flt(
        deal.get(fieldname),
        2,
    )

    return min(
        max(
            probability,
            0,
        ),
        100,
    )


def _closed_date(
    deal: dict[str, Any],
    schema,
):
    fieldname = schema[
        "closed_date_field"
    ]

    if not fieldname:
        return None

    return _safe_date(
        deal.get(fieldname)
    )


def _expected_date(
    deal: dict[str, Any],
    schema,
):
    fieldname = schema[
        "expected_closing_field"
    ]

    if not fieldname:
        return None

    return _safe_date(
        deal.get(fieldname)
    )


def _closing_days(
    deal: dict[str, Any],
    schema,
) -> int | None:
    created = _safe_date(
        deal.get("creation")
    )

    closed = _closed_date(
        deal,
        schema,
    )

    if not created or not closed:
        return None

    return max(
        date_diff(
            closed,
            created,
        ),
        0,
    )


def _days_without_activity(
    deal: dict[str, Any],
    schema,
    *,
    today,
) -> int:
    fieldname = (
        schema["last_activity_field"]
        or "modified"
    )

    activity_date = _safe_date(
        deal.get(fieldname)
    )

    if not activity_date:
        return 0

    return max(
        date_diff(
            today,
            activity_date,
        ),
        0,
    )


def _action_row(
    *,
    deal,
    schema,
    badge,
    priority,
) -> dict[str, Any]:
    name = str(
        deal.get("name")
        or ""
    )

    title_field = (
        schema["title_field"]
        or "name"
    )

    title = str(
        deal.get(title_field)
        or name
    )

    territory_field = schema[
        "territory_field"
    ]

    return {
        "name": name,
        "title": title,
        "subtitle": str(
            deal.get(territory_field)
            if territory_field
            else ""
        ),
        "badge": badge,
        "deal_value": _normal_number(
            _deal_value(
                deal,
                schema,
            )
        ),
        "expected_closing_date": str(
            _expected_date(
                deal,
                schema,
            )
            or ""
        ),
        "route": f"/crm/deals/{name}",
        "priority": _normal_number(
            priority
        ),
    }


def _get_user_names(
    user_ids: Iterable[str],
) -> dict[str, str]:
    result: dict[str, str] = {}

    for user_id in user_ids:
        if not user_id:
            continue

        full_name = frappe.db.get_value(
            "User",
            user_id,
            "full_name",
        )

        result[user_id] = (
            full_name
            or user_id
        )

    return result


def _status_type(
    status,
    status_map: dict[str, str],
) -> str:
    status_name = str(
        status
        or ""
    )

    mapped = str(
        status_map.get(status_name)
        or ""
    )

    if mapped in {"Won", "Lost"}:
        return mapped

    lowered = status_name.casefold()

    if (
        "won" in lowered
        or "thắng" in lowered
    ):
        return "Won"

    if (
        "lost" in lowered
        or "thua" in lowered
    ):
        return "Lost"

    return "Open"


def _field_value(
    row: dict[str, Any],
    fieldname: str | None,
) -> str:
    if not fieldname:
        return ""

    return str(
        row.get(fieldname)
        or ""
    )


def _safe_date(value):
    if not value:
        return None

    try:
        return getdate(value)
    except Exception:
        return None


def _date_in_period(
    value,
    from_date,
    to_date,
) -> bool:
    return bool(
        value
        and from_date
        <= value
        <= to_date
    )


def _unique_deals(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        name = str(
            row.get("name")
            or ""
        )

        if name and name in seen:
            continue

        if name:
            seen.add(name)

        result.append(row)

    return result


def _percentage(
    numerator,
    denominator,
) -> float:
    if not denominator:
        return 0

    return round(
        (
            float(numerator)
            / float(denominator)
            * 100
        ),
        2,
    )


def _average(
    values: Iterable[float],
) -> float:
    values = list(values)

    if not values:
        return 0

    return round(
        sum(values)
        / len(values),
        2,
    )


def _trend_percent(
    current,
    previous,
) -> float:
    current = float(
        current
        or 0
    )

    previous = float(
        previous
        or 0
    )

    if previous == 0:
        return (
            100.0
            if current > 0
            else 0.0
        )

    return round(
        (
            current - previous
        )
        / previous
        * 100,
        2,
    )


def _normal_number(value):
    rounded = round(
        float(
            value
            or 0
        ),
        2,
    )

    if rounded.is_integer():
        return int(rounded)

    return rounded


def _setting_int(
    settings,
    fieldname: str,
    default: int,
) -> int:
    return cint(
        getattr(
            settings,
            fieldname,
            default,
        )
        or default
    )
def _get_base_currency() -> str:
    currency = ""

    if frappe.db.exists(
        "DocType",
        "FCRM Settings",
    ):
        currency = (
            frappe.db.get_single_value(
                "FCRM Settings",
                "currency",
            )
            or ""
        )

    if (
        not currency
        and frappe.db.exists(
            "DocType",
            "CRM Reports Settings",
        )
    ):
        currency = (
            frappe.db.get_single_value(
                "CRM Reports Settings",
                "report_currency",
            )
            or ""
        )

    return str(
        currency or "VND"
    ).strip().upper()
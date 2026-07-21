from __future__ import annotations


from collections import defaultdict
from typing import Any


import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, get_datetime, now_datetime
from crm_reports.permissions import get_report_context




DEAL_DOCTYPE = "CRM Deal"
REPORT_NAME = "Deal Closing Performance Report"
PAGE_SIZE = 500
MAX_REPORT_DAYS = 366


EMPLOYEE_FIELD_CANDIDATES = ("deal_owner", "owner")
REVENUE_FIELD_CANDIDATES = (
    "deal_value",
    "net_total",
    "total",
    "expected_deal_value",
    "annual_revenue",
)
CLOSED_DATE_FIELD_CANDIDATES = ("closed_date", "modified")
DEAL_TITLE_FIELD_CANDIDATES = (
    "deal_name",
    "organization_name",
    "organization",
    "lead_name",
)

def _attach_view_meta(
    response: dict,
    context: dict,
) -> dict:
    response.setdefault("meta", {})

    response["meta"].update(
        {
            "view_mode": context["view_mode"],
            "is_manager": context["is_manager"],
            "can_switch_view": context["can_switch_view"],
            "effective_employee": context["employee"] or None,
        }
    )

    return response



@frappe.whitelist()
def get_deal_performance_report(
    from_date: str,
    to_date: str,
    employee: str | None = None,
    status: str | None = None,
    view_mode: str | None = None,
) -> dict[str, Any]:
    """Return the Deal performance report in the agreed frontend JSON format."""

    from_date_obj, to_date_obj = _validate_filters(from_date, to_date)

    context = get_report_context(
        view_mode=view_mode,
        selected_employee=employee,
    )
    employee = context["employee"]

    requested_status = (status or "Won").strip() or "Won"

    meta = frappe.get_meta(DEAL_DOCTYPE)
    warnings: list[str] = []

    employee_field = _first_existing_field(meta, EMPLOYEE_FIELD_CANDIDATES)
    revenue_field = _first_existing_field(meta, REVENUE_FIELD_CANDIDATES)
    closed_date_field = _first_existing_field(
        meta,
        CLOSED_DATE_FIELD_CANDIDATES,
    )
    title_fields = [
        fieldname
        for fieldname in DEAL_TITLE_FIELD_CANDIDATES
        if meta.has_field(fieldname)
    ]

    if not employee_field:
        frappe.throw(
            _("Could not find the employee owner field in CRM Deal."),
            title=_("CRM Deal Configuration Missing"),
        )

    if not closed_date_field:
        frappe.throw(
            _("Could not find a closing date field or the modified field in CRM Deal."),
            title=_("CRM Deal Configuration Missing"),
        )

    if not revenue_field:
        warnings.append(
            _(
                "CRM Deal has no suitable revenue/value field; "
                "revenue is returned as 0."
            )
        )

    if employee_field == "owner":
        warnings.append(
            _(
                "Could not find deal_owner; the report is using owner "
                "as the responsible employee."
            )
        )

    if closed_date_field == "modified":
        warnings.append(
            _(
                "Could not find closed_date; the report is using "
                "modified as the closing date."
            )
        )

    success_statuses = _resolve_success_statuses(requested_status)

    if not success_statuses:
        response = _build_empty_response(
            from_date_obj=from_date_obj,
            to_date_obj=to_date_obj,
            employee=employee,
            requested_status=requested_status,
            employee_field=employee_field,
            revenue_field=revenue_field,
            closed_date_field=closed_date_field,
            warnings=[
                *warnings,
                _(
                    "No Deal status matched the filter '{0}'."
                ).format(requested_status),
            ],
        )
        return _attach_view_meta(response, context)

    deals = _get_deals(
        meta=meta,
        from_date=from_date_obj,
        to_date=to_date_obj,
        employee=employee,
        success_statuses=success_statuses,
        employee_field=employee_field,
        revenue_field=revenue_field,
        closed_date_field=closed_date_field,
        title_fields=title_fields,
    )

    response = _build_report(
        deals=deals,
        from_date_obj=from_date_obj,
        to_date_obj=to_date_obj,
        employee=employee,
        requested_status=requested_status,
        employee_field=employee_field,
        revenue_field=revenue_field,
        closed_date_field=closed_date_field,
        title_fields=title_fields,
        warnings=warnings,
    )

    return _attach_view_meta(response, context)

def _validate_filters(from_date: str, to_date: str):
    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required."))


    try:
        from_date_obj = getdate(from_date)
        to_date_obj = getdate(to_date)
    except Exception:
        frappe.throw(_("Invalid date. The correct format is YYYY-MM-DD."))


    if from_date_obj > to_date_obj:
        frappe.throw(_("From Date cannot be later than To Date."))


    total_days = date_diff(to_date_obj, from_date_obj) + 1
    if total_days > MAX_REPORT_DAYS:
        frappe.throw(
            _("The report date range cannot exceed {0} days.").format(
                MAX_REPORT_DAYS
            )
        )


    return from_date_obj, to_date_obj




def _first_existing_field(meta, candidates: tuple[str, ...]) -> str | None:
    for fieldname in candidates:
        if fieldname in {"owner", "creation", "modified", "name"}:
            return fieldname
        if meta.has_field(fieldname):
            return fieldname
    return None




def _resolve_success_statuses(requested_status: str) -> list[str]:
    """
    `CRM Deal.status` is a Link to CRM Deal Status.


    When frontend sends "Won", select every configured status whose type is Won.
    This also supports customized status names such as "Đã chốt".
    For any other value, treat it as an exact CRM Deal Status name.
    """
    if requested_status.casefold() == "won":
        statuses = frappe.get_all(
            "CRM Deal Status",
            filters={"type": "Won"},
            pluck="name",
        )
        if statuses:
            return statuses


        if frappe.db.exists("CRM Deal Status", "Won"):
            return ["Won"]


        return []


    if frappe.db.exists("CRM Deal Status", requested_status):
        return [requested_status]


    return []




def _get_deals(
    *,
    meta,
    from_date,
    to_date,
    employee: str,
    success_statuses: list[str],
    employee_field: str,
    revenue_field: str | None,
    closed_date_field: str,
    title_fields: list[str],
) -> list[dict[str, Any]]:
    fields = ["name", "creation", "status", employee_field, closed_date_field]


    if revenue_field:
        fields.append(revenue_field)


    for fieldname in title_fields:
        if fieldname not in fields:
            fields.append(fieldname)


    filters: dict[str, Any] = {
        "status": ["in", success_statuses],
        closed_date_field: _date_range_filter(
            meta=meta,
            fieldname=closed_date_field,
            from_date=from_date,
            to_date=to_date,
        ),
    }


    if employee:
        filters[employee_field] = employee


    deals: list[dict[str, Any]] = []
    start = 0


    while True:
        batch = frappe.get_list(
            DEAL_DOCTYPE,
            filters=filters,
            fields=fields,
            order_by=f"{closed_date_field} asc, name asc",
            start=start,
            page_length=PAGE_SIZE,
        )


        if not batch:
            break


        deals.extend(batch)


        if len(batch) < PAGE_SIZE:
            break


        start += PAGE_SIZE


    return deals




def _date_range_filter(*, meta, fieldname: str, from_date, to_date):
    fieldtype = "Datetime" if fieldname == "modified" else None


    if fieldname not in {"modified", "creation", "owner", "name"}:
        docfield = meta.get_field(fieldname)
        fieldtype = docfield.fieldtype if docfield else fieldtype


    if fieldtype in {"Datetime", "Timestamp"}:
        return [
            "between",
            [
                f"{from_date} 00:00:00",
                f"{to_date} 23:59:59.999999",
            ],
        ]


    return ["between", [str(from_date), str(to_date)]]




def _build_report(
    *,
    deals: list[dict[str, Any]],
    from_date_obj,
    to_date_obj,
    employee: str,
    requested_status: str,
    employee_field: str,
    revenue_field: str | None,
    closed_date_field: str,
    title_fields: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "won_deal_count": 0,
            "deal_revenue": 0.0,
            "closing_days": [],
            "deals": [],
        }
    )


    all_closing_days: list[int] = []
    total_revenue = 0.0


    for deal in deals:
        employee_id = (deal.get(employee_field) or "").strip()
        deal_revenue = flt(deal.get(revenue_field), 2) if revenue_field else 0.0
        closing_days = _closing_days(
            created_at=deal.get("creation"),
            closed_at=deal.get(closed_date_field),
        )


        deal_name = _pick_deal_title(deal, title_fields)
        customer_name = _pick_customer_name(deal)


        group = groups[employee_id]
        group["won_deal_count"] += 1
        group["deal_revenue"] += deal_revenue


        total_revenue += deal_revenue


        if closing_days is not None:
            group["closing_days"].append(closing_days)
            all_closing_days.append(closing_days)


        group["deals"].append(
            {
                "deal_id": deal.get("name"),
                "deal_name": deal_name,
                "customer_name": customer_name,
                "deal_value": _normal_number(deal_revenue),
                "created_at": _format_datetime(deal.get("creation")),
                "closed_at": _format_datetime(deal.get(closed_date_field)),
                "closing_days": closing_days if closing_days is not None else 0,
                "status": deal.get("status"),
            }
        )


    employee_names = _get_employee_names(groups.keys())


    total_won_deals = len(deals)
    employees: list[dict[str, Any]] = []


    for employee_id, group in groups.items():
        closing_values = group["closing_days"]
        deal_count = group["won_deal_count"]


        employees.append(
            {
                "employee": employee_id,
                "employee_name": employee_names.get(employee_id)
                or (_("Unassigned") if not employee_id else employee_id),
                "won_deal_count": deal_count,
                "deal_revenue": _normal_number(group["deal_revenue"]),
                "average_closing_days": _average(closing_values),
                "fastest_closing_days": min(closing_values) if closing_values else 0,
                "slowest_closing_days": max(closing_values) if closing_values else 0,
                "percentage_of_total_deals": round(
                    (deal_count / total_won_deals * 100) if total_won_deals else 0,
                    2,
                ),
                "deals": group["deals"],
            }
        )


    employees.sort(
        key=lambda row: (
            -row["won_deal_count"],
            -float(row["deal_revenue"]),
            row["employee_name"],
        )
    )


    assigned_employees = [row for row in employees if row["employee"]]
    top_employee = None
    if assigned_employees:
        top = assigned_employees[0]
        top_employee = {
            "employee": top["employee"],
            "employee_name": top["employee_name"],
            "won_deal_count": top["won_deal_count"],
            "deal_revenue": top["deal_revenue"],
            "average_closing_days": top["average_closing_days"],
        }


    labels = [row["employee_name"] for row in employees]


    return {
        "success": True,
        "report_name": _(REPORT_NAME),
        "summary": {
            "report_period": {
                "from_date": str(from_date_obj),
                "to_date": str(to_date_obj),
                "total_days": date_diff(to_date_obj, from_date_obj) + 1,
            },
            "total_employees": len(assigned_employees),
            "total_won_deals": total_won_deals,
            "total_deal_revenue": _normal_number(total_revenue),
            "average_closing_days": _average(all_closing_days),
            "fastest_closing_days": min(all_closing_days)
            if all_closing_days
            else 0,
            "slowest_closing_days": max(all_closing_days)
            if all_closing_days
            else 0,
            "top_employee": top_employee,
        },
        "employees": employees,
        "chart": {
            "deal_count_by_employee": {
                "labels": labels,
                "values": [row["won_deal_count"] for row in employees],
            },
            "average_closing_days_by_employee": {
                "labels": labels,
                "values": [row["average_closing_days"] for row in employees],
            },
            "revenue_by_employee": {
                "labels": labels,
                "values": [row["deal_revenue"] for row in employees],
            },
        },
        "filters": {
            "from_date": str(from_date_obj),
            "to_date": str(to_date_obj),
            "employee": employee,
            "status": requested_status,
        },
        "meta": {
            "doctype": DEAL_DOCTYPE,
            "employee_field": employee_field,
            "status_field": "status",
            "revenue_field": revenue_field,
            "created_date_field": "creation",
            "closed_date_field": closed_date_field,
            "closing_time_unit": "day",
            "currency": _get_default_currency(),
            "generated_at": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "warnings": warnings,
    }




def _build_empty_response(
    *,
    from_date_obj,
    to_date_obj,
    employee: str,
    requested_status: str,
    employee_field: str,
    revenue_field: str | None,
    closed_date_field: str,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "success": True,
        "report_name": _(REPORT_NAME),
        "summary": {
            "report_period": {
                "from_date": str(from_date_obj),
                "to_date": str(to_date_obj),
                "total_days": date_diff(to_date_obj, from_date_obj) + 1,
            },
            "total_employees": 0,
            "total_won_deals": 0,
            "total_deal_revenue": 0,
            "average_closing_days": 0,
            "fastest_closing_days": 0,
            "slowest_closing_days": 0,
            "top_employee": None,
        },
        "employees": [],
        "chart": {
            "deal_count_by_employee": {"labels": [], "values": []},
            "average_closing_days_by_employee": {"labels": [], "values": []},
            "revenue_by_employee": {"labels": [], "values": []},
        },
        "filters": {
            "from_date": str(from_date_obj),
            "to_date": str(to_date_obj),
            "employee": employee,
            "status": requested_status,
        },
        "meta": {
            "doctype": DEAL_DOCTYPE,
            "employee_field": employee_field,
            "status_field": "status",
            "revenue_field": revenue_field,
            "created_date_field": "creation",
            "closed_date_field": closed_date_field,
            "closing_time_unit": "day",
            "currency": _get_default_currency(),
            "generated_at": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "warnings": warnings,
    }




def _get_employee_names(employee_ids) -> dict[str, str]:
    result: dict[str, str] = {}


    for employee_id in employee_ids:
        if not employee_id:
            continue


        full_name = frappe.db.get_value("User", employee_id, "full_name")
        result[employee_id] = full_name or employee_id


    return result




def _pick_deal_title(deal: dict[str, Any], title_fields: list[str]) -> str:
    for fieldname in title_fields:
        value = deal.get(fieldname)
        if value:
            return str(value)


    return str(deal.get("name") or "")




def _pick_customer_name(deal: dict[str, Any]) -> str:
    for fieldname in ("organization_name", "organization", "lead_name"):
        value = deal.get(fieldname)
        if value:
            return str(value)


    return ""




def _closing_days(created_at, closed_at) -> int | None:
    if not created_at or not closed_at:
        return None


    days = date_diff(getdate(closed_at), getdate(created_at))
    return max(days, 0)




def _average(values: list[int]) -> float:
    if not values:
        return 0


    return round(sum(values) / len(values), 2)




def _normal_number(value: float):
    rounded = round(float(value or 0), 2)
    return int(rounded) if rounded.is_integer() else rounded




def _format_datetime(value) -> str:
    if not value:
        return ""


    return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")




def _get_default_currency() -> str:
    if frappe.db.exists("DocType", "FCRM Settings"):
        currency = frappe.db.get_single_value("FCRM Settings", "currency")
        if currency:
            return currency


    return "VND"
from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_days, getdate, nowdate
from frappe.utils.password import update_password


DEAL_DOCTYPE = "CRM Deal"
LEAD_DOCTYPE = "CRM Lead"
STATUS_DOCTYPE = "CRM Deal Status"

DEMO_PREFIX = "CRM Reports Demo - "
DEMO_PASSWORD = "Demo@12345"

SARAH = "sarah.connor@example.com"
JOHN = "john.parker@example.com"


def _first_field(meta, candidates):
    standard_fields = {
        "name",
        "owner",
        "creation",
        "modified",
        "status",
    }

    for fieldname in candidates:
        if fieldname in standard_fields or meta.has_field(fieldname):
            return fieldname

    return None


def _deal_schema():
    meta = frappe.get_meta(DEAL_DOCTYPE)

    return {
        "title": _first_field(
            meta,
            (
                "deal_name",
                "organization_name",
                "organization",
                "lead_name",
            ),
        ),
        "employee": _first_field(
            meta,
            ("deal_owner", "sales_person", "owner"),
        ),
        "team": _first_field(
            meta,
            ("team", "sales_team", "sales_team_name"),
        ),
        "value": _first_field(
            meta,
            (
                "deal_value",
                "expected_deal_value",
                "net_total",
                "total",
            ),
        ),
        "currency": _first_field(
            meta,
            ("currency", "deal_currency"),
        ),
        "exchange_rate": _first_field(
            meta,
            ("exchange_rate",),
        ),
        "expected": _first_field(
            meta,
            (
                "expected_closure_date",
                "expected_closing_date",
            ),
        ),
        "probability": _first_field(
            meta,
            ("probability", "deal_probability"),
        ),
        "source": _first_field(
            meta,
            ("source", "lead_source"),
        ),
        "territory": _first_field(
            meta,
            ("territory", "region"),
        ),
        "lost_reason": _first_field(
            meta,
            (
                "lost_reason",
                "deal_lost_reason",
                "reason_for_loss",
                "reason",
            ),
        ),
        "closed_date": _first_field(
            meta,
            (
                "custom_closed_date",
                "closed_date",
                "modified",
            ),
        ),
        "last_activity": _first_field(
            meta,
            (
                "last_activity_date",
                "last_interaction_date",
                "modified",
            ),
        ),
        "follow_up": _first_field(
            meta,
            (
                "next_follow_up_date",
                "follow_up_date",
                "next_contact_date",
                "next_action_date",
            ),
        ),
    }


def _lead_schema():
    meta = frappe.get_meta(LEAD_DOCTYPE)

    return {
        "first_name": _first_field(
            meta,
            ("first_name", "lead_name"),
        ),
        "last_name": _first_field(
            meta,
            ("last_name",),
        ),
        "email": _first_field(
            meta,
            ("email", "email_id"),
        ),
        "employee": _first_field(
            meta,
            ("lead_owner", "deal_owner", "owner"),
        ),
        "source": _first_field(
            meta,
            ("source", "lead_source"),
        ),
        "territory": _first_field(
            meta,
            ("territory", "region"),
        ),
    }


def _status_names():
    rows = frappe.get_all(
        STATUS_DOCTYPE,
        fields=["name", "type"],
        order_by="creation asc",
    )

    if not rows:
        frappe.throw(
            "CRM Deal Status chưa có dữ liệu. "
            "Hãy tạo các trạng thái Open, Won và Lost trước."
        )

    won = next(
        (
            row.name
            for row in rows
            if str(row.type or "").casefold() == "won"
        ),
        None,
    )

    lost = next(
        (
            row.name
            for row in rows
            if str(row.type or "").casefold() == "lost"
        ),
        None,
    )

    if not won:
        won = next(
            (
                row.name
                for row in rows
                if "won" in row.name.casefold()
            ),
            None,
        )

    if not lost:
        lost = next(
            (
                row.name
                for row in rows
                if "lost" in row.name.casefold()
            ),
            None,
        )

    open_statuses = [
        row.name
        for row in rows
        if row.name not in {won, lost}
    ]

    if not won or not lost or not open_statuses:
        frappe.throw(
            "Cần ít nhất một trạng thái Won, "
            "một trạng thái Lost và một trạng thái Open."
        )

    return {
        "won": won,
        "lost": lost,
        "open": open_statuses,
    }


def _set(doc, fieldname, value):
    if fieldname and value is not None:
        doc.set(fieldname, value)


def _demo_datetime(day_offset, hour=9):
    day = add_days(getdate(nowdate()), day_offset)
    return f"{day} {hour:02d}:00:00"


def _ensure_sales_user(email, first_name, last_name):
    if not frappe.db.exists("User", email):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "enabled": 1,
                "user_type": "System User",
                "send_welcome_email": 0,
            }
        )

        user.insert(ignore_permissions=True)
    else:
        user = frappe.get_doc("User", email)

    if "Sales User" not in frappe.get_roles(email):
        user.add_roles("Sales User")

    update_password(email, DEMO_PASSWORD)

    return email


def _insert_deal(schema, values):
    doc = frappe.new_doc(DEAL_DOCTYPE)

    _set(doc, schema["title"], values["title"])
    _set(doc, schema["employee"], values["employee"])
    _set(doc, schema["team"], values.get("team"))
    _set(doc, schema["value"], values["value"])
    _set(doc, schema["currency"], "VND")
    _set(doc, schema["exchange_rate"], 1)
    _set(doc, schema["expected"], values.get("expected"))
    _set(doc, schema["probability"], values.get("probability"))
    _set(doc, schema["source"], values.get("source"))
    _set(doc, schema["territory"], values.get("territory"))
    _set(doc, schema["lost_reason"], values.get("lost_reason"))
    _set(doc, schema["follow_up"], values.get("follow_up"))

    doc.status = values["status"]

    closed_field = schema["closed_date"]

    if closed_field and closed_field != "modified":
        _set(doc, closed_field, values.get("closed"))

    activity_field = schema["last_activity"]

    if activity_field and activity_field != "modified":
        _set(doc, activity_field, values.get("activity"))

    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert()

    modified = (
        values.get("activity")
        or values.get("closed")
        or values["creation"]
    )

    frappe.db.set_value(
        DEAL_DOCTYPE,
        doc.name,
        {
            "creation": values["creation"],
            "modified": modified,
        },
        update_modified=False,
    )

    return doc.name


def _insert_lead(schema, index, employee, source, territory):
    doc = frappe.new_doc(LEAD_DOCTYPE)

    _set(
        doc,
        schema["first_name"],
        f"CRM Reports Demo Lead {index}",
    )

    _set(doc, schema["last_name"], "Testing")

    _set(
        doc,
        schema["email"],
        f"crm.reports.demo+{index}@example.com",
    )

    _set(doc, schema["employee"], employee)
    _set(doc, schema["source"], source)
    _set(doc, schema["territory"], territory)

    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_links = True
    doc.insert()

    frappe.db.set_value(
        LEAD_DOCTYPE,
        doc.name,
        {
            "creation": _demo_datetime(-index),
            "modified": _demo_datetime(-index),
        },
        update_modified=False,
    )

    return doc.name


def _configure_settings():
    if frappe.db.exists("DocType", "FCRM Settings"):
        frappe.db.set_single_value(
            "FCRM Settings",
            "currency",
            "VND",
        )

    if frappe.db.exists(
        "DocType",
        "CRM Reports Settings",
    ):
        meta = frappe.get_meta(
            "CRM Reports Settings"
        )

        values = {
            "report_currency": "VND",
            "stale_deal_days": 7,
            "closing_soon_days": 7,
            "high_value_threshold": 100000,
            "show_employee_ranking": 1,
            "show_forecast": 1,
        }

        for fieldname, value in values.items():
            if meta.has_field(fieldname):
                frappe.db.set_single_value(
                    "CRM Reports Settings",
                    fieldname,
                    value,
                )


def clear_demo_data():
    deleted_deals = 0
    deleted_leads = 0

    if frappe.db.exists("DocType", DEAL_DOCTYPE):
        schema = _deal_schema()
        title_field = schema["title"]

        if title_field:
            names = frappe.get_all(
                DEAL_DOCTYPE,
                filters={
                    title_field: [
                        "like",
                        f"{DEMO_PREFIX}%",
                    ]
                },
                pluck="name",
            )

            for name in names:
                frappe.delete_doc(
                    DEAL_DOCTYPE,
                    name,
                    force=True,
                    ignore_permissions=True,
                )
                deleted_deals += 1

    if frappe.db.exists("DocType", LEAD_DOCTYPE):
        schema = _lead_schema()
        email_field = schema["email"]

        if email_field:
            names = frappe.get_all(
                LEAD_DOCTYPE,
                filters={
                    email_field: [
                        "like",
                        "crm.reports.demo+%@example.com",
                    ]
                },
                pluck="name",
            )

            for name in names:
                frappe.delete_doc(
                    LEAD_DOCTYPE,
                    name,
                    force=True,
                    ignore_permissions=True,
                )
                deleted_leads += 1

    frappe.db.commit()

    return {
        "deleted_deals": deleted_deals,
        "deleted_leads": deleted_leads,
    }


def create_demo_data():
    clear_demo_data()
    _configure_settings()

    sarah = _ensure_sales_user(
        SARAH,
        "Sarah",
        "Connor",
    )

    john = _ensure_sales_user(
        JOHN,
        "John",
        "Parker",
    )

    schema = _deal_schema()
    lead_schema = _lead_schema()
    statuses = _status_names()

    open_statuses = statuses["open"]

    qualification = open_statuses[0]
    proposal = open_statuses[
        min(1, len(open_statuses) - 1)
    ]
    negotiation = open_statuses[
        min(2, len(open_statuses) - 1)
    ]

    deals = [
        {
            "title": f"{DEMO_PREFIX}Sarah Won",
            "employee": sarah,
            "team": "Team Alpha",
            "status": statuses["won"],
            "value": 175000,
            "probability": 100,
            "source": "Reference",
            "territory": "Ho Chi Minh",
            "creation": _demo_datetime(-24),
            "closed": _demo_datetime(-3),
            "activity": _demo_datetime(-3),
            "expected": add_days(nowdate(), -3),
        },
        {
            "title": f"{DEMO_PREFIX}Sarah Stale",
            "employee": sarah,
            "team": "Team Alpha",
            "status": qualification,
            "value": 120000,
            "probability": 25,
            "source": "Cold Calling",
            "territory": "Ho Chi Minh",
            "creation": _demo_datetime(-20),
            "activity": _demo_datetime(-10),
            "expected": add_days(nowdate(), 20),
        },
        {
            "title": f"{DEMO_PREFIX}Sarah Follow-up",
            "employee": sarah,
            "team": "Team Alpha",
            "status": proposal,
            "value": 250000,
            "probability": 70,
            "source": "Reference",
            "territory": "Ho Chi Minh",
            "creation": _demo_datetime(-15),
            "activity": _demo_datetime(-1),
            "expected": add_days(nowdate(), 3),
            "follow_up": add_days(nowdate(), 1),
        },
        {
            "title": f"{DEMO_PREFIX}Sarah Pipeline",
            "employee": sarah,
            "team": "Team Alpha",
            "status": negotiation,
            "value": 60000,
            "probability": 50,
            "source": "Advertisement",
            "territory": "Ha Noi",
            "creation": _demo_datetime(-12),
            "activity": _demo_datetime(-9),
            "expected": add_days(nowdate(), 30),
        },
        {
            "title": f"{DEMO_PREFIX}John Overdue",
            "employee": john,
            "team": "Team Alpha",
            "status": negotiation,
            "value": 85000,
            "probability": 60,
            "source": "Advertisement",
            "territory": "Ha Noi",
            "creation": _demo_datetime(-18),
            "activity": _demo_datetime(-8),
            "expected": add_days(nowdate(), -2),
        },
        {
            "title": f"{DEMO_PREFIX}John Closing Soon",
            "employee": john,
            "team": "Team Alpha",
            "status": qualification,
            "value": 200000,
            "probability": 40,
            "source": "Reference",
            "territory": "Da Nang",
            "creation": _demo_datetime(-10),
            "activity": _demo_datetime(-1),
            "expected": add_days(nowdate(), 5),
            "follow_up": add_days(nowdate(), 2),
        },
        {
            "title": f"{DEMO_PREFIX}John Lost Budget",
            "employee": john,
            "team": "Team Alpha",
            "status": statuses["lost"],
            "value": 95000,
            "probability": 0,
            "source": "Cold Calling",
            "territory": "Ha Noi",
            "lost_reason": "Budget",
            "creation": _demo_datetime(-22),
            "closed": _demo_datetime(-4),
            "activity": _demo_datetime(-4),
            "expected": add_days(nowdate(), -4),
        },
        {
            "title": f"{DEMO_PREFIX}John Lost No Response",
            "employee": john,
            "team": "Team Alpha",
            "status": statuses["lost"],
            "value": 55000,
            "probability": 0,
            "source": "Advertisement",
            "territory": "Da Nang",
            "lost_reason": "No Response",
            "creation": _demo_datetime(-17),
            "closed": _demo_datetime(-2),
            "activity": _demo_datetime(-2),
            "expected": add_days(nowdate(), -2),
        },
    ]

    deal_names = [
        _insert_deal(schema, values)
        for values in deals
    ]

    lead_data = [
        (sarah, "Reference", "Ho Chi Minh"),
        (sarah, "Reference", "Ho Chi Minh"),
        (sarah, "Advertisement", "Ha Noi"),
        (john, "Cold Calling", "Ha Noi"),
        (john, "Advertisement", "Da Nang"),
        (john, "Reference", "Da Nang"),
        (john, "Cold Calling", "Ho Chi Minh"),
    ]

    lead_names = [
        _insert_lead(
            lead_schema,
            index,
            employee,
            source,
            territory,
        )
        for index, (
            employee,
            source,
            territory,
        ) in enumerate(lead_data, start=1)
    ]

    frappe.db.commit()

    return {
        "success": True,
        "users": {
            "sarah": SARAH,
            "john": JOHN,
            "password": DEMO_PASSWORD,
        },
        "statuses": statuses,
        "deal_count": len(deal_names),
        "lead_count": len(lead_names),
        "deals": deal_names,
        "leads": lead_names,
    }

from __future__ import annotations

import frappe
from frappe import _


MANAGER_ROLES = {
    "Sales Manager",
    "System Manager",
}

SALES_ROLES = {
    "Sales User",
    "Sales Manager",
    "System Manager",
}


def get_report_context(
    view_mode: str | None = None,
    selected_employee: str | None = None,
) -> dict:
    current_user = frappe.session.user

    if not current_user or current_user == "Guest":
        frappe.throw(
            _("You must sign in to view CRM reports."),
            exc=frappe.PermissionError,
        )

    current_roles = set(frappe.get_roles(current_user))

    is_manager = (
        current_user == "Administrator"
        or bool(current_roles & MANAGER_ROLES)
    )

    employee = _clean_value(selected_employee)
    requested_mode = _clean_value(view_mode).lower()

    if requested_mode and requested_mode not in {
        "manager",
        "employee",
    }:
        frappe.throw(
            _("Invalid dashboard view mode."),
            exc=frappe.ValidationError,
        )

    # Nhân viên bình thường luôn chỉ được xem chính mình.
    if not is_manager:
        if not current_roles & SALES_ROLES:
            frappe.throw(
                _("You do not have permission to view CRM reports."),
                exc=frappe.PermissionError,
            )

        return {
            "current_user": current_user,
            "view_mode": "employee",
            "is_manager": False,
            "can_switch_view": False,
            "employee": current_user,
        }

    # Manager:
    # Không chọn employee -> Manager View.
    # Có chọn employee -> Employee View.
    if not requested_mode:
        requested_mode = "employee" if employee else "manager"

    if requested_mode == "manager":
        return {
            "current_user": current_user,
            "view_mode": "manager",
            "is_manager": True,
            "can_switch_view": True,
            "employee": "",
        }

    if not employee:
        frappe.throw(
            _("Please select a Sales User."),
            exc=frappe.ValidationError,
        )

    _validate_employee(employee)

    return {
        "current_user": current_user,
        "view_mode": "employee",
        "is_manager": True,
        "can_switch_view": True,
        "employee": employee,
    }


def _validate_employee(employee: str) -> None:
    if employee == "Administrator":
        return

    user = frappe.db.get_value(
        "User",
        employee,
        ["name", "enabled", "user_type"],
        as_dict=True,
    )

    if not user:
        frappe.throw(
            _("Selected Sales User does not exist."),
            exc=frappe.ValidationError,
        )

    if not user.enabled:
        frappe.throw(
            _("Selected Sales User is disabled."),
            exc=frappe.ValidationError,
        )

    if user.user_type != "System User":
        frappe.throw(
            _("Selected user is not a System User."),
            exc=frappe.ValidationError,
        )

    employee_roles = set(frappe.get_roles(employee))

    if not employee_roles & SALES_ROLES:
        frappe.throw(
            _("Selected user does not have a CRM sales role."),
            exc=frappe.ValidationError,
        )


def _clean_value(value: str | None) -> str:
    if value is None:
        return ""

    cleaned = str(value).strip()

    if cleaned.lower() in {
        "null",
        "none",
        "undefined",
    }:
        return ""

    return cleaned
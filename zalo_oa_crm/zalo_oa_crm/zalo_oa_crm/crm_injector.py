from __future__ import annotations

from typing import Any

import frappe


MARKER = "<!-- zalo_oa_crm_assets -->"

CRM_SCRIPTS = (
    "/assets/zalo_oa_crm/js/zalo_oa_sidebar.js",
    "/assets/zalo_oa_crm/js/zalo_oa_tab.js",
    "/assets/zalo_oa_crm/js/crm_call_ai_summary.js",
)


def inject_crm_assets(
    request: Any = None,
    response: Any = None,
    **kwargs: Any,
) -> None:
    if response is None:
        return

    # Xác nhận hook thực sự được gọi.
    response.headers["X-Zalo-OA-CRM-Injector"] = "hook-called"

    if request is None:
        response.headers["X-Zalo-OA-CRM-Injector"] = "missing-request"
        return

    path = getattr(request, "path", "") or ""

    if path != "/crm" and not path.startswith("/crm/"):
        response.headers["X-Zalo-OA-CRM-Injector"] = "skipped-path"
        return

    if getattr(request, "method", "") != "GET":
        response.headers["X-Zalo-OA-CRM-Injector"] = "skipped-method"
        return

    if response.status_code != 200:
        response.headers["X-Zalo-OA-CRM-Injector"] = (
            f"skipped-status-{response.status_code}"
        )
        return

    try:
        html = response.get_data(as_text=True)

        if not html:
            response.headers["X-Zalo-OA-CRM-Injector"] = "empty-response"
            return

        if MARKER in html:
            response.headers["X-Zalo-OA-CRM-Injector"] = "already-injected"
            return

        scripts = "\n".join(
            f'<script defer src="{src}" '
            f'data-zalo-oa-crm="true"></script>'
            for src in CRM_SCRIPTS
        )

        injection = f"\n{MARKER}\n{scripts}\n"
        body_position = html.lower().rfind("</body>")

        if body_position >= 0:
            html = (
                html[:body_position]
                + injection
                + html[body_position:]
            )
        else:
            html += injection

        response.set_data(html)
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["X-Zalo-OA-CRM-Injector"] = "injected"

    except Exception:
        response.headers["X-Zalo-OA-CRM-Injector"] = "error"

        frappe.logger("zalo_oa_crm").exception(
            "Failed to inject Zalo OA CRM assets"
        )
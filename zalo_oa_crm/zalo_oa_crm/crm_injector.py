import traceback

import frappe


MARKER = "zalo_oa_crm_assets"

SCRIPTS = """
<!-- zalo_oa_crm_assets -->
<script src="/assets/zalo_oa_crm/js/zalo_oa_sidebar.js"></script>
<script src="/assets/zalo_oa_crm/js/zalo_oa_tab.js"></script>
<script src="/assets/zalo_oa_crm/js/crm_call_ai_summary.js"></script>
"""


def inject_crm_assets(response=None, request=None):
    """Inject Zalo OA assets into the CRM SPA HTML response."""

    req = request or getattr(frappe.local, "request", None)
    path = getattr(req, "path", "") if req else ""

    if response is None:
        return

    if path != "/crm" and not path.startswith("/crm/"):
        return

    # Chứng minh hook đã được gọi.
    response.headers["X-Zalo-OA-CRM-Hook"] = "fired"

    try:
        if getattr(response, "status_code", 0) != 200:
            response.headers["X-Zalo-OA-CRM-Hook"] = "non-200"
            return

        content_type = response.headers.get("Content-Type", "")
        mimetype = getattr(response, "mimetype", "") or ""

        is_html = (
            "html" in content_type.lower()
            or "html" in mimetype.lower()
        )

        if not is_html:
            response.headers["X-Zalo-OA-CRM-Hook"] = "not-html"
            return

        if getattr(response, "direct_passthrough", False):
            response.headers["X-Zalo-OA-CRM-Hook"] = "direct-passthrough"
            return

        html = response.get_data(as_text=True)

        if MARKER in html:
            response.headers["X-Zalo-OA-CRM-Hook"] = "already-injected"
            return

        body_position = html.lower().rfind("</body>")

        if body_position == -1:
            response.headers["X-Zalo-OA-CRM-Hook"] = "no-body"
            return

        patched_html = (
            html[:body_position]
            + SCRIPTS
            + "\n"
            + html[body_position:]
        )

        response.set_data(patched_html)
        response.headers["X-Zalo-OA-CRM-Hook"] = "injected"

    except Exception:
        response.headers["X-Zalo-OA-CRM-Hook"] = "error"

        frappe.logger(
            "zalo_oa_crm",
            allow_site=True,
        ).error(
            "CRM asset injection failed:\n%s",
            traceback.format_exc(),
        )

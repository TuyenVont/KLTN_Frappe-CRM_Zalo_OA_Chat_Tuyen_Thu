app_name = "crm_reports"
app_title = "CRM Reports"
app_publisher = "tuyen"
app_description = "Custom reports for Frappe CRM"
app_email = "23521756@gm.uit.edu.vn"
app_license = "mit"

required_apps = ["crm"]

override_whitelisted_methods = {
    "crm.api.dashboard.get_dashboard":
        "crm_reports.api.dashboard.get_dashboard",
}

website_route_rules = [
    {
        "from_route": "/crm/dashboard",
        "to_route": "crm_reports_shell",
    },
]
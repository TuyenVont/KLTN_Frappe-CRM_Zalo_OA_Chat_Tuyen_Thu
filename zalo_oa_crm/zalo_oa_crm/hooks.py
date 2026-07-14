app_name = "zalo_oa_crm"
app_title = "Zalo OA CRM"
app_publisher = "thu"
app_description = "Zalo OA CRM integration"
app_email = "23521538@gm.uit.edu.vn"
app_license = "mit"


# JavaScript chỉ dành cho Frappe Desk /app/*
app_include_js = [
    "/assets/zalo_oa_crm/js/desk_sidebar.js",
]


# Chèn JavaScript của custom app vào HTML của CRM SPA /crm/*
after_request = [
    "zalo_oa_crm.crm_injector.inject_crm_assets",
]


doc_events = {
    "CRM Lead": {
        "after_insert":
            "zalo_oa_crm.api.chat.sync_zalo_customer_on_lead"
    },
    "CRM Deal": {
        "after_insert":
            "zalo_oa_crm.api.chat.sync_zalo_customer_on_deal"
    },
}


override_whitelisted_methods = {
    "crm.integrations.api.get_recording_url":
        "zalo_oa_crm.api.recording_api.get_recording_url",
}
after_request = [
    "zalo_oa_crm.crm_injector.inject_crm_assets",
]

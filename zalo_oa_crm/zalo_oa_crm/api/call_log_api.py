from __future__ import annotations

from typing import Any, Optional
from urllib.parse import unquote, urlparse

import frappe
from frappe import _
from frappe.utils import cint, now_datetime
from frappe.utils.file_manager import save_file

from zalo_oa_crm.services.call_processor import enqueue_call_log


CRM_CALL_LOG_DOCTYPE = "CRM Call Log"
AI_CALL_LOG_DOCTYPE = "Zalo OA Call Log"


VALID_SOURCES = {
    "manual": "Manual",
    "zalo": "Zalo",
    "facebook": "Facebook",
    "tiktok": "TikTok",
    "phone system": "Phone System",
    "other": "Other",
}


CRM_TYPE_MAP = {
    "incoming": "Incoming",
    "inbound": "Incoming",
    "outgoing": "Outgoing",
    "outbound": "Outgoing",
}


AI_DIRECTION_MAP = {
    "incoming": "Inbound",
    "inbound": "Inbound",
    "outgoing": "Outbound",
    "outbound": "Outbound",
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _get_select_options(
    doc: Any,
    fieldname: str,
) -> list[str]:
    field = doc.meta.get_field(fieldname)

    if not field or field.fieldtype != "Select":
        return []

    return [
        option.strip()
        for option in (field.options or "").splitlines()
        if option.strip()
    ]


def _normalize_select(
    doc: Any,
    fieldname: str,
    value: Any,
    default: Optional[str] = None,
) -> Optional[str]:
    """Trả về giá trị Select hợp lệ theo metadata."""
    text = _clean_text(value)
    options = _get_select_options(
        doc,
        fieldname,
    )

    if not options:
        return text or default

    for option in options:
        if option.casefold() == text.casefold():
            return option

    if default:
        for option in options:
            if option.casefold() == default.casefold():
                return option

    return options[0] if options else None


def _resolve_user(value: Any) -> Optional[str]:
    """Nhận User.name hoặc full_name và trả về User.name."""
    text = _clean_text(value)

    if not text:
        return None

    if frappe.db.exists("User", text):
        return text

    matches = frappe.get_all(
        "User",
        filters={
            "full_name": text,
            "enabled": 1,
        },
        pluck="name",
        limit=2,
    )

    if len(matches) == 1:
        return matches[0]

    return None


def set_if_exists(
    doc: Any,
    fieldname: str,
    value: Any,
) -> None:
    """Chỉ gán field tồn tại và bỏ qua Link không hợp lệ."""
    if value in (None, ""):
        return

    field = doc.meta.get_field(fieldname)

    if not field:
        return

    resolved_value = value

    if field.fieldtype == "Link" and field.options:
        if field.options == "User":
            resolved_value = _resolve_user(value)

        elif frappe.db.exists(field.options, value):
            resolved_value = value

        else:
            resolved_value = None

        if not resolved_value:
            return

    if field.fieldtype == "Select":
        resolved_value = _normalize_select(
            doc,
            fieldname,
            value,
        )

        if not resolved_value:
            return

    doc.set(
        fieldname,
        resolved_value,
    )


def _normalize_source(value: Any) -> str:
    text = _clean_text(value) or "Manual"

    return VALID_SOURCES.get(
        text.casefold(),
        "Other",
    )


def _normalize_call_type(value: Any) -> str:
    text = _clean_text(value) or "Outgoing"

    return CRM_TYPE_MAP.get(
        text.casefold(),
        "Outgoing",
    )


def _normalize_direction(
    value: Any,
    call_type: str,
) -> str:
    text = _clean_text(value) or call_type

    return AI_DIRECTION_MAP.get(
        text.casefold(),
        "Outbound",
    )


def _get_max_file_bytes() -> int:
    max_mb = max(
        cint(
            frappe.get_conf().get(
                "call_log_max_audio_mb"
            )
            or 20
        ),
        1,
    )

    return max_mb * 1024 * 1024


def _resolve_reference(
    crm_lead: str,
    crm_deal: str,
) -> tuple[Optional[str], Optional[str]]:
    """Kiểm tra và trả về cặp reference_doctype/reference_docname."""
    if crm_lead and crm_deal:
        frappe.throw(
            _("Chỉ được liên kết một trong hai: CRM Lead hoặc CRM Deal.")
        )

    if crm_deal:
        if not frappe.db.exists("CRM Deal", crm_deal):
            frappe.throw(
                _("Không tìm thấy CRM Deal: {0}").format(crm_deal)
            )

        return "CRM Deal", crm_deal

    if crm_lead:
        if not frappe.db.exists("CRM Lead", crm_lead):
            frappe.throw(
                _("Không tìm thấy CRM Lead: {0}").format(crm_lead)
            )

        return "CRM Lead", crm_lead

    return None, None


@frappe.whitelist()
def ingest_call():
    """Nhận multipart/form-data từ Postman và chạy pipeline AI."""
    if frappe.request.method != "POST":
        frappe.throw(
            _("Chỉ hỗ trợ POST.")
        )

    args = frappe.form_dict
    uploaded_file = frappe.request.files.get("file")
    audio_url = _clean_text(args.get("audio_url"))
    crm_lead = _clean_text(args.get("crm_lead"))
    crm_deal = _clean_text(args.get("crm_deal"))

    reference_doctype, reference_docname = _resolve_reference(
        crm_lead=crm_lead,
        crm_deal=crm_deal,
    )

    # Chấp nhận một trong hai nguồn: file upload hoặc URL trực tiếp.
    if not uploaded_file and not audio_url:
        frappe.throw(
            _(
                "Phải cung cấp file trong field 'file' "
                "hoặc URL trong field 'audio_url'."
            )
        )

    if audio_url:
        parsed_url = urlparse(audio_url)

        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
        ):
            frappe.throw(
                _("Audio URL không hợp lệ.")
            )

    call_type = _normalize_call_type(
        args.get("type")
    )

    direction = _normalize_direction(
        args.get("direction"),
        call_type,
    )

    source = _normalize_source(
        args.get("source")
    )

    # caller và receiver là Link tới User.
    # Nếu Postman gửi tên hiển thị hoặc giá trị sai,
    # dùng User đang gọi API.
    default_user = (
        frappe.session.user
        if frappe.session.user != "Guest"
        else "Administrator"
    )

    caller_input = _clean_text(
        args.get("caller")
    )

    receiver_input = _clean_text(
        args.get("receiver")
    )

    caller = _resolve_user(caller_input)
    receiver = _resolve_user(receiver_input)

    if caller_input and not caller:
        frappe.throw(
            _("Không tìm thấy User caller: {0}").format(
                caller_input
            )
        )

    if receiver_input and not receiver:
        frappe.throw(
            _("Không tìm thấy User receiver: {0}").format(
                receiver_input
            )
        )

    caller = caller or default_user
    receiver = receiver or default_user

    # 1. Tạo CRM Call Log
    crm_call = frappe.new_doc(
        CRM_CALL_LOG_DOCTYPE
    )

    set_if_exists(
        crm_call,
        "type",
        call_type,
    )

    set_if_exists(
        crm_call,
        "status",
        args.get("status") or "Completed",
    )

    set_if_exists(
        crm_call,
        "from",
        args.get("from_number"),
    )

    set_if_exists(
        crm_call,
        "to",
        args.get("to_number"),
    )

    set_if_exists(
        crm_call,
        "caller",
        caller,
    )

    set_if_exists(
        crm_call,
        "receiver",
        receiver,
    )

    set_if_exists(
        crm_call,
        "start_time",
        args.get("start_time")
        or now_datetime(),
    )

    set_if_exists(
        crm_call,
        "end_time",
        args.get("end_time"),
    )

    set_if_exists(
        crm_call,
        "duration",
        cint(
            args.get("duration_seconds")
            or 0
        ),
    )

    set_if_exists(
        crm_call,
        "telephony_medium",
        args.get("telephony_medium")
        or "Manual",
    )

    if (
        reference_doctype
        and reference_docname
        and crm_call.meta.has_field("reference_doctype")
        and crm_call.meta.has_field("reference_docname")
    ):
        crm_call.set(
            "reference_doctype",
            reference_doctype,
        )

        crm_call.set(
            "reference_docname",
            reference_docname,
        )

    crm_call.insert()

    # 2. Nếu có file upload thì lưu file private vào Frappe.
    # Nếu chỉ có audio_url thì worker sẽ tải URL ở bước xử lý AI.
    file_doc = None
    recording_url = None

    if uploaded_file:
        uploaded_file.stream.seek(0)
        content = uploaded_file.stream.read()

        if not content:
            frappe.throw(
                _("File audio/video bị rỗng.")
            )

        if len(content) > _get_max_file_bytes():
            max_mb = cint(
                frappe.get_conf().get(
                    "call_log_max_audio_mb"
                )
                or 20
            )

            frappe.throw(
                _(
                    "File vượt quá giới hạn {0} MB."
                ).format(max_mb)
            )

        filename = (
            uploaded_file.filename
            or "call-recording.wav"
        )

        file_doc = save_file(
            filename,
            content,
            CRM_CALL_LOG_DOCTYPE,
            crm_call.name,
            is_private=1,
        )
        recording_url = file_doc.file_url

        if crm_call.meta.has_field(
            "recording_url"
        ):
            crm_call.db_set(
                "recording_url",
                recording_url,
                update_modified=False,
            )

    # 3. Tạo Zalo OA Call Log
    ai_call = frappe.new_doc(
        AI_CALL_LOG_DOCTYPE
    )

    if crm_lead:
        set_if_exists(
            ai_call,
            "crm_lead",
            crm_lead,
        )

    if crm_deal:
        set_if_exists(
            ai_call,
            "crm_deal",
            crm_deal,
        )

    set_if_exists(
        ai_call,
        "external_call_id",
        args.get("external_call_id")
        or crm_call.name,
    )

    set_if_exists(
        ai_call,
        "source",
        source,
    )

    set_if_exists(
        ai_call,
        "direction",
        direction,
    )

    set_if_exists(
        ai_call,
        "started_at",
        args.get("start_time")
        or now_datetime(),
    )

    set_if_exists(
        ai_call,
        "duration_seconds",
        cint(
            args.get("duration_seconds")
            or 0
        ),
    )

    agent = (
        caller
        if direction == "Outbound"
        else receiver
    )

    set_if_exists(
        ai_call,
        "agent",
        agent,
    )

    if file_doc:
        set_if_exists(
            ai_call,
            "audio_file",
            file_doc.file_url,
        )
    else:
        set_if_exists(
            ai_call,
            "audio_url",
            audio_url,
        )

    set_if_exists(
        ai_call,
        "processing_status",
        "Pending",
    )

    if ai_call.meta.has_field(
        "crm_call_log"
    ):
        ai_call.set(
            "crm_call_log",
            crm_call.name,
        )

    elif ai_call.meta.has_field(
        "custom_crm_call_log"
    ):
        ai_call.set(
            "custom_crm_call_log",
            crm_call.name,
        )

    ai_call.insert()

    # 4. Liên kết ngược sang CRM Call Log
    if crm_call.meta.has_field(
        "custom_ai_call_log"
    ):
        crm_call.db_set(
            "custom_ai_call_log",
            ai_call.name,
            update_modified=False,
        )

    if crm_call.meta.has_field(
        "custom_ai_status"
    ):
        crm_call.db_set(
            "custom_ai_status",
            "Queued",
            update_modified=False,
        )

    # 5. Đưa vào background worker
    result = enqueue_call_log(
        ai_call.name
    )

    return {
        "ok": True,
        "crm_call_log": crm_call.name,
        "ai_call_log": ai_call.name,
        "reference_doctype": reference_doctype,
        "reference_docname": reference_docname,
        "recording_url": recording_url,
        "audio_url": audio_url or None,
        "source": source,
        "type": call_type,
        "direction": direction,
        "caller": caller,
        "receiver": receiver,
        "processing_status": result.get(
            "status",
            "Queued",
        ),
        "message": result.get(
            "message",
            "Đã đưa cuộc gọi vào hàng đợi AI.",
        ),
    }


@frappe.whitelist()
def get_call_ai_details(
    call_log_name: Optional[str] = None,
    recording_url: Optional[str] = None,
):
    """Lấy transcript và kết quả AI của CRM Call Log."""
    call_log_name = _clean_text(call_log_name)
    recording_url = _clean_text(recording_url)

    if not call_log_name and recording_url:
        parsed_path = unquote(
            urlparse(recording_url).path
        )

        call_log_name = (
            frappe.db.get_value(
                CRM_CALL_LOG_DOCTYPE,
                {"recording_url": parsed_path},
                "name",
            )
            or ""
        )

    if not call_log_name:
        frappe.throw(
            _("Không xác định được CRM Call Log.")
        )

    if not frappe.db.exists(
        CRM_CALL_LOG_DOCTYPE,
        call_log_name,
    ):
        frappe.throw(
            _("Không tìm thấy CRM Call Log.")
        )

    doc = frappe.get_doc(
        CRM_CALL_LOG_DOCTYPE,
        call_log_name,
    )

    doc.check_permission("read")

    def get_value(fieldname: str):
        if not doc.meta.has_field(fieldname):
            return None

        return doc.get(fieldname)

    return {
        "name": doc.name,
        "status": get_value("custom_ai_status"),
        "summary": get_value("custom_ai_summary"),
        "transcript": get_value("custom_transcript"),
        "customer_need": get_value(
            "custom_customer_need"
        ),
        "sentiment": get_value(
            "custom_sentiment"
        ),
        "call_outcome": get_value(
            "custom_call_outcome"
        ),
        "action_items": get_value(
            "custom_action_items"
        ),
        "important_points": get_value(
            "custom_important_points"
        ),
        "quality_notes": get_value(
            "custom_quality_notes"
        ),
        "next_follow_up": get_value(
            "custom_next_follow_up"
        ),
        "processed_at": get_value(
            "custom_processed_at"
        ),
        "error_message": get_value(
            "custom_error_message"
        ),
    }

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import unquote, urlparse

import frappe
from frappe import _
from frappe.utils import cint, now_datetime
from frappe.utils.file_manager import save_file

from zalo_oa_crm.services.call_processor import enqueue_call_log


CRM_CALL_LOG_DOCTYPE = "CRM Call Log"


VALID_SOURCES = {
    "manual": "Manual",
    "zalo": "Zalo",
    "zalo oa": "Zalo",
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
    """Trả về giá trị Select hợp lệ theo metadata của DocType."""
    text = _clean_text(value)
    options = _get_select_options(
        doc,
        fieldname,
    )

    if not options:
        return text or default

    if text:
        for option in options:
            if option.casefold() == text.casefold():
                return option

    if default:
        for option in options:
            if option.casefold() == default.casefold():
                return option

    return None


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
    default: Optional[str] = None,
) -> None:
    """Chỉ gán khi field tồn tại và giá trị hợp lệ."""
    if value in (None, "") and default in (None, ""):
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
            default=default,
        )

        if not resolved_value:
            return

    doc.set(
        fieldname,
        resolved_value,
    )


def _db_set_if_exists(
    doc: Any,
    fieldname: str,
    value: Any,
    *,
    update_modified: bool = False,
) -> None:
    """Cập nhật trực tiếp một field nếu field đó tồn tại."""
    if not doc.meta.has_field(fieldname):
        return

    doc.db_set(
        fieldname,
        value,
        update_modified=update_modified,
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


def _validate_audio_url(audio_url: str) -> None:
    if not audio_url:
        return

    parsed_url = urlparse(audio_url)

    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname
    ):
        frappe.throw(
            _("Audio URL không hợp lệ.")
        )


def _resolve_reference(
    crm_lead: str,
    crm_deal: str,
    reference_doctype: str = "",
    reference_docname: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """Trả về reference_doctype/reference_docname hợp lệ."""
    if crm_lead and crm_deal:
        frappe.throw(
            _("Chỉ được liên kết một trong hai: CRM Lead hoặc CRM Deal.")
        )

    if (
        (reference_doctype and not reference_docname)
        or (reference_docname and not reference_doctype)
    ):
        frappe.throw(
            _(
                "Phải cung cấp đồng thời reference_doctype "
                "và reference_docname."
            )
        )

    if reference_doctype and reference_docname:
        if crm_lead or crm_deal:
            frappe.throw(
                _(
                    "Không gửi đồng thời crm_lead/crm_deal "
                    "với reference_doctype/reference_docname."
                )
            )

        if not frappe.db.exists(
            "DocType",
            reference_doctype,
        ):
            frappe.throw(
                _("Không tìm thấy DocType: {0}").format(
                    reference_doctype
                )
            )

        if not frappe.db.exists(
            reference_doctype,
            reference_docname,
        ):
            frappe.throw(
                _(
                    "Không tìm thấy {0}: {1}"
                ).format(
                    reference_doctype,
                    reference_docname,
                )
            )

        return (
            reference_doctype,
            reference_docname,
        )

    if crm_deal:
        if not frappe.db.exists(
            "CRM Deal",
            crm_deal,
        ):
            frappe.throw(
                _("Không tìm thấy CRM Deal: {0}").format(
                    crm_deal
                )
            )

        return "CRM Deal", crm_deal

    if crm_lead:
        if not frappe.db.exists(
            "CRM Lead",
            crm_lead,
        ):
            frappe.throw(
                _("Không tìm thấy CRM Lead: {0}").format(
                    crm_lead
                )
            )

        return "CRM Lead", crm_lead

    return None, None


def _get_existing_call_log(
    external_call_id: str,
) -> Optional[str]:
    """Tìm CRM Call Log theo field id hoặc theo document name."""
    name = frappe.db.get_value(
        CRM_CALL_LOG_DOCTYPE,
        {"id": external_call_id},
        "name",
    )

    if name:
        return name

    if frappe.db.exists(
        CRM_CALL_LOG_DOCTYPE,
        external_call_id,
    ):
        return external_call_id

    return None


@frappe.whitelist()
def ingest_call():
    """
    Nhận multipart/form-data và tạo/cập nhật duy nhất CRM Call Log.

    Field file:
        file

    Các field form-data chính:
        external_call_id
        source
        type
        status
        from_number
        to_number
        caller
        receiver
        start_time
        end_time
        duration_seconds
        audio_url
        crm_lead
        crm_deal
        reference_doctype
        reference_docname
        zalo_customer
    """
    if frappe.request.method != "POST":
        frappe.throw(
            _("Chỉ hỗ trợ POST.")
        )

    args = frappe.form_dict
    uploaded_file = frappe.request.files.get("file")

    external_call_id = _clean_text(
        args.get("external_call_id")
    )
    audio_url = _clean_text(
        args.get("audio_url")
    )
    from_number = _clean_text(
        args.get("from_number")
    )
    to_number = _clean_text(
        args.get("to_number")
    )

    if not external_call_id:
        frappe.throw(
            _("Thiếu external_call_id.")
        )

    if not from_number:
        frappe.throw(
            _("Thiếu from_number.")
        )

    if not to_number:
        frappe.throw(
            _("Thiếu to_number.")
        )

    if not uploaded_file and not audio_url:
        frappe.throw(
            _(
                "Phải cung cấp file trong field 'file' "
                "hoặc URL trong field 'audio_url'."
            )
        )

    _validate_audio_url(audio_url)

    crm_lead = _clean_text(
        args.get("crm_lead")
    )
    crm_deal = _clean_text(
        args.get("crm_deal")
    )
    reference_doctype_input = _clean_text(
        args.get("reference_doctype")
    )
    reference_docname_input = _clean_text(
        args.get("reference_docname")
    )

    reference_doctype, reference_docname = _resolve_reference(
        crm_lead=crm_lead,
        crm_deal=crm_deal,
        reference_doctype=reference_doctype_input,
        reference_docname=reference_docname_input,
    )

    call_type = _normalize_call_type(
        args.get("type")
    )
    source = _normalize_source(
        args.get("source")
    )

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

    if call_type == "Incoming":
        receiver = receiver or default_user
    else:
        caller = caller or default_user

    existing_name = _get_existing_call_log(
        external_call_id
    )

    if existing_name:
        crm_call = frappe.get_doc(
            CRM_CALL_LOG_DOCTYPE,
            existing_name,
        )
        is_new = False
    else:
        crm_call = frappe.new_doc(
            CRM_CALL_LOG_DOCTYPE
        )
        is_new = True

        set_if_exists(
            crm_call,
            "id",
            external_call_id,
        )

    set_if_exists(
        crm_call,
        "type",
        call_type,
        default="Outgoing",
    )
    set_if_exists(
        crm_call,
        "status",
        args.get("status") or "Completed",
        default="Completed",
    )
    set_if_exists(
        crm_call,
        "from",
        from_number,
    )
    set_if_exists(
        crm_call,
        "to",
        to_number,
    )
    set_if_exists(
        crm_call,
        "start_time",
        args.get("start_time") or now_datetime(),
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

    # Field medium của CRM Call Log lưu nguồn nghiệp vụ.
    set_if_exists(
        crm_call,
        "medium",
        source,
    )

    # telephony_medium là Select chuẩn của CRM.
    # Dùng Manual để tránh lỗi nếu options chưa có Zalo.
    set_if_exists(
        crm_call,
        "telephony_medium",
        args.get("telephony_medium") or "Manual",
        default="Manual",
    )

    # Nếu bạn đã tạo custom_source thì hệ thống sẽ tự gán.
    set_if_exists(
        crm_call,
        "custom_source",
        source,
    )

    if call_type == "Incoming":
        set_if_exists(
            crm_call,
            "receiver",
            receiver,
        )
    else:
        set_if_exists(
            crm_call,
            "caller",
            caller,
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

    zalo_customer = _clean_text(
        args.get("zalo_customer")
        or args.get("customer")
    )

    set_if_exists(
        crm_call,
        "custom_zalo_customer",
        zalo_customer,
    )

    if is_new:
        set_if_exists(
            crm_call,
            "custom_ai_status",
            "Pending",
            default="Pending",
        )
        set_if_exists(
            crm_call,
            "custom_retry_count",
            0,
        )
        crm_call.insert()
    else:
        crm_call.save()

    file_doc = None
    recording_url = _clean_text(
        crm_call.get("recording_url")
        if crm_call.meta.has_field("recording_url")
        else ""
    )

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

    elif audio_url:
        recording_url = audio_url

    if recording_url:
        _db_set_if_exists(
            crm_call,
            "recording_url",
            recording_url,
            update_modified=False,
        )

    _db_set_if_exists(
        crm_call,
        "custom_error_message",
        None,
        update_modified=False,
    )

    result = enqueue_call_log(
        crm_call.name
    )

    return {
        "ok": True,
        "created": is_new,
        "crm_call_log": crm_call.name,
        "external_call_id": external_call_id,
        "reference_doctype": reference_doctype,
        "reference_docname": reference_docname,
        "recording_url": recording_url or None,
        "source": source,
        "type": call_type,
        "caller": caller,
        "receiver": receiver,
        "processing_status": result.get(
            "status",
            "Queued",
        ),
        "message": result.get(
            "message",
            "Đã đưa CRM Call Log vào hàng đợi AI.",
        ),
    }


@frappe.whitelist()
def get_call_ai_details(
    call_log_name: Optional[str] = None,
    recording_url: Optional[str] = None,
):
    """Lấy transcript và kết quả AI trực tiếp từ CRM Call Log."""
    call_log_name = _clean_text(
        call_log_name
    )
    recording_url = _clean_text(
        recording_url
    )

    if not call_log_name and recording_url:
        call_log_name = (
            frappe.db.get_value(
                CRM_CALL_LOG_DOCTYPE,
                {"recording_url": recording_url},
                "name",
            )
            or ""
        )

        if not call_log_name:
            parsed_path = unquote(
                urlparse(recording_url).path
            )

            if parsed_path:
                call_log_name = (
                    frappe.db.get_value(
                        CRM_CALL_LOG_DOCTYPE,
                        {"recording_url": parsed_path},
                        "name",
                    )
                    or ""
                )

    if call_log_name and not frappe.db.exists(
        CRM_CALL_LOG_DOCTYPE,
        call_log_name,
    ):
        call_log_name = (
            frappe.db.get_value(
                CRM_CALL_LOG_DOCTYPE,
                {"id": call_log_name},
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
        "external_call_id": get_value("id"),
        "recording_url": get_value("recording_url"),
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
        "retry_count": get_value(
            "custom_retry_count"
        ),
        "raw_ai_result": get_value(
            "custom_raw_ai_result"
        ),
    }

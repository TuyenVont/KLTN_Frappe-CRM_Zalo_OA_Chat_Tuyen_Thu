from __future__ import annotations

from frappe.utils.file_manager import save_file
import ipaddress
import json
import mimetypes
import os
import socket
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse


import frappe
import requests
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime


from zalo_oa_crm.services.ai_call_service import summarize_call, transcribe_audio




DOCTYPE = "Zalo OA Call Log"
CRM_CALL_LOG_DOCTYPE = "CRM Call Log"
REALTIME_EVENT = "zalo_oa_call_log_ai_update"


# Hỗ trợ cả field được tạo trong app và Custom Field tạo qua Customize Form.
CRM_LINK_FIELDS = ("crm_call_log", "custom_crm_call_log")


ACTIVE_STATUSES = {"Queued", "Transcribing", "Summarizing"}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


ALLOWED_GENERIC_CONTENT_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
    "application/ogg",
    "application/x-ogg",
}




@frappe.whitelist()
def enqueue_call_log(
    call_log_name: str,
    force: int = 0,
    retranscribe: int = 0,
) -> Dict[str, Any]:
    """Đưa một Zalo OA Call Log vào background queue để xử lý AI.


    Args:
        call_log_name: Tên bản ghi Zalo OA Call Log.
        force: Cho phép chạy lại bản ghi đã Completed.
        retranscribe: Xóa transcript cũ và chạy Whisper lại.


    Returns:
        Dictionary chứa trạng thái đưa vào queue.
    """
    force = bool(cint(force))
    retranscribe = bool(cint(retranscribe))


    doc = frappe.get_doc(DOCTYPE, call_log_name)
    doc.check_permission("write")


    status = (doc.processing_status or "Pending").strip()


    if status in ACTIVE_STATUSES:
        return {
            "queued": False,
            "status": status,
            "message": _("Cuộc gọi đang được AI xử lý."),
        }


    if status == "Completed" and not force:
        return {
            "queued": False,
            "status": status,
            "message": _("Cuộc gọi đã được xử lý. Dùng force=1 để chạy lại."),
        }


    if not doc.transcript and not doc.audio_file and not doc.audio_url:
        frappe.throw(
            _("Cần có Transcript, Audio File hoặc Audio URL trước khi chạy AI.")
        )


    updates: Dict[str, Any] = {
        "processing_status": "Queued",
        "error_message": None,
    }


    if retranscribe:
        updates["transcript"] = None


    _set_fields(doc.name, updates, commit=True)


    _sync_crm_call_log(
        call_log_name=doc.name,
        status="Queued",
        transcript=None if retranscribe else (doc.transcript or None),
        error_message=None,
        commit=True,
    )


    _publish_status(doc.name, "Queued")


    timeout = cint(frappe.get_conf().get("call_log_job_timeout") or 1800)


    frappe.enqueue(
        "zalo_oa_crm.services.call_processor.process_call_log",
        queue="long",
        timeout=timeout,
        job_name="AI Call Log {0}".format(doc.name),
        enqueue_after_commit=True,
        call_log_name=doc.name,
        retranscribe=retranscribe,
    )


    return {
        "queued": True,
        "status": "Queued",
        "message": _("Đã đưa cuộc gọi vào hàng đợi AI."),
    }




def process_call_log(
    call_log_name: str,
    retranscribe: int = 0,
) -> Dict[str, Any]:
    """Chạy Whisper và Gemma trong background worker."""
    retranscribe = bool(cint(retranscribe))
    temporary_path: Optional[str] = None
    transcript = ""


    try:
        doc = frappe.get_doc(DOCTYPE, call_log_name)
        transcript = (doc.transcript or "").strip()


        if retranscribe or not transcript:
            _set_status(
                call_log_name=call_log_name,
                status="Transcribing",
                transcript=None,
            )

            audio_path, is_temporary = _resolve_audio_source(doc)

            if is_temporary:
                temporary_path = audio_path

                # Lưu file tải từ URL thành File private trong Frappe.
                file_url = _save_remote_audio(
                    call_log_name=doc.name,
                    local_path=audio_path,
                    original_url=doc.audio_url,
                )

                _set_fields(
                    doc.name,
                    {
                        "audio_file": file_url,
                    },
                    commit=True,
                )

                _set_crm_recording_url(
                    call_log_name=doc.name,
                    file_url=file_url,
                    commit=True,
                )

            transcript_result = transcribe_audio(audio_path)
            transcript = _extract_transcript(transcript_result)


            if not transcript:
                frappe.throw(_("Whisper không trả về transcript."))


            _set_fields(
                call_log_name,
                {
                    "transcript": transcript,
                    "processing_status": "Summarizing",
                    "error_message": None,
                },
                commit=True,
            )


            _sync_crm_call_log(
                call_log_name=call_log_name,
                status="Summarizing",
                transcript=transcript,
                error_message=None,
                commit=True,
            )


            _publish_status(call_log_name, "Summarizing")


        else:
            _set_status(
                call_log_name=call_log_name,
                status="Summarizing",
                transcript=transcript,
            )


        ai_result = summarize_call(transcript)


        if not isinstance(ai_result, dict):
            frappe.throw(
                _("summarize_call() phải trả về dictionary, nhận được {0}.").format(
                    type(ai_result).__name__
                )
            )


        processed_at = now_datetime()


        updates = _map_ai_result(ai_result)
        updates.update(
            {
                "processing_status": "Completed",
                "processed_at": processed_at,
                "error_message": None,
                "retry_count": 0,
                "raw_ai_result": _json_dump(ai_result),
            }
        )


        _set_fields(call_log_name, updates, commit=True)


        _sync_crm_call_log(
            call_log_name=call_log_name,
            status="Completed",
            transcript=transcript,
            ai_result=ai_result,
            processed_at=processed_at,
            error_message=None,
            commit=True,
        )


        _publish_status(call_log_name, "Completed")


        return {
            "name": call_log_name,
            "status": "Completed",
            "transcript": transcript,
            "ai_result": ai_result,
        }


    except Exception as exc:
        trace = frappe.get_traceback()


        frappe.log_error(
            message=trace,
            title="AI Call Log failed: {0}".format(call_log_name),
        )


        error_message = _clean_error(exc)


        try:
            current_retry = cint(
                frappe.db.get_value(DOCTYPE, call_log_name, "retry_count") or 0
            )


            _set_fields(
                call_log_name,
                {
                    "processing_status": "Failed",
                    "error_message": error_message,
                    "retry_count": current_retry + 1,
                },
                commit=True,
            )


            _sync_crm_call_log(
                call_log_name=call_log_name,
                status="Failed",
                transcript=transcript or None,
                error_message=error_message,
                commit=True,
            )


            _publish_status(
                call_log_name,
                "Failed",
                error_message=error_message,
            )


        except Exception:
            frappe.log_error(
                message=frappe.get_traceback(),
                title="Cannot update failed Call Log: {0}".format(call_log_name),
            )


        raise


    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            except OSError:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title="Cannot remove temporary Call Log media",
                )




def _resolve_audio_source(doc: Any) -> Tuple[str, bool]:
    """Trả về (đường_dẫn_local, có_phải_file_tạm).


    Audio File được ưu tiên trước Audio URL.
    """
    if doc.audio_file:
        return _resolve_frappe_file(doc.audio_file), False


    if doc.audio_url:
        return _download_remote_media(doc.audio_url), True


    frappe.throw(_("Không tìm thấy Audio File hoặc Audio URL."))
    raise AssertionError("unreachable")


def _save_remote_audio(
    call_log_name: str,
    local_path: str,
    original_url: Optional[str] = None,
) -> str:
    """Lưu file tải từ URL thành File private trong Frappe."""
    path = Path(local_path)

    filename = Path(
        urlparse(original_url or "").path
    ).name

    if not filename:
        filename = "call-recording{0}".format(
            path.suffix or ".media"
        )

    with path.open("rb") as file_handle:
        content = file_handle.read()

    file_doc = save_file(
        fname=filename,
        content=content,
        dt=DOCTYPE,
        dn=call_log_name,
        is_private=1,
    )

    return file_doc.file_url


def _set_crm_recording_url(
    call_log_name: str,
    file_url: str,
    commit: bool = False,
) -> None:
    """Đưa file ghi âm private sang CRM Call Log."""
    crm_call_log_name = _get_linked_crm_call_log(
        call_log_name
    )

    if not crm_call_log_name:
        return

    meta = frappe.get_meta(
        CRM_CALL_LOG_DOCTYPE
    )

    if not meta.has_field("recording_url"):
        return

    frappe.db.set_value(
        CRM_CALL_LOG_DOCTYPE,
        crm_call_log_name,
        "recording_url",
        file_url,
        update_modified=True,
    )

    if commit:
        frappe.db.commit()

def _resolve_frappe_file(file_url: str) -> str:
    """Tìm đường dẫn vật lý của File document trong Frappe."""
    file_name = frappe.db.get_value(
        "File",
        {"file_url": file_url},
        "name",
    )


    if not file_name:
        frappe.throw(
            _("Không tìm thấy File document tương ứng với {0}.").format(file_url)
        )


    file_doc = frappe.get_doc("File", file_name)
    file_path = file_doc.get_full_path()


    if not file_path or not os.path.isfile(file_path):
        frappe.throw(_("File audio không tồn tại trên máy chủ."))


    _validate_file_size(file_path)
    return file_path




def _download_remote_media(url: str) -> str:
    """Tải URL media trực tiếp với giới hạn dung lượng và kiểm tra SSRF."""
    current_url = url.strip()
    max_bytes = _max_audio_bytes()


    for _redirect_index in range(4):
        _assert_public_http_url(current_url)


        with requests.get(
            current_url,
            stream=True,
            allow_redirects=False,
            timeout=(10, 120),
            headers={
                "User-Agent": "Zalo-OA-CRM-Call-Processor/1.0",
            },
        ) as response:
            if response.status_code in REDIRECT_STATUSES:
                location = response.headers.get("Location")


                if not location:
                    frappe.throw(
                        _("Media URL redirect nhưng thiếu Location header.")
                    )


                current_url = urljoin(current_url, location)
                continue


            response.raise_for_status()


            content_type = (
                response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )


            if content_type.startswith("text/") or content_type in {
                "application/json",
                "application/xml",
                "text/html",
            }:
                frappe.throw(
                    _(
                        "Audio URL đang trỏ tới trang HTML/API, "
                        "không phải file media trực tiếp."
                    )
                )


            if (
                content_type
                and not content_type.startswith("audio/")
                and not content_type.startswith("video/")
                and content_type not in ALLOWED_GENERIC_CONTENT_TYPES
            ):
                frappe.throw(
                    _("Content-Type không được hỗ trợ: {0}").format(content_type)
                )


            content_length = cint(
                response.headers.get("Content-Length") or 0
            )


            if content_length and content_length > max_bytes:
                frappe.throw(
                    _("File vượt quá giới hạn {0} MB.").format(
                        _max_audio_mb()
                    )
                )


            suffix = _guess_suffix(current_url, content_type)


            temp_file = tempfile.NamedTemporaryFile(
                prefix="zalo-call-",
                suffix=suffix,
                delete=False,
            )


            temp_path = temp_file.name
            total = 0


            try:
                with temp_file:
                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if not chunk:
                            continue


                        total += len(chunk)


                        if total > max_bytes:
                            frappe.throw(
                                _("File vượt quá giới hạn {0} MB.").format(
                                    _max_audio_mb()
                                )
                            )


                        temp_file.write(chunk)


                if total == 0:
                    frappe.throw(_("File media tải về bị rỗng."))


                return temp_path


            except Exception:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


                raise


    frappe.throw(_("Media URL redirect quá nhiều lần."))
    raise AssertionError("unreachable")




def _assert_public_http_url(url: str) -> None:
    """Chỉ cho phép URL HTTP/HTTPS trỏ tới địa chỉ mạng công khai."""
    parsed = urlparse(url)


    if parsed.scheme not in {"http", "https"}:
        frappe.throw(_("Audio URL chỉ hỗ trợ http hoặc https."))


    if not parsed.hostname:
        frappe.throw(_("Audio URL không hợp lệ."))


    if parsed.username or parsed.password:
        frappe.throw(
            _("Audio URL không được chứa username/password.")
        )


    try:
        port = parsed.port or (
            443 if parsed.scheme == "https" else 80
        )


        addresses = socket.getaddrinfo(
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )


    except (OSError, ValueError) as exc:
        frappe.throw(
            _("Không phân giải được hostname của Audio URL: {0}").format(exc)
        )
        return


    if not addresses:
        frappe.throw(
            _("Hostname của Audio URL không có địa chỉ IP.")
        )


    for address in addresses:
        ip_text = address[4][0]
        ip_value = ipaddress.ip_address(
            ip_text.split("%", 1)[0]
        )


        if (
            ip_value.is_private
            or ip_value.is_loopback
            or ip_value.is_link_local
            or ip_value.is_multicast
            or ip_value.is_reserved
            or ip_value.is_unspecified
        ):
            frappe.throw(
                _(
                    "Audio URL trỏ tới địa chỉ mạng nội bộ "
                    "hoặc không an toàn."
                )
            )




def _validate_file_size(file_path: str) -> None:
    size = os.path.getsize(file_path)


    if size <= 0:
        frappe.throw(_("File audio bị rỗng."))


    if size > _max_audio_bytes():
        frappe.throw(
            _("File vượt quá giới hạn {0} MB.").format(
                _max_audio_mb()
            )
        )




def _max_audio_mb() -> int:
    return max(
        cint(
            frappe.get_conf().get("call_log_max_audio_mb")
            or 20
        ),
        1,
    )




def _max_audio_bytes() -> int:
    return _max_audio_mb() * 1024 * 1024




def _guess_suffix(url: str, content_type: str) -> str:
    url_suffix = Path(urlparse(url).path).suffix


    if url_suffix and len(url_suffix) <= 10:
        return url_suffix


    guessed = mimetypes.guess_extension(
        content_type or ""
    )


    return guessed or ".media"




def _extract_transcript(value: Any) -> str:
    """Chuẩn hóa kết quả transcribe_audio về string."""
    if isinstance(value, str):
        return value.strip()


    if isinstance(value, dict):
        for key in ("text", "transcript"):
            candidate = value.get(key)


            if isinstance(candidate, str):
                return candidate.strip()


    frappe.throw(
        _(
            "transcribe_audio() phải trả về string "
            "hoặc dict chứa text/transcript."
        )
    )


    raise AssertionError("unreachable")




def _map_ai_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Map kết quả AI vào field của Zalo OA Call Log."""
    return {
        "ai_summary": _as_text(result.get("summary")),
        "customer_need": _as_text(result.get("customer_need")),
        "sentiment": _as_text(result.get("sentiment")),
        "call_outcome": _as_text(result.get("call_outcome")),
        "action_items": _as_multiline_text(
            result.get("action_items")
        ),
        "next_follow_up": _as_datetime(
            result.get("next_follow_up")
        ),
    }




def _sync_crm_call_log(
    call_log_name: str,
    status: Optional[str] = None,
    transcript: Optional[str] = None,
    ai_result: Optional[Dict[str, Any]] = None,
    processed_at: Any = None,
    error_message: Optional[str] = None,
    commit: bool = False,
) -> None:
    """Đồng bộ trạng thái và kết quả AI về CRM Call Log.


    Các field không tồn tại sẽ tự động được bỏ qua. Những field được hỗ trợ:


        custom_ai_status
        custom_transcript
        custom_ai_summary
        custom_customer_need
        custom_sentiment
        custom_call_outcome
        custom_action_items
        custom_important_points
        custom_next_follow_up
        custom_quality_notes
        custom_processed_at
        custom_raw_ai_result
        custom_error_message
    """
    crm_call_log_name = _get_linked_crm_call_log(
        call_log_name
    )


    if not crm_call_log_name:
        return


    if not frappe.db.exists(
        CRM_CALL_LOG_DOCTYPE,
        crm_call_log_name,
    ):
        return


    values: Dict[str, Any] = {}


    if status is not None:
        values["custom_ai_status"] = status


    if transcript is not None:
        values["custom_transcript"] = transcript


    if error_message is not None:
        values["custom_error_message"] = error_message
    elif status in {
        "Queued",
        "Transcribing",
        "Summarizing",
        "Completed",
    }:
        values["custom_error_message"] = None


    if processed_at is not None:
        values["custom_processed_at"] = processed_at


    if ai_result is not None:
        values.update(
            {
                "custom_ai_summary": _as_text(
                    ai_result.get("summary")
                ),
                "custom_customer_need": _as_text(
                    ai_result.get("customer_need")
                ),
                "custom_sentiment": _as_text(
                    ai_result.get("sentiment")
                ),
                "custom_call_outcome": _as_text(
                    ai_result.get("call_outcome")
                ),
                "custom_action_items": _as_multiline_text(
                    ai_result.get("action_items")
                ),
                "custom_important_points": _as_multiline_text(
                    ai_result.get("important_points")
                ),
                "custom_next_follow_up": _as_datetime(
                    ai_result.get("next_follow_up")
                ),
                "custom_quality_notes": _as_text(
                    ai_result.get("quality_notes")
                ),
                "custom_raw_ai_result": _json_dump(ai_result),
            }
        )


    existing_values = _filter_existing_fields(
        CRM_CALL_LOG_DOCTYPE,
        values,
    )


    if not existing_values:
        return


    frappe.db.set_value(
        CRM_CALL_LOG_DOCTYPE,
        crm_call_log_name,
        existing_values,
        update_modified=True,
    )


    if commit:
        frappe.db.commit()




def _get_linked_crm_call_log(
    call_log_name: str,
) -> Optional[str]:
    """Lấy CRM Call Log được liên kết từ Zalo OA Call Log."""
    meta = frappe.get_meta(DOCTYPE)


    for fieldname in CRM_LINK_FIELDS:
        if not meta.has_field(fieldname):
            continue


        value = frappe.db.get_value(
            DOCTYPE,
            call_log_name,
            fieldname,
        )


        if value:
            return str(value)


    return None




def _filter_existing_fields(
    doctype: str,
    values: Dict[str, Any],
) -> Dict[str, Any]:
    """Chỉ giữ các field thật sự tồn tại trong DocType."""
    meta = frappe.get_meta(doctype)


    return {
        fieldname: value
        for fieldname, value in values.items()
        if meta.has_field(fieldname)
    }




def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None


    if isinstance(value, str):
        text = value.strip()
        return text or None


    if isinstance(value, (list, tuple, set)):
        text_items = [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]


        return ", ".join(text_items) or None


    if isinstance(value, dict):
        return _json_dump(value)


    return str(value).strip() or None




def _as_multiline_text(value: Any) -> Optional[str]:
    if value is None:
        return None


    if isinstance(value, str):
        return value.strip() or None


    if isinstance(value, (list, tuple, set)):
        lines = []


        for item in value:
            item_text = _as_text(item)


            if item_text:
                lines.append("- {0}".format(item_text))


        return "\n".join(lines) or None


    return _as_text(value)




def _as_datetime(value: Any) -> Any:
    """Chỉ trả datetime khi giá trị AI có thể parse hợp lệ."""
    if value in (None, "", "null", "None"):
        return None


    try:
        return get_datetime(value)
    except Exception:
        # Ví dụ "Chiều thứ Năm" không phải Datetime hợp lệ.
        # Giá trị gốc vẫn được giữ trong raw_ai_result.
        return None




def _json_dump(value: Any) -> str:
    """Lưu JSON với tiếng Việt rõ ràng, không chuyển thành \\uXXXX."""
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    )




def _set_status(
    call_log_name: str,
    status: str,
    error_message: Optional[str] = None,
    transcript: Optional[str] = None,
) -> None:
    _set_fields(
        call_log_name,
        {
            "processing_status": status,
            "error_message": error_message,
        },
        commit=True,
    )


    _sync_crm_call_log(
        call_log_name=call_log_name,
        status=status,
        transcript=transcript,
        error_message=error_message,
        commit=True,
    )


    _publish_status(
        call_log_name,
        status,
        error_message=error_message,
    )




def _set_fields(
    call_log_name: str,
    values: Dict[str, Any],
    commit: bool = False,
) -> None:
    frappe.db.set_value(
        DOCTYPE,
        call_log_name,
        values,
        update_modified=True,
    )


    if commit:
        frappe.db.commit()




def _publish_status(
    call_log_name: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {
        "name": call_log_name,
        "status": status,
        "error_message": error_message,
    }


    try:
        crm_call_log_name = _get_linked_crm_call_log(
            call_log_name
        )


        if crm_call_log_name:
            payload["crm_call_log"] = crm_call_log_name


    except Exception:
        # Không để lỗi đọc liên kết CRM làm hỏng pipeline chính.
        pass


    frappe.publish_realtime(
        REALTIME_EVENT,
        payload,
    )




def _clean_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:4000]


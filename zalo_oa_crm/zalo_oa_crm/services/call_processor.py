from __future__ import annotations

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
from frappe.utils.file_manager import save_file

from zalo_oa_crm.services.ai_call_service import (
    summarize_call,
    transcribe_audio,
)


DOCTYPE = "CRM Call Log"

# Giữ tên event cũ để JavaScript hiện tại không phải đổi ngay.
REALTIME_EVENT = "zalo_oa_call_log_ai_update"

ACTIVE_STATUSES = {
    "Queued",
    "Transcribing",
    "Summarizing",
}

REDIRECT_STATUSES = {
    301,
    302,
    303,
    307,
    308,
}

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
    """
    Đưa một CRM Call Log vào background queue để xử lý AI.

    Args:
        call_log_name:
            Tên document CRM Call Log.
        force:
            Cho phép chạy lại document đã Completed.
        retranscribe:
            Xóa transcript cũ và chạy Whisper lại.

    Returns:
        Dictionary chứa trạng thái đưa vào queue.
    """
    call_log_name = str(call_log_name or "").strip()

    if not call_log_name:
        frappe.throw(
            _("Thiếu tên CRM Call Log.")
        )

    force = bool(cint(force))
    retranscribe = bool(cint(retranscribe))

    if not frappe.db.exists(
        DOCTYPE,
        call_log_name,
    ):
        frappe.throw(
            _("Không tìm thấy CRM Call Log: {0}").format(
                call_log_name
            )
        )

    doc = frappe.get_doc(
        DOCTYPE,
        call_log_name,
    )
    doc.check_permission("write")

    status = str(
        doc.get("custom_ai_status")
        or "Pending"
    ).strip()

    if status in ACTIVE_STATUSES:
        return {
            "queued": False,
            "status": status,
            "message": _(
                "Cuộc gọi đang được AI xử lý."
            ),
        }

    if status == "Completed" and not force:
        return {
            "queued": False,
            "status": status,
            "message": _(
                "Cuộc gọi đã được xử lý. "
                "Dùng force=1 để chạy lại."
            ),
        }

    transcript = str(
        doc.get("custom_transcript")
        or ""
    ).strip()

    recording_url = str(
        doc.get("recording_url")
        or ""
    ).strip()

    if (
        retranscribe
        and not recording_url
    ):
        frappe.throw(
            _(
                "Cần có Recording URL để chạy "
                "Whisper lại."
            )
        )

    if not transcript and not recording_url:
        frappe.throw(
            _(
                "Cần có Transcript hoặc Recording URL "
                "trước khi chạy AI."
            )
        )

    updates: Dict[str, Any] = {
        "custom_ai_status": "Queued",
        "custom_error_message": None,
    }

    if retranscribe:
        updates["custom_transcript"] = None

    _set_fields(
        call_log_name,
        updates,
        commit=True,
    )

    _publish_status(
        call_log_name,
        "Queued",
    )

    timeout = cint(
        frappe.get_conf().get(
            "call_log_job_timeout"
        )
        or 1800
    )

    frappe.enqueue(
        (
            "zalo_oa_crm.services.call_processor."
            "process_call_log"
        ),
        queue="long",
        timeout=timeout,
        job_name="AI CRM Call Log {0}".format(
            call_log_name
        ),
        enqueue_after_commit=True,
        call_log_name=call_log_name,
        retranscribe=retranscribe,
    )

    return {
        "queued": True,
        "status": "Queued",
        "message": _(
            "Đã đưa CRM Call Log vào hàng đợi AI."
        ),
    }


def process_call_log(
    call_log_name: str,
    retranscribe: int = 0,
) -> Dict[str, Any]:
    """
    Chạy Whisper và AI summary cho chính CRM Call Log.

    Toàn bộ trạng thái, transcript và kết quả AI được
    ghi trực tiếp vào các Custom Field của CRM Call Log.
    """
    retranscribe = bool(cint(retranscribe))
    temporary_path: Optional[str] = None
    transcript = ""

    try:
        if not frappe.db.exists(
            DOCTYPE,
            call_log_name,
        ):
            frappe.throw(
                _(
                    "Không tìm thấy CRM Call Log: {0}"
                ).format(call_log_name)
            )

        doc = frappe.get_doc(
            DOCTYPE,
            call_log_name,
        )

        transcript = str(
            doc.get("custom_transcript")
            or ""
        ).strip()

        if retranscribe or not transcript:
            _set_status(
                call_log_name=call_log_name,
                status="Transcribing",
                transcript=None,
            )

            audio_path, is_temporary = (
                _resolve_audio_source(doc)
            )

            if is_temporary:
                temporary_path = audio_path

                # URL bên ngoài được tải xuống, lưu lại
                # thành File private gắn với CRM Call Log.
                file_url = _save_remote_audio(
                    call_log_name=doc.name,
                    local_path=audio_path,
                    original_url=doc.get(
                        "recording_url"
                    ),
                )

                _set_fields(
                    call_log_name,
                    {
                        "recording_url": file_url,
                    },
                    commit=True,
                )

            transcript_result = transcribe_audio(
                audio_path
            )

            transcript = _extract_transcript(
                transcript_result
            )

            if not transcript:
                frappe.throw(
                    _(
                        "Whisper không trả về transcript."
                    )
                )

            _set_fields(
                call_log_name,
                {
                    "custom_transcript": transcript,
                    "custom_ai_status": "Summarizing",
                    "custom_error_message": None,
                },
                commit=True,
            )

            _publish_status(
                call_log_name,
                "Summarizing",
            )

        else:
            _set_status(
                call_log_name=call_log_name,
                status="Summarizing",
                transcript=transcript,
            )

        ai_result = summarize_call(
            transcript
        )

        if not isinstance(
            ai_result,
            dict,
        ):
            frappe.throw(
                _(
                    "summarize_call() phải trả về "
                    "dictionary, nhận được {0}."
                ).format(
                    type(ai_result).__name__
                )
            )

        processed_at = now_datetime()

        updates = _map_ai_result(
            ai_result
        )
        updates.update(
            {
                "custom_transcript": transcript,
                "custom_ai_status": "Completed",
                "custom_processed_at": processed_at,
                "custom_error_message": None,
                "custom_retry_count": 0,
                "custom_raw_ai_result": _json_dump(
                    ai_result
                ),
            }
        )

        _set_fields(
            call_log_name,
            updates,
            commit=True,
        )

        _publish_status(
            call_log_name,
            "Completed",
        )

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
            title=(
                "AI CRM Call Log failed: {0}"
            ).format(call_log_name),
        )

        error_message = _clean_error(
            exc
        )

        try:
            current_retry = cint(
                frappe.db.get_value(
                    DOCTYPE,
                    call_log_name,
                    "custom_retry_count",
                )
                or 0
            )

            _set_fields(
                call_log_name,
                {
                    "custom_ai_status": "Failed",
                    "custom_error_message": (
                        error_message
                    ),
                    "custom_retry_count": (
                        current_retry + 1
                    ),
                },
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
                title=(
                    "Cannot update failed "
                    "CRM Call Log: {0}"
                ).format(call_log_name),
            )

        raise

    finally:
        if temporary_path:
            try:
                os.remove(
                    temporary_path
                )
            except FileNotFoundError:
                pass
            except OSError:
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=(
                        "Cannot remove temporary "
                        "Call Log media"
                    ),
                )


def _resolve_audio_source(
    doc: Any,
) -> Tuple[str, bool]:
    """
    Trả về:
        (đường_dẫn_local, có_phải_file_tạm)

    CRM Call Log chỉ dùng field recording_url.
    """
    recording_url = str(
        doc.get("recording_url")
        or ""
    ).strip()

    if not recording_url:
        frappe.throw(
            _(
                "CRM Call Log chưa có Recording URL."
            )
        )

    parsed = urlparse(
        recording_url
    )
    parsed_path = parsed.path or ""

    # File nội bộ Frappe dạng:
    # /files/...
    # /private/files/...
    if recording_url.startswith(
        ("/files/", "/private/files/")
    ):
        return (
            _resolve_frappe_file(
                recording_url
            ),
            False,
        )

    # Hỗ trợ cả URL tuyệt đối trỏ vào file path.
    # Nếu File document có đúng file_url thì ưu tiên
    # đọc local, không tải qua HTTP.
    if parsed_path.startswith(
        ("/files/", "/private/files/")
    ):
        file_name = frappe.db.get_value(
            "File",
            {"file_url": parsed_path},
            "name",
        )

        if file_name:
            return (
                _resolve_frappe_file(
                    parsed_path
                ),
                False,
            )

    if parsed.scheme in {
        "http",
        "https",
    }:
        return (
            _download_remote_media(
                recording_url
            ),
            True,
        )

    frappe.throw(
        _("Recording URL không hợp lệ.")
    )
    raise AssertionError(
        "unreachable"
    )


def _save_remote_audio(
    call_log_name: str,
    local_path: str,
    original_url: Optional[str] = None,
) -> str:
    """
    Lưu file tải từ URL thành File private và
    gắn trực tiếp với CRM Call Log.
    """
    path = Path(
        local_path
    )

    filename = Path(
        urlparse(
            original_url or ""
        ).path
    ).name

    if not filename:
        filename = (
            "call-recording{0}"
        ).format(
            path.suffix or ".media"
        )

    with path.open(
        "rb"
    ) as file_handle:
        content = file_handle.read()

    if not content:
        frappe.throw(
            _("File media tải về bị rỗng.")
        )

    file_doc = save_file(
        fname=filename,
        content=content,
        dt=DOCTYPE,
        dn=call_log_name,
        is_private=1,
    )

    return file_doc.file_url


def _resolve_frappe_file(
    file_url: str,
) -> str:
    """
    Tìm đường dẫn vật lý của File document
    trong Frappe.
    """
    file_name = frappe.db.get_value(
        "File",
        {"file_url": file_url},
        "name",
    )

    if not file_name:
        frappe.throw(
            _(
                "Không tìm thấy File document "
                "tương ứng với {0}."
            ).format(file_url)
        )

    file_doc = frappe.get_doc(
        "File",
        file_name,
    )
    file_path = file_doc.get_full_path()

    if (
        not file_path
        or not os.path.isfile(file_path)
    ):
        frappe.throw(
            _(
                "File audio không tồn tại "
                "trên máy chủ."
            )
        )

    _validate_file_size(
        file_path
    )

    return file_path


def _download_remote_media(
    url: str,
) -> str:
    """
    Tải URL media với giới hạn dung lượng,
    kiểm tra redirect và chống SSRF.
    """
    current_url = url.strip()
    max_bytes = _max_audio_bytes()

    for _redirect_index in range(4):
        _assert_public_http_url(
            current_url
        )

        with requests.get(
            current_url,
            stream=True,
            allow_redirects=False,
            timeout=(10, 120),
            headers={
                "User-Agent": (
                    "Zalo-OA-CRM-"
                    "Call-Processor/1.0"
                ),
            },
        ) as response:
            if (
                response.status_code
                in REDIRECT_STATUSES
            ):
                location = (
                    response.headers.get(
                        "Location"
                    )
                )

                if not location:
                    frappe.throw(
                        _(
                            "Media URL redirect "
                            "nhưng thiếu Location header."
                        )
                    )

                current_url = urljoin(
                    current_url,
                    location,
                )
                continue

            response.raise_for_status()

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
                .split(";", 1)[0]
                .strip()
                .lower()
            )

            if (
                content_type.startswith("text/")
                or content_type
                in {
                    "application/json",
                    "application/xml",
                    "text/html",
                }
            ):
                frappe.throw(
                    _(
                        "Audio URL đang trỏ tới "
                        "trang HTML/API, không phải "
                        "file media trực tiếp."
                    )
                )

            if (
                content_type
                and not content_type.startswith(
                    "audio/"
                )
                and not content_type.startswith(
                    "video/"
                )
                and content_type
                not in ALLOWED_GENERIC_CONTENT_TYPES
            ):
                frappe.throw(
                    _(
                        "Content-Type không được "
                        "hỗ trợ: {0}"
                    ).format(content_type)
                )

            content_length = cint(
                response.headers.get(
                    "Content-Length"
                )
                or 0
            )

            if (
                content_length
                and content_length > max_bytes
            ):
                frappe.throw(
                    _(
                        "File vượt quá giới hạn "
                        "{0} MB."
                    ).format(
                        _max_audio_mb()
                    )
                )

            suffix = _guess_suffix(
                current_url,
                content_type,
            )

            temp_file = (
                tempfile.NamedTemporaryFile(
                    prefix="zalo-call-",
                    suffix=suffix,
                    delete=False,
                )
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
                                _(
                                    "File vượt quá "
                                    "giới hạn {0} MB."
                                ).format(
                                    _max_audio_mb()
                                )
                            )

                        temp_file.write(
                            chunk
                        )

                if total == 0:
                    frappe.throw(
                        _(
                            "File media tải về bị rỗng."
                        )
                    )

                return temp_path

            except Exception:
                try:
                    os.remove(
                        temp_path
                    )
                except OSError:
                    pass

                raise

    frappe.throw(
        _("Media URL redirect quá nhiều lần.")
    )
    raise AssertionError(
        "unreachable"
    )


def _assert_public_http_url(
    url: str,
) -> None:
    """
    Chỉ cho phép URL HTTP/HTTPS trỏ tới
    địa chỉ mạng công khai.
    """
    parsed = urlparse(
        url
    )

    if parsed.scheme not in {
        "http",
        "https",
    }:
        frappe.throw(
            _(
                "Audio URL chỉ hỗ trợ "
                "http hoặc https."
            )
        )

    if not parsed.hostname:
        frappe.throw(
            _("Audio URL không hợp lệ.")
        )

    if (
        parsed.username
        or parsed.password
    ):
        frappe.throw(
            _(
                "Audio URL không được chứa "
                "username/password."
            )
        )

    try:
        port = parsed.port or (
            443
            if parsed.scheme == "https"
            else 80
        )

        addresses = socket.getaddrinfo(
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )

    except (
        OSError,
        ValueError,
    ) as exc:
        frappe.throw(
            _(
                "Không phân giải được hostname "
                "của Audio URL: {0}"
            ).format(exc)
        )
        return

    if not addresses:
        frappe.throw(
            _(
                "Hostname của Audio URL "
                "không có địa chỉ IP."
            )
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
                    "Audio URL trỏ tới địa chỉ "
                    "mạng nội bộ hoặc không an toàn."
                )
            )


def _validate_file_size(
    file_path: str,
) -> None:
    size = os.path.getsize(
        file_path
    )

    if size <= 0:
        frappe.throw(
            _("File audio bị rỗng.")
        )

    if size > _max_audio_bytes():
        frappe.throw(
            _(
                "File vượt quá giới hạn "
                "{0} MB."
            ).format(
                _max_audio_mb()
            )
        )


def _max_audio_mb() -> int:
    return max(
        cint(
            frappe.get_conf().get(
                "call_log_max_audio_mb"
            )
            or 20
        ),
        1,
    )


def _max_audio_bytes() -> int:
    return (
        _max_audio_mb()
        * 1024
        * 1024
    )


def _guess_suffix(
    url: str,
    content_type: str,
) -> str:
    url_suffix = Path(
        urlparse(url).path
    ).suffix

    if (
        url_suffix
        and len(url_suffix) <= 10
    ):
        return url_suffix

    guessed = mimetypes.guess_extension(
        content_type or ""
    )

    return guessed or ".media"


def _extract_transcript(
    value: Any,
) -> str:
    """
    Chuẩn hóa kết quả transcribe_audio
    về string.
    """
    if isinstance(
        value,
        str,
    ):
        return value.strip()

    if isinstance(
        value,
        dict,
    ):
        for key in (
            "text",
            "transcript",
        ):
            candidate = value.get(
                key
            )

            if isinstance(
                candidate,
                str,
            ):
                return candidate.strip()

    frappe.throw(
        _(
            "transcribe_audio() phải trả về "
            "string hoặc dict chứa "
            "text/transcript."
        )
    )

    raise AssertionError(
        "unreachable"
    )


def _map_ai_result(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Map kết quả AI trực tiếp vào Custom Field
    của CRM Call Log.
    """
    return {
        "custom_ai_summary": _as_text(
            result.get("summary")
        ),
        "custom_customer_need": _as_text(
            result.get("customer_need")
        ),
        "custom_sentiment": _as_text(
            result.get("sentiment")
        ),
        "custom_call_outcome": _as_text(
            result.get("call_outcome")
        ),
        "custom_action_items": (
            _as_multiline_text(
                result.get("action_items")
            )
        ),
        "custom_important_points": (
            _as_multiline_text(
                result.get("important_points")
            )
        ),
        "custom_quality_notes": _as_text(
            result.get("quality_notes")
        ),
        "custom_next_follow_up": (
            _as_datetime(
                result.get("next_follow_up")
            )
        ),
    }


def _filter_existing_fields(
    doctype: str,
    values: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Chỉ giữ các field thật sự tồn tại
    trong DocType.
    """
    meta = frappe.get_meta(
        doctype
    )

    return {
        fieldname: value
        for fieldname, value
        in values.items()
        if meta.has_field(
            fieldname
        )
    }


def _as_text(
    value: Any,
) -> Optional[str]:
    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        text = value.strip()
        return text or None

    if isinstance(
        value,
        (list, tuple, set),
    ):
        text_items = [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

        return (
            ", ".join(text_items)
            or None
        )

    if isinstance(
        value,
        dict,
    ):
        return _json_dump(
            value
        )

    return (
        str(value).strip()
        or None
    )


def _as_multiline_text(
    value: Any,
) -> Optional[str]:
    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        return (
            value.strip()
            or None
        )

    if isinstance(
        value,
        (list, tuple, set),
    ):
        lines = []

        for item in value:
            item_text = _as_text(
                item
            )

            if item_text:
                lines.append(
                    "- {0}".format(
                        item_text
                    )
                )

        return (
            "\n".join(lines)
            or None
        )

    return _as_text(
        value
    )


def _as_datetime(
    value: Any,
) -> Any:
    """
    Chỉ trả datetime khi giá trị AI có thể
    parse hợp lệ.
    """
    if value in (
        None,
        "",
        "null",
        "None",
    ):
        return None

    try:
        return get_datetime(
            value
        )
    except Exception:
        # Ví dụ "Chiều thứ Năm" không phải
        # Datetime hợp lệ. Giá trị gốc vẫn
        # nằm trong custom_raw_ai_result.
        return None


def _json_dump(
    value: Any,
) -> str:
    """
    Lưu JSON tiếng Việt rõ ràng,
    không chuyển thành chuỗi \\uXXXX.
    """
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
    values: Dict[str, Any] = {
        "custom_ai_status": status,
        "custom_error_message": (
            error_message
        ),
    }

    if transcript is not None:
        values[
            "custom_transcript"
        ] = transcript

    _set_fields(
        call_log_name,
        values,
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
    existing_values = (
        _filter_existing_fields(
            DOCTYPE,
            values,
        )
    )

    if not existing_values:
        return

    frappe.db.set_value(
        DOCTYPE,
        call_log_name,
        existing_values,
        update_modified=True,
    )

    if commit:
        frappe.db.commit()


def _publish_status(
    call_log_name: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Publish cả name và crm_call_log để tương
    thích với JavaScript hiện tại.
    """
    frappe.publish_realtime(
        REALTIME_EVENT,
        {
            "name": call_log_name,
            "crm_call_log": call_log_name,
            "status": status,
            "error_message": error_message,
        },
    )


def _clean_error(
    exc: Exception,
) -> str:
    text = (
        str(exc).strip()
        or exc.__class__.__name__
    )

    return text[:4000]

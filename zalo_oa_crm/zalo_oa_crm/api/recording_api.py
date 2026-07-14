from __future__ import annotations


import mimetypes
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse


import frappe
from frappe import _
from werkzeug.wrappers import Response




CRM_CALL_LOG_DOCTYPE = "CRM Call Log"


RANGE_PATTERN = re.compile(
    r"^bytes=(\d*)-(\d*)$"
)




def _resolve_local_recording_path(
    file_url: str,
) -> Optional[str]:
    """Chuyển /files/... hoặc /private/files/... thành đường dẫn local an toàn."""
    url_path = unquote(
        urlparse(file_url).path
    )


    if url_path.startswith(
        "/private/files/"
    ):
        base_directory = frappe.get_site_path(
            "private",
            "files",
        )
        relative_path = url_path[
            len("/private/files/"):
        ]


    elif url_path.startswith("/files/"):
        base_directory = frappe.get_site_path(
            "public",
            "files",
        )
        relative_path = url_path[
            len("/files/"):
        ]


    else:
        return None


    base_directory = os.path.realpath(
        base_directory
    )


    candidate_path = os.path.realpath(
        os.path.join(
            base_directory,
            relative_path,
        )
    )


    try:
        common_path = os.path.commonpath(
            [
                base_directory,
                candidate_path,
            ]
        )
    except ValueError:
        return None


    if common_path != base_directory:
        frappe.throw(
            _("Đường dẫn recording không hợp lệ.")
        )


    if not os.path.isfile(candidate_path):
        frappe.throw(
            _("Không tìm thấy file recording.")
        )


    return candidate_path




def _parse_range(
    range_header: str,
    file_size: int,
) -> Optional[Tuple[int, int]]:
    """Đọc HTTP Range để audio player có thể seek."""
    match = RANGE_PATTERN.match(
        range_header.strip()
    )


    if not match:
        return None


    start_text = match.group(1)
    end_text = match.group(2)


    if not start_text and not end_text:
        return None


    if not start_text:
        suffix_length = int(end_text)


        if suffix_length <= 0:
            return None


        start = max(
            file_size - suffix_length,
            0,
        )
        end = file_size - 1


    else:
        start = int(start_text)


        if end_text:
            end = int(end_text)
        else:
            end = file_size - 1


    if start < 0:
        return None


    if start >= file_size:
        return None


    end = min(
        end,
        file_size - 1,
    )


    if end < start:
        return None


    return start, end




def _make_file_response(
    file_path: str,
) -> Response:
    file_size = os.path.getsize(file_path)


    if file_size <= 0:
        frappe.throw(
            _("File recording bị rỗng.")
        )


    range_header = frappe.request.headers.get(
        "Range"
    )


    start = 0
    end = file_size - 1
    status_code = 200


    if range_header:
        byte_range = _parse_range(
            range_header,
            file_size,
        )


        if byte_range is None:
            response = Response(
                status=416
            )
            response.headers[
                "Content-Range"
            ] = f"bytes */{file_size}"


            return response


        start, end = byte_range
        status_code = 206


    content_length = end - start + 1


    with open(file_path, "rb") as recording:
        recording.seek(start)
        content = recording.read(
            content_length
        )


    mime_type = (
        mimetypes.guess_type(file_path)[0]
        or "application/octet-stream"
    )


    filename = Path(file_path).name.replace(
        '"',
        "",
    )


    response = Response(
        status=status_code
    )
    response.data = content
    response.mimetype = mime_type


    response.headers[
        "Content-Length"
    ] = str(len(content))


    response.headers[
        "Accept-Ranges"
    ] = "bytes"


    response.headers[
        "Content-Disposition"
    ] = f'inline; filename="{filename}"'


    response.headers[
        "Cache-Control"
    ] = "private, max-age=3600"


    if status_code == 206:
        response.headers[
            "Content-Range"
        ] = (
            f"bytes {start}-{end}/{file_size}"
        )


    return response




@frappe.whitelist()
def get_recording_url(
    call_log_name: str,
):
    """Phát recording local cho CRM Call Log loại Manual."""


    if not call_log_name:
        frappe.throw(
            _("Thiếu tên CRM Call Log.")
        )


    if not frappe.db.exists(
        CRM_CALL_LOG_DOCTYPE,
        call_log_name,
    ):
        frappe.throw(
            _("Không tìm thấy Call Log."),
            frappe.DoesNotExistError,
        )


    call_log = frappe.get_doc(
        CRM_CALL_LOG_DOCTYPE,
        call_log_name,
    )


    call_log.check_permission("read")


    if not call_log.recording_url:
        frappe.throw(
            _("Call Log chưa có recording URL."),
            frappe.DoesNotExistError,
        )


    # Giữ nguyên cách xử lý chuẩn cho provider thật.
    if call_log.telephony_medium in {
        "Twilio",
        "Exotel",
    }:
        from crm.integrations.api import (
            get_recording_url as core_get_recording_url,
        )


        return core_get_recording_url(
            call_log_name
        )


    file_path = _resolve_local_recording_path(
        call_log.recording_url
    )


    if not file_path:
        frappe.throw(
            _(
                "Recording của cuộc gọi Manual phải là "
                "/files/... hoặc /private/files/..."
            )
        )


    return _make_file_response(
        file_path
    )


import os
import re
import wave
import math
import struct


import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, get_datetime




def _create_demo_recording_file(duration_seconds=3):
    """
    Tạo file ghi âm giả lập nếu Postman không truyền recording_url.
    File nằm tại: /files/zalo_demo_call_recording.wav
    """


    files_dir = frappe.get_site_path("public", "files")
    os.makedirs(files_dir, exist_ok=True)


    filename = "zalo_demo_call_recording.wav"
    file_path = os.path.join(files_dir, filename)


    if os.path.exists(file_path):
        return f"/files/{filename}"


    sample_rate = 16000
    seconds = int(duration_seconds or 3)
    amplitude = 12000
    frequency = 440


    with wave.open(file_path, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)


        for i in range(sample_rate * seconds):
            value = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
            wav_file.writeframes(struct.pack("<h", value))


    return f"/files/{filename}"




def _validate_required(value, field_label):
    if value is None or str(value).strip() == "":
        frappe.throw(_(f"Missing required field: {field_label}"))




def _make_demo_email(name):
    """
    Chuyển tên demo thành email hợp lệ.
    Ví dụ:
    Sarah Connor -> sarah.connor@zalo-demo.example.com
    """


    base = re.sub(r"[^a-z0-9]+", ".", str(name).strip().lower()).strip(".")


    if not base:
        base = "demo.user"


    return f"{base}@zalo-demo.example.com"




def _get_or_create_demo_user(value):
    """
    CRM Call Log field caller/receiver là Link tới User.
    Vì vậy nếu Postman gửi Sarah Connor / Bob Martinez,
    hàm này sẽ tự tạo User demo rồi trả về email User hợp lệ.


    Nếu gửi Administrator hoặc email User đã tồn tại thì dùng luôn.
    """


    value = str(value).strip()


    if frappe.db.exists("User", value):
        return value


    email = value if "@" in value else _make_demo_email(value)


    if frappe.db.exists("User", email):
        return email


    parts = value.replace("@", " ").replace(".", " ").split()


    first_name = parts[0].title() if parts else "Demo"
    last_name = " ".join([p.title() for p in parts[1:]]) if len(parts) > 1 else "User"


    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "enabled": 1,
        "user_type": "System User",
        "send_welcome_email": 0,
    })


    user.insert(
        ignore_permissions=True,
        ignore_mandatory=True
    )


    return email




@frappe.whitelist(allow_guest=True)
def simulate_completed_call(
    caller=None,
    receiver=None,
    from_number=None,
    to_number=None,
    duration=None,
    call_type="Outgoing",
    start_time=None,
    recording_url=None,
):
    """
    API giả lập cuộc gọi hoàn thành để test bằng Postman.


    Postman truyền vào:
    - caller
    - receiver
    - from_number
    - to_number
    - duration
    - call_type: Incoming hoặc Outgoing
    - start_time: optional
    - recording_url: optional


    API sẽ tạo record vào CRM Call Log gồm:
    - Ai gọi
    - Ai nhận
    - Số gọi đi
    - Số nhận
    - Thời gian bắt đầu
    - Thời gian kết thúc
    - Duration
    - File ghi âm
    """


    _validate_required(caller, "caller")
    _validate_required(receiver, "receiver")
    _validate_required(from_number, "from_number")
    _validate_required(to_number, "to_number")
    _validate_required(duration, "duration")


    duration = int(duration)


    if duration <= 0:
        frappe.throw(_("Duration must be greater than 0"))


    if call_type not in ["Incoming", "Outgoing"]:
        frappe.throw(_("call_type must be Incoming or Outgoing"))


    caller_user = _get_or_create_demo_user(caller)
    receiver_user = _get_or_create_demo_user(receiver)


    start_dt = get_datetime(start_time) if start_time else add_to_date(
        now_datetime(),
        seconds=-duration
    )
    end_dt = add_to_date(start_dt, seconds=duration)


    if not recording_url:
        recording_url = _create_demo_recording_file()

    call_id = f"ZALO-DEMO-{frappe.generate_hash(length=10)}"

    doc = frappe.get_doc({
        "doctype": "CRM Call Log",
        "id": call_id,
        "telephony_medium": "Manual",
        "type": call_type,
        "status": "Completed",
        "caller": caller_user,
        "receiver": receiver_user,
        "from": from_number,
        "to": to_number,
        "start_time": start_dt,
        "end_time": end_dt,
        "duration": duration,
        "recording_url": recording_url,
    })


    doc.insert(ignore_permissions=True)
    frappe.db.commit()


    result = {
        "ok": True,
        "site": frappe.local.site,
        "call_log": doc.name,
        "caller_input": caller,
        "receiver_input": receiver,
        "caller": caller_user,
        "receiver": receiver_user,
        "type": call_type,
        "status": "Completed",
        "from_number": from_number,
        "to_number": to_number,
        "start_time": str(start_dt),
        "end_time": str(end_dt),
        "duration": duration,
        "recording_url": recording_url,
    }


    frappe.logger("zalo_oa_crm").info(
        f"[CALL_SIMULATOR] Completed call created: {result}"
    )

    return result




@frappe.whitelist(allow_guest=True)
def get_recent_call_logs(limit=10):
    """
    API phụ để kiểm tra nhanh bằng Postman xem dữ liệu đã vào database chưa.
    """


    limit = int(limit or 10)


    logs = frappe.get_all(
        "CRM Call Log",
        fields=[
            "name",
            "caller",
            "receiver",
            "type",
            "status",
            "duration",
            "from",
            "to",
            "start_time",
            "end_time",
            "recording_url",
            "creation",
        ],
        order_by="creation desc",
        limit_page_length=limit,
        ignore_permissions=True,
    )


    return {
        "ok": True,
        "site": frappe.local.site,
        "count": len(logs),
        "logs": logs,
    }


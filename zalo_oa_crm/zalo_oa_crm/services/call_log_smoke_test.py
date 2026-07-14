from __future__ import annotations


from typing import Any, Dict


import frappe


from zalo_oa_crm.services.ai_call_service import summarize_call, transcribe_audio
from zalo_oa_crm.services.call_processor import process_call_log




SAMPLE_CALL_TRANSCRIPT = """
Nhân viên: Em chào anh, em gọi từ bộ phận kinh doanh. Anh đang quan tâm gói CRM nào ạ?
Khách hàng: Tôi cần gói cho khoảng 15 nhân viên, ưu tiên quản lý khách hàng và lịch sử gọi điện.
Nhân viên: Bên em có gói phù hợp. Em sẽ gửi báo giá trong hôm nay.
Khách hàng: Được, gửi qua email giúp tôi. Chiều thứ Năm gọi lại trao đổi thêm.
""".strip()




def test_summary(transcript: str = SAMPLE_CALL_TRANSCRIPT) -> Dict[str, Any]:
    result = summarize_call(transcript)
    if not isinstance(result, dict):
        frappe.throw(
            "summarize_call() phải trả về dict, nhận được {0}".format(
                type(result).__name__
            )
        )
    return result




def test_transcription(file_path: str) -> Dict[str, str]:
    result = transcribe_audio(file_path)


    if isinstance(result, str):
        transcript = result.strip()
    elif isinstance(result, dict):
        transcript = str(result.get("text") or result.get("transcript") or "").strip()
    else:
        frappe.throw(
            "transcribe_audio() phải trả về str hoặc dict, nhận được {0}".format(
                type(result).__name__
            )
        )


    if not transcript:
        frappe.throw("Whisper không trả về transcript.")


    return {"transcript": transcript}




def test_call_log(call_log_name: str) -> Dict[str, Any]:
    return process_call_log(call_log_name)




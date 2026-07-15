from __future__ import annotations


import json
import random
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any


import frappe
from faster_whisper import WhisperModel
from openai import APIStatusError, OpenAI




ALLOWED_SENTIMENTS = {
    "Positive",
    "Neutral",
    "Negative",
    "Mixed",
}


ALLOWED_OUTCOMES = {
    "Interested",
    "Follow-up",
    "Won",
    "Lost",
    "No answer",
    "Unknown",
}




def _get_config_value(
    key: str,
    default: Any = None,
) -> Any:
    """Đọc một giá trị từ site_config.json."""


    return frappe.get_conf().get(key, default)




def _get_openrouter_client() -> OpenAI:
    """Khởi tạo OpenRouter client bằng OpenAI-compatible SDK."""


    api_key = _get_config_value("openrouter_api_key")
    base_url = _get_config_value(
        "openrouter_base_url",
        "https://openrouter.ai/api/v1",
    )


    if not api_key:
        frappe.throw(
            "Chưa cấu hình openrouter_api_key "
            "trong site_config.json."
        )


    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=180.0,
    )




@lru_cache(maxsize=1)
def _get_whisper_model() -> WhisperModel:
    """
    Tải Whisper model một lần trong vòng đời tiến trình.


    Background worker sẽ tái sử dụng model để tránh tải lại
    cho mỗi cuộc gọi.
    """


    model_name = _get_config_value(
        "call_log_transcription_model",
        "small",
    )
    device = _get_config_value(
        "call_log_whisper_device",
        "cpu",
    )
    compute_type = _get_config_value(
        "call_log_whisper_compute_type",
        "int8",
    )


    frappe.logger("zalo_oa_crm").info(
        "Loading Whisper model: model=%s device=%s compute_type=%s",
        model_name,
        device,
        compute_type,
    )


    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
    )




def transcribe_audio(file_path: str) -> str:
    """
    Chuyển file audio thành transcript tiếng Việt.


    Args:
        file_path:
            Đường dẫn tuyệt đối tới file audio trong container.


    Returns:
        Transcript đã được nối thành một chuỗi.
    """


    file_path = str(file_path or "").strip()


    if not file_path:
        frappe.throw("Thiếu đường dẫn file audio.")


    audio_path = Path(file_path)


    if not audio_path.exists():
        frappe.throw(
            f"Không tìm thấy file audio: {audio_path}"
        )


    if not audio_path.is_file():
        frappe.throw(
            f"Đường dẫn audio không phải là file: {audio_path}"
        )


    model = _get_whisper_model()


    segments, info = model.transcribe(
    str(audio_path),
    language=None,
    beam_size=5,
    vad_filter=False,
    condition_on_previous_text=True,
)

    transcript_parts: list[str] = []


    for segment in segments:
        text = str(segment.text or "").strip()


        if text:
            transcript_parts.append(text)


    transcript = " ".join(transcript_parts).strip()


    if not transcript:
        frappe.throw(
            "Không nhận diện được nội dung nói trong file audio."
        )


    frappe.logger("zalo_oa_crm").info(
        "Transcription completed: language=%s probability=%s",
        getattr(info, "language", None),
        getattr(info, "language_probability", None),
    )


    return transcript




def _extract_json(raw_text: str) -> dict[str, Any]:
    """
    Trích JSON từ kết quả AI.


    Hỗ trợ cả trường hợp model trả:


    ```json
    {...}
    ```
    """


    text = str(raw_text or "").strip()


    if not text:
        frappe.throw("AI trả về nội dung trống.")


    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*```$",
        "",
        text,
    ).strip()


    start = text.find("{")
    end = text.rfind("}")


    if start < 0 or end < 0 or end <= start:
        frappe.log_error(
            title="Call Summary Missing JSON",
            message=f"Raw AI response:\n{text}",
        )


        frappe.throw(
            "AI không trả về JSON object hợp lệ."
        )


    json_text = text[start : end + 1]


    try:
        result = json.loads(json_text)


    except json.JSONDecodeError as exc:
        frappe.log_error(
            title="Call Summary JSON Parsing Failed",
            message=(
                f"JSON error: {exc}\n\n"
                f"Raw AI response:\n{raw_text}"
            ),
        )


        frappe.throw(
            "Không thể đọc kết quả JSON do AI trả về."
        )


    if not isinstance(result, dict):
        frappe.throw(
            "Kết quả AI phải là một JSON object."
        )


    return result




def _normalize_string_list(value: Any) -> list[str]:
    """Chuẩn hóa dữ liệu dạng danh sách chuỗi."""


    if value is None:
        return []


    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []


    if not isinstance(value, list):
        return []


    normalized: list[str] = []


    for item in value:
        text = str(item or "").strip()


        if text:
            normalized.append(text)


    return normalized




def _normalize_enum(
    value: Any,
    allowed_values: set[str],
    default: str,
) -> str:
    """Chuẩn hóa enum không phân biệt chữ hoa/chữ thường."""


    text = str(value or "").strip()


    if not text:
        return default


    lookup = {
        allowed.lower(): allowed
        for allowed in allowed_values
    }


    return lookup.get(text.lower(), default)




def _is_retryable_openrouter_error(
    exc: APIStatusError,
) -> bool:
    """
    Xác định lỗi OpenRouter có thể thử lại.


    Bao gồm:
    - timeout;
    - rate limit;
    - lỗi tạm thời phía provider;
    - OpenRouter trả 404 nhưng metadata chứa lỗi 429 trước đó.
    """


    status_code = getattr(exc, "status_code", None)


    try:
        body_text = json.dumps(
            getattr(exc, "body", None),
            ensure_ascii=False,
            default=str,
        ).lower()


    except Exception:
        body_text = str(exc).lower()


    if status_code in {
        408,
        409,
        429,
        500,
        502,
        503,
        504,
    }:
        return True


    if status_code == 404:
        temporary_markers = (
            "temporarily rate-limited",
            "rate limit",
            "rate-limited",
            '"code": 429',
            "'code': 429",
            "previous_errors",
        )


        return any(
            marker in body_text
            for marker in temporary_markers
        )


    return False




def _get_retry_after_seconds(
    exc: APIStatusError,
) -> float | None:
    """Đọc Retry-After từ HTTP response nếu có."""


    response = getattr(exc, "response", None)


    if response is None:
        return None


    retry_after = response.headers.get("retry-after")


    if not retry_after:
        return None


    try:
        return max(float(retry_after), 0)


    except (TypeError, ValueError):
        return None




def _completion_has_content(response: Any) -> bool:
    """Kiểm tra Chat Completion có nội dung text hay không."""


    choices = getattr(response, "choices", None)


    if not choices:
        return False


    message = getattr(choices[0], "message", None)


    if message is None:
        return False


    content = getattr(message, "content", None)


    return (
        isinstance(content, str)
        and bool(content.strip())
    )




def _dump_response(response: Any) -> str:
    """Chuyển response thành JSON để ghi log an toàn."""


    try:
        return response.model_dump_json(indent=2)


    except Exception:
        return str(response)




def _create_summary_completion(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
):
    """
    Gọi OpenRouter bằng Google AI Studio BYOK.


    Tự retry khi:
    - provider trả lỗi 429 hoặc lỗi tạm thời;
    - provider trả response không có choices;
    - choices không chứa nội dung text.
    """


    max_attempts = int(
        _get_config_value(
            "call_log_summary_max_attempts",
            4,
        )
    )


    max_attempts = max(1, min(max_attempts, 6))


    retry_delays = [5, 15, 45, 60, 90]
    last_empty_response = None


    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ],
    temperature=0.1,
    max_completion_tokens=1600,
)


            if _completion_has_content(response):
                return response


            last_empty_response = response


            frappe.logger("zalo_oa_crm").warning(
                "OpenRouter returned empty completion. "
                "Attempt %s/%s. Response: %s",
                attempt,
                max_attempts,
                _dump_response(response),
            )


        except APIStatusError as exc:
            is_last_attempt = (
                attempt >= max_attempts
            )


            if (
                is_last_attempt
                or not _is_retryable_openrouter_error(exc)
            ):
                frappe.log_error(
                    title="OpenRouter API Error",
                    message=(
                        f"Attempt: {attempt}/{max_attempts}\n"
                        f"Status: "
                        f"{getattr(exc, 'status_code', None)}\n"
                        f"Error: {exc}\n"
                        f"Body: "
                        f"{getattr(exc, 'body', None)}"
                    ),
                )


                raise


            retry_after = _get_retry_after_seconds(exc)


            if retry_after is None:
                delay_index = min(
                    attempt - 1,
                    len(retry_delays) - 1,
                )
                retry_after = retry_delays[delay_index]
                retry_after += random.uniform(0, 2)


            frappe.logger("zalo_oa_crm").warning(
                "OpenRouter temporary error. "
                "Attempt %s/%s; retrying after %.1f seconds. "
                "Error: %s",
                attempt,
                max_attempts,
                retry_after,
                exc,
            )


            time.sleep(retry_after)
            continue


        if attempt < max_attempts:
            delay_index = min(
                attempt - 1,
                len(retry_delays) - 1,
            )
            retry_after = retry_delays[delay_index]
            retry_after += random.uniform(0, 2)


            frappe.logger("zalo_oa_crm").warning(
                "Retrying empty OpenRouter response "
                "after %.1f seconds.",
                retry_after,
            )


            time.sleep(retry_after)


    if last_empty_response is not None:
        frappe.log_error(
            title="OpenRouter Empty Completion",
            message=_dump_response(
                last_empty_response
            ),
        )


    frappe.throw(
        "OpenRouter trả về phản hồi rỗng sau nhiều lần thử."
    )




def summarize_call(
    transcript: str,
) -> dict[str, Any]:
    """
    Phân tích transcript và trả kết quả chuẩn hóa cho Call Log.


    Returns:
        Dictionary gồm summary, customer_need, sentiment,
        call_outcome, action_items và các dữ liệu liên quan.
    """


    transcript = str(transcript or "").strip()


    if not transcript:
        frappe.throw("Transcript đang trống.")


    model = _get_config_value(
        "call_log_summary_model",
        "google/gemma-4-31b-it:free",
    )


    client = _get_openrouter_client()


    system_prompt = """
Bạn là trợ lý phân tích cuộc gọi bán hàng trong hệ thống CRM.


Quy tắc bắt buộc:
- Trả lời bằng tiếng Việt.
- Không suy đoán dữ liệu không có trong transcript.
- Không thêm tên, số điện thoại, giá tiền hoặc lịch hẹn
  không xuất hiện trong transcript.
- Chỉ trả về một JSON object hợp lệ.
- Không viết nội dung giải thích ngoài JSON.
- Không sử dụng Markdown.
- Không đặt JSON trong dấu ba dấu nháy ngược.


Các giá trị sentiment hợp lệ:
Positive, Neutral, Negative, Mixed.


Các giá trị call_outcome hợp lệ:
Interested, Follow-up, Won, Lost, No answer, Unknown.
""".strip()


    user_prompt = f"""
Phân tích transcript cuộc gọi sau:


--- TRANSCRIPT ---
{transcript}
--- END TRANSCRIPT ---


Trả về đúng cấu trúc JSON sau:


{{
  "summary": "Tóm tắt cuộc gọi trong 3 đến 5 câu",
  "customer_need": "Nhu cầu chính của khách hàng",
  "sentiment": "Positive",
  "call_outcome": "Follow-up",
  "action_items": [
    "Việc cần thực hiện"
  ],
  "important_points": [
    "Thông tin quan trọng"
  ],
  "next_follow_up": null,
  "quality_notes": "Nhận xét ngắn về chất lượng tư vấn"
}}


Chỉ được chọn sentiment từ:
Positive, Neutral, Negative, Mixed.


Chỉ được chọn call_outcome từ:
Interested, Follow-up, Won, Lost, No answer, Unknown.
""".strip()


    response = _create_summary_completion(
        client=client,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


    raw_text = (
        response.choices[0]
        .message.content
        .strip()
    )


    result = _extract_json(raw_text)


    sentiment = _normalize_enum(
        value=result.get("sentiment"),
        allowed_values=ALLOWED_SENTIMENTS,
        default="Neutral",
    )


    call_outcome = _normalize_enum(
        value=result.get("call_outcome"),
        allowed_values=ALLOWED_OUTCOMES,
        default="Unknown",
    )


    return {
        "summary": str(
            result.get("summary") or ""
        ).strip(),
        "customer_need": str(
            result.get("customer_need") or ""
        ).strip(),
        "sentiment": sentiment,
        "call_outcome": call_outcome,
        "action_items": _normalize_string_list(
            result.get("action_items")
        ),
        "important_points": _normalize_string_list(
            result.get("important_points")
        ),
        "next_follow_up": result.get(
            "next_follow_up"
        ),
        "quality_notes": str(
            result.get("quality_notes") or ""
        ).strip(),
        "raw": result,
    }


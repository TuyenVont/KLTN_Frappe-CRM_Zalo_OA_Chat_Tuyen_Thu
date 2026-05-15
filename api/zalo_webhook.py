import hashlib
import json
from datetime import datetime
from urllib.parse import unquote_plus


import frappe
from frappe.utils import now_datetime




INBOUND_EVENTS = {
    "user_send_text",
    "user_send_image",
    "user_send_file",
    "user_send_link",
    "user_send_location",
    "user_send_sticker",


    # Để tương thích nếu payload thật dùng tên event tổng quát hơn
    "user_send_message",
}


OUTBOUND_EVENTS = {
    "oa_send_text",
    "oa_send_image",
    "oa_send_file",
    "oa_send_message",
}




@frappe.whitelist(allow_guest=True)
def receive():
    """
    Webhook endpoint nhận dữ liệu từ Zalo OA hoặc payload giả lập.


    Endpoint:
    /api/method/zalo_oa_crm.api.zalo_webhook.receive


    Method:
    POST


    Mục tiêu:
    - nhận payload JSON
    - verify signature nếu bật cấu hình
    - normalize payload
    - tạo/cập nhật Customer, Conversation, Message
    - chống trùng zalo_message_id
    - lưu raw_payload để debug
    """


    raw_body = frappe.local.request.get_data(as_text=True) or ""


    # Một số hệ thống webhook có thể gọi GET để kiểm tra endpoint.
    # Zalo OA chủ yếu dùng POST event, nhưng trả OK cho GET giúp dễ test browser.
    if frappe.local.request.method == "GET":
        return {
            "ok": True,
            "message": "Zalo OA webhook endpoint is alive"
        }


    if not raw_body:
        frappe.local.response["http_status_code"] = 400
        return {
            "ok": False,
            "error": "Empty request body"
        }


    try:
        payload = json.loads(raw_body)
    except Exception as e:
        frappe.local.response["http_status_code"] = 400
        return {
            "ok": False,
            "error": f"Invalid JSON: {str(e)}"
        }


    if should_verify_signature():
        verify_result = verify_zalo_signature(raw_body, payload)
        if not verify_result.get("ok"):
            frappe.local.response["http_status_code"] = 401
            return verify_result


    result = process_payload(payload)


    frappe.db.commit()


    return result




@frappe.whitelist()
def simulate_message(
    zalo_user_id="zalo-user-001",
    customer_name="Nguyễn Văn An",
    text="Shop còn hàng không?",
    msg_id=None
):
    """
    Hàm giả lập khách nhắn Zalo OA.
    Dùng demo nhanh, chưa cần Zalo OA thật.
    """


    text = unquote_plus(text or "")
    customer_name = unquote_plus(customer_name or "")


    if not msg_id:
        msg_id = f"mock-{frappe.generate_hash(length=10)}"


    payload = {
        "app_id": "demo-app-id",
        "event_name": "user_send_text",
        "sender": {
            "id": zalo_user_id,
            "name": customer_name
        },
        "recipient": {
            "id": "demo-oa-id"
        },
        "message": {
            "text": text,
            "msg_id": msg_id
        },
        "timestamp": int(datetime.now().timestamp() * 1000),
        "source": "simulate_message"
    }


    result = process_payload(payload)


    frappe.db.commit()


    return result




def process_payload(payload):
    """
    Xử lý payload sau khi parse JSON.
    """


    normalized = normalize_payload(payload)


    event_name = normalized.get("event_name")
    zalo_user_id = normalized.get("zalo_user_id")
    customer_display_name = normalized.get("customer_display_name")
    msg_id = normalized.get("msg_id")
    content = normalized.get("content")
    sent_at = normalized.get("sent_at")
    sender_type = normalized.get("sender_type")
    message_type = normalized.get("message_type")
    delivery_status = normalized.get("delivery_status")


    log_name = create_webhook_log(
        payload=payload,
        status="Received",
        event_name=event_name,
        zalo_user_id=zalo_user_id,
        message_id=msg_id
    )


    try:
        if event_name not in INBOUND_EVENTS and event_name not in OUTBOUND_EVENTS:
            update_webhook_log(
                log_name,
                status="Ignored",
                error_message=f"Unsupported event_name: {event_name}"
            )
            return {
                "ok": True,
                "ignored": True,
                "reason": f"Unsupported event_name: {event_name}"
            }


        if not zalo_user_id:
            raise Exception("Missing Zalo user id")


        if not msg_id:
            msg_id = build_fallback_message_id(payload, event_name, zalo_user_id)


        customer_name = get_or_create_customer(
            zalo_user_id=zalo_user_id,
            customer_display_name=customer_display_name
        )


        conversation_name = get_or_create_conversation(
            customer_name=customer_name,
            content=content,
            sent_at=sent_at
        )


        message_result = create_message_if_not_exists(
            conversation_name=conversation_name,
            customer_name=customer_name,
            sender_type=sender_type,
            message_type=message_type,
            content=content,
            sent_at=sent_at,
            msg_id=msg_id,
            delivery_status=delivery_status,
            is_read=1 if sender_type in ("Agent", "OA") else 0,
            payload=payload
        )


        if message_result.get("duplicate"):
            update_webhook_log(
                log_name,
                status="Duplicate",
                related_customer=customer_name,
                related_conversation=conversation_name,
                related_message=message_result.get("message"),
                error_message="Duplicate zalo_message_id"
            )
            return {
                "ok": True,
                "duplicate": True,
                "customer": customer_name,
                "conversation": conversation_name,
                "message": message_result.get("message")
            }


        update_conversation_summary(
            conversation_name=conversation_name,
            content=content,
            sent_at=sent_at,
            sender_type=sender_type
        )


        update_webhook_log(
            log_name,
            status="Processed",
            related_customer=customer_name,
            related_conversation=conversation_name,
            related_message=message_result.get("message")
        )


        return {
            "ok": True,
            "customer": customer_name,
            "conversation": conversation_name,
            "message": message_result.get("message"),
            "event_name": event_name,
            "zalo_user_id": zalo_user_id,
            "sender_type": sender_type
        }


    except Exception as e:
        update_webhook_log(
            log_name,
            status="Failed",
            error_message=str(e)
        )


        frappe.log_error(
            title="Zalo OA Webhook Failed",
            message=frappe.get_traceback()
        )


        frappe.local.response["http_status_code"] = 500


        return {
            "ok": False,
            "error": str(e)
        }




def normalize_payload(payload):
    """
    Chuyển payload từ Zalo/mock về format nội bộ thống nhất.


    Inbound:
    - khách gửi đến OA
    - sender là customer


    Outbound:
    - OA/agent gửi cho khách
    - recipient thường là customer
    """


    event_name = payload.get("event_name") or payload.get("event")
    sender = payload.get("sender") or {}
    recipient = payload.get("recipient") or {}
    message = payload.get("message") or {}
    data = payload.get("data") or {}


    timestamp = payload.get("timestamp") or data.get("timestamp")
    sent_at = parse_zalo_timestamp(timestamp)


    is_outbound = event_name in OUTBOUND_EVENTS or str(event_name or "").startswith("oa_")


    if is_outbound:
        zalo_user_id = (
            recipient.get("id")
            or recipient.get("user_id")
            or data.get("user_id")
            or payload.get("user_id")
        )
        customer_display_name = recipient.get("name") or data.get("user_name")
        sender_type = "OA"
        delivery_status = "Sent"
    else:
        zalo_user_id = (
            sender.get("id")
            or sender.get("user_id")
            or data.get("user_id")
            or payload.get("user_id")
        )
        customer_display_name = sender.get("name") or data.get("user_name")
        sender_type = "Customer"
        delivery_status = "Received"


    msg_id = (
        message.get("msg_id")
        or message.get("message_id")
        or data.get("msg_id")
        or data.get("message_id")
        or payload.get("msg_id")
        or payload.get("message_id")
    )


    content = extract_content(event_name, message, data)
    message_type = map_message_type(event_name, message, data)


    return {
        "event_name": event_name,
        "zalo_user_id": zalo_user_id,
        "customer_display_name": customer_display_name,
        "msg_id": msg_id,
        "content": content,
        "sent_at": sent_at,
        "sender_type": sender_type,
        "message_type": message_type,
        "delivery_status": delivery_status
    }




def get_or_create_customer(zalo_user_id, customer_display_name=None):
    existing = frappe.db.exists(
        "Zalo OA Customer",
        {
            "zalo_user_id": zalo_user_id
        }
    )


    if existing:
        customer = frappe.get_doc("Zalo OA Customer", existing)


        if customer_display_name and (
            not customer.customer_name
            or str(customer.customer_name).startswith("Zalo User")
        ):
            customer.customer_name = customer_display_name
            customer.save(ignore_permissions=True)


        return existing


    customer = frappe.get_doc({
        "doctype": "Zalo OA Customer",
        "zalo_user_id": zalo_user_id,
        "customer_name": customer_display_name or f"Zalo User {zalo_user_id}",
        "phone": "",
        "avatar_url": "",
        "source": "Zalo OA",
        "customer_status": "New",
        "tags": "ZaloOA, Webhook"
    })


    customer.insert(ignore_permissions=True)


    return customer.name




def get_or_create_conversation(customer_name, content, sent_at):
    conversations = frappe.get_all(
        "Zalo OA Conversation",
        filters=[
            ["customer", "=", customer_name],
            ["conversation_status", "!=", "Closed"]
        ],
        fields=["name"],
        order_by="last_message_at desc",
        limit=1
    )


    if conversations:
        return conversations[0].name


    customer = frappe.get_doc("Zalo OA Customer", customer_name)


    conversation = frappe.get_doc({
        "doctype": "Zalo OA Conversation",
        "customer": customer_name,
        "conversation_title": f"Chat với {customer.customer_name}",
        "last_message": content,
        "last_message_at": sent_at,
        "unread_count": 0,
        "conversation_status": "Open",
        "topic": guess_topic(content),
        "linked_deal": ""
    })


    conversation.insert(ignore_permissions=True)


    return conversation.name




def create_message_if_not_exists(
    conversation_name,
    customer_name,
    sender_type,
    message_type,
    content,
    sent_at,
    msg_id,
    delivery_status,
    is_read,
    payload
):
    existing = frappe.db.exists(
        "Zalo OA Message",
        {
            "zalo_message_id": msg_id
        }
    )


    if existing:
        return {
            "duplicate": True,
            "message": existing
        }


    message = frappe.get_doc({
        "doctype": "Zalo OA Message",
        "conversation": conversation_name,
        "customer": customer_name,
        "sender_type": sender_type,
        "message_type": message_type,
        "content": content,
        "sent_at": sent_at,
        "zalo_message_id": msg_id,
        "delivery_status": delivery_status,
        "is_read": is_read,
        "raw_payload": json.dumps(payload, ensure_ascii=False)
    })


    message.insert(ignore_permissions=True)


    return {
        "duplicate": False,
        "message": message.name
    }




def update_conversation_summary(conversation_name, content, sent_at, sender_type):
    conversation = frappe.get_doc("Zalo OA Conversation", conversation_name)


    conversation.last_message = content
    conversation.last_message_at = sent_at


    if sender_type == "Customer":
        conversation.unread_count = (conversation.unread_count or 0) + 1


    if sender_type in ("Agent", "OA"):
        # Khi agent/OA trả lời, không tăng unread.
        # Có thể set Pending/Resolved tùy quy trình chăm sóc khách hàng.
        if not conversation.conversation_status:
            conversation.conversation_status = "Open"


    if not conversation.conversation_status:
        conversation.conversation_status = "Open"


    if not conversation.topic:
        conversation.topic = guess_topic(content)


    conversation.save(ignore_permissions=True)




def extract_content(event_name, message, data=None):
    data = data or {}


    text = (
        message.get("text")
        or data.get("text")
        or message.get("content")
        or data.get("content")
    )


    if text:
        return text


    attachment = message.get("attachment") or data.get("attachment") or {}
    payload = attachment.get("payload") or {}


    url = (
        message.get("url")
        or data.get("url")
        or payload.get("url")
        or payload.get("href")
    )


    title = (
        message.get("title")
        or data.get("title")
        or payload.get("title")
        or payload.get("name")
    )


    if event_name in ("user_send_image", "oa_send_image"):
        return "[Hình ảnh] " + (url or title or "")


    if event_name in ("user_send_file", "oa_send_file"):
        return "[File] " + (url or title or "")


    if event_name == "user_send_link":
        return "[Link] " + (url or title or "")


    if event_name == "user_send_location":
        return "[Vị trí] " + json.dumps(message or data, ensure_ascii=False)


    if event_name == "user_send_sticker":
        return "[Sticker]"


    return json.dumps(message or data, ensure_ascii=False)




def map_message_type(event_name, message=None, data=None):
    event_name = event_name or ""
    message = message or {}
    data = data or {}


    attachment = message.get("attachment") or data.get("attachment") or {}
    attachment_type = attachment.get("type") or message.get("type") or data.get("type")


    if "image" in event_name or attachment_type == "image":
        return "Image"


    if "file" in event_name or attachment_type == "file":
        return "File"


    if "sticker" in event_name or attachment_type == "sticker":
        return "Sticker" if is_select_option_allowed("Zalo OA Message", "message_type", "Sticker") else "Text"


    return "Text"




def parse_zalo_timestamp(timestamp):
    if not timestamp:
        return now_datetime()


    try:
        if isinstance(timestamp, int) or str(timestamp).isdigit():
            ts = int(timestamp)


            # Zalo thường dùng milliseconds.
            if ts > 10_000_000_000:
                ts = ts / 1000


            return datetime.fromtimestamp(ts)


        return frappe.utils.get_datetime(timestamp)


    except Exception:
        return now_datetime()




def guess_topic(content):
    text = (content or "").lower()


    if "giá" in text or "báo giá" in text or "bao nhiêu" in text:
        return "Báo giá"


    if "ship" in text or "giao" in text or "vận chuyển" in text:
        return "Vận chuyển"


    if "bảo hành" in text or "lỗi" in text:
        return "Bảo hành"


    if "khiếu nại" in text or "không hài lòng" in text:
        return "Khiếu nại"


    return "Tư vấn sản phẩm"




def build_fallback_message_id(payload, event_name, zalo_user_id):
    timestamp = payload.get("timestamp") or now_datetime().strftime("%Y%m%d%H%M%S%f")
    raw = f"{event_name}-{zalo_user_id}-{timestamp}-{json.dumps(payload, ensure_ascii=False)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()




def should_verify_signature():
    """
    Trong giai đoạn demo local, để False.
    Khi dùng OA thật, bật bằng site_config hoặc Zalo OA Settings.
    """


    value = get_zalo_setting("verify_signature", default=0)


    return str(value).lower() in ("1", "true", "yes")




def verify_zalo_signature(raw_body, payload):
    """
    Verify X-ZEvent-Signature.


    Theo tài liệu Zalo webhook, signature dùng SHA256 trên chuỗi gồm:
    appId + data + timeStamp + OAsecretKey.


    Lưu ý:
    - Tên header/timestamp có thể khác theo phiên bản tài liệu.
    - Vì vậy hàm này đọc signature từ X-ZEvent-Signature,
      timestamp từ payload.timestamp.
    - Khi test local bằng Postman chưa ký, hãy tắt verify_signature.
    """


    signature = (
        frappe.local.request.headers.get("X-ZEvent-Signature")
        or frappe.local.request.headers.get("x-zevent-signature")
        or ""
    )


    if not signature:
        return {
            "ok": False,
            "error": "Missing X-ZEvent-Signature"
        }


    signature = signature.replace("mac=", "").strip()


    app_id = str(payload.get("app_id") or get_zalo_setting("app_id", default=""))
    timestamp = str(payload.get("timestamp") or "")
    oa_secret_key = str(get_zalo_setting("oa_secret_key", default=""))


    if not app_id or not timestamp or not oa_secret_key:
        return {
            "ok": False,
            "error": "Missing app_id, timestamp, or oa_secret_key for signature verification"
        }


    content = f"{app_id}{raw_body}{timestamp}{oa_secret_key}"
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()


    if expected != signature:
        return {
            "ok": False,
            "error": "Invalid Zalo webhook signature"
        }


    return {
        "ok": True
    }




def get_zalo_setting(fieldname, default=None):
    """
    Đọc cấu hình từ:
    1. site_config.json
    2. Single DocType Zalo OA Settings nếu bạn tạo sau này
    """


    site_config_value = frappe.conf.get(f"zalo_oa_{fieldname}")
    if site_config_value is not None:
        return site_config_value


    if frappe.db.exists("DocType", "Zalo OA Settings"):
        try:
            settings = frappe.get_single("Zalo OA Settings")
            if hasattr(settings, "get_password") and fieldname in (
                "access_token",
                "refresh_token",
                "app_secret",
                "oa_secret_key"
            ):
                value = settings.get_password(fieldname)
            else:
                value = settings.get(fieldname)


            if value is not None:
                return value
        except Exception:
            pass


    return default




def create_webhook_log(payload, status, event_name=None, zalo_user_id=None, message_id=None):
    if not frappe.db.exists("DocType", "Zalo OA Webhook Log"):
        return None


    log = frappe.get_doc({
        "doctype": "Zalo OA Webhook Log",
        "event_name": event_name or "",
        "zalo_user_id": zalo_user_id or "",
        "message_id": message_id or "",
        "status": status,
        "pay_load": json.dumps(payload, ensure_ascii=False, indent=2),
        "processed_at": now_datetime()
    })


    log.insert(ignore_permissions=True)


    return log.name




def update_webhook_log(
    log_name,
    status,
    error_message=None,
    related_customer=None,
    related_conversation=None,
    related_message=None
):
    if not log_name:
        return


    log = frappe.get_doc("Zalo OA Webhook Log", log_name)


    log.status = status
    log.processed_at = now_datetime()


    if error_message:
        log.error_message = error_message


    if related_customer:
        log.related_customer = related_customer


    if related_conversation:
        log.related_conversation = related_conversation


    if related_message:
        log.related_message = related_message


    log.save(ignore_permissions=True)




def is_select_option_allowed(doctype, fieldname, value):
    meta = frappe.get_meta(doctype)
    field = meta.get_field(fieldname)


    if not field or not field.options:
        return False


    options = [x.strip() for x in field.options.split("\n") if x.strip()]
    return value in options




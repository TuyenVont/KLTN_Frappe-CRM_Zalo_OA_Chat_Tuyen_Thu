import frappe
from frappe.utils import now_datetime


CUSTOMER_DT = "Zalo OA Customer"
CONVERSATION_DT = "Zalo OA Conversation"
MESSAGE_DT = "Zalo OA Message"


def normalize_ref(doctype=None, docname=None, doc_name=None, reference_doctype=None, reference_name=None):
    final_doctype = reference_doctype or doctype
    final_docname = reference_name or docname or doc_name

    if final_doctype in ["Lead", "lead", "CRM Lead"]:
        final_doctype = "CRM Lead"

    if final_doctype in ["Deal", "deal", "CRM Deal"]:
        final_doctype = "CRM Deal"

    return final_doctype, final_docname


def get_link_field(doctype):
    if not doctype:
        frappe.throw("Thiếu doctype.")

    if "lead" in doctype.lower():
        return "linked_lead"

    return "linked_deal"


def get_or_create_customer(doctype, docname, user_id=None, display_name=None, phone=None):
    link_field = get_link_field(doctype)

    customer = frappe.db.get_value(
        CUSTOMER_DT,
        {link_field: docname},
        "name"
    )

    if customer:
        return customer

    if user_id:
        customer = frappe.db.get_value(
            CUSTOMER_DT,
            {"zalo_user_id": user_id},
            "name"
        )

        if customer:
            frappe.db.set_value(CUSTOMER_DT, customer, link_field, docname)
            frappe.db.commit()
            return customer

    customer_doc = frappe.get_doc({
        "doctype": CUSTOMER_DT,
        "zalo_user_id": user_id or f"postman-{docname}",
        "customer_name": display_name or "Khách hàng Zalo",
        "phone": phone or "",
        "source": "Zalo OA",
        "customer_status": "Active",
        link_field: docname
    })

    customer_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return customer_doc.name


def get_or_create_conversation(customer, first_message=None):
    conversation = frappe.db.get_value(
        CONVERSATION_DT,
        {"customer": customer},
        "name"
    )

    if conversation:
        return conversation

    customer_name = frappe.db.get_value(
        CUSTOMER_DT,
        customer,
        "customer_name"
    ) or "Khách hàng"

    conv_doc = frappe.get_doc({
        "doctype": CONVERSATION_DT,
        "customer": customer,
        "conversation_title": f"Chat với {customer_name}",
        "last_message": first_message or "",
        "last_message_at": now_datetime(),
        "unread_count": 0,
        "conversation_status": "Open",
        "topic": "Tư vấn sản phẩm"
    })

    conv_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return conv_doc.name


def create_message(customer, conversation, sender_type, content, delivery_status):
    if not content or not str(content).strip():
        frappe.throw("Nội dung tin nhắn không được để trống.")

    content = str(content).strip()

    msg_doc = frappe.get_doc({
        "doctype": MESSAGE_DT,
        "conversation": conversation,
        "customer": customer,
        "sender_type": sender_type,
        "message_type": "Text",
        "content": content,
        "sent_at": now_datetime(),
        "zalo_message_id": f"msg-{frappe.generate_hash(length=12)}",
        "delivery_status": delivery_status,
        "is_read": 1 if sender_type == "Agent" else 0,
        "raw_payload": frappe.as_json({
            "source": "frappe_crm" if sender_type == "Agent" else "postman_simulation"
        })
    })

    msg_doc.insert(ignore_permissions=True)

    unread_count = 0
    if sender_type == "Customer":
        unread_count = frappe.db.count(
            MESSAGE_DT,
            {
                "conversation": conversation,
                "sender_type": "Customer",
                "is_read": 0
            }
        )

    frappe.db.set_value(
        CONVERSATION_DT,
        conversation,
        {
            "last_message": content,
            "last_message_at": now_datetime(),
            "unread_count": unread_count
        }
    )

    frappe.db.commit()

    return msg_doc


@frappe.whitelist()
def get_chat_history(doctype=None, docname=None, doc_name=None, reference_doctype=None, reference_name=None):
    doctype, docname = normalize_ref(
        doctype=doctype,
        docname=docname,
        doc_name=doc_name,
        reference_doctype=reference_doctype,
        reference_name=reference_name
    )

    if not doctype or not docname:
        frappe.throw("Thiếu doctype/docname.")

    link_field = get_link_field(doctype)

    customer = frappe.db.get_value(
        CUSTOMER_DT,
        {link_field: docname},
        "name"
    )

    if not customer:
        return {
            "ok": True,
            "status": "empty",
            "messages": [],
            "customer": None,
            "conversation": None
        }

    customer_name = frappe.db.get_value(CUSTOMER_DT, customer, "customer_name")
    zalo_user_id = frappe.db.get_value(CUSTOMER_DT, customer, "zalo_user_id")

    conversation = frappe.db.get_value(
        CONVERSATION_DT,
        {"customer": customer},
        "name"
    )

    if not conversation:
        return {
            "ok": True,
            "status": "success",
            "messages": [],
            "customer": customer,
            "customer_name": customer_name,
            "zalo_user_id": zalo_user_id,
            "conversation": None
        }

    rows = frappe.get_all(
        MESSAGE_DT,
        filters={"conversation": conversation},
        fields=[
            "name",
            "sender_type",
            "message_type",
            "content",
            "sent_at",
            "delivery_status",
            "is_read"
        ],
        order_by="sent_at asc",
        limit_page_length=500
    )

    messages = []

    for row in rows:
        sender_type = row.get("sender_type") or ""
        is_customer = sender_type == "Customer"

        messages.append({
            "name": row.get("name"),
            "content": row.get("content") or "",
            "message": row.get("content") or "",
            "sender_type": "customer" if is_customer else "staff",
            "sender": customer_name if is_customer else "Bạn / Frappe",
            "direction": "incoming" if is_customer else "outgoing",
            "message_type": row.get("message_type") or "Text",
            "timestamp": str(row.get("sent_at") or ""),
            "sent_at": str(row.get("sent_at") or ""),
            "delivery_status": row.get("delivery_status"),
            "is_read": row.get("is_read")
        })

    return {
        "ok": True,
        "status": "success",
        "messages": messages,
        "customer": customer,
        "customer_name": customer_name,
        "zalo_user_id": zalo_user_id,
        "conversation": conversation
    }


@frappe.whitelist()
def send_message(doctype=None, docname=None, doc_name=None, reference_doctype=None, reference_name=None, message=None):
    doctype, docname = normalize_ref(
        doctype=doctype,
        docname=docname,
        doc_name=doc_name,
        reference_doctype=reference_doctype,
        reference_name=reference_name
    )

    if not doctype or not docname:
        frappe.throw("Thiếu doctype/docname.")

    if not message or not str(message).strip():
        frappe.throw("Nội dung phản hồi không được để trống.")

    customer = get_or_create_customer(
        doctype=doctype,
        docname=docname
    )

    conversation = get_or_create_conversation(
        customer=customer,
        first_message=message
    )

    msg = create_message(
        customer=customer,
        conversation=conversation,
        sender_type="Agent",
        content=message,
        delivery_status="Sent"
    )

    return {
        "ok": True,
        "status": "success",
        "message_docname": msg.name,
        "message_id": msg.zalo_message_id,
        "conversation": conversation,
        "sender_type": "staff",
        "content": message
    }


@frappe.whitelist(allow_guest=True)
def simulate_customer_message(
    doctype=None,
    docname=None,
    doc_name=None,
    reference_doctype=None,
    reference_name=None,
    user_id=None,
    zalo_user_id=None,
    display_name=None,
    phone=None,
    message=None,
    text=None,
    content=None,
    message_type="text"
):
    data = {}

    try:
        body = frappe.request.get_json(silent=True)
        if isinstance(body, dict):
            data.update(body)
    except Exception:
        pass

    try:
        data.update(dict(frappe.form_dict))
    except Exception:
        pass

    data.pop("cmd", None)

    doctype, docname = normalize_ref(
        doctype=doctype or data.get("doctype"),
        docname=docname or data.get("docname"),
        doc_name=doc_name or data.get("doc_name"),
        reference_doctype=reference_doctype or data.get("reference_doctype"),
        reference_name=reference_name or data.get("reference_name")
    )

    final_user_id = (
        user_id
        or zalo_user_id
        or data.get("user_id")
        or data.get("zalo_user_id")
        or f"postman-{docname}"
    )

    final_display_name = (
        display_name
        or data.get("display_name")
        or data.get("customer_name")
        or "Khách hàng Postman"
    )

    final_phone = phone or data.get("phone") or ""

    final_message = (
        message
        or text
        or content
        or data.get("message")
        or data.get("text")
        or data.get("content")
    )

    if not doctype or not docname:
        frappe.throw("Thiếu reference_doctype/reference_name hoặc doctype/docname.")

    if not final_message or not str(final_message).strip():
        frappe.throw("Thiếu nội dung tin nhắn.")

    customer = get_or_create_customer(
        doctype=doctype,
        docname=docname,
        user_id=final_user_id,
        display_name=final_display_name,
        phone=final_phone
    )

    conversation = get_or_create_conversation(
        customer=customer,
        first_message=final_message
    )

    msg = create_message(
        customer=customer,
        conversation=conversation,
        sender_type="Customer",
        content=final_message,
        delivery_status="Received"
    )

    return {
        "ok": True,
        "status": "success",
        "source": "postman_simulation",
        "customer": customer,
        "conversation": conversation,
        "message_docname": msg.name,
        "message_id": msg.zalo_message_id,
        "sender_type": "customer",
        "content": final_message
    }

@frappe.whitelist()
def get_sidebar_conversations(limit=100):
    """
    API cho màn hình Zalo OA tổng trên sidebar.
    Lấy toàn bộ hội thoại, bao gồm khách liên kết Lead và Deal.
    """

    try:
        limit = int(limit or 100)
    except Exception:
        limit = 100

    conversations = frappe.get_all(
        "Zalo OA Conversation",
        fields=[
            "name",
            "customer",
            "conversation_title",
            "last_message",
            "last_message_at",
            "unread_count",
            "conversation_status",
            "topic",
        ],
        order_by="last_message_at desc",
        limit_page_length=limit,
    )

    result = []

    for conv in conversations:
        customer_name = conv.get("customer")

        if not customer_name or not frappe.db.exists("Zalo OA Customer", customer_name):
            continue

        customer = frappe.db.get_value(
            "Zalo OA Customer",
            customer_name,
            [
                "name",
                "customer_name",
                "phone",
                "zalo_user_id",
                "avatar_url",
                "customer_status",
                "linked_lead",
                "linked_deal",
            ],
            as_dict=True,
        )

        linked_doctype = None
        linked_name = None
        linked_route = None

        if customer.get("linked_lead"):
            linked_doctype = "Lead"
            linked_name = customer.get("linked_lead")
            linked_route = f"/crm/leads/{linked_name}"

        elif customer.get("linked_deal"):
            linked_doctype = "Deal"
            linked_name = customer.get("linked_deal")
            linked_route = f"/crm/deals/{linked_name}"

        result.append({
            "name": conv.get("name"),
            "customer": customer_name,
            "customer_name": customer.get("customer_name") or "Khách Zalo",
            "phone": customer.get("phone") or "",
            "zalo_user_id": customer.get("zalo_user_id") or "",
            "avatar_url": customer.get("avatar_url") or "",
            "customer_status": customer.get("customer_status") or "",
            "conversation_title": conv.get("conversation_title") or "",
            "last_message": conv.get("last_message") or "",
            "last_message_at": str(conv.get("last_message_at") or ""),
            "unread_count": conv.get("unread_count") or 0,
            "conversation_status": conv.get("conversation_status") or "",
            "topic": conv.get("topic") or "",
            "linked_doctype": linked_doctype,
            "linked_name": linked_name,
            "linked_route": linked_route,
            "linked_lead": customer.get("linked_lead"),
            "linked_deal": customer.get("linked_deal"),
        })

    return {
        "ok": True,
        "conversations": result,
    }


@frappe.whitelist()
def get_sidebar_messages(conversation):
    """
    API lấy tin nhắn theo conversation cho màn hình Zalo OA tổng.
    """

    if not conversation:
        frappe.throw("Thiếu conversation.")

    if not frappe.db.exists("Zalo OA Conversation", conversation):
        frappe.throw("Conversation không tồn tại.")

    rows = frappe.get_all(
        "Zalo OA Message",
        filters={"conversation": conversation},
        fields=[
            "name",
            "conversation",
            "customer",
            "sender_type",
            "message_type",
            "content",
            "sent_at",
            "zalo_message_id",
            "delivery_status",
            "is_read",
        ],
        order_by="sent_at asc",
        limit_page_length=500,
    )

    messages = []

    for row in rows:
        is_customer = row.get("sender_type") == "Customer"

        messages.append({
            "name": row.get("name"),
            "conversation": row.get("conversation"),
            "customer": row.get("customer"),
            "sender_type": "customer" if is_customer else "staff",
            "direction": "incoming" if is_customer else "outgoing",
            "message_type": row.get("message_type") or "Text",
            "content": row.get("content") or "",
            "message": row.get("content") or "",
            "sent_at": str(row.get("sent_at") or ""),
            "timestamp": str(row.get("sent_at") or ""),
            "zalo_message_id": row.get("zalo_message_id"),
            "delivery_status": row.get("delivery_status"),
            "is_read": row.get("is_read"),
        })

    frappe.db.sql(
        """
        UPDATE `tabZalo OA Message`
        SET is_read = 1
        WHERE conversation = %s AND sender_type = 'Customer'
        """,
        conversation,
    )

    frappe.db.set_value("Zalo OA Conversation", conversation, "unread_count", 0)
    frappe.db.commit()

    return {
        "ok": True,
        "messages": messages,
    }


@frappe.whitelist()
def send_sidebar_message(conversation, message):
    """
    Gửi tin nhắn ngay trong màn hình Zalo OA tổng.
    Không cần doctype/docname, chỉ cần conversation.
    """

    if not conversation:
        frappe.throw("Thiếu conversation.")

    if not message or not str(message).strip():
        frappe.throw("Nội dung phản hồi không được để trống.")

    conv = frappe.get_doc("Zalo OA Conversation", conversation)

    if not conv.customer:
        frappe.throw("Conversation chưa liên kết Zalo OA Customer.")

    content = str(message).strip()

    msg_doc = frappe.get_doc({
        "doctype": "Zalo OA Message",
        "conversation": conversation,
        "customer": conv.customer,
        "sender_type": "Agent",
        "message_type": "Text",
        "content": content,
        "sent_at": now_datetime(),
        "zalo_message_id": f"msg-sidebar-{frappe.generate_hash(length=10)}",
        "delivery_status": "Sent",
        "is_read": 1,
        "raw_payload": frappe.as_json({
            "source": "zalo_oa_sidebar"
        }),
    })

    msg_doc.insert(ignore_permissions=True)

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        {
            "last_message": content,
            "last_message_at": now_datetime(),
        },
    )

    frappe.db.commit()

    return {
        "ok": True,
        "status": "success",
        "conversation": conversation,
        "message_docname": msg_doc.name,
        "message_id": msg_doc.zalo_message_id,
        "content": content,
    }
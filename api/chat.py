import frappe
from frappe.utils import get_datetime, now_datetime




def create_or_get_customer(item):
    existing_customer = frappe.db.exists(
        "Zalo OA Customer",
        {
            "zalo_user_id": item["zalo_user_id"]
        }
    )


    if existing_customer:
        return existing_customer


    customer = frappe.get_doc({
        "doctype": "Zalo OA Customer",
        "zalo_user_id": item["zalo_user_id"],
        "customer_name": item["customer_name"],
        "phone": item["phone"],
        "avatar_url": item["avatar_url"],
        "source": "Zalo OA",
        "customer_status": item["customer_status"],
        "tags": item["tags"],
    })


    customer.insert(ignore_permissions=True)


    return customer.name




def create_or_get_conversation(customer_name, item):
    existing_conversation = frappe.db.exists(
        "Zalo OA Conversation",
        {
            "customer": customer_name
        }
    )


    if existing_conversation:
        return existing_conversation


    conversation = frappe.get_doc({
        "doctype": "Zalo OA Conversation",
        "customer": customer_name,
        "conversation_title": f"Chat với {item['customer_name']}",
        "last_message": item["last_message"],
        "last_message_at": get_datetime(item["last_message_at"]),
        "unread_count": item["unread_count"],
        "conversation_status": "Open",
        "topic": item["topic"],
        "linked_deal": item.get("linked_deal") or "",
    })


    conversation.insert(ignore_permissions=True)


    return conversation.name




def create_message_if_not_exists(conversation_name, customer_name, item, index, msg):
    sender_type, content, sent_at, status = msg
    zalo_message_id = f"mock-{item['zalo_user_id']}-{index + 1}"


    if frappe.db.exists("Zalo OA Message", {"zalo_message_id": zalo_message_id}):
        return None


    message = frappe.get_doc({
        "doctype": "Zalo OA Message",
        "conversation": conversation_name,
        "customer": customer_name,
        "sender_type": sender_type,
        "message_type": "Text",
        "content": content,
        "sent_at": get_datetime(sent_at),
        "zalo_message_id": zalo_message_id,
        "delivery_status": status,
        "is_read": 1 if sender_type == "Agent" else 0,
        "raw_payload": frappe.as_json({
            "source": "mock",
            "zalo_user_id": item["zalo_user_id"],
        }),
    })


    message.insert(ignore_permissions=True)


    return message.name




@frappe.whitelist()
def test_create_customer():
    item = {
        "zalo_user_id": "84909123456",
        "customer_name": "Nguyễn Văn An",
        "phone": "0909123456",
        "avatar_url": "https://i.pravatar.cc/100?img=1",
        "customer_status": "Active",
        "tags": "ZaloOA, Khách mới, Quan tâm SP A",
    }


    customer_name = create_or_get_customer(item)


    frappe.db.commit()


    return {
        "ok": True,
        "message": "Customer created successfully",
        "customer": customer_name,
    }




@frappe.whitelist()
def seed_mock_data():
    customers = [
        {
            "zalo_user_id": "84909123456",
            "customer_name": "Nguyễn Văn An",
            "phone": "+84909123456",
            "avatar_url": "https://i.pravatar.cc/100?img=1",
            "customer_status": "Active",
            "tags": "ZaloOA, Khách mới, Quan tâm SP A",
            "topic": "Tư vấn sản phẩm",
            "linked_deal": "DEAL-0007",
            "last_message": "Màu đen, ship HCM bao lâu?",
            "last_message_at": "2026-05-12 09:18:00",
            "unread_count": 2,
            "messages": [
                ("Customer", "Shop còn mẫu này không ạ?", "2026-05-12 09:15:00", "Received"),
                ("Agent", "Dạ còn ạ. Anh/chị muốn lấy màu nào để em kiểm kho?", "2026-05-12 09:16:00", "Delivered"),
                ("Customer", "Màu đen, ship HCM bao lâu?", "2026-05-12 09:18:00", "Received"),
            ],
        },
        {
            "zalo_user_id": "84918123456",
            "customer_name": "Trần Thị Bình",
            "phone": "+84918123456",
            "avatar_url": "https://i.pravatar.cc/100?img=5",
            "customer_status": "Active",
            "tags": "ZaloOA, Báo giá, Tiềm năng",
            "topic": "Báo giá",
            "linked_deal": "DEAL-0011",
            "last_message": "Cho mình xin báo giá combo nhé",
            "last_message_at": "2026-05-11 16:42:00",
            "unread_count": 0,
            "messages": [
                ("Customer", "Shop có combo cho doanh nghiệp không?", "2026-05-11 16:30:00", "Received"),
                ("Agent", "Dạ có ạ. Chị cần khoảng bao nhiêu bộ?", "2026-05-11 16:35:00", "Delivered"),
                ("Customer", "Cho mình xin báo giá combo nhé", "2026-05-11 16:42:00", "Received"),
            ],
        },
        {
            "zalo_user_id": "+4977123456",
            "customer_name": "Lê Hoàng Minh",
            "phone": "+84977123456",
            "avatar_url": "https://i.pravatar.cc/100?img=8",
            "customer_status": "New",
            "tags": "ZaloOA, Bảo hành",
            "topic": "Bảo hành",
            "linked_deal": "",
            "last_message": "Sản phẩm của mình bị lỗi thì bảo hành sao?",
            "last_message_at": "2026-05-10 14:20:00",
            "unread_count": 1,
            "messages": [
                ("Customer", "Sản phẩm của mình bị lỗi thì bảo hành sao?", "2026-05-10 14:20:00", "Received"),
            ],
        },
    ]


    created = []


    for item in customers:
        customer_name = create_or_get_customer(item)
        conversation_name = create_or_get_conversation(customer_name, item)


        for index, msg in enumerate(item["messages"]):
            create_message_if_not_exists(
                conversation_name=conversation_name,
                customer_name=customer_name,
                item=item,
                index=index,
                msg=msg,
            )


        created.append({
            "customer": customer_name,
            "conversation": conversation_name,
        })


    frappe.db.commit()


    return {
        "ok": True,
        "message": "Seed mock data completed",
        "created": created,
    }




@frappe.whitelist()
def get_conversations(search=None, status=None, topic=None):
    filters = {}


    if status and status != "All":
        filters["conversation_status"] = status


    if topic and topic != "All":
        filters["topic"] = topic


    conversations = frappe.get_all(
        "Zalo OA Conversation",
        filters=filters,
        fields=[
            "name",
            "customer",
            "conversation_title",
            "last_message",
            "last_message_at",
            "unread_count",
            "conversation_status",
            "topic",
            "linked_deal",
        ],
        order_by="last_message_at desc"
    )


    result = []


    for conv in conversations:
        customer = frappe.get_doc("Zalo OA Customer", conv.customer)


        if search:
            keyword = search.lower()
            text = f"{customer.customer_name} {customer.phone or ''} {customer.zalo_user_id or ''}".lower()


            if keyword not in text:
                continue


        result.append({
            "name": conv.name,
            "customer": conv.customer,
            "customer_name": customer.customer_name,
            "phone": customer.phone,
            "zalo_user_id": customer.zalo_user_id,
            "avatar_url": customer.avatar_url,
            "tags": customer.tags,
            "conversation_title": conv.conversation_title,
            "last_message": conv.last_message,
            "last_message_at": conv.last_message_at,
            "unread_count": conv.unread_count,
            "conversation_status": conv.conversation_status,
            "topic": conv.topic,
            "linked_deal": conv.linked_deal,
            "customer_status": customer.customer_status,
            "linked_lead": getattr(customer, "linked_lead", None),
            "linked_contact": getattr(customer, "linked_contact", None),
        })


    return result




@frappe.whitelist()
def get_messages(conversation):
    if not conversation:
        frappe.throw("Missing conversation")


    messages = frappe.get_all(
        "Zalo OA Message",
        filters={
            "conversation": conversation
        },
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
        order_by="sent_at asc"
    )


    return messages




@frappe.whitelist()
def send_mock_message(conversation, content):
    if not conversation:
        frappe.throw("Missing conversation")


    if not content:
        frappe.throw("Missing content")


    conv = frappe.get_doc("Zalo OA Conversation", conversation)


    message = frappe.get_doc({
        "doctype": "Zalo OA Message",
        "conversation": conversation,
        "customer": conv.customer,
        "sender_type": "Agent",
        "message_type": "Text",
        "content": content,
        "sent_at": now_datetime(),
        "zalo_message_id": f"mock-agent-{frappe.generate_hash(length=10)}",
        "delivery_status": "Sent",
        "is_read": 1,
        "raw_payload": frappe.as_json({
            "source": "mock_send_from_crm"
        }),
    })


    message.insert(ignore_permissions=True)


    conv.last_message = content
    conv.last_message_at = message.sent_at
    conv.save(ignore_permissions=True)


    frappe.db.commit()


    return {
        "ok": True,
        "message": message.name,
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        frappe.throw("Missing conversation")

    frappe.db.sql(
        """
        update `tabZalo OA Message`
        set is_read = 1
        where conversation = %s
          and sender_type = 'Customer'
        """,
        conversation
    )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        "unread_count",
        0
    )

    frappe.db.commit()

    return {
        "ok": True
    }


@frappe.whitelist()
def send_mock_reply(conversation, text):
    """
    Alias cho giao diện Zalo OA Chat mới.
    JS gọi send_mock_reply(conversation, text),
    còn backend cũ đang có send_mock_message(conversation, content).
    """
    return send_mock_message(conversation=conversation, content=text)

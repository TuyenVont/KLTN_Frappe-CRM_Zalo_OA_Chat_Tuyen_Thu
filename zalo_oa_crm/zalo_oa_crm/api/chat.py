import frappe
from frappe.utils import get_datetime, now_datetime
# =========================================================================
# 🌟 HOOKS TỰ ĐỘNG TẠO MỚI HOẶC ĐỒNG BỘ ZALO CUSTOMER KHI CÓ LEADS / DEALS
# =========================================================================


def sync_zalo_customer_on_lead(doc, method=None):
    """
    Hook chạy sau khi tạo Lead (after_insert).
    Tự động đồng bộ thông tin sang Zalo OA Customer để chat được ngay.
    """
    lead_phone = doc.mobile_no or doc.phone
    if not lead_phone:
        return  


    lead_phone = lead_phone.strip()
    search_phone = lead_phone[-9:] if len(lead_phone) >= 9 else lead_phone


    # 1. Quét tìm khách hàng Zalo cũ theo số điện thoại hoặc ID trùng khớp
    zalo_cust_name = frappe.db.sql(
        """
        SELECT name FROM `tabZalo OA Customer`
        WHERE phone LIKE %s OR phone LIKE %s OR zalo_user_id = %s
        LIMIT 1
        """,
        (f"%{search_phone}", f"%{lead_phone}", lead_phone),
        as_dict=True
    )


    if zalo_cust_name:
        # Nếu đã có, gán mối liên kết vào Lead mới tạo
        frappe.db.set_value("Zalo OA Customer", zalo_cust_name[0].name, "linked_lead", doc.name)
    else:
        # Nếu chưa có, tự động sinh mới một bản ghi Zalo OA Customer dữ liệu thật
        new_zalo_cust = frappe.get_doc({
            "doctype": "Zalo OA Customer",
            "zalo_user_id": lead_phone,  # Tạm lấy SĐT làm định danh gửi tin
            "customer_name": doc.lead_name or f"{doc.first_name or ''} {doc.last_name or ''}".strip() or "Khách hàng mới",
            "phone": lead_phone,
            "source": "Zalo OA",
            "customer_status": "Active",
            "linked_lead": doc.name  
        })
        new_zalo_cust.insert(ignore_permissions=True)


    frappe.db.commit()
def sync_zalo_customer_on_deal(doc, method=None):
    """
    Hook chạy sau khi tạo Deal (after_insert).
    Bọc toàn bộ trong try-except để không bao giờ làm crash nút bấm Create Deal ngoài CRM.
    """
    try:
        # 1. Nếu Deal kế thừa từ Lead cũ, ưu tiên tìm mối liên kết sẵn có của Lead đó
        if getattr(doc, "lead", None):
            zalo_cust_name = frappe.db.get_value("Zalo OA Customer", {"linked_lead": doc.lead}, "name")
            if zalo_cust_name:
                frappe.db.set_value("Zalo OA Customer", zalo_cust_name, "linked_deal", doc.name)
                frappe.db.commit()
                return


        # 2. Tìm số điện thoại của Deal (Quét linh hoạt qua các trường có thể có trên form)
        deal_phone = getattr(doc, "primary_mobile_no", None) or getattr(doc, "mobile_no", None) or getattr(doc, "phone", None)
        if not deal_phone:
            return  # Không có số điện thoại thì dừng luồng, không tạo bậy


        deal_phone = str(deal_phone).strip()
        search_phone = deal_phone[-9:] if len(deal_phone) >= 9 else deal_phone
       
        # 3. Quét xem số điện thoại này đã tồn tại trong danh sách Zalo OA Customer chưa
        zalo_cust_name = frappe.db.sql(
            """
            SELECT name FROM `tabZalo OA Customer`
            WHERE phone LIKE %s OR phone LIKE %s OR zalo_user_id = %s
            LIMIT 1
            """,
            (f"%{search_phone}", f"%{deal_phone}", deal_phone),
            as_dict=True
        )


        if zalo_cust_name:
            frappe.db.set_value("Zalo OA Customer", zalo_cust_name[0].name, "linked_deal", doc.name)
        else:
            # 4. Trích xuất tên hiển thị an toàn cho Khách hàng Zalo mới
            cust_name = getattr(doc, "organization_name", None) or getattr(doc, "customer_name", None)
            if not cust_name:
                first = getattr(doc, "first_name", "") or ""
                last = getattr(doc, "last_name", "") or ""
                cust_name = f"{first} {last}".strip()
            if not cust_name:
                cust_name = "Khách hàng từ Deal"


            # 5. Tự động tạo mới bản ghi khách hàng Zalo
            new_zalo_cust = frappe.get_doc({
                "doctype": "Zalo OA Customer",
                "zalo_user_id": deal_phone,
                "customer_name": cust_name,
                "phone": deal_phone,
                "source": "Zalo OA",
                "customer_status": "Active",
                "linked_deal": doc.name
            })
            new_zalo_cust.insert(ignore_permissions=True)


        frappe.db.commit()
    except Exception as e:
        # Nếu có bất kỳ lỗi logic nào xảy ra ngầm, ghi vào log và bỏ qua, tuyệt đối không chặn đứng lệnh Create Deal
        frappe.logger().error(f"❌ [Zalo Hook Deal Error] {str(e)}")
# =========================================================================
# LÕI BACKEND & API HỆ THỐNG CHAT TIẾP NHẬN ĐỒNG BỘ 2 CHIỀU
# =========================================================================


def create_or_get_customer(item):
    existing_customer = frappe.db.exists("Zalo OA Customer", {"zalo_user_id": item["zalo_user_id"]})
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
    existing_conversation = frappe.db.exists("Zalo OA Conversation", {"customer": customer_name})
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
        "raw_payload": frappe.as_json({"source": "mock", "zalo_user_id": item["zalo_user_id"]}),
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
    return {"ok": True, "message": "Customer created successfully", "customer": customer_name}




@frappe.whitelist()
def seed_mock_data():
    """Hàm đồng bộ dữ liệu mẫu khớp hoàn toàn với ID thực tế trên Database"""
    target_customer = frappe.db.get_value("Zalo OA Customer", {"zalo_user_id": "zalo-user-009"}, "name")
   
    if not target_customer:
        cust_doc = frappe.get_doc({
            "doctype": "Zalo OA Customer",
            "zalo_user_id": "zalo-user-009",
            "customer_name": "Lê Hoàng Minh",
            "phone": "0926788932",
            "source": "Zalo OA",
            "customer_status": "New",
            "linked_lead": "CRM-LEAD-2026-00014"
        })
        cust_doc.insert(ignore_permissions=True)
        target_customer = cust_doc.name
    else:
        frappe.db.set_value("Zalo OA Customer", target_customer, "linked_lead", "CRM-LEAD-2026-00014")


    conversation_name = frappe.db.get_value("Zalo OA Conversation", {"customer": target_customer}, "name")
    if not conversation_name:
        conv_doc = frappe.get_doc({
            "doctype": "Zalo OA Conversation",
            "customer": target_customer,
            "conversation_title": "Chat với Lê Hoàng Minh",
            "last_message": "Shop còn mẫu màu đen không?",
            "last_message_at": now_datetime(),
            "conversation_status": "Open",
            "topic": "Tư vấn sản phẩm"
        })
        conv_doc.insert(ignore_permissions=True)
        conversation_name = conv_doc.name


    zalo_msg_id = "mock-msg-real-001"
    if not frappe.db.exists("Zalo OA Message", {"zalo_message_id": zalo_msg_id}):
        frappe.get_doc({
            "doctype": "Zalo OA Message",
            "conversation": conversation_name,
            "customer": target_customer,
            "sender_type": "Customer",
            "message_type": "Text",
            "content": "Shop còn mẫu màu đen không?",
            "sent_at": now_datetime(),
            "zalo_message_id": zalo_msg_id,
            "delivery_status": "Received",
            "is_read": 0
        }).insert(ignore_permissions=True)


    frappe.db.commit()
    return {"ok": True, "message": "Đã sửa lỗi đồng bộ định danh thành công!", "linked_customer_id": target_customer, "conversation": conversation_name}




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
        fields=["name", "customer", "conversation_title", "last_message", "last_message_at", "unread_count", "conversation_status", "topic"],
        order_by="last_message_at desc"
    )


    result = []
    for conv in conversations:
        if not frappe.db.exists("Zalo OA Customer", conv.customer):
            continue
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
            "customer_status": customer.customer_status,
            "linked_lead": getattr(customer, "linked_lead", None),
            "linked_contact": getattr(customer, "linked_contact", None),
            "linked_deal": getattr(customer, "linked_deal", None)
        })
    return result




@frappe.whitelist()
def get_messages(conversation):
    if not conversation:
        frappe.throw("Missing conversation")
    return frappe.get_all(
        "Zalo OA Message",
        filters={"conversation": conversation},
        fields=["name", "conversation", "customer", "sender_type", "message_type", "content", "sent_at", "zalo_message_id", "delivery_status", "is_read"],
        order_by="sent_at asc"
    )
# 🌟 ĐÃ KHÔI PHỤC HÀM ĐÁNH DẤU ĐÃ XEM CHO TRANG CHAT TỔNG (FIX LỖI POPUP)
@frappe.whitelist()
def mark_conversation_read(conversation):
    if not conversation:
        return {"ok": False, "message": "Missing conversation"}
   
    # Cập nhật trạng thái các tin nhắn đến từ khách hàng thành đã đọc
    frappe.db.sql(
        """
        UPDATE `tabZalo OA Message`
        SET is_read = 1
        WHERE conversation = %s AND sender_type = 'Customer'
        """,
        conversation
    )
    # Reset bộ đếm tin nhắn chưa đọc của cuộc hội thoại
    frappe.db.set_value("Zalo OA Conversation", conversation, "unread_count", 0)
    frappe.db.commit()
    return {"ok": True}








# =========================================================================
# 🚀 KHỐI XỬ LÝ LẤY LỊCH SỬ CHAT VÀ GỬI TIN CHO TAB CHI TIẾT (LEADS / DEALS)
# =========================================================================


@frappe.whitelist()
def get_chat_history(doctype=None, docname=None, doc_name=None):
    """
    Lấy lịch sử chat Zalo OA theo đúng Lead/Deal đang mở.
    Hỗ trợ cả 2 kiểu tham số:
    - docname: từ frontend JS
    - doc_name: nếu gọi thủ công/API cũ
    """

    doc_name = docname or doc_name

    if not doctype or not doc_name:
        return {
            "status": "error",
            "error": "Thiếu doctype hoặc docname.",
            "messages": []
        }

    zalo_customer_id = get_linked_zalo_user(doc_name, doctype)

    if not zalo_customer_id:
        return {
            "status": "empty",
            "error": f"Bản ghi {doc_name} chưa được liên kết với Zalo OA Customer.",
            "messages": []
        }

    zalo_user_id = frappe.db.get_value(
        "Zalo OA Customer",
        zalo_customer_id,
        "zalo_user_id"
    )

    customer_name = frappe.db.get_value(
        "Zalo OA Customer",
        zalo_customer_id,
        "customer_name"
    )

    conversation_name = frappe.db.get_value(
        "Zalo OA Conversation",
        {"customer": zalo_customer_id},
        "name"
    )

    if not conversation_name:
        return {
            "status": "success",
            "error": None,
            "messages": [],
            "zalo_user_id": zalo_user_id or zalo_customer_id,
            "customer": zalo_customer_id,
            "customer_name": customer_name,
            "conversation": None
        }

    messages = frappe.get_all(
        "Zalo OA Message",
        filters={"conversation": conversation_name},
        fields=[
            "name",
            "content",
            "sender_type",
            "sent_at",
            "delivery_status",
            "is_read"
        ],
        order_by="sent_at asc"
    )

    normalized_messages = []

    for msg in messages:
        sender_type = msg.get("sender_type") or ""

        is_customer = sender_type == "Customer"

        normalized_messages.append({
            "name": msg.get("name"),
            "content": msg.get("content") or "",
            "message": msg.get("content") or "",
            "sender_type": sender_type,
            "sender": "Khách hàng" if is_customer else "Bạn / Frappe",
            "direction": "Incoming" if is_customer else "Outgoing",
            "creation": str(msg.get("sent_at") or ""),
            "sent_at": str(msg.get("sent_at") or ""),
            "delivery_status": msg.get("delivery_status"),
            "is_read": msg.get("is_read"),
        })

    return {
        "status": "success",
        "error": None,
        "messages": normalized_messages,
        "zalo_user_id": zalo_user_id or zalo_customer_id,
        "customer": zalo_customer_id,
        "customer_name": customer_name,
        "conversation": conversation_name
    }


@frappe.whitelist()
def send_message(doctype=None, docname=None, doc_name=None, message=None):
    """
    Gửi tin nhắn từ tab Zalo OA trong Lead/Deal.
    Hỗ trợ cả docname và doc_name để tránh lệch frontend/backend.
    """

    doc_name = docname or doc_name

    if not doctype or not doc_name:
        frappe.throw("Thiếu doctype hoặc docname.")

    if not message or not message.strip():
        frappe.throw("Nội dung phản hồi không được để trống.")

    customer_name = get_linked_zalo_user(doc_name, doctype)

    if not customer_name:
        frappe.throw(f"Bản ghi {doc_name} này chưa được liên kết với bất kỳ Zalo Customer nào.")

    conversation_name = frappe.db.get_value(
        "Zalo OA Conversation",
        {"customer": customer_name},
        "name"
    )

    if not conversation_name:
        conv_doc = frappe.get_doc({
            "doctype": "Zalo OA Conversation",
            "customer": customer_name,
            "conversation_title": f"Chat với {frappe.db.get_value('Zalo OA Customer', customer_name, 'customer_name')}",
            "conversation_status": "Open",
            "topic": "Tư vấn sản phẩm",
            "last_message": message,
            "last_message_at": now_datetime()
        })
        conv_doc.insert(ignore_permissions=True)
        conversation_name = conv_doc.name
    else:
        frappe.db.set_value(
            "Zalo OA Conversation",
            conversation_name,
            {
                "last_message": message,
                "last_message_at": now_datetime()
            }
        )

    msg_doc = frappe.get_doc({
        "doctype": "Zalo OA Message",
        "conversation": conversation_name,
        "customer": customer_name,
        "sender_type": "Agent",
        "message_type": "Text",
        "content": message,
        "sent_at": now_datetime(),
        "zalo_message_id": f"msg-tab-{frappe.generate_hash(length=10)}",
        "delivery_status": "Sent",
        "is_read": 1
    })

    msg_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "message_id": msg_doc.zalo_message_id,
        "conversation": conversation_name
    }


def get_linked_zalo_user(doc_name, doctype):
    """
    Tìm Zalo OA Customer đang liên kết với Lead/Deal hiện tại.
    Lead dùng field linked_lead.
    Deal dùng field linked_deal.
    """

    if not doc_name or not doctype:
        return None

    is_lead = "lead" in doctype.lower()

    if is_lead:
        return frappe.db.get_value(
            "Zalo OA Customer",
            {"linked_lead": doc_name},
            "name"
        )

    return frappe.db.get_value(
        "Zalo OA Customer",
        {"linked_deal": doc_name},
        "name"
    )


# =========================================================================
# ✅ API BỔ SUNG: GIAO DIỆN CHAT ZALO OA + POSTMAN GIẢ LẬP KHÁCH NHẮN
# Dán ở CUỐI FILE để override hàm cũ nhưng không làm mất logic cũ.
# =========================================================================

import json
import frappe
from frappe.utils import now_datetime


def _normalize_ref(doctype=None, docname=None, doc_name=None, reference_doctype=None, reference_name=None):
    """
    Chuẩn hoá tham số từ nhiều kiểu frontend/API:
    - doctype + docname
    - doctype + doc_name
    - reference_doctype + reference_name
    """

    final_doctype = reference_doctype or doctype
    final_docname = reference_name or docname or doc_name

    if final_doctype in ["Lead", "lead", "CRM Lead"]:
        final_doctype = "CRM Lead"

    if final_doctype in ["Deal", "deal", "CRM Deal"]:
        final_doctype = "CRM Deal"

    return final_doctype, final_docname


def _get_request_json():
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
    return data


def _get_or_create_zalo_customer(final_doctype, final_docname, user_id=None, display_name=None, phone=None):
    """
    Tìm hoặc tạo Zalo OA Customer.
    Ưu tiên tìm theo linked_lead / linked_deal.
    Sau đó tìm theo zalo_user_id.
    """

    if not final_doctype or not final_docname:
        frappe.throw("Thiếu doctype hoặc docname.")

    is_lead = "lead" in final_doctype.lower()
    link_field = "linked_lead" if is_lead else "linked_deal"

    customer_name = frappe.db.get_value(
        "Zalo OA Customer",
        {link_field: final_docname},
        "name"
    )

    if customer_name:
        return customer_name

    if user_id:
        customer_name = frappe.db.get_value(
            "Zalo OA Customer",
            {"zalo_user_id": user_id},
            "name"
        )

        if customer_name:
            frappe.db.set_value("Zalo OA Customer", customer_name, link_field, final_docname)
            frappe.db.commit()
            return customer_name

    user_id = user_id or f"postman-{final_docname}"
    display_name = display_name or "Khách hàng Postman"

    doc = frappe.get_doc({
        "doctype": "Zalo OA Customer",
        "zalo_user_id": user_id,
        "customer_name": display_name,
        "phone": phone or "",
        "source": "Zalo OA",
        "customer_status": "Active",
        link_field: final_docname
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


def _get_or_create_conversation(customer_name, first_message=None):
    """
    Tìm hoặc tạo Zalo OA Conversation theo customer.
    """

    conversation_name = frappe.db.get_value(
        "Zalo OA Conversation",
        {"customer": customer_name},
        "name"
    )

    if conversation_name:
        return conversation_name

    customer_display_name = frappe.db.get_value(
        "Zalo OA Customer",
        customer_name,
        "customer_name"
    ) or "Khách hàng"

    conv = frappe.get_doc({
        "doctype": "Zalo OA Conversation",
        "customer": customer_name,
        "conversation_title": f"Chat với {customer_display_name}",
        "last_message": first_message or "",
        "last_message_at": now_datetime(),
        "unread_count": 0,
        "conversation_status": "Open",
        "topic": "Tư vấn sản phẩm"
    })

    conv.insert(ignore_permissions=True)
    frappe.db.commit()

    return conv.name


def _create_zalo_message(customer_name, conversation_name, sender_type, content, delivery_status="Received", raw_payload=None):
    """
    Tạo Zalo OA Message.
    sender_type:
    - Customer: khách hàng / Postman giả lập Zalo
    - Agent: nhân viên CRM gửi
    """

    if not content or not str(content).strip():
        frappe.throw("Nội dung tin nhắn không được để trống.")

    msg = frappe.get_doc({
        "doctype": "Zalo OA Message",
        "conversation": conversation_name,
        "customer": customer_name,
        "sender_type": sender_type,
        "message_type": "Text",
        "content": str(content).strip(),
        "sent_at": now_datetime(),
        "zalo_message_id": f"msg-{frappe.generate_hash(length=12)}",
        "delivery_status": delivery_status,
        "is_read": 1 if sender_type == "Agent" else 0,
        "raw_payload": frappe.as_json(raw_payload or {})
    })

    msg.insert(ignore_permissions=True)

    unread_count = 0

    if sender_type == "Customer":
        unread_count = frappe.db.count(
            "Zalo OA Message",
            {
                "conversation": conversation_name,
                "sender_type": "Customer",
                "is_read": 0
            }
        )

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation_name,
        {
            "last_message": str(content).strip(),
            "last_message_at": now_datetime(),
            "unread_count": unread_count
        }
    )

    frappe.db.commit()

    return msg


@frappe.whitelist()
def get_chat_history(
    doctype=None,
    docname=None,
    doc_name=None,
    reference_doctype=None,
    reference_name=None
):
    """
    API cho tab Zalo OA trong Lead/Deal.
    Hỗ trợ cả frontend cũ và frontend mới.
    """

    final_doctype, final_docname = _normalize_ref(
        doctype=doctype,
        docname=docname,
        doc_name=doc_name,
        reference_doctype=reference_doctype,
        reference_name=reference_name
    )

    if not final_doctype or not final_docname:
        return {
            "ok": False,
            "status": "error",
            "error": "Thiếu doctype/docname hoặc reference_doctype/reference_name.",
            "messages": []
        }

    is_lead = "lead" in final_doctype.lower()
    link_field = "linked_lead" if is_lead else "linked_deal"

    customer_name = frappe.db.get_value(
        "Zalo OA Customer",
        {link_field: final_docname},
        "name"
    )

    if not customer_name:
        return {
            "ok": True,
            "status": "empty",
            "error": f"Bản ghi {final_docname} chưa liên kết với Zalo OA Customer.",
            "messages": [],
            "customer": None,
            "conversation": None
        }

    customer_display_name = frappe.db.get_value(
        "Zalo OA Customer",
        customer_name,
        "customer_name"
    )

    zalo_user_id = frappe.db.get_value(
        "Zalo OA Customer",
        customer_name,
        "zalo_user_id"
    )

    conversation_name = frappe.db.get_value(
        "Zalo OA Conversation",
        {"customer": customer_name},
        "name"
    )

    if not conversation_name:
        return {
            "ok": True,
            "status": "success",
            "error": None,
            "messages": [],
            "customer": customer_name,
            "customer_name": customer_display_name,
            "zalo_user_id": zalo_user_id,
            "conversation": None
        }

    rows = frappe.get_all(
        "Zalo OA Message",
        filters={"conversation": conversation_name},
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
            "sender": customer_display_name if is_customer else "Bạn / Frappe",
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
        "error": None,
        "messages": messages,
        "customer": customer_name,
        "customer_name": customer_display_name,
        "zalo_user_id": zalo_user_id,
        "conversation": conversation_name
    }


@frappe.whitelist()
def send_message(
    doctype=None,
    docname=None,
    doc_name=None,
    reference_doctype=None,
    reference_name=None,
    message=None
):
    """
    Nhân viên gửi tin từ giao diện CRM.
    Tin này sẽ hiện bên phải, giống Zalo thật.
    """

    final_doctype, final_docname = _normalize_ref(
        doctype=doctype,
        docname=docname,
        doc_name=doc_name,
        reference_doctype=reference_doctype,
        reference_name=reference_name
    )

    if not final_doctype or not final_docname:
        frappe.throw("Thiếu doctype/docname hoặc reference_doctype/reference_name.")

    if not message or not str(message).strip():
        frappe.throw("Nội dung phản hồi không được để trống.")

    customer_name = _get_or_create_zalo_customer(
        final_doctype=final_doctype,
        final_docname=final_docname,
        user_id=None,
        display_name=None
    )

    conversation_name = _get_or_create_conversation(
        customer_name=customer_name,
        first_message=message
    )

    msg = _create_zalo_message(
        customer_name=customer_name,
        conversation_name=conversation_name,
        sender_type="Agent",
        content=message,
        delivery_status="Sent",
        raw_payload={
            "source": "crm_tab",
            "doctype": final_doctype,
            "docname": final_docname
        }
    )

    return {
        "ok": True,
        "status": "success",
        "message_id": msg.zalo_message_id,
        "message_docname": msg.name,
        "conversation": conversation_name,
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
    """
    API để Postman giả lập khách hàng nhắn từ Zalo thật.
    Dùng POSTMAN gọi hàm này.
    Tin này sẽ hiện bên trái như khách hàng nhắn.
    """

    data = _get_request_json()

    final_doctype, final_docname = _normalize_ref(
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
        or f"postman-{final_docname}"
    )

    final_display_name = (
        display_name
        or data.get("display_name")
        or data.get("customer_name")
        or data.get("name")
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

    if not final_doctype or not final_docname:
        frappe.throw("Thiếu reference_doctype/reference_name hoặc doctype/docname.")

    if not final_message or not str(final_message).strip():
        frappe.throw("Thiếu nội dung tin nhắn.")

    customer_name = _get_or_create_zalo_customer(
        final_doctype=final_doctype,
        final_docname=final_docname,
        user_id=final_user_id,
        display_name=final_display_name,
        phone=final_phone
    )

    conversation_name = _get_or_create_conversation(
        customer_name=customer_name,
        first_message=final_message
    )

    msg = _create_zalo_message(
        customer_name=customer_name,
        conversation_name=conversation_name,
        sender_type="Customer",
        content=final_message,
        delivery_status="Received",
        raw_payload=data or {
            "source": "postman",
            "zalo_user_id": final_user_id
        }
    )

    return {
        "ok": True,
        "status": "success",
        "source": "postman_simulation",
        "customer": customer_name,
        "conversation": conversation_name,
        "message_docname": msg.name,
        "message_id": msg.zalo_message_id,
        "sender_type": "customer",
        "content": final_message}


@frappe.whitelist()
def send_sidebar_message(conversation=None, message=None):
    """
    Gửi tin nhắn từ giao diện Zalo OA tổng trên sidebar.
    Không cần phân biệt Lead/Deal, chỉ cần conversation.
    """

    if not conversation:
        frappe.throw("Thiếu conversation.")

    if not message or not str(message).strip():
        frappe.throw("Nội dung phản hồi không được để trống.")

    if not frappe.db.exists("Zalo OA Conversation", conversation):
        frappe.throw("Conversation không tồn tại.")

    conv = frappe.get_doc("Zalo OA Conversation", conversation)
    customer_name = conv.customer

    if not customer_name:
        frappe.throw("Conversation chưa liên kết khách hàng.")

    content = str(message).strip()

    msg_doc = frappe.get_doc({
        "doctype": "Zalo OA Message",
        "conversation": conversation,
        "customer": customer_name,
        "sender_type": "Agent",
        "message_type": "Text",
        "content": content,
        "sent_at": now_datetime(),
        "zalo_message_id": f"msg-sidebar-{frappe.generate_hash(length=10)}",
        "delivery_status": "Sent",
        "is_read": 1,
        "raw_payload": frappe.as_json({
            "source": "zalo_oa_sidebar"
        })
    })

    msg_doc.insert(ignore_permissions=True)

    frappe.db.set_value(
        "Zalo OA Conversation",
        conversation,
        {
            "last_message": content,
            "last_message_at": now_datetime()
        }
    )

    frappe.db.commit()

    return {
        "ok": True,
        "status": "success",
        "conversation": conversation,
        "message_docname": msg_doc.name,
        "message_id": msg_doc.zalo_message_id,
        "content": content
    }
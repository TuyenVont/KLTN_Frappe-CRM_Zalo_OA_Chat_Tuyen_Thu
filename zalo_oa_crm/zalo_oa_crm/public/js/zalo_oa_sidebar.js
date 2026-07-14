// public/js/zalo_oa_sidebar.js




(function () {
  const BTN_ID = "zalo-oa-sidebar-btn";
  const PAGE_ID = "zalo-oa-sidebar-page";




  const API = {
    conversations: "zalo_oa_crm.api.chat.get_conversations",
    messages: "zalo_oa_crm.api.chat.get_messages",
    markRead: "zalo_oa_crm.api.chat.mark_conversation_read",
    send: "zalo_oa_crm.api.chat.send_sidebar_message",
    demo: "zalo_oa_crm.api.chat.seed_mock_data",
  };




    let selectedConversation = null;
    let conversationCache = [];
    let selectedConversationData = null;




    let zoaAutoRefreshTimer = null;
    let zoaIsPolling = false;
    let zoaLastMessageSignature = "";




  function getCSRFToken() {
      // Ưu tiên lấy window.csrf_token (chuẩn của Frappe CRM hiện tại)
      return (
        window.csrf_token || 
        window.frappe?.csrf_token ||
        document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
        ""
      );
    }

    async function frappeCall(method, args = {}, httpMethod = "GET") {
      let url = `/api/method/${method}`;

      const options = {
        method: httpMethod,
        credentials: "same-origin",
        headers: {},
      };

      if (httpMethod === "GET") {
        const qs = new URLSearchParams(args).toString();
        if (qs) url += `?${qs}`;
      } else {
        // Đổi sang chuẩn application/json giống hệt file zalo_oa_tab.js
        options.headers["Content-Type"] = "application/json";
        options.headers["X-Frappe-CSRF-Token"] = getCSRFToken();
        options.body = JSON.stringify(args);
      }

      const res = await fetch(url, options);

      if (!res.ok) {
        throw new Error(`API ${method} failed: ${res.status}`);
      }

      const data = await res.json();
      return data.message || data;
    }



  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }




  function initials(name) {
    const text = String(name || "").trim();
    if (!text) return "Z";




    const parts = text.split(/\s+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();




    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }




  function formatDateTime(value) {
    if (!value) return "";
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return String(value);
      const dd = String(d.getDate()).padStart(2, "0");
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const yyyy = d.getFullYear();
      const hh = String(d.getHours()).padStart(2, "0");
      const mi = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      return `${dd}-${mm}-${yyyy} ${hh}:${mi}:${ss}`;
    } catch (e) {
      return String(value);
    }
  }




  function findMainSidebar() {
    return (
      document.querySelector("aside") ||
      document.querySelector("nav") ||
      document.querySelector('[class*="sidebar"]') ||
      document.querySelector('[class*="Sidebar"]')
    );
  }




  function getSidebarRight() {
    const sidebar = findMainSidebar();
    if (!sidebar) return 280;
    const rect = sidebar.getBoundingClientRect();
    return Math.max(rect.right, 72);
  }




  function findCallLogsMenu() {
    const byHref =
      document.querySelector('a[href*="call-logs"]') ||
      document.querySelector('a[href*="call_logs"]') ||
      document.querySelector('a[href*="call-log"]');




    if (byHref) return byHref;




    const sidebar = findMainSidebar();
    if (!sidebar) return null;




    const items = Array.from(sidebar.querySelectorAll("a, button, div, span"));
    const matched = items.find((el) => {
      const text = (el.textContent || "").trim().toLowerCase();
      return text === "call logs" || text === "nhật ký cuộc gọi" || text === "nhat ky cuoc goi";
    });




    return matched ? matched.closest("a, button") || matched : null;
  }




  function getLastMainMenuItem() {
    const sidebar = findMainSidebar();
    if (!sidebar) return null;




    const links = Array.from(sidebar.querySelectorAll("a, button")).filter((el) => {
      const text = (el.textContent || "").trim();
      if (!text) return false;
      if (text.includes("Continue")) return false;
      if (text.includes("Getting started")) return false;
      if (text.includes("Collapse")) return false;
      return true;
    });




    return links.length ? links[links.length - 1] : null;
  }




    function createZaloButton(baseItem) {
    const zaloBtn = document.createElement("a");








    zaloBtn.id = BTN_ID;
    zaloBtn.href = "/crm/zalo-oa";
    zaloBtn.title = "Zalo OA";
    zaloBtn.className = baseItem?.className || "";
    zaloBtn.style.cursor = "pointer";
    zaloBtn.style.textDecoration = "none";








    // Giữ layout giống menu core
    zaloBtn.style.display = "flex";
    zaloBtn.style.alignItems = "center";
    zaloBtn.style.gap = "10px";








    zaloBtn.innerHTML = `
        <span style="
        width: 20px;
        min-width: 20px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        ">
        <span style="
            width: 18px;
            height: 18px;
            border-radius: 4px;
            background: #0b66ff;
            color: #ffffff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: 400;
            line-height: 1;
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        ">Z</span>
        </span>








        <span style="
        font-size: 14px;
        font-weight: inherit;
        color: #4b5563;
        line-height: 20px;
        white-space: nowrap;
        ">Zalo OA</span>
    `;








  zaloBtn.addEventListener("click", function (e) {
  e.preventDefault();


  try {
    window.history.pushState({}, "", "/crm/zalo-oa");
  } catch (err) {
    console.error("[Zalo OA] Không đổi được URL:", err);
  }


  openZaloPage();
});


return zaloBtn;
}






  function addZaloOASidebarButton() {
    if (document.getElementById(BTN_ID)) return true;




    let targetItem = findCallLogsMenu();
    if (!targetItem) targetItem = getLastMainMenuItem();
    if (!targetItem) return false;




    const baseItem = targetItem.closest("a, button") || targetItem;
    const zaloBtn = createZaloButton(baseItem);




    baseItem.insertAdjacentElement("afterend", zaloBtn);
    return true;
  }




function ensureStyles() {
    if (document.getElementById("zalo-oa-sidebar-style")) return;

    const style = document.createElement("style");
    style.id = "zalo-oa-sidebar-style";
    style.innerHTML = `
      #${PAGE_ID} {
        position: fixed;
        top: 0;
        right: 0;
        bottom: 0;
        background: #ffffff;
        z-index: 55;
        border-left: 1px solid #e5e7eb;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      .zoa-shell {
        height: 100%;
        display: flex;
        flex-direction: column;
        background: #f8fafc;
      }

      .zoa-toolbar {
        padding: 16px;
        border-bottom: 1px solid #e5e7eb;
        background: #ffffff;
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
      }

      .zoa-toolbar input,
      .zoa-toolbar select {
        height: 40px;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        padding: 0 12px;
        font-size: 14px;
        background: #fff;
      }

      .zoa-toolbar input {
        min-width: 280px;
        flex: 1 1 280px;
      }

      .zoa-toolbar button {
        height: 40px;
        padding: 0 14px;
        border-radius: 8px;
        border: 1px solid #111827;
        background: #111827;
        color: #fff;
        cursor: pointer;
        font-size: 14px;
        font-weight: 600;
      }

      .zoa-toolbar .zoa-btn-secondary {
        background: #f3f4f6;
        color: #111827;
        border-color: #e5e7eb;
      }

      .zoa-body {
        min-height: 0;
        flex: 1;
        display: grid;
        grid-template-columns: 360px minmax(0, 1fr) 340px;
      }

      .zoa-panel {
        background: #fff;
        min-width: 0;
        min-height: 0;
        display: flex;
        flex-direction: column;
        border-right: 1px solid #e5e7eb;
      }

      .zoa-panel:last-child {
        border-right: none;
      }

      .zoa-panel-title {
        padding: 16px 18px;
        border-bottom: 1px solid #e5e7eb;
        font-size: 16px;
        font-weight: 700;
        color: #111827;
      }

      .zoa-conversation-list,
      .zoa-profile-scroll {
        overflow: auto;
        flex: 1;
      }

      .zoa-conv-item {
        display: flex;
        gap: 12px;
        padding: 14px 16px;
        cursor: pointer;
        border-bottom: 1px solid #eef2f7;
      }

      .zoa-conv-item:hover {
        background: #f8fafc;
      }

      .zoa-conv-item.active {
        background: #dbeafe;
      }

      .zoa-avatar {
        width: 46px;
        height: 46px;
        border-radius: 999px;
        background: #2563eb;
        color: #fff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 18px;
        overflow: hidden;
        flex: 0 0 auto;
      }

      .zoa-avatar img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }

      .zoa-conv-main {
        min-width: 0;
        flex: 1;
      }

      .zoa-conv-row {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        align-items: flex-start;
      }

      .zoa-conv-name {
        font-size: 16px;
        font-weight: 700;
        color: #111827;
        line-height: 1.35;
      }

      .zoa-conv-time {
        font-size: 12px;
        color: #64748b;
        white-space: nowrap;
      }

      .zoa-conv-last {
        margin-top: 4px;
        font-size: 13px;
        color: #334155;
        line-height: 1.4;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .zoa-tags {
        margin-top: 10px;
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }

      .zoa-tag {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 999px;
        background: #f1f5f9;
        color: #334155;
        font-size: 12px;
      }

      .zoa-center-head {
        padding: 16px 18px;
        border-bottom: 1px solid #e5e7eb;
        background: #fff;
      }

      .zoa-customer-name {
        font-size: 18px;
        font-weight: 800;
        color: #111827;
      }

      .zoa-customer-sub {
        margin-top: 6px;
        font-size: 14px;
        color: #64748b;
      }

      .zoa-messages {
        flex: 1;
        overflow: auto;
        padding: 18px;
        background: #f8fafc;
      }

      .zoa-message-row {
        display: flex;
        margin-bottom: 16px;
      }

      .zoa-message-row.outgoing {
        justify-content: flex-end;
      }

      .zoa-bubble {
        max-width: min(520px, 78%);
        border-radius: 16px;
        padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
      }

      .zoa-message-row.incoming .zoa-bubble {
        background: #fff;
        border: 1px solid #e5e7eb;
      }

      .zoa-message-row.outgoing .zoa-bubble {
        background: #dbeafe;
        border: 1px solid #bfdbfe;
      }

      .zoa-bubble-content {
        font-size: 15px;
        line-height: 1.5;
        color: #111827;
        white-space: pre-wrap;
        word-break: break-word;
      }

      .zoa-bubble-meta {
        margin-top: 10px;
        font-size: 12px;
        line-height: 1.5;
        color: #64748b;
      }

      .zoa-composer {
        border-top: 1px solid #e5e7eb;
        background: #fff;
        padding: 12px;
        display: flex;
        gap: 10px;
      }

      .zoa-composer textarea {
        flex: 1;
        min-height: 42px;
        max-height: 120px;
        resize: none;
        border: 1px solid #d1d5db;
        border-radius: 10px;
        padding: 10px 12px;
        font-size: 14px;
        outline: none;
      }

      .zoa-composer button {
        min-width: 96px;
        border-radius: 10px;
        border: 1px solid #111827;
        background: #111827;
        color: #fff;
        font-weight: 600;
        cursor: pointer;
      }

      .zoa-profile-scroll {
        padding: 16px;
      }

      .zoa-profile-header {
        display: flex;
        gap: 14px;
        align-items: center;
        padding-bottom: 16px;
        border-bottom: 1px solid #e5e7eb;
      }

      .zoa-profile-name {
        font-size: 18px;
        font-weight: 800;
        color: #111827;
      }

      .zoa-profile-sub {
        margin-top: 4px;
        color: #64748b;
        font-size: 14px;
      }

      .zoa-info-block {
        padding: 16px 0;
        border-bottom: 1px solid #e5e7eb;
      }

      .zoa-info-label {
        font-size: 13px;
        color: #64748b;
        margin-bottom: 6px;
      }

      .zoa-info-value {
        font-size: 14px;
        color: #111827;
        font-weight: 600;
        word-break: break-word;
      }

      .zoa-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 180px;
        text-align: center;
        padding: 24px;
        color: #64748b;
      }

      @media (max-width: 1200px) {
        .zoa-body {
          grid-template-columns: 320px minmax(0, 1fr);
        }
        .zoa-panel.zoa-right {
          display: none;
        }
      }

      @media (max-width: 900px) {
        #${PAGE_ID} {
          left: 0 !important;
        }
        .zoa-body {
          grid-template-columns: 1fr;
        }
        .zoa-panel.zoa-left,
        .zoa-panel.zoa-right {
          display: none;
        }
      }

      /* TẮT HOÀN TOÀN THANH TRẮNG TRÊN TOÀN BỘ SIDEBAR CỦA FRAPPE CRM */
      aside a, aside button, 
      nav a, nav button, 
      [class*="sidebar"] a, [class*="sidebar"] button {
        background-color: transparent !important;
        background: transparent !important;
        box-shadow: none !important;
      }

      /* Chỉ giữ lại màu xám rất nhẹ khi rê chuột (hover) để user biết họ đang chỉ vào đâu */
      aside a:hover, aside button:hover, 
      nav a:hover, nav button:hover, 
      [class*="sidebar"] a:hover, [class*="sidebar"] button:hover {
        background-color: #f8fafc !important; 
      }
    `;

    document.head.appendChild(style);
  }




    function getMessageSignature(rows) {
    return rows
        .map((msg) => {
        return [
            msg.name || "",
            msg.zalo_message_id || "",
            msg.sent_at || "",
            msg.content || "",
            msg.delivery_status || "",
        ].join("::");
        })
        .join("|");
    }




    function startZaloAutoRefresh() {
    stopZaloAutoRefresh();




    zoaAutoRefreshTimer = setInterval(function () {
        autoRefreshZaloData();
    }, 2000);
    }




    function stopZaloAutoRefresh() {
    if (zoaAutoRefreshTimer) {
        clearInterval(zoaAutoRefreshTimer);
        zoaAutoRefreshTimer = null;
    }
    }




    async function autoRefreshZaloData() {
    const page = document.getElementById(PAGE_ID);




    if (!page) {
        stopZaloAutoRefresh();
        return;
    }




    if (zoaIsPolling) {
        return;
    }




    zoaIsPolling = true;




    try {
        const search = document.getElementById("zoa-search")?.value || "";
        const status = document.getElementById("zoa-status")?.value || "All";
        const topic = document.getElementById("zoa-topic")?.value || "All";




        const conversations = await frappeCall(
        API.conversations,
        {
            search,
            status,
            topic,
        },
        "GET"
        );




        conversationCache = Array.isArray(conversations) ? conversations : [];
        renderConversationList(conversationCache);




        if (!selectedConversation) {
        return;
        }




        const latestSelectedRow =
        conversationCache.find((x) => x.name === selectedConversation) ||
        selectedConversationData;




        selectedConversationData = latestSelectedRow;




        renderConversationDetail(latestSelectedRow);
        renderProfile(latestSelectedRow);




        const messages = await frappeCall(
        API.messages,
        {
            conversation: selectedConversation,
        },
        "GET"
        );




        const messageRows = Array.isArray(messages) ? messages : [];
        const newSignature = getMessageSignature(messageRows);




        if (newSignature !== zoaLastMessageSignature) {
        zoaLastMessageSignature = newSignature;
        renderMessages(messageRows);
        }
    } catch (err) {
        console.warn("[Zalo OA] Auto refresh warning:", err);
    } finally {
        zoaIsPolling = false;
    }
    }




  function openZaloPage() {
    ensureStyles();
    let page = document.getElementById(PAGE_ID);
    if (!page) {
      page = document.createElement("div");
      page.id = PAGE_ID;
      document.body.appendChild(page);
    }


    page.style.display = "block";

    page.style.left = `${getSidebarRight()}px`;




    page.innerHTML = `
      <div class="zoa-shell">
        <div class="zoa-toolbar">
          <input id="zoa-search" type="text" placeholder="Tìm theo tên, SĐT, Zalo ID..." />
          <select id="zoa-status">
            <option value="All">Tất cả trạng thái</option>
            <option value="Open">Open</option>
            <option value="Closed">Closed</option>
          </select>
          <select id="zoa-topic">
            <option value="All">Tất cả chủ đề</option>
            <option value="Báo giá">Báo giá</option>
            <option value="Bảo hành">Bảo hành</option>
            <option value="Tư vấn sản phẩm">Tư vấn sản phẩm</option>
          </select>
          <button id="zoa-refresh">Làm mới</button>
          <button id="zoa-demo" class="zoa-btn-secondary">Tạo dữ liệu demo</button>
        </div>




        <div class="zoa-body">
          <section class="zoa-panel zoa-left">
            <div class="zoa-panel-title">Cuộc hội thoại</div>
            <div id="zoa-conversation-list" class="zoa-conversation-list">
              <div class="zoa-empty">Đang tải hội thoại...</div>
            </div>
          </section>




          <section class="zoa-panel zoa-center">
            <div id="zoa-center-head" class="zoa-center-head">
              <div class="zoa-customer-name">Chọn một cuộc hội thoại</div>
              <div class="zoa-customer-sub">Tin nhắn của Leads và Deals sẽ hiển thị tại đây</div>
            </div>




            <div id="zoa-messages" class="zoa-messages">
              <div class="zoa-empty">Chưa chọn hội thoại</div>
            </div>




            <form id="zoa-composer" class="zoa-composer">
              <textarea id="zoa-message-input" placeholder="Nhập tin nhắn..." disabled></textarea>
              <button id="zoa-send-btn" type="submit" disabled>Gửi</button>
            </form>
          </section>




          <section class="zoa-panel zoa-right">
            <div class="zoa-panel-title">Hồ sơ khách hàng</div>
            <div id="zoa-profile" class="zoa-profile-scroll">
              <div class="zoa-empty">Chưa chọn khách hàng</div>
            </div>
          </section>
        </div>
      </div>
    `;




    document.getElementById("zoa-search").addEventListener("input", debounce(loadConversations, 250));
    document.getElementById("zoa-status").addEventListener("change", loadConversations);
    document.getElementById("zoa-topic").addEventListener("change", loadConversations);
    document.getElementById("zoa-refresh").addEventListener("click", loadConversations);
    document.getElementById("zoa-demo").addEventListener("click", async function () {
      try {
        await frappeCall(API.demo, {}, "POST");
        await loadConversations();
      } catch (e) {
        console.error(e);
        alert("Không tạo được dữ liệu demo.");
      }
    });
    document.getElementById("zoa-composer").addEventListener("submit", sendMessage);




    loadConversations();
    startZaloAutoRefresh();
  }

  function closeZaloPage() {
    const page = document.getElementById(PAGE_ID);
    if (page) {
        page.style.display = "none"; // Giấu bức màn đi
    }
    stopZaloAutoRefresh(); // Tắt luôn timer gọi API để đỡ nặng máy
  }




  function renderAvatar(item, size = 46) {
    if (item?.avatar_url) {
      return `<span class="zoa-avatar" style="width:${size}px;height:${size}px;"><img src="${escapeHtml(item.avatar_url)}" alt=""></span>`;
    }
    return `<span class="zoa-avatar" style="width:${size}px;height:${size}px;">${escapeHtml(initials(item?.customer_name))}</span>`;
  }




  async function loadConversations() {
    const listEl = document.getElementById("zoa-conversation-list");
    if (!listEl) return;




    listEl.innerHTML = `<div class="zoa-empty">Đang tải hội thoại...</div>`;




    const search = document.getElementById("zoa-search")?.value || "";
    const status = document.getElementById("zoa-status")?.value || "All";
    const topic = document.getElementById("zoa-topic")?.value || "All";




    try {
      const rows = await frappeCall(API.conversations, { search, status, topic }, "GET");
      conversationCache = Array.isArray(rows) ? rows : [];




      renderConversationList(conversationCache);




      if (selectedConversation) {
        const exists = conversationCache.find((x) => x.name === selectedConversation);
        if (!exists) {
          selectedConversation = null;
          selectedConversationData = null;
          renderConversationDetail(null);
          renderProfile(null);
        }
      }
    } catch (e) {
      console.error("[Zalo OA] loadConversations error", e);
      listEl.innerHTML = `<div class="zoa-empty">Không tải được danh sách hội thoại.</div>`;
    }
  }




  function renderConversationList(rows) {
    const listEl = document.getElementById("zoa-conversation-list");
    if (!listEl) return;




    if (!rows.length) {
      listEl.innerHTML = `<div class="zoa-empty">Chưa có cuộc hội thoại nào.</div>`;
      return;
    }




    listEl.innerHTML = rows
      .map((item) => {
        const active = selectedConversation === item.name ? "active" : "";
        const tags = [];




        if (item.conversation_status) tags.push(item.conversation_status);
        if (item.topic) tags.push(item.topic);




        return `
          <div class="zoa-conv-item ${active}" data-conversation="${escapeHtml(item.name)}">
            ${renderAvatar(item)}
            <div class="zoa-conv-main">
              <div class="zoa-conv-row">
                <div class="zoa-conv-name">${escapeHtml(item.customer_name || "Khách hàng")}</div>
                <div class="zoa-conv-time">${escapeHtml(formatDateTime(item.last_message_at))}</div>
              </div>




              <div class="zoa-conv-last">${escapeHtml(item.last_message || "")}</div>




              <div class="zoa-tags">
                ${tags.map(tag => `<span class="zoa-tag">${escapeHtml(tag)}</span>`).join("")}
              </div>
            </div>
          </div>
        `;
      })
      .join("");




    listEl.querySelectorAll(".zoa-conv-item").forEach((el) => {
      el.addEventListener("click", function () {
        const conversation = this.getAttribute("data-conversation");
        const row = conversationCache.find((x) => x.name === conversation) || null;
        selectedConversation = conversation;
        selectedConversationData = row;
        renderConversationList(conversationCache);
        loadMessages(conversation, row);
      });
    });
  }




  async function loadMessages(conversation, row) {
    const messagesEl = document.getElementById("zoa-messages");
    if (!messagesEl) return;




    renderConversationDetail(row);
    renderProfile(row);




    messagesEl.innerHTML = `<div class="zoa-empty">Đang tải tin nhắn...</div>`;




    const input = document.getElementById("zoa-message-input");
    const sendBtn = document.getElementById("zoa-send-btn");




    if (input) input.disabled = false;
    if (sendBtn) sendBtn.disabled = false;




    try {
        const messages = await frappeCall(API.messages, { conversation }, "GET");
        const rows = Array.isArray(messages) ? messages : [];




        zoaLastMessageSignature = getMessageSignature(rows);




        renderMessages(rows);




      try {
        await frappeCall(API.markRead, { conversation }, "POST");
      } catch (markErr) {
        console.warn("[Zalo OA] markRead warning", markErr);
      }




      await loadConversations();
      selectedConversation = conversation;
    } catch (e) {
      console.error("[Zalo OA] loadMessages error", e);
      messagesEl.innerHTML = `<div class="zoa-empty">Không tải được tin nhắn.</div>`;
    }
  }




  function renderConversationDetail(row) {
    const head = document.getElementById("zoa-center-head");
    if (!head) return;




    if (!row) {
      head.innerHTML = `
        <div class="zoa-customer-name">Chọn một cuộc hội thoại</div>
        <div class="zoa-customer-sub">Tin nhắn của Leads và Deals sẽ hiển thị tại đây</div>
      `;
      return;
    }




    head.innerHTML = `
      <div class="zoa-customer-name">${escapeHtml(row.customer_name || "Khách hàng")}</div>
      <div class="zoa-customer-sub">
        ${row.phone ? `SĐT: ${escapeHtml(row.phone)}` : "Chưa có SĐT"}
        ${row.zalo_user_id ? ` · Zalo ID: ${escapeHtml(row.zalo_user_id)}` : ""}
      </div>
    `;
  }




  function renderMessages(rows) {
    const messagesEl = document.getElementById("zoa-messages");
    if (!messagesEl) return;




    if (!rows.length) {
      messagesEl.innerHTML = `<div class="zoa-empty">Hội thoại này chưa có tin nhắn.</div>`;
      return;
    }




    messagesEl.innerHTML = rows
      .map((msg) => {
        const isCustomer = (msg.sender_type || "") === "Customer";
        const direction = isCustomer ? "incoming" : "outgoing";
        const senderLabel = isCustomer ? "Customer" : "Agent";
        const content = msg.content || "";
        const sentAt = formatDateTime(msg.sent_at);
        const deliveryStatus = msg.delivery_status || "";
        const messageType = msg.message_type || "Text";




        return `
          <div class="zoa-message-row ${direction}">
            <div class="zoa-bubble">
              <div class="zoa-bubble-content">${escapeHtml(content)}</div>
              <div class="zoa-bubble-meta">
                ${escapeHtml(senderLabel)} · ${escapeHtml(messageType)} · ${escapeHtml(sentAt)} · ${escapeHtml(deliveryStatus)}<br>
                ID: ${escapeHtml(msg.zalo_message_id || msg.name || "")}
              </div>
            </div>
          </div>
        `;
      })
      .join("");




    messagesEl.scrollTop = messagesEl.scrollHeight;
  }




  function renderProfile(row) {
    const profile = document.getElementById("zoa-profile");
    if (!profile) return;




    if (!row) {
      profile.innerHTML = `<div class="zoa-empty">Chưa chọn khách hàng</div>`;
      return;
    }




    profile.innerHTML = `
      <div class="zoa-profile-header">
        ${renderAvatar(row, 54)}
        <div>
          <div class="zoa-profile-name">${escapeHtml(row.customer_name || "Khách hàng")}</div>
          <div class="zoa-profile-sub">${row.phone ? escapeHtml(row.phone) : "Chưa có SĐT"}</div>
        </div>
      </div>




      <div class="zoa-info-block">
        <div class="zoa-info-label">Zalo User ID</div>
        <div class="zoa-info-value">${escapeHtml(row.zalo_user_id || "")}</div>
      </div>




      <div class="zoa-info-block">
        <div class="zoa-info-label">Customer Doc</div>
        <div class="zoa-info-value">${escapeHtml(row.customer || "")}</div>
      </div>




      <div class="zoa-info-block">
        <div class="zoa-info-label">Trạng thái khách</div>
        <div class="zoa-info-value">${escapeHtml(row.customer_status || "")}</div>
      </div>




      <div class="zoa-info-block">
        <div class="zoa-info-label">Nguồn</div>
        <div class="zoa-info-value">Zalo OA</div>
      </div>




      <div class="zoa-info-block">
        <div class="zoa-info-label">Conversation</div>
        <div class="zoa-info-value">${escapeHtml(row.conversation_title || row.name || "")}</div>
      </div>




      <div class="zoa-info-block">
        <div class="zoa-info-label">Deal</div>
        <div class="zoa-info-value">${escapeHtml(row.linked_deal || "Chưa gắn Deal")}</div>
      </div>




      <div class="zoa-info-block">
        <div class="zoa-info-label">Lead</div>
        <div class="zoa-info-value">${escapeHtml(row.linked_lead || "Chưa gắn Lead")}</div>
      </div>
    `;
  }




  async function sendMessage(e) {
    e.preventDefault();




    if (!selectedConversation) return;




    const input = document.getElementById("zoa-message-input");
    const text = String(input?.value || "").trim();




    if (!text) return;




    input.value = "";




    try {
      await frappeCall(API.send, { conversation: selectedConversation, message: text }, "POST");
      await loadMessages(selectedConversation, selectedConversationData);
    } catch (e) {
      console.error("[Zalo OA] sendMessage error", e);
      alert("Không gửi được tin nhắn.");
    }
  }




  function debounce(fn, delay) {
    let timer = null;
    return function () {
      const ctx = this;
      const args = arguments;
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(ctx, args), delay);
    };
  }




  function bootZaloOASidebar() {
      addZaloOASidebarButton();

      const observer = new MutationObserver(function () {
          addZaloOASidebarButton();
      });

      observer.observe(document.body, {
          childList: true,
          subtree: true,
      });

      let count = 0;
      const timer = setInterval(function () {
          count += 1;
          if (addZaloOASidebarButton() || count >= 30) {
              clearInterval(timer);
          }
      }, 500);

      // Mở trang nếu đang đứng sẵn ở link Zalo OA
      if (location.pathname === "/crm/zalo-oa") {
          setTimeout(openZaloPage, 500);
      }

// Vệ sĩ giờ chỉ làm 1 việc duy nhất: Đóng trang Zalo nếu URL thay đổi
    setInterval(function() {
        const isZaloActive = window.location.pathname === "/crm/zalo-oa";
        if (!isZaloActive) {
            closeZaloPage();
        }
    }, 100);

      window.addEventListener("resize", function () {
          const page = document.getElementById(PAGE_ID);
          if (page && page.style.display !== "none") { // Chỉ update resize khi đang mở
              page.style.left = `${getSidebarRight()}px`;
          }
      });
  }




  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootZaloOASidebar);
  } else {
    bootZaloOASidebar();
  }
})();







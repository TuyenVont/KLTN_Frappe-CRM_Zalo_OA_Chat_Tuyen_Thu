(function () {
  if (window.zaloOaCrmV9Loaded) return;
  window.zaloOaCrmV9Loaded = true;

  var TAB_ID = "zalo_oa_tab_v9";
  var PANEL_ID = "zalo_oa_panel_v9";
  var STYLE_ID = "zalo_oa_style_v9";

  var chatPoller = null;

  var NATIVE_TABS = [
      "Activity", "Hoạt động", "Hoạt Động",
      "Emails", "Email",
      "Comments", "Bình luận",
      "Data", "Dữ liệu",
      "Calls", "Cuộc gọi",
      "Tasks", "Nhiệm vụ",
      "Notes", "Ghi chú",
      "Attachments", "Tệp đính kèm", "Tệp tin đính kèm"
    ];

  function getRef() {
    var path = window.location.pathname || "";

    var lead = path.match(/\/crm\/leads\/([^/?#]+)/i);
    if (lead) {
      var leadName = decodeURIComponent(lead[1]);
      if (
        leadName &&
        leadName !== "view" &&
        leadName !== "list" &&
        leadName.indexOf("CRM-LEAD-") === 0
      ) {
        return { doctype: "CRM Lead", docname: leadName };
      }
    }

    var deal = path.match(/\/crm\/deals\/([^/?#]+)/i);
    if (deal) {
      var dealName = decodeURIComponent(deal[1]);
      if (
        dealName &&
        dealName !== "view" &&
        dealName !== "list" &&
        dealName.indexOf("CRM-DEAL-") === 0
      ) {
        return { doctype: "CRM Deal", docname: dealName };
      }
    }

    return null;
  }

  function esc(v) {
    return String(v || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function visible(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  function cleanText(el) {
    return (el.innerText || el.textContent || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function isInsideSidebar(el) {
    return !!(el && el.closest && el.closest("aside"));
  }

  function findNativeTab(label) {
      // CHỈ tìm trong button, thẻ a, hoặc role='tab'. Bỏ div và span để không bao giờ bắt nhầm tiêu đề nữa.
      var selectors = "button, a, [role='tab']";
      var nodes = Array.from(document.querySelectorAll(selectors));

      var matched = nodes
        .filter(function (el) {
          if (!visible(el)) return false;
          if (isInsideSidebar(el)) return false;
          if (el.id === TAB_ID) return false;

          var text = cleanText(el);
          if (!text) return false;
          if (text.length > 60) return false;

          // Ép về chữ thường hết để so sánh, tránh lỗi do viết hoa chữ cái đầu
          return text.toLowerCase() === label.toLowerCase() || text.toLowerCase().indexOf(label.toLowerCase()) !== -1;
        })
        .map(function (el) {
          return el.closest("button, a, [role='tab']") || el;
        })
        .filter(function (el, index, arr) {
          return arr.indexOf(el) === index;
        });

      matched.sort(function (a, b) {
        var ra = a.getBoundingClientRect();
        var rb = b.getBoundingClientRect();

        var scoreA = ra.width * ra.height;
        var scoreB = rb.width * rb.height;

        return scoreA - scoreB;
      });

      return matched[0] || null;
    }

  function findAnyNativeTab() {
      for (var i = 0; i < NATIVE_TABS.length; i++) {
        var found = findNativeTab(NATIVE_TABS[i]);
        if (found) return found;
      }
      return null;
    }

  function findTabBar() {
    var anchor = findAnyNativeTab();
    if (!anchor) return null;

    var p = anchor.parentElement;

    while (p && p !== document.body) {
      if (!visible(p)) {
        p = p.parentElement;
        continue;
      }

      if (isInsideSidebar(p)) {
        p = p.parentElement;
        continue;
      }

      var text = cleanText(p);
      var r = p.getBoundingClientRect();

      var count = NATIVE_TABS.filter(function (name) {
        return text.indexOf(name) !== -1;
      }).length;

      if (
        count >= 2 &&
        r.width > 500 &&
        r.height >= 32 &&
        r.height <= 150
      ) {
        return p;
      }

      p = p.parentElement;
    }

    return anchor.parentElement || null;
  }

  function findPanelHost() {
    var inlineFallback = document.getElementById("zalo_oa_inline_fallback_tabbar_v9");
    if (inlineFallback && inlineFallback.parentNode) {
      return inlineFallback.parentNode;
    }
    var tabBar = findTabBar();
    if (tabBar && tabBar.parentNode) return tabBar.parentNode;

    var tab = document.getElementById(TAB_ID);
    if (tab) {
      var p = tab.parentElement;
      while (p && p !== document.body) {
        var r = p.getBoundingClientRect();
        if (r.width > 600 && r.height > 100 && !isInsideSidebar(p)) {
          return p;
        }
        p = p.parentElement;
      }
    }

    return (
      document.querySelector("main") ||
      document.querySelector(".layout-main-section") ||
      document.querySelector(".page-content") ||
      document.querySelector(".page-body") ||
      document.body
    );
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;

    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .zalo-oa-tab-v9 {
        height: 42px;
        padding: 0 12px;
        border: 0;
        border-bottom: 2px solid transparent;
        background: transparent;
        color: #64748b;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        white-space: nowrap;
      }

      .zalo-oa-tab-v9.active {
        border-bottom-color: #0068ff;
        color: #111827;
      }

      .zalo-oa-icon-v9 {
        width: 20px;
        height: 20px;
        border-radius: 4px;
        background: #0068ff;
        color: white;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        font-weight: 700;
        font-family: Arial, sans-serif;
      }

      .zalo-oa-panel-v9 {
        width: 100%;
        height: 600px;
        margin-top: 16px;
        border: 1px solid #e5eaf2;
        border-radius: 8px;
        background: #ffffff;
        display: flex;
        flex-direction: column;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        box-sizing: border-box;
      }

      .zalo-oa-head-v9 {
        padding: 16px 20px;
        border-bottom: 1px solid #e5eaf2;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }

      .zalo-oa-title-v9 {
        font-size: 16px;
        font-weight: 700;
        color: #0f172a;
      }

      .zalo-oa-sub-v9 {
        font-size: 12px;
        color: #64748b;
        margin-top: 4px;
      }

      .zalo-oa-actions-v9 {
        display: flex;
        gap: 12px;
        align-items: center;
      }

      .zalo-oa-btn-v9 {
        height: 32px;
        padding: 0 14px;
        border-radius: 6px;
        border: 1px solid #d1d5db;
        background: #ffffff;
        color: #374151;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
      }

      .zalo-oa-btn-primary-v9 {
        border-color: #0068ff;
        background: #0068ff;
        color: white;
      }

      .zalo-oa-msgs-v9 {
        flex: 1;
        padding: 24px;
        background: #ffffff;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 16px;
        scroll-behavior: smooth;
      }

      .zalo-oa-row-v9 {
        display: flex;
        width: 100%;
      }

      .zalo-oa-row-v9.customer {
        justify-content: flex-start;
      }

      .zalo-oa-row-v9.staff {
        justify-content: flex-end;
      }

      .zalo-oa-bubble-v9 {
        max-width: 75%;
        padding: 14px 18px;
        border-radius: 8px;
        border: 1px solid #e5eaf2;
        background: #ffffff;
      }

      .zalo-oa-row-v9.staff .zalo-oa-bubble-v9 {
        background: #eff6ff;
        border-color: #bfdbfe;
      }

      .zalo-oa-sender-v9 {
        font-size: 11px;
        color: #64748b;
        margin-bottom: 8px;
        font-weight: 600;
      }

      .zalo-oa-content-v9 {
        font-size: 14px;
        color: #1e293b;
        line-height: 1.5;
        white-space: pre-wrap;
        word-break: break-word;
      }

      .zalo-oa-time-v9 {
        font-size: 11px;
        color: #94a3b8;
        margin-top: 10px;
      }

      .zalo-oa-input-v9 {
        padding: 16px 20px;
        border-top: 1px solid #e5eaf2;
        background: #f8fafc;
        display: flex;
        gap: 12px;
        align-items: center;
        border-bottom-left-radius: 8px;
        border-bottom-right-radius: 8px;
      }

      .zalo-oa-text-v9 {
        flex: 1;
        height: 44px;
        box-sizing: border-box;
        padding: 10px 14px;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        font-size: 14px;
        resize: none;
        background: #ffffff;
        outline: none;
        font-family: inherit;
        line-height: 22px;
        transition: border-color 0.2s;
      }

      .zalo-oa-text-v9:focus {
        border-color: #0068ff;
        box-shadow: 0 0 0 2px rgba(0,104,255,0.1);
      }

      .zalo-oa-send-v9 {
        width: 44px;
        height: 44px;
        box-sizing: border-box;
        border: none;
        border-radius: 8px;
        background: #0068ff;
        color: white;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        transition: background 0.2s;
      }

      .zalo-oa-send-v9:hover {
        background: #0056d6;
      }

      .zalo-oa-send-v9 svg {
        width: 20px;
        height: 20px;
        fill: currentColor;
        transform: translateX(-1px);
      }

      .zalo-oa-send-v9:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }

      .zalo-oa-empty-v9 {
        padding: 40px 20px;
        color: #64748b;
        text-align: center;
      }
    `;

    document.head.appendChild(style);
  }

  function toggleNativeContent(show) {
    var tabBar = findTabBar();
    if (!tabBar || !tabBar.parentNode) return;

    var children = Array.from(tabBar.parentNode.children);

    children.forEach(function (child) {
      if (child === tabBar) return;
      if (child.id === PANEL_ID) return;
      if (child.tagName === "STYLE") return;

      child.style.display = show ? "" : "none";
      child.setAttribute("data-zalo-hidden", show ? "false" : "true");
    });
  }

  function startAutoRefresh(panel, ref) {
    if (chatPoller) clearInterval(chatPoller);

    chatPoller = setInterval(function () {
      load(panel, ref, true);
    }, 3000);
  }

  function stopAutoRefresh() {
    if (chatPoller) {
      clearInterval(chatPoller);
      chatPoller = null;
    }
  }

  async function api(method, args) {
    var response = await fetch("/api/method/" + method, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": window.csrf_token || ""
      },
      body: JSON.stringify(args || {})
    });

    var data = await response.json().catch(function () {
      return {};
    });

    if (!response.ok || data.exc || data.exception) {
      throw new Error(
        data._server_messages ||
        data.exception ||
        data.exc ||
        "API error: " + response.status
      );
    }

    return data.message || data;
  }

  function render(panel, messages) {
    var box = panel.querySelector("[data-zalo-messages]");
    if (!box) return;

    var newHTML = "";

    if (!messages.length) {
      newHTML = '<div class="zalo-oa-empty-v9">Chưa có dữ liệu hội thoại.</div>';
    } else {
      newHTML = messages.map(function (m) {
        return `
          <div class="zalo-oa-row-v9 ${esc(m.type)}">
            <div class="zalo-oa-bubble-v9">
              <div class="zalo-oa-sender-v9">${esc(m.senderName)}</div>
              <div class="zalo-oa-content-v9">${esc(m.content)}</div>
              <div class="zalo-oa-time-v9">${esc(String(m.time || "").slice(0, 19))}</div>
            </div>
          </div>
        `;
      }).join("");
    }

    if (panel._chatHtmlCache !== newHTML) {
      box.innerHTML = newHTML;
      panel._chatHtmlCache = newHTML;
      box.scrollTop = box.scrollHeight;
    }
  }

  async function load(panel, ref, silent) {
    silent = !!silent;

    var box = panel.querySelector("[data-zalo-messages]");
    if (!box) return;

    if (!silent && !panel._chatHtmlCache) {
      box.innerHTML = '<div class="zalo-oa-empty-v9">Đang tải...</div>';
    }

    try {
      var res = await api("zalo_oa_crm.api.chat_v2.get_chat_history", {
        doctype: ref.doctype,
        docname: ref.docname
      });

      var rows = res.messages || [];

      var msgs = rows.map(function (m) {
        var senderType = String(m.sender_type || "").toLowerCase();
        var direction = String(m.direction || "").toLowerCase();

        var isCustomer =
          senderType.indexOf("customer") !== -1 ||
          direction.indexOf("incoming") !== -1;

        return {
          content: m.content || m.message || "",
          senderName: isCustomer ? (m.sender || "Khách hàng") : "Bạn / Frappe",
          type: isCustomer ? "customer" : "staff",
          time: m.timestamp || m.sent_at || ""
        };
      });

      render(panel, msgs);
    } catch (e) {
      console.warn("[Zalo OA Tab] Chưa có hội thoại hoặc lỗi API:", e);
      if (!silent) {
        box.innerHTML = '<div class="zalo-oa-empty-v9">Chưa có dữ liệu hội thoại. Bắt đầu nhắn tin để tạo mới.</div>';
      }
    }
  }

  async function send(panel, ref) {
    var input = panel.querySelector("[data-zalo-input]");
    if (!input) return;

    var msg = input.value.trim();
    if (!msg) return;

    var btns = panel.querySelectorAll("[data-zalo-send]");
    btns.forEach(function (btn) {
      btn.disabled = true;
    });

    try {
      await api("zalo_oa_crm.api.chat_v2.send_message", {
        doctype: ref.doctype,
        docname: ref.docname,
        message: msg
      });

      input.value = "";
      await load(panel, ref, false);
    } catch (e) {
      console.error("[Zalo OA Tab] Lỗi gửi tin nhắn:", e);
      alert("Lỗi gửi tin nhắn");
    } finally {
      btns.forEach(function (btn) {
        btn.disabled = false;
      });
      input.focus();
    }
  }

  function build(ref) {
    injectStyle();

    var panel = document.getElementById(PANEL_ID) || document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "zalo-oa-panel-v9";
    panel._chatHtmlCache = "";

    var host = findPanelHost();
    if (host && panel.parentNode !== host) {
      host.appendChild(panel);
    }

    panel.innerHTML = `
      <div class="zalo-oa-head-v9">
        <div>
          <div class="zalo-oa-title-v9">Zalo OA</div>
          <div class="zalo-oa-sub-v9">${esc(ref.doctype)}: ${esc(ref.docname)}</div>
        </div>
        <div class="zalo-oa-actions-v9">
          <button class="zalo-oa-btn-v9" data-zalo-reload>Tải hội thoại</button>
          <button class="zalo-oa-btn-v9 zalo-oa-btn-primary-v9" data-zalo-focus>Gửi tin nhắn</button>
        </div>
      </div>

      <div class="zalo-oa-msgs-v9" data-zalo-messages></div>

      <div class="zalo-oa-input-v9">
        <textarea class="zalo-oa-text-v9" data-zalo-input placeholder="Nhập tin nhắn..."></textarea>
        <button class="zalo-oa-send-v9" data-zalo-send title="Gửi tin nhắn">
          <svg viewBox="0 0 24 24">
            <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"></path>
          </svg>
        </button>
      </div>
    `;

    panel.querySelector("[data-zalo-reload]").onclick = function () {
      load(panel, ref, false);
    };

    panel.querySelector("[data-zalo-focus]").onclick = function () {
      var input = panel.querySelector("[data-zalo-input]");
      if (input) input.focus();
    };

    panel.querySelectorAll("[data-zalo-send]").forEach(function (btn) {
      btn.onclick = function () {
        send(panel, ref);
      };
    });

    panel.querySelector("[data-zalo-input]").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send(panel, ref);
      }
    });

    load(panel, ref, false);
    startAutoRefresh(panel, ref);
  }

  function show() {
    var ref = getRef();
    if (!ref) return;

    if (window.location.hash !== "#zalo-oa") {
      history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search + "#zalo-oa"
      );
    }

    var tab = document.getElementById(TAB_ID);
    if (tab) tab.classList.add("active");

    build(ref);
    toggleNativeContent(false);
  }

  function hidePanel() {
    var panel = document.getElementById(PANEL_ID);

    if (panel) {
      stopAutoRefresh();
      panel.remove();
    }

    var tab = document.getElementById(TAB_ID);
    if (tab) tab.classList.remove("active");

    toggleNativeContent(true);
  }

  function findTabBarByGeometry() {
  var nodes = Array.from(document.querySelectorAll("div, nav, section"));

  var rows = nodes
    .filter(function (el) {
      if (!visible(el)) return false;
      if (isInsideSidebar(el)) return false;

      var r = el.getBoundingClientRect();
      if (r.width < 500) return false;
      if (r.height < 30 || r.height > 90) return false;
      if (r.top < 90 || r.top > 320) return false;

      var clickableCount = el.querySelectorAll("button, a, [role='tab'], [role='button']").length;
      var childCount = Array.from(el.children).filter(function (child) {
        if (!visible(child)) return false;
        var cr = child.getBoundingClientRect();
        return cr.width > 20 && cr.height > 20 && cr.height < 70;
      }).length;

      return clickableCount >= 3 || childCount >= 4;
    })
    .map(function (el) {
      var text = cleanText(el);
      var hitCount = NATIVE_TABS.filter(function (name) {
        return text.indexOf(name) !== -1;
      }).length;

      var clickableCount = el.querySelectorAll("button, a, [role='tab'], [role='button']").length;
      var childCount = Array.from(el.children).filter(function (child) {
        if (!visible(child)) return false;
        var cr = child.getBoundingClientRect();
        return cr.width > 20 && cr.height > 20 && cr.height < 70;
      }).length;

      return {
        el: el,
        score: hitCount * 20 + clickableCount * 3 + childCount
      };
    });

  rows.sort(function (a, b) {
    if (b.score !== a.score) return b.score - a.score;
    return a.el.getBoundingClientRect().height - b.el.getBoundingClientRect().height;
  });

  return rows[0] ? rows[0].el : null;
}

function createInlineFallbackTabBar() {
  var existed = document.getElementById("zalo_oa_inline_fallback_tabbar_v9");
  if (existed) return existed;

  var host =
    document.querySelector("main") ||
    document.querySelector(".layout-main-section") ||
    document.querySelector(".page-content") ||
    document.querySelector(".page-body") ||
    document.body;

  var bar = document.createElement("div");
  bar.id = "zalo_oa_inline_fallback_tabbar_v9";
  bar.style.cssText = [
    "display:flex",
    "align-items:center",
    "gap:8px",
    "min-height:42px",
    "padding:0 16px",
    "margin:8px 0 0 0",
    "border-bottom:1px solid #e5eaf2",
    "background:#ffffff",
    "box-sizing:border-box",
    "width:100%"
  ].join(";");

  if (host.firstElementChild) {
    host.insertBefore(bar, host.firstElementChild.nextSibling);
  } else {
    host.appendChild(bar);
  }

  console.warn("[Zalo OA Tab] Không bắt được tabbar native, đã tạo fallback inline.");
  return bar;
}

  function ensureTab() {
    var ref = getRef();
    if (!ref) return;

    injectStyle();

    var tab = document.getElementById(TAB_ID);
    if (tab) return;

// Bổ sung chữ "Tập" vào để hệ thống nhận diện đúng
    var attachmentsTab =
      findNativeTab("Attachments") ||
      findNativeTab("Tập tin đính kèm") || 
      findNativeTab("Tệp đính kèm") ||
      findNativeTab("Tệp tin đính kèm") ||
      findNativeTab("Dinh kem") ||
      findNativeTab("Đính kèm");

    var tabBar =
      findTabBar() ||
      findTabBarByGeometry();

    tab = document.createElement("button");
    tab.id = TAB_ID;
    tab.type = "button";
    tab.className = "zalo-oa-tab-v9";
    tab.innerHTML = '<span class="zalo-oa-icon-v9">Z</span><span>Zalo OA</span>';

    tab.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      show();
    }, true);

    if (attachmentsTab) {
      attachmentsTab.insertAdjacentElement("afterend", tab);
      console.log("[Zalo OA Tab] Đã chèn Zalo OA sau Attachments.");
      return;
    }

    if (tabBar) {
      tabBar.appendChild(tab);
      console.log("[Zalo OA Tab] Đã chèn Zalo OA vào tabbar bằng geometry.");
      return;
    }

    var fallbackBar = createInlineFallbackTabBar();
    fallbackBar.appendChild(tab);
    console.log("[Zalo OA Tab] Đã chèn Zalo OA vào fallback inline tabbar.");
  }

  function boot() {
    var ref = getRef();

    if (!ref) {
      hidePanel();
      return;
    }

    ensureTab();

    if (window.location.hash === "#zalo-oa") {
      if (!document.getElementById(PANEL_ID)) {
        show();
      }
    } else {
      hidePanel();
    }
  }

  document.addEventListener("click", function (e) {
    var target = e.target && e.target.closest
      ? e.target.closest("button, a, [role='tab'], div, span")
      : null;

    if (!target) return;

    var text = cleanText(target);

    var isNativeTab = NATIVE_TABS.some(function (name) {
      return text === name || text.indexOf(name + " ") === 0;
    });

    if (isNativeTab && text.indexOf("Zalo OA") === -1) {
      if (window.location.hash === "#zalo-oa") {
        history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search
        );
      }

      hidePanel();
    }
  }, true);

  setInterval(boot, 800);
})();
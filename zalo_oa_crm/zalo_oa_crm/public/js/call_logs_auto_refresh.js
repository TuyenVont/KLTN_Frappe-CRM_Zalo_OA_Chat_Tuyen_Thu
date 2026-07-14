// public/js/call_logs_auto_refresh.js


(function () {
  "use strict";


  // Ngăn file chạy trùng nhiều lần
  if (window.zaloOaCallLogsAutoRefreshLoaded) {
    return;
  }


  window.zaloOaCallLogsAutoRefreshLoaded = true;


  const API_URL =
    "/api/method/zalo_oa_crm.api.call_simulator.get_recent_call_logs";


  // Kiểm tra dữ liệu mới mỗi 2 giây
  const POLL_INTERVAL = 2000;


  let initialized = false;
  let latestCallLogName = null;
  let checking = false;
  let pollingTimer = null;
  let realtimeBound = false;


  /**
   * Kiểm tra hiện tại có đang đứng ở trang Call Logs không.
   */
  function isCallLogsPage() {
    return (window.location.pathname || "").startsWith(
      "/crm/call-logs"
    );
  }


  /**
   * Kiểm tra phần tử đang hiển thị.
   */
  function isVisible(element) {
    if (!element) {
      return false;
    }


    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();


    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      rect.width > 0 &&
      rect.height > 0
    );
  }


  /**
   * Lấy toàn bộ nội dung có thể dùng để nhận diện button.
   */
  function getButtonSearchText(button) {
    return [
      button.getAttribute("title") || "",
      button.getAttribute("aria-label") || "",
      button.getAttribute("data-tooltip") || "",
      button.getAttribute("data-testid") || "",
      button.textContent || "",
      button.innerHTML || "",
    ]
      .join(" ")
      .toLowerCase();
  }


  /**
   * Tìm nút Refresh của CRM Call Logs.
   */
  function findRefreshButton() {
    const buttons = Array.from(
      document.querySelectorAll("button")
    ).filter(isVisible);


    // Cách 1: tìm trực tiếp theo title, aria-label hoặc icon.
    const directMatch = buttons.find(function (button) {
      const text = getButtonSearchText(button);


      return (
        text.includes("refresh") ||
        text.includes("reload") ||
        text.includes("làm mới") ||
        text.includes("lam moi") ||
        text.includes("refresh-cw") ||
        text.includes("rotate-cw")
      );
    });


    if (directMatch) {
      return directMatch;
    }


    // Cách 2: tìm nút Filter.
    // Trong CRM, nút Refresh thường nằm ngay bên trái Filter.
    const filterButton = buttons.find(function (button) {
      const text = getButtonSearchText(button);


      return (
        text.includes("filter") ||
        text.includes("bộ lọc") ||
        text.includes("bo loc")
      );
    });


    if (!filterButton) {
      return null;
    }


    const filterRect = filterButton.getBoundingClientRect();


    // Tìm button nhỏ nằm gần bên trái nút Filter.
    const candidates = buttons
      .filter(function (button) {
        return button !== filterButton;
      })
      .map(function (button) {
        return {
          button: button,
          rect: button.getBoundingClientRect(),
        };
      })
      .filter(function (item) {
        const rect = item.rect;


        const sameRow =
          Math.abs(rect.top - filterRect.top) <= 16;


        const onLeft =
          rect.right <= filterRect.left + 8;


        const closeEnough =
          filterRect.left - rect.right <= 120;


        const iconSized =
          rect.width <= 72 &&
          rect.height <= 72;


        return (
          sameRow &&
          onLeft &&
          closeEnough &&
          iconSized
        );
      })
      .sort(function (a, b) {
        // Ưu tiên button gần Filter nhất
        return b.rect.right - a.rect.right;
      });


    return candidates.length
      ? candidates[0].button
      : null;
  }


  /**
   * Làm mới danh sách Call Logs.
   */
  function refreshCallLogList() {
    if (!isCallLogsPage()) {
      return;
    }


    const refreshButton = findRefreshButton();


    if (refreshButton) {
      refreshButton.click();


      console.info(
        "[Call Logs] Đã tự làm mới danh sách."
      );


      return;
    }


    // Dự phòng nếu không tìm thấy nút refresh.
    // Trang sẽ tự reload, người dùng không cần bấm F5.
    console.warn(
      "[Call Logs] Không tìm thấy nút Refresh, tự tải lại trang."
    );


    window.location.reload();
  }


  /**
   * Lấy Call Log mới nhất từ backend.
   */
  async function fetchLatestCallLog() {
    const url =
      API_URL +
      "?limit=1&_=" +
      Date.now();


    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });


    if (!response.ok) {
      throw new Error(
        "get_recent_call_logs failed: " +
          response.status
      );
    }


    const payload = await response.json();


    // Frappe thường trả dữ liệu trong message
    const data = payload.message || payload;


    const logs = Array.isArray(data.logs)
      ? data.logs
      : [];


    return logs.length
      ? logs[0]
      : null;
  }


  /**
   * Kiểm tra có Call Log mới không.
   */
  async function checkForNewCallLog() {
    if (!isCallLogsPage() || checking) {
      return;
    }


    checking = true;


    try {
      const latest =
        await fetchLatestCallLog();


      const currentName =
        latest && latest.name
          ? latest.name
          : null;


      // Lần đầu chỉ lưu bản ghi hiện tại làm mốc.
      if (!initialized) {
        initialized = true;
        latestCallLogName = currentName;


        console.info(
          "[Call Logs] Mốc ban đầu:",
          currentName
        );


        return;
      }


      // Nếu tên bản ghi mới nhất thay đổi,
      // nghĩa là có Call Log mới.
      if (
        currentName &&
        currentName !== latestCallLogName
      ) {
        console.info(
          "[Call Logs] Phát hiện Call Log mới:",
          currentName
        );


        latestCallLogName = currentName;


        refreshCallLogList();
      }
    } catch (error) {
      console.warn(
        "[Call Logs] Polling warning:",
        error
      );
    } finally {
      checking = false;
    }
  }


  /**
   * Nhận sự kiện realtime nếu Socket.IO hoạt động.
   * Polling vẫn là phương án chính dự phòng.
   */
  function bindRealtime() {
    if (realtimeBound) {
      return;
    }


    const realtime =
      window.frappe &&
      window.frappe.realtime;


    if (!realtime || !realtime.on) {
      console.warn(
        "[Call Logs] Realtime chưa sẵn sàng, dùng polling."
      );


      return;
    }


    realtime.on(
      "crm_call_log_created",
      function (data) {
        console.info(
          "[Call Logs] Nhận sự kiện realtime:",
          data
        );


        if (data && data.name) {
          latestCallLogName = data.name;
          initialized = true;
        }


        refreshCallLogList();
      }
    );


    realtimeBound = true;


    console.info(
      "[Call Logs] Đã đăng ký realtime listener."
    );
  }


  /**
   * Khi chuyển trang SPA về Call Logs,
   * lấy lại mốc dữ liệu mới nhất.
   */
  function handleRouteChange() {
    if (!isCallLogsPage()) {
      return;
    }


    initialized = false;
    latestCallLogName = null;


    checkForNewCallLog();
    bindRealtime();
  }


  /**
   * Khởi động auto refresh.
   */
  function boot() {
    bindRealtime();


    checkForNewCallLog();


    pollingTimer = window.setInterval(
      checkForNewCallLog,
      POLL_INTERVAL
    );


    window.addEventListener(
      "popstate",
      handleRouteChange
    );


    console.info(
      "[Call Logs] Auto refresh đã chạy."
    );
  }


  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      boot,
      {
        once: true,
      }
    );
  } else {
    boot();
  }
})();
(() => {
  if (window.__zaloCallAiSummaryLoaderStarted) {
    return;
  }


  window.__zaloCallAiSummaryLoaderStarted = true;


  const AI_SCRIPT_PATH =
    "/assets/zalo_oa_crm/js/crm_call_ai_summary.js";


  const existingScript = Array.from(
    document.scripts
  ).find((script) =>
    script.src.includes(
      "/assets/zalo_oa_crm/js/crm_call_ai_summary.js"
    )
  );


  if (existingScript) {
    console.log(
      "[Call Logs] AI summary script đã tồn tại"
    );
    return;
  }


  let version = "";


  try {
    const currentScriptUrl =
      document.currentScript?.src;


    if (currentScriptUrl) {
      version =
        new URL(
          currentScriptUrl,
          window.location.origin
        ).searchParams.get("v") || "";
    }
  } catch (error) {
    console.warn(
      "[Call Logs] Không đọc được asset version",
      error
    );
  }


  const script = document.createElement("script");


  script.src =
    AI_SCRIPT_PATH +
    (version
      ? `?v=${encodeURIComponent(version)}`
      : "");


  script.defer = true;
  script.dataset.zaloCallAiSummary = "1";


  script.onload = () => {
    console.log(
      "[Call Logs] AI summary script loaded"
    );
  };


  script.onerror = (error) => {
    window.__zaloCallAiSummaryLoaderStarted = false;


    console.error(
      "[Call Logs] Không tải được AI summary script",
      error
    );
  };


  document.head.appendChild(script);
})();


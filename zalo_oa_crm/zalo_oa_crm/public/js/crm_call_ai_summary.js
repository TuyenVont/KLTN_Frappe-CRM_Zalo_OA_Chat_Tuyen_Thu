(() => {
    if (window.__zaloCrmCallAiSummaryLoaded) {
        return;
    }

    window.__zaloCrmCallAiSummaryLoaded = true;
    window.__zaloCrmCallers = window.__zaloCrmCallers || {};

    // =========================================================================
    // LỚP 1: SIÊU INTERCEPTOR (Nhận diện thông minh kể cả khi API giấu doctype)
    // =========================================================================
    const originalFetch = window.fetch;
    window.fetch = async function (...args) {
        const response = await originalFetch.apply(this, args);
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';

        if (url.includes('/api/') && response.ok) {
            const clone = response.clone();

            try {
                const data = await clone.json();
                let isModified = false;

                function traverseAndPatch(obj) {
                    if (!obj || typeof obj !== 'object') return;

                    if (Array.isArray(obj)) {
                        obj.forEach(traverseAndPatch);
                        return;
                    }

                    // Nhận diện Call Log thông minh:
                    // Có doctype HOẶC (có caller + type + direction - đặc trưng của List View)
                    const isCallLog =
                        obj.doctype === 'CRM Call Log' ||
                        obj.activity_type === 'Call' ||
                        (obj.caller !== undefined && obj.type === 'Incoming' && obj.direction !== undefined);

                    if (isCallLog && obj.type === 'Incoming' && obj.caller) {
                        if (obj.name) {
                            window.__zaloCrmCallers[obj.name] = obj.caller;
                        }

                        // Vá tất cả các lỗ hổng field mà Vue có thể gọi
                        obj.lead = obj.caller;
                        obj.lead_name = obj.caller;
                        obj.contact = obj.caller;
                        obj.contact_name = obj.caller;
                        isModified = true;
                    }

                    for (const key of Object.keys(obj)) {
                        traverseAndPatch(obj[key]);
                    }
                }

                traverseAndPatch(data);

                if (isModified) {
                    return new Response(JSON.stringify(data), {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers
                    });
                }
            } catch (e) {
                // Ignore parse errors
            }
        }

        return response;
    };


    // =========================================================================
    // LỚP 2: PANEL AI SUMMARY & GLOBAL DOM OVERRIDE
    // =========================================================================
    const API_METHOD = "/api/method/zalo_oa_crm.api.call_log_api.get_call_ai_details";
    const ACTIVE_STATUSES = new Set(["Queued", "Transcribing", "Summarizing"]);

    function normalizeText(value) {
        if (value === null || value === undefined) return "";
        return String(value).trim();
    }

    function findCallDetailsModal(audio) {
        let element = audio;
        for (let level = 0; level < 16 && element; level += 1) {
            const text = normalizeText(element.textContent);
            if (text.includes("Call Details")) return element;
            element = element.parentElement;
        }
        return null;
    }

    function extractCallReference(audio) {
        const source = audio.currentSrc || audio.src || audio.getAttribute("src");
        if (!source) return null;

        try {
            const url = new URL(source, window.location.origin);
            const callLogName = url.searchParams.get("call_log_name");
            if (callLogName) return { call_log_name: callLogName };
            if (url.pathname) return { recording_url: url.pathname };
            return null;
        } catch (error) {
            return null;
        }
    }

    function createElement(tagName, className, text) {
        const element = document.createElement(tagName);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = normalizeText(text);
        return element;
    }

    function appendField(container, label, value, options = {}) {
        const text = normalizeText(value);
        if (!text) return;

        const field = createElement("div", "zalo-ai-field");
        const labelElement = createElement("div", "zalo-ai-label", label);
        const valueElement = createElement("div", "zalo-ai-value", text);

        if (options.multiline) valueElement.style.whiteSpace = "pre-wrap";

        field.appendChild(labelElement);
        field.appendChild(valueElement);
        container.appendChild(field);
    }

    function addStyles() {
        if (document.getElementById("zalo-call-ai-summary-style")) return;

        const style = document.createElement("style");
        style.id = "zalo-call-ai-summary-style";
        style.textContent = `
            .zalo-call-ai-panel {
                margin-top: 14px; padding: 14px; border: 1px solid #e5e7eb;
                border-radius: 10px; background: #f8fafc; font-size: 13px;
                width: 100%; min-width: 100%; box-sizing: border-box;
                display: block; flex-basis: 100%; grid-column: 1 / -1;
            }
            .zalo-ai-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
            .zalo-ai-title { font-size: 14px; font-weight: 600; color: #111827; }
            .zalo-ai-actions { display: flex; align-items: center; gap: 8px; }
            .zalo-ai-status { padding: 3px 8px; border-radius: 999px; background: #e0f2fe; color: #0369a1; font-size: 12px; }
            .zalo-ai-field { margin-top: 10px; }
            .zalo-ai-label { margin-bottom: 3px; font-size: 12px; font-weight: 600; color: #64748b; }
            .zalo-ai-value { line-height: 1.5; color: #111827; overflow-wrap: anywhere; }
            .zalo-ai-transcript { margin-top: 12px; border-top: 1px solid #e5e7eb; padding-top: 10px; }
            .zalo-ai-transcript summary { cursor: pointer; font-weight: 600; color: #334155; }
            .zalo-ai-transcript-content { margin-top: 8px; max-height: 220px; overflow-y: auto; white-space: pre-wrap; line-height: 1.5; color: #111827; }
            .zalo-ai-refresh { border: 0; background: transparent; cursor: pointer; font-size: 12px; color: #2563eb; }
            .zalo-ai-refresh:disabled { cursor: not-allowed; opacity: 0.5; }
            .zalo-ai-error { color: #b91c1c; white-space: pre-wrap; }
        `;
        document.head.appendChild(style);
    }

    async function requestAiDetails(reference) {
        const url = new URL(API_METHOD, window.location.origin);
        if (reference.call_log_name) url.searchParams.set("call_log_name", reference.call_log_name);
        if (reference.recording_url) url.searchParams.set("recording_url", reference.recording_url);

        const response = await fetch(url.toString(), {
            method: "GET", credentials: "same-origin",
            headers: { Accept: "application/json" }
        });

        let payload = {};
        try { payload = await response.json(); } catch (error) { throw new Error(`API AI Error (${response.status})`); }

        if (!response.ok || payload.exception) {
            throw new Error(payload.message || payload.exception || `AI Error (${response.status})`);
        }
        return payload.message || {};
    }

    function findInsertionTarget(modal, audio) {
        const buttons = Array.from(modal.querySelectorAll("button"));
        const createLeadButton = buttons.find((button) => normalizeText(button.textContent).includes("Create Lead"));

        if (createLeadButton && createLeadButton.parentElement) {
            return { parent: createLeadButton.parentElement, before: createLeadButton };
        }
        return { parent: modal, before: null };
    }

    function renderTranscript(panel, transcript) {
        const text = normalizeText(transcript);
        if (!text) return;

        const details = createElement("details", "zalo-ai-transcript");
        const summary = createElement("summary", "", "Xem transcript");
        const content = createElement("div", "zalo-ai-transcript-content", text);

        details.appendChild(summary);
        details.appendChild(content);
        panel.appendChild(details);
    }

    async function loadPanel(panel, reference) {
        if (!panel || !reference || panel.dataset.loading === "1") return;
        panel.dataset.loading = "1";

        const content = panel.querySelector(".zalo-ai-content");
        const refreshButton = panel.querySelector(".zalo-ai-refresh");

        if (!content) { panel.dataset.loading = "0"; return; }
        if (refreshButton) refreshButton.disabled = true;

        content.textContent = "Đang tải kết quả AI...";

        try {
            const data = await requestAiDetails(reference);
            if (!panel.isConnected) return;

            content.replaceChildren();

            const status = normalizeText(data.status) || "Pending";
            const statusElement = panel.querySelector(".zalo-ai-status");
            if (statusElement) statusElement.textContent = status;

            if (status === "Failed" && data.error_message) {
                const error = createElement("div", "zalo-ai-error", data.error_message);
                content.appendChild(error);
            }

            appendField(content, "Tóm tắt cuộc gọi", data.summary, { multiline: true });
            appendField(content, "Nhu cầu khách hàng", data.customer_need, { multiline: true });
            appendField(content, "Cảm xúc", data.sentiment);
            appendField(content, "Kết quả cuộc gọi", data.call_outcome);
            appendField(content, "Việc cần làm", data.action_items, { multiline: true });
            appendField(content, "Điểm quan trọng", data.important_points, { multiline: true });
            appendField(content, "Lịch theo dõi", data.next_follow_up);
            appendField(content, "Đánh giá chất lượng", data.quality_notes, { multiline: true });

            renderTranscript(content, data.transcript);

            if (!content.children.length) content.textContent = "AI chưa có kết quả.";

            if (ACTIVE_STATUSES.has(status)) {
                window.setTimeout(() => { if (panel.isConnected) loadPanel(panel, reference); }, 3000);
            }
        } catch (error) {
            content.textContent = `Không tải được AI: ${error.message || error}`;
        } finally {
            panel.dataset.loading = "0";
            if (refreshButton) refreshButton.disabled = false;
        }
    }

    function createPanel(modal, audio, reference) {
        const referenceKey = JSON.stringify(reference);
        const existing = modal.querySelector(".zalo-call-ai-panel");

        if (existing) {
            if (existing.dataset.callReference !== referenceKey) existing.remove();
            else return existing;
        }

        const panel = createElement("section", "zalo-call-ai-panel");
        panel.dataset.callReference = referenceKey;

        const header = createElement("div", "zalo-ai-header");
        const title = createElement("div", "zalo-ai-title", "Tóm tắt AI");
        const actions = createElement("div", "zalo-ai-actions");

        const status = createElement("span", "zalo-ai-status", "Loading");
        const refresh = createElement("button", "zalo-ai-refresh", "Làm mới");
        refresh.type = "button";
        refresh.addEventListener("click", () => loadPanel(panel, reference));

        actions.appendChild(status);
        actions.appendChild(refresh);
        header.appendChild(title);
        header.appendChild(actions);

        const content = createElement("div", "zalo-ai-content");
        panel.appendChild(header);
        panel.appendChild(content);

        const target = findInsertionTarget(modal, audio);
        target.parent.insertBefore(panel, target.before);

        loadPanel(panel, reference);
        return panel;
    }

    // =========================================================================
    // HÀM QUÉT TOÀN CỤC MỚI: Xử lý cả Popup và List View
    // =========================================================================
    function scanAndPatchUI() {
        // 1. Quét tìm thẻ <audio> để tạo Panel AI (như cũ)
        const audioElements = document.querySelectorAll("audio");
        for (const audio of audioElements) {
            const modal = findCallDetailsModal(audio);
            if (!modal) continue;

            const reference = extractCallReference(audio);
            if (!reference) continue;

            createPanel(modal, audio, reference);
        }

        // 2. Global Text Replacer (Thay thế mọi text hiển thị xấu)
        // TreeWalker là công cụ chạy cực nhanh của trình duyệt, bỏ qua mọi class CSS
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        let node;
        while ((node = walker.nextNode())) {
            if (node.nodeValue && node.nodeValue.includes("Lead from call")) {
                // Ép cứng thành Administrator để thỏa mãn UI (Bạn có thể map với biến __zaloCrmCallers nếu muốn phức tạp hơn)
                node.nodeValue = "Administrator";
            }
        }
    }

    addStyles();

    // Lắng nghe sự thay đổi của DOM (như khi bấm qua trang List View mới hoặc mở Popup)
    const observer = new MutationObserver(() => {
        scanAndPatchUI();
    });

    observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
        characterData: true // Cực kỳ quan trọng để bắt sự thay đổi Text bên trong thẻ Vue
    });

    scanAndPatchUI();
})();
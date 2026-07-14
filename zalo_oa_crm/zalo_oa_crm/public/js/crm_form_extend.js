(function() {
    console.log("Zalo OA Force Injector Active");


    function injectZaloTab() {
        // 1. Tìm thanh tab chuẩn dựa trên dữ liệu bạn đã quét từ Elements
        const tabList = document.querySelector('[role="tablist"]');
        if (!tabList || document.getElementById('zalo-oa-custom-tab')) return;


        // 2. Tìm nút Attachments để làm mốc
        const buttons = Array.from(tabList.querySelectorAll('button'));
        const attachmentBtn = buttons.find(btn => btn.textContent.includes('Attachments'));


        if (attachmentBtn) {
            // Tạo nút Zalo OA mới
            const zaloBtn = document.createElement('button');
            zaloBtn.id = 'zalo-oa-custom-tab';
            zaloBtn.setAttribute('role', 'tab');
            zaloBtn.setAttribute('data-state', 'inactive');
            // Copy toàn bộ class từ nút Attachments để đồng bộ giao diện
            zaloBtn.className = attachmentBtn.className + " zalo-oa-btn";
            zaloBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="size-4"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                <span>Zalo OA</span>
            `;
            zaloBtn.style.marginLeft = "20px";


            // Chèn sau nút Attachments
            attachmentBtn.parentNode.insertBefore(zaloBtn, attachmentBtn.nextSibling);


            // Xử lý sự kiện click
            zaloBtn.addEventListener('click', () => {
                // Deactivate các tab khác
                buttons.forEach(btn => btn.setAttribute('data-state', 'inactive'));
                zaloBtn.setAttribute('data-state', 'active');
               
                // Ẩn nội dung cũ và hiện khung chat
                const panels = document.querySelectorAll('[role="tabpanel"]');
                panels.forEach(p => p.style.display = 'none');
               
                renderZaloPanel();
            });
        }
    }


    function renderZaloPanel() {
        if (document.getElementById('zalo-chat-panel')) return;
        const mainContent = document.querySelector('[role="tabpanel"]').parentNode;
        const panel = document.createElement('div');
        panel.id = 'zalo-chat-panel';
        panel.className = "flex flex-col flex-1 p-5 bg-white border rounded-lg mt-4";
        panel.style.minHeight = "400px";
        panel.innerHTML = `
            <div class="font-bold border-b pb-2 mb-4">💬 Zalo OA Chat</div>
            <div id="zalo-messages" class="flex-1 overflow-y-auto bg-gray-50 p-4 rounded mb-4" style="min-height: 300px;"></div>
            <div class="flex gap-2">
                <input id="zalo-input" class="flex-1 border rounded px-3 py-2" placeholder="Nhập tin nhắn..." />
                <button class="bg-blue-600 text-white px-4 py-2 rounded" onclick="handleSend()">Gửi</button>
            </div>
        `;
        mainContent.appendChild(panel);
    }


    // Chạy vòng lặp kiểm tra liên tục để xử lý Single Page App
    setInterval(injectZaloTab, 1000);
})();

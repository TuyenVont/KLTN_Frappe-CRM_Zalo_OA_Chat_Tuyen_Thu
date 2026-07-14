// Auto thêm Zalo OA Chat vào sidebar trái của Frappe Desk
$(document).on('page-change', function () {
    setTimeout(() => {
        // Tìm phân đoạn chứa danh sách item menu của sidebar chính
        let sidebar = $('.standard-sidebar-section, .nested-container .sidebar-items').first();
       
        // Nếu tìm thấy và nút chưa được tạo thì tiến hành chèn vào cuối cụm menu
        if (sidebar.length && !$('.zalo-oa-sidebar-btn').length) {
            sidebar.append(`
                <a class="standard-sidebar-item zalo-oa-sidebar-btn"
                   href="/app/zalo-oa-chat"
                   style="cursor:pointer; display: flex; align-items: center; gap: 8px; padding: 8px 12px;">
                    <span class="sidebar-item-icon" style="display: flex; align-items: center;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"
                             viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                    </span>
                    <span class="sidebar-item-label">Zalo OA Chat</span>
                </a>
            `);
        }
    }, 600); // Tăng nhẹ thời gian delay lên một chút để chắc chắn DOM của Workspace đã render xong
});

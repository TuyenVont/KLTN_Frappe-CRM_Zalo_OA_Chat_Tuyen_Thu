frappe.pages['zalo-oa-chat'].on_page_load = function(wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: 'Zalo OA Chat',
    single_column: true
  });


  new ZaloOAChatPage(page);
};


class ZaloOAChatPage {
  constructor(page) {
    this.page = page;
    this.wrapper = $(page.body);


    this.conversations = [];
    this.currentConversation = null;


    this.filters = {
      search: '',
      status: 'All',
      topic: 'All'
    };


    this.make();
    this.loadConversations();
  }


  make() {
    this.wrapper.html(`
      <style>
        .zalo-chat-page {
          padding: 12px 0;
        }


        .zalo-chat-toolbar {
          display: flex;
          gap: 8px;
          align-items: center;
          margin-bottom: 12px;
          flex-wrap: wrap;
        }


        .zalo-chat-toolbar input,
        .zalo-chat-toolbar select {
          height: 32px;
          border: 1px solid #d1d5db;
          border-radius: 6px;
          padding: 4px 8px;
          background: #fff;
        }


        .zalo-search-input {
          min-width: 260px;
        }


        .zalo-chat-layout {
          display: grid;
          grid-template-columns: 330px minmax(420px, 1fr) 300px;
          height: calc(100vh - 165px);
          min-height: 560px;
          border: 1px solid #e5e7eb;
          border-radius: 10px;
          overflow: hidden;
          background: #fff;
        }


        .zalo-sidebar {
          border-right: 1px solid #e5e7eb;
          background: #f9fafb;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }


        .zalo-section-title {
          font-weight: 700;
          padding: 12px 14px;
          border-bottom: 1px solid #e5e7eb;
          background: #fff;
          color: #111827;
        }


        .zalo-conversation-list {
          overflow-y: auto;
          flex: 1;
        }


        .zalo-conversation-item {
          display: flex;
          gap: 10px;
          padding: 12px;
          cursor: pointer;
          border-bottom: 1px solid #e5e7eb;
          background: #fff;
        }


        .zalo-conversation-item:hover {
          background: #eef6ff;
        }


        .zalo-conversation-item.active {
          background: #dbeafe;
        }


        .zalo-avatar,
        .zalo-profile-avatar {
          width: 40px;
          height: 40px;
          border-radius: 999px;
          background: #2563eb;
          color: #fff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          flex-shrink: 0;
          overflow: hidden;
        }


        .zalo-avatar img,
        .zalo-profile-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }


        .zalo-conversation-content {
          flex: 1;
          min-width: 0;
        }


        .zalo-conversation-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
        }


        .zalo-conversation-name {
          font-weight: 700;
          color: #111827;
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
        }


        .zalo-conversation-time {
          font-size: 11px;
          color: #6b7280;
          white-space: nowrap;
        }


        .zalo-last-message {
          color: #4b5563;
          font-size: 12px;
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
          margin-bottom: 6px;
        }


        .zalo-conversation-meta {
          display: flex;
          gap: 5px;
          align-items: center;
          flex-wrap: wrap;
        }


        .zalo-status,
        .zalo-topic,
        .zalo-tag {
          font-size: 11px;
          padding: 2px 6px;
          border-radius: 999px;
          background: #e5e7eb;
          color: #374151;
        }


        .zalo-unread-badge {
          font-size: 11px;
          min-width: 20px;
          height: 20px;
          padding: 2px 6px;
          border-radius: 999px;
          background: #ef4444;
          color: #fff;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
        }


        .zalo-chat-main {
          display: flex;
          flex-direction: column;
          min-width: 0;
          background: #fff;
        }


        .zalo-chat-header {
          padding: 13px 16px;
          border-bottom: 1px solid #e5e7eb;
          background: #fff;
        }


        .zalo-chat-customer-name {
          font-size: 16px;
          font-weight: 800;
          color: #111827;
        }


        .zalo-chat-subtitle {
          margin-top: 3px;
          font-size: 12px;
          color: #6b7280;
        }


        .zalo-message-list {
          flex: 1;
          overflow-y: auto;
          padding: 18px;
          background: #f3f4f6;
        }


        .zalo-message-row {
          display: flex;
          margin-bottom: 12px;
        }


        .zalo-message-row.customer {
          justify-content: flex-start;
        }


        .zalo-message-row.agent {
          justify-content: flex-end;
        }


        .zalo-message-bubble {
          max-width: 72%;
          padding: 10px 12px;
          border-radius: 14px;
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
          word-break: break-word;
        }


        .zalo-message-row.customer .zalo-message-bubble {
          background: #fff;
          color: #111827;
          border-bottom-left-radius: 4px;
        }


        .zalo-message-row.agent .zalo-message-bubble {
          background: #dbeafe;
          color: #111827;
          border-bottom-right-radius: 4px;
        }


        .zalo-message-content {
          font-size: 14px;
          line-height: 1.45;
        }


        .zalo-message-image {
          display: block;
          max-width: 240px;
          max-height: 180px;
          border-radius: 10px;
          margin-top: 6px;
          border: 1px solid #e5e7eb;
          object-fit: cover;
        }


        .zalo-message-file {
          display: inline-block;
          margin-top: 6px;
          padding: 6px 10px;
          border-radius: 8px;
          background: #f9fafb;
          border: 1px solid #d1d5db;
          color: #2563eb;
          text-decoration: none;
          font-size: 12px;
        }


        .zalo-message-meta {
          margin-top: 6px;
          font-size: 11px;
          color: #6b7280;
        }


        .zalo-message-composer {
          display: flex;
          gap: 8px;
          padding: 12px;
          border-top: 1px solid #e5e7eb;
          background: #fff;
        }


        .zalo-message-input {
          flex: 1;
          height: 36px;
          border: 1px solid #d1d5db;
          border-radius: 8px;
          padding: 6px 10px;
        }


        .zalo-customer-panel {
          border-left: 1px solid #e5e7eb;
          background: #fff;
          overflow-y: auto;
        }


        .zalo-customer-detail {
          padding: 14px;
        }


        .zalo-profile-card {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }


        .zalo-profile-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding-bottom: 12px;
          border-bottom: 1px solid #e5e7eb;
        }


        .zalo-profile-avatar {
          width: 48px;
          height: 48px;
        }


        .zalo-profile-name {
          font-weight: 800;
          color: #111827;
        }


        .zalo-muted {
          color: #6b7280;
          font-size: 12px;
        }


        .zalo-info-block {
          padding-bottom: 10px;
          border-bottom: 1px solid #f3f4f6;
        }


        .zalo-info-label {
          font-size: 12px;
          color: #6b7280;
          margin-bottom: 3px;
        }


        .zalo-info-value {
          font-weight: 600;
          color: #111827;
          word-break: break-word;
        }


        .zalo-tags {
          display: flex;
          gap: 5px;
          flex-wrap: wrap;
        }


        .zalo-empty-state {
          padding: 24px;
          text-align: center;
          color: #6b7280;
        }


        @media (max-width: 1100px) {
          .zalo-chat-layout {
            grid-template-columns: 300px 1fr;
          }


          .zalo-customer-panel {
            display: none;
          }
        }
      </style>


      <div class="zalo-chat-page">
        <div class="zalo-chat-toolbar">
          <input class="zalo-search-input" type="text" placeholder="Tìm theo tên, SĐT, Zalo ID..." />


          <select class="zalo-status-filter">
            <option value="All">Tất cả trạng thái</option>
            <option value="Open">Open</option>
            <option value="Pending">Pending</option>
            <option value="Resolved">Resolved</option>
            <option value="Closed">Closed</option>
          </select>


          <select class="zalo-topic-filter">
            <option value="All">Tất cả chủ đề</option>
            <option value="Tư vấn sản phẩm">Tư vấn sản phẩm</option>
            <option value="Báo giá">Báo giá</option>
            <option value="Vận chuyển">Vận chuyển</option>
            <option value="Bảo hành">Bảo hành</option>
            <option value="Khiếu nại">Khiếu nại</option>
            <option value="Khác">Khác</option>
          </select>


          <button class="btn btn-primary btn-sm zalo-refresh-btn">Làm mới</button>
          <button class="btn btn-default btn-sm zalo-seed-btn">Tạo dữ liệu demo</button>
        </div>


        <div class="zalo-chat-layout">
          <div class="zalo-sidebar">
            <div class="zalo-section-title">Cuộc hội thoại</div>
            <div class="zalo-conversation-list">
              <div class="zalo-empty-state">Đang tải hội thoại...</div>
            </div>
          </div>


          <div class="zalo-chat-main">
            <div class="zalo-chat-header">
              <div class="zalo-chat-customer-name">Chọn một cuộc hội thoại</div>
              <div class="zalo-chat-subtitle">Lịch sử tương tác qua Zalo OA</div>
            </div>


            <div class="zalo-message-list">
              <div class="zalo-empty-state">Chọn khách hàng bên trái để xem lịch sử chat.</div>
            </div>


            <div class="zalo-message-composer">
              <input class="zalo-message-input" type="text" placeholder="Nhập tin nhắn OA giả lập..." disabled />
              <button class="btn btn-primary zalo-send-btn" disabled>Gửi</button>
            </div>
          </div>


          <div class="zalo-customer-panel">
            <div class="zalo-section-title">Hồ sơ khách hàng</div>
            <div class="zalo-customer-detail">
              <div class="zalo-empty-state">Chưa chọn khách hàng.</div>
            </div>
          </div>
        </div>
      </div>
    `);


    this.bindEvents();
  }


  bindEvents() {
    this.wrapper.find('.zalo-refresh-btn').on('click', () => {
      this.loadConversations();
    });


    this.wrapper.find('.zalo-seed-btn').on('click', () => {
      this.seedMockData();
    });


    this.wrapper.find('.zalo-search-input').on('input', frappe.utils.debounce((e) => {
      this.filters.search = $(e.currentTarget).val();
      this.loadConversations();
    }, 400));


    this.wrapper.find('.zalo-status-filter').on('change', (e) => {
      this.filters.status = $(e.currentTarget).val();
      this.loadConversations();
    });


    this.wrapper.find('.zalo-topic-filter').on('change', (e) => {
      this.filters.topic = $(e.currentTarget).val();
      this.loadConversations();
    });


    this.wrapper.find('.zalo-send-btn').on('click', () => {
      this.sendMockMessage();
    });


    this.wrapper.find('.zalo-message-input').on('keypress', (e) => {
      if (e.which === 13) {
        this.sendMockMessage();
      }
    });
  }


  seedMockData() {
    frappe.call({
      method: 'zalo_oa_crm.api.chat.seed_mock_data',
      callback: (r) => {
        if (r.message && r.message.ok) {
          frappe.show_alert({
            message: 'Đã tạo dữ liệu demo',
            indicator: 'green'
          });


          this.currentConversation = null;
          this.loadConversations();
        }
      }
    });
  }


  loadConversations() {
    frappe.call({
      method: 'zalo_oa_crm.api.chat.get_conversations',
      args: {
        search: this.filters.search,
        status: this.filters.status,
        topic: this.filters.topic,
        limit: 100
      },
      callback: (r) => {
        this.conversations = r.message || [];
        this.renderConversationList();


        if (!this.currentConversation && this.conversations.length) {
          this.selectConversation(this.conversations[0]);
          return;
        }


        if (this.currentConversation) {
          const updated = this.conversations.find((c) => c.name === this.currentConversation.name);
          if (updated) {
            this.currentConversation = updated;
            this.renderConversationList();
          }
        }
      }
    });
  }


  renderConversationList() {
    const list = this.wrapper.find('.zalo-conversation-list');


    if (!this.conversations.length) {
      list.html(`<div class="zalo-empty-state">Chưa có cuộc hội thoại.</div>`);
      return;
    }


    const html = this.conversations.map((conv) => {
      const active = this.currentConversation && this.currentConversation.name === conv.name ? 'active' : '';
      const unreadBadge = Number(conv.unread_count || 0) > 0
        ? `<span class="zalo-unread-badge">${this.escape(conv.unread_count)}</span>`
        : '';


      return `
        <div class="zalo-conversation-item ${active}" data-conversation="${this.escape(conv.name)}">
          <div class="zalo-avatar">
            ${conv.avatar_url
              ? `<img src="${this.escape(conv.avatar_url)}" />`
              : `<span>${this.escape(this.getInitials(conv.customer_name))}</span>`
            }
          </div>


          <div class="zalo-conversation-content">
            <div class="zalo-conversation-top">
              <div class="zalo-conversation-name">${this.escape(conv.customer_name || conv.customer)}</div>
              <div class="zalo-conversation-time">${this.escape(this.formatDateTime(conv.last_message_at))}</div>
            </div>


            <div class="zalo-last-message">${this.escape(conv.last_message || 'Chưa có tin nhắn')}</div>


            <div class="zalo-conversation-meta">
              <span class="zalo-status">${this.escape(conv.conversation_status || 'Open')}</span>
              <span class="zalo-topic">${this.escape(conv.topic || 'Chưa phân loại')}</span>
              ${unreadBadge}
            </div>
          </div>
        </div>
      `;
    }).join('');


    list.html(html);


    list.find('.zalo-conversation-item').on('click', (e) => {
      const conversationName = $(e.currentTarget).data('conversation');
      const conversation = this.conversations.find((c) => c.name === conversationName);


      if (conversation) {
        this.selectConversation(conversation);
      }
    });
  }


  selectConversation(conversation) {
    this.currentConversation = conversation;


    this.renderConversationList();
    this.renderCustomerPanel(conversation);
    this.loadMessages(conversation.name);


    this.wrapper.find('.zalo-chat-customer-name').text(conversation.customer_name || conversation.customer);
    this.wrapper.find('.zalo-chat-subtitle').text(
      `${conversation.phone || 'Chưa có SĐT'} · Zalo ID: ${conversation.zalo_user_id || 'N/A'}`
    );


    this.wrapper.find('.zalo-message-input').prop('disabled', false);
    this.wrapper.find('.zalo-send-btn').prop('disabled', false);


    frappe.call({
      method: 'zalo_oa_crm.api.chat.mark_conversation_read',
      args: {
        conversation: conversation.name
      },
      callback: () => {
        conversation.unread_count = 0;


        const item = this.conversations.find((c) => c.name === conversation.name);
        if (item) {
          item.unread_count = 0;
        }


        this.renderConversationList();
      }
    });
  }


  loadMessages(conversationName) {
    frappe.call({
      method: 'zalo_oa_crm.api.chat.get_messages',
      args: {
        conversation: conversationName
      },
      callback: (r) => {
        const data = r.message || {};


        if (Array.isArray(data)) {
          this.renderMessages(data);
          return;
        }


        this.renderMessages(data.messages || []);


        if (data.customer && data.conversation) {
          const panelData = Object.assign({}, data.customer, data.conversation);
          this.renderCustomerPanel(panelData);


          this.wrapper.find('.zalo-chat-customer-name').text(data.customer.customer_name || data.customer.name);
          this.wrapper.find('.zalo-chat-subtitle').text(
            `${data.customer.phone || 'Chưa có SĐT'} · Zalo ID: ${data.customer.zalo_user_id || 'N/A'}`
          );
        }
      }
    });
  }


  renderMessages(messages) {
    const list = this.wrapper.find('.zalo-message-list');


    if (!messages.length) {
      list.html(`<div class="zalo-empty-state">Chưa có tin nhắn trong cuộc hội thoại này.</div>`);
      return;
    }


    const html = messages.map((msg) => {
      const isAgent = ['Agent', 'OA'].includes(msg.sender_type);
      const sideClass = isAgent ? 'agent' : 'customer';


      return `
        <div class="zalo-message-row ${sideClass}">
          <div class="zalo-message-bubble">
            <div class="zalo-message-content">${this.renderMessageContent(msg)}</div>
            <div class="zalo-message-meta">
              ${this.escape(msg.sender_type || '')}
              · ${this.escape(msg.message_type || 'Text')}
              · ${this.escape(this.formatDateTime(msg.sent_at))}
              · ${this.escape(msg.delivery_status || '')}
              ${msg.zalo_message_id ? `<br>ID: ${this.escape(msg.zalo_message_id)}` : ''}
            </div>
          </div>
        </div>
      `;
    }).join('');


    list.html(html);
    list.scrollTop(list[0].scrollHeight);
  }


  renderMessageContent(msg) {
    const content = msg.content || '';
    const escaped = this.escape(content);
    const url = this.extractUrl(content);


    if (msg.message_type === 'Image' && url) {
      return `
        <div>${escaped}</div>
        <img class="zalo-message-image" src="${this.escape(url)}" />
      `;
    }


    if (msg.message_type === 'File' && url) {
      return `
        <div>${escaped}</div>
        <a class="zalo-message-file" href="${this.escape(url)}" target="_blank">
          Mở file
        </a>
      `;
    }


    return escaped;
  }


  renderCustomerPanel(customer) {
    const detail = this.wrapper.find('.zalo-customer-detail');


    if (!customer) {
      detail.html(`<div class="zalo-empty-state">Chưa chọn khách hàng.</div>`);
      return;
    }


    const tags = customer.tags
      ? String(customer.tags).split(',').map((tag) => `<span class="zalo-tag">${this.escape(tag.trim())}</span>`).join('')
      : `<span class="zalo-muted">Chưa có tag</span>`;


    detail.html(`
      <div class="zalo-profile-card">
        <div class="zalo-profile-header">
          <div class="zalo-profile-avatar">
            ${customer.avatar_url
              ? `<img src="${this.escape(customer.avatar_url)}" />`
              : `<span>${this.escape(this.getInitials(customer.customer_name))}</span>`
            }
          </div>


          <div>
            <div class="zalo-profile-name">${this.escape(customer.customer_name || customer.customer || 'Khách hàng')}</div>
            <div class="zalo-muted">${this.escape(customer.phone || 'Chưa có SĐT')}</div>
          </div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Zalo User ID</div>
          <div class="zalo-info-value">${this.escape(customer.zalo_user_id || 'N/A')}</div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Customer Doc</div>
          <div class="zalo-info-value">${this.escape(customer.name || customer.customer || 'N/A')}</div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Trạng thái khách</div>
          <div class="zalo-info-value">${this.escape(customer.customer_status || 'N/A')}</div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Nguồn</div>
          <div class="zalo-info-value">${this.escape(customer.source || 'Zalo OA')}</div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Conversation</div>
          <div class="zalo-info-value">${this.escape(customer.conversation_title || customer.conversation || customer.name || 'N/A')}</div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Deal</div>
          <div class="zalo-info-value">${this.escape(customer.linked_deal || 'Chưa gắn Deal')}</div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Chủ đề</div>
          <div class="zalo-info-value">${this.escape(customer.topic || 'N/A')}</div>
        </div>


        <div class="zalo-info-block">
          <div class="zalo-info-label">Tags</div>
          <div class="zalo-tags">${tags}</div>
        </div>
      </div>
    `);
  }


  sendMockMessage() {
    if (!this.currentConversation) {
      frappe.msgprint('Vui lòng chọn một cuộc hội thoại trước.');
      return;
    }


    const input = this.wrapper.find('.zalo-message-input');
    const content = input.val().trim();


    if (!content) {
      return;
    }


    this.wrapper.find('.zalo-send-btn').prop('disabled', true);


    frappe.call({
      method: 'zalo_oa_crm.api.chat.send_mock_reply',
      args: {
        conversation: this.currentConversation.name,
        text: content
      },
      callback: (r) => {
        this.wrapper.find('.zalo-send-btn').prop('disabled', false);


        if (r.message && r.message.ok) {
          input.val('');
          this.loadMessages(this.currentConversation.name);
          this.loadConversations();
        }
      },
      error: () => {
        this.wrapper.find('.zalo-send-btn').prop('disabled', false);
      }
    });
  }


  extractUrl(text) {
    const match = String(text || '').match(/https?:\/\/[^\s]+/);
    return match ? match[0] : '';
  }


  getInitials(name) {
    if (!name) {
      return '?';
    }


    return String(name)
      .split(' ')
      .filter(Boolean)
      .map((part) => part[0])
      .join('')
      .slice(-2)
      .toUpperCase();
  }


  formatDateTime(value) {
    if (!value) {
      return '';
    }


    try {
      return frappe.datetime.str_to_user(value);
    } catch (e) {
      return value;
    }
  }


  escape(value) {
    return $('<div>').text(value || '').html();
  }
}

frappe.provide('my_ai_assistant');

my_ai_assistant.ChatWidget = class ChatWidget {
    constructor() {
        this.initialized = false;
        this.conversationHistory = [];
        this.maxHistory = 10;
        this.init();
    }

    init() {
        if (this.initialized) return;
        if (!frappe.session?.user || frappe.session.user === 'Guest') {
            setTimeout(() => this.init(), 1000);
            return;
        }
        if (document.getElementById('ai-chat-fab')) return;

        this.render();
        this.bind_events();
        this.testConnection();
        this.initialized = true;
    }

    render() {
        const userInitials = (frappe.session.user_fullname || frappe.session.user || 'U').substring(0, 2).toUpperCase();
        const botSVG = '<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2M9 9a2 2 0 0 0-2 2 2 2 0 0 0 2 2 2 2 0 0 0 2-2 2 2 0 0 0-2-2m6 0a2 2 0 0 0-2 2 2 2 0 0 0 2 2 2 2 0 0 0 2-2 2 2 0 0 0-2-2z"/></svg>';

        document.body.insertAdjacentHTML('beforeend', `
            <!-- Hidden file input for bill image upload -->
            <input type="file" id="ai-bill-file-input" accept="image/*" style="display:none">

            <button id="ai-chat-fab" title="AI Assistant (Ctrl+Shift+A)">
                <span class="fab-icon fab-open"><svg viewBox="0 0 24 24" style="width:26px;height:26px;fill:white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7 9h-2V5h2v6zm0 4h-2v-2h2v2z"/></svg></span>
                <span class="fab-icon fab-close"><svg viewBox="0 0 24 24" style="width:26px;height:26px;fill:white"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></span>
            </button>
            <div id="ai-chat-window">
                <div id="ai-chat-header">
                    <div class="ai-avatar">${botSVG}</div>
                    <div class="ai-header-info">
                        <div class="ai-header-name">SKYERP AI Assistant</div>
                        <div class="ai-header-status">
                            <span class="ai-status-dot" id="ai-status-dot"></span>
                            <span id="ai-status-text">Connecting...</span>
                        </div>
                    </div>
                    <div class="ai-header-actions">
                        <button class="ai-header-btn" id="ai-test-btn" title="Test Connection">
                            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                        </button>
                        <button class="ai-header-btn" id="ai-clear-btn" title="Clear Chat">
                            <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                        </button>
                        <button class="ai-header-btn" id="ai-close-btn" title="Close">
                            <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                        </button>
                    </div>
                </div>
                <div id="ai-quick-actions">
                    <button class="ai-quick-btn" data-q="business summary">📊 Summary</button>
                    <button class="ai-quick-btn" data-q="how many customers">👥 Customers</button>
                    <button class="ai-quick-btn" data-q="how many suppliers">🏢 Suppliers</button>
                    <button class="ai-quick-btn" data-q="total revenue this month">💰 Revenue</button>
                    <button class="ai-quick-btn" data-q="overdue invoices">🚨 Overdue</button>
                    <button class="ai-quick-btn" data-q="help">❓ Help</button>
                </div>
                <div id="ai-chat-messages">
                    <div class="ai-welcome">
                        <div class="ai-welcome-icon">${botSVG}</div>
                        <h4>Welcome to AI Assistant! 👋</h4>
                        <p>I can access your <b>live SKYERP data</b> in real-time.<br>
                        Ask me anything about customers, invoices, sales, or say <b>"create customer ABC Ltd"</b><br><br>
                        📸 <b>New:</b> Click <b>📎</b> to upload a bill image — I'll auto-create the invoice draft!</p>
                    </div>
                </div>

                <!-- Bill type selector (hidden by default, shown after image chosen) -->
                <div id="ai-bill-type-bar" style="display:none;padding:8px 12px;background:#F0FDF4;border-top:1px solid #BBF7D0;align-items:center;gap:8px;flex-wrap:wrap;">
                    <span style="font-size:12px;font-weight:600;color:#15803d;">📄 Invoice type:</span>
                    <button class="ai-bill-type-btn active" data-type="auto"   style="font-size:11px;padding:3px 10px;border-radius:20px;border:1.5px solid #16a34a;background:#16a34a;color:white;cursor:pointer;">Auto Detect</button>
                    <button class="ai-bill-type-btn"        data-type="Sales Invoice"    style="font-size:11px;padding:3px 10px;border-radius:20px;border:1.5px solid #6b7280;background:white;color:#374151;cursor:pointer;">Sales Invoice</button>
                    <button class="ai-bill-type-btn"        data-type="Purchase Invoice" style="font-size:11px;padding:3px 10px;border-radius:20px;border:1.5px solid #6b7280;background:white;color:#374151;cursor:pointer;">Purchase Invoice</button>
                    <button id="ai-bill-cancel-btn" style="margin-left:auto;font-size:11px;padding:3px 10px;border-radius:20px;border:1.5px solid #dc2626;background:white;color:#dc2626;cursor:pointer;">✕ Cancel</button>
                </div>

                <!-- Image preview bar (hidden by default) -->
                <div id="ai-image-preview-bar" style="display:none;padding:8px 12px;background:#EFF6FF;border-top:1px solid #BFDBFE;align-items:center;gap:10px;">
                    <img id="ai-image-thumb" src="" style="width:48px;height:48px;object-fit:cover;border-radius:6px;border:1px solid #93C5FD;">
                    <div style="flex:1;min-width:0;">
                        <div id="ai-image-name" style="font-size:12px;font-weight:600;color:#1d4ed8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"></div>
                        <div style="font-size:11px;color:#6b7280;">Ready to scan · Click <b>Send</b> to create invoice</div>
                    </div>
                    <button id="ai-scan-send-btn" style="padding:6px 14px;background:linear-gradient(135deg,#2563eb,#1d4ed8);color:white;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;">
                        🔍 Scan &amp; Create
                    </button>
                </div>

                <div id="ai-chat-input-area">
                    <!-- Upload bill button -->
                    <button id="ai-upload-bill-btn" title="Upload bill image to auto-create invoice" style="
                        flex-shrink:0;width:36px;height:36px;border-radius:50%;border:none;
                        background:linear-gradient(135deg,#7C3AED,#6D28D9);
                        color:white;cursor:pointer;display:flex;align-items:center;justify-content:center;
                        transition:transform 0.15s,box-shadow 0.15s;box-shadow:0 2px 6px rgba(109,40,217,0.4);
                    ">
                        <svg viewBox="0 0 24 24" style="width:18px;height:18px;fill:white">
                            <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
                        </svg>
                    </button>
                    <textarea id="ai-chat-input" placeholder="Ask a question or upload a bill image 📎 ..." rows="1"></textarea>
                    <button id="ai-send-btn">
                        <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                    </button>
                </div>
                <div id="ai-chat-footer">Powered by Gemini AI · Live SKYERP Data · 📸 Bill Scanner</div>
            </div>
        `);

        this.fab          = document.getElementById('ai-chat-fab');
        this.win          = document.getElementById('ai-chat-window');
        this.msgs         = document.getElementById('ai-chat-messages');
        this.input        = document.getElementById('ai-chat-input');
        this.sendBtn      = document.getElementById('ai-send-btn');
        this.statusDot    = document.getElementById('ai-status-dot');
        this.statusText   = document.getElementById('ai-status-text');
        this.fileInput    = document.getElementById('ai-bill-file-input');
        this.uploadBtn    = document.getElementById('ai-upload-bill-btn');
        this.billTypeBar  = document.getElementById('ai-bill-type-bar');
        this.previewBar   = document.getElementById('ai-image-preview-bar');
        this.imageThumb   = document.getElementById('ai-image-thumb');
        this.imageName    = document.getElementById('ai-image-name');
        this.scanSendBtn  = document.getElementById('ai-scan-send-btn');

        this.isOpen        = false;
        this.isLoading     = false;
        this.pendingImage  = null;   // { base64, fileName, invoiceType }
        this.selectedBillType = 'auto';
        this.botSVG        = botSVG;
        this.userInitials  = userInitials;
    }

    bind_events() {
        this.fab.addEventListener('click', () => this.toggleChat());
        document.getElementById('ai-close-btn').addEventListener('click', () => { this.isOpen = true; this.toggleChat(); });
        document.getElementById('ai-clear-btn').addEventListener('click', () => this.clearChat());
        document.getElementById('ai-test-btn').addEventListener('click', () => this.testConnection(true));

        document.querySelectorAll('.ai-quick-btn').forEach(btn => {
            btn.addEventListener('click', () => this.sendMessage(btn.getAttribute('data-q')));
        });

        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        this.input.addEventListener('input', () => {
            this.input.style.height = 'auto';
            this.input.style.height = Math.min(this.input.scrollHeight, 120) + 'px';
        });

        document.addEventListener('click', (e) => {
            if (this.isOpen && !this.win.contains(e.target) && !this.fab.contains(e.target)) {
                this.isOpen = true;
                this.toggleChat();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'a') {
                e.preventDefault();
                this.toggleChat();
            }
        });

        // ── Bill image upload ────────────────────────────────────────────────
        this.uploadBtn.addEventListener('click', () => {
            this.fileInput.value = '';
            this.fileInput.click();
        });

        this.fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;
            this._handleImageSelected(file);
        });

        // Drag-and-drop onto chat window
        this.win.addEventListener('dragover', (e) => { e.preventDefault(); this.win.style.outline = '2px dashed #7C3AED'; });
        this.win.addEventListener('dragleave', ()  => { this.win.style.outline = ''; });
        this.win.addEventListener('drop', (e) => {
            e.preventDefault();
            this.win.style.outline = '';
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) this._handleImageSelected(file);
        });

        // Bill type selector buttons
        document.querySelectorAll('.ai-bill-type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.ai-bill-type-btn').forEach(b => {
                    b.style.background = 'white';
                    b.style.color = '#374151';
                    b.style.borderColor = '#6b7280';
                });
                btn.style.background = '#16a34a';
                btn.style.color = 'white';
                btn.style.borderColor = '#16a34a';
                this.selectedBillType = btn.getAttribute('data-type');
                if (this.pendingImage) this.pendingImage.invoiceType = this.selectedBillType;
            });
        });

        // Cancel image
        document.getElementById('ai-bill-cancel-btn').addEventListener('click', () => this._clearPendingImage());

        // Scan & create button
        this.scanSendBtn.addEventListener('click', () => this._uploadAndScan());

        // Upload btn hover pulse
        this.uploadBtn.addEventListener('mouseenter', () => {
            this.uploadBtn.style.transform = 'scale(1.1)';
            this.uploadBtn.style.boxShadow = '0 4px 12px rgba(109,40,217,0.5)';
        });
        this.uploadBtn.addEventListener('mouseleave', () => {
            this.uploadBtn.style.transform = '';
            this.uploadBtn.style.boxShadow = '0 2px 6px rgba(109,40,217,0.4)';
        });
    }

    // ── Image handling ─────────────────────────────────────────────────────
    _handleImageSelected(file) {
        const reader = new FileReader();
        reader.onload = (ev) => {
            const base64 = ev.target.result; // includes data:image/...;base64, prefix
            this.pendingImage = {
                base64: base64,
                fileName: file.name,
                invoiceType: this.selectedBillType
            };

            // Show thumbnail + preview bar
            this.imageThumb.src = base64;
            this.imageName.textContent = file.name;
            this.previewBar.style.display  = 'flex';
            this.billTypeBar.style.display = 'flex';

            // Disable text input while image pending
            this.input.placeholder = '📎 Image ready — click "Scan & Create" or type a note...';
        };
        reader.readAsDataURL(file);
    }

    _clearPendingImage() {
        this.pendingImage = null;
        this.fileInput.value = '';
        this.previewBar.style.display  = 'none';
        this.billTypeBar.style.display = 'none';
        this.input.placeholder = 'Ask a question or upload a bill image 📎 ...';
        // Reset bill type buttons
        document.querySelectorAll('.ai-bill-type-btn').forEach(b => {
            b.style.background = 'white';
            b.style.color = '#374151';
            b.style.borderColor = '#6b7280';
        });
        const autoBtn = document.querySelector('.ai-bill-type-btn[data-type="auto"]');
        if (autoBtn) { autoBtn.style.background = '#16a34a'; autoBtn.style.color = 'white'; autoBtn.style.borderColor = '#16a34a'; }
        this.selectedBillType = 'auto';
    }

    _uploadAndScan() {
        if (!this.pendingImage || this.isLoading) return;

        const { base64, fileName, invoiceType } = this.pendingImage;
        this._clearPendingImage();

        this.isLoading = true;
        this.sendBtn.disabled    = true;
        this.scanSendBtn.disabled = true;

        // Show user message with thumbnail
        this._appendBillUserMsg(fileName, base64);

        // Show typing
        const typing = this.showTyping();

        frappe.call({
            method: 'my_ai_assistant.ai_helper.scan_bill_image',
            args: {
                image_data:   base64,
                file_name:    fileName,
                invoice_type: invoiceType || 'auto'
            },
            callback: (r) => {
                typing.remove();
                this.isLoading = false;
                this.sendBtn.disabled    = false;
                this.scanSendBtn.disabled = false;

                try {
                    let msg = r.message;
                    if (!msg) {
                        this.appendAIMsg({ type: 'error', message: 'No response received from bill scanner.' });
                        return;
                    }
                    if (typeof msg === 'string') {
                        try { msg = JSON.parse(msg); } catch(e) { msg = { type: 'text', message: msg }; }
                    }
                    this.appendAIMsg(msg);
                } catch(e) {
                    this.appendAIMsg({ type: 'error', message: 'Error processing bill: ' + e.message });
                }
                this.input.focus();
            },
            error: (err) => {
                typing.remove();
                this.isLoading = false;
                this.sendBtn.disabled    = false;
                this.scanSendBtn.disabled = false;
                console.error('Bill scan error:', err);
                this.appendAIMsg({ type: 'error', message: '❌ Error scanning bill. Please try again.' });
                this.input.focus();
            }
        });
    }

    _appendBillUserMsg(fileName, base64) {
        const w = this.msgs.querySelector('.ai-welcome');
        if (w) w.remove();

        const div = document.createElement('div');
        div.className = 'ai-msg user';
        div.innerHTML = `
            <div class="ai-msg-content">
                <div class="ai-msg-bubble" style="padding:8px;">
                    <div style="font-size:12px;color:#6b7280;margin-bottom:6px;">📸 Bill uploaded</div>
                    <img src="${base64}" style="max-width:180px;max-height:180px;border-radius:8px;object-fit:cover;display:block;border:1px solid rgba(255,255,255,0.3);">
                    <div style="font-size:11px;margin-top:5px;color:#e0e7ff;opacity:0.8;">${this.escapeHtml(fileName)}</div>
                </div>
                <div class="ai-msg-time">${this.getTime()}</div>
            </div>
            <div class="ai-msg-avatar">${this.userInitials}</div>
        `;
        this.msgs.appendChild(div);
        this.msgs.scrollTop = this.msgs.scrollHeight;
    }

    // ── Chat helpers (unchanged) ───────────────────────────────────────────
    toggleChat() {
        this.isOpen = !this.isOpen;
        this.fab.classList.toggle('open', this.isOpen);
        this.win.classList.toggle('open', this.isOpen);
        if (this.isOpen) {
            setTimeout(() => this.input.focus(), 300);
        }
    }

    clearChat() {
        this.conversationHistory = [];
        this._clearPendingImage();
        this.msgs.innerHTML = `
            <div class="ai-welcome">
                <div class="ai-welcome-icon">${this.botSVG}</div>
                <h4>Chat cleared! 🗑️</h4>
                <p>Ask me anything about your SKYERP data.<br>📸 Click <b>📎</b> to upload a bill image.</p>
            </div>
        `;
    }

    getTime() {
        return new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    }

    testConnection(showToast = false) {
        frappe.call({
            method: 'my_ai_assistant.ai_helper.test_connection',
            callback: function(r) {
                var statusEl = document.querySelector('.ai-header-status');
                if (r && r.message && r.message.success) {
                    if (statusEl) statusEl.innerHTML = '<span class="ai-status-dot"></span>Live data · Connected';
                } else {
                    if (statusEl) statusEl.innerHTML = '<span style="color:#fca5a5;font-size:11px">⚠️ Check API key</span>';
                }
            },
            error: function() {
                var statusEl = document.querySelector('.ai-header-status');
                if (statusEl) statusEl.innerHTML = '<span style="color:#fca5a5;font-size:11px">⚠️ No connection</span>';
            }
        });
    }

    setStatus(status, text) {
        const colors = { connected: '#4ADE80', connecting: '#FBBF24', error: '#EF4444' };
        this.statusDot.style.background = colors[status] || colors.connecting;
        this.statusText.textContent = text;
    }

    renderResponse(response) {
        if (typeof response === 'string') {
            return response.replace(/\n/g, '<br>');
        }

        const type    = response.type || 'text';
        const message = response.message || '';
        let html = '';

        switch(type) {
            case 'success':
                html = `<div style="color:#16a34a;font-weight:500;font-size:14px">${message}</div>`;
                if (response.link) {
                    const route = response.link.replace('/app/', '');
                    html += `<div style="margin-top:8px">
                        <a href="${response.link}"
                           onclick="frappe.set_route('${route}');return false;"
                           style="display:inline-block;padding:6px 14px;background:linear-gradient(135deg,#10B981,#059669);color:white;border-radius:8px;font-size:12px;text-decoration:none;font-weight:500;">
                            🔗 Open ${response.doctype || 'Record'} →
                        </a>
                    </div>`;
                }
                break;

            case 'error':
                html = `<div style="color:#dc2626;font-size:13.5px;background:#FEF2F2;padding:10px;border-radius:8px;border-left:3px solid #dc2626;">❌ ${message}</div>`;
                break;

            case 'info':
                html = `<div style="color:#d97706;font-size:13.5px;background:#FFFBEB;padding:10px;border-radius:8px;border-left:3px solid #d97706;">⚠️ ${message}</div>`;
                if (response.link) {
                    const route = response.link.replace('/app/', '');
                    html += `<div style="margin-top:6px">
                        <a href="${response.link}"
                           onclick="frappe.set_route('${route}');return false;"
                           style="color:#5B4FE9;font-size:12px;text-decoration:none;font-weight:500;">
                            🔗 View Record →
                        </a>
                    </div>`;
                }
                break;

            case 'list':
                html = `<div style="font-weight:600;margin-bottom:10px;color:#374151;">${message}</div>`;
                const items = response.items || response.results || [];
                const dt = (response.doctype || '').toLowerCase().replace(/ /g, '-');
                if (items.length > 0) {
                    html += '<div style="background:white;border-radius:8px;border:1px solid #E5E7EB;overflow:hidden;">';
                    items.forEach((item, idx) => {
                        const isLast = idx === items.length - 1;
                        const borderStyle = isLast ? '' : 'border-bottom:1px solid #F3F4F6;';
                        if (dt) {
                            const route = dt + '/' + item;
                            html += `<div style="padding:10px 14px;${borderStyle}font-size:13px;transition:background 0.2s;">
                                <a href="/app/${route}"
                                   onclick="frappe.set_route('${route}');return false;"
                                   style="color:#5B4FE9;text-decoration:none;font-weight:500;">
                                    → ${item}
                                </a>
                            </div>`;
                        } else {
                            html += `<div style="padding:10px 14px;${borderStyle}font-size:13px;color:#374151;">• ${item}</div>`;
                        }
                    });
                    html += '</div>';
                }
                break;

            default:
                const messageStr = typeof message === 'string' ? message : String(message);
                html = `<div style="font-size:13.5px;line-height:1.7;color:#374151;">${messageStr.replace(/\n/g, '<br>')}</div>`;
        }

        return html;
    }

    appendUserMsg(text) {
        const w = this.msgs.querySelector('.ai-welcome');
        if (w) w.remove();

        const div = document.createElement('div');
        div.className = 'ai-msg user';
        div.innerHTML = `
            <div class="ai-msg-content">
                <div class="ai-msg-bubble">${this.escapeHtml(text)}</div>
                <div class="ai-msg-time">${this.getTime()}</div>
            </div>
            <div class="ai-msg-avatar">${this.userInitials}</div>
        `;
        this.msgs.appendChild(div);
        this.msgs.scrollTop = this.msgs.scrollHeight;

        this.conversationHistory.push({role: 'user', content: text});
        this.trimHistory();
    }

    appendAIMsg(response) {
        const w = this.msgs.querySelector('.ai-welcome');
        if (w) w.remove();

        const div = document.createElement('div');
        div.className = 'ai-msg ai';
        const html = this.renderResponse(response);
        div.innerHTML = `
            <div class="ai-msg-avatar">${this.botSVG}</div>
            <div class="ai-msg-content">
                <div class="ai-msg-bubble">${html}</div>
                <div class="ai-msg-time">${this.getTime()}</div>
            </div>
        `;
        this.msgs.appendChild(div);
        this.msgs.scrollTop = this.msgs.scrollHeight;

        const msgText = typeof response === 'object' ? (response.message || '') : String(response);
        this.conversationHistory.push({role: 'assistant', content: msgText});
        this.trimHistory();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    trimHistory() {
        if (this.conversationHistory.length > this.maxHistory * 2) {
            this.conversationHistory = this.conversationHistory.slice(-this.maxHistory * 2);
        }
    }

    showTyping() {
        const div = document.createElement('div');
        div.className = 'ai-msg ai typing';
        div.id = 'ai-typing-indicator';
        div.innerHTML = `
            <div class="ai-msg-avatar">${this.botSVG}</div>
            <div class="ai-typing-bubble">
                <div class="ai-typing-dot"></div>
                <div class="ai-typing-dot"></div>
                <div class="ai-typing-dot"></div>
            </div>
        `;
        this.msgs.appendChild(div);
        this.msgs.scrollTop = this.msgs.scrollHeight;
        return div;
    }

    sendMessage(question) {
        // If there is a pending image and user presses send, scan it
        if (this.pendingImage && !question) {
            this._uploadAndScan();
            return;
        }

        question = (question || this.input.value).trim();
        if (!question || this.isLoading) return;

        this.input.value = '';
        this.input.style.height = 'auto';
        this.isLoading = true;
        this.sendBtn.disabled = true;

        this.appendUserMsg(question);
        const typing = this.showTyping();

        const args = {
            question: question,
            doctype: '',
            conversation_history: JSON.stringify(this.conversationHistory.slice(-5))
        };

        frappe.call({
            method: 'my_ai_assistant.ai_helper.ask_ai',
            args: args,
            callback: (r) => {
                typing.remove();
                this.isLoading = false;
                this.sendBtn.disabled = false;

                try {
                    let msg = r.message;
                    if (!msg) {
                        this.appendAIMsg({ type: 'error', message: 'No response received.' });
                    } else {
                        if (typeof msg === 'string') {
                            msg = msg.trim();
                            try { msg = JSON.parse(msg); } catch(e) { msg = { type: 'text', message: msg }; }
                        }
                        if (typeof msg === 'object' && msg !== null) {
                            if (msg.type && msg.message !== undefined) {
                                this.appendAIMsg(msg);
                            } else {
                                this.appendAIMsg({ type: 'text', message: JSON.stringify(msg) });
                            }
                        } else {
                            this.appendAIMsg({ type: 'text', message: String(msg) });
                        }
                    }
                } catch(e) {
                    this.appendAIMsg({ type: 'error', message: 'Error: ' + e.message });
                }

                this.input.focus();
            },
            error: (err) => {
                typing.remove();
                this.isLoading = false;
                this.sendBtn.disabled = false;
                console.error("API Error:", err);
                this.appendAIMsg({
                    type: 'error',
                    message: 'Connection error. Please check your internet connection and try again.'
                });
                this.input.focus();
            }
        });
    }
};

// Initialize widget
function initAIWidget() {
    if (!document.getElementById('ai-chat-fab') && frappe.session?.user && frappe.session.user !== 'Guest') {
        new my_ai_assistant.ChatWidget();
    }
}

if (frappe.boot) {
    setTimeout(initAIWidget, 800);
} else {
    $(document).on('frappe-ready', () => setTimeout(initAIWidget, 800));
}

$(document).on('page-change', () => setTimeout(initAIWidget, 500));
$(document).ready(() => setTimeout(initAIWidget, 1500));

document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        const existing = document.getElementById('ai-chat-fab');
        if (existing) existing.click();
    }
});

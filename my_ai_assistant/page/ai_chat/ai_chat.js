frappe.pages['ai-chat'].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: 'AI Business Assistant',
        single_column: true
    });

    $(wrapper).find('.page-content').html(`
        <div style="padding:20px; max-width:900px; margin:auto">
            <div style="background:linear-gradient(135deg, #5B4FE9 0%, #06B6D4 100%); color:white; padding:24px 28px; border-radius:16px; margin-bottom:20px;">
                <div style="display:flex; align-items:center; gap:16px;">
                    <div style="width:56px;height:56px;background:rgba(255,255,255,0.2);border-radius:14px;display:flex;align-items:center;justify-content:center;">
                        <svg viewBox="0 0 24 24" style="width:32px;height:32px;fill:white"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/></svg>
                    </div>
                    <div>
                        <div style="font-size:22px;font-weight:600;margin-bottom:4px;">ERPNext AI Business Assistant</div>
                        <div style="opacity:0.9;font-size:14px;">Ask anything about your business data - I have access to real-time ERPNext information</div>
                    </div>
                </div>
            </div>

            <div id="chat-history" style="height:500px; overflow-y:auto; border:1px solid #E5E7EB; padding:20px; margin-bottom:16px; border-radius:12px; background:#F9FAFB; font-size:14px;"></div>

            <div style="margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap;">
                <button class="btn btn-default quick-ask-btn" data-q="how many customers" style="border-radius:20px;font-size:12px;">👥 Customers</button>
                <button class="btn btn-default quick-ask-btn" data-q="how many suppliers" style="border-radius:20px;font-size:12px;">🏢 Suppliers</button>
                <button class="btn btn-default quick-ask-btn" data-q="list all items" style="border-radius:20px;font-size:12px;">📦 Items</button>
                <button class="btn btn-default quick-ask-btn" data-q="total revenue" style="border-radius:20px;font-size:12px;">💰 Revenue</button>
                <button class="btn btn-default quick-ask-btn" data-q="overdue invoices" style="border-radius:20px;font-size:12px;">🚨 Overdue</button>
                <button class="btn btn-default quick-ask-btn" data-q="help" style="border-radius:20px;font-size:12px;">❓ Help</button>
                <button class="btn btn-warning" id="upload-doc-btn" style="border-radius:20px;font-size:12px;">📷 Scan Document</button>
            </div>

            <input type="file" id="document-upload" accept="image/*" style="display:none;" />

            <div id="upload-status" style="display:none;margin-bottom:12px;padding:12px;background:#FEF3C7;border-radius:8px;border:1px solid #FCD34D;">
                <div style="display:flex;align-items:center;gap:8px;">
                    <span class="spinner" style="width:16px;height:16px;border:2px solid #F59E0B;border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite;"></span>
                    <span id="upload-text">Processing document image...</span>
                </div>
            </div>

            <div style="display:flex; gap:12px; background:white; padding:16px; border-radius:12px; border:1px solid #E5E7EB;">
                <input id="user-question" class="form-control"
                    placeholder="e.g. How many customers do I have? List all items. What's my total revenue?"
                    style="flex:1;border-radius:10px;padding:12px 16px;font-size:14px;border:1.5px solid #E5E7EB;"/>
                <button class="btn btn-primary" id="ask-btn" style="border-radius:10px;padding:12px 24px;font-weight:600;">
                    <span style="display:flex;align-items:center;gap:6px;">
                        <svg viewBox="0 0 24 24" style="width:18px;height:18px;fill:white"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                        Ask AI
                    </span>
                </button>
            </div>

            <p style="color:#9CA3AF; font-size:12px; margin-top:12px; text-align:center;">
                <span style="display:inline-flex;align-items:center;gap:6px;">
                    <span style="width:8px;height:8px;background:#10B981;border-radius:50%;"></span>
                    AI has live access to your ERPNext data · Responses are generated using Gemini AI
                </span>
            </p>
        </div>
    `);

    // Welcome message
    appendMessage('AI', `<div style="color:#374151;font-size:14px;line-height:1.6">
        <b>Hello ${frappe.session.user_fullname || 'there'}! 👋</b><br><br>
        I'm your SkyERP AI Assistant with access to your live business data. I can help you with:<br><br>
        <b>📊 Data Queries:</b> "How many customers?", "List all items", "Total sales"<br>
        <b>🔍 Record Lookup:</b> "Find customer ABC", "Show invoice SINV-001"<br>
        <b>➕ Create Records:</b> "Create customer John Doe", "Add employee"<br>
        <b>📷 Document Scanning:</b> Upload invoices, orders for auto-entry<br>
        <b>💡 Business Insights:</b> Revenue analysis, overdue, stock levels<br><br>
        Type your question or upload a document image!
    </div>`, true);

    function appendMessage(sender, text, isAI) {
        const avatar = isAI
            ? '<div style="width:36px;height:36px;background:linear-gradient(135deg,#5B4FE9,#06B6D4);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:white"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/></svg></div>'
            : '<div style="width:36px;height:36px;background:#374151;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;color:white;font-size:13px;font-weight:600;">' + (frappe.session.user_fullname || 'U').substring(0,2).toUpperCase() + '</div>';

        const bubbleStyle = isAI
            ? 'background:white;border:1px solid #E5E7EB;border-bottom-left-radius:4px;'
            : 'background:linear-gradient(135deg,#5B4FE9,#6D5FED);color:white;border-bottom-right-radius:4px;';

        $('#chat-history').append(`
            <div style="display:flex;gap:12px;margin-bottom:16px;${isAI ? '' : 'flex-direction:row-reverse;'}">
                ${avatar}
                <div style="max-width:80%;">
                    <div style="padding:14px 18px;border-radius:16px;font-size:14px;line-height:1.6;${bubbleStyle}">${text}</div>
                    <div style="font-size:11px;color:#9CA3AF;margin-top:4px;${isAI ? '' : 'text-align:right;'}">${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</div>
                </div>
            </div>
        `);
        $('#chat-history').scrollTop($('#chat-history')[0].scrollHeight);
    }

    function showTyping() {
        $('#chat-history').append(`
            <div id="typing-indicator" style="display:flex;gap:12px;margin-bottom:16px;">
                <div style="width:36px;height:36px;background:linear-gradient(135deg,#5B4FE9,#06B6D4);border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;"><svg viewBox="0 0 24 24" style="width:20px;height:20px;fill:white"><path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1H2a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/></svg></div>
                <div style="background:white;border:1px solid #E5E7EB;border-radius:16px;border-bottom-left-radius:4px;padding:16px 20px;display:flex;gap:5px;align-items:center;">
                    <div style="width:7px;height:7px;background:#5B4FE9;border-radius:50%;animation:dotPulse 1.2s infinite;"></div>
                    <div style="width:7px;height:7px;background:#5B4FE9;border-radius:50%;animation:dotPulse 1.2s infinite 0.2s;"></div>
                    <div style="width:7px;height:7px;background:#5B4FE9;border-radius:50%;animation:dotPulse 1.2s infinite 0.4s;"></div>
                </div>
            </div>
        `);
        $('#chat-history').scrollTop($('#chat-history')[0].scrollHeight);
    }

    // Add CSS animations
    if (!$('#ai-dot-animation').length) {
        $('head').append(`<style id="ai-dot-animation">
            @keyframes dotPulse { 0%,100%{transform:translateY(0);opacity:.4} 50%{transform:translateY(-5px);opacity:1} }
            @keyframes spin { to { transform: rotate(360deg); } }
        </style>`);
    }

    // Quick ask buttons
    $('.quick-ask-btn').on('click', function() {
        $('#user-question').val($(this).data('q'));
        $('#ask-btn').click();
    });

    $('#ask-btn').on('click', function() {
        var question = $('#user-question').val().trim();
        if (!question) return;

        appendMessage('You', question, false);
        $('#user-question').val('');
        $('#ask-btn').prop('disabled', true).html('<span class="flex align-center gap-2"><span class="spinner" style="width:16px;height:16px;border:2px solid white;border-top-color:transparent;"></span>Thinking...</span>');
        showTyping();

        frappe.call({
            method: 'my_ai_assistant.api.get_ai_response',
            args: { prompt: question },
            callback: function(r) {
                $('#typing-indicator').remove();
                var response = r.message;
                var html = '';

                if (typeof response === 'string') {
                    try { response = JSON.parse(response); } catch(e) {}
                }

                if (typeof response === 'object' && response.message) {
                    html = response.message;
                    if (response.link) {
                        var route = response.link.replace('/app/', '');
                        html += '<div style="margin-top:10px;"><a href="' + response.link + '" onclick="frappe.set_route(\'' + route + '\');return false;" style="display:inline-block;padding:6px 14px;background:linear-gradient(135deg,#10B981,#059669);color:white;border-radius:8px;font-size:12px;text-decoration:none;font-weight:500;">🔗 Open ' + (response.doctype || 'Record') + ' →</a></div>';
                    }
                } else {
                    html = String(response);
                }

                appendMessage('AI Assistant', html, true);
                $('#ask-btn').prop('disabled', false).html('<span style="display:flex;align-items:center;gap:6px;"><svg viewBox="0 0 24 24" style="width:18px;height:18px;fill:white"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>Ask AI</span>');
            },
            error: function(err) {
                $('#typing-indicator').remove();
                appendMessage('Error', '<div style="color:#dc2626;">❌ Something went wrong. Please check console for details.</div>', true);
                $('#ask-btn').prop('disabled', false).html('<span style="display:flex;align-items:center;gap:6px;"><svg viewBox="0 0 24 24" style="width:18px;height:18px;fill:white"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>Ask AI</span>');
            }
        });
    });

    $('#user-question').on('keypress', function(e) {
        if (e.which === 13) $('#ask-btn').click();
    });

    // Document Image Upload Handlers
    $('#upload-doc-btn').on('click', function() {
        $('#document-upload').click();
    });

    $('#document-upload').on('change', function(e) {
        var file = e.target.files[0];
        if (!file) return;

        // Show processing status
        $('#upload-status').show();
        $('#upload-text').text('Reading document image...');

        // Read file as base64
        var reader = new FileReader();
        reader.onload = function(event) {
            var base64Data = event.target.result.split(',')[1];

            appendMessage('You', '<div style="color:#6b7280;">📎 Uploaded: ' + file.name + '</div>', false);
            showTyping();

            frappe.call({
                method: 'my_ai_assistant.api.process_document_image_api',
                args: {
                    image_data: base64Data,
                    document_type: 'auto'
                },
                callback: function(r) {
                    $('#upload-status').hide();
                    $('#typing-indicator').remove();

                    var response = r.message;
                    var html = '';

                    if (typeof response === 'object' && response.message) {
                        html = response.message;
                        if (response.link) {
                            var route = response.link.replace('/app/', '');
                            html += '<div style="margin-top:10px;"><a href="' + response.link + '" onclick="frappe.set_route(\'' + route + '\');return false;" style="display:inline-block;padding:6px 14px;background:linear-gradient(135deg,#10B981,#059669);color:white;border-radius:8px;font-size:12px;text-decoration:none;font-weight:500;"> Open ' + (response.doctype || 'Record') + ' </a></div>';
                        }
                    } else {
                        html = String(response);
                    }

                    appendMessage('AI Assistant', html, true);
                },
                error: function(err) {
                    $('#upload-status').hide();
                    $('#typing-indicator').remove();
                    appendMessage('Error', '<div style="color:#dc2626;">❌ Failed to process document. Please try a clearer image.</div>', true);
                }
            });
        };
        reader.readAsDataURL(file);
        $(this).val(''); // Reset input
    });
};

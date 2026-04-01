"""
AI Assistant Core - Main orchestrator
Ties together all services for clean architecture
"""

import frappe
import json
import re

# Import services
from my_ai_assistant.config.settings import get_api_key, is_feature_enabled
from my_ai_assistant.services.doctype_service import (
    detect_doctype_from_question,
    get_doctype_structure,
    discover_all_doctypes
)
from my_ai_assistant.services.entity_service import extract_entities_from_question
from my_ai_assistant.services.data_service import (
    safe_get_list,
    safe_get_full_doc,
    get_entity_statistics,
    get_business_overview,
    safe_count
)
from my_ai_assistant.services.document_service import create_document
from my_ai_assistant.services.ai_service import generate_ai_response
from my_ai_assistant.services.image_service import process_document_image

@frappe.whitelist()
def ask_ai(question, doctype="", conversation_history=""):
    """
    Main AI assistant endpoint - handles ALL user questions globally
    """
    # Check API key
    if not get_api_key():
        return {
            "type": "error",
            "message": """🔑 API key not configured.<br>
            Run: <code>bench --site skydot set-config vertex_api_key YOUR_KEY</code>"""
        }

    # Handle greetings
    q_clean = re.sub(r"[!?.]+$", "", question.lower().strip())
    greetings = ["hi", "hello", "hey", "good morning", "good evening", "good afternoon"]
    if q_clean in greetings:
        return get_greeting_response()

    # Handle help
    if q_clean in ["help", "what can you do", "commands", "?"]:
        return get_help_response()

    # Gather live data based on question context
    live_data = gather_live_data(question)

    # Generate AI response
    ai_response = generate_ai_response(question, live_data, conversation_history)

    # Handle document creation
    if isinstance(ai_response, dict) and ai_response.get("type") == "create":
        return create_document(
            ai_response.get("doctype"),
            ai_response.get("data", {})
        )

    return ai_response

@frappe.whitelist()
def process_image(image_data, document_type="auto"):
    """
    Process document image and create ERPNext entry
    Supports: Sales Invoice, Purchase Invoice, Sales Order, Purchase Order
    """
    if not is_feature_enabled("image_processing"):
        return {"type": "error", "message": "Image processing is disabled for this site."}

    return process_document_image(image_data, document_type)

@frappe.whitelist()
def discover_doctypes(category=None):
    """
    Discover available doctypes in the system
    """
    try:
        result = discover_all_doctypes(category)
        return {"type": "success", "data": result}
    except Exception as e:
        return {"type": "error", "message": str(e)}

@frappe.whitelist()
def get_doctype_info(doctype):
    """
    Get structure info for a doctype (for AI to understand creation)
    """
    try:
        info = get_doctype_structure(doctype)
        return {"type": "success", "data": info}
    except Exception as e:
        return {"type": "error", "message": str(e)}

def gather_live_data(question):
    """
    Gather relevant live data based on question content
    This is the key to global search capability
    """
    data = {}
    q = question.lower()
    today = frappe.utils.today()

    # Detect entities mentioned
    entities = extract_entities_from_question(question)

    # Detect doctype intent
    detected_dt, doc_id = detect_doctype_from_question(question)

    # If specific document ID mentioned
    if detected_dt and doc_id and detected_dt != "GSTIN":
        data["specific_document"] = safe_get_full_doc(detected_dt, doc_id)
        return data

    # If GSTIN mentioned
    if detected_dt == "GSTIN":
        from my_ai_assistant.utils.gstin_helper import get_gstin_details
        data["gstin_details"] = get_gstin_details(doc_id)
        return data

    # Include business overview (always useful)
    data["overview"] = get_business_overview()

    # Entity-specific data gathering
    if entities.get("customer"):
        cid = entities["customer"]
        data["entity_customer"] = safe_get_full_doc("Customer", cid)
        data["entity_customer_stats"] = get_entity_statistics("Customer", cid)
        data["entity_customer_name"] = entities.get("customer_display", cid)

    if entities.get("supplier"):
        sid = entities["supplier"]
        data["entity_supplier"] = safe_get_full_doc("Supplier", sid)
        data["entity_supplier_stats"] = get_entity_statistics("Supplier", sid)
        data["entity_supplier_name"] = entities.get("supplier_display", sid)

    if entities.get("item"):
        iid = entities["item"]
        data["entity_item"] = safe_get_full_doc("Item", iid)
        data["entity_item_stats"] = get_entity_statistics("Item", iid)
        data["entity_item_name"] = entities.get("item_display", iid)

    if entities.get("employee"):
        eid = entities["employee"]
        data["entity_employee"] = safe_get_full_doc("Employee", eid)
        data["entity_employee_stats"] = get_entity_statistics("Employee", eid)
        data["entity_employee_name"] = entities.get("employee_display", eid)

    # Keyword-based data gathering for broader context
    # Customers
    if any(w in q for w in ["customer", "customers", "client", "buyer"]):
        data["customers"] = safe_get_list("Customer",
            ["name", "customer_name", "customer_group", "territory", "gstin"], limit=500)

    # Suppliers
    if any(w in q for w in ["supplier", "suppliers", "vendor"]):
        data["suppliers"] = safe_get_list("Supplier",
            ["name", "supplier_name", "supplier_group", "gstin"], limit=500)

    # Items
    if any(w in q for w in ["item", "items", "product", "stock", "inventory"]):
        data["items"] = safe_get_list("Item",
            ["name", "item_name", "item_group", "stock_uom", "is_stock_item"], limit=500)

    # Sales Invoices
    if any(w in q for w in ["invoice", "invoices", "revenue", "sales invoice", "billing"]):
        data["sales_invoices"] = safe_get_list("Sales Invoice",
            ["name", "customer", "status", "posting_date", "grand_total", "outstanding_amount", "docstatus"],
            limit=1000)

    # Purchase Invoices
    if any(w in q for w in ["purchase invoice", "bill", "purchase", "payable"]):
        data["purchase_invoices"] = safe_get_list("Purchase Invoice",
            ["name", "supplier", "status", "posting_date", "grand_total", "outstanding_amount", "docstatus"],
            limit=1000)

    # Sales Orders
    if any(w in q for w in ["sales order", "order", "so-"]):
        data["sales_orders"] = safe_get_list("Sales Order",
            ["name", "customer", "status", "transaction_date", "grand_total"], limit=500)

    # Purchase Orders
    if any(w in q for w in ["purchase order", "po-"]):
        data["purchase_orders"] = safe_get_list("Purchase Order",
            ["name", "supplier", "status", "transaction_date", "grand_total"], limit=500)

    # Employees
    if any(w in q for w in ["employee", "employees", "staff", "payroll"]):
        data["employees"] = safe_get_list("Employee",
            ["name", "employee_name", "department", "designation", "status"], limit=500)

    # Payments
    if any(w in q for w in ["payment", "receipt", "collection", "paid"]):
        data["payments"] = safe_get_list("Payment Entry",
            ["name", "party", "party_type", "paid_amount", "posting_date", "payment_type"],
            limit=300)

    # Quotation
    if any(w in q for w in ["quotation", "quote", "estimate"]):
        data["quotations"] = safe_get_list("Quotation",
            ["name", "party_name", "status", "transaction_date", "grand_total"], limit=200)

    # Dynamic doctype detection - search for any doctype name mentioned
    all_doctypes = discover_all_doctypes()
    for category in ["transactions", "masters", "other"]:
        for dt in all_doctypes.get(category, []):
            dt_lower = dt.lower().replace("_", " ")
            if dt_lower in q or dt.lower().replace(" ", "") in q.replace(" ", ""):
                try:
                    if safe_count(dt) > 0:
                        fields = ["name"]
                        # Try to get a display field
                        meta = frappe.get_meta(dt)
                        if hasattr(meta, 'fields') and len(meta.fields) > 0:
                            for f in meta.fields[:3]:
                                if f.fieldtype not in ["Section Break", "Column Break", "Tab Break"]:
                                    fields.append(f.fieldname)
                                    break
                        data[f"detected_{dt.lower().replace(' ', '_')}"] = safe_get_list(dt, fields, limit=100)
                except:
                    pass

    return data

def get_greeting_response():
    """Return greeting message"""
    user = frappe.session.user_fullname or "there"
    return {
        "type": "text",
        "message": f"""👋 Hello <b>{user}</b>! I am your SkyERP AI Assistant.<br><br>
        I can help you with:<br>
        • 📊 Business data analysis & reports<br>
        • 👥 Customer/Supplier/Item/Employee management<br>
        • 🧾 Sales & Purchase invoices, orders<br>
        • 📷 Document scanning (SI, PI, SO, PO)<br>
        • 📈 Revenue, outstanding, trends<br>
        • ➕ Creating new records<br><br>
        Type <b>help</b> for available commands."""
    }

def get_help_response():
    """Return help message with all commands"""
    return {
        "type": "text",
        "message": """🤖 <b>SkyERP AI Assistant - Commands:</b><br><br>

<b>📊 Data Queries:</b><br>
• "How many customers/suppliers/items?"<br>
• "Total revenue this month/year"<br>
• "Show all overdue invoices"<br>
• "Business summary/overview"<br><br>

<b>🔍 Entity Questions:</b><br>
• "Show customer [Name] details"<br>
• "Total billing of [Customer]"<br>
• "Outstanding amount for [Customer]"<br>
• "Stock of [Item]"<br>
• "Salary of [Employee]"<br><br>

<b>➕ Create Records:</b><br>
• "Create customer [Name]"<br>
• "Create supplier with GSTIN [Number]"<br>
• "Add item [Name]"<br>
• "Add employee [Name]"<br><br>

<b>📄 Document IDs:</b><br>
• "Show SINV-2024-00001"<br>
• "Details of SO-2024-00001"<br>
• "Find PO-2024-00001"<br><br>

<b>📷 Image Processing:</b><br>
Upload any invoice/order image to auto-create:<br>
• Sales Invoice<br>
• Purchase Invoice<br>
• Sales Order<br>
• Purchase Order"""
    }

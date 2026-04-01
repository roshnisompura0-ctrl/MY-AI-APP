"""
Image Processing Service for Document Creation
Handles Sales Invoice, Purchase Invoice, Sales Order, Purchase Order from images
"""

import frappe
import json
import base64
import re

def process_document_image(image_data, document_type="auto"):
    """
    Process uploaded image and create ERPNext document
    document_type: "sales_invoice", "purchase_invoice", "sales_order", "purchase_order", "auto"
    """
    try:
        # Get AI service
        from my_ai_assistant.services.ai_service import call_gemini_vision

        # Auto-detect document type if not specified
        if document_type == "auto":
            document_type = detect_document_type_from_image(image_data)

        # Extract data from image using AI
        extracted_data = extract_data_from_image(image_data, document_type)

        if not extracted_data:
            return {
                "type": "error",
                "message": "Could not extract data from image. Please try a clearer image."
            }

        # Create appropriate document
        if document_type in ["sales_invoice", "sales order", "salesorder"]:
            return create_sales_document("Sales Invoice", extracted_data)
        elif document_type in ["purchase_invoice", "purchase order", "purchaseorder", "bill"]:
            return create_purchase_document(document_type, extracted_data)
        else:
            # Try to infer from extracted data
            if extracted_data.get("document_type") in ["Sales Invoice", "Sales Order"]:
                return create_sales_document(extracted_data.get("document_type", "Sales Invoice"), extracted_data)
            else:
                return create_purchase_document("Purchase Invoice", extracted_data)

    except Exception as e:
        frappe.log_error(f"Image processing error: {str(e)}")
        return {
            "type": "error",
            "message": f"Error processing image: {str(e)[:200]}"
        }

def detect_document_type_from_image(image_data):
    """Use AI to detect what type of document is in the image"""
    prompt = """
    Analyze this document image and identify what type of business document it is.
    Look for keywords, layout patterns, and document structure.

    Common document types:
    - Sales Invoice / Tax Invoice (issued to customers)
    - Purchase Invoice / Bill (received from suppliers)
    - Sales Order / Customer Order
    - Purchase Order / PO
    - Quotation / Estimate
    - Delivery Challan

    Respond with ONLY the document type name in this format:
    {"document_type": "Sales Invoice"}
    or
    {"document_type": "Purchase Invoice"}
    etc.
    """

    try:
        from my_ai_assistant.services.ai_service import call_gemini_vision
        result = call_gemini_vision(prompt, image_data)

        if isinstance(result, dict) and "document_type" in result:
            doc_type = result["document_type"].lower()
            if "sales" in doc_type and "invoice" in doc_type:
                return "sales_invoice"
            elif "purchase" in doc_type and "invoice" in doc_type:
                return "purchase_invoice"
            elif "sales" in doc_type and "order" in doc_type:
                return "sales_order"
            elif "purchase" in doc_type and "order" in doc_type:
                return "purchase_order"
    except:
        pass

    return "auto"

def extract_data_from_image(image_data, document_type):
    """Extract structured data from document image"""
    prompt = f"""
    Extract all business data from this {document_type} image.

    Extract these fields:
    - invoice_number / order_number / document_number
    - invoice_date / order_date / document_date
    - due_date (if available)
    - party_name (customer name or supplier name)
    - party_gstin (if available)
    - party_address (if available)
    - items: list with item_name, description, qty, rate, amount
    - subtotal / net_total
    - tax_amount / gst_amount
    - grand_total / total_amount
    - terms_and_conditions (if any)
    - po_number / reference (if referenced)

    Return ONLY valid JSON in this exact format:
    {{
        "document_type": "Sales Invoice",
        "document_number": "INV-001",
        "date": "2024-01-15",
        "due_date": "2024-02-15",
        "party_name": "ABC Company",
        "party_gstin": "27AABCU9603R1ZX",
        "items": [
            {{
                "item_name": "Product A",
                "description": "Description of product",
                "qty": 10,
                "rate": 100.00,
                "amount": 1000.00
            }}
        ],
        "subtotal": 1000.00,
        "tax_amount": 180.00,
        "grand_total": 1180.00
    }}
    """

    try:
        from my_ai_assistant.services.ai_service import call_gemini_vision
        result = call_gemini_vision(prompt, image_data)

        if isinstance(result, dict):
            return result

        # Try to parse if string
        if isinstance(result, str):
            try:
                return json.loads(result)
            except:
                pass

    except Exception as e:
        frappe.log_error(f"Data extraction error: {str(e)}")

    return None

def create_sales_document(doctype, extracted):
    """Create Sales Invoice or Sales Order from extracted data"""
    try:
        company = frappe.defaults.get_global_default("company")
        if not company:
            company = frappe.db.get_list("Company", limit=1)[0].name

        today = frappe.utils.today()

        # Handle party (Customer)
        party_name = extracted.get("party_name", "Walk-in Customer").strip()
        if not party_name or party_name.lower() in ["cash", "", "na"]:
            party_name = "Walk-in Customer"

        customer = get_or_create_party("Customer", party_name)

        # Process items
        items = []
        raw_items = extracted.get("items", [])

        if not raw_items and extracted.get("grand_total"):
            # Create single item with total amount
            raw_items = [{
                "item_name": "Miscellaneous Item",
                "qty": 1,
                "rate": float(extracted.get("grand_total", 0)),
                "amount": float(extracted.get("grand_total", 0))
            }]

        for item in raw_items:
            item_name = item.get("item_name") or item.get("description") or "Miscellaneous Item"
            item_code = get_or_create_item(item_name, item.get("uom", "Nos"))

            items.append({
                "item_code": item_code,
                "item_name": item_name,
                "description": item.get("description") or item_name,
                "qty": float(item.get("qty") or item.get("quantity") or 1),
                "rate": float(item.get("rate") or item.get("unit_price") or 0),
                "amount": float(item.get("amount") or 0)
            })

        # Document data
        doc_data = {
            "doctype": doctype,
            "company": company,
            "customer": customer,
            "posting_date": parse_date(extracted.get("date") or extracted.get("invoice_date") or today),
            "due_date": parse_date(extracted.get("due_date")) if extracted.get("due_date") else None,
            "items": items
        }

        # Add order-specific fields
        if doctype == "Sales Order":
            doc_data["transaction_date"] = doc_data.pop("posting_date")
            doc_data["delivery_date"] = frappe.utils.add_days(doc_data["transaction_date"], 7)

        # Add taxes if present
        tax_amount = extracted.get("tax_amount") or extracted.get("gst_amount")
        if tax_amount and float(tax_amount) > 0:
            tax_account = get_tax_account_for_company(company, "sales")
            if tax_account:
                doc_data["taxes"] = [{
                    "charge_type": "Actual",
                    "account_head": tax_account,
                    "description": "Tax",
                    "tax_amount": float(tax_amount)
                }]

        # Add terms if available
        if extracted.get("terms_and_conditions"):
            doc_data["terms"] = extracted.get("terms_and_conditions")[:500]

        # Create document
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        label = "Sales Invoice" if doctype == "Sales Invoice" else "Sales Order"

        return {
            "type": "success",
            "message": format_success_message(label, doc.name, extracted, items),
            "doctype": doctype,
            "name": doc.name,
            "link": f"/app/{doctype.lower().replace(' ', '-')}/{doc.name}"
        }

    except Exception as e:
        frappe.log_error(f"Create sales document error: {str(e)}")
        return {"type": "error", "message": f"Error creating document: {str(e)[:200]}"}

def create_purchase_document(doc_type, extracted):
    """Create Purchase Invoice or Purchase Order from extracted data"""
    try:
        company = frappe.defaults.get_global_default("company")
        if not company:
            company = frappe.db.get_list("Company", limit=1)[0].name

        today = frappe.utils.today()

        # Handle party (Supplier)
        party_name = extracted.get("party_name", "Unknown Supplier").strip()
        if not party_name or party_name.lower() in ["cash", "", "na"]:
            party_name = "Unknown Supplier"

        supplier = get_or_create_party("Supplier", party_name)

        # Determine actual doctype
        if "order" in doc_type.lower():
            doctype = "Purchase Order"
        else:
            doctype = "Purchase Invoice"

        # Process items
        items = []
        raw_items = extracted.get("items", [])

        if not raw_items and extracted.get("grand_total"):
            raw_items = [{
                "item_name": "Miscellaneous Item",
                "qty": 1,
                "rate": float(extracted.get("grand_total", 0)),
                "amount": float(extracted.get("grand_total", 0))
            }]

        for item in raw_items:
            item_name = item.get("item_name") or item.get("description") or "Miscellaneous Item"
            item_code = get_or_create_item(item_name, item.get("uom", "Nos"))

            items.append({
                "item_code": item_code,
                "item_name": item_name,
                "description": item.get("description") or item_name,
                "qty": float(item.get("qty") or item.get("quantity") or 1),
                "rate": float(item.get("rate") or item.get("unit_price") or 0),
                "amount": float(item.get("amount") or 0)
            })

        # Document data
        doc_date = parse_date(extracted.get("date") or extracted.get("invoice_date") or today)

        doc_data = {
            "doctype": doctype,
            "company": company,
            "supplier": supplier,
            "items": items
        }

        # Type-specific date fields
        if doctype == "Purchase Order":
            doc_data["transaction_date"] = doc_date
            doc_data["schedule_date"] = frappe.utils.add_days(doc_date, 7)
        else:
            doc_data["posting_date"] = doc_date
            doc_data["due_date"] = parse_date(extracted.get("due_date")) if extracted.get("due_date") else None

            # Bill number for Purchase Invoice
            bill_no = extracted.get("document_number") or extracted.get("invoice_number")
            if bill_no:
                doc_data["bill_no"] = str(bill_no)[:140]
                doc_data["bill_date"] = doc_date

        # Add taxes
        tax_amount = extracted.get("tax_amount") or extracted.get("gst_amount")
        if tax_amount and float(tax_amount) > 0:
            tax_account = get_tax_account_for_company(company, "purchase")
            if tax_account:
                doc_data["taxes"] = [{
                    "charge_type": "Actual",
                    "account_head": tax_account,
                    "description": "Tax",
                    "tax_amount": float(tax_amount)
                }]

        # Create document
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        label = "Purchase Invoice" if doctype == "Purchase Invoice" else "Purchase Order"

        return {
            "type": "success",
            "message": format_success_message(label, doc.name, extracted, items),
            "doctype": doctype,
            "name": doc.name,
            "link": f"/app/{doctype.lower().replace(' ', '-')}/{doc.name}"
        }

    except Exception as e:
        frappe.log_error(f"Create purchase document error: {str(e)}")
        return {"type": "error", "message": f"Error creating document: {str(e)[:200]}"}

def get_or_create_party(doctype, name):
    """Get existing party or create new one"""
    name_field = "customer_name" if doctype == "Customer" else "supplier_name"

    # Check existing
    existing = frappe.db.get_value(doctype, {name_field: name}, "name")
    if existing:
        return existing

    # Create new
    try:
        defaults = {
            "Customer": {
                "customer_type": "Company" if " " in name else "Individual",
                "customer_group": "All Customer Groups",
                "territory": "All Territories"
            },
            "Supplier": {
                "supplier_type": "Company" if " " in name else "Individual",
                "supplier_group": "All Supplier Groups"
            }
        }

        doc = frappe.get_doc({
            "doctype": doctype,
            name_field: name,
            **defaults.get(doctype, {})
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except:
        return name

def get_or_create_item(item_name, uom="Nos"):
    """Get existing item or create new one"""
    # Check by name
    existing = frappe.db.get_value("Item", {"item_name": item_name}, "name")
    if existing:
        return existing

    # Check by item_code
    existing = frappe.db.get_value("Item", {"item_code": item_name}, "name")
    if existing:
        return existing

    # Create new
    try:
        doc = frappe.get_doc({
            "doctype": "Item",
            "item_name": item_name,
            "item_code": item_name[:140],
            "item_group": "All Item Groups",
            "stock_uom": uom if frappe.db.exists("UOM", uom) else "Nos",
            "is_stock_item": 0
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except:
        return "Miscellaneous Item"

def get_tax_account_for_company(company, account_type="sales"):
    """Get tax account for company"""
    try:
        patterns = ["Output Tax GST", "Output GST"] if account_type == "sales" else ["Input Tax GST", "Input GST"]
        for pattern in patterns:
            account = frappe.db.get_value("Account",
                {"account_name": ["like", f"%{pattern}%"], "company": company, "is_group": 0},
                "name")
            if account:
                return account
    except:
        pass
    return None

def parse_date(date_str):
    """Parse various date formats"""
    if not date_str:
        return frappe.utils.today()

    formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y"]

    for fmt in formats:
        try:
            from datetime import datetime
            parsed = datetime.strptime(str(date_str), fmt)
            return parsed.strftime("%Y-%m-%d")
        except:
            continue

    return frappe.utils.today()

def format_success_message(doctype, doc_name, extracted, items):
    """Format success message for created document"""
    party = extracted.get("party_name", "N/A")
    date = extracted.get("date") or extracted.get("invoice_date", "N/A")
    total = extracted.get("grand_total") or extracted.get("total_amount", "N/A")

    items_html = ""
    for item in items[:5]:
        items_html += f"<br>&nbsp;&nbsp;• <b>{item.get('item_name', 'Item')}</b> × {item.get('qty', 1)} @ ₹{item.get('rate', 0)}"
    if len(items) > 5:
        items_html += f"<br>&nbsp;&nbsp;… and {len(items) - 5} more items"

    return f"""🧾 <b>{doctype} Draft Created!</b>
<br>👤 <b>Party:</b> {party}
<br>📅 <b>Date:</b> {date}
<br>📦 <b>Items:</b> {items_html}
<br>💰 <b>Total:</b> ₹{total}
<br><br><span style='color:#6b7280;font-size:12px'>✏️ Draft saved — review and submit in ERPNext</span>"""

import frappe
import requests
import json
import re
import base64
from frappe import get_meta

def get_api_key():
    return frappe.conf.get("vertex_api_key") or frappe.conf.get("ai_api_key")

def get_doctype_fields(doctype):
    try:
        meta = get_meta(doctype)
        fields = []
        for field in meta.fields:
            if field.fieldtype not in ["Section Break", "Column Break", "Tab Break", "HTML", "Button", "Attach", "Attach Image"]:
                if not field.fieldname.startswith(("_", "idx", "docstatus", "parent", "parenttype", "parentfield", "modified", "modified_by", "creation", "owner")):
                    fields.append(field.fieldname)
        return fields[:50]
    except:
        return ["name"]

def safe_get(dt, fields, filters=None, limit=500):
    try:
        if not fields:
            fields = ["name"]
        result = frappe.get_all(dt, fields=fields, filters=filters or {}, limit=limit, ignore_permissions=True, order_by="modified desc")
        return result
    except Exception as e:
        frappe.log_error(f"safe_get error for {dt}: {str(e)}")
        return []

def safe_get_full_doc(dt, doc_name):
    try:
        doc = frappe.get_doc(dt, doc_name)
        data = doc.as_dict()
        for fieldname in [f.fieldname for f in doc.meta.get_table_fields()]:
            if hasattr(doc, fieldname):
                data[fieldname] = [item.as_dict() for item in getattr(doc, fieldname)]
        return data
    except Exception as e:
        return {"error": str(e), "doctype": dt, "name": doc_name}

def get_country_name():
    for name in ["India", "INDIA", "india"]:
        if frappe.db.exists("Country", name):
            return name
    result = frappe.db.get_value("Country", {"country_name": ["like", "%India%"]}, "name")
    if result:
        return result
    result = frappe.db.get_list("Country", limit=1)
    if result:
        return result[0].name
    return None

def ensure_india_country():
    country_name = get_country_name()
    if country_name:
        return country_name
    try:
        doc = frappe.get_doc({
            "doctype": "Country",
            "country_name": "India",
            "code": "in",
            "date_format": "dd-mm-yyyy",
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except Exception as e:
        frappe.log_error("Could not create India country: " + str(e))
        return None

def get_gstin_details(gstin):
    try:
        gstin = gstin.upper().strip()
        try:
            from india_compliance.gst_india.api_classes.public import PublicAPI
            api = PublicAPI()
            response = api.get_gstin_info(gstin)
            if response:
                data = response.get("data", response) if isinstance(response, dict) and "data" in response else response
                legal_name = data.get("lgnm") or data.get("tradeName") or data.get("legal_name")
                trade_name = data.get("tradeName") or data.get("trade_name")
                pradr = data.get("pradr", {})
                addr = pradr.get("addr", {}) if isinstance(pradr, dict) else {}
                address_parts = [addr.get(k) for k in ["bno", "bnm", "st", "locality"] if addr.get(k)]
                full_address = ", ".join(address_parts) if address_parts else data.get("adr") or ""
                city = addr.get("loc", "") or addr.get("dst", "")
                state = addr.get("stcd", "")
                pincode = addr.get("pncd", "")
                if legal_name:
                    return {"success": True, "gstin": gstin, "legal_name": legal_name, "trade_name": trade_name or legal_name, "address": full_address, "state": state, "city": city, "pincode": pincode, "status": data.get("sts", ""), "taxpayer_type": data.get("dty", "")}
        except Exception as e:
            frappe.log_error("India Compliance PublicAPI error: " + str(e))
        try:
            existing = frappe.db.get_value("GSTIN Detail", {"gstin": gstin}, ["gstin", "legal_name", "trade_name", "address_line_1", "city", "state", "pincode", "status"], as_dict=True)
            if existing and existing.legal_name:
                return {"success": True, "gstin": existing.gstin, "legal_name": existing.legal_name, "trade_name": existing.trade_name or existing.legal_name, "address": existing.address_line_1 or "", "city": existing.city, "state": existing.state, "pincode": existing.pincode, "status": existing.status}
        except:
            pass
        return {"error": "Could not fetch GSTIN details.", "gstin": gstin}
    except Exception as e:
        return {"error": str(e), "gstin": gstin}

def detect_doctype_from_question(question):
    q = question.lower()
    gstin_match = re.search(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9]{1}[A-Z]{1}[0-9]{1})\b", question, re.IGNORECASE)
    if gstin_match:
        return "GSTIN", gstin_match.group(1).upper()
    doc_patterns = [
        (r"SINV-[\w-]+", "Sales Invoice"), (r"PINV-[\w-]+", "Purchase Invoice"),
        (r"SO-[\w-]+", "Sales Order"), (r"PO-[\w-]+", "Purchase Order"),
        (r"QUOT-[\w-]+", "Quotation"), (r"DN-[\w-]+", "Delivery Note"),
        (r"HR-EMP-[\w-]+", "Employee"),
    ]
    for pattern, doctype in doc_patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return doctype, match.group(0)
    keyword_map = {
        "customer": "Customer", "supplier": "Supplier", "vendor": "Supplier",
        "item": "Item", "product": "Item", "employee": "Employee", "staff": "Employee",
        "lead": "Lead", "sales invoice": "Sales Invoice", "invoice": "Sales Invoice",
        "purchase invoice": "Purchase Invoice", "sales order": "Sales Order",
        "purchase order": "Purchase Order", "quotation": "Quotation",
        "payment": "Payment Entry", "delivery": "Delivery Note",
    }
    for keyword, doctype in keyword_map.items():
        if keyword in q:
            return doctype, None
    return None, None

def db_count(dt):
    try:
        return frappe.db.count(dt)
    except:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
#  ENTITY NAME EXTRACTOR
#  Scans the question for any known customer / supplier / item / employee name
# ─────────────────────────────────────────────────────────────────────────────
def extract_entity_from_question(question):
    """
    Returns a dict with keys: customer, supplier, item, employee
    Each value is the ERPNext document name (ID) when found.
    """
    q_lower = question.lower()
    result  = {}

    # ── Customers ────────────────────────────────────────────────────────────
    try:
        customers = frappe.get_all("Customer", fields=["name", "customer_name"], limit=2000, ignore_permissions=True)
        for c in customers:
            cname = (c.get("customer_name") or c.get("name") or "").strip()
            if cname and len(cname) > 1 and cname.lower() in q_lower:
                result["customer"]         = c.get("name")
                result["customer_display"] = cname
                break
    except:
        pass

    # ── Suppliers ────────────────────────────────────────────────────────────
    try:
        suppliers = frappe.get_all("Supplier", fields=["name", "supplier_name"], limit=2000, ignore_permissions=True)
        for s in suppliers:
            sname = (s.get("supplier_name") or s.get("name") or "").strip()
            if sname and len(sname) > 1 and sname.lower() in q_lower:
                result["supplier"]         = s.get("name")
                result["supplier_display"] = sname
                break
    except:
        pass

    # ── Items ────────────────────────────────────────────────────────────────
    try:
        items = frappe.get_all("Item", fields=["name", "item_name", "item_code"], limit=2000, ignore_permissions=True)
        for i in items:
            iname = (i.get("item_name") or i.get("item_code") or i.get("name") or "").strip()
            if iname and len(iname) > 2 and iname.lower() in q_lower:
                result["item"]         = i.get("name")
                result["item_display"] = iname
                break
    except:
        pass

    # ── Employees ────────────────────────────────────────────────────────────
    try:
        employees = frappe.get_all("Employee", fields=["name", "employee_name"], limit=1000, ignore_permissions=True)
        for e in employees:
            ename = (e.get("employee_name") or e.get("name") or "").strip()
            if ename and len(ename) > 2 and ename.lower() in q_lower:
                result["employee"]         = e.get("name")
                result["employee_display"] = ename
                break
    except:
        pass

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN DATA FETCHER  —  entity-aware + keyword-based
# ─────────────────────────────────────────────────────────────────────────────
def get_live_data(question):
    q     = question.lower()
    data  = {}
    today = frappe.utils.today()

    detected_doctype, doc_name = detect_doctype_from_question(question)

    # ── GSTIN lookup ─────────────────────────────────────────────────────────
    if detected_doctype == "GSTIN" and doc_name:
        data["gstin_details"] = get_gstin_details(doc_name)
        return data

    # ── Specific document by ID (SINV-xxxx, SO-xxxx …) ───────────────────────
    if detected_doctype and doc_name:
        if not any(w in q for w in ["create", "add", "new"]):
            data["specific_document"] = safe_get_full_doc(detected_doctype, doc_name)
            return data

    # ── Detect entity names mentioned in the question ─────────────────────────
    entities = extract_entity_from_question(question)

    # ── Always include overview counts ───────────────────────────────────────
    data["overview"] = {
        "customers":         db_count("Customer"),
        "suppliers":         db_count("Supplier"),
        "items":             db_count("Item"),
        "employees":         db_count("Employee"),
        "sales_invoices":    db_count("Sales Invoice"),
        "purchase_invoices": db_count("Purchase Invoice"),
        "sales_orders":      db_count("Sales Order"),
        "purchase_orders":   db_count("Purchase Order"),
        "quotations":        db_count("Quotation"),
        "leads":             db_count("Lead"),
        "payment_entries":   db_count("Payment Entry"),
        "delivery_notes":    db_count("Delivery Note"),
        "purchase_receipts": db_count("Purchase Receipt"),
        "journal_entries":   db_count("Journal Entry"),
    }

    # ═════════════════════════════════════════════════════════════════════════
    # ENTITY-SPECIFIC DATA
    # ═════════════════════════════════════════════════════════════════════════

    # ── Customer-specific ────────────────────────────────────────────────────
    if entities.get("customer"):
        cid = entities["customer"]
        data["entity_customer"]         = safe_get_full_doc("Customer", cid)
        data["entity_customer_name"]    = entities.get("customer_display", cid)

        sinv_c = safe_get("Sales Invoice", [
            "name", "customer", "customer_name", "status", "posting_date",
            "due_date", "grand_total", "outstanding_amount", "docstatus"
        ], filters={"customer": cid}, limit=1000)
        submitted_c = [i for i in sinv_c if str(i.get("docstatus")) == "1"]

        data["entity_customer_invoices"]       = sinv_c
        data["entity_customer_invoice_count"]  = len(sinv_c)
        data["entity_customer_submitted_count"]= len(submitted_c)
        data["entity_customer_total_billing"]  = sum(float(i.get("grand_total") or 0) for i in submitted_c)
        data["entity_customer_outstanding"]    = sum(float(i.get("outstanding_amount") or 0) for i in submitted_c)
        data["entity_customer_paid_count"]     = len([i for i in sinv_c if i.get("status") == "Paid"])
        data["entity_customer_unpaid_count"]   = len([i for i in sinv_c if i.get("status") in ["Unpaid", "Overdue"]])
        data["entity_customer_overdue_count"]  = len([i for i in sinv_c if i.get("status") == "Overdue"])

        so_c = safe_get("Sales Order", [
            "name", "customer", "customer_name", "status", "transaction_date", "delivery_date", "grand_total"
        ], filters={"customer": cid}, limit=500)
        data["entity_customer_orders"]      = so_c
        data["entity_customer_order_count"] = len(so_c)

        pay_c = safe_get("Payment Entry", [
            "name", "party", "party_name", "payment_type", "paid_amount", "posting_date", "mode_of_payment"
        ], filters={"party": cid, "party_type": "Customer"}, limit=300)
        data["entity_customer_payments"]      = pay_c
        data["entity_customer_payment_total"] = sum(float(r.get("paid_amount") or 0) for r in pay_c)

        dn_c = safe_get("Delivery Note", [
            "name", "customer", "customer_name", "status", "posting_date", "grand_total"
        ], filters={"customer": cid}, limit=200)
        data["entity_customer_delivery_notes"]      = dn_c
        data["entity_customer_delivery_note_count"] = len(dn_c)

        quot_c = safe_get("Quotation", [
            "name", "party_name", "status", "transaction_date", "grand_total"
        ], filters={"party_name": cid}, limit=100)
        data["entity_customer_quotations"]      = quot_c
        data["entity_customer_quotation_count"] = len(quot_c)

    # ── Supplier-specific ────────────────────────────────────────────────────
    if entities.get("supplier"):
        sid = entities["supplier"]
        data["entity_supplier"]      = safe_get_full_doc("Supplier", sid)
        data["entity_supplier_name"] = entities.get("supplier_display", sid)

        pinv_s = safe_get("Purchase Invoice", [
            "name", "supplier", "supplier_name", "status", "posting_date",
            "grand_total", "outstanding_amount", "docstatus"
        ], filters={"supplier": sid}, limit=1000)
        submitted_s = [i for i in pinv_s if str(i.get("docstatus")) == "1"]

        data["entity_supplier_invoices"]       = pinv_s
        data["entity_supplier_invoice_count"]  = len(pinv_s)
        data["entity_supplier_total_billing"]  = sum(float(i.get("grand_total") or 0) for i in submitted_s)
        data["entity_supplier_outstanding"]    = sum(float(i.get("outstanding_amount") or 0) for i in submitted_s)

        po_s = safe_get("Purchase Order", [
            "name", "supplier", "supplier_name", "status", "transaction_date", "grand_total"
        ], filters={"supplier": sid}, limit=300)
        data["entity_supplier_orders"]      = po_s
        data["entity_supplier_order_count"] = len(po_s)

        pay_s = safe_get("Payment Entry", [
            "name", "party", "party_name", "payment_type", "paid_amount", "posting_date", "mode_of_payment"
        ], filters={"party": sid, "party_type": "Supplier"}, limit=200)
        data["entity_supplier_payments"]      = pay_s
        data["entity_supplier_payment_total"] = sum(float(r.get("paid_amount") or 0) for r in pay_s)

        pr_s = safe_get("Purchase Receipt", [
            "name", "supplier", "supplier_name", "status", "posting_date", "grand_total"
        ], filters={"supplier": sid}, limit=200)
        data["entity_supplier_receipts"]      = pr_s
        data["entity_supplier_receipt_count"] = len(pr_s)

    # ── Item-specific ─────────────────────────────────────────────────────────
    if entities.get("item"):
        iid = entities["item"]
        data["entity_item"]      = safe_get_full_doc("Item", iid)
        data["entity_item_name"] = entities.get("item_display", iid)

        try:
            sinv_items = frappe.db.sql("""
                SELECT si.name, si.customer_name, si.status, si.posting_date,
                       sii.qty, sii.rate, sii.amount
                FROM `tabSales Invoice` si
                JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
                WHERE sii.item_code = %s AND si.docstatus = 1
                ORDER BY si.posting_date DESC LIMIT 200
            """, iid, as_dict=True)
            data["entity_item_sales"]          = sinv_items
            data["entity_item_total_sold_qty"] = sum(float(r.get("qty") or 0) for r in sinv_items)
            data["entity_item_total_revenue"]  = sum(float(r.get("amount") or 0) for r in sinv_items)
        except Exception as e:
            frappe.log_error("Item sales query: " + str(e))

        try:
            pinv_items = frappe.db.sql("""
                SELECT pi.name, pi.supplier_name, pi.status, pi.posting_date,
                       pii.qty, pii.rate, pii.amount
                FROM `tabPurchase Invoice` pi
                JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
                WHERE pii.item_code = %s AND pi.docstatus = 1
                ORDER BY pi.posting_date DESC LIMIT 200
            """, iid, as_dict=True)
            data["entity_item_purchases"]          = pinv_items
            data["entity_item_total_purchased_qty"]= sum(float(r.get("qty") or 0) for r in pinv_items)
        except Exception as e:
            frappe.log_error("Item purchases query: " + str(e))

        try:
            stock = frappe.db.sql("""
                SELECT warehouse, actual_qty, valuation_rate
                FROM `tabBin` WHERE item_code = %s
            """, iid, as_dict=True)
            data["entity_item_stock"]       = stock
            data["entity_item_total_stock"] = sum(float(r.get("actual_qty") or 0) for r in stock)
        except:
            pass

    # ── Employee-specific ────────────────────────────────────────────────────
    if entities.get("employee"):
        eid = entities["employee"]
        data["entity_employee"]      = safe_get_full_doc("Employee", eid)
        data["entity_employee_name"] = entities.get("employee_display", eid)

        try:
            attendance = safe_get("Attendance", [
                "name", "attendance_date", "status", "employee_name"
            ], filters={"employee": eid}, limit=200)
            data["entity_employee_attendance"]    = attendance
            data["entity_employee_present_days"]  = len([a for a in attendance if a.get("status") == "Present"])
            data["entity_employee_absent_days"]   = len([a for a in attendance if a.get("status") == "Absent"])
        except:
            pass

        try:
            leaves = safe_get("Leave Application", [
                "name", "leave_type", "from_date", "to_date", "status", "total_leave_days"
            ], filters={"employee": eid}, limit=50)
            data["entity_employee_leaves"] = leaves
        except:
            pass

        try:
            salary_slips = safe_get("Salary Slip", [
                "name", "start_date", "end_date", "net_pay", "gross_pay", "total_deduction", "status"
            ], filters={"employee": eid}, limit=24)
            data["entity_employee_salary_slips"]  = salary_slips
            submitted_slips = [s for s in salary_slips if s.get("status") == "Submitted"]
            data["entity_employee_latest_net_pay"]= submitted_slips[0].get("net_pay") if submitted_slips else None
        except:
            pass

    # ═════════════════════════════════════════════════════════════════════════
    # KEYWORD-BASED GENERAL DATA
    # ═════════════════════════════════════════════════════════════════════════

    # ── CUSTOMERS list ────────────────────────────────────────────────────────
    if any(w in q for w in ["customer", "customers", "client", "buyer", "all customer"]):
        rows = safe_get("Customer", ["name", "customer_name", "customer_group", "territory", "gstin", "mobile_no", "email_id"], limit=1000)
        data["customers"]       = rows
        data["total_customers"] = len(rows)

    # ── SUPPLIERS list ────────────────────────────────────────────────────────
    if any(w in q for w in ["supplier", "suppliers", "vendor", "vendors", "all supplier"]):
        rows = safe_get("Supplier", ["name", "supplier_name", "supplier_group", "gstin", "mobile_no", "email_id"], limit=1000)
        data["suppliers"]       = rows
        data["total_suppliers"] = len(rows)

    # ── ITEMS list ────────────────────────────────────────────────────────────
    if any(w in q for w in ["item", "items", "product", "products", "stock", "inventory", "all item"]):
        rows = safe_get("Item", ["name", "item_name", "item_code", "item_group", "stock_uom", "standard_rate", "is_stock_item"], limit=1000)
        data["items"]       = rows
        data["total_items"] = len(rows)
        try:
            stock_rows = frappe.db.sql("""
                SELECT item_code, SUM(actual_qty) as total_qty
                FROM `tabBin` GROUP BY item_code
                ORDER BY total_qty DESC LIMIT 200
            """, as_dict=True)
            data["stock_balances"] = stock_rows
        except:
            pass

    # ── EMPLOYEES list ────────────────────────────────────────────────────────
    if any(w in q for w in ["employee", "employees", "staff", "worker", "all employee"]):
        rows = safe_get("Employee", ["name", "employee_name", "department", "designation", "status", "date_of_joining", "gender", "mobile_no"], limit=500)
        data["employees"]       = rows
        data["total_employees"] = len(rows)

    # ── LEADS ─────────────────────────────────────────────────────────────────
    if any(w in q for w in ["lead", "leads", "prospect"]):
        rows = safe_get("Lead", ["name", "lead_name", "status", "email_id", "mobile_no", "source", "lead_owner"], limit=300)
        data["leads"]       = rows
        data["total_leads"] = len(rows)

    # ── SALES INVOICES ────────────────────────────────────────────────────────
    sinv_kw = [
        "invoice", "invoices", "sinv", "sales invoice", "revenue", "outstanding",
        "overdue", "paid", "unpaid", "due", "billing", "amount", "total revenue",
        "this month", "collection", "receivable", "discount", "grand total",
        "money", "earning", "income", "summary", "business", "how many invoice", "all invoice"
    ]
    if any(w in q for w in sinv_kw):
        sinv = safe_get("Sales Invoice", [
            "name", "customer", "customer_name", "status", "posting_date",
            "due_date", "grand_total", "outstanding_amount", "discount_amount", "docstatus"
        ], limit=2000)
        submitted   = [i for i in sinv if str(i.get("docstatus")) == "1"]
        month_start = str(frappe.utils.get_first_day(today))
        year_start  = today[:4] + "-01-01"
        month_sinv  = [i for i in submitted if str(i.get("posting_date", "")) >= month_start]
        year_sinv   = [i for i in submitted if str(i.get("posting_date", "")) >= year_start]

        data["sales_invoices"]        = sinv
        data["total_sales_invoices"]  = len(sinv)
        data["submitted_invoices"]    = len(submitted)
        data["total_revenue"]         = sum(float(i.get("grand_total") or 0) for i in submitted)
        data["revenue_this_month"]    = sum(float(i.get("grand_total") or 0) for i in month_sinv)
        data["revenue_this_year"]     = sum(float(i.get("grand_total") or 0) for i in year_sinv)
        data["total_outstanding"]     = sum(float(i.get("outstanding_amount") or 0) for i in submitted)
        data["overdue_invoices"]      = [i for i in sinv if i.get("status") == "Overdue"]
        data["overdue_count"]         = len(data["overdue_invoices"])
        data["paid_invoices"]         = [i for i in sinv if i.get("status") == "Paid"]
        data["paid_count"]            = len(data["paid_invoices"])
        data["unpaid_invoices"]       = [i for i in sinv if i.get("status") == "Unpaid"]
        data["unpaid_count"]          = len(data["unpaid_invoices"])
        data["invoices_this_month"]   = len(month_sinv)
        data["invoices_this_year"]    = len(year_sinv)

    # ── PURCHASE INVOICES ─────────────────────────────────────────────────────
    if any(w in q for w in ["purchase invoice", "pinv", "payable", "purchase bill", "bill", "purchase amount"]):
        pinv = safe_get("Purchase Invoice", [
            "name", "supplier", "supplier_name", "status",
            "posting_date", "grand_total", "outstanding_amount", "docstatus"
        ], limit=2000)
        submitted_p                     = [i for i in pinv if str(i.get("docstatus")) == "1"]
        data["purchase_invoices"]        = pinv
        data["total_purchase_invoices"]  = len(pinv)
        data["total_payable"]            = sum(float(i.get("outstanding_amount") or 0) for i in submitted_p)
        data["total_purchase_amount"]    = sum(float(i.get("grand_total") or 0) for i in submitted_p)

    # ── SALES ORDERS ─────────────────────────────────────────────────────────
    if any(w in q for w in ["sales order", "so-", "order", "all order"]):
        rows = safe_get("Sales Order", [
            "name", "customer", "customer_name", "status",
            "transaction_date", "delivery_date", "grand_total"
        ], limit=1000)
        data["sales_orders"]       = rows
        data["total_sales_orders"] = len(rows)
        data["pending_so"]         = len([r for r in rows if r.get("status") in ["Draft", "To Deliver and Bill"]])
        data["completed_so"]       = len([r for r in rows if r.get("status") == "Completed"])

    # ── PURCHASE ORDERS ───────────────────────────────────────────────────────
    if any(w in q for w in ["purchase order", "po-", "all purchase order"]):
        rows = safe_get("Purchase Order", [
            "name", "supplier", "supplier_name", "status", "transaction_date", "grand_total"
        ], limit=500)
        data["purchase_orders"]       = rows
        data["total_purchase_orders"] = len(rows)

    # ── PAYMENTS ──────────────────────────────────────────────────────────────
    if any(w in q for w in ["payment", "payments", "receipt", "collection", "received", "paid amount"]):
        rows = safe_get("Payment Entry", [
            "name", "party", "party_name", "party_type", "payment_type",
            "paid_amount", "posting_date", "mode_of_payment", "reference_no"
        ], limit=500)
        data["payments"]       = rows
        data["total_payments"] = len(rows)
        data["total_received"] = sum(float(r.get("paid_amount") or 0) for r in rows if r.get("payment_type") == "Receive")
        data["total_paid_out"] = sum(float(r.get("paid_amount") or 0) for r in rows if r.get("payment_type") == "Pay")

    # ── QUOTATIONS ────────────────────────────────────────────────────────────
    if any(w in q for w in ["quotation", "quote", "quot-", "all quotation"]):
        rows = safe_get("Quotation", [
            "name", "party_name", "status", "transaction_date", "grand_total", "valid_till"
        ], limit=300)
        data["quotations"]       = rows
        data["total_quotations"] = len(rows)
        data["open_quotations"]  = len([r for r in rows if r.get("status") == "Open"])

    # ── DELIVERY NOTES ────────────────────────────────────────────────────────
    if any(w in q for w in ["delivery", "delivery note", "shipment", "dispatch"]):
        rows = safe_get("Delivery Note", [
            "name", "customer", "customer_name", "status", "posting_date", "grand_total"
        ], limit=300)
        data["delivery_notes"]       = rows
        data["total_delivery_notes"] = len(rows)

    # ── PURCHASE RECEIPTS ─────────────────────────────────────────────────────
    if any(w in q for w in ["purchase receipt", "grn", "goods receipt", "material receipt"]):
        rows = safe_get("Purchase Receipt", [
            "name", "supplier", "supplier_name", "status", "posting_date", "grand_total"
        ], limit=300)
        data["purchase_receipts"] = rows

    # ── JOURNAL ENTRIES ───────────────────────────────────────────────────────
    if any(w in q for w in ["journal", "journal entry", "jv", "voucher"]):
        rows = safe_get("Journal Entry", [
            "name", "title", "posting_date", "total_amount", "voucher_type", "docstatus"
        ], limit=200)
        data["journal_entries"]       = rows
        data["total_journal_entries"] = len(rows)

    # ── ATTENDANCE ────────────────────────────────────────────────────────────
    if any(w in q for w in ["attendance", "present", "absent"]):
        rows = safe_get("Attendance", [
            "name", "employee", "employee_name", "attendance_date", "status", "department"
        ], limit=500)
        data["attendance"]    = rows
        data["present_count"] = len([r for r in rows if r.get("status") == "Present"])
        data["absent_count"]  = len([r for r in rows if r.get("status") == "Absent"])

    # ── LEAVE APPLICATIONS ────────────────────────────────────────────────────
    if any(w in q for w in ["leave", "leave application", "leave request"]):
        rows = safe_get("Leave Application", [
            "name", "employee", "employee_name", "leave_type",
            "from_date", "to_date", "total_leave_days", "status"
        ], limit=300)
        data["leave_applications"] = rows

    # ── SALARY / PAYROLL ──────────────────────────────────────────────────────
    if any(w in q for w in ["salary", "payroll", "payslip", "wage", "ctc", "net pay"]):
        rows = safe_get("Salary Slip", [
            "name", "employee", "employee_name", "start_date", "end_date",
            "gross_pay", "net_pay", "total_deduction", "status"
        ], limit=200)
        data["salary_slips"]      = rows
        data["total_salary_paid"] = sum(float(r.get("net_pay") or 0) for r in rows if r.get("status") == "Submitted")

    # ── EXPENSES ─────────────────────────────────────────────────────────────
    if any(w in q for w in ["expense", "expenses", "expense claim"]):
        rows = safe_get("Expense Claim", [
            "name", "employee", "employee_name", "expense_date",
            "total_claimed_amount", "total_sanctioned_amount", "status"
        ], limit=200)
        data["expense_claims"] = rows
        data["total_expenses"] = sum(float(r.get("total_sanctioned_amount") or 0) for r in rows)

    # ── ACCOUNTS ─────────────────────────────────────────────────────────────
    if any(w in q for w in ["account", "ledger", "balance sheet", "profit", "loss"]):
        rows = safe_get("Account", [
            "name", "account_name", "account_type", "root_type", "parent_account"
        ], limit=200)
        data["accounts"] = rows

    # ── TASKS / PROJECTS ──────────────────────────────────────────────────────
    if any(w in q for w in ["task", "tasks", "project", "projects"]):
        try:
            proj = safe_get("Project", ["name", "project_name", "status", "percent_complete", "expected_end_date"], limit=100)
            tasks = safe_get("Task", ["name", "subject", "status", "priority", "exp_end_date", "project"], limit=200)
            data["projects"]       = proj
            data["total_projects"] = len(proj)
            data["tasks"]          = tasks
            data["total_tasks"]    = len(tasks)
        except:
            pass

    # ── CONTACTS ─────────────────────────────────────────────────────────────
    if any(w in q for w in ["contact", "contacts", "phone", "mobile", "email"]):
        rows = safe_get("Contact", ["name", "first_name", "last_name", "email_id", "mobile_no", "phone"], limit=300)
        data["contacts"]       = rows
        data["total_contacts"] = len(rows)

    # ── COMPANIES ────────────────────────────────────────────────────────────
    if any(w in q for w in ["company", "companies", "branch"]):
        rows = safe_get("Company", ["name", "company_name", "country", "default_currency", "phone_no"], limit=50)
        data["companies"] = rows

    # ── WAREHOUSES ───────────────────────────────────────────────────────────
    if any(w in q for w in ["warehouse", "warehouses", "godown", "store", "storage"]):
        rows = safe_get("Warehouse", ["name", "warehouse_name", "warehouse_type", "city", "is_group"], limit=100)
        data["warehouses"] = rows

    # ── BANK ACCOUNTS ────────────────────────────────────────────────────────
    if any(w in q for w in ["bank", "bank account", "bank balance"]):
        rows = safe_get("Bank Account", ["name", "account_name", "bank", "account_type", "is_default"], limit=50)
        data["bank_accounts"] = rows

    # ── PRICE LISTS ──────────────────────────────────────────────────────────
    if any(w in q for w in ["price", "price list", "pricing", "rate list"]):
        rows = safe_get("Item Price", ["name", "item_code", "item_name", "price_list", "price_list_rate", "currency"], limit=300)
        data["item_prices"] = rows

    # ── BUSINESS SUMMARY ─────────────────────────────────────────────────────
    if any(w in q for w in ["summary", "business", "overview", "dashboard", "report", "analytics"]):
        sinv_all      = safe_get("Sales Invoice", ["grand_total", "outstanding_amount", "docstatus", "status", "posting_date"], limit=2000)
        submitted_all = [i for i in sinv_all if str(i.get("docstatus")) == "1"]
        month_start   = str(frappe.utils.get_first_day(today))
        month_sinv2   = [i for i in submitted_all if str(i.get("posting_date", "")) >= month_start]
        pinv_all      = safe_get("Purchase Invoice", ["grand_total", "outstanding_amount", "docstatus"], limit=2000)
        submitted_pinv= [i for i in pinv_all if str(i.get("docstatus")) == "1"]

        data["business_summary"] = {
            "total_customers":         db_count("Customer"),
            "total_suppliers":         db_count("Supplier"),
            "total_items":             db_count("Item"),
            "total_employees":         db_count("Employee"),
            "total_leads":             db_count("Lead"),
            "total_sales_orders":      db_count("Sales Order"),
            "total_purchase_orders":   db_count("Purchase Order"),
            "total_quotations":        db_count("Quotation"),
            "total_delivery_notes":    db_count("Delivery Note"),
            "total_sales_invoices":    len(sinv_all),
            "total_purchase_invoices": len(pinv_all),
            "total_revenue":           sum(float(i.get("grand_total") or 0) for i in submitted_all),
            "revenue_this_month":      sum(float(i.get("grand_total") or 0) for i in month_sinv2),
            "total_outstanding":       sum(float(i.get("outstanding_amount") or 0) for i in submitted_all),
            "total_payable":           sum(float(i.get("outstanding_amount") or 0) for i in submitted_pinv),
            "overdue_count":           len([i for i in sinv_all if i.get("status") == "Overdue"]),
            "paid_invoice_count":      len([i for i in sinv_all if i.get("status") == "Paid"]),
        }

    return data


# ─────────────────────────────────────────────────────────────────────────────
#  CREATE ADDRESS
# ─────────────────────────────────────────────────────────────────────────────
def create_address(doctype, doc_name, gstin_details, gstin_value):
    try:
        country_doc_name = ensure_india_country()
        if not country_doc_name:
            return False
        address_line1 = gstin_details.get("address") or "Not Provided"
        city          = gstin_details.get("city") or "Not Provided"
        state         = gstin_details.get("state") or ""
        pincode       = gstin_details.get("pincode") or ""
        billing_addr  = frappe.get_doc({
            "doctype": "Address", "address_title": doc_name, "address_type": "Billing",
            "address_line1": address_line1, "city": city, "state": state, "pincode": pincode,
            "country": country_doc_name, "gstin": gstin_value, "is_primary_address": 1,
            "links": [{"link_doctype": doctype, "link_name": doc_name}]
        })
        billing_addr.insert(ignore_permissions=True)
        shipping_addr = frappe.get_doc({
            "doctype": "Address", "address_title": doc_name + "-Shipping", "address_type": "Shipping",
            "address_line1": address_line1, "city": city, "state": state, "pincode": pincode,
            "country": country_doc_name, "gstin": gstin_value, "is_shipping_address": 1,
            "links": [{"link_doctype": doctype, "link_name": doc_name}]
        })
        shipping_addr.insert(ignore_permissions=True)
        frappe.db.commit()
        return True
    except Exception as e:
        frappe.log_error("Address creation error: " + str(e))
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  CREATE FROM AI
# ─────────────────────────────────────────────────────────────────────────────
def create_from_ai(doctype, data):
    try:
        data["doctype"] = doctype
        gstin_details   = None
        gstin_value     = data.get("gstin", "")
        if doctype in ["Customer", "Supplier"] and gstin_value:
            gstin_details = get_gstin_details(gstin_value)
            if gstin_details.get("success"):
                legal_name = gstin_details.get("legal_name") or gstin_details.get("trade_name")
                if legal_name:
                    if doctype == "Customer":
                        data["customer_name"] = legal_name
                    else:
                        data["supplier_name"] = legal_name
                taxpayer_type    = gstin_details.get("taxpayer_type", "")
                gst_category_map = {"Regular": "Registered Regular", "Composition": "Registered Composition", "SEZ": "SEZ", "SEZ Developer": "SEZ Developer"}
                if frappe.db.has_column(doctype, "gst_category"):
                    data["gst_category"] = gst_category_map.get(taxpayer_type, "Registered Regular")
        name_field_map = {"Customer": "customer_name", "Supplier": "supplier_name", "Item": "item_name", "Lead": "lead_name", "Employee": "first_name"}
        name_field = name_field_map.get(doctype)
        if name_field and data.get(name_field):
            existing = frappe.db.exists(doctype, {name_field: data[name_field]})
            if existing:
                url = "/app/" + doctype.lower().replace(" ", "-") + "/" + existing
                return {"type": "info", "message": "⚠️ " + doctype + " <b>" + str(data[name_field]) + "</b> already exists.", "link": url}
        if doctype == "Employee":
            if not data.get("company"):
                data["company"] = frappe.defaults.get_global_default("company") or frappe.db.get_list("Company", limit=1)[0].name
            data.setdefault("date_of_joining", frappe.utils.today())
            data.setdefault("gender", "Male")
            data.setdefault("status", "Active")
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        addr_msg = ""
        if doctype in ["Customer", "Supplier"] and gstin_details and gstin_details.get("success"):
            addr_ok  = create_address(doctype, doc.name, gstin_details, gstin_value)
            addr_msg = "<br>📍 Billing & Shipping address created." if addr_ok else "<br>⚠️ Address could not be created automatically."
        url        = "/app/" + doctype.lower().replace(" ", "-") + "/" + doc.name
        gstin_info = ""
        if gstin_details and gstin_details.get("success"):
            gstin_info = "<br>🏢 <b>Legal Name:</b> " + str(gstin_details.get("legal_name", ""))
            if gstin_details.get("city"):
                gstin_info += "<br>📍 " + str(gstin_details.get("city", "")) + ", " + str(gstin_details.get("state", ""))
        return {"type": "success", "message": "✅ " + doctype + " <b>" + doc.name + "</b> created successfully!" + gstin_info + addr_msg, "doctype": doctype, "name": doc.name, "link": url}
    except Exception as e:
        frappe.log_error("create_from_ai error: " + str(e))
        return {"type": "error", "message": "❌ Error creating " + doctype + ": " + str(e)}


# ─────────────────────────────────────────────────────────────────────────────
#  TAX ACCOUNT HELPER
# ─────────────────────────────────────────────────────────────────────────────
def get_tax_account_head(invoice_type, company):
    try:
        if invoice_type == "sales":
            patterns = ["Output Tax GST", "Output GST", "Sales GST", "CGST", "SGST", "IGST", "Output Tax", "GST Output", "Tax Output"]
        else:
            patterns = ["Input Tax GST", "Input GST", "Purchase GST", "CGST", "SGST", "IGST", "Input Tax", "GST Input", "Tax Input"]
        for pattern in patterns:
            account = frappe.db.get_value("Account", {"account_name": ["like", f"%{pattern}%"], "company": company, "is_group": 0}, "name")
            if account:
                return account
        for pattern in patterns:
            account = frappe.db.get_value("Account", {"account_name": ["like", f"%{pattern}%"], "is_group": 0}, "name")
            if account:
                return account
        return frappe.db.get_value("Account", {"account_type": "Tax", "is_group": 0, "company": company}, "name")
    except Exception as e:
        frappe.log_error(f"Tax account lookup error: {str(e)}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  BILL IMAGE SCANNING
# ─────────────────────────────────────────────────────────────────────────────
def create_invoice_from_extracted(invoice_type, extracted):
    try:
        today   = frappe.utils.today()
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.db.get_list("Company", limit=1)[0].name
        )

        if invoice_type == "sales":
            doctype        = "Sales Invoice"
            party_field    = "customer"
            party_name_val = (extracted.get("party_name") or extracted.get("customer") or "Walk-in Customer").strip()
            existing_party = frappe.db.get_value("Customer", {"customer_name": party_name_val}, "name")
            if not existing_party:
                try:
                    cust = frappe.get_doc({"doctype": "Customer", "customer_name": party_name_val, "customer_type": "Company", "customer_group": "All Customer Groups", "territory": "All Territories"})
                    cust.insert(ignore_permissions=True)
                    frappe.db.commit()
                    party_lookup = cust.name
                except Exception as ce:
                    frappe.log_error("Auto-create customer: " + str(ce))
                    party_lookup = party_name_val
            else:
                party_lookup = existing_party
        else:
            doctype        = "Purchase Invoice"
            party_field    = "supplier"
            party_name_val = (extracted.get("party_name") or extracted.get("supplier") or "Unknown Supplier").strip()
            existing_party = frappe.db.get_value("Supplier", {"supplier_name": party_name_val}, "name")
            if not existing_party:
                try:
                    sup = frappe.get_doc({"doctype": "Supplier", "supplier_name": party_name_val, "supplier_type": "Company", "supplier_group": "All Supplier Groups"})
                    sup.insert(ignore_permissions=True)
                    frappe.db.commit()
                    party_lookup = sup.name
                except Exception as se:
                    frappe.log_error("Auto-create supplier: " + str(se))
                    party_lookup = party_name_val
            else:
                party_lookup = existing_party

        raw_items = extracted.get("items") or []
        inv_items = []
        if not frappe.db.exists("Item", "Misc Item"):
            try:
                misc = frappe.get_doc({"doctype": "Item", "item_name": "Misc Item", "item_code": "Misc Item", "item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 0})
                misc.insert(ignore_permissions=True)
                frappe.db.commit()
            except:
                pass

        for it in raw_items:
            item_name_val = (it.get("item_name") or it.get("description") or "Misc Item").strip()
            uom_val       = it.get("uom") or "Nos"
            if not frappe.db.exists("UOM", uom_val):
                uom_val = "Nos"
            item_code = (
                frappe.db.get_value("Item", {"item_name": item_name_val}, "name")
                or frappe.db.get_value("Item", {"item_code": item_name_val}, "name")
            )
            if not item_code:
                try:
                    new_item = frappe.get_doc({"doctype": "Item", "item_name": item_name_val, "item_code": item_name_val, "item_group": "All Item Groups", "stock_uom": uom_val, "is_stock_item": 0})
                    new_item.insert(ignore_permissions=True)
                    frappe.db.commit()
                    item_code = new_item.name
                except Exception as ie:
                    frappe.log_error("Auto-create item: " + str(ie))
                    item_code = "Misc Item"
                    uom_val   = "Nos"
            inv_items.append({
                "item_code":   item_code,
                "item_name":   item_name_val,
                "description": it.get("description") or item_name_val,
                "qty":         float(it.get("qty") or it.get("quantity") or 1),
                "rate":        float(it.get("rate") or it.get("unit_price") or it.get("price") or 0),
                "uom":         uom_val,
            })

        if not inv_items:
            inv_items = [{"item_code": "Misc Item", "item_name": "Misc Item", "description": "Auto-created from bill scan", "qty": 1, "rate": float(extracted.get("grand_total") or 0), "uom": "Nos"}]

        taxes            = []
        tax_account_head = None
        for tx in (extracted.get("taxes") or []):
            tax_amt = float(tx.get("amount") or tx.get("tax_amount") or 0)
            if tax_amt:
                if not tax_account_head:
                    tax_account_head = get_tax_account_head(invoice_type, company)
                account_head = tx.get("account_head") or tax_account_head
                if account_head:
                    taxes.append({"charge_type": "Actual", "account_head": account_head, "description": tx.get("description") or tx.get("tax_type") or "GST", "tax_amount": tax_amt})

        posting_date = extracted.get("posting_date") or extracted.get("invoice_date") or today
        inv_data = {
            "doctype":      doctype,
            "company":      company,
            party_field:    party_lookup,
            "posting_date": posting_date,
            "due_date":     extracted.get("due_date") or posting_date,
            "items":        inv_items,
        }
        if invoice_type == "purchase":
            bill_no = str(extracted.get("bill_no") or extracted.get("invoice_number") or "").strip()
            if bill_no:
                inv_data["bill_no"]   = bill_no[:140]
                inv_data["bill_date"] = posting_date
        if taxes:
            inv_data["taxes"] = taxes

        doc = frappe.get_doc(inv_data)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        url   = "/app/" + doctype.lower().replace(" ", "-") + "/" + doc.name
        label = "Sales Invoice" if invoice_type == "sales" else "Purchase Invoice"
        items_html = ""
        for it in inv_items[:6]:
            items_html += "<br>&nbsp;&nbsp;• <b>" + str(it["item_name"]) + "</b> × " + str(it["qty"]) + " @ ₹" + str(it["rate"])
        if len(inv_items) > 6:
            items_html += "<br>&nbsp;&nbsp;… and " + str(len(inv_items) - 6) + " more items"

        return {
            "type": "success",
            "message": (
                "🧾 <b>" + label + " Draft Created!</b>"
                "<br>👤 <b>Party:</b> " + str(party_name_val)
                + "<br>📅 <b>Date:</b> " + str(posting_date)
                + ("<br>🔢 <b>GSTIN:</b> " + str(extracted["gstin"]) if extracted.get("gstin") else "")
                + "<br>📦 <b>Items:</b>" + items_html
                + "<br>💰 <b>Grand Total:</b> ₹" + str(extracted.get("grand_total") or "—")
                + "<br><br><span style='color:#6b7280;font-size:12px'>✏️ Draft saved — review and submit in SkyERP</span>"
            ),
            "doctype": doctype,
            "name":    doc.name,
            "link":    url,
        }

    except Exception as e:
        frappe.log_error("create_invoice_from_extracted error: " + str(e))
        return {"type": "error", "message": "❌ Error creating invoice from bill: " + str(e)}


@frappe.whitelist()
def scan_bill_image(image_data, invoice_type="auto"):
    try:
        api_key = get_api_key()
        if not api_key:
            return {"type": "error", "message": "API key not configured."}

        if "," in image_data:
            mime_part, b64_part = image_data.split(",", 1)
            mime_type = mime_part.split(":")[1].split(";")[0] if ":" in mime_part else "image/jpeg"
        else:
            b64_part  = image_data
            mime_type = "image/jpeg"

        extraction_prompt = """You are an expert bill/invoice OCR system for SkyERP.
Extract ALL information from this bill or invoice image and return ONLY valid JSON.

IMPORTANT: Return ONLY the JSON object. No markdown, no code fences, no explanations.

Detect whether this is:
- A SALES bill  → issued BY a business TO a customer  
- A PURCHASE bill → received FROM a supplier

Return this exact JSON structure:
{"invoice_type": "sales" or "purchase", "party_name": "customer or supplier name", "invoice_number": "bill number", "posting_date": "YYYY-MM-DD", "due_date": "YYYY-MM-DD or null", "gstin": "GST number or null", "items": [{"item_name": "product name", "description": "full description", "qty": 1, "rate": 0.00, "uom": "Nos", "amount": 0.00}], "taxes": [{"tax_type": "CGST/SGST/IGST", "description": "e.g. CGST 9%", "amount": 0.00}], "subtotal": 0.00, "tax_total": 0.00, "grand_total": 0.00, "currency": "INR"}

Rules:
- Extract EVERY line item with quantities and rates
- Convert all dates to YYYY-MM-DD format
- Use null for missing fields
- Return ONLY valid JSON, no other text"""

        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + api_key,
            headers={"content-type": "application/json"},
            json={
                "contents": [{"parts": [{"inline_data": {"mime_type": mime_type, "data": b64_part}}, {"text": extraction_prompt}]}],
                "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.1},
            },
            timeout=90,
        )
        result = response.json()
        if "error" in result:
            return {"type": "error", "message": "Gemini API Error: " + str(result["error"].get("message", ""))}

        ai_text     = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        extracted   = None
        parse_error = None

        if "```" in ai_text:
            for part in ai_text.split("```"):
                part = part.strip()
                if part.lower().startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") and part.endswith("}"):
                    try:
                        extracted = json.loads(part)
                        break
                    except Exception as e:
                        parse_error = str(e)

        if not extracted:
            try:
                s = ai_text.find("{")
                e = ai_text.rfind("}")
                if s != -1 and e != -1 and e > s:
                    extracted = json.loads(ai_text[s:e + 1])
            except Exception as ex:
                parse_error = str(ex)

        if not extracted:
            try:
                extracted = json.loads(ai_text)
            except Exception as ex:
                parse_error = str(ex)

        if not extracted:
            frappe.log_error("Bill scan parse error: " + str(parse_error) + "\nRaw: " + repr(ai_text[:800]))
            return {"type": "error", "message": "Could not read the bill data. Please try a clearer photo."}

        detected   = (extracted.get("invoice_type") or "").lower()
        final_type = detected if invoice_type == "auto" and detected in ["sales", "purchase"] else (invoice_type if invoice_type in ["sales", "purchase"] else "sales")

        return create_invoice_from_extracted(final_type, extracted)

    except requests.exceptions.ConnectionError:
        return {"type": "error", "message": "❌ Cannot connect to Gemini AI. Check internet connection."}
    except Exception as e:
        frappe.log_error("scan_bill_image error: " + str(e))
        return {"type": "error", "message": "Error scanning bill: " + str(e)[:200]}


# ─────────────────────────────────────────────────────────────────────────────
#  TEST CONNECTION
# ─────────────────────────────────────────────────────────────────────────────
@frappe.whitelist()
def test_connection():
    try:
        import socket
        try:
            socket.setdefaulttimeout(5)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        except:
            return {"success": False, "message": "No internet connection on server."}
        api_key = get_api_key()
        if not api_key:
            return {"success": False, "message": "API key not configured."}
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + api_key,
            headers={"content-type": "application/json"},
            json={"contents": [{"parts": [{"text": "Say OK"}]}], "generationConfig": {"maxOutputTokens": 5}},
            timeout=15
        )
        result = response.json()
        if "error" in result:
            return {"success": False, "message": "API Error: " + str(result["error"].get("message", ""))}
        return {"success": True, "message": "Connected"}
    except Exception as e:
        return {"success": False, "message": str(e)[:80]}


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN AI ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────
@frappe.whitelist()
def ask_ai(question, doctype="", conversation_history=""):
    api_key = get_api_key()
    if not api_key:
        return {"type": "error", "message": "API key not configured. Run: bench --site YOUR_SITE set-config vertex_api_key YOUR_KEY"}

    q       = question.lower().strip()
    q_clean = re.sub(r"[!?.]+$", "", q.strip())

    greetings = ["hi", "hii", "hiii", "hello", "hey", "heyy", "good morning", "good evening", "good afternoon", "how are you"]
    if q_clean in greetings:
        user = frappe.session.user_fullname or "there"
        return {"type": "text", "message": (
            "👋 Hello <b>" + user + "</b>! I am your SkyERP AI Assistant.<br><br>"
            "I can:<br>"
            "• Answer questions about your <b>live SkyERP data</b><br>"
            "• Create records (customers, suppliers, items, employees)<br>"
            "• Auto-fetch details from GSTIN<br>"
            "• Analyze sales, purchases, invoices, inventory<br>"
            "• 📸 <b>Scan bill images</b> to auto-create invoice drafts<br><br>"
            "Type <b>help</b> to see all commands."
        )}

    if q_clean in ["help", "what can you do", "commands"]:
        return {"type": "text", "message": (
            "🤖 <b>SkyERP AI Assistant Commands:</b><br><br>"
            "<b>➕ Create Records:</b><br>"
            "- create customer Harsh Ahir<br>"
            "- create supplier ABC Traders<br>"
            "- create customer using GSTIN 07AAGFF2194N1Z1<br>"
            "- add item Laptop<br>"
            "- add employee Ravi Patel<br><br>"
            "<b>📊 Data Questions (general):</b><br>"
            "- how many customers / suppliers / items / employees<br>"
            "- list all customers / suppliers / items<br>"
            "- total revenue this month / year<br>"
            "- overdue invoices / unpaid invoices<br>"
            "- business summary / dashboard<br><br>"
            "<b>🔍 Entity-specific questions:</b><br>"
            "- how many sales invoices for STTC SBI<br>"
            "- total billing of ABC Ltd<br>"
            "- outstanding amount of XYZ customer<br>"
            "- orders from supplier ABC Traders<br>"
            "- stock of item Laptop<br>"
            "- salary of employee Ravi Patel<br>"
            "- attendance of John<br><br>"
            "<b>📄 Specific Document:</b><br>"
            "- show SINV-2024-00001<br>"
            "- details of SO-2024-00001<br><br>"
            "<b>📸 Bill Scan → Invoice:</b><br>"
            "- Click the 📎 icon to upload a bill image<br>"
            "- AI reads the bill and creates the invoice draft!"
        )}

    live_data = get_live_data(question)

    system_prompt = """You are an advanced SkyERP AI Assistant with access to LIVE business data.

STRICT RESPONSE RULES — return ONLY valid JSON, no text outside JSON:

For answers/questions:
{"type": "text", "message": "your HTML answer here"}

For creating records:
{"type": "create", "doctype": "DocType", "data": {...}}

For listing records:
{"type": "list", "message": "header text", "items": ["name1", "name2"], "doctype": "Customer"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENTITY-SPECIFIC DATA (HIGHEST PRIORITY):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When live data has "entity_customer_*" keys → use them for all customer questions:
- entity_customer_invoice_count   = total invoices (ALL statuses) for that customer
- entity_customer_submitted_count = submitted/confirmed invoices only
- entity_customer_invoices        = full invoice list for that customer
- entity_customer_total_billing   = total amount billed (submitted only)
- entity_customer_outstanding     = total outstanding balance
- entity_customer_paid_count      = count of paid invoices
- entity_customer_overdue_count   = count of overdue invoices
- entity_customer_order_count     = number of sales orders
- entity_customer_payment_total   = total payments received from customer
- entity_customer_delivery_note_count = delivery notes count

When live data has "entity_supplier_*" keys → use them for all supplier questions:
- entity_supplier_invoice_count   = purchase invoices from that supplier
- entity_supplier_total_billing   = total amount purchased
- entity_supplier_outstanding     = total payable to supplier
- entity_supplier_order_count     = purchase orders count

When live data has "entity_item_*" keys:
- entity_item_total_stock         = current stock quantity
- entity_item_total_sold_qty      = total qty sold
- entity_item_total_revenue       = total revenue from item

When live data has "entity_employee_*" keys:
- entity_employee_present_days    = days present
- entity_employee_absent_days     = days absent
- entity_employee_latest_net_pay  = latest salary

RULE: If entity data exists in the live data — ALWAYS use it. Never say "I don't have data".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERAL DATA RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Use EXACT numbers from live data — never guess or fabricate
- For listing: extract "customer_name" from customers array for items[]
- For counting: use exact count fields
- Always show ₹ symbol for Indian Rupee amounts
- Format numbers with commas for readability

CREATE FIELD DEFAULTS:
- Customer: customer_name, customer_type=Individual, customer_group=All Customer Groups, territory=All Territories
- Supplier: supplier_name, supplier_type=Individual, supplier_group=All Supplier Groups
- Item: item_name, item_code=same, item_group=All Item Groups, stock_uom=Nos, is_stock_item=1
- Employee: first_name, last_name, gender=Male, status=Active
- Lead: lead_name, status=Open

Return ONLY valid JSON. No explanation outside JSON."""

    live_data_str = json.dumps(live_data, indent=2, default=str)
    if len(live_data_str) > 14000:
        trimmed = {}
        for k, v in live_data.items():
            if isinstance(v, list) and len(v) > 50:
                trimmed[k]                 = v[:50]
                trimmed[k + "_total_count"]= len(v)
            else:
                trimmed[k] = v
        live_data_str = json.dumps(trimmed, indent=2, default=str)[:14000]

    user_message = "LIVE SkyERP Data:\n" + live_data_str + "\n\nUser Question: " + question

    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + api_key,
            headers={"content-type": "application/json"},
            json={
                "contents": [{"parts": [{"text": system_prompt + "\n\n" + user_message}]}],
                "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.1}
            },
            timeout=60
        )
        result = response.json()

        if "error" in result:
            return {"type": "error", "message": "API Error: " + str(result["error"].get("message", "Unknown error"))}

        ai_reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()

        if "```" in ai_reply:
            for part in ai_reply.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    ai_reply = part
                    break
        ai_reply = ai_reply.strip()

        try:
            parsed = json.loads(ai_reply)
        except:
            return {"type": "text", "message": ai_reply}

        if parsed.get("type") == "create":
            return create_from_ai(parsed.get("doctype"), parsed.get("data", {}))

        return parsed

    except requests.exceptions.ConnectionError:
        return {"type": "error", "message": "❌ Cannot connect to Gemini AI. Check internet on server.<br>Run: <code>ping google.com</code>"}
    except Exception as e:
        frappe.log_error("AI Assistant Error: " + str(e))
        return {"type": "error", "message": "Something went wrong: " + str(e)[:150]}
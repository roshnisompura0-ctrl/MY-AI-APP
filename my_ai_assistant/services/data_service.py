"""
Safe Data Retrieval Service
Handles all database queries with safety checks and limits
"""

import frappe

def safe_get_list(doctype, fields=None, filters=None, limit=500, order_by="modified desc"):
    """
    Safely get list of documents with error handling
    """
    try:
        if not fields:
            fields = ["name"]

        return frappe.get_all(
            doctype,
            fields=fields,
            filters=filters or {},
            limit=limit,
            ignore_permissions=True,
            order_by=order_by
        )
    except Exception as e:
        frappe.log_error(f"safe_get_list error for {doctype}: {str(e)}")
        return []

def safe_get_full_doc(doctype, doc_name):
    """
    Safely get full document with child tables
    """
    try:
        doc = frappe.get_doc(doctype, doc_name)
        data = doc.as_dict()

        # Include child table data
        for field in doc.meta.get_table_fields():
            if hasattr(doc, field.fieldname):
                items = getattr(doc, field.fieldname)
                data[field.fieldname] = [item.as_dict() for item in items]

        return data
    except Exception as e:
        return {"error": str(e), "doctype": doctype, "name": doc_name}

def safe_count(doctype, filters=None):
    """Safely get count with error handling"""
    try:
        return frappe.db.count(doctype, filters=filters or {})
    except:
        return 0

def get_entity_statistics(entity_type, entity_id):
    """
    Get comprehensive statistics for an entity
    Customer, Supplier, Item, Employee
    """
    stats = {}
    today = frappe.utils.today()
    month_start = str(frappe.utils.get_first_day(today))

    try:
        if entity_type == "Customer":
            # Sales Invoices
            sinv = safe_get_list("Sales Invoice",
                ["name", "status", "posting_date", "grand_total", "outstanding_amount", "docstatus"],
                {"customer": entity_id}, limit=1000)
            submitted = [i for i in sinv if str(i.get("docstatus")) == "1"]

            stats["total_invoices"] = len(sinv)
            stats["submitted_invoices"] = len(submitted)
            stats["total_revenue"] = sum(float(i.get("grand_total", 0)) for i in submitted)
            stats["outstanding_amount"] = sum(float(i.get("outstanding_amount", 0)) for i in submitted)
            stats["paid_count"] = len([i for i in sinv if i.get("status") == "Paid"])
            stats["overdue_count"] = len([i for i in sinv if i.get("status") == "Overdue"])

            # Sales Orders
            so = safe_get_list("Sales Order",
                ["name", "status", "transaction_date", "grand_total"],
                {"customer": entity_id}, limit=500)
            stats["total_orders"] = len(so)

            # Payments
            payments = safe_get_list("Payment Entry",
                ["name", "paid_amount", "posting_date"],
                {"party": entity_id, "party_type": "Customer"}, limit=300)
            stats["total_payments"] = len(payments)
            stats["total_paid"] = sum(float(p.get("paid_amount", 0)) for p in payments)

        elif entity_type == "Supplier":
            # Purchase Invoices
            pinv = safe_get_list("Purchase Invoice",
                ["name", "status", "posting_date", "grand_total", "outstanding_amount", "docstatus"],
                {"supplier": entity_id}, limit=1000)
            submitted = [i for i in pinv if str(i.get("docstatus")) == "1"]

            stats["total_invoices"] = len(pinv)
            stats["total_purchases"] = sum(float(i.get("grand_total", 0)) for i in submitted)
            stats["outstanding_amount"] = sum(float(i.get("outstanding_amount", 0)) for i in submitted)

            # Purchase Orders
            po = safe_get_list("Purchase Order",
                ["name", "status", "transaction_date", "grand_total"],
                {"supplier": entity_id}, limit=500)
            stats["total_orders"] = len(po)

        elif entity_type == "Item":
            # Sales history
            sinv_items = frappe.db.sql("""
                SELECT sii.qty, sii.rate, sii.amount, si.posting_date
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE sii.item_code = %s AND si.docstatus = 1
                ORDER BY si.posting_date DESC LIMIT 200
            """, entity_id, as_dict=True)

            stats["total_sold_qty"] = sum(float(r.get("qty", 0)) for r in sinv_items)
            stats["total_revenue"] = sum(float(r.get("amount", 0)) for r in sinv_items)

            # Current stock
            stock = frappe.db.sql("""
                SELECT warehouse, actual_qty, valuation_rate
                FROM `tabBin` WHERE item_code = %s
            """, entity_id, as_dict=True)
            stats["stock_by_warehouse"] = stock
            stats["total_stock"] = sum(float(r.get("actual_qty", 0)) for r in stock)

        elif entity_type == "Employee":
            # Attendance
            attendance = safe_get_list("Attendance",
                ["name", "attendance_date", "status"],
                {"employee": entity_id}, limit=200)
            stats["total_attendance_records"] = len(attendance)
            stats["present_days"] = len([a for a in attendance if a.get("status") == "Present"])
            stats["absent_days"] = len([a for a in attendance if a.get("status") == "Absent"])

            # Salary
            salary_slips = safe_get_list("Salary Slip",
                ["name", "start_date", "end_date", "net_pay", "status"],
                {"employee": entity_id}, limit=24)
            stats["salary_slips"] = salary_slips
            submitted_slips = [s for s in salary_slips if s.get("status") == "Submitted"]
            stats["latest_net_pay"] = submitted_slips[0].get("net_pay") if submitted_slips else None

            # Leaves
            leaves = safe_get_list("Leave Application",
                ["name", "leave_type", "from_date", "to_date", "total_leave_days", "status"],
                {"employee": entity_id}, limit=50)
            stats["leave_applications"] = leaves

    except Exception as e:
        frappe.log_error(f"Entity stats error for {entity_type} {entity_id}: {str(e)}")

    return stats

def get_business_overview():
    """Get complete business summary statistics"""
    today = frappe.utils.today()
    month_start = str(frappe.utils.get_first_day(today))
    year_start = today[:4] + "-01-01"

    overview = {}

    # Master data counts
    overview["customers"] = safe_count("Customer")
    overview["suppliers"] = safe_count("Supplier")
    overview["items"] = safe_count("Item")
    overview["employees"] = safe_count("Employee")
    overview["leads"] = safe_count("Lead")

    # Sales data
    sinv = safe_get_list("Sales Invoice",
        ["grand_total", "outstanding_amount", "docstatus", "status", "posting_date"],
        limit=2000)
    submitted_sinv = [i for i in sinv if str(i.get("docstatus")) == "1"]

    overview["total_sales_invoices"] = len(sinv)
    overview["total_revenue"] = sum(float(i.get("grand_total", 0)) for i in submitted_sinv)
    overview["revenue_this_month"] = sum(
        float(i.get("grand_total", 0)) for i in submitted_sinv
        if str(i.get("posting_date", "")) >= month_start
    )
    overview["total_outstanding"] = sum(float(i.get("outstanding_amount", 0)) for i in submitted_sinv)
    overview["overdue_invoices"] = len([i for i in sinv if i.get("status") == "Overdue"])
    overview["paid_invoices"] = len([i for i in sinv if i.get("status") == "Paid"])

    # Purchase data
    pinv = safe_get_list("Purchase Invoice",
        ["grand_total", "outstanding_amount", "docstatus"],
        limit=2000)
    submitted_pinv = [i for i in pinv if str(i.get("docstatus")) == "1"]

    overview["total_purchase_invoices"] = len(pinv)
    overview["total_purchases"] = sum(float(i.get("grand_total", 0)) for i in submitted_pinv)
    overview["total_payable"] = sum(float(i.get("outstanding_amount", 0)) for i in submitted_pinv)

    # Orders
    overview["sales_orders"] = safe_count("Sales Order")
    overview["purchase_orders"] = safe_count("Purchase Order")
    overview["quotations"] = safe_count("Quotation")

    return overview

"""
Dynamic Doctype Discovery Service
Handles detection and introspection of all ERPNext doctypes
"""

import frappe
from frappe import get_meta

def discover_all_doctypes(category=None):
    """
    Discover all available doctypes in the system
    Returns list of doctype names grouped by category
    """
    try:
        all_doctypes = frappe.db.sql("""
            SELECT name, issingle, istable, issubmittable, module
            FROM `tabDocType`
            WHERE custom = 0 AND is_virtual = 0
            ORDER BY name
        """, as_dict=True)

        result = {
            "masters": [],
            "transactions": [],
            "setup": [],
            "other": []
        }

        for dt in all_doctypes:
            name = dt.get("name")
            if dt.get("issingle"):
                result["setup"].append(name)
            elif dt.get("istable"):
                continue  # Skip child tables
            elif dt.get("issubmittable"):
                result["transactions"].append(name)
            elif any(x in name.lower() for x in ["item", "customer", "supplier", "employee", "account", "warehouse"]):
                result["masters"].append(name)
            else:
                result["other"].append(name)

        return result.get(category, result) if category else result
    except Exception as e:
        frappe.log_error(f"Doctype discovery error: {str(e)}")
        return {}

def get_doctype_fields(doctype, exclude_system=True):
    """
    Get all fields for a doctype with metadata
    Returns list of field dicts with name, type, required, etc.
    """
    try:
        meta = get_meta(doctype)
        fields = []

        system_fields = {
            "name", "owner", "creation", "modified", "modified_by",
            "docstatus", "idx", "parent", "parenttype", "parentfield",
            "_user_tags", "_comments", "_assign", "_liked_by"
        }

        ui_fields = {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}

        for field in meta.fields:
            if field.fieldtype in ui_fields:
                continue
            if exclude_system and field.fieldname in system_fields:
                continue
            if exclude_system and field.fieldname.startswith("_"):
                continue

            fields.append({
                "fieldname": field.fieldname,
                "fieldtype": field.fieldtype,
                "label": field.label,
                "reqd": field.reqd,
                "options": field.options,
                "default": field.default,
                "description": field.description,
                "depends_on": field.depends_on
            })

        return fields[:50]  # Limit to prevent token overflow
    except Exception as e:
        frappe.log_error(f"Get doctype fields error for {doctype}: {str(e)}")
        return []

def get_doctype_structure(doctype):
    """
    Get complete structure info for a doctype
    Used for AI to understand how to create documents
    """
    try:
        meta = get_meta(doctype)

        # Get required fields
        required_fields = []
        optional_fields = []

        for field in meta.fields:
            if field.fieldtype in ["Section Break", "Column Break", "Tab Break", "HTML", "Button", "Attach", "Attach Image"]:
                continue
            if field.fieldname.startswith("_"):
                continue

            field_info = {
                "name": field.fieldname,
                "type": field.fieldtype,
                "label": field.label,
                "options": field.options
            }

            if field.reqd and not field.default:
                required_fields.append(field_info)
            else:
                optional_fields.append(field_info)

        # Get child table fields
        table_fields = []
        for field in meta.get_table_fields():
            table_fields.append({
                "name": field.fieldname,
                "label": field.label,
                "child_doctype": field.options,
                "fields": get_doctype_fields(field.options, exclude_system=True)[:10]
            })

        return {
            "doctype": doctype,
            "name_field": meta.name_field,
            "autoname": meta.autoname,
            "required_fields": required_fields[:10],
            "optional_fields": optional_fields[:20],
            "table_fields": table_fields[:3],
            "is_submittable": meta.is_submittable,
            "has_mapping": bool(meta.get("mapping"))
        }
    except Exception as e:
        frappe.log_error(f"Get doctype structure error for {doctype}: {str(e)}")
        return {"doctype": doctype, "error": str(e)}

def detect_doctype_from_question(question):
    """
    Advanced doctype detection from user question
    Returns (doctype, doc_id) tuple or (None, None)
    """
    import re

    q = question.lower().strip()

    # GSTIN detection
    gstin_match = re.search(
        r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9]{1}[A-Z]{1}[0-9]{1}\b",
        question, re.IGNORECASE
    )
    if gstin_match:
        return "GSTIN", gstin_match.group(1).upper()

    # Document ID patterns
    doc_patterns = [
        (r"\bSINV-[\w-]+\b", "Sales Invoice"),
        (r"\bPINV-[\w-]+\b", "Purchase Invoice"),
        (r"\bSO-[\w-]+\b", "Sales Order"),
        (r"\bPO-[\w-]+\b", "Purchase Order"),
        (r"\bQUOT-[\w-]+\b", "Quotation"),
        (r"\bDN-[\w-]+\b", "Delivery Note"),
        (r"\bPR-[\w-]+\b", "Purchase Receipt"),
        (r"\bJV-[\w-]+\b", "Journal Entry"),
        (r"\bPAY-[\w-]+\b", "Payment Entry"),
        (r"\bHR-EMP-[\w-]+\b", "Employee"),
    ]

    for pattern, doctype in doc_patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return doctype, match.group(0).upper()

    # Keyword-based detection with scoring
    keyword_scores = {
        "Sales Invoice": ["sales invoice", "sinv", "customer invoice", "outgoing invoice"],
        "Purchase Invoice": ["purchase invoice", "pinv", "supplier invoice", "incoming invoice", "bill"],
        "Sales Order": ["sales order", "so-", "customer order", "sale order"],
        "Purchase Order": ["purchase order", "po-", "supplier order", "po to"],
        "Quotation": ["quotation", "quote", "estimation", "estimate"],
        "Delivery Note": ["delivery note", "dn-", "delivery", "dispatch"],
        "Customer": ["customer", "client", "buyer", "debtor"],
        "Supplier": ["supplier", "vendor", "seller", "creditor"],
        "Item": ["item", "product", "goods", "material", "sku"],
        "Employee": ["employee", "staff", "worker", "team member"],
        "Lead": ["lead", "prospect", "opportunity"],
        "Payment Entry": ["payment", "receipt", "collection"],
        "Journal Entry": ["journal", "voucher", "jv"],
    }

    best_match = None
    best_score = 0

    for doctype, keywords in keyword_scores.items():
        score = sum(2 if kw in q else 0 for kw in keywords)
        if score > best_score:
            best_score = score
            best_match = doctype

    return best_match if best_score > 0 else None, None

def get_all_entity_names(doctype, limit=2000):
    """
    Get all names for a doctype with display names
    Used for entity extraction
    """
    try:
        # Determine name field
        meta = get_meta(doctype)
        name_field = meta.name_field or "name"

        if doctype == "Customer":
            fields = ["name", "customer_name as display"]
        elif doctype == "Supplier":
            fields = ["name", "supplier_name as display"]
        elif doctype == "Item":
            fields = ["name", "item_name as display"]
        elif doctype == "Employee":
            fields = ["name", "employee_name as display"]
        elif doctype == "Lead":
            fields = ["name", "lead_name as display"]
        else:
            fields = ["name", f"{name_field} as display"]

        return frappe.get_all(doctype, fields=fields, limit=limit, ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"Get entity names error for {doctype}: {str(e)}")
        return []

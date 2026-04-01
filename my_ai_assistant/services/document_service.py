"""
Document Creation Service
Handles creating all types of ERPNext documents with validation
"""

import frappe

def create_document(doctype, data, auto_create_linked=False):
    """
    Generic document creator with validation and error handling
    """
    try:
        data["doctype"] = doctype

        # Get doctype meta
        meta = frappe.get_meta(doctype)

        # Apply field defaults
        data = apply_field_defaults(doctype, data, meta)

        # Check for duplicates
        duplicate_check = check_duplicate(doctype, data, meta)
        if duplicate_check:
            return {
                "type": "info",
                "message": f"⚠️ {doctype} already exists: <b>{duplicate_check}</b>",
                "link": f"/app/{doctype.lower().replace(' ', '-')}/{duplicate_check}"
            }

        # Create document
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        # Create addresses for Customer/Supplier if GSTIN provided
        if doctype in ["Customer", "Supplier"] and data.get("gstin"):
            create_addresses_for_gstin(doctype, doc.name, data.get("gstin"))

        return {
            "type": "success",
            "message": f"✅ {doctype} <b>{doc.name}</b> created successfully!",
            "doctype": doctype,
            "name": doc.name,
            "link": f"/app/{doctype.lower().replace(' ', '-')}/{doc.name}"
        }

    except Exception as e:
        frappe.log_error(f"Create document error for {doctype}: {str(e)}")
        return {
            "type": "error",
            "message": f"❌ Error creating {doctype}: {str(e)[:200]}"
        }

def apply_field_defaults(doctype, data, meta=None):
    """Apply default values for required fields"""
    if not meta:
        meta = frappe.get_meta(doctype)

    # Get company default
    company = frappe.defaults.get_global_default("company")
    if not company:
        try:
            company = frappe.db.get_list("Company", limit=1)[0].name
        except:
            pass

    # Doctype-specific defaults
    defaults_map = {
        "Customer": {
            "customer_type": "Individual",
            "customer_group": "All Customer Groups",
            "territory": "All Territories"
        },
        "Supplier": {
            "supplier_type": "Company",
            "supplier_group": "All Supplier Groups"
        },
        "Item": {
            "item_group": "All Item Groups",
            "stock_uom": "Nos",
            "is_stock_item": 1
        },
        "Employee": {
            "company": company,
            "gender": "Male",
            "status": "Active",
            "date_of_joining": frappe.utils.today()
        },
        "Lead": {
            "status": "Open"
        }
    }

    # Apply defaults
    for field, value in defaults_map.get(doctype, {}).items():
        if not data.get(field):
            data[field] = value

    # Apply general defaults from meta
    for field in meta.fields:
        if field.reqd and not data.get(field.fieldname) and field.default:
            data[field.fieldname] = field.default

    return data

def check_duplicate(doctype, data, meta=None):
    """Check if document with same key field already exists"""
    # Map doctypes to their identifying fields
    key_fields = {
        "Customer": ["customer_name", "name"],
        "Supplier": ["supplier_name", "name"],
        "Item": ["item_name", "item_code", "name"],
        "Employee": ["employee_name", "name"],
        "Lead": ["lead_name", "email_id", "name"],
        "Contact": ["email_id", "mobile_no"],
        "Address": ["address_line1", "city"]
    }

    fields_to_check = key_fields.get(doctype, ["name"])

    for field in fields_to_check:
        if data.get(field):
            existing = frappe.db.exists(doctype, {field: data[field]})
            if existing:
                return existing

    return None

def create_addresses_for_gstin(doctype, doc_name, gstin):
    """Create billing and shipping addresses from GSTIN"""
    try:
        from india_compliance.gst_india.api_classes.public import PublicAPI
        api = PublicAPI()
        response = api.get_gstin_info(gstin)

        if response and isinstance(response, dict):
            data = response.get("data", response)
            legal_name = data.get("lgnm") or data.get("tradeName")
            pradr = data.get("pradr", {})
            addr = pradr.get("addr", {}) if isinstance(pradr, dict) else {}

            address_line1 = ", ".join(filter(None, [
                addr.get("bno"), addr.get("bnm"), addr.get("st")
            ])) or "Not Provided"

            city = addr.get("loc") or "Not Provided"
            state = addr.get("stcd") or ""
            pincode = addr.get("pncd") or ""

            # Get or create India country
            country = get_or_create_india()

            # Create billing address
            billing = frappe.get_doc({
                "doctype": "Address",
                "address_title": doc_name,
                "address_type": "Billing",
                "address_line1": address_line1,
                "city": city,
                "state": state,
                "pincode": pincode,
                "country": country,
                "gstin": gstin,
                "is_primary_address": 1,
                "links": [{"link_doctype": doctype, "link_name": doc_name}]
            })
            billing.insert(ignore_permissions=True)

            # Create shipping address
            shipping = frappe.get_doc({
                "doctype": "Address",
                "address_title": f"{doc_name}-Shipping",
                "address_type": "Shipping",
                "address_line1": address_line1,
                "city": city,
                "state": state,
                "pincode": pincode,
                "country": country,
                "gstin": gstin,
                "is_shipping_address": 1,
                "links": [{"link_doctype": doctype, "link_name": doc_name}]
            })
            shipping.insert(ignore_permissions=True)

            frappe.db.commit()
            return True
    except Exception as e:
        frappe.log_error(f"Address creation error: {str(e)}")

    return False

def get_or_create_india():
    """Get India country doc or create if missing"""
    try:
        for name in ["India", "INDIA", "india"]:
            if frappe.db.exists("Country", name):
                return name

        # Create India
        doc = frappe.get_doc({
            "doctype": "Country",
            "country_name": "India",
            "code": "IN"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except:
        return "India"

def get_tax_account(invoice_type="sales", company=None):
    """Get appropriate tax account for invoices"""
    try:
        company = company or frappe.defaults.get_global_default("company")

        if invoice_type == "sales":
            patterns = ["Output Tax GST", "Output GST", "Sales GST", "Output Tax"]
        else:
            patterns = ["Input Tax GST", "Input GST", "Purchase GST", "Input Tax"]

        for pattern in patterns:
            account = frappe.db.get_value("Account",
                {"account_name": ["like", f"%{pattern}%"], "company": company, "is_group": 0},
                "name")
            if account:
                return account

        # Fallback: any tax account
        return frappe.db.get_value("Account",
            {"account_type": "Tax", "is_group": 0, "company": company},
            "name")
    except:
        return None

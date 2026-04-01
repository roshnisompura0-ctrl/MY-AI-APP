"""
GSTIN Helper Utility
Handles GSTIN verification and data fetching
"""

import frappe
import re

def get_gstin_details(gstin):
    """Fetch GSTIN details from India Compliance or cache"""
    try:
        gstin = gstin.upper().strip()

        # Validate format
        if not re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9]{1}[A-Z]{1}[0-9]{1}$", gstin):
            return {"error": "Invalid GSTIN format", "gstin": gstin}

        # Try India Compliance API
        try:
            from india_compliance.gst_india.api_classes.public import PublicAPI
            api = PublicAPI()
            response = api.get_gstin_info(gstin)

            if response and isinstance(response, dict):
                data = response.get("data", response)

                # Parse address
                pradr = data.get("pradr", {})
                addr = pradr.get("addr", {}) if isinstance(pradr, dict) else {}

                address_parts = [addr.get(k) for k in ["bno", "bnm", "st", "locality"] if addr.get(k)]
                full_address = ", ".join(address_parts) if address_parts else data.get("adr", "")

                return {
                    "success": True,
                    "gstin": gstin,
                    "legal_name": data.get("lgnm") or data.get("tradeName"),
                    "trade_name": data.get("tradeName") or data.get("lgnm"),
                    "address": full_address,
                    "city": addr.get("loc", ""),
                    "state": addr.get("stcd", ""),
                    "pincode": addr.get("pncd", ""),
                    "status": data.get("sts", ""),
                    "taxpayer_type": data.get("dty", ""),
                    "registration_date": data.get("rgdt", ""),
                    "last_update": data.get("lstupdt", "")
                }
        except Exception as e:
            frappe.log_error(f"India Compliance API error: {str(e)}")

        # Try cached data
        try:
            cached = frappe.db.get_value("GSTIN Detail",
                {"gstin": gstin},
                ["gstin", "legal_name", "trade_name", "address_line_1", "city", "state", "pincode", "status"],
                as_dict=True)

            if cached and cached.legal_name:
                return {
                    "success": True,
                    "gstin": cached.gstin,
                    "legal_name": cached.legal_name,
                    "trade_name": cached.trade_name or cached.legal_name,
                    "address": cached.address_line_1 or "",
                    "city": cached.city,
                    "state": cached.state,
                    "pincode": cached.pincode,
                    "status": cached.status,
                    "source": "cache"
                }
        except:
            pass

        return {"error": "Could not fetch GSTIN details", "gstin": gstin}

    except Exception as e:
        return {"error": str(e), "gstin": gstin}

def get_gst_category(taxpayer_type):
    """Map taxpayer type to GST category"""
    mapping = {
        "Regular": "Registered Regular",
        "Composition": "Registered Composition",
        "SEZ": "SEZ",
        "SEZ Developer": "SEZ Developer",
        "Casual Taxable Person": "Casual Taxable Person",
        "Input Service Distributor": "Input Service Distributor",
        "Non Resident": "Non Resident"
    }
    return mapping.get(taxpayer_type, "Registered Regular")

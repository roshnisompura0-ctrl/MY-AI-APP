"""
Site-safe Configuration Manager
Handles API keys and settings safely across multiple sites
"""

import frappe
from frappe.utils import cstr

def get_api_key():
    """Get AI API key from site config (safe for multi-site)"""
    # Priority: site_config > common_config > env
    api_key = (
        frappe.conf.get("vertex_api_key")
        or frappe.conf.get("gemini_api_key")
        or frappe.conf.get("ai_api_key")
    )
    return cstr(api_key) if api_key else None

def get_ai_model():
    """Get configured AI model with fallback"""
    return frappe.conf.get("ai_model") or "gemini-2.5-flash"

def get_max_tokens():
    """Get max output tokens configuration"""
    return frappe.conf.get("ai_max_tokens") or 2048

def get_temperature():
    """Get AI temperature setting"""
    return frappe.conf.get("ai_temperature") or 0.1

def is_feature_enabled(feature_name):
    """Check if a feature is enabled for current site"""
    enabled = frappe.conf.get(f"ai_enable_{feature_name}", True)
    return enabled in (True, 1, "1", "True", "true")

def get_request_timeout():
    """Get API request timeout (seconds)"""
    return frappe.conf.get("ai_request_timeout") or 60

def get_max_data_limit(doctype):
    """Get max records limit for doctype queries"""
    limits = frappe.conf.get("ai_data_limits", {})
    return limits.get(doctype, 1000)

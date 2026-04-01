"""
API Endpoints for AI Assistant
Clean API layer calling internal services
"""

import frappe
import json

# Import main orchestrator
from my_ai_assistant.assistant import ask_ai, process_image, discover_doctypes, get_doctype_info

@frappe.whitelist()
def get_ai_response(prompt, user=None):
    """
    Main AI response endpoint - handles all queries globally
    Backwards compatible with original API
    """
    try:
        result = ask_ai(question=prompt, conversation_history="")
        return result
    except Exception as e:
        frappe.log_error(f"API get_ai_response error: {str(e)}")
        return {"type": "error", "message": f"Service error: {str(e)[:200]}"}

@frappe.whitelist()
def process_document_image_api(image_data, document_type="auto"):
    """
    Process document image and create entry
    Supports: Sales Invoice, Purchase Invoice, Sales Order, Purchase Order
    """
    try:
        result = process_image(image_data=image_data, document_type=document_type)
        return result
    except Exception as e:
        frappe.log_error(f"API process_image error: {str(e)}")
        return {"type": "error", "message": f"Image processing error: {str(e)[:200]}"}

@frappe.whitelist()
def get_doctypes_list(category=None):
    """Get list of available doctypes"""
    try:
        return discover_doctypes(category=category)
    except Exception as e:
        return {"type": "error", "message": str(e)}

@frappe.whitelist()
def get_doctype_schema(doctype):
    """Get schema for creating a doctype"""
    try:
        return get_doctype_info(doctype=doctype)
    except Exception as e:
        return {"type": "error", "message": str(e)}

@frappe.whitelist()
def create_record(doctype, data):
    """Direct API to create any record"""
    try:
        if isinstance(data, str):
            data = json.loads(data)

        from my_ai_assistant.services.document_service import create_document
        result = create_document(doctype, data)
        return result
    except Exception as e:
        frappe.log_error(f"API create_record error: {str(e)}")
        return {"type": "error", "message": f"Create error: {str(e)[:200]}"}

"""
Entity Extraction Service
Smart entity detection with fuzzy matching and similarity scoring
"""

import frappe
from difflib import SequenceMatcher

def similarity(a, b):
    """Calculate string similarity ratio"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def extract_entities_from_question(question, entity_types=None):
    """
    Extract entity mentions from user question using fuzzy matching
    Returns dict with detected entities and their ERPNext IDs
    """
    q_lower = question.lower()
    result = {}

    types_to_check = entity_types or ["Customer", "Supplier", "Item", "Employee", "Lead"]

    for entity_type in types_to_check:
        entity_id = find_entity_mention(question, entity_type)
        if entity_id:
            result[entity_type.lower()] = entity_id
            # Also get display name
            result[f"{entity_type.lower()}_display"] = get_display_name(entity_type, entity_id)

    return result

def find_entity_mention(question, doctype):
    """
    Find if a doctype name is mentioned in the question
    Uses fuzzy matching with threshold
    """
    try:
        # Get all entity names
        entities = get_all_entity_names(doctype, limit=2000)

        best_match = None
        best_score = 0.65  # Minimum threshold

        for entity in entities:
            name = entity.get("name", "").strip()
            display = entity.get("display", name).strip()

            # Skip empty names
            if not name or len(name) < 2:
                continue

            # Check exact match first
            if name.lower() in question.lower():
                return name
            if display.lower() in question.lower():
                return name

            # Check similarity for display name
            if display and len(display) > 2:
                score = similarity(display, question)
                if score > best_score:
                    best_score = score
                    best_match = name

            # Check similarity for actual name
            if len(name) > 2:
                score = similarity(name, question)
                if score > best_score:
                    best_score = score
                    best_match = name

        return best_match
    except Exception as e:
        frappe.log_error(f"Find entity mention error for {doctype}: {str(e)}")
        return None

def get_all_entity_names(doctype, limit=2000):
    """Get all names for a doctype with display names"""
    try:
        # Map doctype to its display field
        display_field_map = {
            "Customer": "customer_name",
            "Supplier": "supplier_name",
            "Item": "item_name",
            "Employee": "employee_name",
            "Lead": "lead_name"
        }

        display_field = display_field_map.get(doctype, "name")

        fields = ["name", f"{display_field} as display"]
        return frappe.get_all(doctype, fields=fields, limit=limit, ignore_permissions=True)
    except Exception as e:
        return []

def get_display_name(doctype, name):
    """Get display name for an entity"""
    try:
        display_field_map = {
            "Customer": "customer_name",
            "Supplier": "supplier_name",
            "Item": "item_name",
            "Employee": "employee_name",
            "Lead": "lead_name"
        }

        display_field = display_field_map.get(doctype)
        if display_field:
            display = frappe.db.get_value(doctype, name, display_field)
            return display or name
        return name
    except:
        return name

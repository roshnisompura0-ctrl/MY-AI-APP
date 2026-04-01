from . import __version__ as app_version

app_name = "my_ai_assistant"
app_title = "My AI Assistant"
app_publisher = "SkyERP"
app_description = "AI Assistant for ERPNext with clean architecture, global search, and document scanning"
app_email = "ai@skyerp.com"
app_license = "mit"

# Include CSS/JS assets
app_include_css = "/assets/my_ai_assistant/css/ai_chat_widget.css"
app_include_js = "/assets/my_ai_assistant/js/ai_chat_widget.js"

# Page fixtures
fixtures = [
    {
        "doctype": "Page",
        "filters": [["name", "in", ["ai-chat"]]]
    }
]

# Export Python functions
global_search_doctypes = {
    "Sales Invoice": ["name", "customer_name", "grand_total"],
    "Purchase Invoice": ["name", "supplier_name", "grand_total"],
    "Sales Order": ["name", "customer", "grand_total"],
    "Purchase Order": ["name", "supplier", "grand_total"],
    "Customer": ["name", "customer_name", "gstin"],
    "Supplier": ["name", "supplier_name", "gstin"],
    "Item": ["name", "item_name", "item_group"],
    "Employee": ["name", "employee_name", "department"],
}

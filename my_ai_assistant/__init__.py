"""
My AI Assistant - Clean Architecture v2.0
Global ERPNext AI Assistant with dynamic doctype support.
"""

__version__ = "2.0.0"

# Core doctype categories for dynamic discovery
MASTER_DOCTYPES = [
    "Customer", "Supplier", "Item", "Employee", "Lead",
    "Contact", "Address", "Company", "Warehouse",
    "Project", "Task", "Asset", "Branch"
]

TRANSACTION_DOCTYPES = [
    "Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
    "Quotation", "Delivery Note", "Purchase Receipt",
    "Payment Entry", "Journal Entry", "Expense Claim",
    "Stock Entry", "Material Request"
]

HR_DOCTYPES = [
    "Attendance", "Leave Application", "Salary Slip",
    "Employee Checkin", "Shift Assignment"
]

ENTITY_DOCTYPES = ["Customer", "Supplier", "Item", "Employee", "Lead"]

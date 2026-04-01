import frappe
import requests
import json

# Hardcoded Vertex API Key
VERTEX_API_KEY = "Your API Key"

@frappe.whitelist()
def get_ai_response(prompt, user=None):

    system = """You are an intelligent ERPNext assistant. You help users create, find, and manage records.

When a user wants to CREATE a record, respond with ONLY valid JSON like this:
{
  "action": "create",
  "doctype": "Customer",
  "data": {
    "customer_name": "Harsh Ahir",
    "customer_type": "Individual",
    "customer_group": "All Customer Groups",
    "territory": "All Territories"
  },
  "message": "Customer Harsh Ahir created successfully!"
}

When a user wants to SEARCH or LIST records:
{
  "action": "search",
  "doctype": "Customer",
  "filters": {},
  "message": "Here are the customers."
}

When it is a normal question:
{
  "action": "none",
  "message": "Your answer here."
}

IMPORTANT RULES:
- For Customer: always use customer_name, customer_type=Individual, customer_group=All Customer Groups, territory=All Territories
- For Supplier: use supplier_name, supplier_type=Individual, supplier_group=All Supplier Groups
- For Item: use item_name, item_code (same as item_name), item_group=All Item Groups, stock_uom=Nos
- For Employee: use first_name, last_name, company, department, designation, gender=Male
- For Lead: use lead_name, email_id, mobile_no
- NEVER add qty, rate or sales order fields to Customer or Supplier
- Always return ONLY valid JSON. No text outside JSON."""

    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + VERTEX_API_KEY,
            headers={"content-type": "application/json"},
            json={
                "contents": [{"parts": [{"text": system + "\n\nUser request: " + prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 200,
                    "temperature": 0.1
                }
            },
            timeout=180
        )

        resp_json = response.json()
        if "error" in resp_json:
            return {
                "type": "error",
                "message": "API error: " + str(resp_json.get("error", {}).get("message", "Unknown"))
            }
        ai_reply = resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        frappe.log_error(f"AI API Error: {str(e)}")
        return {
            "type": "error",
            "message": "API request failed. Please check your API key configuration."
        }

    # Remove markdown code blocks if present
    if "```" in ai_reply:
        ai_reply = ai_reply.split("```")[1]
        if ai_reply.startswith("json"):
            ai_reply = ai_reply[4:]
    ai_reply = ai_reply.strip()

    try:
        parsed = json.loads(ai_reply)
        action = parsed.get("action", "none")

        if action == "create":
            doctype = parsed.get("doctype")
            data = parsed.get("data", {})
            data["doctype"] = doctype

            # Check duplicate
            first_key = list(data.keys())[1]  # skip 'doctype'
            existing = frappe.db.exists(doctype, {first_key: data[first_key]})
            if existing:
                return {
                    "type": "info",
                    "message": f"⚠️ {doctype} <b>{data[first_key]}</b> already exists.",
                    "link": f"/app/{doctype.lower().replace(' ', '-')}/{existing}"
                }

            doc = frappe.get_doc(data)
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

            doctype_url = doctype.lower().replace(' ', '-')
            return {
                "type": "success",
                "message": f"✅ {doctype} <b>{doc.name}</b> created successfully!",
                "doctype": doctype,
                "name": doc.name,
                "link": f"/app/{doctype_url}/{doc.name}"
            }

        elif action == "search":
            doctype = parsed.get("doctype")
            filters = parsed.get("filters", {})
            results = frappe.get_list(
                doctype,
                filters=filters,
                fields=["name"],
                limit=10
            )
            if results:
                names = [r["name"] for r in results]
                return {
                    "type": "list",
                    "message": f"Found <b>{len(results)}</b> {doctype}(s):",
                    "doctype": doctype,
                    "results": names
                }
            else:
                return {
                    "type": "info",
                    "message": f"No {doctype} records found."
                }

        else:
            return {
                "type": "text",
                "message": parsed.get("message", ai_reply)
            }

    except Exception as e:
        frappe.log_error(f"AI Chatbot Error: {str(e)}\nResponse: {ai_reply}")
        return {
            "type": "text",
            "message": "Sorry, I could not process that. Please try again with more details."
        }

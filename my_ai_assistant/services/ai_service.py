"""
AI Orchestration Service
Handles all AI model interactions with global search capability
"""

import frappe
import requests
import json
import re
from my_ai_assistant.config.settings import get_api_key, get_ai_model, get_max_tokens, get_temperature, get_request_timeout

def call_gemini_text(prompt, system_prompt=None):
    """Call Gemini text model for general queries"""
    api_key = get_api_key()
    if not api_key:
        return {"error": "API key not configured"}

    try:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{get_ai_model()}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": get_max_tokens(),
                    "temperature": get_temperature()
                }
            },
            timeout=get_request_timeout()
        )

        result = response.json()

        if "error" in result:
            return {"error": result["error"].get("message", "API error")}

        return result["candidates"][0]["content"]["parts"][0]["text"]

    except requests.exceptions.Timeout:
        return {"error": "Request timed out"}
    except Exception as e:
        frappe.log_error(f"Gemini text error: {str(e)}")
        return {"error": str(e)}

def call_gemini_vision(prompt, image_data):
    """Call Gemini vision model for image analysis"""
    api_key = get_api_key()
    if not api_key:
        return {"error": "API key not configured"}

    try:
        # Handle base64 image data
        if isinstance(image_data, str):
            if "base64," in image_data:
                image_data = image_data.split("base64,")[1]
            elif image_data.startswith("data:image"):
                image_data = image_data.split(",")[1]

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_data
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "maxOutputTokens": get_max_tokens(),
                    "temperature": 0.1
                }
            },
            timeout=get_request_timeout() + 30  # Longer for vision
        )

        result = response.json()

        if "error" in result:
            return {"error": result["error"].get("message", "Vision API error")}

        text_response = result["candidates"][0]["content"]["parts"][0]["text"]

        # Try to extract JSON
        json_match = re.search(r'\{.*?\}', text_response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass

        return text_response

    except Exception as e:
        frappe.log_error(f"Gemini vision error: {str(e)}")
        return {"error": str(e)}

def generate_ai_response(question, live_data, conversation_history=""):
    """
    Main AI response generator with global search capability
    Handles ANY question by analyzing context and available data
    """
    api_key = get_api_key()
    if not api_key:
        return {
            "type": "error",
            "message": "API key not configured. Please set vertex_api_key in site_config.json"
        }

    # Build comprehensive system prompt
    system_prompt = build_system_prompt()

    # Prepare data context
    data_context = format_live_data(live_data)

    # Build user message
    user_message = f"""
AVAILABLE LIVE DATA FROM SKYERP:
{data_context}

USER QUESTION: {question}

IMPORTANT INSTRUCTIONS:
1. Answer based on the LIVE data provided above
2. Use exact numbers and facts from the data
3. If creating a record, use the exact JSON format specified
4. Format currency with ₹ symbol
5. Be concise but comprehensive
6. If data is not available, say so clearly

Respond with ONLY valid JSON matching the format rules above."""

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{get_ai_model()}:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": system_prompt + "\n\n" + user_message}]}],
                "generationConfig": {
                    "maxOutputTokens": get_max_tokens(),
                    "temperature": get_temperature()
                }
            },
            timeout=get_request_timeout()
        )

        result = response.json()

        if "error" in result:
            return {
                "type": "error",
                "message": f"AI API Error: {result['error'].get('message', 'Unknown error')}"
            }

        ai_reply = result["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Extract JSON from markdown code blocks
        if "```" in ai_reply:
            for part in ai_reply.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    try:
                        return json.loads(part)
                    except:
                        continue

        # Try direct JSON parse
        if ai_reply.startswith("{"):
            try:
                return json.loads(ai_reply)
            except:
                pass

        # Fallback: return as text
        return {"type": "text", "message": ai_reply}

    except requests.exceptions.ConnectionError:
        return {"type": "error", "message": "Cannot connect to AI service. Check internet connection."}
    except Exception as e:
        frappe.log_error(f"AI generation error: {str(e)}")
        return {"type": "error", "message": f"Error generating response: {str(e)[:150]}"}

def build_system_prompt():
    """Build comprehensive system prompt for global question handling"""
    return """You are an intelligent SkyERP AI Assistant with access to LIVE business data.

RESPONSE FORMAT - Return ONLY valid JSON:

For answers and information:
{"type": "text", "message": "Your HTML-formatted answer here"}

For creating new records:
{"type": "create", "doctype": "Customer", "data": {"field": "value"}}

For listing records:
{"type": "list", "message": "Header", "items": ["name1", "name2"], "doctype": "Customer"}

For errors or clarifications:
{"type": "text", "message": "Explanation of what information is needed"}

FORMATTING RULES:
- Use HTML tags (<br>, <b>, etc.) for formatting
- Use ₹ symbol for Indian Rupees
- Format large numbers with commas (e.g., ₹1,25,000)
- Use bullet points with • symbol for lists
- Keep responses concise but informative

ENTITY DATA PRIORITY:
- When entity_customer_* data exists → use it for customer questions
- When entity_supplier_* data exists → use it for supplier questions
- When entity_item_* data exists → use it for item questions
- When entity_employee_* data exists → use it for employee questions

BUSINESS DATA INSIGHTS:
- Calculate totals, averages, trends from raw data
- Compare this month vs previous periods when data available
- Identify overdue items, low stock, pending orders
- Highlight key metrics that answer the user's question

CREATE RECORD DEFAULTS:
Customer: customer_name, customer_type=Individual, customer_group=All Customer Groups, territory=All Territories
Supplier: supplier_name, supplier_type=Company, supplier_group=All Supplier Groups
Item: item_name, item_code=same, item_group=All Item Groups, stock_uom=Nos
Employee: first_name, last_name, company, gender=Male, status=Active

DO NOT:
- Add fields that don't exist in the doctype
- Guess or fabricate numbers not in the data
- Return text outside the JSON structure
- Use markdown code blocks in the response"""

def format_live_data(live_data):
    """Format live data for AI consumption with size limits"""
    if not live_data:
        return "No live data available for this query."

    # Convert to JSON string
    data_str = json.dumps(live_data, indent=2, default=str)

    # Truncate if too large (token limit consideration)
    max_length = 14000
    if len(data_str) > max_length:
        # Keep essential data, truncate arrays
        trimmed = {}
        for key, value in live_data.items():
            if isinstance(value, list) and len(value) > 50:
                trimmed[key] = value[:50]
                trimmed[f"{key}_total_count"] = len(value)
            else:
                trimmed[key] = value

        data_str = json.dumps(trimmed, indent=2, default=str)[:max_length]
        data_str += "\n... (truncated for size)"

    return data_str

def parse_ai_response(ai_reply):
    """Parse and validate AI response"""
    try:
        # Remove markdown code blocks
        if "```" in ai_reply:
            for part in ai_reply.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    ai_reply = part
                    break

        parsed = json.loads(ai_reply.strip())

        # Validate required fields
        if "type" not in parsed:
            parsed["type"] = "text"

        return parsed

    except json.JSONDecodeError:
        # Not valid JSON - wrap as text response
        return {"type": "text", "message": ai_reply}

    except Exception as e:
        frappe.log_error(f"Parse AI response error: {str(e)}")
        return {"type": "error", "message": "Could not parse AI response"}

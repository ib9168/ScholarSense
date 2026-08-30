from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from pymongo import MongoClient
from datetime import datetime, timezone
from openai import OpenAI
import os
import time
import httpx
import json
import certifi


app = FastAPI(title="ScholarSense API")
client = MongoClient(
    os.environ["MONGODB_URI"],
    tlsCAFile=certifi.where(),
    tls=True,
    tlsAllowInvalidCertificates=False,
    serverSelectionTimeoutMS=30000,
)
db = client["scholarsense"]
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
SERPAPI_URL = "https://serpapi.com/search"

openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
)

def _parse_price(raw) -> float | None:
    try:
        return float(str(raw).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_delivery_cost(delivery: str) -> float:
    import re
    match = re.search(r"\$\s*([\d]+\.[\d]{1,2}|[\d]+)", delivery)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return 0.0


def _normalize_date(date_str: str) -> str:
    """Accept YYYY-MM-DD or natural language like 'June 10, 2026' / '10th June 2026'."""
    import re
    clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str).strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%d %B %Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(clean, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


# Features to handle budgeting, expense logging, price searching, and watchlist management.

class BudgetCategory(BaseModel):
    name: str
    budget: float

class SetBudgetRequest(BaseModel):
    userId: str = "user_001"
    startDate: str
    endDate: str
    categories: list[BudgetCategory]

class LogExpenseRequest(BaseModel):
    userId: str = "user_001"
    category: str
    item: str
    amount: float
    store: str
    purchaseType: str = "online"

class WatchlistRequest(BaseModel):
    userId: str = "user_001"
    product: str
    alertThresholdPrice: float


# API call to set or update a student's budget with spending categories and a date timeline.

@app.post("/set_budget")
def set_budget(req: SetBudgetRequest):
    start_date = _normalize_date(req.startDate)
    end_date = _normalize_date(req.endDate)
    total = sum(c.budget for c in req.categories)
    existing = db.budgets.find_one({"userId": req.userId}) or {}
    existing_cats = {c["name"]: c.get("spent", 0.0) for c in existing.get("categories", [])}
    categories = [
        {"name": c.name, "budget": c.budget, "spent": existing_cats.get(c.name, 0.0)}
        for c in req.categories
    ]
    total_spent = sum(c["spent"] for c in categories)
    doc = {
        "userId": req.userId,
        "timeline": {"start": start_date, "end": end_date},
        "categories": categories,
        "totalBudget": total,
        "totalSpent": total_spent,
        "createdAt": existing.get("createdAt", datetime.now(timezone.utc).isoformat()),
    }
    db.budgets.replace_one({"userId": req.userId}, doc, upsert=True)
    return {"message": f"Budget set. Total: ${total:.2f}", "categories": categories}


# Parses the user input and returns the current budget, remaining balance per category, spending percentages, and proactive overspend warnings.

@app.get("/read_budget/{userId}")
def read_budget(userId: str):
    budget = db.budgets.find_one({"userId": userId}, {"_id": 0})
    if not budget:
        return {"message": "No budget set yet. Ask the user to set up their budget first.", "categories": [], "warnings": [], "elapsedPct": 0}
    start = datetime.fromisoformat(budget["timeline"]["start"]).replace(tzinfo=None)
    end = datetime.fromisoformat(budget["timeline"]["end"]).replace(tzinfo=None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    total_days = (end - start).days or 1
    elapsed_days = max(0, (now - start).days)
    elapsed_pct = round((elapsed_days / total_days) * 100, 1)
    warnings = []
    for cat in budget["categories"]:
        cat["remaining"] = round(cat["budget"] - cat["spent"], 2)
        cat["spentPct"] = round((cat["spent"] / cat["budget"]) * 100, 1) if cat["budget"] else 0
        if cat["spentPct"] - elapsed_pct > 10:
            warnings.append(
                f"Warning: You've spent {cat['spentPct']}% of {cat['name']} "
                f"with only {elapsed_pct}% of your timeline elapsed. "
                f"At this rate you may run short before your end date."
            )
    budget["elapsedPct"] = elapsed_pct
    budget["warnings"] = warnings
    return budget


# Tracks expenses and deducts them from the appropriate budget category. If the expense exceeds the remaining budget, it returns a warning instead of logging the expense.

@app.post("/log_expense")
def log_expense(req: LogExpenseRequest):
    budget = db.budgets.find_one({"userId": req.userId})
    if not budget:
        return {"error": "No budget found. Ask the user to set up their budget first."}
    cat = next((c for c in budget["categories"] if c["name"] == req.category), None)
    if not cat:
        return {"error": f"Category '{req.category}' not found in budget. Available categories: {[c['name'] for c in budget['categories']]}"}
    if cat["spent"] + req.amount > cat["budget"]:
        return {"error": f"Purchase of ${req.amount:.2f} exceeds remaining budget of ${cat['budget'] - cat['spent']:.2f} in {req.category}. Ask the user if they want to proceed anyway."}
    db.expenses.insert_one({
        "userId": req.userId,
        "category": req.category,
        "item": req.item,
        "amount": req.amount,
        "store": req.store,
        "purchaseType": req.purchaseType,
        "date": datetime.now(timezone.utc).isoformat(),
    })
    db.budgets.update_one(
        {"userId": req.userId, "categories.name": req.category},
        {"$inc": {"categories.$.spent": req.amount, "totalSpent": req.amount}},
    )
    remaining = round(cat["budget"] - cat["spent"] - req.amount, 2)
    return {"message": f"Logged ${req.amount:.2f} for {req.item}. ${remaining:.2f} remaining in {req.category}."}


# Requests to add a product to the price watchlist. The agent will alert the student when the price drops to or below the threshold.

@app.post("/add_to_watchlist")
def add_to_watchlist(req: WatchlistRequest):
    db.watchlist.insert_one({
        "userId": req.userId,
        "product": req.product,
        "alertThresholdPrice": req.alertThresholdPrice,
        "lastCheckedPrice": None,
        "lastCheckedAt": None,
        "active": True,
    })
    return {"message": f"Watching '{req.product}' — alert when price drops to ${req.alertThresholdPrice:.2f}."}


# Retrieves the current watchlist for a user, including product names, alert thresholds, and last checked prices.

@app.get("/get_watchlist/{userId}")
def get_watchlist(userId: str):
    items = list(db.watchlist.find({"userId": userId, "active": True}, {"_id": 0}))
    return {"watchlist": items}


# checks watchlist (calls SerpAPI per item) 

@app.get("/check_watchlist/{userId}")
def check_watchlist(userId: str):
    items = list(db.watchlist.find({"userId": userId, "active": True}))
    if not items:
        return {"alerts": [], "message": "No active watchlist items."}

    alerts = []
    for item in items:
        try:
            resp = httpx.get(SERPAPI_URL, params={
                "engine": "google_shopping",
                "q": item["product"],
                "api_key": SERPAPI_KEY,
            }, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("shopping_results", [])
        except Exception as e:
            alerts.append({"product": item["product"], "error": f"Price check failed: {str(e)}"})
            continue

        if not results:
            continue

        best_price = None
        best_store = None
        for r in results[:5]:
            price = _parse_price(r.get("price", ""))
            if price is not None and (best_price is None or price < best_price):
                best_price = price
                best_store = r.get("source", "Unknown")

        now_iso = datetime.now(timezone.utc).isoformat()
        if best_price is not None:
            db.watchlist.update_one(
                {"_id": item["_id"]},
                {"$set": {"lastCheckedPrice": best_price, "lastCheckedAt": now_iso}},
            )
            if best_price <= item["alertThresholdPrice"]:
                alerts.append({
                    "product": item["product"],
                    "currentPrice": best_price,
                    "threshold": item["alertThresholdPrice"],
                    "store": best_store,
                    "message": (
                        f"Price drop alert: '{item['product']}' is now ${best_price:.2f} "
                        f"at {best_store} — below your ${item['alertThresholdPrice']:.2f} threshold!"
                    ),
                })

    return {
        "alerts": alerts,
        "checked": len(items),
        "message": f"Checked {len(items)} item(s). {len(alerts)} alert(s) triggered.",
    }


# Looks for product pricesbased on the location and returns the top results ranked by total cost including delivery. Use a descriptive query.

@app.get("/price_search")
def price_search(q: str, zipCode: str = ""):
    params = {"engine": "google_shopping", "q": q, "api_key": SERPAPI_KEY}
    if zipCode:
        params["location"] = zipCode
    try:
        resp = httpx.get(SERPAPI_URL, params=params, timeout=10)
        results = resp.json().get("shopping_results", [])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SerpAPI error: {str(e)}")

    if not results:
        return {"results": [], "message": "No results found."}

    top = []
    for r in results[:5]:
        price = _parse_price(r.get("price", ""))
        if price is None:
            continue
        delivery = r.get("delivery", "")
        delivery_cost = 0.0 if not delivery or "free" in delivery.lower() else _parse_delivery_cost(delivery)
        top.append({
            "title": r.get("title", ""),
            "price": price,
            "deliveryCost": delivery_cost,
            "totalCost": round(price + delivery_cost, 2),
            "store": r.get("source", ""),
            "delivery": delivery,
            "link": r.get("product_link", ""),
        })

    if not top:
        return {"results": [], "message": "No results with parseable prices found."}
    top.sort(key=lambda x: x["totalCost"])
    return {"results": top, "recommendation": top[0]}


# MCP  endpoint

MCP_TOOLS = [
    {
        "name": "set_budget",
        "description": "Set or update a student's budget with spending categories and a date timeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userId": {"type": "string"},
                "startDate": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                "endDate": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "budget": {"type": "number"}
                        },
                        "required": ["name", "budget"]
                    }
                }
            },
            "required": ["userId", "startDate", "endDate", "categories"]
        }
    },
    {
        "name": "read_budget",
        "description": "Read a student's current budget — returns remaining balance per category, spending percentages, and proactive overspend warnings.",
        "inputSchema": {
            "type": "object",
            "properties": {"userId": {"type": "string"}},
            "required": ["userId"]
        }
    },
    {
        "name": "log_expense",
        "description": "Log a confirmed purchase and deduct it from the appropriate budget category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userId": {"type": "string"},
                "category": {"type": "string"},
                "item": {"type": "string"},
                "amount": {"type": "number"},
                "store": {"type": "string"},
                "purchaseType": {"type": "string", "enum": ["online", "in-store"]}
            },
            "required": ["userId", "category", "item", "amount", "store", "purchaseType"]
        }
    },
    {
        "name": "price_search",
        "description": "Search live Google Shopping prices for any product. Returns top results ranked by total cost including delivery. Use a descriptive query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Full descriptive product search query"},
                "zipCode": {"type": "string", "description": "User zip code for local store results"}
            },
            "required": ["q"]
        }
    },
    {
        "name": "add_to_watchlist",
        "description": "Add a product to the price watchlist. The agent will alert the student when the price drops to or below the threshold.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "userId": {"type": "string"},
                "product": {"type": "string"},
                "alertThresholdPrice": {"type": "number"}
            },
            "required": ["userId", "product", "alertThresholdPrice"]
        }
    },
    {
        "name": "check_watchlist",
        "description": "Check all active watchlist items against live prices. Returns alerts for any item at or below its threshold price.",
        "inputSchema": {
            "type": "object",
            "properties": {"userId": {"type": "string"}},
            "required": ["userId"]
        }
    }
]


def _call_tool(name: str, args: dict):
    if name == "set_budget":
        return set_budget(SetBudgetRequest(**args))
    elif name == "read_budget":
        return read_budget(args["userId"])
    elif name == "log_expense":
        return log_expense(LogExpenseRequest(**args))
    elif name == "price_search":
        return price_search(args["q"], args.get("zipCode", ""))
    elif name == "add_to_watchlist":
        return add_to_watchlist(WatchlistRequest(**args))
    elif name == "check_watchlist":
        return check_watchlist(args["userId"])
    else:
        raise ValueError(f"Unknown tool: {name}")


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "scholarsense-mcp", "version": "1.0.0"}
            }
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

    if method == "tools/call":
        params = body.get("params") or {}
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        if not tool_name:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Missing tool name"}}
        try:
            result = _call_tool(tool_name, args)
            text = json.dumps(result)
        except Exception as e:
            text = json.dumps({"error": str(e), "tool": tool_name, "received_args": args})
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": text}]}
        }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}




OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

CHAT_TOOLS = [
    {"type": "function", "function": {"name": "set_budget", "description": "Set or update a student's budget with spending categories and a date timeline.", "parameters": {"type": "object", "properties": {"userId": {"type": "string"}, "startDate": {"type": "string"}, "endDate": {"type": "string"}, "categories": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "budget": {"type": "number"}}, "required": ["name", "budget"]}}}, "required": ["userId", "startDate", "endDate", "categories"]}}},
    {"type": "function", "function": {"name": "read_budget", "description": "Read a student's current budget — returns remaining balance per category, spending percentages, and overspend warnings.", "parameters": {"type": "object", "properties": {"userId": {"type": "string"}}, "required": ["userId"]}}},
    {"type": "function", "function": {"name": "log_expense", "description": "Log a confirmed purchase and deduct it from the appropriate budget category.", "parameters": {"type": "object", "properties": {"userId": {"type": "string"}, "category": {"type": "string"}, "item": {"type": "string"}, "amount": {"type": "number"}, "store": {"type": "string"}, "purchaseType": {"type": "string", "enum": ["online", "in-store"]}}, "required": ["userId", "category", "item", "amount", "store", "purchaseType"]}}},
    {"type": "function", "function": {"name": "price_search", "description": "Search live Google Shopping prices for a product. Returns top results ranked by total cost including delivery.", "parameters": {"type": "object", "properties": {"q": {"type": "string"}, "zipCode": {"type": "string"}}, "required": ["q"]}}},
    {"type": "function", "function": {"name": "add_to_watchlist", "description": "Add a product to the price watchlist. Alerts when price drops to or below the threshold.", "parameters": {"type": "object", "properties": {"userId": {"type": "string"}, "product": {"type": "string"}, "alertThresholdPrice": {"type": "number"}}, "required": ["userId", "product", "alertThresholdPrice"]}}},
    {"type": "function", "function": {"name": "check_watchlist", "description": "Check all active watchlist items against live prices. Returns alerts for items at or below threshold.", "parameters": {"type": "object", "properties": {"userId": {"type": "string"}}, "required": ["userId"]}}},
]

SYSTEM_PROMPT = """You are ScholarSense, an AI budget assistant for college students on tight fixed budgets.
At the start of every conversation, silently call read_budget then check_watchlist for the user.
If read_budget returns warnings, open with them. If check_watchlist returns alerts, list them after.
Always use the userId provided to you. Infer budget categories from items:
food/drinks/produce → groceries | notebooks/pens/textbooks → school supplies | headphones/cables/chargers → electronics.
Only call log_expense when the user explicitly confirms a purchase. Be concise. Use dollar amounts with two decimal places."""


class ChatRequest(BaseModel):
    messages: list[dict]
    userId: str = "user_001"


@app.post("/chat")
def chat(req: ChatRequest):
    system = SYSTEM_PROMPT + (
        f"\nThe current user's userId is: {req.userId}. "
        "Use this exact userId for every tool call — never ask the user for it."
    )
    messages = [{"role": "system", "content": system}] + req.messages# keeping it temporarily before clerk authentication 
    for _ in range(10):
        response = None
        last_err = None
        for attempt in range(3):
            try:
                response = openrouter_client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=messages,
                    tools=CHAT_TOOLS,
                    tool_choice="auto",
                )
                if getattr(response, "choices", None):
                    break
                detail = (getattr(response, "model_extra", {}) or {}).get("error")
                last_err = f"Empty response (no choices). Detail: {detail}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)}"
            response = None
            if attempt < 2:
                time.sleep(2)
        if response is None:
            return {"error": f"LLM call failed after 3 attempts: {last_err}", "model": OPENROUTER_MODEL}
        choice = response.choices[0]
        if choice.finish_reason == "tool_calls":
            assistant_msg = choice.message
            messages.append({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in assistant_msg.tool_calls
                ],
            })
            for tc in assistant_msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                    args["userId"] = req.userId
                    result = _call_tool(tc.function.name, args)
                except Exception as e:
                    result = {"error": str(e)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
        else:
            return {"reply": choice.message.content or ""}
    return {"reply": "I wasn't able to complete that request — too many tool calls. Please try rephrasing."}



@app.get("/health")
def health():
    return {"status": "ok"}

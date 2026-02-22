"""
Jumbo API – FastAPI web service & REST endpoints.
"""
import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from jumbo_client import JumboClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger(__name__)

# ── FastAPI application ───────────────────────────────────────────────

DESCRIPTION = """
## Jumbo.com Basket & Product API

Manage your Jumbo grocery basket, look up products by SKU or barcode,
view your shopping lists, and monitor session state – all from a single REST interface.

### Features
- **Authentication** – automated Selenium login, cookie management
- **Basket** – view, add, remove & update products
- **Lists** – view all your shopping lists (lijstjes)
- **Product lookup** – comprehensive product details with nutrition info, allergens, images, pricing, and more
- **Orders** – view order history and detailed order information
- **Receipts** – store receipt details with parsed product items, VAT, and loyalty points
- **History** – recent command log

### Product Details Include
- Full product information (brand, categories, descriptions)
- Nutritional data & allergen information
- Multiple product images (thumbnails & high-res)
- Pricing with promotions & volume discounts
- Availability & stock information
- Manufacturer details & origin
- Storage, recycling, and preparation instructions
"""

tags_metadata = [
    {"name": "Auth", "description": "Login & session status"},
    {"name": "Basket", "description": "View and modify your Jumbo basket"},
    {"name": "Lists", "description": "View shopping lists (lijstjes)"},
    {"name": "Orders", "description": "Order history and receipt details"},
    {"name": "Products", "description": "Comprehensive product search by SKU or barcode with full details"},
    {"name": "Settings", "description": "User preferences for product matching"},
    {"name": "System", "description": "Health check & command history"},
]

app = FastAPI(
    title="Jumbo API",
    description=DESCRIPTION,
    version="2.6.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_tags=tags_metadata,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

client = JumboClient()
command_history: List[dict] = []

# ── Bot Management ────────────────────────────────────────────────────
@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return Response(
        content="""User-agent: *
Disallow: /feed
Disallow: /rss
Disallow: /blog
Disallow: /articles
Disallow: *.xml
Disallow: *.rss

Allow: /docs
Allow: /api""",
        media_type="text/plain"
    )

# ── Startup Event ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Auto-login on startup if credentials are available."""
    if client.username and client.password:
        log.info("🔐 Credentials detected. Attempting auto-login on startup...")
        result = await client.login(client.username, client.password, save_credentials=False)
        if result.get("success"):
            log.info("✅ Auto-login successful!")
        else:
            log.warning("⚠️ Auto-login failed: %s", result.get("message"))
    elif not client.is_authenticated():
        log.info("ℹ️ No saved credentials or cookies. Login required via /api/login")
    else:
        log.info("✅ Loaded session cookies from file")

# ── Models ────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., example="user@example.com")
    password: str = Field(..., example="password123")

class AddProductRequest(BaseModel):
    sku: str = Field(..., example="67649PAK")
    quantity: float = Field(1, ge=0.1, example=1)

class RemoveProductRequest(BaseModel):
    line_id: Optional[str] = Field(None, description="Basket line ID")
    sku: Optional[str] = Field(None, description="Product SKU (used to resolve line ID)")

class UpdateQuantityRequest(BaseModel):
    quantity: float = Field(..., ge=0.1, example=2, description="New quantity for the basket item")

class BarcodeRequest(BaseModel):
    barcode: str = Field(..., example="8718452044801")

# ── Helpers ───────────────────────────────────────────────────────────

def _log(cmd: str, status: str, details: Optional[dict] = None):
    command_history.append(
        {"timestamp": datetime.now().isoformat(), "command": cmd, "status": status, "details": details}
    )
    if len(command_history) > 50:
        command_history.pop(0)

# ── Web dashboard ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ── Auth endpoints ────────────────────────────────────────────────────

@app.post("/api/login", tags=["Auth"], summary="Login to Jumbo.com")
async def login(body: LoginRequest):
    """Automate browser login via Selenium and capture session cookies."""
    try:
        result = await client.login(body.username, body.password)
        status = "success" if result.get("success") else "failed"
        _log("login", status, result)
        code = 200 if result.get("success") else 401
        return JSONResponse(content=result, status_code=code)
    except Exception as exc:
        _log("login", "error", {"error": str(exc)})
        raise HTTPException(500, detail=str(exc))


@app.get("/api/auth/status", tags=["Auth"], summary="Session status")
async def auth_status():
    """Return whether the client holds valid session cookies."""
    info = client.get_auth_info()
    return info

# ── Basket endpoints ──────────────────────────────────────────────────

@app.get("/api/basket", tags=["Basket"], summary="Get basket contents")
async def get_basket():
    """Fetch the active basket including product details and prices."""
    try:
        basket = await client.get_basket()
        _log("Get Basket", "success", {"item_count": len(basket.get("lines", []))})
        return basket
    except Exception as exc:
        _log("Get Basket", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))


@app.post("/api/basket/add", tags=["Basket"], summary="Add product to basket")
async def add_product(body: AddProductRequest):
    """Add a product by SKU (with optional quantity) to the basket."""
    try:
        result = await client.add_to_basket(body.sku, body.quantity)
        _log(f"Add {body.sku}", "success", {"sku": body.sku, "quantity": body.quantity})
        return result
    except Exception as exc:
        _log(f"Add {body.sku}", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))


@app.post("/api/basket/remove", tags=["Basket"], summary="Remove product from basket")
async def remove_product(body: RemoveProductRequest):
    """Remove a basket line by its ID or by product SKU."""
    try:
        result = await client.remove_from_basket(line_id=body.line_id, sku=body.sku)
        _log(f"Remove {body.sku or body.line_id}", "success")
        return result
    except Exception as exc:
        _log("Remove product", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))


@app.patch("/api/basket/items/{line_id}", tags=["Basket"], summary="Update basket item quantity")
async def update_basket_item_quantity(line_id: str, body: UpdateQuantityRequest):
    """Update the quantity of a specific basket item by its line ID."""
    try:
        result = await client.update_basket_item_quantity(line_id, body.quantity)
        _log(f"Update {line_id}", "success", {"line_id": line_id, "quantity": body.quantity})
        return result
    except Exception as exc:
        _log(f"Update {line_id}", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))

# ── Lists endpoints ───────────────────────────────────────────────────

@app.get("/api/lists", tags=["Lists"], summary="Get shopping lists")
async def get_lists():
    """Fetch all customer shopping lists (lijstjes) including favorites."""
    try:
        lists_data = await client.get_lists()
        _log("Get Lists", "success", {
            "customer_lists": len(lists_data.get("customerLists", {}).get("items", [])),
            "favourite_lists": len(lists_data.get("favouriteLists", {}).get("items", []))
        })
        return lists_data
    except Exception as exc:
        _log("Get Lists", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))

@app.get("/api/lists/{list_id}", tags=["Lists"], summary="Get specific list details")
async def get_list_by_id(list_id: str):
    """Fetch a specific shopping list with full product details."""
    try:
        list_data = await client.get_list_by_id(list_id)
        product_list = list_data.get("productListV2", {})
        _log(f"Get List {list_id}", "success", {
            "title": product_list.get("title"),
            "products": product_list.get("productsCount", 0)
        })
        return product_list
    except Exception as exc:
        _log(f"Get List {list_id}", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))

# ── Orders endpoints ──────────────────────────────────────────────────

@app.get("/api/orders", tags=["Orders"], summary="Get orders and receipts")
async def get_orders(limit: int = 10, page: int = 0, page_size: int = 10):
    """Fetch online orders and store receipts history."""
    try:
        data = await client.get_orders_and_receipts(
            orders_limit=limit,
            receipts_page=page,
            receipts_page_size=page_size
        )
        orders_count = len(data.get("onlineOrders", {}).get("orders", []))
        receipts_count = len(data.get("storeReceipts", {}).get("receipts", []))
        _log("Get Orders", "success", {
            "orders": orders_count,
            "receipts": receipts_count
        })
        return data
    except Exception as exc:
        _log("Get Orders", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))

@app.get("/api/orders/{order_id}", tags=["Orders"], summary="Get order details")
async def get_order_detail(order_id: int):
    """Fetch detailed information about a specific order including all products."""
    try:
        order = await client.get_order_details(order_id)
        if not order:
            raise HTTPException(404, detail=f"Order {order_id} not found")
        
        items_count = len(order.get("items", []))
        total = order.get("totals", {}).get("totalToPay", {}).get("amount", "0.00")
        
        _log(f"Get Order {order_id}", "success", {
            "items": items_count,
            "total": f"€{total}",
            "status": order.get("progress", {}).get("status", "UNKNOWN")
        })
        return order
    except HTTPException:
        raise
    except Exception as exc:
        _log(f"Get Order {order_id}", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))


@app.get("/api/receipts/{transaction_id:path}", tags=["Orders"], summary="Get store receipt detail")
async def get_receipt_detail(transaction_id: str):
    """Fetch a digital receipt with parsed product line items, totals, VAT breakdown, and loyalty points."""
    try:
        receipt = await client.get_receipt_detail(transaction_id)
        if not receipt:
            raise HTTPException(404, detail=f"Receipt {transaction_id} not found")

        items_count = len(receipt.get("items", []))
        total = receipt.get("total")
        _log(f"Get Receipt {transaction_id[:20]}…", "success", {
            "items": items_count,
            "total": f"€{total}" if total else "–",
        })
        return receipt
    except HTTPException:
        raise
    except Exception as exc:
        _log(f"Get Receipt", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))

# ── Product endpoints ─────────────────────────────────────────────────

@app.get("/api/products/search", tags=["Products"], summary="Search by SKU")
async def search_product(sku: str):
    """Look up a single product by its Jumbo SKU code."""
    try:
        product = await client.search_by_sku(sku)
        if not product:
            raise HTTPException(404, detail="Product not found")
        _log(f"SKU {sku}", "success", {"title": product.get("title")})
        return product
    except HTTPException:
        raise
    except Exception as exc:
        _log(f"SKU {sku}", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))


@app.post("/api/products/barcode", tags=["Products"], summary="Barcode lookup")
async def lookup_barcode(body: BarcodeRequest):
    """Resolve an EAN barcode to a Jumbo product (uses local cache)."""
    try:
        result = await client.barcode_lookup(body.barcode)
        if not result:
            raise HTTPException(404, detail="Barcode not found")
        _log(f"Barcode {body.barcode}", "success", {"sku": result.get("sku")})
        return result
    except HTTPException:
        raise
    except Exception as exc:
        _log(f"Barcode {body.barcode}", "error", {"error": str(exc)})
        raise HTTPException(400, detail=str(exc))

# ── Settings endpoints ────────────────────────────────────────────────

@app.get("/api/settings", tags=["Settings"], summary="Get settings")
async def get_settings():
    """Return current user settings for product matching."""
    settings = client.load_settings()
    # Add auth info (without passwords)
    settings["hasCredentials"] = bool(client.username and client.password)
    settings["username"] = client.username or ""
    return settings


class SettingsUpdate(BaseModel):
    productMatchingEnabled: Optional[bool] = None
    strictMatching: Optional[bool] = None
    confidenceThreshold: Optional[int] = Field(None, ge=0, le=100)
    useWeightMatching: Optional[bool] = None
    usePriceMatching: Optional[bool] = None
    useNameMatching: Optional[bool] = None
    useOpenFoodFactsFallback: Optional[bool] = None
    maxProductCandidates: Optional[int] = Field(None, ge=5, le=50)
    useQuantityInSearch: Optional[bool] = None
    useBrandInSearch: Optional[bool] = None
    useBarcodeCache: Optional[bool] = None
    priceMatchWeight: Optional[int] = Field(None, ge=0, le=100)
    weightMatchWeight: Optional[int] = Field(None, ge=0, le=100)
    nameMatchWeight: Optional[int] = Field(None, ge=0, le=100)
    eanScore10Plus: Optional[int] = Field(None, ge=0, le=100)
    eanScore8Plus: Optional[int] = Field(None, ge=0, le=100)
    eanScore6Plus: Optional[int] = Field(None, ge=0, le=100)
    eanScore4Plus: Optional[int] = Field(None, ge=0, le=100)


@app.put("/api/settings", tags=["Settings"], summary="Update settings")
async def update_settings(body: SettingsUpdate):
    """Update user settings for product matching behaviour."""
    current = client.load_settings()
    updates = body.model_dump(exclude_none=True)
    current.update(updates)
    saved = client.save_settings(current)
    _log("Update Settings", "success", updates)
    return saved


@app.post("/api/settings/clear-cache", tags=["Settings"], summary="Clear product match cache")
async def clear_match_cache():
    """Delete the receipt→product cache so all items get re-matched on next view."""
    client.clear_receipt_sku_cache()
    _log("Clear Match Cache", "success")
    return {"message": "Receipt product cache cleared. Items will be re-matched on next receipt view."}


class CredentialsUpdate(BaseModel):
    username: Optional[str] = Field(None, example="your@email.com")
    password: Optional[str] = Field(None, example="yourpassword")
    removeCredentials: Optional[bool] = False


@app.put("/api/settings/credentials", tags=["Settings"], summary="Update saved credentials")
async def update_credentials(body: CredentialsUpdate):
    """Update or remove saved login credentials."""
    if body.removeCredentials:
        client.username = None
        client.password = None
        client._save_credentials()
        _log("Remove Credentials", "success")
        return {"message": "Credentials removed", "hasCredentials": False}
    
    if body.username:
        client.username = body.username
    if body.password:
        client.password = body.password
    
    if client.username and client.password:
        client._save_credentials()
        _log("Update Credentials", "success", {"username": client.username})
        return {
            "message": "Credentials saved successfully",
            "hasCredentials": True,
            "username": client.username
        }
    
    raise HTTPException(400, detail="Username and password required")


# ── System endpoints ──────────────────────────────────────────────────

@app.get("/api/history", tags=["System"], summary="Command history")
async def get_history(limit: int = 20):
    """Return the last *limit* commands executed through the API."""
    return {"history": command_history[-limit:]}


@app.get("/api/health", tags=["System"], summary="Health check")
async def health_check():
    """Lightweight health probe used by Docker HEALTHCHECK."""
    return {
        "status": "healthy",
        "authenticated": client.is_authenticated(),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

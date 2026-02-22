"""Phase 3: Deep field probing + try to discover item/line fields on DigitalReceipt."""
import json
import httpx
import asyncio
import re

GRAPHQL_ENDPOINT = "https://www.jumbo.com/api/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/144.0.0.0 Safari/537.36",
    "apollographql-client-name": "JUMBO_WEB-orders",
    "apollographql-client-version": "master-v29.2.0-web",
    "x-source": "JUMBO_WEB-orders",
}

# Load cookies
try:
    with open("data/session-cookies.json") as f:
        cookies = json.load(f).get("cookies", {})
    print(f"Loaded {len(cookies)} cookies")
except:
    cookies = {}
    print("No cookies loaded")


async def probe(client, field_expr):
    """Try a field on DigitalReceipt and return the raw response."""
    q = f'''query Receipt($tid: String!) {{
      receipt(transactionId: $tid) {{
        transactionId
        {field_expr}
      }}
    }}'''
    body = {"query": q, "variables": {"tid": "test"}}
    resp = await client.post(GRAPHQL_ENDPOINT, json=body, headers=HEADERS, cookies=cookies)
    return resp.json()


async def try_field(client, field, silent_invalid=True):
    """Check a field and print result."""
    data = await probe(client, field)
    errors = data.get("errors", [])
    
    for e in errors:
        msg = e.get("message", "")
        if "Cannot query field" in msg:
            # Check for "Did you mean" suggestions
            suggestion = re.search(r'Did you mean "([^"]+)"', msg)
            if suggestion:
                print(f"  ✗ {field:40s} -> Did you mean: {suggestion.group(1)}")
                return "suggestion", suggestion.group(1)
            if not silent_invalid:
                print(f"  ✗ {field:40s} -> Invalid")
            return "invalid", None
        if "must have a selection of subfields" in msg:
            print(f"  ◉ {field:40s} -> OBJECT TYPE (needs subfields)")
            return "object", None
    
    if not errors or ("data" in data and data.get("data", {}).get("receipt") is not None):
        print(f"  ✓ {field:40s} -> VALID")
        return "valid", data
    
    if any("INTERNAL_ERROR" in str(e) or "unauthorized" in str(e).lower() for e in errors):
        print(f"  ✓ {field:40s} -> VALID (auth error = field exists)")
        return "valid_auth", data
    
    # Other errors might still indicate field is valid
    for e in errors:
        msg = e.get("message", "")
        if "Cannot query field" not in msg and "GRAPHQL_VALIDATION_FAILED" not in str(e.get("extensions", {})):
            print(f"  ? {field:40s} -> {msg[:80]}")
            return "maybe", data
    
    if not silent_invalid:
        print(f"  ✗ {field:40s} -> Invalid")
    return "invalid", None


async def main():
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        
        # Phase 1: More comprehensive field name search
        print("=== PHASE 1: Exhaustive field probe on DigitalReceipt ===\n")
        
        fields_to_try = [
            # Already confirmed: id, transactionId, store, __typename
            # Previously tried and invalid: items, lines, products, entries, etc.
            
            # Receipt/purchase specific
            "receiptId", "receiptNumber", "receiptType",
            "purchaseId", "purchaseNumber", "purchaseType",
            "transactionType", "transactionNumber",
            
            # Amount/total variations
            "totalAmount", "total", "totalPrice", "grandTotal",
            "subTotal", "subtotal", "netAmount", "grossAmount",
            "amount", "price", "cost",
            "totalToPay", "amountDue", "amountPaid",
            
            # Line items - more creative names
            "receiptLines", "receiptItems", "receiptEntries",
            "digitalReceiptLines", "digitalReceiptItems", 
            "purchaseLines", "purchaseItems", "purchaseProducts",
            "transactionLines", "transactionItems", "transactionEntries",
            "orderLines", "orderItems",
            "basketLines", "basketItems",
            "lineItems", "itemLines",
            "articles", "articleLines",
            "products", "productLines",
            "rows", "records", "entries",
            "ticketLines", "ticketItems",
            
            # Date/time
            "date", "dateTime", "timestamp", "createdAt", "updatedAt",
            "purchaseDate", "purchaseStartOn", "purchaseEndOn",
            "transactionDate", "transactionDateTime",
            "receiptDate",
            
            # Payment
            "payment", "payments", "paymentMethod", "paymentType",
            "paymentDetails", "paymentInfo",
            "tender", "tenders",
            
            # Store/location
            "storeId", "storeName", "storeInfo", "storeDetails",
            "location", "branch",
            
            # Customer/loyalty
            "customerId", "customer", "customerInfo",
            "bonusCard", "bonusCardNumber", "loyaltyCard",
            "bonusPoints", "loyaltyPoints", "points",
            "pointBalance", "pointsEarned", "pointsRedeemed",
            "extraPoints", "earnedPoints",
            
            # Savings/discounts  
            "savings", "totalSavings", "totalDiscount",
            "discount", "discounts", "discountAmount",
            "promotions", "offers", "coupons",
            "bonusSavings", "promotionSavings",
            
            # Tax/VAT
            "tax", "taxAmount", "vat", "vatAmount",
            "taxLines", "taxDetails",
            
            # Status/source
            "status", "type", "source", "receiptSource",
            "channel",
            
            # Content/data
            "content", "body", "raw", "rawReceipt",
            "data", "receiptData", "detail", "details",
            "digitalReceipt", "receiptContent",
            "header", "footer", "summary",
            
            # Misc
            "cashier", "register", "terminal", "lane",
            "barcode", "qrCode",
            "numberOfItems", "itemCount", "totalQuantity",
            "bags", "carrier",
            "currency",
            "version",
            "url", "link", "href",
            "image", "pdf", "pdfUrl",
            "printed", "emailed",
        ]
        
        valid_fields = ["id", "transactionId", "__typename"]
        object_fields = ["store"]
        
        for field in fields_to_try:
            status, result = await try_field(client, field)
            if status == "valid" or status == "valid_auth":
                valid_fields.append(field)
            elif status == "object":
                object_fields.append(field)
            elif status == "suggestion":
                # The suggestion IS a valid field name, add it
                valid_fields.append(result)
                print(f"    ↳ Added suggested field: {result}")
        
        print(f"\n=== SUMMARY ===")
        print(f"Valid scalar fields: {valid_fields}")
        print(f"Object fields (need subfields): {object_fields}")
        
        # Phase 2: Explore store object subfields
        print(f"\n=== PHASE 2: Probe 'store' subfields ===\n")
        store_subfields = [
            "storeId", "name", "id", "address", "city", "postalCode",
            "street", "houseNumber", "phone", "location", "type",
            "openingHours", "__typename",
        ]
        valid_store = []
        for sf in store_subfields:
            status, _ = await try_field(client, f"store {{ {sf} }}")
            if status in ("valid", "valid_auth"):
                valid_store.append(sf)
        
        print(f"\nValid store subfields: {valid_store}")
        
        # Phase 3: For any object fields found, probe their subfields
        for obj_field in object_fields:
            if obj_field == "store":
                continue
            print(f"\n=== PHASE 3: Probe '{obj_field}' subfields ===\n")
            common_subs = [
                "id", "name", "title", "description", "sku", "quantity",
                "price", "amount", "total", "discount", "type", "unit",
                "__typename", "image", "link", "brand", "category",
                "lineNumber", "lineId", "articleNumber", "barcode", "ean",
                "unitPrice", "totalPrice", "weight", "volume",
            ]
            for sf in common_subs:
                await try_field(client, f"{obj_field} {{ {sf} }}")
        
        # Phase 4: Try the receipt query with auth through the local proxy
        print(f"\n=== PHASE 4: Full query via local API ===\n")
        # We can't go through localhost directly since the local API 
        # doesn't expose raw graphql. But let's try via the raw endpoint anyway.


asyncio.run(main())

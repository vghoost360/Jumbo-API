"""Phase 2: Probe DigitalReceipt type fields by trial-and-error."""
import json
import httpx
import asyncio

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


async def probe_field(client, field_expr):
    """Try a field on DigitalReceipt and return error or success."""
    q = f'''query Receipt($tid: String!) {{
      receipt(transactionId: $tid) {{
        transactionId
        {field_expr}
      }}
    }}'''
    body = {"query": q, "variables": {"tid": "test"}}
    resp = await client.post(GRAPHQL_ENDPOINT, json=body, headers=HEADERS, cookies=cookies)
    data = resp.json()
    
    errors = data.get("errors", [])
    for e in errors:
        msg = e.get("message", "")
        if "Cannot query field" in msg:
            return "INVALID", msg
        if "Did you mean" in msg:
            return "SUGGESTION", msg
    
    if "data" in data:
        return "VALID", data
    return "OTHER", errors


async def main():
    # Known fields from receiptOverview
    known_fields = [
        "transactionId", "purchaseEndOn", "receiptSource", "pointBalance",
    ]
    
    # Candidate fields based on common receipt patterns
    candidate_fields = [
        # Direct fields
        "id", "store", "items", "lines", "products", "entries", "lineItems",
        "totalAmount", "total", "totalPrice", "amount", "subtotal",
        "receiptLines", "receiptItems", "receiptEntries", "receiptProducts",
        "digitalReceiptLines", "digitalReceiptItems",
        "purchaseLines", "purchaseItems", "purchaseProducts",
        "transactionLines", "transactionItems",
        "details", "detail", "data",
        "storeId", "storeName", "storeInfo",
        "customerId", "customerName",
        "paymentMethod", "paymentType", "payment",
        "date", "dateTime", "timestamp", "createdAt",
        "currency", "taxAmount", "tax", "vat",
        "discount", "discounts", "discountAmount",
        "bonusCard", "bonusPoints", "loyaltyPoints",
        "cashier", "register", "terminal",
        "receiptNumber", "receiptId", "number",
        "barcode", "qrCode",
        "header", "footer",
        "status", "type", "source",
        "totalQuantity", "itemCount", "numberOfItems",
        "__typename",
        # Nested store fields
        "store { storeId name }",
        # Maybe items with different structure
        "receiptData", "content", "body", "raw",
        "digitalReceipt", "storeReceipt",
        "purchaseDate", "purchaseTime",
        "savings", "totalSavings", "totalDiscount",
        "paymentDetails", "payments",
        "pointsEarned", "pointsSpent", "extraPoints",
    ]
    
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        print("\n=== PROBING DigitalReceipt FIELDS ===\n")
        
        valid = []
        suggestions = []
        
        for field in candidate_fields:
            status, result = await probe_field(client, field)
            
            if status == "VALID":
                print(f"  ✓ VALID: {field}")
                valid.append(field)
            elif status == "SUGGESTION":
                print(f"  ~ SUGGEST: {field} -> {result}")
                suggestions.append((field, result))
            elif status == "INVALID":
                # Quiet for invalid, but check for suggestions in the error
                if "Did you mean" in str(result):
                    print(f"  ~ SUGGEST: {field} -> {result}")
                    suggestions.append((field, result))
                # else: skip
            else:
                print(f"  ? OTHER: {field} -> {result}")
        
        print(f"\n=== RESULTS ===")
        print(f"Valid fields: {valid}")
        print(f"Suggestions: {suggestions}")
        
        # Now try with valid fields + __typename to see full structure
        if valid:
            print(f"\n=== TRYING ALL VALID FIELDS ===")
            valid_str = " ".join(valid)
            q = f'''query Receipt($tid: String!) {{
              receipt(transactionId: $tid) {{
                {valid_str}
              }}
            }}'''
            body = {"query": q, "variables": {"tid": "ievb1sv5th-2b5633de-0fec-11f1-8bb7-ac190a7f0000.json"}}
            resp = await client.post(GRAPHQL_ENDPOINT, json=body, headers=HEADERS, cookies=cookies)
            data = resp.json()
            print(json.dumps(data, indent=2)[:5000])


asyncio.run(main())

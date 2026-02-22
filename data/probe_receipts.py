"""Probe Jumbo GraphQL API for receipt-related types and queries."""
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

# Load cookies from saved session
try:
    with open("data/session-cookies.json") as f:
        cookies = json.load(f).get("cookies", {})
    print(f"Loaded {len(cookies)} cookies: {list(cookies.keys())}")
except Exception as e:
    print(f"No cookies: {e}")
    cookies = {}


async def query(name, q, variables=None, client_name=None):
    """Run a single GraphQL query and print result."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    
    body = {"query": q}
    if variables:
        body["variables"] = variables
    
    hdrs = {**HEADERS}
    if client_name:
        hdrs["apollographql-client-name"] = client_name
        hdrs["x-source"] = client_name
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.post(GRAPHQL_ENDPOINT, json=body, headers=hdrs, cookies=cookies)
            data = resp.json()
            print(json.dumps(data, indent=2)[:3000])
            return data
    except Exception as e:
        print(f"ERROR: {e}")
        return None


async def main():
    # 1. Introspection - list all query fields
    print("\n" + "#"*60)
    print("# 1. INTROSPECTION - All query fields")
    print("#"*60)
    
    result = await query(
        "Introspection - query fields",
        """{ __schema { queryType { fields { name description args { name type { name kind ofType { name } } } } } } }"""
    )
    
    # 2. Introspection - look for receipt-related types
    print("\n" + "#"*60)
    print("# 2. INTROSPECTION - All types (filter receipt-related)")
    print("#"*60)
    
    result = await query(
        "Introspection - types",
        """{ __schema { types { name kind fields { name type { name kind ofType { name kind } } } } } }"""
    )
    if result and "data" in result:
        types = result["data"]["__schema"]["types"]
        receipt_types = [t for t in types if t["name"] and ("receipt" in t["name"].lower() or "Receipt" in t["name"])]
        print(f"\n--- RECEIPT-RELATED TYPES ({len(receipt_types)}) ---")
        for t in receipt_types:
            print(json.dumps(t, indent=2))
    
    # 3. Try receipt/receiptDetail query with transactionId
    print("\n" + "#"*60)
    print("# 3. PROBE - receipt query")
    print("#"*60)
    
    tx_id = "ievb1sv5th-2b5633de-0fec-11f1-8bb7-ac190a7f0000.json"
    
    await query(
        "receipt(transactionId)",
        """query Receipt($transactionId: String!) {
          receipt(transactionId: $transactionId) {
            transactionId
            purchaseEndOn
            store { storeId name }
            items { name quantity price }
          }
        }""",
        {"transactionId": tx_id}
    )
    
    # 4. Try receiptDetail query
    print("\n" + "#"*60)
    print("# 4. PROBE - receiptDetail query")
    print("#"*60)
    
    await query(
        "receiptDetail(transactionId)",
        """query ReceiptDetail($transactionId: String!) {
          receiptDetail(transactionId: $transactionId) {
            transactionId
            purchaseEndOn
            store { storeId name }
            items { name quantity price }
          }
        }""",
        {"transactionId": tx_id}
    )
    
    # 5. Try storeReceipt query
    print("\n" + "#"*60)
    print("# 5. PROBE - storeReceipt query")
    print("#"*60)
    
    await query(
        "storeReceipt(transactionId)",
        """query StoreReceipt($transactionId: String!) {
          storeReceipt(transactionId: $transactionId) {
            transactionId
            purchaseEndOn
            store { storeId name }
            items { name quantity price }
          }
        }""",
        {"transactionId": tx_id}
    )
    
    # 6. Try receiptById query
    print("\n" + "#"*60)
    print("# 6. PROBE - receiptById query")  
    print("#"*60)
    
    await query(
        "receiptById(transactionId)",
        """query ReceiptById($transactionId: String!) {
          receiptById(transactionId: $transactionId) {
            transactionId
            purchaseEndOn
            store { storeId name }
          }
        }""",
        {"transactionId": tx_id}
    )
    
    # 7. Try __type introspection for specific types
    print("\n" + "#"*60)
    print("# 7. TYPE INTROSPECTION - Receipt / ReceiptDetail / StoreReceipt")
    print("#"*60)
    
    for type_name in ["Receipt", "ReceiptDetail", "StoreReceipt", "ReceiptOverview", "ReceiptItem", "ReceiptLine", "ReceiptProduct"]:
        await query(
            f"__type({type_name})",
            """query TypeInfo($name: String!) {
              __type(name: $name) {
                name
                kind
                fields {
                  name
                  type { name kind ofType { name kind ofType { name } } }
                }
              }
            }""",
            {"name": type_name}
        )

    # 8. Try the receiptOverview query with __typename to see what type it returns
    print("\n" + "#"*60)
    print("# 8. receiptOverview with __typename")
    print("#"*60)
    
    await query(
        "receiptOverview __typename",
        """query { 
          receiptOverview(page: 0, pageSize: 1) { 
            __typename
            totalResults 
            receipts { 
              __typename
              transactionId 
              purchaseEndOn 
            } 
          } 
        }"""
    )

    print("\n\nDONE.")


asyncio.run(main())

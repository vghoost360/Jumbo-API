"""Phase 6: With real cookies - probe receipt detail and Jumbo frontend."""
import json
import httpx
import asyncio
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/144.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}

GQL_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": HEADERS["User-Agent"],
    "apollographql-client-name": "JUMBO_WEB-orders",
    "apollographql-client-version": "master-v29.2.0-web",
    "x-source": "JUMBO_WEB-orders",
}

GRAPHQL_ENDPOINT = "https://www.jumbo.com/api/graphql"

with open("data/session-cookies.json") as f:
    cookies = json.load(f).get("cookies", {})
print(f"Loaded {len(cookies)} cookies: {list(cookies.keys())}")

TX_ID = "ievb1sv5th-2b5633de-0fec-11f1-8bb7-ac190a7f0000.json"


async def main():
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        
        # Step 1: Fetch the authenticated receipt with all known valid fields
        print("=== STEP 1: Fetch receipt with known valid fields (WITH AUTH) ===\n")
        
        q = '''query Receipt($tid: String!) {
          receipt(transactionId: $tid) {
            __typename
            id
            transactionId
            purchaseStartOn
            purchaseEndOn
            receiptSource
            store { storeId name __typename }
          }
        }'''
        body = {"query": q, "variables": {"tid": TX_ID}}
        resp = await client.post(GRAPHQL_ENDPOINT, json=body, headers=GQL_HEADERS, cookies=cookies)
        data = resp.json()
        print(json.dumps(data, indent=2))
        
        # Step 2: Fetch the Jumbo bonnen page with auth
        print("\n=== STEP 2: Fetch /mijn/bonnen with auth ===\n")
        resp = await client.get("https://www.jumbo.com/mijn/bonnen", headers=HEADERS, cookies=cookies)
        html = resp.text
        print(f"Status: {resp.status_code}, Length: {len(html)}")
        
        # Find all scripts
        scripts = re.findall(r'<script[^>]*(?:src=["\']([^"\']+)["\'])?[^>]*>(.*?)</script>', html, re.DOTALL)
        all_js_urls = set()
        for src, inline in scripts:
            if src:
                url = src if src.startswith("http") else f"https://www.jumbo.com{src}"
                all_js_urls.add(url)
                
        print(f"Found {len(all_js_urls)} JS URLs:")
        for u in sorted(all_js_urls):
            print(f"  {u}")
        
        # Check for receipt-related content in page
        receipt_refs = re.findall(r'[Rr]eceipt|[Bb]on(?:nen)|[Dd]igital[Rr]eceipt', html)
        print(f"\nReceipt references in page: {len(receipt_refs)}")
        
        # Look in __NUXT_DATA__
        nuxt_blocks = re.findall(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        for i, block in enumerate(nuxt_blocks):
            print(f"\nNUXT block {i}: {len(block)} chars")
            for m in re.finditer(r'"[^"]*[Rr]eceipt[^"]*"', block):
                print(f"  {m.group()}")
            for m in re.finditer(r'"[^"]*[Dd]igital[^"]*"', block):
                print(f"  {m.group()}")
            for m in re.finditer(r'"[^"]*query[^"]*"', block, re.IGNORECASE):
                print(f"  {m.group()[:100]}")
        
        # Step 3: Fetch JS bundles with receipt content
        print("\n=== STEP 3: Search JS bundles for receipt queries ===\n")
        
        for js_url in sorted(all_js_urls):
            try:
                resp = await client.get(js_url, headers=HEADERS)
                content = resp.text
                
                if 'receipt' not in content.lower() and 'DigitalReceipt' not in content:
                    continue
                
                print(f"\n  === {js_url.split('/')[-1]} ({len(content)} chars) ===")
                
                # Find all DigitalReceipt occurrences
                for m in re.finditer(r'DigitalReceipt', content):
                    s = max(0, m.start() - 300)
                    e = min(len(content), m.end() + 300)
                    ctx = content[s:e]
                    print(f"\n  DIGITAL_RECEIPT:\n    {ctx[:600]}\n")
                
                # Find receipt query patterns
                for m in re.finditer(r'receipt\s*[\(\{]', content, re.IGNORECASE):
                    s = max(0, m.start() - 200)
                    e = min(len(content), m.end() + 400)
                    ctx = content[s:e]
                    print(f"\n  RECEIPT_QUERY:\n    {ctx[:600]}\n")
                    
            except:
                pass
        
        # Step 4: Also check the main Jumbo page for the global app bundle 
        print("\n=== STEP 4: Check main page JS bundles ===\n")
        resp = await client.get("https://www.jumbo.com/", headers=HEADERS, cookies=cookies)
        main_html = resp.text
        main_scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', main_html)
        main_js_urls = set()
        for src in main_scripts:
            url = src if src.startswith("http") else f"https://www.jumbo.com{src}"
            main_js_urls.add(url)
        
        print(f"Main page has {len(main_js_urls)} JS URLs")
        
        for js_url in sorted(main_js_urls):
            try:
                resp = await client.get(js_url, headers=HEADERS)
                content = resp.text
                if 'receipt' not in content.lower():
                    continue
                
                print(f"\n  === {js_url.split('/')[-1]} ({len(content)} chars) ===")
                for m in re.finditer(r'DigitalReceipt', content):
                    s = max(0, m.start() - 300)
                    e = min(len(content), m.end() + 300)
                    print(f"    {content[s:e][:500]}")
            except:
                pass
        
        # Step 5: Probe more field names on DigitalReceipt with auth
        print("\n=== STEP 5: Extended field probe with auth ===\n")
        
        extra_fields = [
            # Dutch words
            "artikelen", "producten", "regels", "bonregels", "bonartikelen",
            "artikels", "productregels", "kassabon",
            # More English variations
            "groups", "sections", "segments", "blocks", "parts",
            "receiptGroups", "receiptSections", "digitalItems",
            "categories", "departments", "lineEntries",
            "ticketLines", "ticketItems", "salesLines", "salesItems",
            "purchases", "bought", "boughtItems",
            "productSummary", "itemSummary", "summary",
            "metadata", "meta", "info", "attributes",
            "coupons", "vouchers", "rewards",
            "pointBalance", "points", "bonusPoints",
            "totalAmount", "total", "totalPrice",
            "paymentMethod", "payment", "payments",
            "subtotal", "taxAmount", "discount",
        ]
        
        for field in extra_fields:
            q = f'query {{ receipt(transactionId: "{TX_ID}") {{ transactionId {field} }} }}'
            body = {"query": q}
            resp = await client.post(GRAPHQL_ENDPOINT, json=body, headers=GQL_HEADERS, cookies=cookies)
            data = resp.json()
            errors = data.get("errors", [])
            
            is_invalid = any("Cannot query field" in e.get("message", "") for e in errors)
            is_object = any("must have a selection of subfields" in e.get("message", "") for e in errors)
            has_suggestion = any("Did you mean" in e.get("message", "") for e in errors)
            
            if not is_invalid or is_object or has_suggestion:
                msg = errors[0].get("message", "") if errors else "VALID (no error)"
                print(f"  ✓ {field:40s} -> {msg[:100]}")
            elif is_invalid:
                # Check if there's a suggestion embedded
                for e in errors:
                    if "Did you mean" in e.get("message", ""):
                        print(f"  ~ {field:40s} -> {e['message'][:100]}")
        
        print("\n\nDONE.")


asyncio.run(main())

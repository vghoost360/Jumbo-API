"""Phase 5: Deep frontend investigation - find receipt detail loading mechanism."""
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

try:
    with open("data/session-cookies.json") as f:
        cookies = json.load(f).get("cookies", {})
    print(f"Loaded {len(cookies)} cookies")
except:
    cookies = {}
    print("No cookies")


async def main():
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        
        # Step 1: Fetch the bonnen (receipts) page
        print("=== STEP 1: Fetch /mijn/bonnen page ===\n")
        resp = await client.get("https://www.jumbo.com/mijn/bonnen", headers=HEADERS, cookies=cookies)
        html = resp.text
        print(f"Status: {resp.status_code}, Length: {len(html)}")
        
        # Find ALL script tags and link tags
        scripts = re.findall(r'<script[^>]*(?:src=["\']([^"\']+)["\'])?[^>]*>(.*?)</script>', html, re.DOTALL)
        links = re.findall(r'<link[^>]*href=["\']([^"\']+)["\'][^>]*>', html)
        
        all_js_urls = set()
        for src, inline in scripts:
            if src:
                url = src if src.startswith("http") else f"https://www.jumbo.com{src}"
                all_js_urls.add(url)
            if inline and 'receipt' in inline.lower():
                print(f"  INLINE SCRIPT with receipt: {inline[:500]}")
        
        print(f"\n  Found {len(all_js_urls)} script URLs")
        for u in sorted(all_js_urls):
            print(f"    {u}")
        
        # Step 2: Look in NUXT data
        print("\n=== STEP 2: Check __NUXT_DATA__ ===\n")
        nuxt = re.findall(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        for i, data in enumerate(nuxt):
            print(f"  NUXT block {i}: {len(data)} chars")
            # Find receipt-related strings
            for m in re.finditer(r'[^,\[\]"]{0,50}[Rr]eceipt[^,\[\]"]{0,50}', data):
                print(f"    {m.group()}")
            for m in re.finditer(r'[^,\[\]"]{0,50}[Bb]on(?:nen)?[^,\[\]"]{0,50}', data):
                s = m.group()
                if 'bon' in s.lower() and len(s) < 100:
                    print(f"    {s}")
        
        # Step 3: Fetch JS bundles and search for GraphQL queries
        print("\n=== STEP 3: Search JS bundles ===\n")
        
        for js_url in sorted(all_js_urls):
            try:
                resp = await client.get(js_url, headers=HEADERS)
                content = resp.text
                
                has_receipt = 'receipt' in content.lower() or 'Receipt' in content
                has_bon = 'bonnen' in content.lower() or '/mijn/bon' in content.lower()
                has_gql = 'graphql' in content.lower() or 'query' in content.lower()
                
                if not (has_receipt or has_bon):
                    continue
                
                print(f"\n  === {js_url} ({len(content)} chars) ===")
                print(f"    has_receipt={has_receipt}, has_bon={has_bon}, has_gql={has_gql}")
                
                # Find all occurrences of "receipt" with surrounding context
                for m in re.finditer(r'receipt', content, re.IGNORECASE):
                    start = max(0, m.start() - 150)
                    end = min(len(content), m.end() + 150)
                    ctx = content[start:end].replace('\n', '\\n')
                    print(f"    CTX: ...{ctx}...")
                    
                # Find DigitalReceipt references
                for m in re.finditer(r'DigitalReceipt', content):
                    start = max(0, m.start() - 200)
                    end = min(len(content), m.end() + 200)
                    ctx = content[start:end].replace('\n', '\\n')
                    print(f"    DIGITAL: ...{ctx}...")
                
            except Exception as e:
                print(f"  Error fetching {js_url}: {e}")
        
        # Step 4: Try a receipt detail page URL (the specific receipt)  
        print("\n=== STEP 4: Try receipt detail page URLs ===\n")
        tx_id = "ievb1sv5th-2b5633de-0fec-11f1-8bb7-ac190a7f0000.json"
        
        detail_urls = [
            f"https://www.jumbo.com/mijn/bonnen/{tx_id}",
            f"https://www.jumbo.com/mijn/bon/{tx_id}",
            f"https://www.jumbo.com/api/receipt/{tx_id}",
            f"https://www.jumbo.com/api/receipts/{tx_id}",
            f"https://www.jumbo.com/api/digital-receipt/{tx_id}",
        ]
        
        for url in detail_urls:
            try:
                resp = await client.get(url, headers=HEADERS, cookies=cookies)
                print(f"  {url}")
                print(f"    Status: {resp.status_code}, Content-Type: {resp.headers.get('content-type', 'unknown')}")
                if resp.status_code == 200:
                    text = resp.text
                    print(f"    Length: {len(text)}")
                    if 'json' in resp.headers.get('content-type', ''):
                        print(f"    Body: {text[:1000]}")
                    else:
                        # Look for receipt data in HTML
                        for m in re.finditer(r'receipt|transaction|product|item', text[:5000], re.IGNORECASE):
                            start = max(0, m.start() - 50)
                            end = min(len(text), m.end() + 50)
                            print(f"    HTML: ...{text[start:end]}...")
                            break
            except Exception as e:
                print(f"  {url} -> Error: {e}")
        
        # Step 5: Check if there's a dedicated receipt REST API
        print("\n=== STEP 5: Probe REST API endpoints ===\n")
        
        rest_urls = [
            "https://www.jumbo.com/api/loyalty/receipts",
            "https://www.jumbo.com/api/loyalty/receipt",
            f"https://www.jumbo.com/api/loyalty/receipts/{tx_id}",
            f"https://www.jumbo.com/api/loyalty/receipt/{tx_id}",
        ]
        
        for url in rest_urls:
            try:
                resp = await client.get(url, headers={**HEADERS, "Accept": "application/json"}, cookies=cookies)
                print(f"  {resp.status_code} {url}")
                if resp.status_code < 500:
                    print(f"    {resp.text[:500]}")
            except Exception as e:
                print(f"  Error: {url} -> {e}")
        
        # Step 6: Try DigitalReceipt with more creative field names
        # Maybe the items are called "groups", "sections", "lines" etc.
        print("\n=== STEP 6: More DigitalReceipt field probing ===\n")
        
        extra_fields = [
            "groups", "sections", "segments", "blocks", "parts",
            "artikelen", "producten", "regels", "bonregels",  # Dutch
            "receiptGroups", "receiptSections", "receiptSegments",
            "digitalReceiptData", "receiptBody", "receiptContent",
            "vatLines", "vatGroups", "averages",
            "paymentLines", "tenderLines",
            "reward", "rewards", "bonusInfo",
            "totalItems", "totalProducts",
            "receiptUrl", "receiptPdf", "pdfLink",
            "categories", "departments",
            "metadata", "meta", "info",
            "coupons", "vouchers",
            "signature",
            "operator", "till", "tillNumber",
        ]
        
        for field in extra_fields:
            q = f'query {{ receipt(transactionId: "test") {{ transactionId {field} }} }}'
            body = {"query": q}
            resp = await client.post(GRAPHQL_ENDPOINT, json=body, headers=GQL_HEADERS, cookies=cookies)
            data = resp.json()
            errors = data.get("errors", [])
            
            is_invalid = any("Cannot query field" in e.get("message", "") for e in errors)
            is_object = any("must have a selection of subfields" in e.get("message", "") for e in errors)
            has_suggestion = any("Did you mean" in e.get("message", "") for e in errors)
            
            if not is_invalid or is_object or has_suggestion:
                msg = errors[0].get("message", "") if errors else "NO ERROR"
                print(f"  ✓ {field:40s} -> {msg[:100]}")
        
        print("\n\nDONE.")


asyncio.run(main())

"""Phase 4: Scrape Jumbo.com frontend JS for receipt-related GraphQL queries."""
import json
import httpx
import asyncio
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/144.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
}

GRAPHQL_ENDPOINT = "https://www.jumbo.com/api/graphql"
GQL_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": HEADERS["User-Agent"],
    "apollographql-client-name": "JUMBO_WEB-orders",
    "apollographql-client-version": "master-v29.2.0-web",
    "x-source": "JUMBO_WEB-orders",
}

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
        
        # 1. Fetch the Jumbo receipt page HTML to find JS bundle URLs
        print("=== FETCHING JUMBO RECEIPT PAGE ===\n")
        
        urls_to_check = [
            "https://www.jumbo.com/mijn/bonnen",
            "https://www.jumbo.com/mijn/bestellingen",
        ]
        
        all_js_urls = set()
        
        for url in urls_to_check:
            print(f"Fetching {url}...")
            try:
                resp = await client.get(url, headers=HEADERS, cookies=cookies)
                html = resp.text
                
                # Find all JS bundle URLs
                js_urls = re.findall(r'(?:src|href)=["\']([^"\']*\.js(?:\?[^"\']*)?)["\']', html)
                for js in js_urls:
                    if js.startswith("/"):
                        js = f"https://www.jumbo.com{js}"
                    if "jumbo.com" in js or js.startswith("/_nuxt/"):
                        all_js_urls.add(js if js.startswith("http") else f"https://www.jumbo.com{js}")
                
                # Also check for NUXT data
                nuxt_match = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                if nuxt_match:
                    nuxt_data = nuxt_match.group(1)
                    # Look for receipt-related strings
                    receipt_strings = re.findall(r'[^"]*[Rr]eceipt[^"]*', nuxt_data)
                    if receipt_strings:
                        print(f"  NUXT receipt strings: {receipt_strings[:20]}")
                    
                print(f"  Found {len(js_urls)} JS URLs")
            except Exception as e:
                print(f"  Error: {e}")
        
        print(f"\nTotal unique JS URLs: {len(all_js_urls)}")
        
        # 2. Fetch JS bundles and search for receipt-related GraphQL queries
        print("\n=== SEARCHING JS BUNDLES FOR RECEIPT QUERIES ===\n")
        
        receipt_patterns = [
            re.compile(r'receipt|Receipt|RECEIPT', re.IGNORECASE),
            re.compile(r'digitalReceipt|DigitalReceipt', re.IGNORECASE),
            re.compile(r'bon(?:nen)?', re.IGNORECASE),  # Dutch for receipt
        ]
        
        gql_pattern = re.compile(r'(query|mutation)\s+\w*[Rr]eceipt\w*[^}]*\{[^}]*\}', re.DOTALL)
        gql_pattern2 = re.compile(r'receipt\s*\([^)]*\)\s*\{[^}]*\}', re.DOTALL)
        
        found_queries = []
        
        for js_url in sorted(all_js_urls):
            try:
                resp = await client.get(js_url, headers=HEADERS)
                content = resp.text
                
                # Quick check for receipt-related content
                if 'receipt' not in content.lower() and 'Receipt' not in content:
                    continue
                
                print(f"  MATCH in: {js_url}")
                
                # Find GraphQL query strings
                # Look for template literals or string concatenations with receipt queries
                
                # Pattern 1: Long strings that look like GraphQL
                for m in re.finditer(r'["`]([^"`]{50,})["`]', content):
                    chunk = m.group(1)
                    if 'receipt' in chunk.lower() and ('query' in chunk.lower() or 'mutation' in chunk.lower() or '{' in chunk):
                        print(f"    GQL chunk: {chunk[:200]}...")
                        found_queries.append(chunk)
                
                # Pattern 2: Minified GraphQL with receipt
                for m in re.finditer(r'((?:query|mutation)\s+\w*(?:receipt|Receipt|bon)\w*(?:\([^)]*\))?\s*\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})', content):
                    q = m.group(0)
                    print(f"    QUERY: {q[:300]}...")
                    found_queries.append(q)
                
                # Pattern 3: Look for operationName with receipt
                for m in re.finditer(r'operationName["\s:]+["\']([\w]*[Rr]eceipt[\w]*)["\']', content):
                    print(f"    OPERATION: {m.group(1)}")
                
                # Pattern 4: Look for field names near receipt
                for m in re.finditer(r'receipt(?:Detail|Lines?|Items?|Products?|Data|Content|Overview|By\w+|Info)\b', content, re.IGNORECASE):
                    ctx_start = max(0, m.start() - 100)
                    ctx_end = min(len(content), m.end() + 100)
                    context_str = content[ctx_start:ctx_end].replace('\n', ' ')
                    print(f"    CONTEXT: ...{context_str}...")
                
                # Pattern 5: Look for specific field names near "DigitalReceipt"
                for m in re.finditer(r'DigitalReceipt', content):
                    ctx_start = max(0, m.start() - 300)
                    ctx_end = min(len(content), m.end() + 300)
                    context_str = content[ctx_start:ctx_end].replace('\n', ' ')
                    print(f"    DIGITAL_RECEIPT_CTX: ...{context_str}...")
                
            except Exception as e:
                pass
        
        # 3. Also try alternative query names / approaches
        print("\n=== PHASE 3: Try more query names and union/interface patterns ===\n")
        
        # Try fragment on DigitalReceipt
        tests = [
            # Maybe there's a digitalReceipt query
            ("digitalReceipt query", '{ digitalReceipt(transactionId: "test") { __typename } }'),
            # Maybe there's a bon/bonnen query (Dutch)
            ("bon query", '{ bon(transactionId: "test") { __typename } }'),
            ("bonDetail query", '{ bonDetail(transactionId: "test") { __typename } }'),
            # Maybe there's a receiptContent query
            ("receiptContent query", '{ receiptContent(transactionId: "test") { __typename } }'),
            # Try receipt with different arg names
            ("receipt(id)", 'query { receipt(id: "test") { __typename } }'),
            ("receipt(receiptId)", 'query { receipt(receiptId: "test") { __typename } }'),
            # Maybe it's a nested field on another query
            ("receiptOverview receipts with detail", '''
                query { receiptOverview(page: 0, pageSize: 1) { 
                    receipts { transactionId details { __typename } } 
                } }
            '''),
            ("receiptOverview receipts items", '''
                query { receiptOverview(page: 0, pageSize: 1) { 
                    receipts { transactionId items { __typename } } 
                } }
            '''),
            # pointBalance on DigitalReceipt?
            ("receipt pointBalance", 'query { receipt(transactionId: "test") { transactionId pointBalance } }'),
            # Maybe receiptLines is a separate top-level query
            ("receiptLines query", '{ receiptLines(transactionId: "test") { __typename } }'),
            ("receiptItems query", '{ receiptItems(transactionId: "test") { __typename } }'),
            # Try with storeReceipts as plural
            ("storeReceipts query", '{ storeReceipts(transactionId: "test") { __typename } }'),
        ]
        
        for name, q in tests:
            body = {"query": q}
            resp = await client.post(GRAPHQL_ENDPOINT, json=body, headers=GQL_HEADERS, cookies=cookies)
            data = resp.json()
            errors = data.get("errors", [])
            
            interesting = False
            for e in errors:
                msg = e.get("message", "")
                if "Cannot query field" not in msg and "GRAPHQL_VALIDATION_FAILED" not in str(e.get("extensions", {})):
                    interesting = True
                if "Did you mean" in msg:
                    interesting = True
            
            if not errors or interesting or data.get("data"):
                print(f"  {name}: {json.dumps(data, indent=2)[:300]}")
            else:
                err_msgs = [e.get("message", "")[:100] for e in errors]
                # Only print if there's useful info
                has_suggestion = any("Did you mean" in m for m in err_msgs)
                has_valid = "Cannot query field" not in str(err_msgs)
                if has_suggestion or has_valid:
                    print(f"  {name}: {err_msgs}")
        
        print("\n\nDONE.")


asyncio.run(main())

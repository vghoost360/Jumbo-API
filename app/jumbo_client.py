"""
Jumbo.com GraphQL API Client
Handles authentication via Selenium and all basket/product operations.
"""
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

log = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://www.jumbo.com/api/graphql"
SEARCH_ENDPOINT = "https://www.jumbo.com/producten/"
CACHE_FILE = Path("data/barcode-cache.json")
RECEIPT_SKU_CACHE = Path("data/receipt-sku-cache.json")
SETTINGS_FILE = Path("data/settings.json")
COOKIE_FILE = Path("data/session-cookies.json")
CREDS_FILE = Path("data/credentials.json")

DEFAULT_SETTINGS = {
    "productMatchingEnabled": True,
    "strictMatching": False,
    "confidenceThreshold": 50,
    "useWeightMatching": True,
    "usePriceMatching": True,
    "useNameMatching": True,
    "useOpenFoodFactsFallback": True,
    "maxProductCandidates": 15,
    # OpenFoodFacts search options
    "useQuantityInSearch": True,    # Include size/volume in search (e.g., "Cola 1,5 l")
    "useBrandInSearch": False,       # Include brand in search (e.g., "Jumbo Cola")
    # Caching
    "useBarcodeCache": True,         # Cache barcode lookups
    # Receipt matching weights (max points per category)
    "priceMatchWeight": 40,
    "weightMatchWeight": 30,
    "nameMatchWeight": 30,
    # EAN similarity scores for digit matches
    "eanScore10Plus": 90,   # 10+ matching digits
    "eanScore8Plus": 70,     # 8-9 matching digits
    "eanScore6Plus": 50,     # 6-7 matching digits
    "eanScore4Plus": 30,     # 4-5 matching digits
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0"
)

REQUIRED_COOKIES = [
    "user-session",
    "auth-session",
]

# Optional cookies we try to capture but don't require
OPTIONAL_COOKIES = [
    "authentication-token",
    "sid",
    "akaas_as",
    "ak_bmsc",
]


class JumboClient:
    def __init__(self):
        self.cookies: Dict[str, str] = {}
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.auto_reauth: bool = True
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "apollographql-client-name": "JUMBO_WEB-basket",
            "apollographql-client-version": "master-v29.2.0-web",
            "x-source": "JUMBO_WEB-basket",
        }
        self._load_cookies_from_file()
        self._load_credentials()

    # ── Authentication ────────────────────────────────────────────────

    async def login(self, username: str, password: str, save_credentials: bool = True) -> Dict[str, Any]:
        """Automate browser login with Selenium and capture session cookies."""
        try:
            log.info("Starting login…")
            driver = self._create_driver()

            try:
                self._perform_login(driver, username, password)
                cookies_found = self._capture_cookies(driver)

                ok = len(cookies_found) >= 4
                msg = "Login successful" if ok else "Login failed – insufficient cookies"
                log.info("%s \u2013 captured %d cookies", msg, len(cookies_found))
                
                if ok:
                    self._save_cookies_to_file()
                    if save_credentials:
                        self.username = username
                        self.password = password
                        self._save_credentials()
                        log.info("Credentials saved for auto re-authentication")
                
                return {
                    "success": ok,
                    "message": msg,
                    "cookies_captured": len(cookies_found),
                }
            finally:
                driver.quit()

        except Exception as exc:
            log.error("Login error: %s", exc)
            return {"success": False, "message": f"Login error: {exc}"}

    def is_authenticated(self) -> bool:
        # Need at least user-session and auth-session to be authenticated
        # authentication-token and sid may not always be present in all login flows
        required = ["user-session", "auth-session"]
        optional = ["authentication-token", "sid"]
        
        has_required = all(k in self.cookies for k in required)
        present = [k for k in required + optional if k in self.cookies]
        
        if not has_required:
            log.debug("Auth check: missing required cookies (have: %s)", list(self.cookies.keys()))
        
        return has_required

    def get_auth_info(self) -> Dict[str, Any]:
        """Return detailed authentication status info."""
        required = ["user-session", "auth-session"]
        return {
            "authenticated": self.is_authenticated(),
            "cookies_count": len(self.cookies),
            "cookies_present": list(self.cookies.keys()),
            "required_cookies": required,
            "has_credentials": bool(self.username and self.password),
            "auto_reauth_enabled": self.auto_reauth,
        }

    # ── GraphQL transport ─────────────────────────────────────────────

    async def graphql_request(
        self, query: str, variables: Optional[Dict] = None, retry: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
        operation_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_authenticated():
            # Try to auto re-authenticate if credentials are available
            if self.auto_reauth and self.username and self.password:
                log.warning("Not authenticated. Attempting auto re-authentication...")
                result = await self.login(self.username, self.password, save_credentials=False)
                if not result.get("success"):
                    raise Exception("Not authenticated and auto re-authentication failed. Please login first.")
            else:
                raise Exception("Not authenticated. Please login first.")

        body: Dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        if operation_name:
            body["operationName"] = operation_name

        # Build headers: base + optional overrides (thread-safe, no mutation)
        request_headers = {**self.headers}
        if extra_headers:
            request_headers.update(extra_headers)

        timeout = httpx.Timeout(10.0, connect=30.0, read=120.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            resp = await c.post(
                GRAPHQL_ENDPOINT,
                json=body,
                headers=request_headers,
                cookies=self.cookies,
            )
            data = resp.json()

        if "errors" in data:
            error_msg = data['errors'][0].get('message', '')
            # Check if it's an authentication error
            if retry and self.auto_reauth and self.username and self.password and (
                'unauthorized' in error_msg.lower() or 
                'not authenticated' in error_msg.lower() or
                'invalid token' in error_msg.lower()
            ):
                log.warning("Session expired. Re-authenticating...")
                self.cookies.clear()
                result = await self.login(self.username, self.password, save_credentials=False)
                if result.get("success"):
                    # Retry the request once with new cookies
                    return await self.graphql_request(
                        query, variables, retry=False,
                        extra_headers=extra_headers, operation_name=operation_name,
                    )
            raise Exception(f"GraphQL Error: {error_msg}")
        return data.get("data", {})

    async def _graphql_with_headers(
        self, query: str, variables: Optional[Dict] = None,
        client_name: str = "JUMBO_WEB-basket",
    ) -> Dict[str, Any]:
        """GraphQL request with custom client name (thread-safe, no header mutation)."""
        extra = {
            "apollographql-client-name": client_name,
            "x-source": client_name,
        }
        return await self.graphql_request(query, variables, extra_headers=extra)

    # ── Basket operations ─────────────────────────────────────────────

    async def get_basket(self) -> Dict[str, Any]:
        """Return the active basket with full product details & prices."""
        query = """
        {
          activeBasket {
            ... on ActiveBasketResult {
              basket {
                id
                totalProductCount
                type
                lines {
                  sku
                  id
                  quantity
                  details {
                    sku title subtitle brand image link category
                    price {
                      price promoPrice
                      pricePerUnit { price quantity unit }
                    }
                    availability { availability isAvailable label }
                  }
                }
              }
            }
            ... on BasketError { errorMessage reason }
          }
        }
        """
        data = await self.graphql_request(query)
        ab = data.get("activeBasket", {})
        if "errorMessage" in ab:
            raise Exception(f"Basket Error: {ab['errorMessage']}")
        return ab.get("basket", {})

    async def add_to_basket(self, sku: str, quantity: float = 1) -> Dict[str, Any]:
        mutation = """
        mutation AddBasketLines($input: AddBasketLinesInput!) {
          addBasketLines(input: $input) {
            ... on Basket {
              id totalProductCount
              lines { id sku quantity details { sku title } }
            }
            ... on Error { reason errorMessage friendlyMessage }
          }
        }
        """
        variables = {
            "input": {
                "lines": [{"sku": sku, "quantity": quantity}],
                "type": "ECOMMERCE",
            }
        }
        result = (await self.graphql_request(mutation, variables)).get(
            "addBasketLines", {}
        )
        if result.get("reason") or result.get("errorMessage"):
            raise Exception(
                result.get("errorMessage")
                or result.get("friendlyMessage")
                or "Add failed"
            )
        return result

    async def remove_from_basket(
        self, line_id: Optional[str] = None, sku: Optional[str] = None
    ) -> Dict[str, Any]:
        if sku and not line_id:
            basket = await self.get_basket()
            line = next(
                (l for l in basket.get("lines", []) if l.get("sku") == sku), None
            )
            if not line:
                raise Exception(f"SKU {sku} not found in basket")
            line_id = line["id"]

        if not line_id:
            raise Exception("Provide line_id or sku")

        mutation = """
        mutation RemoveBasketLines($input: RemoveBasketLinesInput!) {
          removeBasketLines(input: $input) {
            ... on Basket {
              id totalProductCount
              lines { id sku quantity details { sku title } }
            }
            ... on Error { reason errorMessage friendlyMessage }
          }
        }
        """
        variables = {"input": {"ids": [line_id], "type": "ECOMMERCE"}}
        result = (await self.graphql_request(mutation, variables)).get(
            "removeBasketLines", {}
        )
        if result.get("reason") or result.get("errorMessage"):
            raise Exception(
                result.get("errorMessage")
                or result.get("friendlyMessage")
                or "Remove failed"
            )
        return result
    async def update_basket_item_quantity(
        self, line_id: str, quantity: float
    ) -> Dict[str, Any]:
        """Update the quantity of a basket item."""
        mutation = """
        mutation BasketPageUpdateBasketItemQuantity($input: UpdateBasketLineQuantityInput!) {
          updateBasketLineQuantity(input: $input) {
            ... on Basket {
              id
              contentsChanged
              totalProductCount
              type
              lines {
                sku
                id
                quantity
                details {
                  sku
                  title
                  subtitle
                  brand
                  image
                  link
                  category
                  price {
                    price
                    promoPrice
                    pricePerUnit {
                      price
                      quantity
                      unit
                    }
                  }
                  availability {
                    availability
                    isAvailable
                    label
                  }
                  promotions {
                    id
                    tags {
                      text
                      inverse
                    }
                  }
                }
              }
            }
            ... on Error {
              reason
              errorMessage
              friendlyHeader
              friendlyMessage
            }
          }
        }
        """
        variables = {
            "input": {"id": line_id, "quantity": quantity, "type": "ECOMMERCE"}
        }
        result = (await self.graphql_request(mutation, variables)).get(
            "updateBasketLineQuantity", {}
        )
        if result.get("reason") or result.get("errorMessage"):
            raise Exception(
                result.get("errorMessage")
                or result.get("friendlyMessage")
                or "Update failed"
            )
        return result
    # ── Lists operations ──────────────────────────────────────────────

    async def get_lists(self, list_limit: int = 25, item_limit: int = 4) -> Dict[str, Any]:
        """Fetch all customer shopping lists with preview items."""
        query = """
        query GetCustomerProductLists($listPagination: PaginationInput, $listItemPagination: PaginationInput) {
          customerLists: productLists(
            query: {type: CUSTOMER}
            pagination: $listPagination
          ) {
            ...CustomerProductLists
            __typename
          }
          favouriteLists: productLists(query: {type: FAVORITE}) {
            ...CustomerProductLists
            __typename
          }
          followingLists {
            total
            __typename
          }
        }
        
        fragment CustomerProductLists on ProductListsResponse {
          items {
            id
            productsCount
            title
            type
            userID
            followersCount
            description
            author {
              name
              __typename
            }
            items(pagination: $listItemPagination) {
              product {
                image
                __typename
              }
              __typename
            }
            __typename
          }
          total
          __typename
        }
        """
        variables = {
            "listPagination": {"offset": 0, "limit": list_limit},
            "listItemPagination": {"offset": 0, "limit": item_limit}
        }
        
        return await self._graphql_with_headers(
            query, variables, client_name="JUMBO_WEB-list"
        )

    async def get_list_by_id(self, list_id: str, item_limit: int = 25) -> Dict[str, Any]:
        """Fetch a specific shopping list with full product details."""
        from datetime import datetime, timezone
        
        query = """
        query GetProductList($listId: ID!, $listItemsPagination: PaginationInput, $referenceDate: String!) {
          productListV2(id: $listId) {
            id
            type
            title
            description
            userID
            author {
              name
              verified
              image
              __typename
            }
            items(pagination: $listItemsPagination) {
              id
              sku
              orderIndex
              product {
                sku
                id
                brand
                category
                subtitle: packSizeDisplay
                title
                image
                availability {
                  availability
                  isAvailable
                  label
                  __typename
                }
                link
                prices: price(referenceDate: $referenceDate) {
                  price
                  promoPrice
                  pricePerUnit {
                    price
                    unit
                    __typename
                  }
                  __typename
                }
                quantityDetails {
                  maxAmount
                  minAmount
                  stepAmount
                  defaultAmount
                  __typename
                }
                promotions {
                  id
                  title
                  tags {
                    text
                    __typename
                  }
                  __typename
                }
                __typename
              }
              quantity {
                amount
                unit
                __typename
              }
              __typename
            }
            labels
            isFollowedByMe
            followersCount
            isPublic
            productsCount
            webUrl
            __typename
          }
        }
        """
        
        reference_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        variables = {
            "listId": list_id,
            "listItemsPagination": {"offset": 0, "limit": item_limit},
            "referenceDate": reference_date
        }
        
        return await self._graphql_with_headers(
            query, variables, client_name="JUMBO_WEB-list"
        )

    # ── Orders operations ─────────────────────────────────────────────

    async def get_orders_and_receipts(
        self, orders_limit: int = 10, receipts_page: int = 0, receipts_page_size: int = 10
    ) -> Dict[str, Any]:
        """Fetch online orders and store receipts."""
        query = """
        query GetOnlineOrdersAndStoreReceipts($ordersInput: OrdersInput!, $page: Int, $pageSize: Int) {
          storeReceipts: receiptOverview(page: $page, pageSize: $pageSize) {
            totalResults
            pageSize
            currentPage
            receipts {
              transactionId
              purchaseEndOn
              receiptSource
              store {
                storeId
                name
              }
              pointBalance
            }
          }
          onlineOrders: orders(input: $ordersInput) {
            orders {
              orderId
              customerId
              deliveryDate
              slotStartTime
              slotEndTime
              cutoffTime
              fulfilmentType
              status
              emailAddress
              branchName
              deliveryAddress {
                street
                postalCode
                houseNumber
                addition
                city
              }
              totalToPayMoneyType {
                amount
                currency
              }
            }
            totalCount
          }
        }
        """
        variables = {
            "ordersInput": {
                "offset": 0,
                "limit": orders_limit,
                "direction": "DESC",
                "sortBy": "deliveryDate",
                "statusCategory": "CLOSED"
            },
            "page": receipts_page,
            "pageSize": receipts_page_size
        }
        
        return await self._graphql_with_headers(
            query, variables, client_name="JUMBO_WEB-orders"
        )

    async def get_order_details(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific order including all products."""
        query = """
        query OrderPagesOrder($orderId: Float!, $mergeItemsWithSameSkuAndPrice: Boolean! = true) {
          order(
            orderId: $orderId
            options: {mergeItemsWithSameSkuAndPrice: $mergeItemsWithSameSkuAndPrice}
          ) {
            orderId
            customerId
            deliveryDate
            fulfilmentType
            hasAgeRestrictedItems
            paymentLink {
              url
              isAuthorized
              __typename
            }
            fulfilmentData {
              reservationId
              startTime
              endTime
              storeId
              storeV2 {
                storeId
                name
                location {
                  address {
                    houseNumber
                    postalCode
                    street
                    city
                    __typename
                  }
                  __typename
                }
                __typename
              }
              displayAddress {
                street
                postalCode
                houseNumber
                addition
                city
                __typename
              }
              __typename
            }
            paymentMethod
            items {
              lineId: lineNumber
              sku
              quantity
              orderedQuantity
              pickedQuantity
              unit
              linePriceExDiscount {
                amount
                currency
                __typename
              }
              linePriceIncDiscount {
                amount
                currency
                __typename
              }
              pricePerUnit {
                price {
                  amount
                  currency
                  __typename
                }
                unit
                __typename
              }
              promotions {
                id
                discount {
                  amount
                  currency
                  __typename
                }
                type
                scope
                description
                voucherCode
                __typename
              }
              deposits {
                sku
                quantity
                unitPrice {
                  amount
                  currency
                  __typename
                }
                description
                __typename
              }
              substitution {
                substitutedBy
                substituteFor
                __typename
              }
              surcharges {
                type
                value {
                  amount
                  currency
                  __typename
                }
                __typename
              }
              details {
                id
                sku
                title
                subtitle
                image
                link
                ageRestriction
                category
                brand
                price {
                  price
                  promoPrice
                  pricePerUnit {
                    price
                    quantity
                    unit
                    __typename
                  }
                  __typename
                }
                availability {
                  availability
                  isAvailable
                  label
                  reason
                  __typename
                }
                quantityDetails {
                  defaultAmount
                  maxAmount
                  minAmount
                  stepAmount
                  unit
                  __typename
                }
                primaryProductBadges {
                  alt
                  image
                  __typename
                }
                secondaryProductBadges {
                  alt
                  image
                  __typename
                }
                surcharges {
                  type
                  value {
                    amount
                    currency
                    __typename
                  }
                  __typename
                }
                promotions {
                  start {
                    dayShort
                    date
                    monthShort
                    __typename
                  }
                  end {
                    dayShort
                    date
                    monthShort
                    __typename
                  }
                  tags {
                    text
                    inverse
                    __typename
                  }
                  isKiesAndMix
                  __typename
                }
                __typename
              }
              __typename
            }
            totals {
              totalToPay {
                amount
                currency
                __typename
              }
              totalTax {
                amount
                currency
                __typename
              }
              itemSubtotal {
                amount
                currency
                __typename
              }
              itemDiscounts {
                amount
                currency
                __typename
              }
              orderDiscounts {
                amount
                currency
                __typename
              }
              shippingCosts {
                amount
                currency
                __typename
              }
              shippingDiscounts {
                amount
                currency
                __typename
              }
              __typename
            }
            progress {
              orderChannel
              cutoffTime
              status
              collectedTime
              __typename
            }
            progressHelpers {
              hasPassedCutoffTime
              isCancelled
              isCompleted
              isClosed
              isEditable
              isReadyForDelivery
              __typename
            }
            __typename
          }
        }
        """
        
        log.info("Fetching order details for order %s", order_id)
            
        variables = {
            "orderId": float(order_id),
            "mergeItemsWithSameSkuAndPrice": True
        }
        
        try:
            result = await self._graphql_with_headers(
                query, variables, client_name="JUMBO_WEB-orders"
            )
            
            if result and "order" in result:
                order = result["order"]
                log.info("Retrieved order %s with %d items", order_id, len(order.get('items', [])))
                return order
            
            log.warning("No order data found for order %s", order_id)
            return None
            
        except Exception as e:
            log.error("Error fetching order details for %s: %s", order_id, e)
            return None

    # ── Receipt operations ────────────────────────────────────────────

    async def get_receipt_detail(self, transaction_id: str) -> Dict[str, Any]:
        """Fetch full receipt detail (including parsed line items from print JSON)."""
        query = """
        query GetDigitalReceipt($transactionId: String) {
          receipt(transactionId: $transactionId) {
            receiptImage {
              image
              type
              receiptPoints {
                earned
                newBalance
                oldBalance
                redeemed
              }
            }
            store {
              name
              location {
                address {
                  city
                  houseNumber
                  postalCode
                  street
                }
              }
            }
            purchaseEndOn
            receiptSource
            customerDetails {
              customerId
              loyaltyCard {
                number
              }
            }
            transactionId
          }
        }
        """
        variables = {"transactionId": transaction_id}

        data = await self._graphql_with_headers(
            query, variables, client_name="JUMBO_WEB-orders"
        )

        receipt = data.get("receipt")
        if not receipt:
            return None

        result: Dict[str, Any] = {
            "transactionId": receipt.get("transactionId", transaction_id),
            "purchaseEndOn": receipt.get("purchaseEndOn"),
            "receiptSource": receipt.get("receiptSource"),
            "store": receipt.get("store"),
            "customerDetails": receipt.get("customerDetails"),
            "points": receipt.get("receiptImage", {}).get("receiptPoints"),
        }

        # For ONLINE receipts, extract the order ID from the transaction ID
        if receipt.get("receiptSource") == "ONLINE":
            order_match = re.match(r"^(\d+)-", transaction_id)
            if order_match:
                result["orderId"] = int(order_match.group(1))

        # Parse the receipt print-layout JSON into structured items
        receipt_image = receipt.get("receiptImage", {})
        if receipt_image and receipt_image.get("type") == "JSON" and receipt_image.get("image"):
            parsed = self._parse_receipt_json(receipt_image["image"])
            # Enrich store receipt items with catalog product details
            if parsed.get("items") and receipt.get("receiptSource") != "ONLINE":
                try:
                    settings = self.load_settings()
                    parsed["items"] = await self._resolve_receipt_products(
                        parsed["items"], settings
                    )
                except Exception as e:
                    log.warning("Receipt product enrichment failed: %s", e)
            result.update(parsed)

        return result

    @staticmethod
    def _parse_receipt_json(raw_json: str) -> Dict[str, Any]:
        """Parse the print-layout JSON from a digital receipt into structured data."""
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            return {"items": [], "parseError": "Invalid receipt JSON"}

        text_objects = []
        try:
            sections = data["documents"][0]["documents"][0]["printSections"]
            for section in sections:
                for obj in section.get("textObjects", []):
                    for line in obj.get("textLines", []):
                        texts = [t.get("text", "") for t in line.get("texts", [])]
                        text_objects.append(texts)
        except (KeyError, IndexError, TypeError):
            return {"items": [], "parseError": "Unexpected receipt structure"}

        items = []
        total = None
        payment_method = None
        vat_lines = []
        item_count = None

        i = 0
        in_items = False
        while i < len(text_objects):
            texts = text_objects[i]
            joined = " ".join(t.strip() for t in texts if t.strip())

            # Detect the items section header
            if "OMSCHRIJVING" in joined and "BEDRAG" in joined:
                in_items = True
                i += 1
                # Skip separator after header
                if i < len(text_objects):
                    j2 = "".join(text_objects[i])
                    if j2.startswith("=") or j2.startswith("-"):
                        i += 1
                continue

            # End of items section
            if in_items and joined.startswith("Totaal"):
                in_items = False
                # Extract total from the same line
                for t in texts:
                    val = t.strip().replace(",", ".")
                    try:
                        total = float(val)
                    except ValueError:
                        pass
                i += 1
                continue

            # Parse item lines
            if in_items:
                first = texts[0].strip() if texts else ""

                # Skip separator lines
                if first.startswith("=") or first.startswith("-") or not first:
                    i += 1
                    continue

                # Quantity line: "  2 X 0,94"
                qty_match = re.match(r"^\s*(\d+)\s*[Xx]\s*(\d+[,.]\d+)", first)
                if qty_match and items:
                    qty = int(qty_match.group(1))
                    unit_price_str = qty_match.group(2).replace(",", ".")
                    unit_price = float(unit_price_str)
                    items[-1]["quantity"] = qty
                    items[-1]["unitPrice"] = unit_price
                    # Get line total from last text
                    for t in reversed(texts):
                        val = t.strip().replace(",", ".")
                        try:
                            items[-1]["price"] = float(val)
                            break
                        except ValueError:
                            pass
                    i += 1
                    continue

                # Regular product line
                price_val = None
                for t in reversed(texts):
                    val = t.strip().replace(",", ".")
                    try:
                        price_val = float(val)
                        break
                    except ValueError:
                        pass

                # Check for promo flag (P in second text field)
                is_promo = len(texts) > 1 and texts[1].strip() == "P"

                item = {
                    "name": first.strip(),
                    "price": price_val,
                    "quantity": 1,
                    "unitPrice": price_val,
                    "isPromo": is_promo,
                    "isDeposit": first.strip().upper() == "STATIEGELD",
                }
                items.append(item)
                i += 1
                continue

            # Payment method
            if joined.startswith("Betaald"):
                i += 1
                if i < len(text_objects):
                    pay_texts = text_objects[i]
                    payment_method = pay_texts[0].strip() if pay_texts else None
                i += 1
                continue

            # VAT lines
            if joined.startswith("BTW%") or "Bedrag excl" in joined:
                # Skip the header row
                i += 1
                # Parse VAT data rows
                while i < len(text_objects):
                    vt = text_objects[i]
                    vj = " ".join(t.strip() for t in vt if t.strip())
                    if vj.startswith("-") or vj.startswith("=") or not vj:
                        break
                    if "%" in vj or vj.startswith("BTW Totaal"):
                        parts = [t.strip() for t in vt if t.strip()]
                        vat_lines.append(parts)
                    i += 1
                continue

            # Item count
            count_match = re.match(r"Aantal artikelen.*?:\s*(\d+)", joined)
            if count_match:
                item_count = int(count_match.group(1))
                i += 1
                continue

            i += 1

        # Separate product items and deposit items
        products = [it for it in items if not it["isDeposit"]]
        deposits = [it for it in items if it["isDeposit"]]

        # Build VAT summary
        vat_summary = []
        for parts in vat_lines:
            if len(parts) >= 3 and "Totaal" not in parts[0]:
                vat_summary.append({
                    "rate": parts[0],
                    "amountExcl": parts[1] if len(parts) > 1 else None,
                    "vatAmount": parts[2] if len(parts) > 2 else None,
                })

        return {
            "items": products,
            "deposits": deposits,
            "total": total,
            "paymentMethod": payment_method,
            "vatSummary": vat_summary,
            "itemCount": item_count,
        }

    # ── Product lookup ────────────────────────────────────────────────

    async def search_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        query = """
        query productDetail($sku: String!) {
          product(sku: $sku) {
            id
            sku
            brand
            brandURL
            ean
            rootCategory
            categories {
              name
              path
              id
              __typename
            }
            subtitle
            title
            image
            canonicalUrl
            description
            storage
            recycling
            ingredients
            retailSet
            isMedicine
            preparationAndUsage
            isExcludedForCustomer
            replacementProduct {
              link
              __typename
            }
            thumbnails {
              image
              type
              __typename
            }
            images {
              image
              type
              __typename
            }
            additionalImages {
              image
              type
              __typename
            }
            productAllergens {
              mayContain
              contains
              __typename
            }
            nutritionsTable {
              columns
              rows
              __typename
            }
            nutriScore {
              value
              url
              __typename
            }
            availability {
              availabilityNote
              label
              isAvailable
              availability
              stockLimit
              reason
              delistDate {
                iso
                __typename
              }
              __typename
            }
            link
            price {
              price
              promoPrice
              pricePerUnit {
                price
                unit
                __typename
              }
              __typename
            }
            quantityDetails {
              maxAmount
              minAmount
              stepAmount
              defaultAmount
              __typename
            }
            primaryProductBadges {
              alt
              image
              __typename
            }
            secondaryProductBadges {
              alt
              image
              __typename
            }
            promotions {
              id
              isKiesAndMix
              tags {
                text
                inverse
                __typename
              }
              group
              image
              url
              durationTexts {
                title
                description
                shortTitle
                __typename
              }
              primaryBadges {
                alt
                image
                __typename
              }
              start {
                date
                dayShort
                monthShort
                __typename
              }
              end {
                date
                dayShort
                monthShort
                __typename
              }
              volumeDiscounts {
                discount
                volume
                __typename
              }
              maxPromotionQuantity
              __typename
            }
            manufacturer {
              description
              address
              phone
              website
              __typename
            }
            alcoholByVolume
            nutritionHealthClaims
            additives
            mandatoryInformation
            regulatedProductName
            safety
            safetyWarning
            origin
            fishCatchArea
            fishOriginFreeText
            fishPlaceOfProvenance
            placeOfRearing
            placeOfSlaughter
            placeOfBirth
            customerAllergies {
              showProductContainsMatchingAllergiesPrompt
              showConfigureDietaryPreferencesPrompt
              long
              short
              prompt {
                text
                title
                action
                __typename
              }
              __typename
            }
            sponsored
            drainedWeight
            characteristics {
              freshness {
                name
                value
                url
                __typename
              }
              logo {
                name
                value
                url
                __typename
              }
              tags {
                url
                name
                value
                __typename
              }
              __typename
            }
            __typename
          }
        }
        """
        return (await self.graphql_request(query, {"sku": sku})).get("product")

    async def barcode_lookup(self, barcode: str) -> Optional[Dict[str, Any]]:
        """Look up a product by EAN barcode, with OpenFoodFacts fallback."""
        settings = self.load_settings()
        
        # Check cache first (if enabled)
        if settings.get("useBarcodeCache", True):
            cache = self._load_cache()
            if barcode in cache:
                return cache[barcode]
        else:
            cache = {}

        normalized = re.sub(r"\D", "", barcode)
        candidates = [normalized, f"0{normalized}"]

        headers = {
            **self.headers,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
        }
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=10.0)
        ) as c:
            resp = await c.get(
                SEARCH_ENDPOINT,
                params={"searchType": "keyword", "searchTerms": barcode},
                headers=headers,
                cookies=self.cookies,
            )
        html = resp.text

        nuxt = re.search(
            r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
        )
        sku = title = None
        if nuxt:
            for pat in candidates:
                m = re.search(
                    rf'"([A-Z0-9]{{6,}})","[^"]*","([^"]+)","[^"]*{pat}[^"]*"',
                    nuxt.group(1),
                )
                if m:
                    sku, title = m.group(1).strip(), m.group(2).strip()
                    break

        if not sku:
            m = re.search(r"/producten/[^\"']+-([A-Z0-9]{6,})", html)
            if m:
                sku = m.group(1).strip()

        if not sku:
            # Try OpenFoodFacts fallback if enabled
            if settings.get("useOpenFoodFactsFallback", True):
                log.info(f"Barcode {barcode} not found in Jumbo, trying OpenFoodFacts...")
                result = await self._openfoodfacts_fallback(barcode)
                if result:
                    if settings.get("useBarcodeCache", True):
                        cache[barcode] = result
                        self._save_cache(cache)
                    return result
            return None

        product = await self.search_by_sku(sku)
        if not product:
            # Product not found, try OpenFoodFacts fallback
            if settings.get("useOpenFoodFactsFallback", True):
                log.info(f"SKU {sku} not found, trying OpenFoodFacts for barcode {barcode}...")
                result = await self._openfoodfacts_fallback(barcode)
                if result:
                    if settings.get("useBarcodeCache", True):
                        cache[barcode] = result
                        self._save_cache(cache)
                    return result
            return None

        ean = product.get("ean", "")
        if ean != barcode and ean != normalized:
            # EAN mismatch, try OpenFoodFacts fallback
            if settings.get("useOpenFoodFactsFallback", True):
                log.info(f"EAN mismatch (got {ean}, expected {barcode}), trying OpenFoodFacts...")
                result = await self._openfoodfacts_fallback(barcode)
                if result:
                    if settings.get("useBarcodeCache", True):
                        cache[barcode] = result
                        self._save_cache(cache)
                    return result
            return None

        result = {
            "sku": sku,
            "title": product.get("title", title or ""),
            "ean": barcode,
            "brand": product.get("brand"),
            "image": product.get("image"),
            "price": product.get("price", {}),
            "availability": product.get("availability", {}),
            "verified": True,
        }
        if settings.get("useBarcodeCache", True):
            cache[barcode] = result
            self._save_cache(cache)
        return result

    async def _openfoodfacts_fallback(self, barcode: str) -> Optional[Dict[str, Any]]:
        """Query OpenFoodFacts to get product name, then search Jumbo catalog with EAN matching."""
        try:
            log.info(f"Barcode {barcode}: Querying OpenFoodFacts...")
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.get(
                    f"https://world.openfoodfacts.net/api/v2/product/{barcode}",
                    headers={"User-Agent": "Jumbo-API/2.6.0"}
                )
                if resp.status_code != 200:
                    log.info(f"OpenFoodFacts: HTTP {resp.status_code} for {barcode}")
                    return None
                
                data = resp.json()
                if data.get("status") != 1:
                    log.info(f"OpenFoodFacts: Product not found for {barcode}")
                    return None
                
                product_off = data.get("product", {})
                product_name = product_off.get("product_name") or product_off.get("product_name_nl")
                
                if not product_name:
                    log.info(f"OpenFoodFacts: No product name found for {barcode}")
                    return None
                
                # Build search query based on settings
                settings = self.load_settings()
                search_parts = []
                
                # Add brand if enabled
                if settings.get("useBrandInSearch", False):
                    brand = product_off.get("brands", "")
                    if brand:
                        search_parts.append(brand.split(",")[0].strip())  # Use first brand
                
                # Add product name
                search_parts.append(product_name)
                
                # Add quantity/volume if enabled
                quantity = product_off.get("quantity", "")
                if settings.get("useQuantityInSearch", True) and quantity:
                    search_parts.append(quantity)
                
                search_query = " ".join(search_parts)
                
                if quantity:
                    log.info(f"OpenFoodFacts: Found '{product_name}' (quantity: {quantity}) for {barcode}")
                else:
                    log.info(f"OpenFoodFacts: Found '{product_name}' for {barcode}")
                log.info(f"Search query: '{search_query}'")
                
                # Search Jumbo catalog (skip receipt name cleaning for OpenFoodFacts queries)
                sku_candidates = await self._search_product_skus(search_query, clean_for_receipt=False)
                
                if not sku_candidates:
                    log.info(f"No Jumbo products found matching '{search_query}'")
                    return None
                
                # Fetch details for multiple candidates to find EAN match
                settings = self.load_settings()
                max_candidates = settings.get("maxProductCandidates", 10)
                log.info(f"Checking up to {max_candidates} of {len(sku_candidates)} candidates for EAN match...")
                best_match = None
                best_sku = None
                best_score = 0
                
                for slug, sku in sku_candidates[:max_candidates]:
                    product = await self.search_by_sku(sku)
                    if not product:
                        continue
                    
                    product_ean = product.get("ean", "")
                    if not product_ean:
                        continue
                    
                    # Calculate EAN similarity score
                    score = self._calculate_ean_similarity(barcode, product_ean)
                    
                    log.info(f"  {sku}: EAN={product_ean}, score={score}")
                    
                    if score > best_score:
                        best_score = score
                        best_match = product
                        best_sku = sku  # Preserve SKU from candidates
                
                # Log best match found
                if best_match:
                    log.info(f"  ✓ Best match: {best_sku} with score {best_score}")
                
                if not best_match:
                    log.info(f"No EAN matches found in candidates")
                    # Fall back to first result if no good EAN match
                    slug, sku = sku_candidates[0]
                    best_match = await self.search_by_sku(sku)
                    best_sku = sku
                    best_score = 0
                
                if not best_match:
                    return None
                
                log.info(f"Selected product: {best_sku} with EAN similarity score {best_score}")
                
                # Return with indication it's from OpenFoodFacts
                return {
                    "sku": best_sku,
                    "title": best_match.get("title"),
                    "ean": best_match.get("ean"),  # Actual EAN from Jumbo
                    "scannedBarcode": barcode,  # Original scanned barcode
                    "brand": best_match.get("brand"),
                    "image": best_match.get("image"),
                    "price": best_match.get("price", {}),
                    "availability": best_match.get("availability", {}),
                    "verified": best_score >= 90,  # High confidence if strong EAN match
                    "matchSource": "OpenFoodFacts",
                    "matchedName": product_name,
                    "eanMatchScore": best_score,
                }
        except Exception as e:
            log.warning(f"OpenFoodFacts fallback failed for {barcode}: {e}")
            return None
    
    def _calculate_ean_similarity(self, barcode1: str, barcode2: str) -> int:
        """Calculate similarity score between two EAN codes (0-100)."""
        if not barcode1 or not barcode2:
            return 0
        
        # Exact match
        if barcode1 == barcode2:
            return 100
        
        # Normalize (remove non-digits)
        b1 = re.sub(r"\D", "", str(barcode1))
        b2 = re.sub(r"\D", "", str(barcode2))
        
        if b1 == b2:
            return 100
        
        # Check if one is a zero-padded version of the other
        if b1 == f"0{b2}" or b2 == f"0{b1}":
            return 95
        
        # Count matching prefix digits (8718452829xxx pattern)
        min_len = min(len(b1), len(b2))
        matching_digits = 0
        for i in range(min_len):
            if b1[i] == b2[i]:
                matching_digits += 1
            else:
                break
        
        # More granular scoring - each additional matching digit increases score
        # This ensures 11 matching digits scores higher than 10, etc.
        settings = self.load_settings()
        
        if matching_digits >= 12:
            return 95
        elif matching_digits == 11:
            return 92
        elif matching_digits == 10:
            return settings.get("eanScore10Plus", 90)
        elif matching_digits >= 8:
            return settings.get("eanScore8Plus", 70)
        elif matching_digits >= 6:
            return settings.get("eanScore6Plus", 50)
        elif matching_digits >= 4:
            return settings.get("eanScore4Plus", 30)
        else:
            return 10

    # ── Receipt product matching ──────────────────────────────────────

    # Dutch receipt abbreviation → expansion mapping
    _RECEIPT_ABBREVS = [
        (r"\bJUM\.", "jumbo "),
        (r"\bGESN\.?(?=\s|$)", "gesneden"),
        (r"\bGEM\.?(?=\s|$)", "gemengd"),
        (r"\bRASP\b", "geraspte"),
        (r"\bCHAMP\b", "champignons"),
        (r"\bA\.ANDERS\b", "aardappel anders"),
        (r"\bCC\b", "con carne"),
        (r"\bSPAGH\.?\b", "spaghetti"),
        (r"\bMAC\.?\b", "macaroni"),
        (r"\bGEHAKTBAL\.?\b", "gehaktballen"),
        (r"\bZILVERVLIESR\.?\b", "zilvervliesrijst"),
        (r"\bWITTER\.?\b", "witte rijst"),
        (r"\bAARDB\.?\b", "aardbeien"),
        (r"\bSINAASAPP\.?\b", "sinaasappel"),
        (r"\bTOMAT\.?\b", "tomaten"),
        (r"\bKIPFIL\.?\b", "kipfilet"),
        (r"\bDROGH\.?\b", "droghe"),
        (r"\bMH\b", ""),
        (r"\b6PK\b", ""),
        (r"\b4PK\b", ""),
        (r"\b12PK\b", ""),
    ]

    # Regex to extract weight/volume from receipt name
    _SIZE_RE = re.compile(
        r"(\d+[,.]\d+|\d+)\s*(KG|G|GR|ML|L|CL)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def _clean_receipt_name(name: str) -> str:
        """Expand abbreviated receipt product name into searchable terms."""
        s = name.strip()
        for pat, repl in JumboClient._RECEIPT_ABBREVS:
            s = re.sub(pat, repl, s, flags=re.IGNORECASE)
        # Ensure space between letters and digits (from abbreviation expansion)
        s = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", s)
        # Strip trailing size tokens (e.g. "250", "1KG", "1,5L", "20%")
        s = re.sub(r"\b\d+[,.]\d+\s*(L|KG|G|ML)\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\b\d+\s*(G|ML|L|KG|PK|PAK|ST|STK|CL|GR)\b", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\b\d+%\b", "", s)
        # Collapse whitespace
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def _extract_size_ml(text: str) -> float | None:
        """Extract weight/volume from text and normalise to millilitres or grams."""
        m = JumboClient._SIZE_RE.search(text)
        if not m:
            return None
        value = float(m.group(1).replace(",", "."))
        unit = m.group(2).upper()
        multipliers = {"G": 1, "GR": 1, "ML": 1, "CL": 10, "KG": 1000, "L": 1000}
        return value * multipliers.get(unit, 1)

    @staticmethod
    def _name_words(text: str) -> set[str]:
        """Extract meaningful words from a product name for comparison."""
        stop = {"jumbo", "de", "het", "een", "van", "voor", "met", "en", "of", "in"}
        words = set()
        for w in re.findall(r"[a-záàâäéèêëíìîïóòôöúùûüýñç]+", text.lower()):
            if len(w) >= 2 and w not in stop:
                words.add(w)
        return words

    @staticmethod
    def _compute_confidence(
        receipt_name: str,
        receipt_price_cents: int,
        product: dict,
        settings: dict,
    ) -> int:
        """Compute 0-100 confidence score for a receipt name ↔ catalog product match.

        Breakdown (configurable via settings):
        - Price match:   0-{priceMatchWeight} points (default 40)
        - Weight/volume: 0-{weightMatchWeight} points (default 30)
        - Name overlap:  0-{nameMatchWeight} points (default 30)
        """
        score = 0.0

        price_info = product.get("price", {})
        price_cents = price_info.get("price", 0)
        promo_cents = price_info.get("promoPrice")
        product_title = product.get("title", "")
        product_subtitle = product.get("subtitle", "")
        full_text = f"{product_title} {product_subtitle}"

        # Get configurable weights
        max_price_score = settings.get("priceMatchWeight", 40)
        max_weight_score = settings.get("weightMatchWeight", 30)
        max_name_score = settings.get("nameMatchWeight", 30)

        # ── Price score ──────────────────────────────
        if settings.get("usePriceMatching", True) and receipt_price_cents > 0:
            best_diff = abs(price_cents - receipt_price_cents)
            if promo_cents:
                best_diff = min(best_diff, abs(promo_cents - receipt_price_cents))
            pct_diff = best_diff / max(receipt_price_cents, 1) * 100

            if best_diff == 0:
                score += max_price_score
            elif pct_diff <= 5:
                score += max_price_score * 0.8
            elif pct_diff <= 10:
                score += max_price_score * 0.625
            elif pct_diff <= 20:
                score += max_price_score * 0.375
            elif pct_diff <= 30:
                score += max_price_score * 0.25
            elif pct_diff <= 50:
                score += max_price_score * 0.125
            # >50% difference → 0 points

        # ── Weight/volume score ─────────────────────
        if settings.get("useWeightMatching", True):
            receipt_size = JumboClient._extract_size_ml(receipt_name)
            product_size = JumboClient._extract_size_ml(full_text)

            if receipt_size is not None and product_size is not None:
                size_ratio = min(receipt_size, product_size) / max(receipt_size, product_size) if max(receipt_size, product_size) > 0 else 0
                if size_ratio >= 0.99:
                    score += max_weight_score
                elif size_ratio >= 0.9:
                    score += max_weight_score * 0.67
                elif size_ratio >= 0.7:
                    score += max_weight_score * 0.33
                # Big mismatch → 0
            elif receipt_size is None and product_size is None:
                score += max_weight_score * 0.5  # Neither has size info – neutral
            # One has it but other doesn't → 0 (mild penalty via no points)

        # ── Name overlap score ──────────────────────
        if settings.get("useNameMatching", True):
            receipt_words = JumboClient._name_words(receipt_name)
            product_words = JumboClient._name_words(full_text)
            if receipt_words and product_words:
                overlap = receipt_words & product_words
                # Weight by overlap relative to receipt words (what we're trying to match)
                ratio = len(overlap) / len(receipt_words) if receipt_words else 0
                score += round(ratio * max_name_score)

        return min(100, max(0, round(score)))

    async def _search_product_skus(self, name: str, clean_for_receipt: bool = True) -> list[tuple[str, str]]:
        """Search Jumbo website by product name, return list of (slug, sku) tuples.
        
        Args:
            name: Product name to search for
            clean_for_receipt: If True, apply receipt name cleaning (strips sizes, expands abbreviations).
                              Set False for OpenFoodFacts queries to preserve size information.
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "nl-NL,nl;q=0.9",
        }
        timeout = httpx.Timeout(15.0, connect=10.0)

        # Build search attempts based on context
        raw = name.strip()
        attempts = [raw]  # Always try raw query first
        
        # For receipt queries, also try cleaned version
        if clean_for_receipt:
            cleaned = self._clean_receipt_name(name)
            if cleaned.lower() != raw.lower():
                attempts.append(cleaned)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            for attempt in attempts:
                resp = await c.get(
                    SEARCH_ENDPOINT,
                    params={"searchType": "keyword", "searchTerms": attempt},
                    headers=headers,
                    cookies=self.cookies,
                )
                # Extract unique SKUs from product links
                links = re.findall(r'href="/producten/([^"]+?)-(\d{3,}[A-Z]{2,})"', resp.text)
                seen: set[str] = set()
                unique: list[tuple[str, str]] = []
                for slug, sku in links:
                    if sku not in seen:
                        seen.add(sku)
                        unique.append((slug, sku))
                if unique:
                    return unique[:8]  # top 8 candidates

        return []

    async def _batch_fetch_products(self, skus: list[str]) -> dict[str, dict]:
        """Fetch basic product info for multiple SKUs in one GraphQL call."""
        if not skus:
            return {}
        query = """
        query Products($skus: [String!]!) {
          products(skus: $skus) {
            sku
            title
            subtitle
            image
            brand
            link
            price {
              price
              promoPrice
              pricePerUnit { price unit }
            }
          }
        }
        """
        try:
            data = await self.graphql_request(query, {"skus": skus})
            return {p["sku"]: p for p in data.get("products", [])}
        except Exception as e:
            log.warning("Batch product fetch failed: %s", e)
            return {}

    async def _resolve_receipt_products(
        self, items: list[dict], settings: dict | None = None,
    ) -> list[dict]:
        """Enrich parsed receipt items with catalog product details (SKU, image, brand, etc.)."""
        if not items:
            return items

        settings = settings or self.load_settings()

        if not settings.get("productMatchingEnabled", True):
            return items

        threshold = settings.get("confidenceThreshold", 50)
        if settings.get("strictMatching", False):
            threshold = max(threshold, 70)

        # Load receipt SKU cache
        cache = self._load_receipt_sku_cache()

        # Phase 1: Identify which items need searching
        items_to_search: list[tuple[int, str]] = []  # (index, name)
        cached_skus: dict[int, tuple[str, int]] = {}  # index -> (sku, confidence)

        for idx, item in enumerate(items):
            name = item.get("name", "").strip()
            if not name or item.get("isDeposit"):
                continue
            cache_key = name.upper()
            cached = cache.get(cache_key)
            if cached:
                # Cache stores {"sku": ..., "confidence": ...}
                if isinstance(cached, dict):
                    cached_skus[idx] = (cached["sku"], cached.get("confidence", 50))
                else:
                    # Legacy cache entry (just a sku string)
                    cached_skus[idx] = (cached, 50)
            else:
                items_to_search.append((idx, name))

        # Phase 2: Search for unknown products (HTML scrape)
        all_candidate_skus: set[str] = set()
        candidates_per_item: dict[int, list[tuple[str, str]]] = {}

        for idx, name in items_to_search:
            try:
                results = await self._search_product_skus(name)
                candidates_per_item[idx] = results
                for _, sku in results:
                    all_candidate_skus.add(sku)
            except Exception as e:
                log.warning("Search failed for '%s': %s", name, e)

        # Phase 3: Batch fetch all candidate + cached product details
        cached_sku_set = {sku for sku, _ in cached_skus.values()}
        all_skus = list(all_candidate_skus | cached_sku_set)
        products_by_sku = await self._batch_fetch_products(all_skus) if all_skus else {}

        # Phase 4: Score each candidate and pick best
        for idx, name in items_to_search:
            candidates = candidates_per_item.get(idx, [])
            if not candidates:
                continue

            target_cents = round(
                (items[idx].get("unitPrice") or items[idx].get("price") or 0) * 100
            )
            best_sku = None
            best_score = -1

            for _, sku in candidates:
                p = products_by_sku.get(sku)
                if not p:
                    continue
                conf = self._compute_confidence(name, target_cents, p, settings)
                if conf > best_score:
                    best_score = conf
                    best_sku = sku

            if best_sku and best_score >= 0:
                cache_key = name.upper()
                cache[cache_key] = {"sku": best_sku, "confidence": best_score}
                cached_skus[idx] = (best_sku, best_score)

        # Phase 5: Enrich items with product details (only if above threshold)
        for idx, item in enumerate(items):
            entry = cached_skus.get(idx)
            if not entry:
                continue
            sku, confidence = entry
            item["matchConfidence"] = confidence

            if confidence < threshold:
                log.info(
                    "Skipping low-confidence match: '%s' → %s (score=%d, threshold=%d)",
                    item.get("name"), sku, confidence, threshold,
                )
                continue

            p = products_by_sku.get(sku)
            if p:
                item["sku"] = sku
                item["fullTitle"] = p.get("title")
                item["subtitle"] = p.get("subtitle")
                item["image"] = p.get("image")
                item["brand"] = p.get("brand")
                item["link"] = p.get("link")
                item["catalogPrice"] = p.get("price")

        # Save updated cache
        self._save_receipt_sku_cache(cache)
        return items

    # ── Settings ──────────────────────────────────────────────────────

    @staticmethod
    def load_settings() -> dict:
        """Load user settings from file, with defaults."""
        settings = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                saved = json.loads(SETTINGS_FILE.read_text())
                settings.update(saved)
            except Exception:
                pass
        return settings

    @staticmethod
    def save_settings(settings: dict) -> dict:
        """Save user settings to file and return the merged result."""
        merged = dict(DEFAULT_SETTINGS)
        merged.update(settings)
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(merged, indent=2))
        return merged

    @staticmethod
    def clear_receipt_sku_cache():
        """Delete the receipt→SKU cache so all items get re-matched."""
        if RECEIPT_SKU_CACHE.exists():
            RECEIPT_SKU_CACHE.unlink()

    @staticmethod
    def _load_receipt_sku_cache() -> dict[str, Any]:
        if RECEIPT_SKU_CACHE.exists():
            try:
                return json.loads(RECEIPT_SKU_CACHE.read_text())
            except Exception:
                return {}
        return {}

    @staticmethod
    def _save_receipt_sku_cache(cache: dict[str, Any]):
        RECEIPT_SKU_CACHE.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT_SKU_CACHE.write_text(json.dumps(cache, indent=2))

    # ── Internal helpers ──────────────────────────────────────────────

    def _create_driver(self) -> webdriver.Chrome:
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument(f"user-agent={USER_AGENT}")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_experimental_option(
            "prefs",
            {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
            },
        )

        path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
        if os.path.exists(path):
            svc = Service(path)
        else:
            from webdriver_manager.chrome import ChromeDriverManager

            svc = Service(ChromeDriverManager().install())

        return webdriver.Chrome(service=svc, options=opts)

    def _perform_login(self, driver: webdriver.Chrome, user: str, pw: str):
        log.info("Navigating to login page")
        driver.get("https://www.jumbo.com/account/inloggen")
        time.sleep(1.5)

        log.info("Entering credentials")
        el = driver.find_element(By.ID, "username")
        el.clear()
        el.send_keys(user)
        time.sleep(0.2)

        el = driver.find_element(By.ID, "password")
        el.clear()
        el.send_keys(pw)
        time.sleep(0.3)

        log.info("Submitting login form")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(2.5)

        driver.get("https://www.jumbo.com")
        time.sleep(0.8)
        driver.get("https://www.jumbo.com/mijn/account")
        time.sleep(1)

    def _capture_cookies(self, driver: webdriver.Chrome) -> Dict[str, str]:
        raw = driver.get_cookies()
        log.info("Browser returned %d cookies", len(raw))

        found: Dict[str, str] = {}
        all_target = REQUIRED_COOKIES + OPTIONAL_COOKIES
        for name in all_target:
            c = next((x for x in raw if x["name"] == name), None)
            if c:
                self.cookies[name] = c["value"]
                found[name] = c["value"]
                log.info("Captured cookie: %s", name)
            elif name in REQUIRED_COOKIES:
                log.warning("Missing required cookie: %s", name)
            else:
                log.debug("Optional cookie not present: %s", name)
        
        log.info("Current cookies in memory: %s", list(self.cookies.keys()))
        return found

    def _load_cookies_from_file(self):
        """Load saved cookies from file on startup."""
        if COOKIE_FILE.exists():
            try:
                saved = json.loads(COOKIE_FILE.read_text())
                self.cookies = saved.get("cookies", {})
                if self.cookies:
                    log.info("Loaded %d saved cookies from file", len(self.cookies))
            except Exception as exc:
                log.warning("Failed to load cookies: %s", exc)

    def _save_cookies_to_file(self):
        """Save current cookies to file for persistence."""
        try:
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {"cookies": self.cookies, "saved_at": datetime.now().isoformat()}
            COOKIE_FILE.write_text(json.dumps(data, indent=2))
            log.info("Saved cookies to file")
        except Exception as exc:
            log.warning("Failed to save cookies: %s", exc)

    def _load_credentials(self):
        """Load saved credentials from file or environment variables."""
        # Try environment variables first
        self.username = os.getenv("JUMBO_USERNAME")
        self.password = os.getenv("JUMBO_PASSWORD")
        
        if self.username and self.password:
            log.info("Loaded credentials from environment variables")
            return
        
        # Try file if env vars not set
        if CREDS_FILE.exists():
            try:
                creds = json.loads(CREDS_FILE.read_text())
                self.username = creds.get("username")
                self.password = creds.get("password")
                if self.username and self.password:
                    log.info("Loaded credentials from file (for auto re-authentication)")
            except Exception as exc:
                log.warning("Failed to load credentials: %s", exc)

    def _save_credentials(self):
        """Save credentials to file for auto re-authentication."""
        if not self.username or not self.password:
            return
        try:
            CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "username": self.username,
                "password": self.password,
                "saved_at": datetime.now().isoformat()
            }
            CREDS_FILE.write_text(json.dumps(data, indent=2))
            log.info("Saved credentials to file")
        except Exception as exc:
            log.warning("Failed to save credentials: %s", exc)

    @staticmethod
    def _load_cache() -> Dict[str, Any]:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
        return {}

    @staticmethod
    def _save_cache(cache: Dict[str, Any]):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, indent=2))

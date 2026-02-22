# Jumbo API Documentation

> Programmatic access to your Jumbo.com shopping basket, lists (lijstjes), product search, and more.

## 🚀 Quick Start

### 1. Start the API Server

```bash
docker-compose up -d
```

The API will be available at `http://localhost:8000`

### 2. Authentication

**Option A: Automated Login**
```bash
curl -X POST http://localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"your@email.com","password":"yourpassword"}'
```

**Option B: Load Saved Cookies**
```bash
curl -X POST http://localhost:8000/api/cookies/load
```

### 3. Make Your First Request

```bash
# Get your basket contents
curl http://localhost:8000/api/basket

# Search for a product
curl "http://localhost:8000/api/products/search?sku=67649PAK"

# View your shopping lists
curl http://localhost:8000/api/lists
```

## 📚 Interactive Documentation

### Swagger UI
Access the interactive API explorer at:
```
http://localhost:8000/docs
```

**Features:**
- Try all endpoints directly in your browser
- See request/response schemas
- Auto-generated from OpenAPI specification
- No code required for testing

### Web Dashboard
Access the web interface at:
```
http://localhost:8000
```

## 🔐 Authentication

All protected endpoints require authentication. The API uses session cookies obtained from Jumbo.com.

### Authentication Status
```bash
GET /api/auth/status
```

**Response:**
```json
{
  "authenticated": true,
  "cookies_present": true
}
```

### Login Methods

#### 1. Automated Browser Login (Selenium)
```bash
POST /api/login
Content-Type: application/json

{
  "username": "your@email.com",
  "password": "yourpassword"
}
```

**Note:** Takes ~20 seconds as it launches a headless Chrome browser to authenticate.

#### 2. Load Saved Cookies
```bash
POST /api/cookies/load
```

Loads cookies from `data/jumbo-cookies.json`

#### 3. Save Cookies
```bash
POST /api/cookies/save
```

Saves current session cookies to `data/jumbo-cookies.json`

## 🛒 Basket Endpoints

### Get Basket
```bash
GET /api/basket
```

Returns the active basket with product details and prices.

**Response:**
```json
{
  "id": "697f34ed6614bd807a2d390b",
  "totalProductCount": 3,
  "type": "ECOMMERCE",
  "lines": [
    {
      "sku": "669608DS",
      "id": "6987d8f6b63ec70a2161d4e5",
      "quantity": 3.0,
      "details": {
        "sku": "669608DS",
        "title": "Ariel 3in1 PODS Original, Wasmiddel Capsules 15",
        "brand": "Ariel",
        "image": "https://www.jumbo.com/dam-images/...",
        "price": {
          "price": 1299,
          "promoPrice": null,
          "pricePerUnit": {
            "price": 87,
            "quantity": "1",
            "unit": "pieces"
          }
        }
      }
    }
  ]
}
```

### Add Product to Basket
```bash
POST /api/basket/add
Content-Type: application/json

{
  "sku": "67649PAK",
  "quantity": 2
}
```

**Parameters:**
- `sku` (string, required): Product SKU
- `quantity` (float, optional): Quantity to add (default: 1)

### Remove from Basket
```bash
POST /api/basket/remove
Content-Type: application/json

{
  "line_id": "6987d8f6b63ec70a2161d4e5"
}
```

**OR**

```json
{
  "sku": "67649PAK"
}
```

**Parameters:**
- `line_id` (string, optional): Basket line ID
- `sku` (string, optional): Product SKU (used to find line ID)

### Update Basket Item Quantity ✨ NEW
```bash
PATCH /api/basket/items/{line_id}
Content-Type: application/json

{
  "quantity": 5
}
```

**Parameters:**
- `line_id` (string, required): Basket line ID (path parameter)
- `quantity` (float, required): New quantity (minimum 0.1)

**Example:**
```bash
# Get basket to find line_id
curl http://localhost:8000/api/basket | jq '.lines[0].id'

# Update quantity
curl -X PATCH http://localhost:8000/api/basket/items/6987d8f6b63ec70a2161d4e5 \
  -H 'Content-Type: application/json' \
  -d '{"quantity": 5}'
```

## 📝 Shopping Lists (Lijstjes)

### Get All Lists
```bash
GET /api/lists
```

Returns all customer shopping lists and favorites.

**Response:**
```json
{
  "customerLists": {
    "total": 18,
    "items": [
      {
        "id": "67bcbf39e74268133cd61086",
        "title": "Gerechten",
        "productCount": 72,
        "products": [],
        "createdAt": "2024-12-24T18:00:00Z"
      }
    ]
  },
  "favouriteLists": {
    "total": 1,
    "items": []
  }
}
```

### Get List by ID
```bash
GET /api/lists/{list_id}
```

Returns a specific list with full product details.

**Example:**
```bash
curl http://localhost:8000/api/lists/67bcbf39e74268133cd61086
```

**Response:**
```json
{
  "id": "67bcbf39e74268133cd61086",
  "title": "Gerechten",
  "productCount": 72,
  "products": [
    {
      "sku": "67649PAK",
      "title": "Jumbo Verse Halfvolle Melk 2 L",
      "brand": "Jumbo",
      "image": "https://www.jumbo.com/dam-images/...",
      "price": {
        "price": 249,
        "pricePerUnit": {
          "price": 125,
          "quantity": "1",
          "unit": "liter"
        }
      }
    }
  ]
}
```

## 🔍 Product Search

### Search by SKU
```bash
GET /api/products/search?sku=67649PAK
```

**Response:**
```json
{
  "sku": "67649PAK",
  "title": "Jumbo Verse Halfvolle Melk 2 L",
  "subtitle": "Halfvolle Melk",
  "brand": "Jumbo",
  "image": "https://www.jumbo.com/dam-images/...",
  "link": "/producten/jumbo-verse-halfvolle-melk-2-l-67649PAK",
  "category": "Zuivel en eieren",
  "price": {
    "price": 249,
    "promoPrice": null,
    "pricePerUnit": {
      "price": 125,
      "quantity": "1",
      "unit": "liter"
    }
  }
}
```

### Search by Barcode
```bash
POST /api/products/barcode
Content-Type: application/json

{
  "barcode": "8718452044801"
}
```

Looks up products by EAN barcode. Uses a cache for faster repeated lookups.

## 📊 Utility Endpoints

### Health Check
```bash
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "authenticated": true,
  "timestamp": "2026-02-08T11:50:07.55654"
}
```

### Command History
```bash
GET /api/history?limit=10
```

Returns the last N commands executed (default: 20, max: 100).

**Response:**
```json
{
  "history": [
    {
      "timestamp": "2026-02-08T11:48:59.145813",
      "command": "Get List 67bcbf39e74268133cd61086",
      "status": "success",
      "details": {
        "title": "Gerechten",
        "products": 72
      }
    }
  ]
}
```

## 💡 Usage Examples

### Python
```python
import requests

BASE_URL = "http://localhost:8000"

# Login
response = requests.post(f"{BASE_URL}/api/login", json={
    "username": "your@email.com",
    "password": "yourpassword"
})

# Get basket
basket = requests.get(f"{BASE_URL}/api/basket").json()
print(f"Basket has {basket['totalProductCount']} items")

# Add product
requests.post(f"{BASE_URL}/api/basket/add", json={
    "sku": "67649PAK",
    "quantity": 2
})

# Update quantity
line_id = basket['lines'][0]['id']
requests.patch(f"{BASE_URL}/api/basket/items/{line_id}", json={
    "quantity": 5
})

# Get lists
lists = requests.get(f"{BASE_URL}/api/lists").json()
for lst in lists['customerLists']['items']:
    print(f"{lst['title']}: {lst['productCount']} products")
```

### JavaScript/Node.js
```javascript
const BASE_URL = "http://localhost:8000";

// Login
await fetch(`${BASE_URL}/api/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    username: "your@email.com",
    password: "yourpassword"
  })
});

// Get basket
const basket = await fetch(`${BASE_URL}/api/basket`).then(r => r.json());
console.log(`Basket has ${basket.totalProductCount} items`);

// Add product
await fetch(`${BASE_URL}/api/basket/add`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ sku: "67649PAK", quantity: 2 })
});

// Update quantity
const lineId = basket.lines[0].id;
await fetch(`${BASE_URL}/api/basket/items/${lineId}`, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ quantity: 5 })
});

// Get lists
const lists = await fetch(`${BASE_URL}/api/lists`).then(r => r.json());
lists.customerLists.items.forEach(list => {
  console.log(`${list.title}: ${list.productCount} products`);
});
```

### cURL
```bash
# Login
curl -X POST http://localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"your@email.com","password":"yourpassword"}'

# Get basket
curl http://localhost:8000/api/basket

# Add product
curl -X POST http://localhost:8000/api/basket/add \
  -H 'Content-Type: application/json' \
  -d '{"sku":"67649PAK","quantity":2}'

# Update quantity (get line_id from basket first)
curl -X PATCH http://localhost:8000/api/basket/items/6987d8f6b63ec70a2161d4e5 \
  -H 'Content-Type: application/json' \
  -d '{"quantity":5}'

# Get lists
curl http://localhost:8000/api/lists

# Get specific list
curl http://localhost:8000/api/lists/67bcbf39e74268133cd61086

# Search product
curl "http://localhost:8000/api/products/search?sku=67649PAK"

# Barcode lookup
curl -X POST http://localhost:8000/api/products/barcode \
  -H 'Content-Type: application/json' \
  -d '{"barcode":"8718452044801"}'
```

## 🏗️ Architecture

### Tech Stack
- **Backend:** Python 3.11 + FastAPI + Uvicorn
- **Authentication:** Selenium WebDriver (headless Chromium)
- **GraphQL Client:** httpx for async requests
- **Containerization:** Docker + Docker Compose
- **Frontend:** Vanilla JavaScript + HTML5 + CSS3

### GraphQL Integration
The API reverse-engineers Jumbo.com's internal GraphQL API:
- Endpoint: `https://www.jumbo.com/api/graphql`
- Authentication: Cookie-based sessions
- Client headers: `JUMBO_WEB-basket`, `JUMBO_WEB-list`

### Project Structure
```
jumbo/
├── app/
│   ├── main.py              # FastAPI application & endpoints
│   ├── jumbo_client.py      # GraphQL client & business logic
│   ├── templates/
│   │   └── index.html       # Web dashboard
│   ├── static/
│   │   ├── app.js           # Frontend JavaScript
│   │   └── style.css        # Dark theme styling
│   ├── Dockerfile
│   └── requirements.txt
├── data/
│   ├── jumbo-cookies.json   # Saved session cookies
│   └── barcode-cache.json   # Barcode lookup cache
├── docker-compose.yml
└── API_README.md            # This file
```

## 🔧 Configuration

### Environment Variables
```bash
# Optional: Set custom port
PORT=8000

# Optional: Enable debug mode
DEBUG=1
```

### Docker Compose
```yaml
version: '3.8'
services:
  jumbo-api:
    build: ./app
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - PORT=8000
```

## 🐛 Troubleshooting

### Authentication Issues
```bash
# Check auth status
curl http://localhost:8000/api/auth/status

# Try loading cookies
curl -X POST http://localhost:8000/api/cookies/load

# Re-authenticate
curl -X POST http://localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"your@email.com","password":"yourpassword"}'
```

### Container Issues
```bash
# View logs
docker-compose logs -f

# Restart container
docker-compose restart

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Common Errors

**"GraphQL Error: Variable ... is never used"**
- Fixed in latest version
- Ensure you're using the updated `jumbo_client.py`

**"Failed to load basket"**
- Check authentication status
- Verify cookies are valid
- Try re-authenticating

**"Product not found"**
- Verify SKU is correct
- Ensure you're authenticated
- Product may be unavailable

## 📈 Rate Limiting

Jumbo.com may rate-limit requests. Best practices:
- Use cookie persistence (avoid re-authenticating)
- Implement exponential backoff for retries
- Cache product lookups when possible
- Respect reasonable request intervals

## 🔒 Security Notes

- **Credentials:** Never commit credentials to version control
- **Cookies:** Store in `data/` which is in `.gitignore`
- **API Access:** Run behind reverse proxy in production
- **HTTPS:** Use SSL termination (nginx/Traefik) for production
- **Authentication:** Cookies are session-based and expire

## 📝 API Endpoint Summary

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/health` | Health check | ❌ |
| GET | `/api/auth/status` | Check authentication | ❌ |
| POST | `/api/login` | Automated login | ❌ |
| POST | `/api/cookies/load` | Load saved cookies | ❌ |
| POST | `/api/cookies/save` | Save session cookies | ✅ |
| GET | `/api/basket` | Get basket contents | ✅ |
| POST | `/api/basket/add` | Add product to basket | ✅ |
| POST | `/api/basket/remove` | Remove from basket | ✅ |
| PATCH | `/api/basket/items/{id}` | Update item quantity | ✅ |
| GET | `/api/lists` | Get all shopping lists | ✅ |
| GET | `/api/lists/{id}` | Get specific list | ✅ |
| GET | `/api/products/search` | Search by SKU | ✅ |
| POST | `/api/products/barcode` | Lookup by barcode | ✅ |
| GET | `/api/history` | Command history | ❌ |

## 🎯 Roadmap

- [ ] Add product recommendations
- [ ] Implement order placement
- [ ] Add delivery slot booking
- [ ] Support for promotional codes
- [ ] Price history tracking
- [ ] Shopping list templates
- [ ] Mobile app integration
- [ ] WebSocket support for real-time updates

## 📄 License

This project is for educational purposes. Jumbo.com's Terms of Service apply to API usage.

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📞 Support

- **Interactive Docs:** http://localhost:8000/docs
- **Web Dashboard:** http://localhost:8000
- **Issues:** GitHub Issues (if applicable)

---

**Built with ❤️ using FastAPI, Python, and Docker**

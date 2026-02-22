# Jumbo API

🛒 **Comprehensive REST API and modern web dashboard for the Jumbo.com grocery platform.**

Automates authentication via headless Chromium, manages your shopping basket, lists (lijstjes), order history, store receipts, and provides detailed product lookups by SKU or EAN barcode with **OpenFoodFacts fallback**.

---

## 🚀 Quick Start

```bash
docker compose up -d
```

- **Web Dashboard:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs (Interactive Swagger UI)
- **Complete API Guide:** [API_README.md](API_README.md)

---

## ✨ Features

### 🛒 Shopping Basket
- View your current basket with full product details
- Add/remove products by SKU
- Update quantities
- Real-time price calculations
- Promo price support

### 📝 Shopping Lists (Lijstjes)
- Access all your shopping lists
- View favorite lists and custom lists
- See product images, prices, and details
- Product count tracking

### 📦 Order Management
- View online order history
- Detailed order information with delivery dates
- Item-level details with images and pricing
- Track order status, substitutions, and unavailable items
- Support for home delivery and store pickup orders

### 🧾 Store Receipts
- View in-store and online receipt history
- Detailed receipt breakdown with VAT summaries
- Product matching and enrichment
- Loyalty points tracking (Jumbo Extra's)
- Payment method information
- Store location details

### 🔍 Product Search & Lookup
- Search products by SKU
- **Intelligent barcode lookup (EAN codes) with OpenFoodFacts fallback**
- **EAN similarity matching algorithm** - finds best product match when exact barcode not found
  - Configurable candidate count (5-50, default: 15)
  - Scores matches based on EAN prefix similarity (0-100)
  - Fully customizable scoring thresholds per digit count
  - Color-coded confidence indicators (green ≥90%, yellow <90%)
  - Shows both scanned barcode and matched product EAN
- **Smart OpenFoodFacts integration** with contextual search
  - Includes product size/volume in search (e.g., "Cola 1,5 l" vs "Cola")
  - Optional brand inclusion for brand-specific products
  - Finds single items vs multi-packs accurately
- **Optional barcode cache** - disable for always-fresh results
- Comprehensive product information:
  - Nutritional data & allergens
  - Multiple images (thumbnails & high-res)
  - Pricing with promotions
  - Brand, categories, descriptions
  - Availability & stock status
  - Manufacturer details & origin
  - Storage & preparation instructions

### 🔐 Authentication & Auto Re-login
- Automated Selenium-based browser login
- Cookie persistence across restarts
- Auto re-authentication when sessions expire
- **Web-based credential management in Settings**
- **Save credentials directly from the dashboard**
- Environment variable support for homelab deployments

### 🎨 Modern Web Dashboard
- Dark-themed, responsive UI
- Real-time basket updates
- Interactive product cards with images
- Modal dialogs for detailed views
- Toast notifications
- Command history tracking
- **Comprehensive Settings page with credential management**

### ⚙️ Product Matching Engine
- Intelligent receipt product enrichment
- Configurable confidence thresholds
- Price, weight, and name matching
- Caching for improved performance
- Manual cache clearing
- **OpenFoodFacts integration for unknown barcodes**

---

## 📚 Documentation

### Interactive API Explorer
Visit **http://localhost:8000/docs** for the full Swagger/OpenAPI documentation where you can:
- Try all endpoints directly in your browser
- See request/response schemas
- Test authentication flows
- No code required

### Comprehensive API Reference
See **[API_README.md](API_README.md)** for:
- Complete endpoint documentation
- Authentication guides
- Code examples in Python, JavaScript, and cURL
- Architecture overview
- Troubleshooting tips

---

## 🔐 Authentication Setup

The API supports three methods for persistent authentication:

### Option 1: Web Dashboard (Easiest)
1. Open http://localhost:8000
2. Go to **Settings** tab
3. Enter your credentials in the "Login Credentials" section
4. Click "Save Credentials"
5. Credentials are stored securely for auto re-authentication

### Option 2: Environment Variables (Recommended for Homelab)
Set credentials via environment variables in Portainer or docker-compose:

```yaml
environment:
  - JUMBO_USERNAME=your-email@example.com
  - JUMBO_PASSWORD=your-password
```

### Option 3: Manual Login
Login once via web dashboard:
- Click "Login" button in header
- Enter credentials
- Credentials auto-save for future sessions

**How it works:**
- Session cookies saved to `/app/data/session-cookies.json`
- Credentials saved to `/app/data/credentials.json` (or use env vars)
- Auto re-authentication triggers when cookies expire
- Seamless operation without manual intervention

---

## 🔧 Settings & Configuration

### Web Dashboard Settings
Access the Settings panel to configure all matching and lookup behavior:

#### 🔐 Login Credentials
- Save/update your Jumbo.com credentials
- View credential status
- Remove saved credentials
- Secure storage in Docker volume

#### 🔍 Barcode Lookup
- **OpenFoodFacts Fallback** - automatically query OpenFoodFacts when barcode not found in Jumbo
- **Max Product Candidates** - number of products to check (5-50, default: 15)
- **Include Size/Volume in Search** - add quantity to queries (e.g., "Cola 1,5 l" vs "Cola")
- **Include Brand in Search** - add brand name to queries (e.g., "Jumbo Cola" vs "Cola")

#### 🎯 EAN Matching Scores
Configure scoring thresholds for barcode similarity (0-100 points):
- **10+ Matching Digits** - high confidence matches (default: 90)
- **8-9 Matching Digits** - medium confidence (default: 70)
- **6-7 Matching Digits** - low confidence (default: 50)
- **4-5 Matching Digits** - very low confidence (default: 30)

#### 🧾 Receipt Product Matching
- **Enable/Disable Product Matching** - search catalog for receipt items
- **Strict Matching Mode** - only show high confidence matches (≥70%)
- **Confidence Threshold Slider** - minimum score required (0-100)

#### ⚖️ Matching Weights
Customize how much each factor contributes to match scores:
- **Price Weight** - points for price match (0-100, default: 40)
- **Weight/Volume Weight** - points for size match (0-100, default: 30)
- **Name Weight** - points for name similarity (0-100, default: 30)
- Enable/disable each criterion independently

#### 💾 Cache Settings
- **Enable/Disable Barcode Cache** - cache lookups or force fresh results
- **Clear Cache Button** - remove all cached matches for re-matching

All settings persist across container restarts and are applied immediately.

---

## 🔑 Quick API Examples

### Authentication
```bash
# Login
curl -X POST http://localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"your@email.com","password":"yourpassword"}'

# Check auth status
curl http://localhost:8000/api/auth/status
```

### Basket Operations
```bash
# Get basket
curl http://localhost:8000/api/basket

# Add product
curl -X POST http://localhost:8000/api/basket/add \
  -H 'Content-Type: application/json' \
  -d '{"sku":"67649PAK","quantity":2}'

# Update quantity
curl -X PATCH http://localhost:8000/api/basket/items/{line_id} \
  -H 'Content-Type: application/json' \
  -d '{"quantity":5}'

# Remove product
curl -X POST http://localhost:8000/api/basket/remove \
  -H 'Content-Type: application/json' \
  -d '{"line_id":"abc123"}'
```

### Shopping Lists
```bash
# Get all lists
curl http://localhost:8000/api/lists

# Get specific list details
curl http://localhost:8000/api/lists/{list_id}
```

### Orders & Receipts
```bash
# Get orders and receipts
curl "http://localhost:8000/api/orders?limit=10&page=0"

# Get order details
curl http://localhost:8000/api/orders/{order_id}

# Get receipt details
curl http://localhost:8000/api/receipts/{transaction_id}
```

### Product Search & Barcode Lookup
```bash
# Search by SKU
curl "http://localhost:8000/api/products/search?sku=67649PAK"

# Barcode lookup (with OpenFoodFacts fallback and EAN matching)
curl -X POST http://localhost:8000/api/products/barcode \
  -H 'Content-Type: application/json' \
  -d '{"barcode":"8718452829408"}'

# Response includes EAN matching details:
# {
#   "sku": "629682FLS",
#   "title": "Jumbo Cola Regular 1,5 L",
#   "ean": "8718452829422",
#   "scannedBarcode": "8718452829408",
#   "eanMatchScore": 92,
#   "verified": true,
#   "matchSource": "OpenFoodFacts",
#   "matchedName": "Cola"
# }
```

### Settings Management
```bash
# Get all settings
curl http://localhost:8000/api/settings

# Update settings
curl -X PUT http://localhost:8000/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"useOpenFoodFactsFallback":true,"confidenceThreshold":50}'

# Save credentials
curl -X PUT http://localhost:8000/api/settings/credentials \
  -H 'Content-Type: application/json' \
  -d '{"username":"your@email.com","password":"yourpassword"}'

# Remove credentials
curl -X PUT http://localhost:8000/api/settings/credentials \
  -H 'Content-Type: application/json' \
  -d '{"removeCredentials":true}'

# Clear match cache
curl -X POST http://localhost:8000/api/settings/clear-cache
```

**For more examples, see [API_README.md](API_README.md)**

---

## 🏗️ Project Structure

```
app/
  main.py              # FastAPI application & REST endpoints
  jumbo_client.py      # Jumbo GraphQL client + Selenium auth + OpenFoodFacts
  templates/
    index.html         # Web dashboard with settings management
  static/
    app.js            # Frontend JavaScript
    style.css         # Responsive dark theme
  Dockerfile
  requirements.txt
data/                  # Persistent data volume
  session-cookies.json # Saved session cookies
  credentials.json     # Encrypted credentials (optional)
  barcode-cache.json   # Product barcode cache
  settings.json        # User preferences
docker-compose.yml
API_README.md          # Complete API documentation
```

---

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)
```bash
docker-compose up -d
```

### Using Docker Run
```bash
docker run -d \
  --name jumbo-api \
  -p 8000:8000 \
  -v jumbo-data:/app/data \
  -e JUMBO_USERNAME=your@email.com \
  -e JUMBO_PASSWORD=yourpassword \
  vghoost360/jumbo:latest
```

### Pull Latest Version
```bash
docker pull vghoost360/jumbo:latest
# or specific version
docker pull vghoost360/jumbo:v2.6.0
```

### Volume Mounting
The container uses a persistent volume at `/app/data` for:
- Session cookies
- Credentials (encrypted)
- Product match cache
- Barcode lookup cache
- User settings

**Important:** Mount this volume to preserve authentication between container restarts.

---

## 🛠️ Tech Stack

- **Backend:** Python 3.11, FastAPI, Uvicorn
- **Authentication:** Selenium (headless Chromium)
- **HTTP Client:** httpx (async)
- **External API:** OpenFoodFacts API integration
- **Frontend:** Vanilla JavaScript, CSS Grid/Flexbox
- **Container:** Docker (`python:3.11-slim` + Chromium)

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JUMBO_USERNAME` | Your Jumbo.com email | None |
| `JUMBO_PASSWORD` | Your Jumbo.com password | None |
| `TZ` | Timezone | `Europe/Amsterdam` |

### Settings API
Configure behavior via `/api/settings` or the web dashboard:

**Receipt Matching:**
- `productMatchingEnabled` - Enable/disable receipt enrichment (default: true)
- `strictMatching` - Require higher confidence for matches (default: false)
- `confidenceThreshold` - Minimum confidence percentage 0-100 (default: 50)
- `usePriceMatching` - Include price in matching (default: true)
- `useWeightMatching` - Include weight in matching (default: true)
- `useNameMatching` - Include name similarity in matching (default: true)

**Barcode Lookup:**
- `useOpenFoodFactsFallback` - Query OpenFoodFacts when barcode not found (default: true)
- `maxProductCandidates` - Products to check for EAN match 5-50 (default: 15)
- `useQuantityInSearch` - Include size/volume in search queries (default: true)
- `useBrandInSearch` - Include brand in search queries (default: false)

**Matching Weights (0-100 points):**
- `priceMatchWeight` - Max points for price matches (default: 40)
- `weightMatchWeight` - Max points for weight/volume matches (default: 30)
- `nameMatchWeight` - Max points for name matches (default: 30)

**EAN Scoring Thresholds (0-100 points):**
- `eanScore10Plus` - Score for 10+ matching digits (default: 90)
- `eanScore8Plus` - Score for 8-9 matching digits (default: 70)
- `eanScore6Plus` - Score for 6-7 matching digits (default: 50)
- `eanScore4Plus` - Score for 4-5 matching digits (default: 30)

**Cache:**
- `useBarcodeCache` - Cache barcode lookups (default: true, disable for always-fresh results)

---

## 📊 Health Check

```bash
curl http://localhost:8000/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-02-22T17:43:00Z",
  "authenticated": true
}
```

---

## 🆕 Changelog

### v2.6.0 (2026-02-22)
**New Features:**
- 🌐 **OpenFoodFacts Integration** - Automatic fallback when barcode not found in Jumbo
  - Queries OpenFoodFacts API for product name and metadata
  - Smart search with size/volume inclusion (e.g., "Cola 1,5 l")
  - Optional brand inclusion for brand-specific searches
  - Configurable search behavior via settings
- 🎯 **Enhanced EAN Similarity Matching** - Intelligent product matching system
  - Configurable candidate count (5-50 products, default: 15)
  - Granular scoring: 12+ digits=95, 11 digits=92, 10 digits=90
  - User-adjustable score thresholds for all digit ranges
  - Returns both scanned barcode and matched product EAN
  - Color-coded confidence indicators in UI (green/yellow/red)
- ⚖️ **Fully Customizable Matching Weights** - Fine-tune matching algorithm
  - Adjust price matching weight (0-100 points, default: 40)
  - Adjust weight/volume matching (0-100 points, default: 30)
  - Adjust name matching weight (0-100 points, default: 30)
  - Enable/disable each criterion independently
- 💾 **Cache Control** - Optional caching for consistent results
  - Toggle barcode cache on/off via settings
  - Disable for always-fresh lookups
  - Clear cache button for manual reset
- 🎨 **Reorganized Settings UI** - Intuitive, logical organization
  - Grouped by function: Barcode, EAN Scores, Matching, Weights, Cache
  - All configurable options exposed and documented
  - Number inputs for precise value control
  - All settings persist across restarts
- 🔐 **Credential Management UI** - Save/update credentials directly from Settings
  - Visual credential status indicator
  - Secure credential storage in Docker volume
  - Remove credentials option

**Bug Fixes:**
- 🐛 Fixed critical JavaScript syntax errors preventing button clicks
- 🔧 Fixed maxProductCandidates not persisting (changed from slider to number input)
- 🎨 Fixed Settings page CSS (input field overlap)
- 🔍 Fixed SKU preservation in EAN matching results
- ✅ Fixed barcode lookup returning 6-pack instead of single bottle
  - Now correctly matches 629682FLS (1,5L bottle) with score 92
  - Instead of 629680PAK (6-pack) with score 90
  - Achieved by including product quantity in search queries

**Improvements:**
- 📝 Enhanced settings page with logical grouping and clear descriptions
- 🎯 More accurate barcode matching with contextual search
- 📊 Transparent, customizable confidence scoring system
- 🧹 Code cleanup and validation
- 📚 Comprehensive documentation updates
- 🔄 Consistent API output format across all lookups

### v2.5.1
- Receipt product enrichment
- Order detail views
- Shopping list support
- Product matching engine

---

## 🔒 Security Notes

- Credentials are stored in Docker volumes (not in image)
- `.dockerignore` excludes personal data from builds
- Session cookies managed securely
- No credentials in logs or version control
- Use environment variables for production deployments
- OpenFoodFacts queries use anonymous API access

---

## 🤝 Contributing

This project is for educational purposes. Contributions welcome!

---

## 📝 License

Educational use only. Jumbo.com's and OpenFoodFacts' Terms of Service apply to API usage.

---

## 🐛 Troubleshooting

### Buttons Not Working
- Hard refresh browser (Ctrl+Shift+R)
- Check browser console for JavaScript errors
- Verify container is running: `docker ps`

### Barcode Not Found
- Enable "OpenFoodFacts Fallback" in Settings
- Enable "Include Size/Volume in Search" for better single-item matching
- Check if product exists on OpenFoodFacts.org
- Try searching by product name instead

### Wrong Product Returned
- Adjust EAN matching scores in Settings → EAN Matching Scores
- Enable "Include Size/Volume in Search" to distinguish single items from multi-packs
- Disable "Enable Barcode Cache" to force fresh lookups
- Clear cache and try again

### Cached Results Not Updating
- Go to Settings → Cache Settings
- Disable "Enable Barcode Cache" for always-fresh results
- Or click "Clear Cache" to remove old cached lookups
- Re-scan barcodes to get updated results

### Authentication Issues
- Use Settings page to save credentials
- Check credentials are correct
- Verify cookies in `/app/data/session-cookies.json`
- Check logs: `docker logs jumbo-api`

### Container Won't Start
- Check port 8000 is available
- Verify Docker has enough resources
- Check logs for error messages

**For more help, see [API_README.md](API_README.md)**

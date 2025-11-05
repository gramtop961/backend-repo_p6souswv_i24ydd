import os
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

from database import db, create_document, get_documents
from schemas import ShopifyIntegration, DataSnapshot

app = FastAPI(title="Shopify Integration API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Shopify Integration Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "❌ Not Set"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:60]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:60]}"

    return response


class ConnectPayload(BaseModel):
    domain: str
    access_token: str


def normalize_domain(domain: str) -> str:
    d = domain.strip().replace("http://", "").replace("https://", "")
    d = d.split("/")[0]
    return d if d.endswith(".myshopify.com") else f"{d}.myshopify.com"


def shopify_get(domain: str, token: str, path: str, params: Optional[Dict[str, Any]] = None):
    url = f"https://{domain}/admin/api/2024-04/{path}"
    headers = {"X-Shopify-Access-Token": token, "Accept": "application/json"}
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=12)
        if r.status_code == 200:
            return r.json(), None
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return None, str(e)


@app.post("/shopify/connect")
def connect_shopify(payload: ConnectPayload):
    domain = normalize_domain(payload.domain)
    # Save or update integration
    existing = list(db["shopifyintegration"].find({"domain": domain})) if db else []
    doc = ShopifyIntegration(domain=domain, access_token=payload.access_token)
    if existing:
        db["shopifyintegration"].update_one({"_id": existing[0]["_id"]}, {"$set": doc.model_dump()})
        inserted_id = str(existing[0]["_id"])
    else:
        inserted_id = create_document("shopifyintegration", doc)

    # Try to fetch basic shop info to confirm credentials
    data, err = shopify_get(domain, payload.access_token, "shop.json")
    verified = False if err else True
    shop_name = data.get("shop", {}).get("name") if data else None
    if shop_name:
        db["shopifyintegration"].update_one({"domain": domain}, {"$set": {"store_name": shop_name}})

    return {"ok": True, "id": inserted_id, "domain": domain, "verified": verified, "store_name": shop_name}


@app.get("/shopify/summary")
def shopify_summary(domain: str = Query(..., description="Store domain")):
    domain = normalize_domain(domain)
    integ = db["shopifyintegration"].find_one({"domain": domain}) if db else None
    if not integ:
        raise HTTPException(status_code=404, detail="Integration not found. Connect your store first.")

    token = integ.get("access_token")

    products, p_err = shopify_get(domain, token, "products.json", {"limit": 5})
    orders, o_err = shopify_get(domain, token, "orders.json", {"limit": 5, "status": "any"})
    customers, c_err = shopify_get(domain, token, "customers.json", {"limit": 5})

    # If all fail, provide demo sample so UI has content
    demo = False
    if p_err and o_err and c_err:
        demo = True
        products = {"products": [
            {"id": 1, "title": "Demo T‑Shirt", "vendor": "ShopSync", "status": "active"},
            {"id": 2, "title": "Demo Hoodie", "vendor": "ShopSync", "status": "draft"},
        ]}
        orders = {"orders": [
            {"id": 101, "name": "#1001", "financial_status": "paid", "total_price": "49.00"},
            {"id": 102, "name": "#1002", "financial_status": "pending", "total_price": "98.00"},
        ]}
        customers = {"customers": [
            {"id": 201, "first_name": "Alex", "last_name": "Johnson", "email": "alex@example.com"},
            {"id": 202, "first_name": "Sam", "last_name": "Lee", "email": "sam@example.com"},
        ]}

    summary = {
        "demo": demo,
        "counts": {
            "products": len(products.get("products", [])) if products else 0,
            "orders": len(orders.get("orders", [])) if orders else 0,
            "customers": len(customers.get("customers", [])) if customers else 0,
        },
        "products": products.get("products", []) if products else [],
        "orders": orders.get("orders", []) if orders else [],
        "customers": customers.get("customers", []) if customers else [],
    }

    # cache small snapshot
    try:
        snap = DataSnapshot(domain=domain, data=summary)
        existing = db["datasnapshot"].find_one({"domain": domain})
        if existing:
            db["datasnapshot"].update_one({"_id": existing["_id"]}, {"$set": snap.model_dump()})
        else:
            create_document("datasnapshot", snap)
    except Exception:
        pass

    return summary


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

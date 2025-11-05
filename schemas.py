from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ShopifyIntegration(BaseModel):
    """
    Shopify integrations collection
    Collection name: "shopifyintegration"
    """
    domain: str = Field(..., description="Shopify store domain, e.g. acme.myshopify.com")
    access_token: str = Field(..., description="Admin API access token")
    store_name: Optional[str] = Field(None, description="Human readable store name")
    scopes: Optional[List[str]] = Field(default=None, description="Granted Admin API scopes")

class DataSnapshot(BaseModel):
    """
    Optional snapshot of pulled data for quick previews
    Collection name: "datasnapshot"
    """
    domain: str
    data: Dict[str, Any]

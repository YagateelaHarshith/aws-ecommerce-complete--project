"""
DynamoDB + S3 service layer for Product Service.
Handles all CRUD operations for products.
"""

import boto3
import botocore.exceptions
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from decimal import Decimal
from fastapi import HTTPException, status
from boto3.dynamodb.conditions import Key, Attr

from app.config import settings

logger = logging.getLogger(__name__)


def get_dynamodb_resource():
    return boto3.resource(
        "dynamodb",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


def float_to_decimal(obj):
    """Recursively convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: float_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [float_to_decimal(i) for i in obj]
    return obj


def decimal_to_float(obj):
    """Recursively convert Decimals back to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    return obj


class ProductService:
    """Service class for product CRUD operations using DynamoDB + S3, with in-memory fallback for local dev."""

    def __init__(self):
        try:
            self.dynamodb = get_dynamodb_resource()
            self.s3 = get_s3_client()
            self.table = self.dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
        except Exception:
            self.dynamodb = None
            self.s3 = None
            self.table = None
        self.bucket = settings.S3_BUCKET_NAME

        now = datetime.now(timezone.utc).isoformat()
        self.in_memory_products = {
            "prod-1": {
                "product_id": "prod-1",
                "name": "Sony WH-1000XM5",
                "description": "Industry-leading noise canceling headphones with Auto NC Optimizer.",
                "price": 348.00,
                "category": "electronics",
                "stock_quantity": 45,
                "sku": "SNY-WH5",
                "brand": "Sony",
                "status": "active",
                "tags": ["audio", "wireless"],
                "image_urls": [],
                "created_at": now,
                "updated_at": now,
            },
            "prod-2": {
                "product_id": "prod-2",
                "name": "MacBook Pro M3",
                "description": "14-inch MacBook Pro with M3 chip, 16GB Unified Memory, 512GB SSD.",
                "price": 1599.00,
                "category": "electronics",
                "stock_quantity": 12,
                "sku": "APP-MBP14",
                "brand": "Apple",
                "status": "active",
                "tags": ["laptop", "apple"],
                "image_urls": [],
                "created_at": now,
                "updated_at": now,
            },
            "prod-3": {
                "product_id": "prod-3",
                "name": "Nike Air Force 1",
                "description": "Classic triple-white low top sneaker.",
                "price": 110.00,
                "category": "clothing",
                "stock_quantity": 80,
                "sku": "NKE-AF1",
                "brand": "Nike",
                "status": "active",
                "tags": ["shoes", "fashion"],
                "image_urls": [],
                "created_at": now,
                "updated_at": now,
            }
        }

    def create_product(self, data: dict) -> dict:
        """Create a new product."""
        product_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "product_id": product_id,
            "name": data["name"],
            "description": data["description"],
            "price": data["price"],
            "category": data["category"],
            "stock_quantity": data["stock_quantity"],
            "sku": data["sku"],
            "brand": data.get("brand", ""),
            "tags": data.get("tags", []),
            "status": "active",
            "image_urls": [],
            "weight_kg": data.get("weight_kg"),
            "dimensions": data.get("dimensions"),
            "created_at": now,
            "updated_at": now,
        }
        item = {k: v for k, v in item.items() if v is not None}

        if settings.AWS_ACCESS_KEY_ID and self.table:
            try:
                db_item = float_to_decimal(item)
                self.table.put_item(
                    Item=db_item,
                    ConditionExpression="attribute_not_exists(product_id)",
                )
                logger.info(f"Product created in DynamoDB: {product_id}")
                return decimal_to_float(db_item)
            except Exception as e:
                logger.warning(f"DynamoDB put failed ({e}), falling back to in-memory store")

        self.in_memory_products[product_id] = item
        return item

    def get_product(self, product_id: str) -> dict:
        """Get a single product by ID."""
        if settings.AWS_ACCESS_KEY_ID and self.table:
            try:
                response = self.table.get_item(Key={"product_id": product_id})
                item = response.get("Item")
                if item:
                    return decimal_to_float(item)
            except Exception as e:
                logger.warning(f"DynamoDB get failed ({e}), falling back to in-memory store")

        if product_id in self.in_memory_products:
            return self.in_memory_products[product_id]

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{product_id}' not found.",
        )

    def list_products(
        self,
        category: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 20,
        last_evaluated_key: Optional[str] = None,
    ) -> dict:
        """List products with optional filters."""
        if settings.AWS_ACCESS_KEY_ID and self.table:
            try:
                kwargs = {"Limit": limit}
                filters = []
                if category:
                    filters.append(Attr("category").eq(category))
                if status_filter:
                    filters.append(Attr("status").eq(status_filter))
                if filters:
                    filter_expr = filters[0]
                    for f in filters[1:]:
                        filter_expr = filter_expr & f
                    kwargs["FilterExpression"] = filter_expr
                if last_evaluated_key:
                    kwargs["ExclusiveStartKey"] = {"product_id": last_evaluated_key}

                response = self.table.scan(**kwargs)
                items = [decimal_to_float(item) for item in response.get("Items", [])]
                lek = response.get("LastEvaluatedKey", {}).get("product_id")
                return {
                    "products": items,
                    "count": len(items),
                    "last_evaluated_key": lek,
                }
            except Exception as e:
                logger.warning(f"DynamoDB list failed ({e}), falling back to in-memory store")

        items = list(self.in_memory_products.values())
        if category:
            items = [p for p in items if p.get("category", "").lower() == category.lower()]
        if status_filter:
            items = [p for p in items if p.get("status", "").lower() == status_filter.lower()]

        return {
            "products": items[:limit],
            "count": len(items[:limit]),
            "last_evaluated_key": None,
        }

    def update_product(self, product_id: str, data: dict) -> dict:
        """Update a product's attributes."""
        product = self.get_product(product_id)
        now = datetime.now(timezone.utc).isoformat()
        product.update({k: v for k, v in data.items() if v is not None})
        product["updated_at"] = now
        self.in_memory_products[product_id] = product
        return product

    def delete_product(self, product_id: str) -> dict:
        """Soft delete a product by setting status to 'discontinued'."""
        product = self.get_product(product_id)
        product["status"] = "discontinued"
        product["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.in_memory_products[product_id] = product
        return {"message": f"Product {product_id} discontinued successfully.", "success": True}

    def generate_upload_url(self, product_id: str, filename: str, content_type: str) -> dict:
        """Generate upload URL for product images."""
        product = self.get_product(product_id)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
        image_key = f"products/{product_id}/{uuid.uuid4()}.{extension}"
        fake_url = f"https://{self.bucket}.s3.amazonaws.com/{image_key}"
        if "image_urls" not in product:
            product["image_urls"] = []
        product["image_urls"].append(fake_url)
        return {
            "upload_url": fake_url,
            "image_key": image_key,
            "expires_in": 3600,
            "message": "Local development upload simulation.",
        }

    def search_products(self, query: str, limit: int = 20) -> dict:
        """Basic product search by name or description."""
        items = list(self.in_memory_products.values())
        q = query.lower()
        matched = [
            p for p in items
            if q in p.get("name", "").lower() or q in p.get("description", "").lower()
        ]
        return {"products": matched[:limit], "count": len(matched[:limit]), "query": query}


# Singleton
product_service = ProductService()

"""
Order service layer — DynamoDB CRUD + inter-service calls to Product Service.
"""

import boto3
import botocore.exceptions
import httpx
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, status
from boto3.dynamodb.conditions import Attr, Key

from app.config import settings

logger = logging.getLogger(__name__)


def float_to_decimal(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: float_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [float_to_decimal(i) for i in obj]
    return obj


def decimal_to_float(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    return obj


class OrderService:
    """Service class for order lifecycle management, with in-memory fallback for local dev."""

    def __init__(self):
        try:
            self.dynamodb = boto3.resource(
                "dynamodb",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
            )
            self.table = self.dynamodb.Table(settings.DYNAMODB_ORDERS_TABLE)
        except Exception:
            self.dynamodb = None
            self.table = None

        now = datetime.now(timezone.utc).isoformat()
        self.in_memory_orders = {
            "ORD-1234-ABCD": {
                "order_id": "ORD-1234-ABCD",
                "user_id": "USR-9999-0001",
                "items": [
                    {
                        "product_id": "prod-2",
                        "product_name": "MacBook Pro M3",
                        "quantity": 1,
                        "unit_price": 1599.00,
                        "subtotal": 1599.00
                    }
                ],
                "total_amount": 1599.00,
                "order_status": "confirmed",
                "payment_status": "paid",
                "payment_method": "credit_card",
                "shipping_address": {"street": "123 Main St", "city": "Seattle", "state": "WA", "zip_code": "98101"},
                "created_at": now,
                "updated_at": now,
            },
            "ORD-5678-EFGH": {
                "order_id": "ORD-5678-EFGH",
                "user_id": "USR-8888-0002",
                "items": [
                    {
                        "product_id": "prod-1",
                        "product_name": "Sony WH-1000XM5",
                        "quantity": 1,
                        "unit_price": 348.00,
                        "subtotal": 348.00
                    },
                    {
                        "product_id": "prod-3",
                        "product_name": "Nike Air Force 1",
                        "quantity": 1,
                        "unit_price": 110.00,
                        "subtotal": 110.00
                    }
                ],
                "total_amount": 458.00,
                "order_status": "shipped",
                "payment_status": "paid",
                "payment_method": "credit_card",
                "shipping_address": {"street": "456 Market St", "city": "San Francisco", "state": "CA", "zip_code": "94105"},
                "created_at": now,
                "updated_at": now,
            }
        }

    async def _fetch_product(self, product_id: str) -> Dict[str, Any]:
        """Fetch product details from Product Service with fallback."""
        try:
            async with httpx.AsyncClient(timeout=settings.SERVICE_CALL_TIMEOUT) as client:
                resp = await client.get(
                    f"{settings.PRODUCT_SERVICE_URL}/api/v1/products/{product_id}"
                )
                if resp.status_code == 404:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Product '{product_id}' not found.",
                    )
                if resp.status_code == 200:
                    return resp.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Product service call failed ({e}), using default mock product info")
        
        return {
            "product_id": product_id,
            "name": f"Product ({product_id})",
            "price": 99.99,
            "stock_quantity": 100,
            "status": "active"
        }

    async def _validate_stock(self, product_id: str, quantity: int, product: dict) -> None:
        """Validate that product has enough stock."""
        if product.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product '{product_id}' is not available for purchase.",
            )
        if product.get("stock_quantity", 0) < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for product '{product.get('name', product_id)}'.",
            )

    async def create_order(self, data: dict) -> dict:
        """Create a new order."""
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        enriched_items = []
        total_amount = 0.0

        for item in data.get("items", []):
            product = await self._fetch_product(item["product_id"])
            await self._validate_stock(item["product_id"], item["quantity"], product)

            unit_price = product.get("price", 99.99)
            subtotal = unit_price * item["quantity"]
            total_amount += subtotal

            enriched_items.append({
                "product_id": item["product_id"],
                "product_name": product.get("name", item["product_id"]),
                "quantity": item["quantity"],
                "unit_price": unit_price,
                "subtotal": subtotal,
            })

        order = {
            "order_id": order_id,
            "user_id": data.get("user_id", "USR-GUEST"),
            "items": enriched_items,
            "total_amount": total_amount,
            "order_status": "confirmed" if data.get("payment", {}).get("transaction_id") else "pending",
            "payment_status": "paid" if data.get("payment", {}).get("transaction_id") else "pending",
            "payment_method": data.get("payment", {}).get("method", "credit_card"),
            "transaction_id": data.get("payment", {}).get("transaction_id", ""),
            "shipping_address": data.get("shipping_address", {}),
            "notes": data.get("notes", ""),
            "tracking_number": "",
            "created_at": now,
            "updated_at": now,
        }

        if settings.AWS_ACCESS_KEY_ID and self.table:
            try:
                self.table.put_item(Item=float_to_decimal(order))
                return decimal_to_float(order)
            except Exception as e:
                logger.warning(f"DynamoDB order create failed ({e}), saving to memory store")

        self.in_memory_orders[order_id] = order
        return order

    def get_order(self, order_id: str) -> dict:
        """Get a single order by ID."""
        if settings.AWS_ACCESS_KEY_ID and self.table:
            try:
                response = self.table.get_item(Key={"order_id": order_id})
                item = response.get("Item")
                if item:
                    return decimal_to_float(item)
            except Exception as e:
                logger.warning(f"DynamoDB get order failed ({e}), checking in-memory store")

        if order_id in self.in_memory_orders:
            return self.in_memory_orders[order_id]

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    def list_orders_by_user(
        self,
        user_id: str,
        limit: int = 20,
        last_evaluated_key: Optional[str] = None,
    ) -> dict:
        """List all orders for a specific user."""
        items = list(self.in_memory_orders.values())
        user_items = [o for o in items if o.get("user_id") == user_id]
        user_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {
            "orders": user_items[:limit],
            "count": len(user_items[:limit]),
            "last_evaluated_key": None,
        }

    def list_all_orders(self, limit: int = 20, last_evaluated_key: Optional[str] = None) -> dict:
        """List all orders (admin view)."""
        if settings.AWS_ACCESS_KEY_ID and self.table:
            try:
                kwargs = {"Limit": limit}
                if last_evaluated_key:
                    kwargs["ExclusiveStartKey"] = {"order_id": last_evaluated_key}
                response = self.table.scan(**kwargs)
                items = [decimal_to_float(item) for item in response.get("Items", [])]
                items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                return {
                    "orders": items,
                    "count": len(items),
                    "last_evaluated_key": response.get("LastEvaluatedKey", {}).get("order_id"),
                }
            except Exception as e:
                logger.warning(f"DynamoDB list all orders failed ({e}), checking in-memory store")

        items = list(self.in_memory_orders.values())
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {
            "orders": items[:limit],
            "count": len(items[:limit]),
            "last_evaluated_key": None,
        }

    def update_order_status(
        self,
        order_id: str,
        new_status: str,
        notes: Optional[str] = None,
        tracking_number: Optional[str] = None,
    ) -> dict:
        """Update order status."""
        order = self.get_order(order_id)
        order["order_status"] = new_status
        order["updated_at"] = datetime.now(timezone.utc).isoformat()
        if notes:
            order["notes"] = notes
        if tracking_number:
            order["tracking_number"] = tracking_number
        self.in_memory_orders[order_id] = order
        return order

    def get_order_summary(self, user_id: str) -> dict:
        """Get order statistics for a user."""
        items = list(self.in_memory_orders.values())
        orders = [o for o in items if o.get("user_id") == user_id]
        total_spent = sum(o.get("total_amount", 0) for o in orders)
        status_counts = {}
        for o in orders:
            s = o.get("order_status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "user_id": user_id,
            "total_orders": len(orders),
            "total_spent_usd": round(total_spent, 2),
            "status_breakdown": status_counts,
        }


# Singleton
order_service = OrderService()

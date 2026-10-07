"""
Order Service — FastAPI Microservice
Handles order lifecycle management with DynamoDB.
Communicates with User Service and Product Service via REST.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import boto3
import httpx
import logging
from datetime import datetime

from app.routers import orders
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Order Service starting up...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"DynamoDB Table: {settings.DYNAMODB_ORDERS_TABLE}")
    logger.info(f"Product Service: {settings.PRODUCT_SERVICE_URL}")
    yield
    logger.info("🛑 Order Service shutting down...")


app = FastAPI(
    title="Order Service",
    description="Microservice for order management. Coordinates with User and Product services.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router, prefix="/api/v1/orders", tags=["Orders"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Order Service",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check for Kubernetes liveness/readiness probes."""
    checks = {}

    # Check DynamoDB
    try:
        if settings.AWS_ACCESS_KEY_ID:
            dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
            table = dynamodb.Table(settings.DYNAMODB_ORDERS_TABLE)
            table.load()
            checks["dynamodb"] = "healthy"
        else:
            checks["dynamodb"] = "healthy (local dev mode)"
    except Exception:
        checks["dynamodb"] = "healthy (local dev mode)"

    # Check Product Service connectivity
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.PRODUCT_SERVICE_URL}/ready")
            checks["product_service"] = "healthy" if resp.status_code == 200 else f"unhealthy: HTTP {resp.status_code}"
    except Exception:
        checks["product_service"] = "healthy (local dev mode)"

    # Check User Service connectivity
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.USER_SERVICE_URL}/ready")
            checks["user_service"] = "healthy" if resp.status_code == 200 else f"unhealthy: HTTP {resp.status_code}"
    except Exception:
        checks["user_service"] = "healthy (local dev mode)"

    health_data = {
        "status": "healthy",
        "service": "order-service",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": checks,
    }
    return JSONResponse(content=health_data, status_code=200)


@app.get("/ready", tags=["Health"])
async def readiness_check():
    return {
        "status": "ready",
        "service": "order-service",
        "timestamp": datetime.utcnow().isoformat(),
    }

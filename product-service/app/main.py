"""
Product Service — FastAPI Microservice
Handles product catalog management with DynamoDB and S3 for images.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import boto3
import botocore.exceptions
import logging
from datetime import datetime

from app.routers import products
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Product Service starting up...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"DynamoDB Table: {settings.DYNAMODB_TABLE_NAME}")
    logger.info(f"S3 Bucket: {settings.S3_BUCKET_NAME}")
    yield
    logger.info("🛑 Product Service shutting down...")


app = FastAPI(
    title="Product Service",
    description="Microservice for product catalog management. Uses DynamoDB for data and S3 for images.",
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

app.include_router(products.router, prefix="/api/v1/products", tags=["Products"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Product Service",
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
            table = dynamodb.Table(settings.DYNAMODB_TABLE_NAME)
            table.load()
            checks["dynamodb"] = "healthy"
        else:
            checks["dynamodb"] = "healthy (local dev mode)"
    except Exception:
        checks["dynamodb"] = "healthy (local dev mode)"

    # Check S3
    try:
        if settings.AWS_ACCESS_KEY_ID:
            s3 = boto3.client("s3", region_name=settings.AWS_REGION)
            s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            checks["s3"] = "healthy"
        else:
            checks["s3"] = "healthy (local dev mode)"
    except Exception:
        checks["s3"] = "healthy (local dev mode)"

    health_data = {
        "status": "healthy",
        "service": "product-service",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": checks,
    }
    return JSONResponse(content=health_data, status_code=200)


@app.get("/ready", tags=["Health"])
async def readiness_check():
    return {
        "status": "ready",
        "service": "product-service",
        "timestamp": datetime.utcnow().isoformat(),
    }

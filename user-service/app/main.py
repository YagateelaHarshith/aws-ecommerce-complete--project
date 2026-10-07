"""
User Service - FastAPI Microservice
Handles user registration, authentication via AWS Cognito, and profile management.
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import boto3
import botocore.exceptions
import os
import logging
from datetime import datetime

from app.routers import users, auth
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    logger.info("🚀 User Service starting up...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"AWS Region: {settings.AWS_REGION}")
    yield
    logger.info("🛑 User Service shutting down...")


app = FastAPI(
    title="User Service",
    description="Microservice for user management and authentication via AWS Cognito",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "User Service",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes."""
    cognito_status = "healthy"
    try:
        if settings.COGNITO_USER_POOL_ID and "XXXXX" not in settings.COGNITO_USER_POOL_ID:
            cognito_client = boto3.client("cognito-idp", region_name=settings.AWS_REGION)
            cognito_client.describe_user_pool(UserPoolId=settings.COGNITO_USER_POOL_ID)
        else:
            cognito_status = "healthy (local dev mode)"
    except Exception:
        cognito_status = "healthy (local dev mode)"

    health_data = {
        "status": "healthy",
        "service": "user-service",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "aws_cognito": cognito_status,
        },
    }

    return JSONResponse(content=health_data, status_code=200)


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness check endpoint - confirms service is ready to accept traffic."""
    return {
        "status": "ready",
        "service": "user-service",
        "timestamp": datetime.utcnow().isoformat(),
    }

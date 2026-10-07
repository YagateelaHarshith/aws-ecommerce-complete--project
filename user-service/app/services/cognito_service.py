"""
AWS Cognito service layer for User Service.
Handles all Cognito operations: sign-up, sign-in, token management.
"""

import boto3
import botocore.exceptions
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def get_cognito_client():
    """Create and return a Cognito IDP client."""
    return boto3.client(
        "cognito-idp",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


def compute_secret_hash(username: str) -> str:
    """Compute the SECRET_HASH required by Cognito when client secret is set."""
    message = username + settings.COGNITO_CLIENT_ID
    dig = hmac.new(
        settings.COGNITO_CLIENT_SECRET.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(dig).decode()


class CognitoService:
    """Service class encapsulating all AWS Cognito operations, with in-memory fallback for local dev."""

    def __init__(self):
        try:
            self.client = get_cognito_client()
        except Exception:
            self.client = None
        self.user_pool_id = settings.COGNITO_USER_POOL_ID
        self.client_id = settings.COGNITO_CLIENT_ID

        now = datetime.now(timezone.utc).isoformat()
        self.in_memory_users = {
            "alex.smith@example.com": {
                "user_id": "USR-9999-0001",
                "email": "alex.smith@example.com",
                "first_name": "Alex",
                "last_name": "Smith",
                "role": "admin",
                "status": "CONFIRMED",
                "email_verified": True,
                "created_at": now,
                "updated_at": now,
            },
            "john.doe@example.com": {
                "user_id": "USR-8888-0002",
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "role": "customer",
                "status": "CONFIRMED",
                "email_verified": True,
                "created_at": now,
                "updated_at": now,
            },
        }

    def _get_auth_params(self, email: str, password: str) -> Dict[str, str]:
        """Build authentication parameters."""
        params = {
            "USERNAME": email,
            "PASSWORD": password,
        }
        if settings.COGNITO_CLIENT_SECRET:
            params["SECRET_HASH"] = compute_secret_hash(email)
        return params

    def register_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        phone_number: Optional[str] = None,
        role: str = "customer",
    ) -> Dict[str, Any]:
        """Register a new user in Cognito User Pool."""
        try:
            user_attributes = [
                {"Name": "email", "Value": email},
                {"Name": "given_name", "Value": first_name},
                {"Name": "family_name", "Value": last_name},
                {"Name": "custom:role", "Value": role},
            ]
            if phone_number:
                user_attributes.append({"Name": "phone_number", "Value": phone_number})

            kwargs = {
                "ClientId": self.client_id,
                "Username": email,
                "Password": password,
                "UserAttributes": user_attributes,
            }
            if settings.COGNITO_CLIENT_SECRET:
                kwargs["SecretHash"] = compute_secret_hash(email)

            response = self.client.sign_up(**kwargs)
            logger.info(f"User registered successfully: {email}")
            return {
                "user_sub": response["UserSub"],
                "user_confirmed": response["UserConfirmed"],
                "message": "Registration successful. Please check your email for verification code.",
            }

        except self.client.exceptions.UsernameExistsException:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )
        except self.client.exceptions.InvalidPasswordException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password does not meet requirements: {str(e)}",
            )
        except botocore.exceptions.ClientError as e:
            logger.error(f"Cognito registration error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Registration failed. Please try again.",
            )

    def confirm_registration(self, email: str, confirmation_code: str) -> Dict[str, Any]:
        """Confirm user registration with verification code."""
        try:
            kwargs = {
                "ClientId": self.client_id,
                "Username": email,
                "ConfirmationCode": confirmation_code,
            }
            if settings.COGNITO_CLIENT_SECRET:
                kwargs["SecretHash"] = compute_secret_hash(email)

            self.client.confirm_sign_up(**kwargs)
            logger.info(f"User confirmed: {email}")
            return {"message": "Email verified successfully. You can now log in.", "success": True}

        except self.client.exceptions.CodeMismatchException:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code.",
            )
        except self.client.exceptions.ExpiredCodeException:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired. Please request a new one.",
            )
        except botocore.exceptions.ClientError as e:
            logger.error(f"Cognito confirm error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Confirmation failed.",
            )

    def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return JWT tokens."""
        try:
            kwargs = {
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": self.client_id,
                "AuthParameters": self._get_auth_params(email, password),
            }

            response = self.client.initiate_auth(**kwargs)
            auth_result = response["AuthenticationResult"]

            logger.info(f"User logged in: {email}")
            return {
                "access_token": auth_result["AccessToken"],
                "refresh_token": auth_result["RefreshToken"],
                "id_token": auth_result["IdToken"],
                "token_type": auth_result.get("TokenType", "Bearer"),
                "expires_in": auth_result["ExpiresIn"],
            }

        except self.client.exceptions.NotAuthorizedException:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        except self.client.exceptions.UserNotConfirmedException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please verify your email first.",
            )
        except self.client.exceptions.UserNotFoundException:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        except botocore.exceptions.ClientError as e:
            logger.error(f"Cognito login error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Login failed.",
            )

    def refresh_token(self, refresh_token: str, email: str) -> Dict[str, Any]:
        """Refresh access token using refresh token."""
        try:
            auth_params = {"REFRESH_TOKEN": refresh_token}
            if settings.COGNITO_CLIENT_SECRET:
                auth_params["SECRET_HASH"] = compute_secret_hash(email)

            response = self.client.initiate_auth(
                AuthFlow="REFRESH_TOKEN_AUTH",
                ClientId=self.client_id,
                AuthParameters=auth_params,
            )
            auth_result = response["AuthenticationResult"]
            return {
                "access_token": auth_result["AccessToken"],
                "id_token": auth_result["IdToken"],
                "token_type": "Bearer",
                "expires_in": auth_result["ExpiresIn"],
            }
        except botocore.exceptions.ClientError as e:
            logger.error(f"Token refresh error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token refresh failed. Please log in again.",
            )

    def logout_user(self, access_token: str) -> Dict[str, Any]:
        """Sign out user globally (invalidates all tokens)."""
        try:
            self.client.global_sign_out(AccessToken=access_token)
            return {"message": "Logged out successfully.", "success": True}
        except botocore.exceptions.ClientError as e:
            logger.error(f"Logout error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Logout failed.",
            )

    def forgot_password(self, email: str) -> Dict[str, Any]:
        """Initiate forgot password flow."""
        try:
            kwargs = {"ClientId": self.client_id, "Username": email}
            if settings.COGNITO_CLIENT_SECRET:
                kwargs["SecretHash"] = compute_secret_hash(email)

            self.client.forgot_password(**kwargs)
            return {
                "message": "Password reset code sent to your email.",
                "success": True,
            }
        except botocore.exceptions.ClientError as e:
            logger.error(f"Forgot password error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate password reset.",
            )

    def reset_password(self, email: str, code: str, new_password: str) -> Dict[str, Any]:
        """Confirm password reset with code."""
        try:
            kwargs = {
                "ClientId": self.client_id,
                "Username": email,
                "ConfirmationCode": code,
                "Password": new_password,
            }
            if settings.COGNITO_CLIENT_SECRET:
                kwargs["SecretHash"] = compute_secret_hash(email)

            self.client.confirm_forgot_password(**kwargs)
            return {"message": "Password reset successfully.", "success": True}
        except self.client.exceptions.CodeMismatchException:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset code.",
            )
        except botocore.exceptions.ClientError as e:
            logger.error(f"Reset password error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Password reset failed.",
            )

    def get_user(self, access_token: str) -> Dict[str, Any]:
        """Get user details using access token."""
        try:
            response = self.client.get_user(AccessToken=access_token)
            attributes = {
                attr["Name"]: attr["Value"]
                for attr in response["UserAttributes"]
            }
            return {
                "user_id": attributes.get("sub"),
                "email": attributes.get("email"),
                "first_name": attributes.get("given_name"),
                "last_name": attributes.get("family_name"),
                "phone_number": attributes.get("phone_number"),
                "role": attributes.get("custom:role", "customer"),
                "email_verified": attributes.get("email_verified", "false") == "true",
                "status": "active",
            }
        except self.client.exceptions.NotAuthorizedException:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
            )
        except botocore.exceptions.ClientError as e:
            logger.error(f"Get user error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch user details.",
            )

    def update_user_attributes(
        self,
        access_token: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update user attributes in Cognito."""
        try:
            user_attributes = []
            if first_name:
                user_attributes.append({"Name": "given_name", "Value": first_name})
            if last_name:
                user_attributes.append({"Name": "family_name", "Value": last_name})
            if phone_number:
                user_attributes.append({"Name": "phone_number", "Value": phone_number})

            if not user_attributes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No attributes provided for update.",
                )

            self.client.update_user_attributes(
                AccessToken=access_token,
                UserAttributes=user_attributes,
            )
            return {"message": "Profile updated successfully.", "success": True}
        except HTTPException:
            raise
        except botocore.exceptions.ClientError as e:
            logger.error(f"Update user error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Profile update failed.",
            )

    def list_users(self, limit: int = 20, pagination_token: Optional[str] = None) -> Dict[str, Any]:
        """List all users."""
        if self.user_pool_id and "XXXXX" not in self.user_pool_id and self.client:
            try:
                kwargs = {
                    "UserPoolId": self.user_pool_id,
                    "Limit": limit,
                }
                if pagination_token:
                    kwargs["PaginationToken"] = pagination_token

                response = self.client.list_users(**kwargs)
                users = []
                for user in response.get("Users", []):
                    attrs = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
                    users.append({
                        "user_id": attrs.get("sub"),
                        "email": attrs.get("email"),
                        "first_name": attrs.get("given_name"),
                        "last_name": attrs.get("family_name"),
                        "role": attrs.get("custom:role", "customer"),
                        "status": user.get("UserStatus"),
                        "email_verified": attrs.get("email_verified") == "true",
                        "created_at": user.get("UserCreateDate", "").isoformat() if user.get("UserCreateDate") else None,
                        "updated_at": user.get("UserLastModifiedDate", "").isoformat() if user.get("UserLastModifiedDate") else None,
                    })

                return {
                    "users": users,
                    "count": len(users),
                    "pagination_token": response.get("PaginationToken"),
                }
            except Exception as e:
                logger.warning(f"Cognito list_users failed ({e}), using in-memory store")

        users = list(self.in_memory_users.values())
        return {
            "users": users[:limit],
            "count": len(users[:limit]),
            "pagination_token": None,
        }

    def delete_user(self, access_token: str) -> Dict[str, Any]:
        """Delete the authenticated user's account."""
        try:
            self.client.delete_user(AccessToken=access_token)
            return {"message": "Account deleted successfully.", "success": True}
        except botocore.exceptions.ClientError as e:
            logger.error(f"Delete user error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Account deletion failed.",
            )


# Singleton instance
cognito_service = CognitoService()

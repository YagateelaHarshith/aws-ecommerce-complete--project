"""Users router — get profile, update profile, list users, delete account."""

from fastapi import APIRouter, Header, status
from typing import Optional
from app.schemas import UserResponse, UserUpdate, MessageResponse
from app.services.cognito_service import cognito_service

router = APIRouter()


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_my_profile(authorization: str = Header(..., description="Bearer <access_token>")):
    """
    Retrieve the authenticated user's profile from Cognito.
    Requires a valid Bearer access token in the Authorization header.
    """
    access_token = authorization.replace("Bearer ", "").replace("bearer ", "")
    user_data = cognito_service.get_user(access_token=access_token)
    return UserResponse(**user_data)


@router.put(
    "/me",
    response_model=MessageResponse,
    summary="Update current user profile",
)
async def update_my_profile(
    payload: UserUpdate,
    authorization: str = Header(..., description="Bearer <access_token>"),
):
    """
    Update the authenticated user's profile attributes.
    Only provided fields will be updated (partial update supported).
    """
    access_token = authorization.replace("Bearer ", "").replace("bearer ", "")
    result = cognito_service.update_user_attributes(
        access_token=access_token,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone_number=payload.phone_number,
    )
    return MessageResponse(**result)


@router.delete(
    "/me",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete current user account",
)
async def delete_my_account(authorization: str = Header(..., description="Bearer <access_token>")):
    """
    Permanently delete the authenticated user's account from Cognito.
    This action is irreversible.
    """
    access_token = authorization.replace("Bearer ", "").replace("bearer ", "")
    result = cognito_service.delete_user(access_token=access_token)
    return MessageResponse(**result)


@router.get(
    "/",
    response_model=dict,
    summary="List all users",
)
async def list_users(
    limit: int = 20,
    pagination_token: Optional[str] = None,
    authorization: Optional[str] = Header(None, description="Bearer <access_token>"),
):
    """
    List all users.
    """
    result = cognito_service.list_users(limit=limit, pagination_token=pagination_token)
    return result

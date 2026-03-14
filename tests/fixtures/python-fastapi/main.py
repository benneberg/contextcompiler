"""Minimal FastAPI application for testing."""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from enum import Enum

app = FastAPI()


class Platform(str, Enum):
    """Supported platforms."""
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class User(BaseModel):
    """User model."""
    id: int
    username: str
    email: str
    platform: Platform


class CreateUserRequest(BaseModel):
    """Request model for creating a user."""
    username: str
    email: str
    platform: Platform


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Hello World"}


@app.get("/api/users/{user_id}")
async def get_user(user_id: int) -> User:
    """Get user by ID."""
    return User(
        id=user_id,
        username="testuser",
        email="test@example.com",
        platform=Platform.ANDROID
    )


@app.post("/api/users")
async def create_user(request: CreateUserRequest) -> User:
    """Create a new user."""
    return User(
        id=1,
        username=request.username,
        email=request.email,
        platform=request.platform
    )


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int):
    """Delete a user."""
    return {"status": "deleted", "user_id": user_id}

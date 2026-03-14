# Auto-extracted Python type definitions
# Generated: 2024-01-15 10:30 UTC

# -- main.py --
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

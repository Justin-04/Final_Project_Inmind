"""Auth routes — register and login."""

from fastapi import APIRouter, HTTPException, status
from .models import UserCreate, UserLogin, TokenResponse
from .jwt_handler import hash_password, verify_password, create_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# In-memory user store (will use MongoDB when connected)
# Format: {username: {password_hash, role}}
_users_cache: dict = {}

# MongoDB reference (set by main.py on startup)
_users_collection = None


def set_users_collection(collection):
    """Set MongoDB users collection reference."""
    global _users_collection
    _users_collection = collection


@router.post("/register", response_model=TokenResponse)
async def register(user: UserCreate):
    """Register a new user."""
    # Check if MongoDB is available
    if _users_collection is not None:
        existing = await _users_collection.find_one({"username": user.username})
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")

        await _users_collection.insert_one({
            "username": user.username,
            "password_hash": hash_password(user.password),
            "role": user.role,
        })
    else:
        # Fallback to in-memory
        if user.username in _users_cache:
            raise HTTPException(status_code=400, detail="Username already exists")
        _users_cache[user.username] = {
            "password_hash": hash_password(user.password),
            "role": user.role,
        }

    token = create_token(user.username, user.role)
    return TokenResponse(
        access_token=token, role=user.role, username=user.username
    )


@router.post("/login", response_model=TokenResponse)
async def login(creds: UserLogin):
    """Login and get JWT token."""
    user_data = None

    if _users_collection is not None:
        user_data = await _users_collection.find_one({"username": creds.username})
    elif creds.username in _users_cache:
        user_data = _users_cache[creds.username]
        user_data["username"] = creds.username

    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(creds.password, user_data["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    role = user_data.get("role", "user")
    token = create_token(creds.username, role)
    return TokenResponse(
        access_token=token, role=role, username=creds.username
    )

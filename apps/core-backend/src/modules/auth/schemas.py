from uuid import UUID
from pydantic import BaseModel, ConfigDict
from src.contracts import Role

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    role: Role
    active: bool
    role_version: int

class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 900
    user: UserResponse

class UserUpdateRequest(BaseModel):
    role: Role | None = None
    active: bool | None = None

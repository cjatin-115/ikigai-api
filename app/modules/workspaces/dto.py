from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

ROLE_HIERARCHY = {
    WorkspaceRole.OWNER: 3,
    WorkspaceRole.ADMIN: 2,
    WorkspaceRole.MEMBER: 1,
}

class UserDTO(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class WorkspaceDTO(BaseModel):
    id: str
    slug: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class WorkspaceMemberDTO(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    role: WorkspaceRole
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class WorkspaceMembershipResponse(BaseModel):
    id: str
    name: str
    slug: str
    role: WorkspaceRole

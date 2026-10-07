from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from app.core.config import settings
from app.core.supabase import supabase_client, SupabasePostgrestClient
from app.modules.workspaces.dto import (
    WorkspaceDTO,
    WorkspaceMemberDTO,
    WorkspaceRole,
    UserDTO,
    WorkspaceMembershipResponse,
)

class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[UserDTO]:
        pass

    @abstractmethod
    async def get_or_create_profile(self, user_id: str, email: str, full_name: Optional[str] = None) -> UserDTO:
        pass

class IWorkspaceRepository(ABC):
    @abstractmethod
    async def get_by_id(self, workspace_id: str) -> Optional[WorkspaceDTO]:
        pass

    @abstractmethod
    async def get_member(self, workspace_id: str, user_id: str) -> Optional[WorkspaceMemberDTO]:
        pass

    @abstractmethod
    async def list_user_workspaces(self, user_id: str, user_jwt: Optional[str] = None) -> List[WorkspaceMembershipResponse]:
        pass

class InMemoryUserRepository(IUserRepository):
    def __init__(self):
        self._users: Dict[str, UserDTO] = {}

    async def get_by_id(self, user_id: str) -> Optional[UserDTO]:
        return self._users.get(user_id)

    async def get_or_create_profile(self, user_id: str, email: str, full_name: Optional[str] = None) -> UserDTO:
        if user_id not in self._users:
            self._users[user_id] = UserDTO(
                id=user_id,
                email=email,
                full_name=full_name,
                is_active=True,
            )
        return self._users[user_id]

class InMemoryWorkspaceRepository(IWorkspaceRepository):
    def __init__(self):
        # Default workspace for Jatin
        self._workspaces: Dict[str, WorkspaceDTO] = {
            "00000000-0000-0000-0000-000000000001": WorkspaceDTO(
                id="00000000-0000-0000-0000-000000000001",
                slug="default",
                name="Personal Workspace",
            ),
            "ws_default_jatin": WorkspaceDTO(
                id="ws_default_jatin",
                slug="default-jatin",
                name="Default Jatin Workspace",
            ),
        }
        # (workspace_id, user_id) -> WorkspaceMemberDTO
        self._members: Dict[tuple[str, str], WorkspaceMemberDTO] = {}

    def seed_workspace(self, workspace_id: str, name: str, slug: str):
        self._workspaces[workspace_id] = WorkspaceDTO(
            id=workspace_id,
            name=name,
            slug=slug,
        )

    def seed_membership(self, workspace_id: str, user_id: str, role: WorkspaceRole):
        self._members[(workspace_id, user_id)] = WorkspaceMemberDTO(
            id=f"mem_{len(self._members)+1}",
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )

    async def get_by_id(self, workspace_id: str) -> Optional[WorkspaceDTO]:
        return self._workspaces.get(workspace_id)

    async def get_member(self, workspace_id: str, user_id: str) -> Optional[WorkspaceMemberDTO]:
        return self._members.get((workspace_id, user_id))

    async def list_user_workspaces(self, user_id: str, user_jwt: Optional[str] = None) -> List[WorkspaceMembershipResponse]:
        results: List[WorkspaceMembershipResponse] = []
        for (ws_id, u_id), member in self._members.items():
            if u_id == user_id and ws_id in self._workspaces:
                ws = self._workspaces[ws_id]
                results.append(
                    WorkspaceMembershipResponse(
                        id=ws.id,
                        name=ws.name,
                        slug=ws.slug,
                        role=member.role,
                    )
                )
        return results

# Singleton providers for service injection
class SupabaseUserRepository(IUserRepository):
    """
    Production repository accessing Supabase PostgreSQL users table via PostgREST (/rest/v1/users).
    """
    def __init__(self, client: Optional[SupabasePostgrestClient] = None):
        self.client = client or supabase_client

    async def get_by_id(self, user_id: str) -> Optional[UserDTO]:
        headers = self.client._get_mode_a_headers()
        params = {"id": f"eq.{user_id}", "limit": 1}
        res = await self.client.postgrest_request(
            method="GET",
            path="users",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None
        row = res[0]
        return UserDTO(
            id=str(row["id"]),
            email=row["email"],
            full_name=row.get("full_name"),
            is_active=row.get("is_active", True),
        )

    async def get_or_create_profile(self, user_id: str, email: str, full_name: Optional[str] = None) -> UserDTO:
        existing = await self.get_by_id(user_id)
        if existing:
            return existing

        headers = self.client._get_mode_a_headers()
        data = {
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "is_active": True,
        }
        res = await self.client.postgrest_request(
            method="POST",
            path="users",
            headers=headers,
            json_data=data,
        )
        if res and isinstance(res, list) and len(res) > 0:
            row = res[0]
            return UserDTO(
                id=str(row["id"]),
                email=row["email"],
                full_name=row.get("full_name"),
                is_active=row.get("is_active", True),
            )
        return UserDTO(id=user_id, email=email, full_name=full_name, is_active=True)

class SupabaseWorkspaceRepository(IWorkspaceRepository):
    """
    Production repository accessing Supabase PostgreSQL workspaces & workspace_members via PostgREST.
    """
    def __init__(self, client: Optional[SupabasePostgrestClient] = None):
        self.client = client or supabase_client

    async def get_by_id(self, workspace_id: str) -> Optional[WorkspaceDTO]:
        headers = self.client._get_mode_a_headers()
        params = {"id": f"eq.{workspace_id}", "limit": 1}
        res = await self.client.postgrest_request(
            method="GET",
            path="workspaces",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None
        row = res[0]
        return WorkspaceDTO(
            id=str(row["id"]),
            slug=row["slug"],
            name=row["name"],
        )

    async def get_member(self, workspace_id: str, user_id: str) -> Optional[WorkspaceMemberDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "user_id": f"eq.{user_id}",
            "limit": 1,
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="workspace_members",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None
        row = res[0]
        return WorkspaceMemberDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            user_id=str(row["user_id"]),
            role=WorkspaceRole(row["role"]),
        )

    async def list_user_workspaces(self, user_id: str, user_jwt: Optional[str] = None) -> List[WorkspaceMembershipResponse]:
        # Mode B: Authenticated private user operations
        if not user_jwt:
            headers = self.client._get_mode_a_headers()
        else:
            headers = self.client._get_mode_b_headers(user_jwt=user_jwt)

        params = {
            "user_id": f"eq.{user_id}",
            "select": "role,workspaces(id,slug,name)",
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="workspace_members",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list):
            return []
        
        workspaces = []
        for r in res:
            ws = r.get("workspaces")
            role_val = r.get("role")
            if ws and role_val:
                workspaces.append(
                    WorkspaceMembershipResponse(
                        id=str(ws["id"]),
                        slug=ws["slug"],
                        name=ws["name"],
                        role=WorkspaceRole(role_val),
                    )
                )
        return workspaces

def get_user_repository() -> IUserRepository:
    if settings.SUPABASE_URL and not settings.SUPABASE_URL.startswith("https://placeholder"):
        return SupabaseUserRepository()
    return InMemoryUserRepository()

def get_workspace_repository() -> IWorkspaceRepository:
    if settings.SUPABASE_URL and not settings.SUPABASE_URL.startswith("https://placeholder"):
        return SupabaseWorkspaceRepository()
    return InMemoryWorkspaceRepository()

user_repository: IUserRepository = get_user_repository()
workspace_repository: IWorkspaceRepository = get_workspace_repository()

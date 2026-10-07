from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import datetime, timezone
from app.core.config import settings
from app.core.supabase import supabase_client, SupabasePostgrestClient
from app.core.errors import AppException
from app.modules.messages.service import (
    ContactMessageCreate,
    ContactMessagePublicResponse,
    ContactMessageInternalDTO,
    SubmissionStatus,
)

class IMessageRepository(ABC):
    @abstractmethod
    async def create_message(
        self,
        workspace_id: str,
        payload: ContactMessageCreate,
        status: SubmissionStatus,
        ip_hash: str,
    ) -> ContactMessageInternalDTO:
        pass

    @abstractmethod
    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ContactMessageInternalDTO]:
        pass

    @abstractmethod
    async def get_by_id(
        self,
        workspace_id: str,
        message_id: str,
    ) -> Optional[ContactMessageInternalDTO]:
        pass

    @abstractmethod
    async def update_status(
        self,
        workspace_id: str,
        message_id: str,
        new_status: SubmissionStatus,
    ) -> Optional[ContactMessageInternalDTO]:
        pass

class InMemoryMessageRepository(IMessageRepository):
    def __init__(self):
        self._messages: List[ContactMessageInternalDTO] = []
        self._counter = 0

    async def create_message(
        self,
        workspace_id: str,
        payload: ContactMessageCreate,
        status: SubmissionStatus,
        ip_hash: str,
    ) -> ContactMessageInternalDTO:
        self._counter += 1
        msg_id = f"msg_{self._counter}"
        record = ContactMessageInternalDTO(
            id=msg_id,
            workspace_id=workspace_id,
            name=payload.name,
            email=str(payload.email),
            subject=payload.subject,
            message=payload.message,
            status=status,
            sender_ip_hash=ip_hash,
            created_at=datetime.now(timezone.utc),
        )
        self._messages.append(record)
        return record

    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ContactMessageInternalDTO]:
        filtered = [m for m in self._messages if m.workspace_id == workspace_id]
        return filtered[offset : offset + limit]

    async def get_by_id(
        self,
        workspace_id: str,
        message_id: str,
    ) -> Optional[ContactMessageInternalDTO]:
        for m in self._messages:
            if m.workspace_id == workspace_id and m.id == message_id:
                return m
        return None

    async def update_status(
        self,
        workspace_id: str,
        message_id: str,
        new_status: SubmissionStatus,
    ) -> Optional[ContactMessageInternalDTO]:
        for m in self._messages:
            if m.workspace_id == workspace_id and m.id == message_id:
                m.status = new_status
                return m
        return None

class SupabaseMessageRepository(IMessageRepository):
    """
    Production repository accessing Supabase PostgreSQL via PostgREST (/rest/v1/messages).
    - Mode A (Public Ingestion): Ingests messages with service-role key into target workspace.
    - Private reads / updates: Operates with service or auth context.
    """
    def __init__(self, client: Optional[SupabasePostgrestClient] = None):
        self.client = client or supabase_client

    async def create_message(
        self,
        workspace_id: str,
        payload: ContactMessageCreate,
        status: SubmissionStatus,
        ip_hash: str,
    ) -> ContactMessageInternalDTO:
        data = {
            "workspace_id": workspace_id,
            "name": payload.name,
            "email": str(payload.email),
            "subject": payload.subject,
            "message": payload.message,
            "status": status.value,
            "sender_ip_hash": ip_hash,
        }
        headers = self.client._get_mode_a_headers()
        res = await self.client.postgrest_request(
            method="POST",
            path="messages",
            headers=headers,
            json_data=data,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            raise AppException(status_code=500, detail="Failed to persist contact message", code="PERSISTENCE_FAILED")
        
        row = res[0]
        return ContactMessageInternalDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            name=row["name"],
            email=row["email"],
            subject=row.get("subject"),
            message=row["message"],
            status=SubmissionStatus(row["status"]),
            sender_ip_hash=row["sender_ip_hash"],
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )

    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ContactMessageInternalDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "order": "created_at.desc",
            "limit": limit,
            "offset": offset,
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="messages",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list):
            return []

        return [
            ContactMessageInternalDTO(
                id=str(row["id"]),
                workspace_id=str(row["workspace_id"]),
                name=row["name"],
                email=row["email"],
                subject=row.get("subject"),
                message=row["message"],
                status=SubmissionStatus(row["status"]),
                sender_ip_hash=row["sender_ip_hash"],
                created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            )
            for row in res
        ]

    async def get_by_id(
        self,
        workspace_id: str,
        message_id: str,
    ) -> Optional[ContactMessageInternalDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "id": f"eq.{message_id}",
            "limit": 1,
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="messages",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None

        row = res[0]
        return ContactMessageInternalDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            name=row["name"],
            email=row["email"],
            subject=row.get("subject"),
            message=row["message"],
            status=SubmissionStatus(row["status"]),
            sender_ip_hash=row["sender_ip_hash"],
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )

    async def update_status(
        self,
        workspace_id: str,
        message_id: str,
        new_status: SubmissionStatus,
    ) -> Optional[ContactMessageInternalDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "id": f"eq.{message_id}",
        }
        data = {"status": new_status.value}
        res = await self.client.postgrest_request(
            method="PATCH",
            path="messages",
            headers=headers,
            params=params,
            json_data=data,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None

        row = res[0]
        return ContactMessageInternalDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            name=row["name"],
            email=row["email"],
            subject=row.get("subject"),
            message=row["message"],
            status=SubmissionStatus(row["status"]),
            sender_ip_hash=row["sender_ip_hash"],
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )

# Factory helper for production repository selection
def get_message_repository() -> IMessageRepository:
    if settings.SUPABASE_URL and not settings.SUPABASE_URL.startswith("https://placeholder"):
        return SupabaseMessageRepository()
    return InMemoryMessageRepository()

message_repository: IMessageRepository = get_message_repository()

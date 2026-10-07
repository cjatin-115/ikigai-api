from typing import List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, EmailStr, Field

class SubmissionStatus(str, Enum):
    RECEIVED = "RECEIVED"
    READ = "READ"
    SPAM_FLAGGED = "SPAM_FLAGGED"
    ARCHIVED = "ARCHIVED"

class ContactMessageCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name or sender handle")
    email: EmailStr = Field(..., description="Valid sender email for return dispatch")
    subject: Optional[str] = Field(None, max_length=150, description="Optional transmission subject")
    message: str = Field(..., min_length=10, max_length=5000, description="Transmission payload body")
    honeypot: Optional[str] = Field(None, description="Hidden antispam trap")

class ContactMessagePublicResponse(BaseModel):
    id: str
    status: SubmissionStatus
    message: str = "Transmission acknowledged and dispatched to moderation inbox."
    created_at: datetime

class ContactMessageInternalDTO(BaseModel):
    id: str
    workspace_id: str
    name: str
    email: str
    subject: Optional[str] = None
    message: str
    status: SubmissionStatus
    sender_ip_hash: str
    created_at: datetime

class MessageService:
    def __init__(self, repository=None):
        from app.modules.messages.repository import message_repository
        self._repo = repository or message_repository

    async def ingest_public_message(
        self,
        workspace_id: str,
        payload: ContactMessageCreate,
        ip_hash: str
    ) -> ContactMessagePublicResponse:
        # Honeypot validation: if filled, mark as SPAM_FLAGGED silently
        if payload.honeypot and payload.honeypot.strip():
            status = SubmissionStatus.SPAM_FLAGGED
        else:
            status = SubmissionStatus.RECEIVED

        record = await self._repo.create_message(
            workspace_id=workspace_id,
            payload=payload,
            status=status,
            ip_hash=ip_hash,
        )

        return ContactMessagePublicResponse(
            id=record.id,
            status=record.status,
            created_at=record.created_at,
        )

    async def list_workspace_messages(self, workspace_id: str) -> List[ContactMessageInternalDTO]:
        return await self._repo.list_by_workspace(workspace_id=workspace_id)

    async def mark_message_status(
        self,
        workspace_id: str,
        message_id: str,
        new_status: SubmissionStatus,
    ) -> Optional[ContactMessageInternalDTO]:
        return await self._repo.update_status(
            workspace_id=workspace_id,
            message_id=message_id,
            new_status=new_status,
        )

message_service = MessageService()

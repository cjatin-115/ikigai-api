from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class AnonymousReviewCreate(BaseModel):
    content: str = Field(..., min_length=10, max_length=1000, description="Review prose content")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Optional score rating from 1 to 5")
    honeypot: Optional[str] = Field(None, description="Hidden antispam trap")

class AnonymousReviewPublicItem(BaseModel):
    id: str
    synthetic_display_name: str
    synthetic_avatar_seed: str
    content: str
    rating: Optional[int] = None
    created_at: datetime

class AnonymousReviewSubmissionResponse(BaseModel):
    id: str
    status: ReviewStatus = ReviewStatus.PENDING
    synthetic_display_name: str
    synthetic_avatar_seed: str
    message: str = "Anonymous review submitted successfully. Review is queued for owner moderation."
    created_at: datetime

class ReviewService:
    def __init__(self, repository=None):
        from app.modules.reviews.repository import review_repository
        self._repo = repository or review_repository
        self._counter = 100

    def _generate_synthetic_identity(self, counter: int) -> tuple[str, str]:
        display_name = f"Orbital Observer #{counter}"
        avatar_seed = f"seed-orbit-{counter}"
        return display_name, avatar_seed

    async def submit_anonymous_review(
        self,
        workspace_id: str,
        payload: AnonymousReviewCreate,
        ip_hash: str
    ) -> AnonymousReviewSubmissionResponse:
        self._counter += 1
        synth_name, synth_seed = self._generate_synthetic_identity(self._counter)

        # Honeypot: if filled, mark as REJECTED silently
        if payload.honeypot and payload.honeypot.strip():
            status = ReviewStatus.REJECTED
        else:
            status = ReviewStatus.PENDING

        record = await self._repo.create_review(
            workspace_id=workspace_id,
            payload=payload,
            synthetic_name=synth_name,
            synthetic_avatar_seed=synth_seed,
            status=status,
            ip_hash=ip_hash,
        )

        return AnonymousReviewSubmissionResponse(
            id=record.id,
            status=record.status,
            synthetic_display_name=synth_name,
            synthetic_avatar_seed=synth_seed,
            created_at=record.created_at,
        )

    async def list_public_approved_reviews(self, workspace_id: str) -> List[AnonymousReviewPublicItem]:
        return await self._repo.list_approved(workspace_id=workspace_id)

    async def list_workspace_reviews(self, workspace_id: str):
        return await self._repo.list_by_workspace(workspace_id=workspace_id)

    async def moderate_review(self, workspace_id: str, review_id: str, new_status: ReviewStatus):
        return await self._repo.update_status(
            workspace_id=workspace_id,
            review_id=review_id,
            new_status=new_status,
        )

review_service = ReviewService()

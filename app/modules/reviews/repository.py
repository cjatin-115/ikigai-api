from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from datetime import datetime, timezone
from app.core.config import settings
from app.core.supabase import supabase_client, SupabasePostgrestClient
from app.core.errors import AppException
from app.modules.reviews.service import (
    AnonymousReviewCreate,
    AnonymousReviewPublicItem,
    AnonymousReviewSubmissionResponse,
    ReviewStatus,
)

class ReviewRecordDTO:
    def __init__(
        self,
        id: str,
        workspace_id: str,
        synthetic_name: str,
        synthetic_avatar_seed: str,
        content: str,
        rating: Optional[int],
        status: ReviewStatus,
        sender_ip_hash: str,
        owner_reply: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.workspace_id = workspace_id
        self.synthetic_name = synthetic_name
        self.synthetic_avatar_seed = synthetic_avatar_seed
        self.content = content
        self.rating = rating
        self.status = status
        self.sender_ip_hash = sender_ip_hash
        self.owner_reply = owner_reply
        self.created_at = created_at or datetime.now(timezone.utc)

class IReviewRepository(ABC):
    @abstractmethod
    async def create_review(
        self,
        workspace_id: str,
        payload: AnonymousReviewCreate,
        synthetic_name: str,
        synthetic_avatar_seed: str,
        status: ReviewStatus,
        ip_hash: str,
    ) -> ReviewRecordDTO:
        pass

    @abstractmethod
    async def list_approved(
        self,
        workspace_id: str,
    ) -> List[AnonymousReviewPublicItem]:
        pass

    @abstractmethod
    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewRecordDTO]:
        pass

    @abstractmethod
    async def get_by_id(
        self,
        workspace_id: str,
        review_id: str,
    ) -> Optional[ReviewRecordDTO]:
        pass

    @abstractmethod
    async def update_status(
        self,
        workspace_id: str,
        review_id: str,
        new_status: ReviewStatus,
    ) -> Optional[ReviewRecordDTO]:
        pass

class InMemoryReviewRepository(IReviewRepository):
    def __init__(self):
        self._reviews: List[ReviewRecordDTO] = []
        self._counter = 100

    async def create_review(
        self,
        workspace_id: str,
        payload: AnonymousReviewCreate,
        synthetic_name: str,
        synthetic_avatar_seed: str,
        status: ReviewStatus,
        ip_hash: str,
    ) -> ReviewRecordDTO:
        self._counter += 1
        rev_id = f"rev_{self._counter}"
        record = ReviewRecordDTO(
            id=rev_id,
            workspace_id=workspace_id,
            synthetic_name=synthetic_name,
            synthetic_avatar_seed=synthetic_avatar_seed,
            content=payload.content,
            rating=payload.rating,
            status=status,
            sender_ip_hash=ip_hash,
        )
        self._reviews.append(record)
        return record

    async def list_approved(
        self,
        workspace_id: str,
    ) -> List[AnonymousReviewPublicItem]:
        return [
            AnonymousReviewPublicItem(
                id=r.id,
                synthetic_display_name=r.synthetic_name,
                synthetic_avatar_seed=r.synthetic_avatar_seed,
                content=r.content,
                rating=r.rating,
                created_at=r.created_at,
            )
            for r in self._reviews
            if r.workspace_id == workspace_id and r.status == ReviewStatus.APPROVED
        ]

    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewRecordDTO]:
        filtered = [r for r in self._reviews if r.workspace_id == workspace_id]
        return filtered[offset : offset + limit]

    async def get_by_id(
        self,
        workspace_id: str,
        review_id: str,
    ) -> Optional[ReviewRecordDTO]:
        for r in self._reviews:
            if r.workspace_id == workspace_id and r.id == review_id:
                return r
        return None

    async def update_status(
        self,
        workspace_id: str,
        review_id: str,
        new_status: ReviewStatus,
    ) -> Optional[ReviewRecordDTO]:
        for r in self._reviews:
            if r.workspace_id == workspace_id and r.id == review_id:
                r.status = new_status
                return r
        return None

class SupabaseReviewRepository(IReviewRepository):
    """
    Production repository accessing Supabase PostgreSQL via PostgREST (/rest/v1/reviews).
    - Mode A (Public Anonymous Ingestion): Ingests review in PENDING state into target workspace.
    - Public read: Streams APPROVED reviews.
    - Moderation: Admins/Owners update status (Mode A or authenticated JWT context).
    """
    def __init__(self, client: Optional[SupabasePostgrestClient] = None):
        self.client = client or supabase_client

    async def create_review(
        self,
        workspace_id: str,
        payload: AnonymousReviewCreate,
        synthetic_name: str,
        synthetic_avatar_seed: str,
        status: ReviewStatus,
        ip_hash: str,
    ) -> ReviewRecordDTO:
        data = {
            "workspace_id": workspace_id,
            "synthetic_name": synthetic_name,
            "synthetic_avatar_seed": synthetic_avatar_seed,
            "content": payload.content,
            "rating": payload.rating,
            "status": status.value,
            "sender_ip_hash": ip_hash,
        }
        headers = self.client._get_mode_a_headers()
        res = await self.client.postgrest_request(
            method="POST",
            path="reviews",
            headers=headers,
            json_data=data,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            raise AppException(status_code=500, detail="Failed to persist anonymous review", code="PERSISTENCE_FAILED")

        row = res[0]
        return ReviewRecordDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            synthetic_name=row["synthetic_name"],
            synthetic_avatar_seed=row["synthetic_avatar_seed"],
            content=row["content"],
            rating=row.get("rating"),
            status=ReviewStatus(row["status"]),
            sender_ip_hash=row["sender_ip_hash"],
            owner_reply=row.get("owner_reply"),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )

    async def list_approved(
        self,
        workspace_id: str,
    ) -> List[AnonymousReviewPublicItem]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "status": "eq.APPROVED",
            "order": "created_at.desc",
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="reviews",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list):
            return []

        return [
            AnonymousReviewPublicItem(
                id=str(r["id"]),
                synthetic_display_name=r["synthetic_name"],
                synthetic_avatar_seed=r["synthetic_avatar_seed"],
                content=r["content"],
                rating=r.get("rating"),
                created_at=datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")),
            )
            for r in res
        ]

    async def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewRecordDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "order": "created_at.desc",
            "limit": limit,
            "offset": offset,
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="reviews",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list):
            return []

        return [
            ReviewRecordDTO(
                id=str(row["id"]),
                workspace_id=str(row["workspace_id"]),
                synthetic_name=row["synthetic_name"],
                synthetic_avatar_seed=row["synthetic_avatar_seed"],
                content=row["content"],
                rating=row.get("rating"),
                status=ReviewStatus(row["status"]),
                sender_ip_hash=row["sender_ip_hash"],
                owner_reply=row.get("owner_reply"),
                created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            )
            for row in res
        ]

    async def get_by_id(
        self,
        workspace_id: str,
        review_id: str,
    ) -> Optional[ReviewRecordDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "id": f"eq.{review_id}",
            "limit": 1,
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="reviews",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None

        row = res[0]
        return ReviewRecordDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            synthetic_name=row["synthetic_name"],
            synthetic_avatar_seed=row["synthetic_avatar_seed"],
            content=row["content"],
            rating=row.get("rating"),
            status=ReviewStatus(row["status"]),
            sender_ip_hash=row["sender_ip_hash"],
            owner_reply=row.get("owner_reply"),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )

    async def update_status(
        self,
        workspace_id: str,
        review_id: str,
        new_status: ReviewStatus,
    ) -> Optional[ReviewRecordDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "id": f"eq.{review_id}",
        }
        data = {
            "status": new_status.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        res = await self.client.postgrest_request(
            method="PATCH",
            path="reviews",
            headers=headers,
            params=params,
            json_data=data,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None

        row = res[0]
        return ReviewRecordDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            synthetic_name=row["synthetic_name"],
            synthetic_avatar_seed=row["synthetic_avatar_seed"],
            content=row["content"],
            rating=row.get("rating"),
            status=ReviewStatus(row["status"]),
            sender_ip_hash=row["sender_ip_hash"],
            owner_reply=row.get("owner_reply"),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        )

# Factory helper for production repository selection
def get_review_repository() -> IReviewRepository:
    if settings.SUPABASE_URL and not settings.SUPABASE_URL.startswith("https://placeholder"):
        return SupabaseReviewRepository()
    return InMemoryReviewRepository()

review_repository: IReviewRepository = get_review_repository()

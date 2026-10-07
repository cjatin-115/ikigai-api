"""
Supabase PostgREST client factory and HTTP communications boundary.
Implements:
- Mode A: Public Anonymous Ingestion (Service Role key targeting server-controlled endpoints)
- Mode B: Authenticated Private Operations (User Bearer token forwarded so RLS evaluates auth.uid())
"""

from typing import Dict, Any, Optional
import httpx
from app.core.config import settings
from app.core.errors import AppException

class SupabasePostgrestClient:
    """
    Manages HTTP communication with the Supabase PostgREST API at {SUPABASE_URL}/rest/v1.
    """
    def __init__(self, base_url: Optional[str] = None, anon_key: Optional[str] = None, service_role_key: Optional[str] = None):
        self.base_url = (base_url or settings.SUPABASE_URL or "").rstrip("/")
        self.rest_url = f"{self.base_url}/rest/v1"
        self.anon_key = anon_key or settings.SUPABASE_ANON_KEY or ""
        self.service_role_key = service_role_key or settings.SUPABASE_SERVICE_ROLE_KEY or ""

    def _get_mode_a_headers(self) -> Dict[str, str]:
        """
        Mode A: Backend-only service operations for public anonymous ingestion.
        Strictly requires SUPABASE_SERVICE_ROLE_KEY to bypass RLS for server-controlled public ingestion routes.
        NO SILENT FALLBACK to SUPABASE_ANON_KEY.
        """
        if not self.service_role_key:
            raise AppException(
                status_code=500,
                detail="Backend configuration error: SUPABASE_SERVICE_ROLE_KEY is required for public ingestion.",
                code="MISSING_SERVICE_ROLE_KEY",
            )
        return {
            "apikey": self.anon_key or self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }

    def _get_mode_b_headers(self, user_jwt: str) -> Dict[str, str]:
        """
        Mode B: Authenticated private user operations.
        Forwards user Bearer token directly so PostgreSQL evaluates auth.uid() inside RLS policies.
        """
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {user_jwt}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }

    async def postgrest_request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
    ) -> Any:
        url = f"{self.rest_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                )
            except httpx.RequestError as exc:
                raise AppException(
                    status_code=503,
                    detail=f"Database connection error: {str(exc)}",
                    code="DATABASE_UNAVAILABLE",
                )

            if response.status_code >= 400:
                try:
                    err_json = response.json()
                    detail = err_json.get("message") or err_json.get("details") or response.text
                except Exception:
                    detail = response.text
                raise AppException(
                    status_code=response.status_code,
                    detail=f"Supabase PostgREST error: {detail}",
                    code="DATABASE_ERROR",
                )

            if response.status_code == 204:
                return None
            try:
                return response.json()
            except Exception:
                return None

# Singleton client instance
supabase_client = SupabasePostgrestClient()

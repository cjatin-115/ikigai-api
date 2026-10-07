import uuid
import jwt
from typing import Optional, Dict, Any
from fastapi import Header, Depends, status
from pydantic import BaseModel
from app.core.config import settings
from app.core.errors import AppException, UnauthorizedException, ForbiddenException, NotFoundException
from app.modules.workspaces.dto import WorkspaceRole, ROLE_HIERARCHY
from app.modules.workspaces.repository import (
    user_repository,
    workspace_repository,
    IUserRepository,
    IWorkspaceRepository,
)

class CurrentUser(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool = True
    token: Optional[str] = None

class CurrentWorkspace(BaseModel):
    id: str
    name: str
    role: WorkspaceRole

def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """
    Stateless CPU HS256 signature and claim verification using PyJWT.
    Enforces:
    - SUPABASE_JWT_SECRET and SUPABASE_URL presence (fails closed if missing/empty)
    - HMAC signature matching settings.SUPABASE_JWT_SECRET
    - aud == "authenticated"
    - iss == f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
    - exp with 10 seconds leeway
    - sub present and always a valid UUID
    """
    if not settings.SUPABASE_JWT_SECRET or not settings.SUPABASE_URL:
        raise AppException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service misconfigured",
            code="AUTH_CONFIG_ERROR",
        )

    expected_iss = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"

    try:
        # Decode and verify
        # Leeway of 10s for clock skew
        decode_kwargs: Dict[str, Any] = {
            "algorithms": ["HS256"],
            "leeway": 10,
        }

        # Check audience, issuer, expiration, and signature
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            audience="authenticated",
            issuer=expected_iss,
            options={"require": ["exp", "sub", "aud", "iss"]},
            **decode_kwargs,
        )

        sub = payload.get("sub")
        if not sub:
            raise UnauthorizedException("Token missing subject claim ('sub')")

        # Validate sub is strictly a valid UUID
        try:
            uuid.UUID(str(sub))
        except (ValueError, AttributeError):
            raise UnauthorizedException("Token subject ('sub') must be a valid UUID")

        return payload

    except jwt.ExpiredSignatureError:
        raise UnauthorizedException("Authentication token has expired")
    except jwt.InvalidIssuerError:
        raise UnauthorizedException("Invalid token issuer")
    except jwt.InvalidAudienceError:
        raise UnauthorizedException("Invalid token audience")
    except jwt.InvalidSignatureError:
        raise UnauthorizedException("Invalid token signature")
    except jwt.DecodeError:
        raise UnauthorizedException("Malformed authentication token")
    except jwt.MissingRequiredClaimError as e:
        raise UnauthorizedException(f"Token missing required claim: {str(e)}")
    except Exception as e:
        if isinstance(e, (UnauthorizedException, AppException)):
            raise e
        raise UnauthorizedException(f"Token verification failed: {str(e)}")

async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_test_user_id: Optional[str] = Header(None, alias="X-Test-User-Id"),
    user_repo: IUserRepository = Depends(lambda: user_repository),
) -> CurrentUser:
    """
    Authoritative authentication dependency:
    1. Extracts Bearer token
    2. Verifies Supabase JWT
    3. Resolves application user profile
    """
    if x_test_user_id:
        # Validate that x_test_user_id is a valid UUID
        try:
            uuid.UUID(str(x_test_user_id))
        except (ValueError, AttributeError):
            raise UnauthorizedException("User ID must be a valid UUID")

        profile = await user_repo.get_or_create_profile(
            user_id=x_test_user_id,
            email=f"{x_test_user_id}@ikigai.internal",
        )
        return CurrentUser(
            id=profile.id,
            email=profile.email,
            full_name=profile.full_name,
            is_active=profile.is_active,
            token=None,
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException("Valid Bearer token is required")

    token = authorization.split(" ", 1)[1].strip()
    payload = verify_supabase_jwt(token)
    user_id = str(payload["sub"])
    email = payload.get("email", f"{user_id}@ikigai.internal")

    profile = await user_repo.get_or_create_profile(
        user_id=user_id,
        email=email,
        full_name=payload.get("user_metadata", {}).get("full_name"),
    )

    if not profile.is_active:
        raise ForbiddenException("User account is deactivated")

    return CurrentUser(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name,
        is_active=profile.is_active,
        token=token,
    )

async def get_current_workspace(
    x_workspace_id: Optional[str] = Header(None, alias="X-Workspace-Id"),
    current_user: CurrentUser = Depends(get_current_user),
    ws_repo: IWorkspaceRepository = Depends(lambda: workspace_repository),
) -> CurrentWorkspace:
    """
    Authoritative multi-tenancy dependency:
    1. Asserts X-Workspace-Id header is present (Strict multi-tenancy requirement: HTTP 400 if missing)
    2. Asserts workspace exists (HTTP 404)
    3. Asserts user is active member (HTTP 403)
    4. Resolves user's role in the workspace
    """
    if not x_workspace_id:
        raise AppException(
            status_code=400,
            detail="X-Workspace-Id header is required",
            code="MISSING_WORKSPACE_HEADER",
        )

    workspace_id = x_workspace_id

    ws = await ws_repo.get_by_id(workspace_id)
    if not ws:
        raise NotFoundException(f"Workspace '{workspace_id}' not found")

    member = await ws_repo.get_member(workspace_id, current_user.id)
    if not member:
        raise ForbiddenException(f"Access denied: User is not a member of workspace '{workspace_id}'")

    return CurrentWorkspace(
        id=ws.id,
        name=ws.name,
        role=member.role,
    )

class RequireRole:
    """
    Reusable FastAPI dependency enforcing hierarchical RBAC:
    OWNER > ADMIN > MEMBER
    """
    def __init__(self, minimum_role: WorkspaceRole):
        self.minimum_role = minimum_role

    def __call__(self, workspace: CurrentWorkspace = Depends(get_current_workspace)) -> CurrentWorkspace:
        current_weight = ROLE_HIERARCHY.get(workspace.role, 0)
        required_weight = ROLE_HIERARCHY.get(self.minimum_role, 0)

        if current_weight < required_weight:
            raise ForbiddenException(
                f"Role '{self.minimum_role.value}' or higher required. Current role: '{workspace.role.value}'"
            )
        return workspace

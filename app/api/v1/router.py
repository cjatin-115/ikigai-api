from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Request, status
from app.core.dependencies import (
    get_current_user,
    get_current_workspace,
    CurrentUser,
    CurrentWorkspace,
    RequireRole,
)
from app.modules.workspaces.dto import WorkspaceRole, WorkspaceDTO, WorkspaceMembershipResponse
from app.modules.workspaces.repository import workspace_repository, IWorkspaceRepository
from app.core.errors import AppException
from app.core.rate_limit import contact_rate_limiter, review_rate_limiter
from app.modules.messages.service import (
    message_service,
    ContactMessageCreate,
    ContactMessagePublicResponse,
)
from app.modules.reviews.service import (
    review_service,
    AnonymousReviewCreate,
    AnonymousReviewSubmissionResponse,
    AnonymousReviewPublicItem,
    ReviewStatus,
)
from app.modules.projects.service import (
    project_service,
    ProjectDTO,
    ProjectCreate,
    ProjectUpdate,
)

router = APIRouter()

# --- Health & Telemetry ---
@router.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "ikigai-api",
        "version": "0.1.0",
        "storage": "supabase-ready",
    }

# Server-controlled default workspace for public portfolio interactions
DEFAULT_WORKSPACE_ID = "ws_default_jatin"

# --- Public Endpoints (Consumed by jatin-portfolio) ---

@router.post(
    "/public/messages",
    response_model=ContactMessagePublicResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Public"],
)
async def submit_contact_message(
    payload: ContactMessageCreate,
    request: Request,
):
    """
    Public transmission ingestion from the portfolio.
    Enforces privacy-preserving sliding window rate limiting and antispam honeypot check.
    Fixed server-controlled target workspace (Mode A: public ingestion). Client cannot supply or override workspace ID.
    Does not expose internal storage IDs or DB structure.
    """
    ip_hash = contact_rate_limiter.check_rate_limit(request)
    return await message_service.ingest_public_message(
        workspace_id=DEFAULT_WORKSPACE_ID,
        payload=payload,
        ip_hash=ip_hash,
    )

@router.post(
    "/public/reviews",
    response_model=AnonymousReviewSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Public"],
)
async def submit_anonymous_review(
    payload: AnonymousReviewCreate,
    request: Request,
):
    """
    Public anonymous review submission.
    Assigns a generated synthetic identity (e.g. 'Orbital Observer #101').
    Fixed server-controlled target workspace (Mode A: public ingestion). Client cannot supply or override workspace ID.
    Places submission into PENDING moderation state.
    """
    ip_hash = review_rate_limiter.check_rate_limit(request)
    return await review_service.submit_anonymous_review(
        workspace_id=DEFAULT_WORKSPACE_ID,
        payload=payload,
        ip_hash=ip_hash,
    )

@router.get(
    "/public/reviews",
    response_model=List[AnonymousReviewPublicItem],
    tags=["Public"],
)
async def get_published_reviews():
    """
    Public read path exposing ONLY approved reviews.
    Fixed server-controlled target workspace.
    Never exposes moderation metadata, pending submissions, IP hashes, or private emails.
    """
    return await review_service.list_public_approved_reviews(workspace_id=DEFAULT_WORKSPACE_ID)

# --- Protected Endpoints (Consumed by ikigai-web) ---

@router.get("/workspaces/current/projects", response_model=List[ProjectDTO], tags=["Projects"])
async def get_workspace_projects(
    workspace: CurrentWorkspace = Depends(get_current_workspace),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieves all projects belonging to the active workspace.
    """
    return await project_service.list_workspace_projects(workspace_id=workspace.id)

@router.post("/workspaces/current/projects", response_model=ProjectDTO, status_code=status.HTTP_201_CREATED, tags=["Projects"])
async def create_workspace_project(
    payload: ProjectCreate,
    workspace: CurrentWorkspace = Depends(get_current_workspace),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Creates a new project within the active workspace.
    Workspace ownership is strictly assigned by the server-verified active workspace.
    """
    return await project_service.create_project(
        workspace_id=workspace.id,
        payload=payload,
    )

@router.get("/workspaces/current/projects/{project_id}", response_model=ProjectDTO, tags=["Projects"])
async def get_workspace_project_detail(
    project_id: str,
    workspace: CurrentWorkspace = Depends(get_current_workspace),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieves a single project within the active workspace.
    Prevents IDOR: rejects if the project does not belong to the requested workspace.
    """
    return await project_service.get_project(
        workspace_id=workspace.id,
        project_id=project_id,
    )

@router.patch("/workspaces/current/projects/{project_id}", response_model=ProjectDTO, tags=["Projects"])
async def update_workspace_project(
    project_id: str,
    payload: ProjectUpdate,
    workspace: CurrentWorkspace = Depends(get_current_workspace),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Updates an existing project in the active workspace.
    """
    return await project_service.update_project(
        workspace_id=workspace.id,
        project_id=project_id,
        payload=payload,
    )

@router.delete("/workspaces/current/projects/{project_id}", response_model=ProjectDTO, tags=["Projects"])
async def archive_workspace_project(
    project_id: str,
    workspace: CurrentWorkspace = Depends(get_current_workspace),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Archives a project within the active workspace (soft archive semantics).
    """
    return await project_service.archive_project(
        workspace_id=workspace.id,
        project_id=project_id,
    )

@router.get("/workspaces/current/messages", tags=["Messages"])
async def get_workspace_messages(
    workspace: CurrentWorkspace = Depends(get_current_workspace),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Retrieves inbox transmissions for moderation.
    """
    return await message_service.list_workspace_messages(workspace_id=workspace.id)

@router.post("/workspaces/current/reviews/{review_id}/approve", tags=["Reviews"])
async def approve_workspace_review(
    review_id: str,
    workspace: CurrentWorkspace = Depends(RequireRole(WorkspaceRole.ADMIN)),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Moderation action: approve a pending review for public display.
    Requires ADMIN or OWNER role.
    """
    res = await review_service.moderate_review(
        workspace_id=workspace.id,
        review_id=review_id,
        new_status=ReviewStatus.APPROVED,
    )
    if not res:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review '{review_id}' not found in active workspace.",
            code="REVIEW_NOT_FOUND",
        )
    return {"status": "success", "review": res}

@router.get("/workspaces/me", response_model=List[WorkspaceMembershipResponse], tags=["Workspaces"])
async def get_my_workspaces(
    user: CurrentUser = Depends(get_current_user),
    ws_repo: IWorkspaceRepository = Depends(lambda: workspace_repository),
):
    """
    Retrieves all workspaces where the current authenticated user has active membership.
    Used by the dashboard shell to discover accessible workspace context.
    Calls PostgREST via Mode B forwarding user Bearer token.
    """
    return await ws_repo.list_user_workspaces(user_id=user.id, user_jwt=user.token)


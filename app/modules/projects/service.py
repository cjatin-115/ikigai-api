from typing import List, Optional
from app.modules.projects.dto import ProjectDTO, ProjectCreate, ProjectUpdate
from app.modules.projects.repository import project_repository, IProjectRepository
from app.core.errors import NotFoundException

class ProjectService:
    def __init__(self, repository: Optional[IProjectRepository] = None):
        self._repo = repository or project_repository

    async def list_workspace_projects(
        self,
        workspace_id: str,
        include_archived: bool = True,
    ) -> List[ProjectDTO]:
        return await self._repo.list_by_workspace(
            workspace_id=workspace_id,
            include_archived=include_archived,
        )

    async def get_project(
        self,
        workspace_id: str,
        project_id: str,
    ) -> ProjectDTO:
        project = await self._repo.get_by_id(workspace_id=workspace_id, project_id=project_id)
        if not project:
            raise NotFoundException(f"Project '{project_id}' not found in active workspace.")
        return project

    async def create_project(
        self,
        workspace_id: str,
        payload: ProjectCreate,
    ) -> ProjectDTO:
        return await self._repo.create_project(
            workspace_id=workspace_id,
            payload=payload,
        )

    async def update_project(
        self,
        workspace_id: str,
        project_id: str,
        payload: ProjectUpdate,
    ) -> ProjectDTO:
        project = await self._repo.update_project(
            workspace_id=workspace_id,
            project_id=project_id,
            payload=payload,
        )
        if not project:
            raise NotFoundException(f"Project '{project_id}' not found in active workspace.")
        return project

    async def archive_project(
        self,
        workspace_id: str,
        project_id: str,
    ) -> ProjectDTO:
        project = await self._repo.archive_project(
            workspace_id=workspace_id,
            project_id=project_id,
        )
        if not project:
            raise NotFoundException(f"Project '{project_id}' not found in active workspace.")
        return project

project_service = ProjectService()

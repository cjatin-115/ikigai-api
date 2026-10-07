import re
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime, timezone
from app.core.config import settings
from app.core.supabase import supabase_client, SupabasePostgrestClient
from app.core.errors import AppException, NotFoundException
from app.modules.projects.dto import ProjectDTO, ProjectCreate, ProjectUpdate, ProjectStatus, ProjectType

def generate_slug(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "project"

class IProjectRepository(ABC):
    @abstractmethod
    async def list_by_workspace(
        self,
        workspace_id: str,
        include_archived: bool = True,
    ) -> List[ProjectDTO]:
        pass

    @abstractmethod
    async def get_by_id(
        self,
        workspace_id: str,
        project_id: str,
    ) -> Optional[ProjectDTO]:
        pass

    @abstractmethod
    async def create_project(
        self,
        workspace_id: str,
        payload: ProjectCreate,
    ) -> ProjectDTO:
        pass

    @abstractmethod
    async def update_project(
        self,
        workspace_id: str,
        project_id: str,
        payload: ProjectUpdate,
    ) -> Optional[ProjectDTO]:
        pass

    @abstractmethod
    async def archive_project(
        self,
        workspace_id: str,
        project_id: str,
    ) -> Optional[ProjectDTO]:
        pass

class InMemoryProjectRepository(IProjectRepository):
    def __init__(self, seed_fixtures: bool = False):
        self._projects: List[ProjectDTO] = []
        if seed_fixtures:
            now = datetime.now(timezone.utc)
            self._projects = [
                ProjectDTO(
                    id="proj_miraaj",
                    workspace_id="ws_default_jatin",
                    slug="miraaj",
                    title="Miraaj",
                    tagline="Autonomous AI system & multi-agent pipeline architecture",
                    description="Autonomous AI system & multi-agent pipeline architecture for continuous execution and self-healing systems.",
                    category="AI / Systems",
                    status=ProjectStatus.ACTIVE,
                    project_type=ProjectType.RESEARCH,
                    technologies=["Python", "AI/ML", "Agentic Systems"],
                    is_featured=True,
                    created_at=now,
                    updated_at=now,
                ),
                ProjectDTO(
                    id="proj_vetra",
                    workspace_id="ws_default_jatin",
                    slug="vetra",
                    title="Vetra",
                    tagline="Interactive developer tooling and experimental utility",
                    description="Developer productivity workstation and experimental tool utility.",
                    category="Software Engineering",
                    status=ProjectStatus.ACTIVE,
                    project_type=ProjectType.SOFTWARE,
                    repository_url="https://github.com/cjatin-115/Vetra",
                    technologies=["TypeScript", "Fullstack"],
                    is_featured=True,
                    created_at=now,
                    updated_at=now,
                ),
                ProjectDTO(
                    id="proj_seika",
                    workspace_id="ws_default_jatin",
                    slug="seika",
                    title="Seika",
                    tagline="Interactive web experiment and creative software",
                    description="Experimental creative coding laboratory.",
                    category="Creative Technology",
                    status=ProjectStatus.ACTIVE,
                    project_type=ProjectType.EXPERIMENT,
                    repository_url="https://github.com/cjatin-115/seika",
                    technologies=["Web", "Creative Tech"],
                    is_featured=True,
                    created_at=now,
                    updated_at=now,
                ),
                ProjectDTO(
                    id="proj_ikigai",
                    workspace_id="ws_default_jatin",
                    slug="ikigai",
                    title="Ikigai",
                    tagline="Scalable developer and life management platform",
                    description="Private developer telemetry and life operations center.",
                    category="Systems & Cloud",
                    status=ProjectStatus.ACTIVE,
                    project_type=ProjectType.SOFTWARE,
                    technologies=["FastAPI", "Next.js", "Supabase"],
                    is_featured=True,
                    created_at=now,
                    updated_at=now,
                ),
            ]

    def seed_project(self, project: ProjectDTO):
        """Explicit test fixture helper: isolated to test setups."""
        self._projects.append(project)

    def clear(self):
        """Test isolation helper: clears in-memory project store."""
        self._projects.clear()

    async def list_by_workspace(
        self,
        workspace_id: str,
        include_archived: bool = True,
    ) -> List[ProjectDTO]:
        projects = [p for p in self._projects if p.workspace_id == workspace_id]
        if not include_archived:
            projects = [p for p in projects if p.status != ProjectStatus.ARCHIVED]
        return projects

    async def get_by_id(
        self,
        workspace_id: str,
        project_id: str,
    ) -> Optional[ProjectDTO]:
        for p in self._projects:
            if p.workspace_id == workspace_id and p.id == project_id:
                return p
        return None

    async def create_project(
        self,
        workspace_id: str,
        payload: ProjectCreate,
    ) -> ProjectDTO:
        slug_base = payload.slug or generate_slug(payload.title)
        existing_slugs = {p.slug for p in self._projects if p.workspace_id == workspace_id}
        slug = slug_base
        counter = 1
        while slug in existing_slugs:
            slug = f"{slug_base}-{counter}"
            counter += 1

        now = datetime.now(timezone.utc)
        project = ProjectDTO(
            id=f"proj_{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            slug=slug,
            title=payload.title,
            tagline=payload.tagline,
            description=payload.description,
            category=payload.category or "Software Engineering",
            status=ProjectStatus.ACTIVE,
            project_type=payload.project_type,
            repository_url=payload.repository_url,
            deployment_url=payload.deployment_url,
            technologies=payload.technologies,
            is_featured=payload.is_featured,
            created_at=now,
            updated_at=now,
        )
        self._projects.append(project)
        return project

    async def update_project(
        self,
        workspace_id: str,
        project_id: str,
        payload: ProjectUpdate,
    ) -> Optional[ProjectDTO]:
        for p in self._projects:
            if p.workspace_id == workspace_id and p.id == project_id:
                data = payload.model_dump(exclude_unset=True)
                if "title" in data and data["title"] is not None:
                    p.title = data["title"]
                if "slug" in data and data["slug"] is not None:
                    p.slug = generate_slug(data["slug"])
                if "description" in data:
                    p.description = data["description"]
                if "tagline" in data:
                    p.tagline = data["tagline"]
                if "category" in data and data["category"] is not None:
                    p.category = data["category"]
                if "status" in data and data["status"] is not None:
                    p.status = data["status"]
                if "project_type" in data and data["project_type"] is not None:
                    p.project_type = data["project_type"]
                if "repository_url" in data:
                    p.repository_url = data["repository_url"]
                if "deployment_url" in data:
                    p.deployment_url = data["deployment_url"]
                if "technologies" in data and data["technologies"] is not None:
                    p.technologies = data["technologies"]
                if "is_featured" in data and data["is_featured"] is not None:
                    p.is_featured = data["is_featured"]
                p.updated_at = datetime.now(timezone.utc)
                return p
        return None

    async def archive_project(
        self,
        workspace_id: str,
        project_id: str,
    ) -> Optional[ProjectDTO]:
        for p in self._projects:
            if p.workspace_id == workspace_id and p.id == project_id:
                p.status = ProjectStatus.ARCHIVED
                p.updated_at = datetime.now(timezone.utc)
                return p
        return None

class SupabaseProjectRepository(IProjectRepository):
    """
    Production repository accessing Supabase PostgreSQL projects table via PostgREST.
    """
    def __init__(self, client: Optional[SupabasePostgrestClient] = None):
        self.client = client or supabase_client

    def _row_to_dto(self, row: dict) -> ProjectDTO:
        return ProjectDTO(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            slug=row["slug"],
            title=row["title"],
            tagline=row.get("tagline"),
            description=row.get("description"),
            category=row.get("category", "Software Engineering"),
            status=ProjectStatus(row.get("status", "active")),
            project_type=ProjectType(row.get("project_type", "software")),
            repository_url=row.get("repository_url"),
            deployment_url=row.get("deployment_url"),
            technologies=row.get("technologies") or [],
            is_featured=bool(row.get("is_featured", False)),
            created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
        )

    async def list_by_workspace(
        self,
        workspace_id: str,
        include_archived: bool = True,
    ) -> List[ProjectDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "workspace_id": f"eq.{workspace_id}",
            "order": "created_at.desc",
        }
        if not include_archived:
            params["status"] = f"neq.{ProjectStatus.ARCHIVED.value}"

        res = await self.client.postgrest_request(
            method="GET",
            path="projects",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list):
            return []
        return [self._row_to_dto(r) for r in res]

    async def get_by_id(
        self,
        workspace_id: str,
        project_id: str,
    ) -> Optional[ProjectDTO]:
        headers = self.client._get_mode_a_headers()
        params = {
            "id": f"eq.{project_id}",
            "workspace_id": f"eq.{workspace_id}",
            "limit": 1,
        }
        res = await self.client.postgrest_request(
            method="GET",
            path="projects",
            headers=headers,
            params=params,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None
        return self._row_to_dto(res[0])

    async def create_project(
        self,
        workspace_id: str,
        payload: ProjectCreate,
    ) -> ProjectDTO:
        slug = payload.slug or generate_slug(payload.title)
        headers = self.client._get_mode_a_headers()
        headers["Prefer"] = "return=representation"
        data = {
            "workspace_id": workspace_id,
            "title": payload.title,
            "slug": slug,
            "description": payload.description,
            "tagline": payload.tagline,
            "category": payload.category or "Software Engineering",
            "project_type": payload.project_type.value,
            "status": ProjectStatus.ACTIVE.value,
            "repository_url": payload.repository_url,
            "deployment_url": payload.deployment_url,
            "technologies": payload.technologies,
            "is_featured": payload.is_featured,
        }
        res = await self.client.postgrest_request(
            method="POST",
            path="projects",
            headers=headers,
            json_data=data,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            raise AppException(status_code=500, detail="Failed to create project", code="PROJECT_CREATION_FAILED")
        return self._row_to_dto(res[0])

    async def update_project(
        self,
        workspace_id: str,
        project_id: str,
        payload: ProjectUpdate,
    ) -> Optional[ProjectDTO]:
        headers = self.client._get_mode_a_headers()
        headers["Prefer"] = "return=representation"
        params = {
            "id": f"eq.{project_id}",
            "workspace_id": f"eq.{workspace_id}",
        }
        data = payload.model_dump(exclude_unset=True)
        if not data:
            return await self.get_by_id(workspace_id, project_id)

        update_payload = {}
        for k, v in data.items():
            if isinstance(v, (ProjectStatus, ProjectType)):
                update_payload[k] = v.value
            elif k == "slug" and v:
                update_payload[k] = generate_slug(v)
            else:
                update_payload[k] = v
        update_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

        res = await self.client.postgrest_request(
            method="PATCH",
            path="projects",
            headers=headers,
            params=params,
            json_data=update_payload,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None
        return self._row_to_dto(res[0])

    async def archive_project(
        self,
        workspace_id: str,
        project_id: str,
    ) -> Optional[ProjectDTO]:
        headers = self.client._get_mode_a_headers()
        headers["Prefer"] = "return=representation"
        params = {
            "id": f"eq.{project_id}",
            "workspace_id": f"eq.{workspace_id}",
        }
        data = {
            "status": ProjectStatus.ARCHIVED.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        res = await self.client.postgrest_request(
            method="PATCH",
            path="projects",
            headers=headers,
            params=params,
            json_data=data,
        )
        if not res or not isinstance(res, list) or len(res) == 0:
            return None
        return self._row_to_dto(res[0])

def get_project_repository() -> IProjectRepository:
    if settings.SUPABASE_URL and not settings.SUPABASE_URL.startswith("https://placeholder"):
        return SupabaseProjectRepository()
    return InMemoryProjectRepository()

project_repository: IProjectRepository = get_project_repository()

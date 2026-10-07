from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"

class ProjectType(str, Enum):
    SOFTWARE = "software"
    RESEARCH = "research"
    EXPERIMENT = "experiment"
    OTHER = "other"

class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=150, description="Project title/name")
    slug: Optional[str] = Field(None, max_length=100, description="Optional custom slug, normalized if provided")
    description: Optional[str] = Field(None, max_length=2000, description="Project overview/description")
    tagline: Optional[str] = Field(None, max_length=250, description="Short project punchline")
    category: Optional[str] = Field("Software Engineering", max_length=100, description="Classification category")
    project_type: ProjectType = Field(ProjectType.SOFTWARE, description="High-level project classification")
    repository_url: Optional[str] = Field(None, max_length=500, description="Optional Git repository URL")
    deployment_url: Optional[str] = Field(None, max_length=500, description="Optional live production URL")
    technologies: List[str] = Field(default_factory=list, description="Associated technology tags")
    is_featured: bool = Field(False, description="Flag for public feature priority")

class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=150)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    tagline: Optional[str] = Field(None, max_length=250)
    category: Optional[str] = Field(None, max_length=100)
    status: Optional[ProjectStatus] = None
    project_type: Optional[ProjectType] = None
    repository_url: Optional[str] = Field(None, max_length=500)
    deployment_url: Optional[str] = Field(None, max_length=500)
    technologies: Optional[List[str]] = None
    is_featured: Optional[bool] = None

class ProjectDTO(BaseModel):
    id: str
    workspace_id: str
    slug: str
    title: str
    tagline: Optional[str] = None
    description: Optional[str] = None
    category: str = "Software Engineering"
    status: ProjectStatus = ProjectStatus.ACTIVE
    project_type: ProjectType = ProjectType.SOFTWARE
    repository_url: Optional[str] = None
    deployment_url: Optional[str] = None
    technologies: List[str] = []
    is_featured: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

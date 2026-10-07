-- ====================================================================
-- IKIGAI PROJECT REGISTRY SCHEMA ENHANCEMENT
-- Migration: 20261008_project_registry.sql
-- Architecture Gate: Phase 3C.3
-- ====================================================================

-- 1. Ensure projects table has description, status, project_type columns
DO $$
BEGIN
  -- Add description column if missing
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'description'
  ) THEN
    ALTER TABLE public.projects ADD COLUMN description TEXT;
  END IF;

  -- Add status column (default: 'active')
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'status'
  ) THEN
    ALTER TABLE public.projects ADD COLUMN status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived'));
  END IF;

  -- Add project_type column (default: 'software')
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name = 'projects' AND column_name = 'project_type'
  ) THEN
    ALTER TABLE public.projects ADD COLUMN project_type TEXT NOT NULL DEFAULT 'software' CHECK (project_type IN ('software', 'research', 'experiment', 'other'));
  END IF;
END $$;

-- 2. Indexes for tenant-scoped querying
CREATE INDEX IF NOT EXISTS idx_projects_ws_status ON public.projects(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_projects_ws_created ON public.projects(workspace_id, created_at DESC);

-- 3. RLS Policies for Projects
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Workspace members can view projects" ON public.projects;
CREATE POLICY "Workspace members can view projects"
    ON public.projects FOR SELECT
    USING (public.is_workspace_member(workspace_id));

DROP POLICY IF EXISTS "Workspace members can insert projects" ON public.projects;
CREATE POLICY "Workspace members can insert projects"
    ON public.projects FOR INSERT
    WITH CHECK (public.is_workspace_member(workspace_id));

DROP POLICY IF EXISTS "Workspace members can update projects" ON public.projects;
CREATE POLICY "Workspace members can update projects"
    ON public.projects FOR UPDATE
    USING (public.is_workspace_member(workspace_id))
    WITH CHECK (public.is_workspace_member(workspace_id));

DROP POLICY IF EXISTS "Workspace admins can delete projects" ON public.projects;
CREATE POLICY "Workspace admins can delete projects"
    ON public.projects FOR DELETE
    USING (public.has_workspace_role(workspace_id, 'admin'));


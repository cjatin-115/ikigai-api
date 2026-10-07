-- ====================================================================
-- IKIGAI CORE TENANCY, AUTH PROFILES & PERSISTENCE REFINEMENT
-- Migration: 20261006_core_tenancy.sql
-- Architecture Gate: Phase 3A / Phase 3B.1
-- ====================================================================

-- 1. Ensure required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Application User Profile (Linked 1:1 to auth.users)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for email lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);

-- Profile Sync Trigger: Automatically provisions public.users on auth.users insert/update
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, avatar_url)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'avatar_url'
  )
  ON CONFLICT (id) DO UPDATE
  SET email = EXCLUDED.email,
      full_name = COALESCE(EXCLUDED.full_name, public.users.full_name),
      updated_at = NOW();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT OR UPDATE OF email, raw_user_meta_data ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 3. Workspaces (Tenant Isolation Root)
CREATE TABLE IF NOT EXISTS public.workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Workspace Members (Tenant Scoping & RBAC: owner, admin, member)
CREATE TABLE IF NOT EXISTS public.workspace_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON public.workspace_members(user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_ws ON public.workspace_members(workspace_id);

-- 5. Seed Initial Server-Controlled Workspace
-- Default workspace ID for Jatin Choudhary's primary portfolio and platform
INSERT INTO public.workspaces (id, slug, name)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'default',
    'Personal Workspace'
)
ON CONFLICT (slug) DO UPDATE
SET name = EXCLUDED.name,
    updated_at = NOW();

-- 6. Hardened RLS Helper Function
-- Prevents search_path hijacking and recursive evaluations
CREATE OR REPLACE FUNCTION public.is_workspace_member(ws_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.workspace_members
    WHERE workspace_id = ws_id
    AND user_id = auth.uid()
  );
END;
$$;

-- Helper to check specific role or higher (Hierarchical: owner > admin > member)
CREATE OR REPLACE FUNCTION public.has_workspace_role(ws_id UUID, required_role TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  user_role TEXT;
BEGIN
  SELECT role INTO user_role
  FROM public.workspace_members
  WHERE workspace_id = ws_id
  AND user_id = auth.uid();

  IF user_role IS NULL THEN
    RETURN false;
  END IF;

  IF required_role = 'member' THEN
    RETURN true; -- owner, admin, member all satisfy member
  ELSIF required_role = 'admin' THEN
    RETURN user_role IN ('admin', 'owner');
  ELSIF required_role = 'owner' THEN
    RETURN user_role = 'owner';
  END IF;

  RETURN false;
END;
$$;

-- 7. Messages Table Refinement (Phase 2E Preservation)
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (char_length(name) <= 100),
    email TEXT NOT NULL,
    subject TEXT CHECK (char_length(subject) <= 150),
    message TEXT NOT NULL CHECK (char_length(message) <= 5000),
    status TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (status IN ('RECEIVED', 'READ', 'SPAM_FLAGGED', 'ARCHIVED')),
    sender_ip_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- If messages table already existed with older schema, ensure status column and constraints exist
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name = 'messages' AND column_name = 'status'
  ) THEN
    ALTER TABLE public.messages ADD COLUMN status TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (status IN ('RECEIVED', 'READ', 'SPAM_FLAGGED', 'ARCHIVED'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_messages_ws_created ON public.messages(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_ws_status ON public.messages(workspace_id, status);

-- 8. Reviews Table Refinement (Phase 2E Preservation)
CREATE TABLE IF NOT EXISTS public.reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    synthetic_name TEXT NOT NULL,
    synthetic_avatar_seed TEXT NOT NULL,
    content TEXT NOT NULL CHECK (char_length(content) <= 1000),
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    owner_reply TEXT,
    sender_ip_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_schema = 'public' AND table_name = 'reviews' AND column_name = 'status'
  ) THEN
    ALTER TABLE public.reviews ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED'));
  END IF;
END $$;

-- Partial index for fast public streaming of approved reviews
CREATE INDEX IF NOT EXISTS idx_reviews_public_stream ON public.reviews(workspace_id, created_at DESC) WHERE status = 'APPROVED';
CREATE INDEX IF NOT EXISTS idx_reviews_ws_status ON public.reviews(workspace_id, status);

-- ====================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ====================================================================

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

-- users policies
DROP POLICY IF EXISTS "Users can view their own profile" ON public.users;
CREATE POLICY "Users can view their own profile"
    ON public.users FOR SELECT
    USING (id = auth.uid());

DROP POLICY IF EXISTS "Users can update their own profile" ON public.users;
CREATE POLICY "Users can update their own profile"
    ON public.users FOR UPDATE
    USING (id = auth.uid());

-- workspaces policies
DROP POLICY IF EXISTS "Workspace members can view workspace" ON public.workspaces;
CREATE POLICY "Workspace members can view workspace"
    ON public.workspaces FOR SELECT
    USING (public.is_workspace_member(id));

DROP POLICY IF EXISTS "Workspace owners/admins can update workspace" ON public.workspaces;
CREATE POLICY "Workspace owners/admins can update workspace"
    ON public.workspaces FOR UPDATE
    USING (public.has_workspace_role(id, 'admin'));

-- workspace_members policies
DROP POLICY IF EXISTS "Members can view workspace member list" ON public.workspace_members;
CREATE POLICY "Members can view workspace member list"
    ON public.workspace_members FOR SELECT
    USING (public.is_workspace_member(workspace_id));

DROP POLICY IF EXISTS "Workspace owners can manage memberships" ON public.workspace_members;
CREATE POLICY "Workspace owners can manage memberships"
    ON public.workspace_members FOR ALL
    USING (public.has_workspace_role(workspace_id, 'owner'));

-- messages policies
DROP POLICY IF EXISTS "Workspace members can view messages" ON public.messages;
CREATE POLICY "Workspace members can view messages"
    ON public.messages FOR SELECT
    USING (public.is_workspace_member(workspace_id));

DROP POLICY IF EXISTS "Workspace admins can update messages" ON public.messages;
CREATE POLICY "Workspace admins can update messages"
    ON public.messages FOR UPDATE
    USING (public.has_workspace_role(workspace_id, 'admin'));

-- reviews policies
DROP POLICY IF EXISTS "Public can view approved reviews" ON public.reviews;
CREATE POLICY "Public can view approved reviews"
    ON public.reviews FOR SELECT
    USING (status = 'APPROVED');

DROP POLICY IF EXISTS "Workspace members can view all reviews" ON public.reviews;
CREATE POLICY "Workspace members can view all reviews"
    ON public.reviews FOR SELECT
    USING (public.is_workspace_member(workspace_id));

DROP POLICY IF EXISTS "Workspace admins can moderate reviews" ON public.reviews;
CREATE POLICY "Workspace admins can moderate reviews"
    ON public.reviews FOR UPDATE
    USING (public.has_workspace_role(workspace_id, 'admin'));

-- ====================================================================
-- IKIGAI MULTI-TENANT ARCHITECTURE SCHEMA (SUPABASE / POSTGRESQL 16+)
-- ====================================================================

-- 1. Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Workspaces (Tenant Isolation Root)
CREATE TABLE IF NOT EXISTS public.workspaces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Workspace Members (RBAC: owner, admin, member)
CREATE TABLE IF NOT EXISTS public.workspace_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL, -- references auth.users(id) in Supabase
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workspace_id, user_id)
);

-- 4. Projects (Monitored Workspaces / Repositories)
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    tagline TEXT,
    category TEXT NOT NULL,
    repository_url TEXT,
    deployment_url TEXT,
    technologies TEXT[] DEFAULT '{}',
    is_featured BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workspace_id, slug)
);

-- 5. Integrations (Configured external accounts per project/workspace)
CREATE TABLE IF NOT EXISTS public.integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('github', 'vercel', 'render', 'uptimerobot')),
    account_alias TEXT NOT NULL,
    encrypted_credentials JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Contact Messages (Portfolio Ingestion Pipeline)
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    subject TEXT,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT false,
    is_spam BOOLEAN DEFAULT false,
    sender_ip_hash TEXT, -- One-way SHA-256 for rate limiting
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Anonymous Reviews (Moderation & Synthetic Persona Queue)
CREATE TABLE IF NOT EXISTS public.reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    synthetic_name TEXT NOT NULL,
    synthetic_avatar_seed TEXT NOT NULL,
    content TEXT NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    is_approved BOOLEAN DEFAULT false,
    owner_reply TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Vault Records (Zero-Knowledge Ciphertext Store)
CREATE TABLE IF NOT EXISTS public.vault_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    ciphertext TEXT NOT NULL,      -- AES-256-GCM encrypted payload
    iv TEXT NOT NULL,              -- 12-byte base64 IV
    auth_tag TEXT NOT NULL,        -- GCM authentication tag
    salt TEXT NOT NULL,            -- Client-side derivation salt
    safe_metadata JSONB DEFAULT '{}', -- Strictly non-secret metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Music Items (Audio Library & Metadata)
CREATE TABLE IF NOT EXISTS public.music_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    duration_seconds INTEGER,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 10. Notes (7-Day Strip & Expandable Calendar)
CREATE TABLE IF NOT EXISTS public.notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    assigned_date DATE,
    reminder_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 11. Notifications
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    is_read BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ====================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ====================================================================

ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vault_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.music_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

-- Helper function to check workspace membership
CREATE OR REPLACE FUNCTION public.is_workspace_member(ws_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.workspace_members
    WHERE workspace_id = ws_id
    AND user_id = auth.uid()
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Public read for approved reviews
CREATE POLICY "Public can view approved reviews"
    ON public.reviews FOR SELECT
    USING (is_approved = true);

-- Tenant isolation policies for workspace members
CREATE POLICY "Workspace members can read projects"
    ON public.projects FOR SELECT
    USING (public.is_workspace_member(workspace_id));

CREATE POLICY "Workspace members can access vault"
    ON public.vault_records FOR ALL
    USING (public.is_workspace_member(workspace_id));

CREATE POLICY "Workspace members can access notes"
    ON public.notes FOR ALL
    USING (public.is_workspace_member(workspace_id));

CREATE POLICY "Workspace members can access messages"
    ON public.messages FOR ALL
    USING (public.is_workspace_member(workspace_id));

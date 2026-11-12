-- VirtualOS schema `vos` — initial migration.
-- All tenant tables carry workspace_id and are protected by RLS via vos.is_member().
-- The API runs user requests as role `authenticated` (SET LOCAL ROLE + request.jwt.claims);
-- the worker runs as the owner role and filters by workspace_id explicitly.

CREATE SCHEMA IF NOT EXISTS vos;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Core tenancy
-- ---------------------------------------------------------------------------
CREATE TABLE vos.workspaces (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'creator' CHECK (kind IN ('creator', 'company', 'agency')),
    plan        TEXT NOT NULL DEFAULT 'free',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE vos.workspace_members (
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL,  -- auth.users.id
    role         TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'member')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (workspace_id, user_id)
);
CREATE INDEX idx_members_user ON vos.workspace_members (user_id);

CREATE TABLE vos.plan_limits (
    plan                     TEXT PRIMARY KEY,
    max_active_niches        INT NOT NULL,
    niche_switches_per_month INT NOT NULL,
    max_tracked_accounts     INT NOT NULL,
    ingestions_per_day       INT NOT NULL,
    agent_messages_per_day   INT NOT NULL,
    llm_budget_usd_month     NUMERIC(10, 2) NOT NULL
);

INSERT INTO vos.plan_limits VALUES
    ('free',   1,  1,  5,  2,  30,  5.00),
    ('pro',    2,  4, 25, 10, 200, 40.00),
    ('agency', 10, 30, 150, 50, 1000, 300.00);

-- ---------------------------------------------------------------------------
-- Niche profiles (built by the mascot; archived, never deleted)
-- ---------------------------------------------------------------------------
CREATE TABLE vos.niche_profiles (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    kind          TEXT NOT NULL DEFAULT 'creator' CHECK (kind IN ('creator', 'company', 'agency')),
    name          TEXT NOT NULL,
    platforms     TEXT[] NOT NULL DEFAULT '{tiktok}',
    countries     TEXT[] NOT NULL DEFAULT '{}',
    languages     TEXT[] NOT NULL DEFAULT '{}',
    keywords      TEXT[] NOT NULL DEFAULT '{}',
    hashtags      TEXT[] NOT NULL DEFAULT '{}',
    seed_accounts JSONB NOT NULL DEFAULT '{}',  -- {"tiktok": ["handle", ...], "instagram": [...]}
    goals         TEXT,
    tone          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at   TIMESTAMPTZ
);
CREATE INDEX idx_niches_ws ON vos.niche_profiles (workspace_id, status);

-- ---------------------------------------------------------------------------
-- Accounts + posts + snapshots
-- ---------------------------------------------------------------------------
CREATE TABLE vos.accounts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    niche_profile_id UUID REFERENCES vos.niche_profiles(id) ON DELETE SET NULL,
    platform      TEXT NOT NULL CHECK (platform IN ('tiktok', 'instagram', 'facebook')),
    handle        TEXT NOT NULL,
    display_name  TEXT,
    followers     BIGINT,
    is_seed       BOOLEAN NOT NULL DEFAULT FALSE,
    raw           JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, platform, handle)
);

CREATE TABLE vos.posts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    account_id    UUID REFERENCES vos.accounts(id) ON DELETE SET NULL,
    platform      TEXT NOT NULL CHECK (platform IN ('tiktok', 'instagram', 'facebook')),
    external_id   TEXT NOT NULL,
    author_handle TEXT,
    url           TEXT,
    published_at  TIMESTAMPTZ,
    views         BIGINT,
    likes         BIGINT,
    comments      BIGINT,
    shares        BIGINT,
    caption       TEXT,
    hashtags      TEXT[] NOT NULL DEFAULT '{}',
    sound_id      TEXT,
    sound_name    TEXT,
    duration_s    NUMERIC(8, 2),
    thumbnail_url TEXT,
    transcript    TEXT,
    outlier_score NUMERIC(10, 3),
    velocity      NUMERIC(14, 3),
    rank_score    NUMERIC(12, 6),
    raw           JSONB,
    s3_raw_key    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, platform, external_id)
);
CREATE INDEX idx_posts_ws_published ON vos.posts (workspace_id, platform, published_at DESC);
CREATE INDEX idx_posts_ws_outlier   ON vos.posts (workspace_id, outlier_score DESC NULLS LAST);
CREATE INDEX idx_posts_author       ON vos.posts (workspace_id, platform, author_handle);

CREATE TABLE vos.post_snapshots (
    id           BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    post_id      UUID NOT NULL REFERENCES vos.posts(id) ON DELETE CASCADE,
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    views        BIGINT,
    likes        BIGINT,
    comments     BIGINT,
    shares       BIGINT
);
CREATE INDEX idx_snapshots_post ON vos.post_snapshots (post_id, captured_at);

-- ---------------------------------------------------------------------------
-- Platform trends + news
-- ---------------------------------------------------------------------------
CREATE TABLE vos.platform_trends (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    platform     TEXT NOT NULL CHECK (platform IN ('tiktok', 'instagram', 'facebook')),
    country      TEXT NOT NULL,
    trend_type   TEXT NOT NULL CHECK (trend_type IN ('hashtag', 'sound')),
    name         TEXT NOT NULL,
    external_id  TEXT,
    rank         INT,
    metrics      JSONB NOT NULL DEFAULT '{}',
    captured_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_trends_ws ON vos.platform_trends (workspace_id, platform, country, captured_at DESC);

CREATE TABLE vos.news_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    niche_profile_id UUID REFERENCES vos.niche_profiles(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    url              TEXT NOT NULL,
    source           TEXT,
    snippet          TEXT,
    published_at     TIMESTAMPTZ,
    raw              JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, url)
);

-- ---------------------------------------------------------------------------
-- Synthesis: hooks, ideas, briefs, feedback
-- ---------------------------------------------------------------------------
CREATE TABLE vos.hooks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    post_id      UUID NOT NULL REFERENCES vos.posts(id) ON DELETE CASCADE,
    hook_text    TEXT NOT NULL,
    hook_type    TEXT,
    structure    JSONB NOT NULL DEFAULT '{}',
    cta          TEXT,
    language     TEXT,
    model        TEXT,
    cost_usd     NUMERIC(10, 6),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, post_id)
);

CREATE TABLE vos.weekly_briefs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    niche_profile_id UUID REFERENCES vos.niche_profiles(id) ON DELETE SET NULL,
    week_start       DATE NOT NULL,
    summary          TEXT,
    content          JSONB NOT NULL DEFAULT '{}',
    pdf_s3_key       TEXT,
    model            TEXT,
    cost_usd         NUMERIC(10, 6),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE vos.content_ideas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    niche_profile_id UUID REFERENCES vos.niche_profiles(id) ON DELETE SET NULL,
    weekly_brief_id  UUID REFERENCES vos.weekly_briefs(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    angle            TEXT,
    hook_suggestion  TEXT,
    script_outline   TEXT,
    status           TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'planned', 'recorded', 'discarded')),
    -- Evidence is MANDATORY: ideas without it are discarded before insert (hard rule).
    evidence_post_ids  UUID[] NOT NULL DEFAULT '{}',
    evidence_trend_ids UUID[] NOT NULL DEFAULT '{}',
    evidence_news_ids  UUID[] NOT NULL DEFAULT '{}',
    model            TEXT,
    cost_usd         NUMERIC(10, 6),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        cardinality(evidence_post_ids) > 0
        OR cardinality(evidence_trend_ids) > 0
        OR cardinality(evidence_news_ids) > 0
    )
);

CREATE TABLE vos.idea_feedback (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    idea_id      UUID NOT NULL REFERENCES vos.content_ideas(id) ON DELETE CASCADE,
    recorded     BOOLEAN NOT NULL DEFAULT TRUE,
    posted_url   TEXT,
    result_views BIGINT,
    notes        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Jobs (PostgresJobQueue) + API usage + agent
-- ---------------------------------------------------------------------------
CREATE TABLE vos.jobs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts     INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    run_after    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_jobs_claim ON vos.jobs (status, run_after) WHERE status = 'pending';

CREATE TABLE vos.api_usage (
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    provider     TEXT NOT NULL,
    day          DATE NOT NULL DEFAULT CURRENT_DATE,
    calls        INT NOT NULL DEFAULT 0,
    units        NUMERIC(14, 6) NOT NULL DEFAULT 0,
    unit_label   TEXT,
    cost_usd     NUMERIC(14, 6) NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, provider, day)
);

CREATE TABLE vos.agent_conversations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL,
    title        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE vos.agent_messages (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    UUID NOT NULL REFERENCES vos.workspaces(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES vos.agent_conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content         TEXT,
    tool_calls      JSONB,
    tokens          INT,
    cost_usd        NUMERIC(10, 6),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agent_messages_conv ON vos.agent_messages (conversation_id, id);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
-- SECURITY DEFINER so the membership check bypasses RLS on workspace_members
-- (standard Supabase pattern to avoid policy recursion).
CREATE OR REPLACE FUNCTION vos.is_member(ws UUID)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = vos, public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM vos.workspace_members m
        WHERE m.workspace_id = ws AND m.user_id = auth.uid()
    );
$$;

ALTER TABLE vos.workspaces          ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.workspace_members   ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.plan_limits         ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.niche_profiles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.accounts            ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.posts               ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.post_snapshots      ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.platform_trends     ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.news_items          ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.hooks               ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.weekly_briefs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.content_ideas       ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.idea_feedback       ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.jobs                ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.api_usage           ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.agent_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE vos.agent_messages      ENABLE ROW LEVEL SECURITY;

CREATE POLICY ws_select ON vos.workspaces FOR ALL
    USING (vos.is_member(id)) WITH CHECK (vos.is_member(id));

CREATE POLICY members_own ON vos.workspace_members FOR ALL
    USING (user_id = auth.uid() OR vos.is_member(workspace_id))
    WITH CHECK (vos.is_member(workspace_id));

CREATE POLICY plan_limits_read ON vos.plan_limits FOR SELECT USING (TRUE);

CREATE POLICY tenant_all ON vos.niche_profiles FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.accounts FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.posts FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.post_snapshots FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.platform_trends FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.news_items FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.hooks FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.weekly_briefs FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.content_ideas FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.idea_feedback FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.jobs FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.api_usage FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.agent_conversations FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));
CREATE POLICY tenant_all ON vos.agent_messages FOR ALL
    USING (vos.is_member(workspace_id)) WITH CHECK (vos.is_member(workspace_id));

-- ---------------------------------------------------------------------------
-- Grants: role `authenticated` goes through RLS; owner (migrations/worker) bypasses.
-- The anon role gets nothing: the API always validates a JWT first.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA vos TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA vos TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA vos TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA vos
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA vos
    GRANT USAGE ON SEQUENCES TO authenticated;

REVOKE INSERT, UPDATE, DELETE ON vos.plan_limits FROM authenticated;

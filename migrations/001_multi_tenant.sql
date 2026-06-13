-- Migration 001: multi-tenancy (per-user recipes + usage log)
--
-- Run this in the Supabase SQL Editor.
-- PREREQUISITE: your own auth user must exist first. Easiest way:
--   Supabase dashboard -> Authentication -> Users -> "Add user" / "Invite user"
--   with your email (dtransla@gmail.com), BEFORE running this script.

-- ── 1. Add user ownership to recipes ─────────────────────────────────
ALTER TABLE recipes
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;

-- ── 2. Backfill existing recipes to the owner account ────────────────
-- Adjust the email if your account uses a different address.
UPDATE recipes
SET user_id = (SELECT id FROM auth.users WHERE email = 'dtransla@gmail.com')
WHERE user_id IS NULL;

-- This will fail if any rows are still NULL (i.e. the email above did
-- not match an auth user). Fix the backfill first, then re-run.
ALTER TABLE recipes ALTER COLUMN user_id SET NOT NULL;

-- ── 3. Replace the permissive policy with per-user policies ──────────
DROP POLICY IF EXISTS "Allow all" ON recipes;

CREATE POLICY "Users read own recipes" ON recipes
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users insert own recipes" ON recipes
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users update own recipes" ON recipes
  FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users delete own recipes" ON recipes
  FOR DELETE USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_recipes_user_id ON recipes(user_id);

-- ── 4. Extraction log (quotas now, billing/usage later) ──────────────
CREATE TABLE IF NOT EXISTS extraction_log (
  id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  url        TEXT DEFAULT '',
  platform   TEXT DEFAULT '',
  status     TEXT DEFAULT '',   -- success | failed | no_recipe
  error      TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE extraction_log ENABLE ROW LEVEL SECURITY;

-- Users may see their own usage; only the server (secret key) writes.
CREATE POLICY "Users read own extraction log" ON extraction_log
  FOR SELECT USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_extraction_log_user_created
  ON extraction_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_extraction_log_created
  ON extraction_log(created_at);

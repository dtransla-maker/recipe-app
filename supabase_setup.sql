-- Run this in your Supabase project's SQL Editor
-- Go to: supabase.com → your project → SQL Editor → New Query → paste this → Run

CREATE TABLE IF NOT EXISTS recipes (
  id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  created_at  TIMESTAMPTZ DEFAULT NOW(),

  -- Recipe content
  title       TEXT NOT NULL,
  description TEXT DEFAULT '',
  servings    TEXT DEFAULT '',
  prep_time   TEXT DEFAULT '',
  cook_time   TEXT DEFAULT '',
  total_time  TEXT DEFAULT '',
  difficulty  TEXT DEFAULT '',

  -- Structured data (arrays stored as JSON)
  ingredients  JSONB DEFAULT '[]'::jsonb,
  instructions JSONB DEFAULT '[]'::jsonb,
  tags         JSONB DEFAULT '[]'::jsonb,

  -- Extra info
  tips          TEXT DEFAULT '',
  source_url    TEXT DEFAULT '',
  platform      TEXT DEFAULT '',
  thumbnail_url TEXT DEFAULT ''
);

-- Allow public read/write access (fine for personal use)
ALTER TABLE recipes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all" ON recipes
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Run once in Supabase SQL Editor for an existing database before enabling the importer.
CREATE UNIQUE INDEX IF NOT EXISTS idx_markets_cricapi_match_id
ON public.markets(cricapi_match_id)
WHERE cricapi_match_id IS NOT NULL;

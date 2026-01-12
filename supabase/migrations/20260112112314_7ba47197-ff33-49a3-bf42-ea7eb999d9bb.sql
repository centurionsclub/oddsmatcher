-- Drop INSERT policies to block new data
DROP POLICY IF EXISTS "Service role can insert scraping logs" ON public.scraping_logs;
DROP POLICY IF EXISTS "Service role can insert cached odds" ON public.odds_cache;
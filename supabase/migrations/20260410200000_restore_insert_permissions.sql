-- Restore INSERT permissions that were revoked in previous migrations
-- This is needed for the odds-scraper edge function to write data

-- Restore table-level INSERT for service_role
GRANT INSERT ON public.odds_cache TO service_role;
GRANT INSERT ON public.scraping_logs TO service_role;

-- Also grant UPDATE and DELETE for cache management
GRANT UPDATE, DELETE ON public.odds_cache TO service_role;
GRANT UPDATE, DELETE ON public.scraping_logs TO service_role;

-- Recreate RLS policies for service_role INSERT
CREATE POLICY IF NOT EXISTS "Service role can insert cached odds"
  ON public.odds_cache
  FOR INSERT
  WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "Service role can insert scraping logs"
  ON public.scraping_logs
  FOR INSERT
  WITH CHECK (true);

-- Ensure odds_cache_by_league also has full service_role access
GRANT INSERT, UPDATE, DELETE ON public.odds_cache_by_league TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.matched_bets TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.aggregated_odds TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.events_master TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.odds_alerts TO service_role;

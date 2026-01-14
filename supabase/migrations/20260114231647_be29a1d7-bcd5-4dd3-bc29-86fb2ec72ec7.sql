-- Revoke INSERT permissions at table level (bypasses RLS)
REVOKE INSERT ON public.odds_cache FROM authenticated, anon, service_role;
REVOKE INSERT ON public.scraping_logs FROM authenticated, anon, service_role;
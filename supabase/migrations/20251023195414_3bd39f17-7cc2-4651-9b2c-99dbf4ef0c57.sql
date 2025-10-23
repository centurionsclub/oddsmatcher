-- Fix RLS policies for odds_cache to allow edge function to insert/update data
-- The edge function uses service_role key, so we allow operations from service_role

CREATE POLICY "Service role can insert cached odds" 
ON public.odds_cache 
FOR INSERT 
TO service_role
WITH CHECK (true);

CREATE POLICY "Service role can update cached odds" 
ON public.odds_cache 
FOR UPDATE 
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role can delete expired cached odds" 
ON public.odds_cache 
FOR DELETE 
TO service_role
USING (true);

-- Also allow insert/update for scraping_logs
CREATE POLICY "Service role can insert scraping logs" 
ON public.scraping_logs 
FOR INSERT 
TO service_role
WITH CHECK (true);
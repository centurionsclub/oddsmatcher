-- Create odds_cache table for caching scraped odds
CREATE TABLE public.odds_cache (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  bookmaker TEXT NOT NULL,
  sport TEXT NOT NULL,
  event_name TEXT NOT NULL,
  league TEXT,
  event_time TIMESTAMPTZ,
  market TEXT NOT NULL,
  odds JSONB NOT NULL,
  scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '30 seconds')
);

-- Create indexes for efficient cache lookups
CREATE INDEX idx_odds_cache_expires ON public.odds_cache(expires_at);
CREATE INDEX idx_odds_cache_lookup ON public.odds_cache(bookmaker, sport, event_name, market);

-- Enable RLS
ALTER TABLE public.odds_cache ENABLE ROW LEVEL SECURITY;

-- Allow all users to read cached odds
CREATE POLICY "Anyone can read cached odds"
ON public.odds_cache
FOR SELECT
USING (true);

-- Create scraping_logs table for monitoring
CREATE TABLE public.scraping_logs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  bookmaker TEXT NOT NULL,
  status TEXT NOT NULL,
  error_message TEXT,
  duration_ms INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Create index for log queries
CREATE INDEX idx_scraping_logs_created ON public.scraping_logs(created_at DESC);

-- Enable RLS
ALTER TABLE public.scraping_logs ENABLE ROW LEVEL SECURITY;

-- Allow all users to read logs
CREATE POLICY "Anyone can read scraping logs"
ON public.scraping_logs
FOR SELECT
USING (true);

-- Create events_master table for event normalization
CREATE TABLE public.events_master (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  sport TEXT NOT NULL,
  league TEXT NOT NULL,
  event_name TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  normalized_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(normalized_name, event_time)
);

-- Create index for event matching
CREATE INDEX idx_events_master_normalized ON public.events_master(normalized_name, event_time);

-- Enable RLS
ALTER TABLE public.events_master ENABLE ROW LEVEL SECURITY;

-- Allow all users to read events
CREATE POLICY "Anyone can read events"
ON public.events_master
FOR SELECT
USING (true);

-- Function to clean expired cache entries
CREATE OR REPLACE FUNCTION public.clean_expired_odds_cache()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  DELETE FROM public.odds_cache WHERE expires_at < now();
END;
$$;
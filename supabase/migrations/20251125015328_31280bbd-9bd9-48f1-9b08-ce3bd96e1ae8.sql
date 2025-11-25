-- Tabella cache intelligente per campionato/sport
CREATE TABLE IF NOT EXISTS public.odds_cache_by_league (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  sport TEXT NOT NULL,
  league TEXT NOT NULL,
  market TEXT NOT NULL,
  cache_key TEXT NOT NULL UNIQUE,
  data JSONB NOT NULL,
  scraped_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  scraping_duration_ms INTEGER,
  total_events INTEGER,
  total_bookmakers INTEGER
);

CREATE INDEX IF NOT EXISTS idx_odds_cache_by_league_cache_key ON public.odds_cache_by_league(cache_key);
CREATE INDEX IF NOT EXISTS idx_odds_cache_by_league_expires ON public.odds_cache_by_league(expires_at);

-- Enable RLS
ALTER TABLE public.odds_cache_by_league ENABLE ROW LEVEL SECURITY;

-- RLS policies
CREATE POLICY "Anyone can read league cache"
  ON public.odds_cache_by_league
  FOR SELECT
  USING (true);

CREATE POLICY "Service role can manage league cache"
  ON public.odds_cache_by_league
  FOR ALL
  USING (true);

-- Tabella alert quote anomale
CREATE TABLE IF NOT EXISTS public.odds_alerts (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  event_name TEXT NOT NULL,
  outcome TEXT NOT NULL,
  bookmaker TEXT NOT NULL,
  odds NUMERIC NOT NULL,
  average_odds NUMERIC NOT NULL,
  difference_percentage NUMERIC NOT NULL,
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  is_read BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_odds_alerts_expires ON public.odds_alerts(expires_at);
CREATE INDEX IF NOT EXISTS idx_odds_alerts_unread ON public.odds_alerts(is_read) WHERE is_read = false;

-- Enable RLS
ALTER TABLE public.odds_alerts ENABLE ROW LEVEL SECURITY;

-- RLS policies
CREATE POLICY "Anyone can read alerts"
  ON public.odds_alerts
  FOR SELECT
  USING (true);

CREATE POLICY "Service role can insert alerts"
  ON public.odds_alerts
  FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Anyone can update alerts read status"
  ON public.odds_alerts
  FOR UPDATE
  USING (true);

-- Abilita realtime per odds_alerts
ALTER PUBLICATION supabase_realtime ADD TABLE public.odds_alerts;
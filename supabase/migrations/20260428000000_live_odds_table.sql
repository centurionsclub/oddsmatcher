-- Table for live odds scraped from centroquote.it
-- The Python scraper writes here every 5 minutes via service_role key.
-- Each row = one bookmaker × event × market × outcome combination.
CREATE TABLE IF NOT EXISTS public.live_odds (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  bookmaker    text        NOT NULL,
  sport        text        NOT NULL,
  league       text        NOT NULL,
  event_name   text        NOT NULL,
  event_time   timestamptz,
  market       text        NOT NULL,
  outcome      text        NOT NULL,
  odds         numeric(10,2) NOT NULL,
  scraped_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL DEFAULT (now() + interval '10 minutes'),
  UNIQUE (bookmaker, event_name, market, outcome)
);

CREATE INDEX IF NOT EXISTS idx_live_odds_expires    ON public.live_odds (expires_at);
CREATE INDEX IF NOT EXISTS idx_live_odds_league     ON public.live_odds (sport, league);
CREATE INDEX IF NOT EXISTS idx_live_odds_event      ON public.live_odds (event_name);
CREATE INDEX IF NOT EXISTS idx_live_odds_market     ON public.live_odds (market);

ALTER TABLE public.live_odds ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read live_odds"
  ON public.live_odds FOR SELECT USING (true);

-- Explicit grants so the service_role key used by the Python scraper can write.
GRANT INSERT, UPDATE, DELETE ON public.live_odds TO service_role;
GRANT SELECT ON public.live_odds TO anon, authenticated;

-- Clean up expired rows automatically (called by the scraper before each run).
CREATE OR REPLACE FUNCTION public.clean_expired_live_odds()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  DELETE FROM public.live_odds WHERE expires_at < now();
END;
$$;
GRANT EXECUTE ON FUNCTION public.clean_expired_live_odds() TO service_role;

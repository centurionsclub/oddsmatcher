-- Add match_url column to live_odds so the frontend can link directly to the
-- bookmaker's event page (e.g. lottomatica.it/scommesse/sport/calcio/italia/serie-a/atalanta-bologna?tid=93&eid=...)
ALTER TABLE public.live_odds
  ADD COLUMN IF NOT EXISTS match_url text;

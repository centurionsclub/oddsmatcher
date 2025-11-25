-- Create matched_bets table for storing arbitrage calculations
CREATE TABLE IF NOT EXISTS public.matched_bets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid REFERENCES public.events_master(id) ON DELETE CASCADE,
  back_bookmaker text NOT NULL,
  lay_bookmaker text NOT NULL DEFAULT 'betfair',
  back_odds decimal(10,2) NOT NULL,
  lay_odds decimal(10,2) NOT NULL,
  back_stake decimal(10,2) NOT NULL,
  lay_stake decimal(10,2) NOT NULL,
  profit decimal(10,2) NOT NULL,
  rating decimal(5,2) NOT NULL,
  commission_rate decimal(5,2) DEFAULT 5.0,
  market text NOT NULL,
  outcome text NOT NULL,
  created_at timestamptz DEFAULT now(),
  expires_at timestamptz DEFAULT (now() + interval '5 minutes')
);

-- Enable RLS
ALTER TABLE public.matched_bets ENABLE ROW LEVEL SECURITY;

-- Policy: anyone can read matched bets
CREATE POLICY "Anyone can read matched bets"
  ON public.matched_bets
  FOR SELECT
  USING (true);

-- Policy: service role can insert
CREATE POLICY "Service role can insert matched bets"
  ON public.matched_bets
  FOR INSERT
  WITH CHECK (true);

-- Policy: service role can delete expired
CREATE POLICY "Service role can delete expired matched bets"
  ON public.matched_bets
  FOR DELETE
  USING (expires_at < now());

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_matched_bets_rating ON public.matched_bets(rating DESC);
CREATE INDEX IF NOT EXISTS idx_matched_bets_expires ON public.matched_bets(expires_at);

-- Create aggregated_odds table for multi-bookmaker comparison
CREATE TABLE IF NOT EXISTS public.aggregated_odds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid REFERENCES public.events_master(id) ON DELETE CASCADE,
  market text NOT NULL,
  outcome text NOT NULL,
  best_back_odds decimal(10,2),
  best_back_bookmaker text,
  best_lay_odds decimal(10,2),
  best_lay_bookmaker text DEFAULT 'betfair',
  updated_at timestamptz DEFAULT now(),
  UNIQUE(event_id, market, outcome)
);

-- Enable RLS
ALTER TABLE public.aggregated_odds ENABLE ROW LEVEL SECURITY;

-- Policy: anyone can read
CREATE POLICY "Anyone can read aggregated odds"
  ON public.aggregated_odds
  FOR SELECT
  USING (true);

-- Policy: service role can manage
CREATE POLICY "Service role can manage aggregated odds"
  ON public.aggregated_odds
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Create function to clean expired matched bets
CREATE OR REPLACE FUNCTION public.clean_expired_matched_bets()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  DELETE FROM public.matched_bets WHERE expires_at < now();
END;
$$;
-- Create table for saved filters
CREATE TABLE public.saved_filters (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  tab_type TEXT NOT NULL CHECK (tab_type IN ('singola', 'multipla', 'trevie', 'bestodds', 'surebet')),
  filter_data JSONB NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE public.saved_filters ENABLE ROW LEVEL SECURITY;

-- Create policy to allow all operations (since there's no authentication)
CREATE POLICY "Allow all operations on saved_filters"
ON public.saved_filters
FOR ALL
USING (true)
WITH CHECK (true);

-- Create function to update timestamps
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic timestamp updates
CREATE TRIGGER update_saved_filters_updated_at
BEFORE UPDATE ON public.saved_filters
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at_column();

-- Create index for faster queries
CREATE INDEX idx_saved_filters_tab_type ON public.saved_filters(tab_type);
CREATE INDEX idx_saved_filters_created_at ON public.saved_filters(created_at DESC);
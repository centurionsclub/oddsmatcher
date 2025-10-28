import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { apiKey, sessionToken } = await req.json();

    if (!apiKey || !sessionToken) {
      return new Response(
        JSON.stringify({ error: 'API Key e Session Token sono obbligatori' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // Log per conferma (non logghiamo i valori effettivi per sicurezza)
    console.log('Betfair credentials update requested');
    
    // Nota: I secrets vengono gestiti a livello di progetto Supabase
    // Questa funzione serve solo per validare il formato
    // L'aggiornamento effettivo avviene tramite secrets management di Lovable

    return new Response(
      JSON.stringify({ 
        success: true, 
        message: 'Credenziali validate. Aggiorna i secrets nel progetto per applicare le modifiche.' 
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('Error updating Betfair credentials:', error);
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return new Response(
      JSON.stringify({ error: errorMessage }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});

# Oddsmatcher

Strumento di matched betting che confronta le quote dei bookmaker italiani con le quote dell'exchange (Betfair) per individuare le opportunità di copertura ottimali.

## Funzionalità

- **Confronto quote in tempo reale** tra oltre 20 bookmaker italiani e Betfair Exchange
- **Calcolo automatico** di stake lay, rischio, profitto e rating
- **Supporto bonus e free bet** con formula corretta (bonus trattato come stake aggiuntivo)
- **Filtri avanzati** per sport, mercato, bookmaker, quota minima/massima, partita e campionato
- **Modalità Best Odds, Singola, Multipla, Tre Vie, Best Opposite**
- **Modal Punta/Banca** con commissione modificabile e riepilogo completo della scommessa

## Stack tecnologico

- **Frontend**: React + TypeScript + Vite
- **UI**: Tailwind CSS + shadcn-ui
- **Database**: Supabase (PostgreSQL)
- **Scraper**: Python + Playwright (CentroQuote) + Betfair API
- **CI/CD**: GitHub Actions (scraper automatici 2×/giorno + ogni 2 ore)
- **Deploy**: Vercel

## Sviluppo locale

```sh
# Clona il repository
git clone https://github.com/fabianodebei/oddsmatcher.git

# Installa le dipendenze
cd oddsmatcher
npm install

# Avvia il server di sviluppo
npm run dev
```

## Variabili d'ambiente

Crea un file `.env` nella root con:

```
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
```

## Scraper

Gli scraper si trovano nella cartella `scraper/` e vengono eseguiti automaticamente tramite GitHub Actions:

- `scrape_centroquote.py` — quote bookmaker (2×/giorno)
- `betfair_scraper.py` — quote exchange Betfair (ogni 2 ore)

Per eseguirli localmente:

```sh
cd scraper
pip install -r requirements.txt
python scrape_centroquote.py
```

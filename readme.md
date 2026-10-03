# LVN Single Ticker Analysis

Workspace standalone per ottimizzare e validare parametri LVN **su ciascun titolo**.

## Obiettivo

- trovare parametri migliori ticker-by-ticker
- salvare output separati per ogni ticker
- confrontare il risultato con una baseline globale a parametri condivisi

## Moduli minimi

- `config.py`: default runtime/strategia/grid
- `engine.py`: logica segnali LVN + filtro RSI
- `backtest.py`: backtest per singolo ticker
- `optimizer.py`: ottimizzazione per ticker + confronto baseline

## Flusso CLI

1. Backtest singolo ticker

```bash
python backtest.py --data-dir /percorso/al/repo/data --ticker UCG --output-dir /tmp/lvn-backtest
```

2. Ottimizzazione mensile multi-ticker

```bash
python optimizer.py --data-dir /percorso/al/repo/data --output-dir /tmp/lvn-optimization
```

3. Aggiornamento prezzi da Yahoo Finance

```bash
python fetch_latest_prices.py --data-dir /percorso/al/repo/data
```

## Universo ticker europeo

`config.py` definisce in `INDEX_TICKERS` tutti i 40 componenti di ciascun indice:
**MIB40 (FTSE MIB, Italia)**, **DAX40 (Germania)** e **CAC40 (Francia)**.
`YAHOO_SYMBOLS` associa i codici locali ai simboli Yahoo Finance (`.MI`, `.DE`, `.PA`,
con `MT.AS` per ArcelorMittal);
`TICKERS` contiene 140 chiavi senza duplicati e conserva anche i ticker legacy,
per non perdere serie CSV o parametri ottimizzati esistenti.

Le liste sono snapshot statiche, non una ricostruzione storica dei componenti
(i backtest possono quindi avere survivorship bias). Fonti consultate il 3 ottobre 2026:

- [FTSE MIB, elenco di base](https://github.com/yfiua/index-constituents/blob/6da4ab7917da2a482d8dce5af701024175e4f6be/docs/constituents-ftsemib.csv), aggiornato con [Technoprobe al posto di DiaSorin dal 21 settembre 2026](https://research.ftserussell.com/products/index-notices/home/getnotice/?id=2621825)
- [DAX, elenco di base](https://github.com/yfiua/index-constituents/blob/98dd8ec5e1042d27ca4b78e967cc20b73c97e63d/docs/constituents-dax.csv), aggiornato con [Hochtief al posto di Porsche Holding dal 22 giugno 2026](https://stoxx.com/stoxx-announces-scheduled-adjustments-to-dax-blue-chip-indices-jun-3-2026/)
- [CAC40, composizione Boursier](https://www.boursier.com/indices/composition/cac-40-FR0003500008,FR.html)

Dopo le revisioni degli indici, aggiornare le tuple in `INDEX_TICKERS` e verificare
i simboli Yahoo e i test. Le quotazioni su borse diverse restano separate:
`AIR.csv` usa `AIR.PA`, mentre `AIR.DE.csv` usa `AIR.DE`;
`STLAM`/`STLAP` e `STMMI`/`STM` distinguono Milano da Parigi.
Per Volkswagen il DAX usa le azioni privilegiate `VOW3.DE`; il codice legacy
`VOW` resta disponibile.

Il download senza `--tickers` elabora l'intero universo e crea i CSV mancanti
dal `2020-01-01` (modificabile con `--bootstrap-start-date`). Un errore su un ticker
non interrompe gli altri download ed è riportato nel riepilogo; un nuovo ticker
senza dati disponibili non produce un CSV e non viene analizzato.
Per selezionare solo alcuni titoli:

```bash
python fetch_latest_prices.py --data-dir /percorso/al/repo/data --tickers UCG SAP SAN
```

Entrambi i workflow scaricano questo universo prima dell'analisi: il backtest
giornaliero e l'ottimizzazione mensile scoprono automaticamente tutti i CSV in
`data/`, inclusi i nuovi titoli, senza liste aggiuntive da mantenere nei workflow.
Per i nuovi ticker il giornaliero usa i default finché non sono disponibili
parametri in `optimized_params.json`.

## Automazione GitHub Actions

La repository usa due workflow GitHub Actions con notifiche via **GitHub Issues** e, opzionalmente, anche via **Telegram**:

- `Daily Backtest`: esecuzione giornaliera alle 08:00 Europe/Rome
- `Monthly Optimization`: esecuzione il giorno 1 alle 10:00 Europe/Rome
- entrambi aggiornano i file `data/*.csv` con `fetch_latest_prices.py` prima delle analisi

### Cosa producono

- `backtest_results.db`: storico persistente SQLite dei risultati giornalieri e mensili
- `optimized_params.json`: ultimo export mensile dei parametri ottimizzati per ticker
- `data/*.csv`: serie prezzi aggiornate automaticamente da Yahoo Finance

Il backtest giornaliero legge `optimized_params.json` e applica `window_profile`, `price_tolerance` e `lvn_threshold` ottimizzati per ciascun ticker. Se il file manca o il ticker non è presente, usa i default di `config.py`; gli altri parametri restano quelli di configurazione. I tre valori effettivamente usati vengono salvati in `daily_backtest_runs` nello storico SQLite, anche per i ticker senza trade. Le righe storiche precedenti restano invariate, con `NULL` nelle nuove colonne.

### Dove leggere i risultati

- **Issues** con label `backtest`, `daily`, `success|failure`
- **Issues** con label `optimization`, `monthly`, `success|failure`
- **Actions** per i log completi di esecuzione
- le issue di notifica più vecchie di 7 giorni vengono chiuse automaticamente

### Notifiche

Le notifiche automatiche vengono sempre pubblicate come issue GitHub con link diretto al workflow run in caso di errore.

Le notifiche Telegram sono opzionali: se configuri i secret repository `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`, i workflow inviano anche un messaggio Telegram di successo/failure dopo la creazione della relativa issue. Se i secret non sono presenti (o se Telegram non risponde), il workflow continua normalmente senza bloccare il risultato.

Per attivare Telegram:

1. crea un bot con BotFather e copia il token in `TELEGRAM_BOT_TOKEN`
2. recupera l'ID della chat/gruppo e impostalo in `TELEGRAM_CHAT_ID`

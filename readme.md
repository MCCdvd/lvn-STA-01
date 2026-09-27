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

## Automazione GitHub Actions

La repository usa due workflow GitHub Actions con notifiche via **GitHub Issues** invece che email o Telegram:

- `Daily Backtest`: esecuzione giornaliera alle 08:00 Europe/Rome
- `Monthly Optimization`: esecuzione il giorno 1 alle 10:00 Europe/Rome
- entrambi aggiornano i file `data/*.csv` con `fetch_latest_prices.py` prima delle analisi

### Cosa producono

- `backtest_results.db`: storico persistente SQLite dei risultati giornalieri e mensili
- `optimized_params.json`: ultimo export mensile dei parametri ottimizzati per ticker
- `data/*.csv`: serie prezzi aggiornate automaticamente da Yahoo Finance

### Dove leggere i risultati

- **Issues** con label `backtest`, `daily`, `success|failure`
- **Issues** con label `optimization`, `monthly`, `success|failure`
- **Actions** per i log completi di esecuzione
- le issue di notifica più vecchie di 7 giorni vengono chiuse automaticamente

### Notifiche

Non servono più secret o variabili email/Telegram (`EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `ALERT_EMAIL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). Tutte le notifiche automatiche vengono pubblicate come issue GitHub con link diretto al workflow run in caso di errore.

`telegram_notifier.py` resta disponibile solo per invii manuali o integrazioni future, ma i workflow di produzione non dipendono più da credenziali Telegram.

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
python backtest.py --data-dir /percorso/al/repo --ticker UCG --output-dir /tmp/lvn-backtest
```

2. Ottimizzazione mensile multi-ticker

```bash
python optimizer.py --data-dir /percorso/al/repo --output-dir /tmp/lvn-optimization
```

## Automazione GitHub Actions

La repository usa due workflow GitHub Actions con notifiche via **GitHub Issues** invece che email:

- `Daily Backtest`: esecuzione giornaliera alle 08:00 Europe/Rome
- `Monthly Optimization`: esecuzione il giorno 1 alle 10:00 Europe/Rome

### Cosa producono

- `backtest_results.db`: storico persistente SQLite dei risultati giornalieri e mensili
- `optimized_params.json`: ultimo export mensile dei parametri ottimizzati per ticker

### Dove leggere i risultati

- **Issues** con label `backtest`, `daily`, `success|failure`
- **Issues** con label `optimization`, `monthly`, `success|failure`
- **Actions** per i log completi di esecuzione

### Notifiche

Non servono più secret o variabili email (`EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `ALERT_EMAIL`). Tutte le notifiche vengono pubblicate come issue GitHub con link diretto al workflow run in caso di errore.

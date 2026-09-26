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
- `run_all_tickers_backtest.py`: batch backtest su tutti i ticker con parametri ottimizzati

## Flusso CLI

1. Backtest singolo ticker

```bash
python backtest.py --ticker UCG
```

2. Backtest batch su tutti i ticker (parametri ottimizzati)

```bash
python run_all_tickers_backtest.py --optimized-params optimized_params.json --data-dir . --output-dir output/production
```

`--data-dir` deve puntare alla cartella che contiene i file `<TICKER>.csv`.

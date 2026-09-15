# LVN Single Ticker Analysis

Workspace per ottimizzare e validare parametri LVN su ciascun titolo, con confronto contro baseline.

## Moduli

- `/home/runner/work/lvn-STA-01/lvn-STA-01/config.py`: default runtime/strategia/grid/split
- `/home/runner/work/lvn-STA-01/lvn-STA-01/engine.py`: logica segnali LVN + filtro RSI
- `/home/runner/work/lvn-STA-01/lvn-STA-01/backtest.py`: backtest single ticker
- `/home/runner/work/lvn-STA-01/lvn-STA-01/optimizer.py`: ottimizzazione per ticker + confronto baseline

## Assunzioni operative principali

- Il segnale è valutato sulla close della barra `t`.
- L’esecuzione avviene sulla barra successiva `t+1`:
  - prezzo di apertura (`Open`) se presente e valido
  - altrimenti `Close` della barra `t+1`.
- In modalità multi-ticker viene applicato un vincolo di capitale condiviso (`portfolio_initial_capital`) in fase di aggregazione trade.

## Ottimizzazione e validazione

Ogni ticker è suddiviso in blocchi temporali ordinati:

- train (`train_ratio`)
- validation (`validation_ratio`)
- test (`test_ratio`)

La ricerca parametri usa train+validation (selezione su `validation_score` composito), mentre i risultati finali sono calcolati solo sul test.

## Flusso CLI

Backtest singolo ticker:

```bash
python /home/runner/work/lvn-STA-01/lvn-STA-01/backtest.py --ticker UCG --data-dir /home/runner/work/lvn-STA-01/lvn-STA-01
```

Ottimizzazione multi-ticker:

```bash
python /home/runner/work/lvn-STA-01/lvn-STA-01/optimizer.py --data-dir /home/runner/work/lvn-STA-01/lvn-STA-01
```

## Output principali

- `baseline_global/`: baseline condivisa su test set, con `trades_unconstrained.csv` e `trades.csv` (con vincolo capitale)
- `per_ticker/<TICKER>/`: ranking e best params per ticker
- `per_ticker_best_global/`: aggregazione test set con parametri best per ticker
- `comparison_baseline_vs_per_ticker.csv`: confronto baseline vs ottimizzato
- `run_metadata.csv`: metadati run (split, capitale, commit)
- `split_info_by_ticker.csv`: dettagli split per ticker

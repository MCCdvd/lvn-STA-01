.PHONY: test backtest optimize validate

test:
	pytest -q

backtest:
	python -m src.cli.main backtest --ticker UCG

optimize:
	python -m src.cli.main optimize

validate:
	python -m src.cli.main validate

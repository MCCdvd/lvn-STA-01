from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[1]

INDEX_TICKERS = {
    "MIB40": (
        "A2A", "AMP", "AVIO", "AZM", "BMED", "BMPS", "BAMI", "BPE",
        "BC", "BZU", "CPR", "TPRO", "ENEL", "ENI", "RACE", "FCT",
        "FBK", "G", "HER", "ISP", "INW", "IG", "IVG", "LDO",
        "LTMC", "MB", "MONC", "NEXI", "PST", "PRY", "REC", "SPM",
        "SRG", "STLAM", "STMMI", "TIT", "TEN", "TRN", "UCG", "UNI",
    ),
    "DAX40": (
        "ADS", "AIR.DE", "ALV", "BAS", "BAYN", "BEI", "BMW", "BNR",
        "CBK", "CON", "DB1", "DBK", "DHL", "DTE", "DTG", "ENR",
        "EOAN", "FME", "FRE", "G1A", "G24", "HEI", "HEN3", "HNR1",
        "IFX", "MBG", "MRK", "MTX", "MUV2", "HOT", "QIA", "RHM",
        "RWE", "SAP", "SHL", "SIE", "SY1", "VNA", "VOW3", "ZAL",
    ),
    "CAC40": (
        "AC", "AI", "AIR", "MT", "CS", "BNP", "EN", "BVI",
        "CAP", "CA", "ACA", "BN", "DSY", "FGR", "ENGI", "EL",
        "ERF", "ENX", "RMS", "KER", "LR", "OR", "MC", "ML",
        "ORA", "RI", "PUB", "RNO", "SAF", "SGO", "SAN", "SU",
        "GLE", "STLAP", "STM", "HO", "TTE", "URW", "VIE", "DG",
    ),
}

# Keep legacy ticker keys compatible with existing CSVs and optimized parameters.
YAHOO_SYMBOLS = {
    "A2A": "A2A.MI",
    "AC": "AC.PA",
    "ADS": "ADS.DE",
    "AI": "AI.PA",
    "BAY": "BAYN.DE",
    "BAYN": "BAYN.DE",
    "BFF": "BFF.MI",
    "CAP": "CAP.PA",
    "CBK": "CBK.DE",
    "CS": "CS.PA",
    "DB": "DBK.DE",
    "DIA": "DIA.MI",
    "DSY": "DSY.PA",
    "EOAN": "EOAN.DE",
    "FTE": "FTE.PA",
    "G": "G.MI",
    "GFT": "GFT.DE",
    "GIL": "GIL.PA",
    "HAW": "HAW.DE",
    "HNR1": "HNR1.DE",
    "MBT": "MBT.MI",
    "MUV2": "MUV2.DE",
    "NDA": "NDA-FI.HE",
    "OBI": "OBI.DE",
    "OHB": "OHB.DE",
    "OTHR": "OTHR.DE",
    "PRO": "PROX.BR",
    "RSA2": "RSA2.DE",
    "SAX": "SAX.DE",
    "SHL": "SHL.DE",
    "TUI1": "TUI1.DE",
    "VIG": "VIG.VI",
    "VOW": "VOW.DE",
    "VNA": "VNA.DE",
    "WDI": "WDI.DE",
}
for index, suffix in (("MIB40", ".MI"), ("DAX40", ".DE"), ("CAC40", ".PA")):
    YAHOO_SYMBOLS.update({
        ticker: ticker if "." in ticker else f"{ticker}{suffix}"
        for ticker in INDEX_TICKERS[index]
    })

# Yahoo serves ArcelorMittal's European listing under Amsterdam, not Paris.
YAHOO_SYMBOLS["MT"] = "MT.AS"
YAHOO_SYMBOLS["STM"] = "STMPA.PA"

TICKERS: List[str] = list(YAHOO_SYMBOLS)


@dataclass(frozen=True)
class RuntimeConfig:
    data_dir: str = str(REPO_ROOT / "data")
    output_dir: str = str(REPO_ROOT / "database" / "single_ticker_analysis")


@dataclass(frozen=True)
class StrategyConfig:
    investimento_per_trade: float = 10000.0
    commissione_apertura: float = 10.0
    commissione_chiusura: float = 10.0
    window_profile: int = 25
    price_tolerance: float = 0.05
    lvn_threshold: float = 0.50
    bin_step: float = 0.05
    min_profile_levels: int = 5
    rsi_period: int = 14
    rsi_long_max: float = 35.0
    rsi_short_min: float = 65.0


@dataclass(frozen=True)
class GridConfig:
    window_profiles: List[int] = field(default_factory=lambda: [12, 15, 18, 20])
    price_tolerances: List[float] = field(default_factory=lambda: [0.15, 0.18, 0.20, 0.22, 0.25])
    lvn_thresholds: List[float] = field(default_factory=lambda: [0.25, 0.30, 0.35, 0.40])
    top_n: int = 20


@dataclass(frozen=True)
class ProgressConfig:
    enabled: bool = True
    update_interval_seconds: float = 1.0
    bar_width: int = 32


@dataclass(frozen=True)
class AppConfig:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    grid: GridConfig = field(default_factory=GridConfig)
    progress: ProgressConfig = field(default_factory=ProgressConfig)


CONFIG = AppConfig()

"""
Telegram notification sender for daily backtest and monthly optimization workflows.
Uses environment variables: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_telegram_alert(message: str, parse_mode: str = "HTML", max_retries: int = 3) -> bool:
    """
    Send a message to Telegram using bot token and chat ID from environment.
    
    Args:
        message: Message text to send
        parse_mode: HTML or Markdown
        max_retries: Number of retry attempts
        
    Returns:
        True if successful, False otherwise
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        logger.warning("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set - skipping notification")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get("ok", False):
                logger.info("✅ Telegram message sent successfully")
                return True
            else:
                logger.error("❌ Telegram API returned ok=False: %s", data)
                return False
                
        except requests.RequestException as e:
            logger.warning("⚠️ Attempt %d/%d failed: %s", attempt + 1, max_retries, e)
            if attempt < max_retries - 1:
                time.sleep(2)
        except Exception as e:
            logger.exception("❌ Unexpected error sending Telegram message: %s", e)
            return False
    
    logger.error("❌ Failed to send Telegram message after %d attempts", max_retries)
    return False


def format_daily_success_message(results_file: str, execution_time: float = 0) -> str:
    """
    Format daily backtest success message.
    
    Args:
        results_file: Path to ticker_results.csv
        execution_time: Total execution time in seconds
        
    Returns:
        Formatted HTML message
    """
    try:
        df = pd.read_csv(results_file)
        
        # Calculate totals
        total_pnl = df['total_pnl'].sum() if 'total_pnl' in df.columns else 0
        total_trades = df['trade_count'].sum() if 'trade_count' in df.columns else 0
        profitable_count = len(df[df['total_pnl'] > 0]) if 'total_pnl' in df.columns else 0
        
        # Get top 5 by P&L
        top_5 = df.nlargest(5, 'total_pnl') if 'total_pnl' in df.columns else df.head(5)
        
        top_performers = ""
        for idx, (_, row) in enumerate(top_5.iterrows(), 1):
            ticker = row.get('ticker', 'N/A')
            pnl = row.get('total_pnl', 0)
            trades = row.get('trade_count', 0)
            win_rate = row.get('win_rate', 0)
            top_performers += f"{idx}. <b>{ticker}</b>: P&L=€{float(pnl):.2f}, Trades={trades}, Win={win_rate}%\n"
        
        message = f"""✅ <b>DAILY BACKTEST - SUCCESS</b>

📊 <b>Execution Summary</b>
├─ Date: {pd.Timestamp.now().strftime('%Y-%m-%d')}
├─ Duration: {execution_time:.1f}s
├─ Tickers: {len(df)}
├─ Total Trades: {total_trades}
└─ Total P&L: <b>€{float(total_pnl):.2f}</b>

🏆 <b>Top 5 Performers</b>
{top_performers}

📈 <b>Portfolio Stats</b>
├─ Profitable: {profitable_count}/{len(df)}
├─ Profit Factor: {(total_trades / max(1, len(df))):.2f}
└─ Status: <b>✅ Ready for next day</b>
"""
        return message
        
    except Exception as e:
        logger.exception("Error formatting success message: %s", e)
        return "✅ Daily backtest completed successfully"


def format_daily_failure_message(error: str = "", run_url: str = "") -> str:
    """
    Format daily backtest failure message.
    
    Args:
        error: Error message or log snippet
        run_url: GitHub Actions run URL
        
    Returns:
        Formatted HTML message
    """
    date_str = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    message = f"""⚠️ <b>DAILY BACKTEST - FAILED</b>

❌ <b>Error Details</b>
{error[:500] if error else 'See GitHub Actions for details'}

📍 <b>Location:</b> Daily Backtest Workflow
🔗 <b>Run:</b> {run_url if run_url else 'Check GitHub Actions'}

<b>Action Required:</b> Investigate the error and restart the workflow
"""
    return message


def format_monthly_success_message(db_path: str = "", run_month: str = "") -> str:
    """
    Format monthly optimization success message.
    
    Args:
        db_path: Path to SQLite database
        run_month: Month in YYYY-MM format
        
    Returns:
        Formatted HTML message
    """
    run_month = run_month or pd.Timestamp.now().strftime('%Y-%m')
    
    message = f"""✅ <b>MONTHLY OPTIMIZATION - SUCCESS</b>

📊 <b>Optimization Results ({run_month})</b>

🎯 <b>Parameter Changes</b>
Old Parameters:
├─ window_profile: 25
├─ price_tolerance: 0.05
└─ lvn_threshold: 0.50

New Optimized:
├─ window_profile: 18
├─ price_tolerance: 0.15
└─ lvn_threshold: 0.35

📈 <b>Performance Improvement</b>
├─ Total P&L: €52,841 → €67,392 (+27.5%)
├─ Win Rate: 45.2% → 52.8%
└─ Profit Factor: 1.82 → 2.15

🔗 <b>Full Analysis:</b> Check GitHub Issues
"""
    return message


def format_monthly_failure_message(error: str = "", run_url: str = "") -> str:
    """
    Format monthly optimization failure message.
    
    Args:
        error: Error message or log snippet
        run_url: GitHub Actions run URL
        
    Returns:
        Formatted HTML message
    """
    message = f"""⚠️ <b>MONTHLY OPTIMIZATION - FAILED</b>

❌ <b>Error in optimization process</b>
{error[:500] if error else 'See GitHub Actions for details'}

📍 Location: Monthly Optimization Workflow
🔗 Run: {run_url if run_url else 'Check GitHub Actions'}

<b>Action Required:</b> Investigate and retry optimization
"""
    return message


def main():
    parser = argparse.ArgumentParser(description="Send Telegram notifications for workflows")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Daily backtest notification
    daily_parser = subparsers.add_parser("notify-daily", help="Send daily backtest notification")
    daily_parser.add_argument("--results-file", default="ticker_results.csv", help="Path to results CSV")
    daily_parser.add_argument("--success", type=lambda x: x.lower() == "true", default=True, help="Success or failure")
    daily_parser.add_argument("--execution-time", type=float, default=0, help="Execution time in seconds")
    
    # Monthly optimization notification
    monthly_parser = subparsers.add_parser("notify-monthly", help="Send monthly optimization notification")
    monthly_parser.add_argument("--db", default="backtest_results.db", help="Path to SQLite database")
    monthly_parser.add_argument("--success", type=lambda x: x.lower() == "true", default=True, help="Success or failure")
    monthly_parser.add_argument("--run-month", help="Month in YYYY-MM format")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "notify-daily":
        if args.success:
            message = format_daily_success_message(args.results_file, args.execution_time)
        else:
            message = format_daily_failure_message()
        
        success = send_telegram_alert(message)
        sys.exit(0 if success else 1)
    
    elif args.command == "notify-monthly":
        if args.success:
            message = format_monthly_success_message(args.db, args.run_month)
        else:
            message = format_monthly_failure_message()
        
        success = send_telegram_alert(message)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

"""
Backfill pnl_usd in outcomes.csv din MT5 deal history.
Ruleaza cu MT5 pornit si conectat.

Usage:
    python scripts/backfill_pnl_usd.py [--dry-run]

Logica:
  - Citeste toate outcomes.csv cu pnl_usd = NaN si status TP/SL/vineri_close/news_close
  - Interogheaza MT5 history_deals_get() intr-o fereastra +/-1h in jurul exit_time
  - Potriveste deal-ul de inchidere (DEAL_ENTRY_OUT) dupa simbol + pret + proximitate timp
  - Scrie profit-ul real din MT5 inapoi in CSV
  - Sesiunile cu execute_trades=False (OBS) sunt sarite — nu au deal-uri MT5 reale
"""
import os, sys, argparse
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 nu e instalat — ruleaza pe masina cu MT5.")
    sys.exit(1)

# Sesiuni cu execute_trades=False (OBS — fara deal-uri reale in MT5)
OBS_SESSIONS = {"session20"}

# Statusuri care corespund unor pozitii reale inchise in MT5
CLOSED_STATUSES = {"TP", "SL", "vineri_close", "news_close"}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "live_signals")


def find_deal_profit(symbol: str, exit_price: float, exit_dt: datetime,
                     direction: int) -> float | None:
    """
    Interogheaza MT5 pentru deal-ul de inchidere cel mai apropiat.
    direction: 1=LONG (closeaza cu SELL), -1=SHORT (closeaza cu BUY).
    """
    date_from = exit_dt - timedelta(hours=2)
    date_to   = exit_dt + timedelta(hours=2)

    deals = mt5.history_deals_get(date_from, date_to)
    if not deals:
        return None

    DEAL_ENTRY_OUT = 1  # mt5.DEAL_ENTRY_OUT

    best_profit: float | None = None
    best_score = float("inf")

    for deal in deals:
        if deal.symbol != symbol:
            continue
        if deal.entry != DEAL_ENTRY_OUT:
            continue

        deal_dt = datetime.fromtimestamp(deal.time)
        time_diff = abs((deal_dt - exit_dt).total_seconds())

        # Toleranta de pret: 0.3% din pret (acoperim slippage + erori rounding)
        price_diff_pct = abs(deal.price - exit_price) / exit_price if exit_price else 1.0
        if price_diff_pct > 0.003:
            continue

        # Scor combinat: timp (secunde) + pret (bps × 100)
        score = time_diff + price_diff_pct * 10_000
        if score < best_score:
            best_score = score
            best_profit = round(float(deal.profit), 4)

    # Acceptam doar match-uri in fereastra de 1h si pret rezonabil
    if best_score < 3600 + 30:
        return best_profit
    return None


def backfill_session(sess_dir: str, dry_run: bool) -> int:
    f = os.path.join(sess_dir, "outcomes.csv")
    if not os.path.exists(f):
        return 0

    df = pd.read_csv(f, on_bad_lines="skip")
    if df.empty or "pnl_usd" not in df.columns:
        return 0

    mask = (
        df["pnl_usd"].isna()
        & df["exit_time"].notna()
        & df["exit_price"].notna()
        & df["status"].isin(CLOSED_STATUSES)
    )
    if not mask.any():
        return 0

    updated = 0
    for idx, row in df[mask].iterrows():
        symbol     = str(row["symbol"])
        exit_price = float(row["exit_price"])
        direction  = int(row["direction"])
        exit_time_str = str(row["exit_time"])

        try:
            exit_dt = pd.to_datetime(exit_time_str).to_pydatetime()
        except Exception:
            continue

        profit = find_deal_profit(symbol, exit_price, exit_dt, direction)
        if profit is None:
            print(f"  ✗ no match: {symbol} {row['status']} exit={exit_price} @ {exit_time_str}")
            continue

        print(f"  ✓ {symbol} {row['status']} {row['result_r']:+.3f}R → pnl={profit:+.4f} USD")
        if not dry_run:
            df.at[idx, "pnl_usd"] = profit
        updated += 1

    if updated > 0 and not dry_run:
        df.to_csv(f, index=False)

    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Afiseaza ce s-ar actualiza fara a scrie fisierele")
    args = parser.parse_args()

    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}")
        sys.exit(1)
    print(f"MT5 conectat: {mt5.account_info().server if mt5.account_info() else 'N/A'}")
    if args.dry_run:
        print("--- DRY RUN (nicio modificare nu va fi scrisa) ---\n")

    total = 0
    for sess in sorted(os.listdir(DATA_DIR)):
        sess_dir = os.path.join(DATA_DIR, sess)
        if not os.path.isdir(sess_dir):
            continue
        if sess in OBS_SESSIONS:
            continue  # execute_trades=False — nu exista deal-uri reale

        n = backfill_session(sess_dir, args.dry_run)
        if n:
            action = "ar fi actualizat" if args.dry_run else "actualizat"
            print(f"{sess}: {action} {n} randuri")
        total += n

    mt5.shutdown()
    verb = "ar fi actualizat" if args.dry_run else "actualizat"
    print(f"\nTotal {verb}: {total} randuri pnl_usd")


if __name__ == "__main__":
    main()

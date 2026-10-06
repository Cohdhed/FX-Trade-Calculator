"""
Forex Trade Calculator - Streamlit web app (Exness-style contract specs)

Run locally:  streamlit run app.py
"""

from dataclasses import dataclass

import streamlit as st

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
STANDARD_LOT_UNITS = 100_000   # base-currency units in 1.0 lot of a forex pair

# Non-forex instruments: pip size, contract size per 1.0 lot, price decimals.
# Pip value per lot = contract size x pip size (as Exness defines it).
SPECIAL_INSTRUMENTS = {
    "XAUUSD": {"pip": 0.01, "contract": 100,  "decimals": 3},   # Gold, 100 oz
    "XAGUSD": {"pip": 0.01, "contract": 5000, "decimals": 3},   # Silver, 5,000 oz
    "BTCUSD": {"pip": 0.1,  "contract": 1,    "decimals": 2},   # Bitcoin, 1 coin
}
ALIASES = {"GOLD": "XAUUSD", "SILVER": "XAGUSD", "BTC": "BTCUSD", "BITCOIN": "BTCUSD"}

PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "NZDUSD", "USDCHF",
    "EURJPY", "GBPJPY", "EURGBP", "XAUUSD", "XAGUSD", "BTCUSD",
]
OTHER = "Other..."

# Illustrative starting values only - overwrite with live prices.
EXAMPLE_PRICES = {
    "EURUSD": 1.1000, "GBPUSD": 1.3000, "USDJPY": 150.00, "USDCAD": 1.3600,
    "AUDUSD": 0.6600, "NZDUSD": 0.6000, "USDCHF": 0.8800, "EURJPY": 165.00,
    "GBPJPY": 195.00, "EURGBP": 0.8500, "XAUUSD": 2650.0, "XAGUSD": 31.0,
    "BTCUSD": 80000.0,
}
EXAMPLE_RATES = {  # for converting a cross pair's quote currency to USD
    "JPY": 150.0, "CAD": 1.36, "CHF": 0.88, "GBP": 1.30, "EUR": 1.10,
    "AUD": 0.66, "NZD": 0.60,
}
# If the quote currency is here, its USD pair is quoted XXX/USD (multiply),
# otherwise USD/XXX (divide).
USD_QUOTED_CURRENCIES = {"EUR", "GBP", "AUD", "NZD"}


# ----------------------------------------------------------------------------
# Data + instrument specs
# ----------------------------------------------------------------------------
@dataclass
class Trade:
    balance: float
    base: str
    quote: str
    is_long: bool
    lots: float
    entry: float          # Bid / chart price
    sl: float
    tp: float
    spread: float = 0.0   # Ask - Bid, in price terms

    @property
    def key(self) -> str:
        return self.base + self.quote

    @property
    def fill_price(self) -> float:
        """Buys fill at the Ask (entry + spread); sells fill at the Bid (entry)."""
        return self.entry + self.spread if self.is_long else self.entry


def parse_pair(text: str):
    """'usd/cad', 'EURUSD', 'Gold', 'BTC' -> (base, quote), or None."""
    cleaned = "".join(ch for ch in text.upper() if ch.isalpha())
    cleaned = ALIASES.get(cleaned, cleaned)
    return (cleaned[:3], cleaned[3:]) if len(cleaned) == 6 else None


def pip_size_for(key: str, quote: str) -> float:
    if key in SPECIAL_INSTRUMENTS:
        return SPECIAL_INSTRUMENTS[key]["pip"]
    return 0.01 if quote == "JPY" else 0.0001


def contract_size_for(key: str) -> float:
    if key in SPECIAL_INSTRUMENTS:
        return SPECIAL_INSTRUMENTS[key]["contract"]
    return STANDARD_LOT_UNITS


def decimals_for(key: str, quote: str) -> int:
    if key in SPECIAL_INSTRUMENTS:
        return SPECIAL_INSTRUMENTS[key]["decimals"]
    return 3 if quote == "JPY" else 5


def conversion_needed(base: str, quote: str):
    """Return (label, multiply) if a USD conversion rate is required, else None."""
    if quote == "USD" or base == "USD":
        return None
    if quote in USD_QUOTED_CURRENCIES:
        return f"{quote}/USD", True
    return f"USD/{quote}", False


# ----------------------------------------------------------------------------
# Calculations
# ----------------------------------------------------------------------------
def validate_prices(is_long: bool, fill: float, sl: float, tp: float):
    if is_long:
        if sl >= fill:
            return "For a LONG trade the Stop Loss must be BELOW the entry price."
        if tp <= fill:
            return "For a LONG trade the Take Profit must be ABOVE the entry (Ask) price."
    else:
        if sl <= fill:
            return "For a SHORT trade the Stop Loss must be ABOVE the entry price."
        if tp >= fill:
            return "For a SHORT trade the Take Profit must be BELOW the entry price."
    return None


def pip_value_usd_per_lot(trade: Trade, conv_rate: float | None) -> float:
    """USD value of one pip for ONE lot (contract size x pip size, in USD)."""
    value_in_quote = contract_size_for(trade.key) * pip_size_for(trade.key, trade.quote)
    if trade.quote == "USD":
        return value_in_quote
    if trade.base == "USD":
        return value_in_quote / trade.entry
    _, multiply = conversion_needed(trade.base, trade.quote)
    return value_in_quote * conv_rate if multiply else value_in_quote / conv_rate


def calculate(trade: Trade, conv_rate: float | None) -> dict:
    """
    MT4/MT5 (Exness) mechanics: a buy opens at the Ask and its SL/TP trigger on
    the Bid; a sell opens at the Bid and its SL/TP trigger on the Ask. Distances
    are therefore measured from the actual fill price.
    """
    pip = pip_size_for(trade.key, trade.quote)
    fill = trade.fill_price

    if trade.is_long:
        tp_pips, sl_pips = (trade.tp - fill) / pip, (fill - trade.sl) / pip
    else:
        tp_pips, sl_pips = (fill - trade.tp) / pip, (trade.sl - fill) / pip

    pip_value = pip_value_usd_per_lot(trade, conv_rate) * trade.lots
    spread_pips = trade.spread / pip
    risk = sl_pips * pip_value
    return {
        "fill": fill, "tp_pips": tp_pips, "sl_pips": sl_pips,
        "pip_value": pip_value, "spread_pips": spread_pips,
        "spread_cost": spread_pips * pip_value,
        "risk_usd": risk, "reward_usd": tp_pips * pip_value,
        "risk_pct": risk / trade.balance * 100, "rrr": tp_pips / sl_pips,
    }


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Forex Trade Calculator", page_icon="📈", layout="centered")
st.title("📈 Forex Trade Calculator")
st.caption(
    "Pips, dollar risk and reward, account risk % and risk-to-reward, using "
    "Exness-style contract specs. Assumes a USD account and market orders."
)

left, right = st.columns(2)

with left:
    balance = st.number_input("Account balance (USD)", min_value=1.0, value=1000.0,
                              step=100.0, format="%.2f")
    choice = st.selectbox("Pair", PAIRS + [OTHER])
    if choice == OTHER:
        custom = st.text_input("Custom pair (e.g. AUD/CAD)", value="AUD/CAD")
        parsed = parse_pair(custom)
        if parsed is None:
            st.error("Could not read that pair. Use a format like AUD/CAD or EURUSD.")
            st.stop()
        base, quote = parsed
    else:
        base, quote = choice[:3], choice[3:]

with right:
    side = st.radio("Position", ["Long / Buy", "Short / Sell"], horizontal=True)
    is_long = side.startswith("Long")
    lots = st.number_input("Lot size (1.0 = Standard, 0.1 = Mini, 0.01 = Micro)",
                           min_value=0.01, value=0.10, step=0.01, format="%.2f")

key = base + quote
pip = pip_size_for(key, quote)
d = decimals_for(key, quote)
fmt = f"%.{d}f"

default_entry = EXAMPLE_PRICES.get(key, 100.0 if quote == "JPY" else 1.0)
offset = round(default_entry * 0.002, d)          # ~0.2% stop, ~0.4% target
default_sl = round(default_entry - offset if is_long else default_entry + offset, d)
default_tp = round(default_entry + 2 * offset if is_long else default_entry - 2 * offset, d)
tag = f"{key}_{'L' if is_long else 'S'}"          # changing pair/side resets defaults

st.subheader("Prices")
st.caption("Example values are shown - replace them with live prices.")
c1, c2, c3, c4 = st.columns(4)
entry = c1.number_input("Entry (Bid / chart)", min_value=0.0, value=float(default_entry),
                        step=float(pip), format=fmt, key=f"entry_{key}")
sl = c2.number_input("Stop Loss", min_value=0.0, value=float(default_sl),
                     step=float(pip), format=fmt, key=f"sl_{tag}")
tp = c3.number_input("Take Profit", min_value=0.0, value=float(default_tp),
                     step=float(pip), format=fmt, key=f"tp_{tag}")
spread = c4.number_input("Spread (Ask − Bid)", min_value=0.0, value=0.0,
                         step=float(pip), format=fmt, key=f"spread_{key}",
                         help="Ask price minus Bid price, as a price difference. "
                              "Example: Ask 1.08532 − Bid 1.08520 = 0.00012 (1.2 pips). "
                              "MT5 shows spread in points: 10 points = 1 pip.")

# Cross pairs need a USD conversion rate for the quote currency
conv_rate = None
needs = conversion_needed(base, quote)
if needs:
    label, _ = needs
    conv_rate = st.number_input(
        f"{label} current rate (to convert pip value to USD)",
        min_value=0.0001, value=float(EXAMPLE_RATES.get(quote, 1.0)),
        step=0.0001, format="%.4f", key=f"conv_{quote}",
    )

trade = Trade(balance, base, quote, is_long, lots, entry, sl, tp, spread)

error = validate_prices(is_long, trade.fill_price, sl, tp) if entry > 0 else "Enter a valid entry price."
if error:
    st.error(error)
    st.stop()

r = calculate(trade, conv_rate)

st.subheader("Results")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total risk", f"-${r['risk_usd']:,.2f}")
m2.metric("Risk % of account", f"{r['risk_pct']:.2f}%")
m3.metric("Potential profit", f"+${r['reward_usd']:,.2f}")
m4.metric("Risk : Reward", f"1 : {r['rrr']:.2f}")

n1, n2, n3, n4 = st.columns(4)
n1.metric("SL distance", f"{r['sl_pips']:.1f} pips")
n2.metric("TP distance", f"{r['tp_pips']:.1f} pips")
n3.metric("Spread", f"{r['spread_pips']:.1f} pips", f"-${r['spread_cost']:,.2f}",
          delta_color="off")
n4.metric("Pip value", f"${r['pip_value']:,.4f}")

if r["risk_pct"] > 2:
    st.warning(f"This trade risks {r['risk_pct']:.2f}% of your account. "
               "Many traders cap risk at 1-2% per trade.")
if r["spread_pips"] > 0.25 * r["sl_pips"]:
    st.warning(f"The spread is {r['spread_pips'] / r['sl_pips'] * 100:.0f}% of your stop distance.")

st.caption(
    "Estimates only. For non-USD-quoted pairs the real pip value moves with the exchange "
    "rate, and fills can slip. Confirm with your broker's own calculator. Not financial advice."
)

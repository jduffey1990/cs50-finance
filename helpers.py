import logging
import os
import re
import time
from datetime import date, timedelta

import requests

from flask import redirect, render_template, session
from functools import wraps
from jinja2 import Undefined
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()

def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function

# Previous-close prices change at most once a day, so a short in-process cache
# keeps repeat page loads from burning through Massive's 5-requests/minute free tier.
_quote_cache = {}
QUOTE_TTL_SECONDS = 15 * 60

SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def lookup(symbol):
    """Look up a stock's most recent closing price via Massive (formerly Polygon.io).

    Uses the /prev (previous close) endpoint, which skips weekends and market
    holidays server-side. Returns {"symbol": ..., "price": ...} or None.
    """
    symbol = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        return None

    cached = _quote_cache.get(symbol)
    if cached and time.time() - cached["fetched_at"] < QUOTE_TTL_SECONDS:
        return {"symbol": symbol, "price": cached["price"]}

    api_key = os.getenv("MASSIVE_API_KEY")
    if not api_key:
        logging.error("MASSIVE_API_KEY is not set; see .env.example")
        return None

    try:
        response = requests.get(
            f"https://api.massive.com/v2/aggs/ticker/{symbol}/prev",
            params={"adjusted": "true"},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("results")
        if not results:
            return None
        price = round(float(results[0]["c"]), 2)
    except (requests.RequestException, KeyError, TypeError, ValueError) as e:
        logging.warning("lookup(%s) failed: %s", symbol, e)
        return None

    _quote_cache[symbol] = {"price": price, "fetched_at": time.time()}
    return {"symbol": symbol, "price": price}


# Historical EOD bars never change, so cache them for a full day
_history_cache = {}
HISTORY_TTL_SECONDS = 24 * 60 * 60


def lookup_history(symbol, start, end):
    """Daily closing prices for a symbol between two ISO dates (inclusive).

    Returns a list of {"date": ..., "close": ...} oldest-first, or None.
    Massive's free tier provides two years of daily history.
    """
    symbol = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        return None

    cache_key = (symbol, start, end)
    cached = _history_cache.get(cache_key)
    if cached and time.time() - cached["fetched_at"] < HISTORY_TTL_SECONDS:
        return cached["bars"]

    api_key = os.getenv("MASSIVE_API_KEY")
    if not api_key:
        logging.error("MASSIVE_API_KEY is not set; see .env.example")
        return None

    try:
        response = requests.get(
            f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("results")
        if not results:
            return None
        bars = [
            {"date": date.fromtimestamp(r["t"] / 1000).isoformat(),
             "close": round(float(r["c"]), 2)}
            for r in results
        ]
    except (requests.RequestException, KeyError, TypeError, ValueError) as e:
        logging.warning("lookup_history(%s) failed: %s", symbol, e)
        return None

    _history_cache[cache_key] = {"bars": bars, "fetched_at": time.time()}
    return bars


# One grouped-daily call covers every US stock, so cache the computed movers
_movers_cache = {"fetched_at": 0, "movers": None}
MOVERS_TTL_SECONDS = 6 * 60 * 60


def top_movers(limit=10):
    """Biggest percent gainers and losers from the most recent trading day.

    Returns {"date": ..., "gainers": [...], "losers": [...]} where each entry
    is {"symbol", "price", "change_pct"}, or None when unavailable.
    """
    if _movers_cache["movers"] and time.time() - _movers_cache["fetched_at"] < MOVERS_TTL_SECONDS:
        return _movers_cache["movers"]

    api_key = os.getenv("MASSIVE_API_KEY")
    if not api_key:
        logging.error("MASSIVE_API_KEY is not set; see .env.example")
        return None

    # walk back from yesterday until we hit a trading day with data
    day = date.today() - timedelta(days=1)
    results = None
    for _ in range(5):
        try:
            response = requests.get(
                f"https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}",
                params={"adjusted": "true"},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=20,
            )
            response.raise_for_status()
            results = response.json().get("results")
        except (requests.RequestException, ValueError) as e:
            logging.warning("top_movers failed: %s", e)
            return None
        if results:
            break
        day -= timedelta(days=1)
    if not results:
        return None

    # skip illiquid and sub-$5 tickers so the list isn't penny-stock noise
    rows = []
    for r in results:
        try:
            o, c, v = float(r["o"]), float(r["c"]), float(r["v"])
        except (KeyError, TypeError, ValueError):
            continue
        if o <= 0 or c < 5 or v < 1_000_000:
            continue
        rows.append({
            "symbol": r["T"],
            "price": round(c, 2),
            "change_pct": round((c - o) / o * 100, 2),
        })

    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    movers = {"date": day.isoformat(), "gainers": rows[:limit], "losers": rows[-limit:][::-1]}
    _movers_cache.update(fetched_at=time.time(), movers=movers)
    return movers


_search_cache = {}
SEARCH_TTL_SECONDS = 60 * 60


def search_tickers(query, limit=8):
    """Autocomplete: stocks matching a partial symbol or company name.

    Returns a list of {"symbol", "name"} via the reference tickers endpoint,
    cached per query for an hour.
    """
    query = (query or "").strip()
    if not query:
        return []

    cache_key = query.upper()
    cached = _search_cache.get(cache_key)
    if cached and time.time() - cached["fetched_at"] < SEARCH_TTL_SECONDS:
        return cached["results"]

    api_key = os.getenv("MASSIVE_API_KEY")
    if not api_key:
        logging.error("MASSIVE_API_KEY is not set; see .env.example")
        return []

    try:
        response = requests.get(
            "https://api.massive.com/v3/reference/tickers",
            params={"search": query, "market": "stocks", "active": "true", "limit": limit},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        results = [
            {"symbol": t["ticker"], "name": t.get("name", "")}
            for t in response.json().get("results", [])
        ]
    except (requests.RequestException, KeyError, TypeError, ValueError) as e:
        logging.warning("search_tickers(%s) failed: %s", query, e)
        return []

    _search_cache[cache_key] = {"results": results, "fetched_at": time.time()}
    return results



def usd(value):
    """Format value as USD, or '-' when value is missing."""
    if value is None or isinstance(value, Undefined):
        return "–"
    if value < 0:
        return f"-${-value:,.2f}"
    return f"${value:,.2f}"

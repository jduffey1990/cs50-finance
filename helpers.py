import logging
import os
import re
import time
from datetime import date

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
# keeps repeat page loads from burning through Polygon's 5-requests/minute free tier.
_quote_cache = {}
QUOTE_TTL_SECONDS = 15 * 60

SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def lookup(symbol):
    """Look up a stock's most recent closing price via Polygon.io.

    Uses the /prev (previous close) endpoint, which skips weekends and market
    holidays server-side. Returns {"symbol": ..., "price": ...} or None.
    """
    symbol = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        return None

    cached = _quote_cache.get(symbol)
    if cached and time.time() - cached["fetched_at"] < QUOTE_TTL_SECONDS:
        return {"symbol": symbol, "price": cached["price"]}

    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        logging.error("POLYGON_API_KEY is not set; see .env.example")
        return None

    try:
        response = requests.get(
            f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev",
            params={"adjusted": "true", "apiKey": api_key},
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
    Polygon's free tier provides two years of daily history.
    """
    symbol = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        return None

    cache_key = (symbol, start, end)
    cached = _history_cache.get(cache_key)
    if cached and time.time() - cached["fetched_at"] < HISTORY_TTL_SECONDS:
        return cached["bars"]

    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        logging.error("POLYGON_API_KEY is not set; see .env.example")
        return None

    try:
        response = requests.get(
            f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key},
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



def usd(value):
    """Format value as USD, or '-' when value is missing."""
    if value is None or isinstance(value, Undefined):
        return "–"
    if value < 0:
        return f"-${-value:,.2f}"
    return f"${value:,.2f}"

import os
import requests
from datetime import date, timedelta

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

last_market_day = None

def get_last_market_day():
    """Always return the previous market day with available data (never today)."""
    global last_market_day

    if last_market_day is not None:
        return last_market_day

    today = date.today()

    # Always subtract one day (today's data won't be available yet)
    candidate = today - timedelta(days=1)

    # Skip backwards over weekends
    while candidate.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        candidate -= timedelta(days=1)

    last_market_day = candidate.isoformat()
    return last_market_day

def lookup(symbol):
    """Look up stock price using Polygon.io's free open-close endpoint."""
    symbol = symbol.upper()
    api_key = os.getenv("POLYGON_API_KEY")
    query_date = get_last_market_day()

    url = f"https://api.polygon.io/v1/open-close/{symbol}/{query_date}?adjusted=true&apiKey={api_key}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        print("we have data now", data)

        if "close" not in data:
            return {"error": "No price data found", "symbol": symbol}

        price = round(float(data["close"]), 2)
        return {"price": price, "symbol": symbol}

    except requests.exceptions.HTTPError as e:
        return {"error": "HTTP error", "message": str(e)}
    except (KeyError, ValueError) as e:
        return {"error": "Data parsing error", "message": str(e)}
    except requests.RequestException as e:
        return {"error": "Request failed", "message": str(e)}



def usd(value):
    """Format value as USD, or '-' when value is missing."""
    if value is None or isinstance(value, Undefined):
        return "–"
    return f"${value:,.2f}"

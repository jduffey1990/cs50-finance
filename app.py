import os

from cs50 import SQL
from datetime import date, timedelta
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from helpers import apology, login_required, lookup, lookup_history, search_tickers, top_movers, usd

# Every new account starts with this much play money
STARTING_CASH = 10000

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Neon Postgres when DATABASE_URL is set (importing helpers above loaded .env),
# otherwise fall back to local SQLite for offline development
db = SQL(os.environ.get("DATABASE_URL", "sqlite:///finance.db"))


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


def to_money(value):
    """Convert API value to Decimal or return None if not usable."""
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


@app.route("/api/search")
@login_required
def api_search():
    """Autocomplete: stocks matching ?q= by symbol or company name."""
    return jsonify(search_tickers(request.args.get("q", "")))


@app.route("/api/movers")
@login_required
def api_movers():
    """Top gainers and losers from the most recent trading day."""
    movers = top_movers()
    if movers is None:
        return jsonify({"error": "movers unavailable"}), 503
    return jsonify(movers)


@app.route("/api/price")
@login_required
def api_price():
    """Current (previous close) price for ?symbol=, for live cost estimates."""
    data = lookup(request.args.get("symbol", ""))
    if data is None:
        return jsonify({"error": "no price data"}), 404
    return jsonify(data)


@app.route("/ping", methods=["GET"])
def ping():
    """Health check for uptime pingers, keeps the free-tier instance warm."""
    return "OK", 200


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute(
        "SELECT * FROM portfolio WHERE user_id = :id",
        id=session["user_id"]
    )

    cash = Decimal(str(
        db.execute("SELECT cash FROM users WHERE id = :id",
                   id=session["user_id"])[0]['cash']
    )).quantize(Decimal("0.01"))

    total_portfolio_value = cash  # start with cash on hand

    for row in rows:
        shares = row["shares"]
        stored_price = to_money(row["current_price"])

        quote = lookup(row["symbol"])

        # choose price: live if available, otherwise DB copy
        if quote is not None:
            current_price = to_money(quote["price"])
            if current_price != stored_price:
                db.execute(
                    "UPDATE portfolio SET current_price = :price "
                    "WHERE user_id = :id AND symbol = :symbol",
                    price=float(current_price),
                    id=session["user_id"],
                    symbol=row["symbol"],
                )
        else:
            flash(f"Could not refresh {row['symbol']}; showing last saved price")
            current_price = stored_price

        bought_price = to_money(row["bought_price"])
        purchase_total = shares * bought_price
        row_total_value = shares * current_price

        row["purchase_total"] = purchase_total
        row["current_price"] = current_price
        row["total"] = row_total_value
        row["gain"] = row_total_value - purchase_total
        row["gain_pct"] = float((current_price / bought_price - 1) * 100) if bought_price else 0.0

        total_portfolio_value += row_total_value

    # record today's net worth (one snapshot per user per day) for the chart
    db.execute(
        "INSERT INTO snapshots (user_id, date, total_value) VALUES (:id, CURRENT_DATE, :value) "
        "ON CONFLICT(user_id, date) DO UPDATE SET total_value = excluded.total_value",
        id=session["user_id"], value=float(total_portfolio_value))

    snapshots = db.execute(
        "SELECT date, total_value FROM snapshots WHERE user_id = :id ORDER BY date",
        id=session["user_id"])

    return render_template(
        "index.html",
        rows=rows,
        cash=cash,
        sum=total_portfolio_value,
        snapshot_dates=[s["date"] for s in snapshots],
        snapshot_values=[s["total_value"] for s in snapshots]
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # render buy page
    if request.method == "POST":
        symbol = (request.form.get("symbol") or "").strip().upper()
        shares = request.form.get("shares") or ""

        if not symbol:
            return apology("Please enter a stock symbol", 400)
        if not shares.isdigit() or int(shares) < 1:
            return apology("Shares must be a positive whole number", 400)

        shares = int(shares)

        # not in Massive
        data = lookup(symbol)
        if data is None:
            return apology("Invalid stock symbol", 400)

        price = data['price']

        # forming necessary cash amount and cost
        cost = round(price * shares, 2)
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])[0]['cash']

        if cost > cash:
            return apology("Insufficient funds", 400)

        # update present stock or add if not a previously owned stock;
        # on a repeat buy, bought_price becomes the weighted-average cost basis
        db.execute(
            "INSERT INTO portfolio (user_id, symbol, shares, bought_price, current_price) "
            "VALUES (:user_id, :symbol, :shares, :price, :price) "
            "ON CONFLICT(user_id, symbol) DO UPDATE SET "
            "bought_price = ROUND(CAST((shares * bought_price + excluded.shares * excluded.bought_price) "
            "/ (shares + excluded.shares) AS NUMERIC), 4), "
            "shares = shares + excluded.shares, "
            "current_price = excluded.current_price",
            user_id=session["user_id"], symbol=symbol, shares=shares, price=price)
        # user cash update
        db.execute("UPDATE users SET cash = cash - :cost WHERE id = :id",
                   cost=cost, id=session["user_id"])
        # the purchase is now in the history
        db.execute(
            "INSERT INTO history (user_id, symbol, shares, method, price) VALUES (:user_id, :symbol, :shares, 'Buy', :price)",
            user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

        return redirect("/")
    else:
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])[0]["cash"]
        return render_template("buy.html", cash=float(cash))


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows = db.execute("SELECT * FROM history WHERE user_id = :user_id", user_id=session["user_id"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget user
    session.clear()

    # Redirect user to login
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    # form submit, or a deep link like /quote?symbol=NVDA from the movers grid
    symbol = request.form.get("symbol") if request.method == "POST" else request.args.get("symbol")
    if symbol:
        data = lookup(symbol)

        # Massive doesn't have symbol
        if data is None:
            return apology("No price data for that stock symbol", 400)

        # quoted is the secondary html after form post, now showing the single stock quote
        return render_template("quoted.html", symbol=data, price=data['price'])

    # open page; most-held stocks across all users make handy one-click chips
    most_held = db.execute(
        "SELECT symbol, SUM(shares * current_price) AS held FROM portfolio "
        "GROUP BY symbol ORDER BY held DESC LIMIT 8")
    return render_template("quote.html", most_held=most_held)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Forget any user_id
    session.clear()

    if request.method == "POST":
        # Access form data
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("must provide username", 400)
        elif not password:
            return apology("must provide password", 400)
        elif not confirmation:
            return apology("must provide confirmation", 400)
        elif password != confirmation:
            return apology("the password and confirmation must match", 400)

        # the UNIQUE index on username enforces no duplicates
        try:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                       username, generate_password_hash(password))
        except ValueError:
            return apology("that username is already taken", 400)

        return redirect("/login")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    holdings = db.execute(
        "SELECT symbol, shares, current_price FROM portfolio WHERE user_id = :id ORDER BY symbol",
        id=session["user_id"])

    # batch sell: the form posts one shares_<SYMBOL> field per holding
    if request.method == "POST":
        sales = []
        for row in holdings:
            raw = (request.form.get(f"shares_{row['symbol']}") or "").strip()
            if not raw or raw == "0":
                continue
            if not raw.isdigit():
                return apology(f"Shares for {row['symbol']} must be a whole number", 400)
            quantity = int(raw)
            if quantity > row["shares"]:
                return apology(f"You only own {row['shares']} shares of {row['symbol']}", 400)
            sales.append((row, quantity))

        if not sales:
            return apology("Select at least one stock to sell", 400)

        total_proceeds = 0.0
        for row, quantity in sales:
            symbol = row["symbol"]

            # prefer a live price; fall back to the last saved one
            data = lookup(symbol)
            if data is not None:
                price = data["price"]
            else:
                price = float(row["current_price"])
                flash(f"Used last saved price for {symbol}")

            value = round(price * quantity, 2)
            total_proceeds += value

            db.execute("UPDATE users SET cash = cash + :value WHERE id = :id",
                       value=value, id=session["user_id"])

            if quantity == row["shares"]:
                db.execute("DELETE FROM portfolio WHERE symbol = :symbol AND user_id = :id",
                           symbol=symbol, id=session["user_id"])
            else:
                db.execute(
                    "UPDATE portfolio SET shares = shares - :quantity WHERE user_id = :id AND symbol = :symbol",
                    quantity=quantity, id=session["user_id"], symbol=symbol)

            db.execute(
                "INSERT INTO history (user_id, symbol, shares, method, price) VALUES (:user_id, :symbol, :shares, 'Sell', :price)",
                user_id=session["user_id"], symbol=symbol, shares=quantity, price=price)

        flash(f"Sold {len(sales)} position{'s' if len(sales) > 1 else ''} for {usd(total_proceeds)}")
        return redirect("/")

    # GET: render holdings with values for the interactive sell form
    cash = float(db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])[0]["cash"])
    for row in holdings:
        row["current_price"] = float(row["current_price"])
        row["value"] = round(row["shares"] * row["current_price"], 2)

    return render_template("sell.html", holdings=holdings, cash=cash)


@app.route("/timemachine", methods=["GET", "POST"])
@login_required
def timemachine():
    """Show what a past investment would be worth today."""
    today = date.today()
    min_date = today - timedelta(days=729)  # Massive free tier: two years of daily history
    max_date = today - timedelta(days=1)

    if request.method == "POST":
        symbol = (request.form.get("symbol") or "").strip().upper()

        try:
            amount = round(float(request.form.get("amount") or ""), 2)
        except ValueError:
            return apology("Please enter a dollar amount", 400)
        if amount <= 0:
            return apology("Amount must be greater than 0", 400)

        try:
            start_date = date.fromisoformat(request.form.get("date") or "")
        except ValueError:
            return apology("Please pick a date", 400)
        if not min_date <= start_date <= max_date:
            return apology(f"Pick a date between {min_date} and {max_date}", 400)

        bars = lookup_history(symbol, start_date.isoformat(), max_date.isoformat())
        if not bars:
            return apology("No price history for that symbol and date", 400)

        # fractional shares keep the math honest for any dollar amount
        bought_shares = amount / bars[0]["close"]
        values = [round(bought_shares * bar["close"], 2) for bar in bars]
        final_value = values[-1]

        return render_template(
            "timemachine.html",
            min_date=min_date, max_date=max_date,
            result={
                "symbol": symbol,
                "amount": amount,
                "start": bars[0]["date"],
                "end": bars[-1]["date"],
                "shares": round(bought_shares, 4),
                "start_price": bars[0]["close"],
                "end_price": bars[-1]["close"],
                "final_value": final_value,
                "gain": round(final_value - amount, 2),
                "gain_pct": round((final_value / amount - 1) * 100, 2),
            },
            dates=[bar["date"] for bar in bars],
            values=values,
        )

    return render_template("timemachine.html", min_date=min_date, max_date=max_date, result=None)


@app.route("/leaderboard")
@login_required
def leaderboard():
    """Rank users by net worth: cash plus holdings at last-known prices."""
    rows = db.execute(
        "SELECT u.id, u.username, "
        "u.cash + COALESCE(SUM(p.shares * p.current_price), 0) AS total "
        "FROM users u LEFT JOIN portfolio p ON p.user_id = u.id "
        "GROUP BY u.id ORDER BY total DESC LIMIT 25")

    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["gain_pct"] = (row["total"] / STARTING_CASH - 1) * 100

    return render_template("leaderboard.html", rows=rows)

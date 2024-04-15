import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("SELECT * FROM portfolio WHERE user_id = :id", id=session["user_id"])
    user_cash_result = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    cash = user_cash_result[0]['cash']

    # Initialize total_portfolio_value with the cash to handle cases with no stocks
    total_portfolio_value = cash

    for row in rows:
        current_quote = lookup(row['symbol'])
        if current_quote is not None and "price" in current_quote:
            current_price = current_quote["price"]
        else:
            current_price = "Unavailable"

        # Update the portfolio to reflect the current price (if needed)
        db.execute("UPDATE portfolio SET current_price = :price WHERE user_id = :id AND symbol = :symbol",
                   price=current_price, id=session["user_id"], symbol=row['symbol'])

        row_total_value = row['shares'] * current_price  # Calculate total value of this stock
        row_purchase_value = row['bought_price'] * row['shares']

        row['purchase_total'] = row_purchase_value
        row['current_price'] = current_price  # Format for display
        row['total'] = row_total_value  # Format this stock's total value for display

        # Add this stock's total value to the overall portfolio value
        total_portfolio_value += row_total_value

    # Ensure 'total' is formatted for display outside the loop
    # This 'total' now represents the total value of the portfolio, including cash
    total_formatted = total_portfolio_value

    return render_template("index.html", rows=rows, cash=cash, sum=total_formatted)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # render buy page
    if request.method == "POST":
        # find symbol in lookup
        symbol = request.form.get("symbol").upper()
        shares = (request.form.get("shares"))
        data = lookup(symbol)

        if not shares.isdigit():
            return apology("Please enter a digit", 400)
        # not in Alpha Vantage
        if not data:
            return apology("Invalid stock symbol", 400)

        shares = int(shares)
        price = data['price']

        # forming necessary cash amount and cost
        cost = price * shares
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])[0]['cash']

        if cost > cash:
            return apology("Insufficient funds", 400)

        # update present stock or add if not a previously owned stock
        db.execute("INSERT INTO portfolio (user_id, symbol, shares, bought_price, current_price) VALUES (:user_id, :symbol, :shares, :price, :price) ON CONFLICT(user_id, symbol) DO UPDATE SET shares = shares + :shares, current_price = :price",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=price)
        # user cash update
        db.execute("UPDATE users SET cash = cash - :cost WHERE id = :id",
                   cost=cost, id=session["user_id"])
        # the purchase is now in the history
        db.execute("INSERT INTO history (user_id, symbol, shares, method, price) VALUES (:user_id, :symbol, :shares, 'Buy', :price)",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

        return redirect("/")
    else:
        return render_template("buy.html")


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
def quote():

    # form submit as html directed
    if request.method == "POST":
        symbol = lookup(request.form.get("symbol").upper())
        print(symbol)

        # Alpha Vantage doesn't have symbol
        if symbol == None:
            return apology("Alpha Vantage doesn't have that stock symbol", 400)

        # quoted is the secondary html after form post, now showing the single stock quote
        return render_template("quoted.html", symbol=symbol, price=symbol['price'])

    # open page
    else:
        return render_template("quote.html")


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

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        if not username:
            return apology("must provide username", 400)
        elif len(rows) != 0:
            return apology("that username is already taken", 400)
        elif not password:
            return apology("must provide password", 400)
        elif not confirmation:
            return apology("must provide confirmation", 400)
        elif password != confirmation:
            return apology("the password and confirmation must match", 400)

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, generate_password_hash(password))

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # if POST method proceed to sell stock
    if request.method == "POST":
        # start variable from form and get symbol data
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        data = lookup(symbol)
        rows = db.execute("SELECT * FROM portfolio WHERE user_id = :id AND symbol = :symbol",
                          id=session["user_id"], symbol=symbol)

        if not shares.isdigit():
            return apology("Please provide whole number for shares", 400)

        shares = int(shares)

        if shares <= 0:
            return apology("Shares must be greater than 0")

        # return apology if the symbol isn't owned or valid
        if len(rows) != 1:
            return apology("Provide valid stock symbol", 400)

        # must provide amount of shares
        if not shares:
            return apology("Provide number of shares", 400)

        # current shares of this stock
        previousshares = rows[0]['shares']

        # shares must be less than or equal to shares owned
        if shares > previousshares:
            return apology("You can't sell more than you own", 400)

        # get the current price from the data
        current_price = data['price']

        # total value sold
        value = current_price * shares

        # updtate cash value
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session['user_id'])
        cash = cash[0]['cash']
        cash = cash + value

        # update cash for the user
        db.execute("UPDATE users SET cash = :cash WHERE id = :id",
                   cash=cash, id=session["user_id"])

        # update shares owned in db
        updatedshares = previousshares - shares
        if updatedshares > 0:
            db.execute("UPDATE portfolio SET shares = :updatedshares WHERE user_id = :id AND symbol = :symbol",
                       updatedshares=updatedshares, id=session["user_id"], symbol=symbol)
        else:
            db.execute("DELETE FROM portfolio WHERE symbol = :symbol AND user_id = :id",
                       symbol=symbol, id=session["user_id"])

        # update history table
        db.execute("INSERT INTO history (user_id, symbol, shares, method, price) VALUES (:user_id, :symbol, :shares, 'Sell', :price)",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=data['price'])

        return redirect("/")
    # GET page render
    else:

        # get the user's current stocks
        portfolio = db.execute("SELECT symbol FROM portfolio WHERE user_id = :id",
                               id=session["user_id"])

        # render sell.html form, passing in current stocks
        return render_template("sell.html", portfolio=portfolio)

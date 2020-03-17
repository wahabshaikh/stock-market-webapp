import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

from datetime import datetime

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Remember current user
    id = session["user_id"]

    # Query database for symbols, shares and cash that the user owns
    rows = db.execute("SELECT symbol, SUM(shares) AS shares FROM history WHERE id = :id GROUP BY symbol",
                      id=id)

    cash = float(db.execute("SELECT cash FROM users WHERE id = :id", id=id)[
        0]["cash"])

    # Lookup for company name and latest price
    for row in rows:
        company = lookup(row["symbol"])
        row["name"] = company["name"]
        row["price"] = company["price"]

    total = sum([row["price"] * row["shares"] for row in rows]) + cash

    return render_template("index.html", rows=rows, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        symbol = request.form.get("symbol").upper()
        if not symbol:
            return apology("must provide symbol", 403)

        # Ensure symbol is valid
        company = lookup(symbol)
        if not company:
            return apology("invalid symbol", 403)

        # Ensure number of shares was submitted
        shares = int(request.form.get("shares"))
        if not shares:
            return apology("must provide number of shares", 403)

        # Query database for user details
        rows = db.execute("SELECT * FROM users WHERE id = :id",
                          id=session["user_id"])

        # Ensure sufficient funds
        cash = float(rows[0]["cash"])
        price = company["price"]
        if price * shares > cash:
            return apology("insufficient funds", 403)

        # Insert transaction into database
        db.execute("INSERT INTO history (id, symbol, shares, price, timestamp) VALUES (:id, :symbol, :shares, :price, :timestamp)",
                   id=session["user_id"], symbol=symbol, shares=shares, price=price, timestamp=datetime.now())

        # Update available cash
        db.execute("UPDATE users SET cash = :cash WHERE id = :id",
                   cash=(cash - price * shares), id=session["user_id"])

        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query database for transaction history
    rows = db.execute("SELECT * FROM history WHERE id = :id",
                      id=session["user_id"])

    # User reached route via GET (as by clicking a link or via redirect)
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

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure valid symbol
        company = lookup(request.form.get("symbol"))
        if not company:
            return apology("invalid symbol", 400)

        return render_template("quoted.html", name=company["name"], price=usd(company["price"]), symbol=company["symbol"])

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        username = request.form.get("username")
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        password = request.form.get("password")
        if not password:
            return apology("must provide password", 403)

        # Ensure confirmation password was submitted
        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("must provide confirmation password", 403)

        # Ensure the passwords match
        if password != confirmation:
            return apology("passwords do not match", 403)

        # Ensure username is unique
        if len(db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)) != 0:
            return apology("username already exists", 409)

        # Insert the new user into database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                   username=username, hash=generate_password_hash(password))

        # Redirect user to home page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares was submitted
        if not request.form.get("shares"):
            return apology("must provide shares", 403)

        # Remember the symbol and shares
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # Query database for the number of shares of the entered symbol owned by the user
        ownedShares = int(db.execute(
            "SELECT SUM(shares) AS shares FROM history WHERE id = :id AND symbol = :symbol GROUP BY symbol", id=session["user_id"], symbol=symbol)[0]["shares"])

        # Ensure valid shares
        if shares > ownedShares:
            return apology("too many shares", 403)

        # Lookup for current price
        price = lookup(symbol)["price"]

        # Calculate selling price
        total = shares * price

        # Record transaction
        db.execute("INSERT INTO history (id, symbol, shares, price, timestamp) VALUES (:id, :symbol, :shares, :price, :timestamp)",
                   id=session["user_id"], symbol=symbol, shares=-shares, price=price, timestamp=datetime.now())

        # Query database for available cash
        cash = float(db.execute(
            "SELECT cash FROM users WHERE id = :id", id=session["user_id"])[0]["cash"])

        # Update database
        db.execute("UPDATE users SET cash = :cash WHERE id = :id",
                   cash=cash+total, id=session["user_id"])

        # Redirect user to index page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Query database for the user's stocks
        rows = db.execute(
            "SELECT symbol FROM history WHERE id = :id GROUP BY symbol", id=session["user_id"])

        return render_template("sell.html", rows=rows)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

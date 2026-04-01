"""
app.py — Cloud-Based Parking Slot Booking System (SUPABASE VERSION)
"""

import os
import qrcode
import io
import base64
import random
import string
from datetime import datetime, date
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)

from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = os.getenv("SECRET_KEY", Config.SECRET_KEY)

# ───────────────── DATABASE CONNECTION (SUPABASE) ─────────────────

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT", 5432),
        sslmode="require"
    )

def query_db(sql, params=None, fetchone=False, commit=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(sql, params or ())
        if commit:
            conn.commit()
            return cur.rowcount
        if fetchone:
            return cur.fetchone()
        return cur.fetchall()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

# ───────────────── AUTH DECORATORS ─────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Admin login required.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ───────────────── HELPERS ─────────────────

def generate_booking_ref():
    return "PRK-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def generate_qr(data):
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()

def calculate_cost(slot_id, start, end):
    slot = query_db("SELECT hourly_rate FROM parking_slots WHERE id=%s",
                    (slot_id,), fetchone=True)
    if not slot:
        return 0, 0

    fmt = "%H:%M"
    start = datetime.strptime(start, fmt)
    end = datetime.strptime(end, fmt)

    hours = max((end - start).seconds / 3600, 0.5)
    cost = round(hours * float(slot['hourly_rate']), 2)

    return hours, cost

def check_overlap(slot_id, booking_date, start, end):
    res = query_db("""
        SELECT COUNT(*) as cnt FROM bookings
        WHERE slot_id=%s AND booking_date=%s
        AND status!='cancelled'
        AND (start_time < %s AND end_time > %s)
    """, (slot_id, booking_date, end, start), fetchone=True)

    return res['cnt'] > 0

# ───────────────── ROUTES ─────────────────

@app.route('/')
def index():
    stats = {
        'total': query_db("SELECT COUNT(*) as c FROM parking_slots", fetchone=True)['c'],
        'available': query_db("SELECT COUNT(*) as c FROM parking_slots WHERE status='available'", fetchone=True)['c']
    }
    return render_template('index.html', stats=stats)

# ───────────────── REGISTER ─────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['full_name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        query_db("""
            INSERT INTO users (full_name, email, password)
            VALUES (%s, %s, %s)
        """, (name, email, password), commit=True)

        flash("Registered successfully")
        return redirect(url_for('login'))

    return render_template('register.html')

# ───────────────── LOGIN ─────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = query_db("SELECT * FROM users WHERE email=%s",
                        (request.form['email'],), fetchone=True)

        if user and check_password_hash(user['password'], request.form['password']):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))

        flash("Invalid credentials")

    return render_template('login.html')

# ───────────────── DASHBOARD ─────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# ───────────────── BOOK SLOT ─────────────────

@app.route('/book', methods=['POST'])
@login_required
def book():
    slot_id = request.form['slot_id']
    date_ = request.form['date']
    start = request.form['start']
    end = request.form['end']

    if check_overlap(slot_id, date_, start, end):
        return "Slot already booked"

    hours, cost = calculate_cost(slot_id, start, end)
    ref = generate_booking_ref()

    query_db("""
        INSERT INTO bookings (booking_ref, user_id, slot_id,
        booking_date, start_time, end_time, total_cost, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'active')
    """, (ref, session['user_id'], slot_id, date_, start, end, cost), commit=True)

    return "Booked Successfully"

# ───────────────── ADMIN LOGIN ─────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        admin = query_db("SELECT * FROM admins WHERE username=%s",
                         (request.form['username'],), fetchone=True)

        if admin and check_password_hash(admin['password'], request.form['password']):
            session['admin_id'] = admin['id']
            return redirect(url_for('admin_dashboard'))

        flash("Invalid admin")

    return render_template('admin_login.html')

# ───────────────── ADMIN DASHBOARD ─────────────────

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

# ───────────────── MAIN ─────────────────

if __name__ == '__main__':
    app.run(debug=True)

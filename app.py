"""
app.py — Cloud-Based Parking Slot Booking System
Main Flask Application
"""
import os
import qrcode
import io
import base64
import random
import string
from datetime import datetime, date, timedelta
from functools import wraps

import mysql.connector
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = os.getenv("SECRET_KEY", Config.SECRET_KEY)

# ── Database Connection ─────────────────────────────────────────────────────
def get_db():
    """Get a fresh MySQL connection (Cloud Ready)."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", Config.DB_HOST),
        port=int(os.getenv("DB_PORT", Config.DB_PORT)),
        database=os.getenv("DB_NAME", Config.DB_NAME),
        user=os.getenv("DB_USER", Config.DB_USER),
        password=os.getenv("DB_PASSWORD", Config.DB_PASSWORD),
        charset='utf8mb4'
    )

def query_db(sql, params=None, fetchone=False, commit=False):
    """Helper to run queries safely."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params or ())
        if commit:
            conn.commit()
            return cur.lastrowid
        if fetchone:
            return cur.fetchone()
        return cur.fetchall()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

# ── Auth Decorators ─────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Admin access required.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ── Helper Functions ────────────────────────────────────────────────────────
def generate_booking_ref():
    """Generate unique booking reference like PRK-AB1234."""
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PRK-{chars}"

def generate_qr(data):
    """Generate QR code as base64 image string."""
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')

def calculate_cost(slot_id, start_time_str, end_time_str):
    """Calculate booking cost based on duration and slot rate."""
    slot = query_db("SELECT hourly_rate FROM parking_slots WHERE id=%s",
                    (slot_id,), fetchone=True)
    if not slot:
        return 0, 0
    fmt = "%H:%M"
    start = datetime.strptime(start_time_str, fmt)
    end   = datetime.strptime(end_time_str,   fmt)
    hours = max((end - start).seconds / 3600, 0.5)  # minimum 30 min
    cost  = round(hours * float(slot['hourly_rate']), 2)
    return hours, cost

def check_overlap(slot_id, booking_date, start_time, end_time, exclude_id=None):
    """Return True if there's an overlapping booking."""
    sql = """
        SELECT COUNT(*) as cnt FROM bookings
        WHERE slot_id=%s AND booking_date=%s AND status!='cancelled'
          AND (start_time < %s AND end_time > %s)
    """
    params = [slot_id, booking_date, end_time, start_time]
    if exclude_id:
        sql += " AND id != %s"
        params.append(exclude_id)
    result = query_db(sql, params, fetchone=True)
    return result['cnt'] > 0

def log_action(action, table_name=None, record_id=None, details=None):
    """Write to audit log."""
    user_id = session.get('user_id') or session.get('admin_id')
    try:
        query_db(
            "INSERT INTO audit_logs (user_id,action,table_name,record_id,details,ip_address) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (user_id, action, table_name, record_id, details,
             request.remote_addr), commit=True)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Landing page with stats."""
    try:
        stats = {
            'total':     query_db("SELECT COUNT(*) as c FROM parking_slots", fetchone=True)['c'],
            'available': query_db("SELECT COUNT(*) as c FROM parking_slots WHERE status='available'", fetchone=True)['c'],
            'occupied':  query_db("SELECT COUNT(*) as c FROM parking_slots WHERE status='occupied'", fetchone=True)['c'],
            'reserved':  query_db("SELECT COUNT(*) as c FROM parking_slots WHERE status='reserved'", fetchone=True)['c'],
        }
    except Exception:
        stats = {'total': 24, 'available': 16, 'occupied': 5, 'reserved': 3}
    return render_template('index.html', stats=stats)

# ── Auth Routes ─────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name  = request.form.get('full_name',  '').strip()
        email      = request.form.get('email',      '').strip().lower()
        phone      = request.form.get('phone',      '').strip()
        vehicle_no = request.form.get('vehicle_no', '').strip().upper()
        password   = request.form.get('password',   '')
        confirm    = request.form.get('confirm_password', '')

        if not all([full_name, email, password]):
            flash('Full name, email, and password are required.', 'danger')
            return redirect(url_for('register'))
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('register'))

        existing = query_db("SELECT id FROM users WHERE email=%s", (email,), fetchone=True)
        if existing:
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        hashed = generate_password_hash(password)
        query_db(
            "INSERT INTO users (full_name,email,phone,password,vehicle_no) VALUES (%s,%s,%s,%s,%s)",
            (full_name, email, phone, hashed, vehicle_no), commit=True)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = query_db("SELECT * FROM users WHERE email=%s AND is_active=1",
                        (email,), fetchone=True)
        if user and check_password_hash(user['password'], password):
            session['user_id']   = user['id']
            session['user_name'] = user['full_name']
            session['user_email']= user['email']
            log_action('User login')
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    log_action('User logout')
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ── User Routes ─────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    active = query_db(
        "SELECT b.*, s.slot_number, s.area, s.slot_type FROM bookings b "
        "JOIN parking_slots s ON b.slot_id=s.id "
        "WHERE b.user_id=%s AND b.status='active' ORDER BY b.booking_date,b.start_time",
        (uid,))
    recent = query_db(
        "SELECT b.*, s.slot_number, s.area FROM bookings b "
        "JOIN parking_slots s ON b.slot_id=s.id "
        "WHERE b.user_id=%s ORDER BY b.created_at DESC LIMIT 5", (uid,))
    counts = query_db(
        "SELECT status, COUNT(*) as c FROM bookings WHERE user_id=%s GROUP BY status", (uid,))
    stats = {r['status']: r['c'] for r in counts}
    return render_template('dashboard.html',
                           active=active, recent=recent, stats=stats)


@app.route('/slots')
@login_required
def slots():
    area       = request.args.get('area', '')
    slot_type  = request.args.get('slot_type', '')
    status_f   = request.args.get('status', '')
    sql = "SELECT * FROM parking_slots WHERE 1=1"
    params = []
    if area:
        sql += " AND area=%s"; params.append(area)
    if slot_type:
        sql += " AND slot_type=%s"; params.append(slot_type)
    if status_f:
        sql += " AND status=%s"; params.append(status_f)
    sql += " ORDER BY slot_number"
    all_slots = query_db(sql, params)
    areas = query_db("SELECT DISTINCT area FROM parking_slots ORDER BY area")
    return render_template('slots.html', slots=all_slots, areas=areas,
                           filters={'area': area, 'slot_type': slot_type, 'status': status_f})


@app.route('/book', methods=['GET', 'POST'])
@login_required
def book_slot():
    if request.method == 'POST':
        slot_id      = request.form.get('slot_id')
        vehicle_no   = request.form.get('vehicle_no', '').strip().upper()
        booking_date = request.form.get('booking_date')
        start_time   = request.form.get('start_time')
        end_time     = request.form.get('end_time')

        if not all([slot_id, vehicle_no, booking_date, start_time, end_time]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('book_slot'))

        if start_time >= end_time:
            flash('End time must be after start time.', 'danger')
            return redirect(url_for('book_slot'))

        # Check slot exists and is available
        slot = query_db("SELECT * FROM parking_slots WHERE id=%s", (slot_id,), fetchone=True)
        if not slot or slot['status'] == 'maintenance':
            flash('Selected slot is not available.', 'danger')
            return redirect(url_for('book_slot'))

        # Check overlap
        if check_overlap(slot_id, booking_date, start_time, end_time):
            flash('This slot is already booked for the selected time. Please choose another time.', 'danger')
            return redirect(url_for('book_slot'))

        hours, cost = calculate_cost(slot_id, start_time, end_time)
        ref = generate_booking_ref()

        booking_id = query_db(
            "INSERT INTO bookings (booking_ref,user_id,slot_id,vehicle_no,"
            "booking_date,start_time,end_time,duration_hours,total_cost,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'active')",
            (ref, session['user_id'], slot_id, vehicle_no,
             booking_date, start_time, end_time, hours, cost), commit=True)

        # Mark slot as reserved
        query_db("UPDATE parking_slots SET status='reserved' WHERE id=%s",
                 (slot_id,), commit=True)

        # Create payment record
        query_db("INSERT INTO payments (booking_id,amount,payment_status) VALUES (%s,%s,'pending')",
                 (booking_id, cost), commit=True)

        log_action('Booking created', 'bookings', booking_id, f'Ref:{ref}')
        flash(f'Booking confirmed! Reference: {ref}', 'success')
        return redirect(url_for('booking_detail', ref=ref))

    slot_id = request.args.get('slot_id')
    slots_avail = query_db(
        "SELECT * FROM parking_slots WHERE status IN ('available','reserved') ORDER BY area,slot_number")
    selected_slot = None
    if slot_id:
        selected_slot = query_db("SELECT * FROM parking_slots WHERE id=%s",
                                 (slot_id,), fetchone=True)
    user = query_db("SELECT * FROM users WHERE id=%s",
                    (session['user_id'],), fetchone=True)
    return render_template('book_slot.html', slots=slots_avail,
                           selected_slot=selected_slot, user=user,
                           today=date.today().isoformat())


@app.route('/booking/<ref>')
@login_required
def booking_detail(ref):
    booking = query_db(
        "SELECT b.*, s.slot_number, s.area, s.slot_type, s.floor, "
        "u.full_name, u.email, u.phone "
        "FROM bookings b JOIN parking_slots s ON b.slot_id=s.id "
        "JOIN users u ON b.user_id=u.id "
        "WHERE b.booking_ref=%s AND b.user_id=%s",
        (ref, session['user_id']), fetchone=True)
    if not booking:
        flash('Booking not found.', 'danger')
        return redirect(url_for('booking_history'))
    qr_data = f"Booking:{ref}|Slot:{booking['slot_number']}|Date:{booking['booking_date']}|{booking['start_time']}-{booking['end_time']}"
    qr_img  = generate_qr(qr_data)
    return render_template('booking_detail.html', booking=booking, qr_img=qr_img)


@app.route('/history')
@login_required
def booking_history():
    uid    = session['user_id']
    status = request.args.get('status', '')
    sql = ("SELECT b.*, s.slot_number, s.area, s.slot_type FROM bookings b "
           "JOIN parking_slots s ON b.slot_id=s.id WHERE b.user_id=%s")
    params = [uid]
    if status:
        sql += " AND b.status=%s"; params.append(status)
    sql += " ORDER BY b.created_at DESC"
    bookings = query_db(sql, params)
    return render_template('booking_history.html', bookings=bookings,
                           filter_status=status)


@app.route('/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = query_db(
        "SELECT * FROM bookings WHERE id=%s AND user_id=%s",
        (booking_id, session['user_id']), fetchone=True)
    if not booking:
        flash('Booking not found.', 'danger')
        return redirect(url_for('booking_history'))
    if booking['status'] != 'active':
        flash('Only active bookings can be cancelled.', 'warning')
        return redirect(url_for('booking_history'))
    query_db("UPDATE bookings SET status='cancelled' WHERE id=%s",
             (booking_id,), commit=True)
    query_db("UPDATE parking_slots SET status='available' WHERE id=%s",
             (booking['slot_id'],), commit=True)
    query_db("UPDATE payments SET payment_status='refunded' WHERE booking_id=%s",
             (booking_id,), commit=True)
    log_action('Booking cancelled', 'bookings', booking_id)
    flash('Booking cancelled successfully.', 'success')
    return redirect(url_for('booking_history'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    uid = session['user_id']
    if request.method == 'POST':
        full_name  = request.form.get('full_name', '').strip()
        phone      = request.form.get('phone', '').strip()
        vehicle_no = request.form.get('vehicle_no', '').strip().upper()
        query_db(
            "UPDATE users SET full_name=%s, phone=%s, vehicle_no=%s WHERE id=%s",
            (full_name, phone, vehicle_no, uid), commit=True)
        session['user_name'] = full_name
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('profile'))
    user = query_db("SELECT * FROM users WHERE id=%s", (uid,), fetchone=True)
    booking_stats = query_db(
        "SELECT status, COUNT(*) as c FROM bookings WHERE user_id=%s GROUP BY status", (uid,))
    return render_template('profile.html', user=user,
                           stats={r['status']: r['c'] for r in booking_stats})

# ── API: Check slot availability ─────────────────────────────────────────────
@app.route('/api/check-availability', methods=['POST'])
@login_required
def api_check_availability():
    data     = request.get_json()
    slot_id  = data.get('slot_id')
    bdate    = data.get('booking_date')
    start    = data.get('start_time')
    end      = data.get('end_time')
    if check_overlap(slot_id, bdate, start, end):
        return jsonify({'available': False, 'message': 'Slot is already booked for this time.'})
    hours, cost = calculate_cost(slot_id, start, end)
    return jsonify({'available': True, 'hours': hours, 'cost': cost})

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()
        admin = query_db("SELECT * FROM admins WHERE username=%s",
                         (username,), fetchone=True)
        if admin and check_password_hash(admin['password'], password):
            session['admin_id']   = admin['id']
            session['admin_name'] = admin['username']
            log_action('Admin login')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin credentials.', 'danger')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    log_action('Admin logout')
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    slots_stat = query_db(
        "SELECT status, COUNT(*) as c FROM parking_slots GROUP BY status")
    slots_dict = {r['status']: r['c'] for r in slots_stat}

    booking_stat = query_db(
        "SELECT status, COUNT(*) as c FROM bookings GROUP BY status")
    booking_dict = {r['status']: r['c'] for r in booking_stat}

    total_revenue = query_db(
        "SELECT COALESCE(SUM(total_cost),0) as rev FROM bookings WHERE status!='cancelled'",
        fetchone=True)['rev']

    recent_bookings = query_db(
        "SELECT b.*, s.slot_number, u.full_name FROM bookings b "
        "JOIN parking_slots s ON b.slot_id=s.id "
        "JOIN users u ON b.user_id=u.id "
        "ORDER BY b.created_at DESC LIMIT 8")

    total_users = query_db("SELECT COUNT(*) as c FROM users", fetchone=True)['c']

    # Zone-wise occupancy
    zones = query_db(
        "SELECT area, "
        "COUNT(*) as total, "
        "SUM(status='available') as avail, "
        "SUM(status='occupied') as occ, "
        "SUM(status='reserved') as res "
        "FROM parking_slots GROUP BY area")

    return render_template('admin_dashboard.html',
                           slots=slots_dict, bookings=booking_dict,
                           total_revenue=total_revenue,
                           recent_bookings=recent_bookings,
                           total_users=total_users,
                           zones=zones)


@app.route('/admin/slots', methods=['GET', 'POST'])
@admin_required
def manage_slots():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            slot_number = request.form.get('slot_number', '').strip().upper()
            slot_type   = request.form.get('slot_type', 'car')
            area        = request.form.get('area', '').strip()
            floor       = request.form.get('floor', 'Ground').strip()
            hourly_rate = request.form.get('hourly_rate', 20.00)
            existing = query_db("SELECT id FROM parking_slots WHERE slot_number=%s",
                                (slot_number,), fetchone=True)
            if existing:
                flash(f'Slot {slot_number} already exists.', 'danger')
            else:
                query_db(
                    "INSERT INTO parking_slots (slot_number,slot_type,area,floor,hourly_rate) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (slot_number, slot_type, area, floor, hourly_rate), commit=True)
                flash(f'Slot {slot_number} added.', 'success')

        elif action == 'edit':
            sid         = request.form.get('slot_id')
            slot_type   = request.form.get('slot_type', 'car')
            area        = request.form.get('area', '').strip()
            floor       = request.form.get('floor', 'Ground').strip()
            status      = request.form.get('status', 'available')
            hourly_rate = request.form.get('hourly_rate', 20.00)
            query_db(
                "UPDATE parking_slots SET slot_type=%s,area=%s,floor=%s,status=%s,hourly_rate=%s "
                "WHERE id=%s",
                (slot_type, area, floor, status, hourly_rate, sid), commit=True)
            flash('Slot updated.', 'success')

        elif action == 'delete':
            sid = request.form.get('slot_id')
            query_db("DELETE FROM parking_slots WHERE id=%s", (sid,), commit=True)
            flash('Slot deleted.', 'success')

        return redirect(url_for('manage_slots'))

    all_slots = query_db("SELECT * FROM parking_slots ORDER BY area, slot_number")
    return render_template('manage_slots.html', slots=all_slots)


@app.route('/admin/bookings', methods=['GET', 'POST'])
@admin_required
def manage_bookings():
    if request.method == 'POST':
        action     = request.form.get('action')
        booking_id = request.form.get('booking_id')
        if action == 'cancel':
            b = query_db("SELECT * FROM bookings WHERE id=%s", (booking_id,), fetchone=True)
            if b and b['status'] == 'active':
                query_db("UPDATE bookings SET status='cancelled' WHERE id=%s",
                         (booking_id,), commit=True)
                query_db("UPDATE parking_slots SET status='available' WHERE id=%s",
                         (b['slot_id'],), commit=True)
                flash('Booking cancelled.', 'success')
        elif action == 'complete':
            b = query_db("SELECT * FROM bookings WHERE id=%s", (booking_id,), fetchone=True)
            if b and b['status'] == 'active':
                query_db("UPDATE bookings SET status='completed' WHERE id=%s",
                         (booking_id,), commit=True)
                query_db("UPDATE parking_slots SET status='available' WHERE id=%s",
                         (b['slot_id'],), commit=True)
                query_db("UPDATE payments SET payment_status='paid',paid_at=NOW() WHERE booking_id=%s",
                         (booking_id,), commit=True)
                flash('Booking marked as completed.', 'success')
        return redirect(url_for('manage_bookings'))

    search     = request.args.get('q', '')
    status_f   = request.args.get('status', '')
    date_f     = request.args.get('date', '')
    sql = ("SELECT b.*, s.slot_number, s.area, u.full_name, u.email "
           "FROM bookings b JOIN parking_slots s ON b.slot_id=s.id "
           "JOIN users u ON b.user_id=u.id WHERE 1=1")
    params = []
    if search:
        sql += " AND (b.booking_ref LIKE %s OR u.full_name LIKE %s OR b.vehicle_no LIKE %s)"
        params.extend([f'%{search}%']*3)
    if status_f:
        sql += " AND b.status=%s"; params.append(status_f)
    if date_f:
        sql += " AND b.booking_date=%s"; params.append(date_f)
    sql += " ORDER BY b.created_at DESC LIMIT 100"
    bookings = query_db(sql, params)
    return render_template('manage_bookings.html', bookings=bookings,
                           search=search, status_f=status_f, date_f=date_f)


@app.route('/admin/users')
@admin_required
def manage_users():
    search = request.args.get('q', '')
    sql = "SELECT u.*, COUNT(b.id) as total_bookings FROM users u LEFT JOIN bookings b ON u.id=b.user_id"
    params = []
    if search:
        sql += " WHERE u.full_name LIKE %s OR u.email LIKE %s"
        params.extend([f'%{search}%']*2)
    sql += " GROUP BY u.id ORDER BY u.created_at DESC"
    users = query_db(sql, params)
    return render_template('manage_users.html', users=users, search=search)


@app.route('/admin/users/toggle/<int:uid>', methods=['POST'])
@admin_required
def toggle_user(uid):
    user = query_db("SELECT is_active FROM users WHERE id=%s", (uid,), fetchone=True)
    if user:
        new_status = 0 if user['is_active'] else 1
        query_db("UPDATE users SET is_active=%s WHERE id=%s",
                 (new_status, uid), commit=True)
        flash(f'User {"activated" if new_status else "deactivated"}.', 'success')
    return redirect(url_for('manage_users'))

# ── Error Handlers ───────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# ── Admin seeder ─────────────────────────────────────────────────────────────
@app.route('/setup-admin')
def setup_admin():
    """One-time route to create default admin. Remove after first use."""
    try:
        # Always delete old record first to avoid stale/broken hashes
        query_db("DELETE FROM admins", commit=True)
        # Generate fresh correct hash
        hashed = generate_password_hash('admin123', method='pbkdf2:sha256')
        query_db(
            "INSERT INTO admins (username, email, password) VALUES (%s, %s, %s)",
            ('admin', 'admin@parkingsystem.com', hashed), commit=True)
        # Verify it was saved correctly
        admin = query_db("SELECT * FROM admins WHERE username='admin'", fetchone=True)
        if admin and check_password_hash(admin['password'], 'admin123'):
            return "SUCCESS! Admin created and verified. username=admin | password=admin123 — Now go to /admin/login"
        return "ERROR: Admin inserted but password verification failed. Contact support."
    except Exception as e:
        return f"Error: {e}"

if __name__ == '__main__':
    app.run(debug=True)

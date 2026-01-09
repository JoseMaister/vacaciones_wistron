from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_file, abort
from datetime import datetime, timedelta
import psycopg2
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import io
import re
# --- NEW IMPORTS FOR EMAIL ---
from flask_mail import Mail, Message
from threading import Thread
# -----------------------------

# ============================================================
# CONFIGURATION
# ============================================================

# Database Connection String
DSN = "postgresql://postgres:1234@localhost:5432/vacaciones_local?sslmode=disable"

def get_conn():
    return psycopg2.connect(DSN)

app = Flask(__name__)
app.secret_key = 'my_super_secret_key'

# --- EMAIL CONFIGURATION ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'noreplyvacacioneswistron@gmail.com'  
app.config['MAIL_PASSWORD'] = 'ztmu nlqe zccb zoka'        
app.config['MAIL_DEFAULT_SENDER'] = 'noreplyvacacioneswistron@gmail.com' 

mail = Mail(app)

# User Roles Constants
ROLE_TECH   = 1
ROLE_ENG    = 2
ROLE_SUP    = 3
ROLE_ADMIN  = 4
ROLE_CLERK  = 5
ROLE_MASTER = 6 

# ============================================================
# HELPER FUNCTIONS (EMAIL)
# ============================================================

def send_async_email(app, msg):
    """Sends email in a background thread to prevent blocking the UI."""
    with app.app_context():
        try:
            mail.send(msg)
            print("Email sent successfully!")
        except Exception as e:
            print(f"Failed to send email: {e}")

def send_email_notification(subject, recipients, body):
    """Prepares the email and starts the background thread."""
    if not recipients:
        return
    msg = Message(subject, recipients=recipients, body=body)
    Thread(target=send_async_email, args=(app, msg)).start()

# ============================================================
# DECORATORS
# ============================================================

def role_required(*roles):
    """
    Decorator to restrict access to specific roles.
    Redirects to login if not authenticated, or returns 403 if unauthorized.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                flash("You must log in first.")
                return redirect(url_for('login'))
            if session.get('role_id') not in roles:
                abort(403) # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ============================================================
# AUTHENTICATION & SESSION ROUTES
# ============================================================

@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    role = session.get('role_id')
    # Technicians go to their submission log, others to the management view
    if role == ROLE_TECH:
        return redirect(url_for('index'))
    return redirect(url_for('show_requests'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        employee_number = request.form.get('username')
        password = request.form.get('password')

        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT id, name, password, role_id, shift
                FROM employees
                WHERE employee_number = %s
            """, (employee_number,))
            user = cur.fetchone()

            # Verify password hash
            if user and check_password_hash(user[2], password):
                session['logged_in'] = True
                session['username'] = user[1]
                session['employee_id'] = user[0]
                session['role_id'] = user[3]
                session['employee_number'] = employee_number
                session['shift'] = user[4]

                if user[3] == ROLE_TECH:
                    return redirect(url_for('index'))
                return redirect(url_for('show_requests'))

            flash("Invalid employee number or password.")
            return redirect(url_for('login'))

        except Exception as e:
            print("Login error:", e)
            flash("Error while logging in.")
            return redirect(url_for('login'))
        finally:
            cur.close()
            conn.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for('login'))

@app.route('/forgot-password')
def forgot_password():
    return render_template('password.html')

# ============================================================
# PASSWORD MANAGEMENT
# ============================================================

@app.route('/change-password')
def change_password_view():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('change_password.html')

@app.route('/change-password', methods=['POST'])
def change_password_submit():
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403

    data = request.get_json()
    current = data.get('current_password')
    new = data.get('new_password')
    confirm = data.get('confirm_password')

    if not current or not new or not confirm:
        return jsonify({"error": "All fields are required"}), 400

    if new != confirm:
        return jsonify({"error": "Passwords do not match"}), 400

    if new == current:
        return jsonify({"error": "New password must be different"}), 400

    user_id = session.get('employee_id')
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("SELECT password FROM employees WHERE id = %s", (user_id,))
        row = cur.fetchone()

        # Verify current password matches hash
        if not row or not check_password_hash(row[0], current):
            return jsonify({"error": "Current password is incorrect"}), 403

        # Hash new password before saving
        new_hashed = generate_password_hash(new)

        cur.execute("UPDATE employees SET password = %s WHERE id = %s", (new_hashed, user_id))
        conn.commit()
        return jsonify({"message": "Password updated successfully"}), 200

    except Exception as e:
        conn.rollback()
        print("Password update error:", e)
        return jsonify({"error": "Internal error"}), 500
    finally:
        cur.close()
        conn.close()

# ============================================================
# DASHBOARD VIEWS (HTML)
# ============================================================

@app.route('/index')
@role_required(ROLE_TECH)
def index():
    return render_template(
        'index.html',
        username=session.get('username'),
        employee_number=session.get('employee_number'),
        shift=session.get('shift')
    )

@app.route('/view-requests')
def show_requests():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('requests.html', shift=session.get('shift'))

@app.route('/calendar')
@role_required(ROLE_ENG, ROLE_SUP, ROLE_ADMIN, ROLE_CLERK, ROLE_MASTER)
def calendar_view():
    # Pass the current user's shift to the template for filtering/display
    return render_template('calendar.html', shift=session.get('shift'))

@app.route('/add-user', methods=['GET'])
@role_required(ROLE_ENG, ROLE_SUP, ROLE_MASTER)
def add_user_view():
    # Retrieve current user credentials from session
    current_role = session.get('role_id')
    current_shift = session.get('shift')

    # Default initialization
    allowed_roles = []
    can_choose_shift = False
    default_shift = 1 

    # Logic to populate dropdowns based on hierarchy
    if current_role == ROLE_ENG:
        # Engineer: Can only create Technicians for their specific shift
        allowed_roles = [{"id": ROLE_TECH, "name": "Technician"}]
        can_choose_shift = False
        default_shift = current_shift  # Lock to current user's shift

    elif current_role == ROLE_SUP:
        # Supervisor: Can create Engineers (allows shift selection)
        allowed_roles = [{"id": ROLE_ENG, "name": "Engineer"}]
        can_choose_shift = True
        
    elif current_role == ROLE_MASTER:
        # Master: Can create any role and choose any shift
        allowed_roles = [
            {"id": ROLE_TECH,  "name": "Technician"},
            {"id": ROLE_ENG,   "name": "Engineer"},
            {"id": ROLE_SUP,   "name": "Supervisor"},
            {"id": ROLE_ADMIN, "name": "Area Manager (Admin)"},
            {"id": ROLE_CLERK, "name": "Clerk (HR)"}
        ]
        can_choose_shift = True

    return render_template(
        'add_user.html',
        allowed_roles=allowed_roles,
        can_choose_shift=can_choose_shift,
        default_shift=default_shift
    )

# ============================================================
# API ENDPOINTS (DATA FETCHING)
# ============================================================

@app.route('/requests', methods=['GET'])
def get_vacation_requests():
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403

    role = session.get('role_id')
    emp_id = session.get('employee_id')
    eng_shift = session.get('shift')

    conn = get_conn()
    cur = conn.cursor()

    try:
        # 1. Technician: Sees only their own requests
        if role == ROLE_TECH:
            cur.execute("""
                SELECT e.employee_number, e.name, vr.date_start, vr.date_end,
                       vr.status, vr.submitted_at, vr.clerk_comment, vr.tech_comment, vr.id
                FROM vacation_requests vr
                JOIN employees e ON vr.employee_id = e.id
                WHERE vr.employee_id = %s
                  AND vr.is_hidden IS FALSE
                ORDER BY vr.submitted_at DESC
            """, (emp_id,))

        # 2. Engineer: Sees only 'Pending Engineer' for their shift
        elif role == ROLE_ENG:
            cur.execute("""
                SELECT e.employee_number, e.name, vr.date_start, vr.date_end,
                       vr.status, vr.submitted_at, vr.clerk_comment, vr.tech_comment, vr.id
                FROM vacation_requests vr
                JOIN employees e ON vr.employee_id = e.id
                WHERE vr.status = 'Pending Engineer'
                  AND e.shift = %s
                  AND vr.is_hidden IS FALSE
                ORDER BY vr.submitted_at DESC
            """, (eng_shift,))

        # 3. Supervisor, Clerk and MASTER: See ALL active history
        elif role in [ROLE_SUP, ROLE_CLERK, ROLE_MASTER]:
            cur.execute("""
                SELECT e.employee_number, e.name, vr.date_start, vr.date_end,
                       vr.status, vr.submitted_at, vr.clerk_comment, vr.tech_comment, vr.id
                FROM vacation_requests vr
                JOIN employees e ON vr.employee_id = e.id
                WHERE vr.is_hidden IS FALSE
                ORDER BY vr.submitted_at DESC
            """)

        # 4. Admin (Area Manager): Sees 'Pending Admin'
        elif role == ROLE_ADMIN:
            cur.execute("""
                SELECT e.employee_number, e.name, vr.date_start, vr.date_end,
                       vr.status, vr.submitted_at, vr.clerk_comment, vr.tech_comment, vr.id
                FROM vacation_requests vr
                JOIN employees e ON vr.employee_id = e.id
                WHERE vr.status = 'Pending Admin'
                  AND vr.is_hidden IS FALSE
                ORDER BY vr.submitted_at DESC
            """)
        else:
            return jsonify([])

        rows = cur.fetchall()
        results = []
        for r in rows:
            results.append({
                "employee_number": r[0],
                "employee_name": r[1],
                "date_start": r[2].strftime("%Y-%m-%d"),
                "date_end": r[3].strftime("%Y-%m-%d"),
                "status": r[4],
                "submitted_at": r[5].strftime("%Y-%m-%d %H:%M:%S"),
                "comment": r[6],
                "tech_comment": r[7],
                "id": r[8]
            })

        return jsonify(results)

    except Exception as e:
        print("Data fetch error:", e)
        return jsonify({"error": "Internal error"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/calendar-data', methods=['GET'])
@role_required(ROLE_ENG, ROLE_SUP, ROLE_ADMIN, ROLE_CLERK, ROLE_MASTER)
def calendar_data():
    role = session.get('role_id')
    user_shift = session.get('shift')
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    today = datetime.today().date()
    if not year or not month:
        year, month = today.year, today.month

    # Calculate start and end dates for the query range
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Determine relevant employees based on hierarchy
        if role == ROLE_ENG:
            # Engineers only see Technicians in their specific shift
            cur.execute("SELECT id FROM employees WHERE role_id = %s AND shift = %s", (ROLE_TECH, user_shift))
        else:
            # Master, Supervisor, Admin, and Clerk see all Technicians
            cur.execute("SELECT id FROM employees WHERE role_id = %s", (ROLE_TECH,))

        tech_ids = [r[0] for r in cur.fetchall()]
        if not tech_ids:
            return jsonify({"year": year, "month": month, "items": []})

        # Fetch Approved or Pending requests for calendar display
        # Filters out hidden (deleted) requests ensuring the calendar remains clean
        cur.execute("""
            SELECT vr.employee_id, e.name, vr.date_start, vr.date_end, vr.status
            FROM vacation_requests vr
            JOIN employees e ON vr.employee_id = e.id
            WHERE vr.employee_id = ANY(%s)
              AND (vr.status = 'Approved' OR vr.status LIKE 'Pending%%')
              AND vr.is_hidden IS FALSE
              AND vr.date_end >= %s
              AND vr.date_start <= %s
            ORDER BY e.name ASC, vr.date_start ASC;
        """, (tech_ids, start_date, end_date))

        items = []
        for emp_id, emp_name, dstart, dend, status in cur.fetchall():
            items.append({
                "employee_id": emp_id,
                "employee_name": emp_name,
                "date_start": dstart.strftime("%Y-%m-%d"),
                "date_end": dend.strftime("%Y-%m-%d"),
                "status": status
            })

        return jsonify({"year": year, "month": month, "items": items})

    except Exception as e:
        print("Calendar fetch error:", e)
        return jsonify({"error": "Internal error"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/export-excel')
def export_excel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    role = session.get('role_id')
    emp_id = session.get('employee_id')
    eng_shift = session.get('shift')

    # Security: Technicians cannot export data
    if role == ROLE_TECH:
        return "Permission denied: Technicians cannot export data.", 403

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Base Query:
        # 1. Removed 'WHERE vr.is_hidden IS FALSE' to include deleted/hidden requests.
        # 2. Added 'e.shift' to the SELECT columns for better reporting.
        base_query = """
            SELECT e.employee_number, e.name, e.shift, vr.date_start, vr.date_end,
                   vr.status, vr.submitted_at, vr.clerk_comment, vr.tech_comment
            FROM vacation_requests vr
            JOIN employees e ON vr.employee_id = e.id
        """
        
        query, params = "", ()

        if role == ROLE_ENG:
            # Engineer: Exports ALL history (active, hidden, rejected, approved), 
            # but strictly filtered by their own SHIFT.
            query = base_query + " WHERE e.shift = %s ORDER BY vr.submitted_at DESC"
            params = (eng_shift,)
            
        elif role in [ROLE_SUP, ROLE_CLERK, ROLE_MASTER, ROLE_ADMIN]:
            # Master/Sup/Admin/Clerk: Exports EVERYTHING (All shifts, all statuses, history included).
            query = base_query + " ORDER BY vr.submitted_at DESC"
            params = ()
            
        else:
            return "Role not allowed", 403

        cur.execute(query, params)
        rows = cur.fetchall()

        # Define headers matching the SELECT order
        columns = ["Employee ID", "Name", "Shift", "Start Date", "End Date", "Status", "Submitted At", "HR Comment", "Tech Comment"]
        df = pd.DataFrame(rows, columns=columns)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Full_History_Report')
        
        output.seek(0)
        # Added timestamp to filename
        filename = f"Vacation_History_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

        return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        print("Excel export error:", e)
        return "Error generating Excel file", 500
    finally:
        cur.close()
        conn.close()

# ============================================================
# ACTION ENDPOINTS (LOGIC)
# ============================================================

@app.route('/submit', methods=['POST'])
@role_required(ROLE_TECH)
def submit_request():
    data = request.get_json(silent=True) or {}
    employee_id = session.get('employee_id')
    
    date_start_str = (data.get('date_start') or "").strip()
    date_end_str   = (data.get('date_end') or "").strip()
    tech_comment   = (data.get('comment') or "").strip()

    if not date_start_str:
        return jsonify({"error": "Missing start date"}), 400
    if not date_end_str:
        date_end_str = date_start_str

    try:
        date_start = datetime.strptime(date_start_str, "%Y-%m-%d").date()
        date_end   = datetime.strptime(date_end_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    if date_end < date_start:
        return jsonify({"error": "End date cannot be before start date"}), 400

    # Minimum 7 days notice
    if date_start < (datetime.today().date() + timedelta(days=7)):
        return jsonify({"error": "Requests must be submitted at least 7 days in advance"}), 400

    # Validate weekends
    d = date_start
    while d <= date_end:
        if d.weekday() >= 5: # 5=Sat, 6=Sun
            return jsonify({"error": "Weekend days (Sat/Sun) are not allowed"}), 400
        d += timedelta(days=1)

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Check for Overlaps (Active requests)
        cur.execute("""
            SELECT COUNT(*) FROM public.vacation_requests
            WHERE employee_id = %s
              AND (status = 'Approved' OR status LIKE 'Pending%%')
              AND is_hidden IS FALSE
              AND date_start <= %s AND date_end >= %s
        """, (employee_id, date_end, date_start))

        if cur.fetchone()[0] > 0:
            return jsonify({"error": "Overlapping request detected."}), 400

        # Insert new request
        cur.execute("""
            INSERT INTO public.vacation_requests
                (employee_id, date_start, date_end, status, submitted_at, tech_comment)
            VALUES (%s, %s, %s, 'Pending Engineer', NOW(), %s)
            RETURNING id
        """, (employee_id, date_start, date_end, tech_comment))

        req_id = cur.fetchone()[0]
        conn.commit()

        # --- EMAIL NOTIFICATION LOGIC (Notify Engineers) ---
        try:
            # 1. Get Technician's info including Employee ID
            cur.execute("SELECT name, shift, employee_number FROM employees WHERE id = %s", (employee_id,))
            tech_data = cur.fetchone()
            tech_name = tech_data[0]
            tech_shift = tech_data[1]
            tech_emp_num = tech_data[2] # Clock Number

            # 2. Find Engineers matching that shift who have an email set
            cur.execute("""
                SELECT email FROM employees 
                WHERE role_id = %s AND shift = %s AND email IS NOT NULL
            """, (ROLE_ENG, tech_shift))
            
            eng_emails = [r[0] for r in cur.fetchall()]

            if eng_emails:
                subject = f"Vacation Request: {tech_name}"
                body = f"""
                New Vacation Request
                --------------------
                Employee: {tech_name}
                ID: {tech_emp_num}
                Shift: {tech_shift}
                
                Dates: {date_start} to {date_end}
                Comment: {tech_comment}
                
                Please log in to review.
                """
                send_email_notification(subject, eng_emails, body)
                print(f"Triggered email to engineers: {eng_emails}")
        except Exception as e:
            print(f"Email trigger error: {e}")
        # ---------------------------------------------------

        return jsonify({"message": "Request submitted", "id": req_id}), 200

    except Exception as e:
        conn.rollback()
        print("Submit error:", e)
        return jsonify({"error": "Internal error"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/add-user', methods=['POST'])
@role_required(ROLE_ENG, ROLE_SUP, ROLE_MASTER)
def add_user_submit():
    role = session.get('role_id')
    session_shift = session.get('shift')
    data = request.get_json(silent=True) or {}

    employee_number = (data.get('employee_number') or '').strip()
    name = (data.get('name') or '').strip()
    password = (data.get('password') or '').strip()
    
    # Master sends target role explicitly
    target_role_id = data.get('role_id') 
    shift = data.get('shift')

    final_role_id = None
    
    # Determine the role of the new user based on Creator
    if role == ROLE_ENG:
        final_role_id = ROLE_TECH
        shift = session_shift # Engineer forces their shift
    elif role == ROLE_SUP:
        final_role_id = ROLE_ENG
        try: shift = int(shift)
        except: shift = None
    elif role == ROLE_MASTER:
        # Master can create anyone. We trust the ID sent from frontend, 
        # allowing creation of Techs, Engineers, Supervisors, Admins, Clerks and Masters.
        valid_master_creates = [ROLE_TECH, ROLE_ENG, ROLE_SUP, ROLE_ADMIN, ROLE_CLERK, ROLE_MASTER]
        
        try: target_role_id = int(target_role_id)
        except: pass

        if target_role_id in valid_master_creates:
            final_role_id = target_role_id
        else:
            return jsonify({"error": "Invalid role selection"}), 400
    
    if not final_role_id:
        return jsonify({"error": "Permission denied"}), 403

    if not employee_number or not name or not password:
        return jsonify({"error": "Missing fields"}), 400

    if not re.fullmatch(r"(ML\d{8}|Z\d{8})", employee_number):
        return jsonify({"error": "Invalid ID format. Use ML######## or Z########"}), 400

    if shift not in (1, 2, 3):
        return jsonify({"error": "Invalid shift"}), 400

    # Hash the password before storage
    hashed_password = generate_password_hash(password)

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Check duplicates
        cur.execute("SELECT 1 FROM employees WHERE employee_number = %s", (employee_number,))
        if cur.fetchone():
            return jsonify({"error": "Employee number already exists"}), 400

        cur.execute("""
            INSERT INTO employees (employee_number, name, password, role_id, shift)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (employee_number, name, hashed_password, final_role_id, shift))

        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"message": "User created", "id": new_id}), 200

    except Exception as e:
        conn.rollback()
        print("Create user error:", e)
        return jsonify({"error": "Internal error"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/approve/<int:req_id>', methods=['POST'])
def approve_request(req_id):
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403

    role = session.get('role_id')
    user_id = session.get('employee_id')
    eng_shift = session.get('shift')
    
    # Retrieve target status if sent (Master only)
    data = request.get_json(silent=True) or {}
    target_status = data.get('target_status') 

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("SELECT status FROM vacation_requests WHERE id = %s", (req_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Request not found"}), 404
        current_status = row[0]

        # --- MASTER LOGIC (JUMP TO SPECIFIC STAGE) ---
        if role == ROLE_MASTER:
            valid_targets = ['Pending Supervisor', 'Pending Admin', 'Pending Clerk', 'Approved']
            
            if target_status and target_status in valid_targets:
                cur.execute("""
                    UPDATE vacation_requests 
                    SET status = %s,
                        clerk_comment = CASE WHEN %s = 'Approved' THEN 'Approved directly by Master' ELSE clerk_comment END
                    WHERE id = %s
                """, (target_status, target_status, req_id))

                # --- NEW EMAIL LOGIC FOR MASTER ACTION ---
                try:
                    # 1. Fetch Request Details
                    cur.execute("""
                        SELECT e.shift, e.name, vr.date_start, vr.date_end, e.employee_number, vr.tech_comment
                        FROM vacation_requests vr 
                        JOIN employees e ON vr.employee_id = e.id 
                        WHERE vr.id = %s
                    """, (req_id,))
                    
                    row_data = cur.fetchone()
                    if row_data:
                        req_shift = row_data[0]
                        req_name = row_data[1]
                        req_start = row_data[2]
                        req_end = row_data[3]
                        req_emp_num = row_data[4]
                        req_comment = row_data[5]

                        # 2. Notify Engineer (of that shift) AND Clerk
                        cur.execute("""
                            SELECT email FROM employees 
                            WHERE ((role_id = %s AND shift = %s) OR role_id = %s) 
                            AND email IS NOT NULL
                        """, (ROLE_ENG, req_shift, ROLE_CLERK))
                        
                        recipients = [r[0] for r in cur.fetchall()]

                        if recipients:
                            subject = f"Master Update: {req_name}"
                            body = f"""
                            The Master User has updated a request manually.
                            -----------------------------------------------
                            Employee: {req_name}
                            ID: {req_emp_num}
                            Shift: {req_shift}
                            
                            New Status: {target_status}
                            Dates: {req_start} to {req_end}
                            Original Comment: {req_comment}
                            """
                            send_email_notification(subject, recipients, body)
                            print(f"Master triggered email to: {recipients}")
                except Exception as e:
                    print(f"Master email error: {e}")
                # -----------------------------------------

            else:
                return jsonify({"error": "Master must select a valid target status"}), 400

        # --- STANDARD CASCADE LOGIC ---
        elif role == ROLE_ENG and current_status == "Pending Engineer":
            # Retrieve request details for validation and email
            cur.execute("""
                SELECT e.shift, e.name, vr.date_start, vr.date_end, e.employee_number, vr.tech_comment
                FROM vacation_requests vr 
                JOIN employees e ON vr.employee_id = e.id 
                WHERE vr.id = %s
            """, (req_id,))
            
            row_data = cur.fetchone()
            if not row_data:
                return jsonify({"error": "Request data missing"}), 404
                
            req_shift = row_data[0]
            req_name = row_data[1]
            req_start = row_data[2]
            req_end = row_data[3]
            req_emp_num = row_data[4] # Clock number
            req_comment = row_data[5] # Original comment

            if req_shift != eng_shift:
                return jsonify({"error": "Permission denied (different shift)"}), 403
            
            cur.execute("UPDATE vacation_requests SET status = 'Pending Supervisor', engineer_id = %s WHERE id = %s", (user_id, req_id))

            # --- EMAIL NOTIFICATION LOGIC (Notify Master & Clerk) ---
            try:
                cur.execute("""
                    SELECT email FROM employees 
                    WHERE role_id IN (%s, %s) AND email IS NOT NULL
                """, (ROLE_MASTER, ROLE_CLERK))
                
                notify_emails = [r[0] for r in cur.fetchall()]
                
                if notify_emails:
                    subject = f"Engineer Approved: {req_name}"
                    body = f"""
                    Update: Engineer has Approved Request
                    -------------------------------------
                    Employee: {req_name}
                    ID: {req_emp_num}
                    Shift: {req_shift}
                    
                    Dates: {req_start} to {req_end}
                    Comment: {req_comment}
                    
                    Current Status: Pending Supervisor
                    """
                    send_email_notification(subject, notify_emails, body)
                    print(f"Triggered email to Master/Clerk: {notify_emails}")
            except Exception as e:
                print(f"Email trigger error: {e}")
            # --------------------------------------------------------

        elif role == ROLE_SUP and current_status == "Pending Supervisor":
            cur.execute("UPDATE vacation_requests SET status = 'Pending Admin', supervisor_id = %s WHERE id = %s", (user_id, req_id))

        elif role == ROLE_ADMIN and current_status == "Pending Admin":
            cur.execute("UPDATE vacation_requests SET status = 'Pending Clerk', admin_id = %s WHERE id = %s", (user_id, req_id))

        elif role == ROLE_CLERK and current_status == "Pending Clerk":
            cur.execute("UPDATE vacation_requests SET status = 'Approved', clerk_id = %s WHERE id = %s", (user_id, req_id))

        else:
            return jsonify({"error": "Permission denied or invalid status"}), 403

        conn.commit()
        return jsonify({"message": "Request processed successfully"}), 200

    except Exception as e:
        conn.rollback()
        print("Approval error:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/reject/<int:req_id>', methods=['POST'])
def reject_request(req_id):
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403

    data = request.get_json(silent=True) or {}
    comment = (data.get('comment') or "").strip()
    
    role = session.get('role_id')
    user_shift = session.get('shift')

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT vr.status, e.shift
            FROM vacation_requests vr
            JOIN employees e ON vr.employee_id = e.id
            WHERE vr.id = %s
        """, (req_id,))
        row = cur.fetchone()
        
        if not row:
            return jsonify({"error": "Request not found"}), 404

        status, req_shift = row
        allowed = False

        # Authorization Check
        if role == ROLE_ENG and status == 'Pending Engineer':
            if req_shift == user_shift: allowed = True
        elif role == ROLE_SUP and status == 'Pending Supervisor':
            allowed = True
        elif role == ROLE_ADMIN and status == 'Pending Admin':
            allowed = True
        elif role == ROLE_CLERK and status == 'Pending Clerk':
            allowed = True
        elif role == ROLE_MASTER:
            allowed = True  # Master can reject at any stage

        if not allowed:
            return jsonify({"error": "Permission denied."}), 403

        cur.execute("""
            UPDATE vacation_requests
            SET status = 'Rejected', clerk_comment = %s, is_hidden = FALSE
            WHERE id = %s
        """, (comment, req_id))

        conn.commit()
        return jsonify({"message": "Request rejected"}), 200

    except Exception as e:
        conn.rollback()
        print("Reject error:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/delete/<int:req_id>', methods=['DELETE'])
def delete_request(req_id):
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403

    role = session.get('role_id')
    user_id = session.get('employee_id')

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Soft Delete Logic: Set is_hidden = TRUE
        if role == ROLE_TECH:
            # Technician can only hide their own requests
            cur.execute("""
                UPDATE vacation_requests SET is_hidden = TRUE
                WHERE id = %s AND employee_id = %s
                RETURNING id
            """, (req_id, user_id))
        else:
            # Admins/Master can hide any request (History management)
            cur.execute("""
                UPDATE vacation_requests SET is_hidden = TRUE 
                WHERE id = %s RETURNING id
            """, (req_id,))

        updated = cur.fetchone()
        conn.commit()

        if not updated:
            return jsonify({"error": "Not found or permission denied"}), 404

        return jsonify({"message": "Request removed from view"}), 200

    except Exception as e:
        conn.rollback()
        print("Delete error:", e)
        return jsonify({"error": "Internal error"}), 500
    finally:
        cur.close()
        conn.close()
# ============================================================
# ADMINISTRATIVE PASSWORD RESET (ENGINEER & MASTER)
# ============================================================

@app.route('/manage-passwords')
@role_required(ROLE_ENG, ROLE_MASTER)
def manage_passwords_view():
    return render_template('manage_passwords.html', shift=session.get('shift'))

@app.route('/api/users-list', methods=['GET'])
@role_required(ROLE_ENG, ROLE_MASTER)
def get_users_for_reset():
    role = session.get('role_id')
    user_shift = session.get('shift')
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Visibility Logic
        if role == ROLE_ENG:
            # Engineer: Sees only Technicians from THEIR shift
            cur.execute("""
                SELECT id, employee_number, name, role_id, shift 
                FROM employees 
                WHERE role_id = %s AND shift = %s
                ORDER BY name ASC
            """, (ROLE_TECH, user_shift))
            
        elif role == ROLE_MASTER:
            # Master: Sees EVERYONE
            cur.execute("""
                SELECT id, employee_number, name, role_id, shift 
                FROM employees 
                ORDER BY role_id DESC, name ASC
            """)
            
        rows = cur.fetchall()
        users = []
        
        # Role mapping to display friendly names in the table
        role_map = {1:"Technician", 2:"Engineer", 3:"Supervisor", 4:"Admin", 5:"Clerk", 6:"Master"}
        
        for r in rows:
            users.append({
                "id": r[0],
                "employee_number": r[1],
                "name": r[2],
                "role_name": role_map.get(r[3], "Unknown"),
                "shift": r[4]
            })
            
        return jsonify(users)
        
    except Exception as e:
        print("Fetch users error:", e)
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route('/admin-reset-password', methods=['POST'])
@role_required(ROLE_ENG, ROLE_MASTER)
def admin_reset_password():
    requester_role = session.get('role_id')
    requester_shift = session.get('shift')
    
    data = request.get_json(silent=True) or {}
    target_id = data.get('target_id')
    new_password = data.get('new_password')
    
    if not target_id or not new_password:
        return jsonify({"error": "Missing data"}), 400
        
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Validate permissions before changing anything
        cur.execute("SELECT role_id, shift FROM employees WHERE id = %s", (target_id,))
        target = cur.fetchone()
        
        if not target:
            return jsonify({"error": "User not found"}), 404
            
        target_role, target_shift = target
        
        allowed = False
        
        # Business Rules
        if requester_role == ROLE_MASTER:
            allowed = True # Master has full access
            
        elif requester_role == ROLE_ENG:
            # Engineer can only reset Technicians from THEIR shift
            if target_role == ROLE_TECH and target_shift == requester_shift:
                allowed = True
                
        if not allowed:
            return jsonify({"error": "Permission denied: You cannot reset this user."}), 403
            
        # All good, proceed with the change
        hashed = generate_password_hash(new_password)
        cur.execute("UPDATE employees SET password = %s WHERE id = %s", (hashed, target_id))
        conn.commit()
        
        return jsonify({"message": "Password reset successfully"}), 200
        
    except Exception as e:
        conn.rollback()
        print("Admin reset error:", e)
        return jsonify({"error": "Internal error"}), 500
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(host="0.0.0.0", debug=True, port=6169)
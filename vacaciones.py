from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from datetime import datetime, timedelta
import psycopg2
from functools import wraps
from flask import abort

# DSN for your local Postgres
DSN = "postgresql://postgres:1234@localhost:5432/vacaciones_local?sslmode=disable"

def get_conn():
    return psycopg2.connect(DSN)

app = Flask(__name__)
app.secret_key = 'my_super_secret_key'


# ============================================================
# DECORATORS
# ============================================================
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                flash("You must log in first.")
                return redirect(url_for('login'))
            
            if session.get('role_id') not in roles:
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================================
# HOME
# ============================================================
@app.route('/')
def home():
    if session.get('logged_in'):
        return redirect(url_for('show_requests'))
    return redirect(url_for('login'))

@app.route('/index')
def index():
    if not session.get('logged_in'):
        flash("You must log in first.")
        return redirect(url_for('login'))

    return render_template(
        'index.html',
        username=session.get('username'),
        employee_number=session.get('employee_number')
    )


# ============================================================
# LOGIN
# ============================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        numero_reloj = request.form.get('username')
        password = request.form.get('password')

        conn = get_conn()
        cur = conn.cursor()

        try:
            # Fetch user by employee number
            cur.execute("""
                SELECT id, nombre, passwrd, role_id 
                FROM example_employees 
                WHERE numero_reloj = %s
            """, (numero_reloj,))
            user = cur.fetchone()

            # Password validation
            if user and user[2] == password:
                session['logged_in'] = True
                session['username'] = user[1]
                session['employee_id'] = user[0]
                session['role_id'] = user[3]
                session['employee_number'] = numero_reloj
                return redirect(url_for('show_requests'))
            else:
                flash("Invalid employee number or password.")
                return redirect(url_for('login'))

        except Exception as e:
            print(" Error during login:", e)
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
# VIEW REQUESTS (HTML)
# ============================================================
@app.route('/view-requests')
def show_requests():
    if not session.get('logged_in'):
        flash("You must log in first.")
        return redirect(url_for('login'))

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Technician (role 4) → Only their own requests
        if session.get('role_id') == 4:
            cur.execute("""
                SELECT vr.id, e.nombre, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM vacation_requests vr
                JOIN example_employees e ON vr.employee_id = e.id
                WHERE vr.employee_id = %s
                ORDER BY vr.submitted_at DESC;
            """, (session.get('employee_id'),))

        # Engineer/Admin → All requests
        else:
            cur.execute("""
                SELECT vr.id, e.nombre, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM vacation_requests vr
                JOIN example_employees e ON vr.employee_id = e.id
                ORDER BY vr.submitted_at DESC;
            """)

        requests = cur.fetchall()
        return render_template('requests.html', requests=requests)

    except Exception as e:
        print(" Error fetching vacation requests:", e)
        flash("Error fetching vacation requests.")
        return redirect(url_for('index'))
    finally:
        cur.close()
        conn.close()


# ============================================================
# GET REQUESTS (JSON API)
# ============================================================
@app.route('/requests', methods=['GET'])
def get_vacation_requests():
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Technician (role 4) → Only their requests
        if session.get('role_id') == 4:
            cur.execute("""
                SELECT vr.id, e.nombre, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM vacation_requests vr
                JOIN example_employees e ON vr.employee_id = e.id
                WHERE vr.employee_id = %s
                ORDER BY vr.submitted_at DESC;
            """, (session.get('employee_id'),))

        # Engineer/Admin → All
        else:
            cur.execute("""
                SELECT vr.id, e.nombre, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM vacation_requests vr
                JOIN example_employees e ON vr.employee_id = e.id
                ORDER BY vr.submitted_at DESC;
            """)

        rows = cur.fetchall()

        # Format JSON
        requests = [{
            "id": r[0],
            "employee_name": r[1],
            "date_start": r[2].strftime("%Y-%m-%d"),
            "date_end": r[3].strftime("%Y-%m-%d"),
            "status": r[4],
            "submitted_at": r[5].strftime("%Y-%m-%d %H:%M:%S")
        } for r in rows]

        return jsonify(requests)

    except Exception as e:
        print(" Error fetching vacation requests:", e)
        return jsonify({"error": "Error fetching vacation requests."}), 500
    finally:
        cur.close()
        conn.close()


# ============================================================
# SUBMIT NEW REQUEST
# ============================================================
@app.route('/submit', methods=['POST'])
def submit_request():
    if not session.get('logged_in'):
        return jsonify({"error": "Not logged in"}), 403

    data = request.get_json()  

    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    employee_id = session.get('employee_id')
    date_start = data.get('date_start')
    date_end = data.get('date_end')

    if not date_start or not date_end:
        return jsonify({"error": "Missing dates"}), 400

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO vacation_requests (employee_id, date_start, date_end, status, submitted_at)
            VALUES (%s, %s, %s, 'Pending', NOW())
            RETURNING id;
        """, (employee_id, date_start, date_end))

        request_id = cur.fetchone()[0]
        conn.commit()

        return jsonify({"message": "Request submitted", "id": request_id}), 200

    except Exception as e:
        conn.rollback()
        print(" Error submitting request:", e)
        return jsonify({"error": "Error submitting request"}), 500

    finally:
        cur.close()
        conn.close()


# ============================================================
# APPROVE
# ============================================================
@app.route('/approve/<int:id>', methods=['POST'])
def approve_request(id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE vacation_requests SET status='Approved' WHERE id=%s RETURNING id;", (id,))
        result = cur.fetchone()
        conn.commit()

        if not result:
            return jsonify({"error": "Request not found"}), 404

        return jsonify({"message": f"Request {id} approved."}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ============================================================
# REJECT
# ============================================================
@app.route('/reject/<int:id>', methods=['POST'])
def reject_request(id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE vacation_requests SET status='Rejected' WHERE id=%s RETURNING id;", (id,))
        result = cur.fetchone()
        conn.commit()

        if not result:
            return jsonify({"error": "Request not found"}), 404

        return jsonify({"message": f"Request {id} rejected."}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ============================================================
# DELETE
# ============================================================
@app.route('/delete/<int:id>', methods=['DELETE'])
def delete_request(id):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM vacation_requests WHERE id=%s RETURNING id;", (id,))
        deleted = cur.fetchone()
        conn.commit()

        if not deleted:
            return jsonify({"error": "Request not found"}), 404

        return jsonify({"message": f"Request {id} deleted."}), 200

    except Exception as e:
        conn.rollback()
        print("Error deleting request:", e)
        return jsonify({"error": "Error deleting vacation request."}), 500
    finally:
        cur.close()
        conn.close()


# ============================================================
# RUN SERVER
# ============================================================
if __name__ == '__main__':
    print("Starting Flask server with PostgreSQL backend...")
    app.run(host="0.0.0.0", debug=True, port=6169)

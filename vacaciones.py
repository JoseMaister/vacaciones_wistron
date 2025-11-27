from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from datetime import datetime, timedelta
import psycopg2
from functools import wraps
from flask import abort

DSN = "postgresql://guillermo:mfte@10.121.161.225:5432/swte_3rd?sslmode=disable"

def get_conn():
    return psycopg2.connect(DSN)

app = Flask(__name__)
app.secret_key = 'my_super_secret_key'  # Required for sessions and flash messages

# --- ROLE CHECK DECORATOR ---
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                flash("You must log in first.")
                return redirect(url_for('login'))
            
            user_role = session.get('role_id')
            if user_role not in roles:
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- HOME (DEFAULT) ---
@app.route('/')
def home():
    """Redirect to login if not logged in"""
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


# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        numero_reloj = request.form.get('username')
        password = request.form.get('password')

        conn = get_conn()
        cur = conn.cursor()

        try:
            cur.execute("SELECT id, nombre, passwrd, role_id FROM example_employees WHERE numero_reloj = %s", (numero_reloj,))
            user = cur.fetchone()

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
            print("⚠️ Error during login:", e)
            flash("An error occurred while trying to log in.")
            return redirect(url_for('login'))
        finally:
            cur.close()
            conn.close()

    return render_template('login.html')

# --- LOGOUT ---
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for('login'))

# --- FORGOT PASSWORD PAGE ---
@app.route('/forgot-password')
def forgot_password():
    return render_template('password.html')

# --- VIEW REQUESTS ---
@app.route('/view-requests')
def show_requests():
    """Protected route: View vacation requests from DB"""
    if not session.get('logged_in'):
        flash("You must log in to view this page.")
        return redirect(url_for('login'))

    conn = get_conn()
    cur = conn.cursor()

    try:
        if session.get('role_id') == 40:  # Technician
            cur.execute("""
                SELECT vr.id, e.name, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM vacation_requests vr
                JOIN example_employees e ON vr.employee_id = e.id
                WHERE vr.employee_id = %s
                ORDER BY vr.submitted_at DESC;
            """, (session.get('numero_reloj'),))
        else:
            cur.execute("""
                SELECT vr.id, e.name, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM vacation_requests vr
                JOIN employees e ON vr.employee_id = e.id
                ORDER BY vr.submitted_at DESC;
            """)

        requests = cur.fetchall()
        return render_template('requests.html', requests=requests)

    except Exception as e:
        print("⚠️ Error fetching vacation requests:", e)
        flash("Error fetching vacation requests.")
        return redirect(url_for('index'))
    finally:
        cur.close()
        conn.close()

# --- SUBMIT VACATION REQUEST ---
@app.route('/submit', methods=['POST'])
def submit_vacation():
    if not request.is_json:
        return jsonify({"error": "The request must be in JSON format."}), 415

    data = request.get_json()

    required_fields = ('date_start', 'date_end')
    if not all(k in data for k in required_fields):
        return jsonify({"error": "Missing required fields: date_start, date_end"}), 400

    try:
        start = datetime.strptime(data['date_start'], "%Y-%m-%d")
        end = datetime.strptime(data['date_end'], "%Y-%m-%d")

        # Validation: End date cannot be before start date
        if end < start:
            return jsonify({"error": "End date cannot be before start date."}), 400

        # Validation: Requests must be submitted at least 7 days in advance
        min_allowed_date = datetime.now() + timedelta(days=6)
        if start < min_allowed_date:
            return jsonify({
                "error": "Vacation requests must be submitted at least 7 days in advance."
            }), 400

    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    conn = get_conn()
    cur = conn.cursor()

    try:
        # Get employee ID from session (for technicians)
        employee_id = session.get('numero_reloj')

        cur.execute("""
            INSERT INTO vacation_requests (employee_id, date_start, date_end, status)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, (employee_id, start, end, 'Pending'))

        new_id = cur.fetchone()[0]
        conn.commit()

        print(f"✅ New vacation request saved (ID {new_id}) for employee ID {employee_id}")

        return jsonify({
            "message": "Vacation request submitted successfully.",
            "id": new_id
        }), 201

    except Exception as e:
        conn.rollback()
        print("⚠️ Error inserting vacation request:", e)
        return jsonify({"error": "Error saving vacation request."}), 500
    finally:
        cur.close()
        conn.close()


# --- GET ALL REQUESTS (JSON API) ---
@app.route('/requests', methods=['GET'])
def get_vacation_requests():
    conn = get_conn()
    cur = conn.cursor()
#--HERE IS THE MDF ERROR--
    try:
        if session.get('role_id') == 40:  # Technician
            cur.execute("""
                SELECT vr.id, e.name, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM example_employees vr
                JOIN example_employees e ON vr.numero_reloj = e.id
                WHERE vr.numero_reloj = %s
                ORDER BY vr.submitted_at DESC;
            """, (session.get('numero_reloj'),))
        else:
            cur.execute("""
                SELECT vr.id, e.name, vr.date_start, vr.date_end, vr.status, vr.submitted_at
                FROM vacation_requests vr
                JOIN employees e ON vr.employee_id = e.id
                ORDER BY vr.submitted_at DESC;
            """)

        rows = cur.fetchall()

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
        print("⚠️ Error fetching vacation requests:", e)
        return jsonify({"error": "Error fetching vacation requests."}), 500
    finally:
        cur.close()
        conn.close()

# --- APPROVE REQUEST ---
@app.route('/approve/<int:id>', methods=['POST'])
def approve_request(id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE vacation_requests SET status='Approved' WHERE id=%s RETURNING id;", (id,))
        updated = cur.fetchone()
        conn.commit()
        if not updated:
            return jsonify({"error": "Request not found"}), 404
        return jsonify({"message": f"Request {id} approved successfully."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# --- REJECT REQUEST ---
@app.route('/reject/<int:id>', methods=['POST'])
def reject_request(id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE vacation_requests SET status='Rejected' WHERE id=%s RETURNING id;", (id,))
        updated = cur.fetchone()
        conn.commit()
        if not updated:
            return jsonify({"error": "Request not found"}), 404
        return jsonify({"message": f"Request {id} rejected successfully."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# --- DELETE VACATION REQUEST ---
@app.route('/delete/<int:id>', methods=['DELETE'])
def delete_request(id):
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM vacation_requests WHERE id = %s RETURNING id;", (id,))
        deleted = cur.fetchone()
        conn.commit()

        if not deleted:
            return jsonify({"error": f"Request {id} not found."}), 404

        return jsonify({"message": f"Request {id} deleted successfully"}), 200

    except Exception as e:
        conn.rollback()
        print("⚠️ Error deleting vacation request:", e)
        return jsonify({"error": "Error deleting vacation request."}), 500
    finally:
        cur.close()
        conn.close()

# --- RUN APP ---
if __name__ == '__main__':
    print("🚀 Starting Flask server with PostgreSQL backend...")
    app.run(host="0.0.0.0", debug=True, port=6169)

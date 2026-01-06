# migrate_passwords.py
import psycopg2
from werkzeug.security import generate_password_hash

DSN = "postgresql://postgres:1234@localhost:5432/vacaciones_local?sslmode=disable"

def migrate():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    print("Fetching users...")
    cur.execute("SELECT id, password FROM employees")
    users = cur.fetchall()

    count = 0
    for user_id, plain_password in users:
        
        if plain_password.startswith("scrypt:") or plain_password.startswith("pbkdf2:"):
            print(f"User {user_id} already hashed. Skipping.")
            continue

        # Convertir a Hash
        new_hash = generate_password_hash(plain_password)
        
        cur.execute("UPDATE employees SET password = %s WHERE id = %s", (new_hash, user_id))
        count += 1
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"Done! Updated {count} users to hashed passwords.")

if __name__ == "__main__":
    migrate()
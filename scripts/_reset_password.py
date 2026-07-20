import bcrypt, psycopg2

pw = "Henockglory@03"
h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()
print("New hash:", h)

conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="citevision", user="citevision", password="citevision")
cur = conn.cursor()
cur.execute("UPDATE users SET password_hash=%s WHERE email=%s", (h, "glory.henock@hologram.cd"))
conn.commit()
print("Updated", cur.rowcount, "rows")
conn.close()

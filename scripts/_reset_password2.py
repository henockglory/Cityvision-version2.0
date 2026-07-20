import bcrypt, subprocess

pw = b"Henockglory@03"
h = bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode()
print("New hash:", h)

sql = f"UPDATE users SET password_hash='{h}' WHERE email='glory.henock@hologram.cd';"
result = subprocess.run(
    ["docker", "exec", "citevision-v2-postgres", "psql", "-U", "citevision", "-d", "citevision", "-c", sql],
    capture_output=True, text=True
)
print("stdout:", result.stdout)
print("stderr:", result.stderr[:200])

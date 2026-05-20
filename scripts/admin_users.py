#!/usr/bin/env python3
"""CLI for managing admin users.

Usage:
    python scripts/admin_users.py list
    python scripts/admin_users.py add <username> <role>           # prompts for password
    python scripts/admin_users.py password <username>             # change password
    python scripts/admin_users.py role <username> <role>          # change role
    python scripts/admin_users.py countries <username> FR,BE,LU   # set country list (comma-separated ISO codes)
    python scripts/admin_users.py delete <username>
"""

import sys, os, getpass
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt
from app.database import SessionLocal
from app.models import AdminUser

ROLES = ("superadmin", "admin")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def prompt_password(username: str) -> str:
    while True:
        pwd = getpass.getpass(f"Password for {username}: ")
        if len(pwd) < 8:
            print("Password must be at least 8 characters.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if pwd != confirm:
            print("Passwords do not match.")
            continue
        return pwd


def cmd_list(db):
    users = db.query(AdminUser).order_by(AdminUser.role, AdminUser.username).all()
    if not users:
        print("No admin users.")
        return
    print(f"{'ID':>4}  {'Username':<20}  {'Role':<12}  {'Countries':<20}  {'Last login'}")
    print("-" * 85)
    for u in users:
        last = u.last_login.strftime("%Y-%m-%d %H:%M") if u.last_login else "—"
        countries = u.countries or "—"
        print(f"{u.id:>4}  {u.username:<20}  {u.role:<12}  {countries:<20}  {last}")


def cmd_add(db, username: str, role: str):
    if role not in ROLES:
        print(f"Invalid role '{role}'. Choose: {', '.join(ROLES)}")
        sys.exit(1)
    if db.query(AdminUser).filter_by(username=username).first():
        print(f"User '{username}' already exists.")
        sys.exit(1)
    pwd = prompt_password(username)
    user = AdminUser(username=username, password_hash=hash_password(pwd), role=role)
    db.add(user)
    db.commit()
    print(f"User '{username}' created with role '{role}'.")


def cmd_password(db, username: str):
    user = db.query(AdminUser).filter_by(username=username).first()
    if not user:
        print(f"User '{username}' not found.")
        sys.exit(1)
    pwd = prompt_password(username)
    user.password_hash = hash_password(pwd)
    db.commit()
    print(f"Password updated for '{username}'.")


def cmd_role(db, username: str, role: str):
    if role not in ROLES:
        print(f"Invalid role '{role}'. Choose: {', '.join(ROLES)}")
        sys.exit(1)
    user = db.query(AdminUser).filter_by(username=username).first()
    if not user:
        print(f"User '{username}' not found.")
        sys.exit(1)
    user.role = role
    db.commit()
    print(f"Role of '{username}' updated to '{role}'.")


def cmd_countries(db, username: str, countries_str: str):
    user = db.query(AdminUser).filter_by(username=username).first()
    if not user:
        print(f"User '{username}' not found.")
        sys.exit(1)
    codes = [c.strip().upper() for c in countries_str.split(",") if c.strip()]
    if not codes:
        user.countries = None
        db.commit()
        print(f"Countries cleared for '{username}'.")
        return
    user.countries = ",".join(codes)
    db.commit()
    print(f"Countries for '{username}' set to: {user.countries}")


def cmd_delete(db, username: str):
    user = db.query(AdminUser).filter_by(username=username).first()
    if not user:
        print(f"User '{username}' not found.")
        sys.exit(1)
    confirm = input(f"Delete user '{username}' ({user.role})? [y/N] ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return
    db.delete(user)
    db.commit()
    print(f"User '{username}' deleted.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    db = SessionLocal()
    try:
        cmd = args[0]
        if cmd == "list":
            cmd_list(db)
        elif cmd == "add" and len(args) == 3:
            cmd_add(db, args[1], args[2])
        elif cmd == "password" and len(args) == 2:
            cmd_password(db, args[1])
        elif cmd == "role" and len(args) == 3:
            cmd_role(db, args[1], args[2])
        elif cmd == "countries" and len(args) == 3:
            cmd_countries(db, args[1], args[2])
        elif cmd == "delete" and len(args) == 2:
            cmd_delete(db, args[1])
        else:
            print(__doc__)
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

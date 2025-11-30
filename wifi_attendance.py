"""
Wi-Fi Hotspot Attendance – Windows Version (MULTI TEACHER VERSION)
"""

import os
import re
import time
import configparser
from datetime import date, datetime
import mysql.connector


# -----------------------
# CONFIG
# -----------------------
def load_config(path="config.ini"):
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg


# -----------------------
# MAC Normalizer
# -----------------------
def normalize_mac(mac_raw, use_dash=False):
    if not mac_raw:
        return None
    s = mac_raw.strip().upper()
    s = re.sub(r'\.', '', s)
    s = re.sub(r'[^0-9A-F]', '', s)
    if len(s) != 12:
        return None
    sep = '-' if use_dash else ':'
    return sep.join(s[i:i+2] for i in range(0, 12, 2))


# -----------------------
# DB FUNCTIONS
# -----------------------
def get_db(cfg):
    return mysql.connector.connect(
        host=cfg.get('mysql', 'host'),
        user=cfg.get('mysql', 'user'),
        password=cfg.get('mysql', 'password'),
        database=cfg.get('mysql', 'database'),
        port=cfg.getint('mysql', 'port')
    )


def load_students(conn, use_dash=False):
    cur = conn.cursor()
    cur.execute("SELECT id, name, roll_no, mac_address FROM students")
    rows = cur.fetchall()
    cur.close()

    students = {}
    for sid, name, roll, mac in rows:
        nm = normalize_mac(mac, use_dash)
        students[nm] = {"id": sid, "name": name, "roll": roll}
    return students


def mark_attendance(conn, sid, class_name, teacher):
    cur = conn.cursor()
    today = date.today()

    cur.execute("""
        SELECT id FROM attendance
        WHERE student_id=%s AND date=%s AND class_name=%s
    """, (sid, today, class_name))

    if cur.fetchone():
        cur.close()
        return False

    cur.execute("""
        INSERT INTO attendance (student_id, date, time, status, class_name, teacher)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (sid, today, datetime.now().time(), "Present", class_name, teacher))

    conn.commit()
    cur.close()
    return True


# -----------------------
# MAIN SCAN (UPDATED)
# -----------------------
def run_scan(cfg, class_name, teacher):
    """
    NEW: Scanner now requires class_name (subject) and teacher
    These values will be coming from Streamlit.
    """

    use_dash = cfg.getboolean("app", "mac_use_dash")
    print(f"\n[{datetime.now()}] 🔍 Scanning for connected devices...")
    print(f"📘 Class: {class_name}  |  👩‍🏫 Teacher: {teacher}")

    try:
        conn = get_db(cfg)
        students = load_students(conn, use_dash)
        print(f"✅ Loaded {len(students)} students from DB")
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return

    # Use ARP to detect connected devices
    raw = os.popen("arp -a").read().splitlines()

    macs_raw = []
    for line in raw:
        m = re.search(r'([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}', line)
        if m:
            macs_raw.append(m.group(0))

    macs_norm = {normalize_mac(m, use_dash) for m in macs_raw if m}

    print("📡 Connected MACs:", macs_norm)

    count = 0
    for mac, info in students.items():
        if mac in macs_norm:
            try:
                ok = mark_attendance(conn, info["id"], class_name, teacher)
                if ok:
                    print(f"✅ Marked: {info['name']} ({info['roll']})")
                else:
                    print(f"ℹ Already Marked: {info['name']}")
                count += 1
            except Exception as e:
                print(f"❌ Attendance Error for {info['name']}: {e}")

    conn.close()
    print(f"🎉 Scan Complete — {count} student(s) present.\n")


# -----------------------
# MAIN ENTRY
# -----------------------
def main():
    cfg = load_config("config.ini")
    run_once = cfg.getboolean("app", "run_once")
    interval = cfg.getint("app", "scan_interval_seconds")

    print("⚠ Run as Administrator for accurate results.")

    # For direct run use dummy values
    class_name = "TEST_CLASS"
    teacher = "TEST_TEACHER"

    if run_once:
        run_scan(cfg, class_name, teacher)
    else:
        while True:
            run_scan(cfg, class_name, teacher)
            time.sleep(interval)


if __name__ == "__main__":
    main()

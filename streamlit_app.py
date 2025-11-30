# streamlit_app.py
import streamlit as st
import os, re
from datetime import date, datetime, timedelta
import configparser
import mysql.connector
import pandas as pd

# For Excel writing
from pathlib import Path

# -----------------------
# CONFIG
# -----------------------
def load_config(path="config.ini"):
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg

cfg = load_config("config.ini")

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
# DB helpers
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
    cur.execute("SELECT id, name, roll_no, mac_address FROM students ORDER BY roll_no")
    rows = cur.fetchall()
    cur.close()

    students = {}
    for sid, name, roll, mac in rows:
        nm = normalize_mac(mac, use_dash)
        students[nm] = {"id": sid, "name": name, "roll": roll, "mac": nm}
    return students

def fetch_attendance(conn, limit=500):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT a.id, a.student_id, s.name as student_name, 
                          s.roll_no, a.date, a.time, a.status,
                          a.class_name, a.teacher
                   FROM attendance a 
                   JOIN students s ON a.student_id = s.id
                   ORDER BY a.date DESC, a.time DESC LIMIT %s""", 
                   (limit,))
    rows = cur.fetchall()
    cur.close()
    return rows

def get_teachers(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, subject FROM teachers ORDER BY name")
    rows = cur.fetchall()
    cur.close()
    return rows

def add_teacher_db(conn, name, subject):
    cur = conn.cursor()
    cur.execute("INSERT INTO teachers (name, subject) VALUES (%s, %s)", (name, subject))
    conn.commit()
    cur.close()

def mark_attendance_db(conn, sid, class_name, teacher):
    cur = conn.cursor()
    today = date.today()

    cur.execute("""
        SELECT id FROM attendance
        WHERE student_id=%s AND date=%s AND class_name=%s AND teacher=%s
    """, (sid, today, class_name, teacher))

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

def manual_set_status(conn, sid, status, class_name, teacher):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO attendance (student_id, date, time, status, class_name, teacher)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (sid, date.today(), datetime.now().time(), status, class_name, teacher))
    conn.commit()
    cur.close()

# -----------------------
# SCAN LOGIC (UPDATED)
# -----------------------
def scan_network_and_mark(cfg, class_name, teacher):
    use_dash = cfg.getboolean("app", "mac_use_dash")

    conn = get_db(cfg)
    students = load_students(conn, use_dash)

    # Run arp -a
    try:
        raw = os.popen("arp -a").read().splitlines()
    except Exception:
        raw = []

    macs_raw = []
    for line in raw:
        m = re.search(r'([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}', line)
        if m:
            macs_raw.append(m.group(0))

    macs_norm = {normalize_mac(m, use_dash) for m in macs_raw if m}

    present = []
    already = []
    errors = []

    for mac, info in students.items():
        if mac in macs_norm:
            try:
                ok = mark_attendance_db(conn, info["id"], class_name, teacher)
                if ok:
                    present.append(info)
                else:
                    already.append(info)
            except Exception as e:
                errors.append((info, str(e)))

    conn.close()
    return {
        "detected_macs": list(macs_norm),
        "marked": present,
        "already": already,
        "errors": errors,
        "count": len(present)
    }

# -----------------------
# EXPORT: per-teacher Excel (one file per teacher, sheets = YYYY-MM)
# -----------------------
def export_month_sheet(conn, teacher_name, class_name, year=None, month=None, out_dir="exports"):
    # default to current month
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    # get all students (we keep file per teacher containing all students)
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT id, name, roll_no FROM students ORDER BY roll_no")
    students = cur.fetchall()
    cur.close()

    # compute month range
    start = date(year, month, 1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = next_month - timedelta(days=1)
    days = last.day

    rows = []
    for sid, name, roll in students:
        row = {"roll_no": roll, "name": name}

        for d in range(1, days + 1):
            cur_date = date(year, month, d)

            # IMPORTANT FIX: use buffered cursor + fetchall()
            c = conn.cursor(buffered=True)
            c.execute("""
                SELECT status FROM attendance 
                WHERE student_id=%s AND date=%s AND class_name=%s AND teacher=%s
            """, (sid, cur_date, class_name, teacher_name))

            result_rows = c.fetchall()       # <-- FIX (no unread results)
            c.close()

            row[f"{d:02d}"] = "P" if result_rows else "A"

        rows.append(row)

    df = pd.DataFrame(rows).set_index(["roll_no", "name"])

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    file_name = f"{out_dir}/attendance_{teacher_name.replace(' ', '_')}.xlsx"
    sheet_name = f"{year}-{month:02d}"

    try:
        with pd.ExcelWriter(file_name, mode="a", engine="openpyxl", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name=sheet_name)
    except Exception:
        with pd.ExcelWriter(file_name, mode="w", engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name)

    return file_name, sheet_name


# -----------------------
# STREAMLIT UI
# -----------------------
st.set_page_config(page_title="Wi-Fi Hotspot Attendance", layout="wide")
st.title("📡 Wi-Fi Hotspot Attendance System")

# utility: load teachers for sidebar
def reload_teachers():
    conn = get_db(cfg)
    teachers = get_teachers(conn)
    conn.close()
    return teachers

# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("Session Setup")

    # teacher selectbox (load from DB)
    teachers = reload_teachers()
    teacher_options = [f"{t['name']} — {t['subject']}" for t in teachers]
    teacher_choice = st.selectbox("Select Teacher (name — subject)", teacher_options if teacher_options else ["No teachers yet"])

    # parse
    if teacher_options:
        selected = next(t for t in teachers if f"{t['name']} — {t['subject']}" == teacher_choice)
        selected_teacher = selected['name']
        selected_class = selected['subject']
    else:
        # fallback empty
        selected_teacher = st.text_input("Teacher Name")
        selected_class = st.text_input("Class / Subject")

    # Keep teacher + class in session_state and detect change
    prev = st.session_state.get("selected_teacher", None)
    prev_class = st.session_state.get("selected_class", None)
    if (selected_teacher != prev) or (selected_class != prev_class):
        # teacher/class changed -> clear last_result so ticks refresh
        st.session_state.pop("last_result", None)
        st.session_state.pop("last_scan", None)
        st.session_state["selected_teacher"] = selected_teacher
        st.session_state["selected_class"] = selected_class

    st.markdown("---")
    
    st.markdown("### Add Teacher")
    with st.form("add_teacher"):
        t_name = st.text_input("Teacher name")
        t_sub = st.text_input("Subject name")
        submitted = st.form_submit_button("Add Teacher")
        if submitted and t_name and t_sub:
            conn = get_db(cfg)
            add_teacher_db(conn, t_name.strip(), t_sub.strip())
            conn.close()
            st.success("Teacher added. Please re-open the selectbox (or Refresh).")

# ---------- TOP BUTTONS ----------
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🔍 Run Scan Now"):
        with st.spinner("Scanning network & marking attendance..."):
            result = scan_network_and_mark(cfg, st.session_state["selected_class"], st.session_state["selected_teacher"])
            st.session_state["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state["last_result"] = result
            st.success(f"Scan complete — {result['count']} new present marked.")

with col2:
    refresh = st.button("⟳ Refresh All")

if refresh:
    st.session_state["recent_attendance"] = []
    st.session_state["detected_macs"] = []
    st.session_state["new_present"] = 0
    st.session_state["already_marked"] = 0
    st.session_state["last_scan_time"] = None

    st.success("UI reset successfully!")


with col3:
    st.write("Last scan:", st.session_state.get("last_scan", "—"))

with col4:
    if st.button("📥 Export Monthly Excel"):
        conn = get_db(cfg)
        file_name, sheet = export_month_sheet(conn,
                                             st.session_state["selected_teacher"],
                                             st.session_state["selected_class"])
        conn.close()
        st.success(f"Exported -> {file_name} (sheet {sheet})")
        st.write(f"Saved: {file_name}")

# ---------- SUMMARY ----------
res = st.session_state.get("last_result", {
    "detected_macs": [], "marked": [], "already": [], "errors": [], "count": 0
})

c1, c2, c3 = st.columns(3)
c1.metric("Detected MACs", len(res["detected_macs"]))
c2.metric("New Present", len(res["marked"]))
c3.metric("Already Marked", len(res["already"]))

st.markdown("---")

# ---------- CONTENT LAYOUT ----------
left, right = st.columns([2,3])

# ---------------- STUDENTS LIST ----------------
with left:
    st.subheader("Students")
    conn = get_db(cfg)
    students = load_students(conn, cfg.getboolean("app","mac_use_dash"))

    # Today's attendance filtered by selected class+teacher only
    cur = conn.cursor()
    cur.execute("SELECT student_id FROM attendance WHERE date=%s AND class_name=%s AND teacher=%s",
                (date.today(), st.session_state["selected_class"], st.session_state["selected_teacher"]))
    present_ids = {r[0] for r in cur.fetchall()}
    cur.close()

    rows = []
    for mac, s in students.items():
        rows.append({
            "id": s["id"],
            "name": s["name"],
            "roll": s["roll"],
            "mac": s["mac"],
            "present": s["id"] in present_ids
        })
    df = pd.DataFrame(rows)

    q = st.text_input("Search (name / roll)")
    if q:
        df = df[df["name"].str.contains(q, case=False) |
                df["roll"].str.contains(q, case=False)]

    st.dataframe(df[["name","roll","mac","present"]], height=360)

    st.markdown("### Manual Actions")
    sel = st.selectbox("Select student (ID)", options=[None]+list(df["id"]))

    if sel:
        st.write(df[df["id"]==sel].iloc[0].to_dict())

        c1, c2, c3 = st.columns(3)

        if c1.button("Mark Present"):
            conn = get_db(cfg)
            manual_set_status(conn, sel, "Present", st.session_state["selected_class"], st.session_state["selected_teacher"])
            conn.close()
            # After manual mark, clear last_result to force UI refresh
            st.session_state.pop("last_result", None)
            st.success("Marked present.")

        if c2.button("Mark Absent"):
            conn = get_db(cfg)
            manual_set_status(conn, sel, "Absent", st.session_state["selected_class"], st.session_state["selected_teacher"])
            conn.close()
            st.session_state.pop("last_result", None)
            st.success("Marked absent.")

        if c3.button("Delete Student"):
            conn = get_db(cfg)
            cur = conn.cursor()
            cur.execute("DELETE FROM students WHERE id=%s", (sel,))
            conn.commit()
            cur.close()
            conn.close()
            st.session_state.pop("last_result", None)
            st.success("Student deleted.")

    st.markdown("### Add Student")
    with st.form("add_student"):
        name = st.text_input("Name")
        roll = st.text_input("Roll")
        mac = st.text_input("MAC Address")
        submitted = st.form_submit_button("Add")
        if submitted:
            conn = get_db(cfg)
            cur = conn.cursor()
            cur.execute("INSERT INTO students (name, roll_no, mac_address) VALUES (%s,%s,%s)",
                        (name, roll, mac))
            conn.commit()
            cur.close()
            conn.close()
            st.session_state.pop("last_result", None)
            st.success("Student added.")

# ---------------- ATTENDANCE TABLE ----------------
with right:
    st.subheader("Recent Attendance")

    conn = get_db(cfg)
    att = fetch_attendance(conn, limit=500)
    conn.close()

    df_att = pd.DataFrame(att)

    if not df_att.empty:
        st.dataframe(df_att[
            ["student_name","roll_no","date","time","status","class_name","teacher"]
        ].sort_values(["date","time"], ascending=False), height=520)

        csv = df_att.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export CSV (all recent)", csv, "attendance_recent.csv", "text/csv")
    else:
        st.info("No attendance yet.")

    # ---- Move Monthly Export Here (bottom-right) ----
    st.markdown("### 📘 Subject-wise Auto Excel Export")

    if st.button("📤 Update Teacher Excel"):
        conn = get_db(cfg)
        file_name, sheet = export_month_sheet(
            conn,
            st.session_state["selected_teacher"],
            st.session_state["selected_class"]
        )
        conn.close()
        st.success(f"Updated → {file_name} (Sheet: {sheet})")
        st.write(f"Saved: {file_name}")

st.caption("Run Streamlit as Administrator for accurate `arp -a` output.")


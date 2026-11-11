import csv
from datetime import datetime
from io import StringIO

from flask import Flask, Response, render_template, request, redirect, url_for
from db import get_conn, init_db

app = Flask(__name__)
init_db()
app.json.ensure_ascii = False

DOORS = {"D01": "一号门（大厅）", "D02": "二号门（机房）"}
WORK_START = "09:00"
OFFLINE_SEC = 60
TIME_FMT = "%Y-%m-%d %H:%M:%S"

RESULT_OK = "通过"
RESULT_UNKNOWN = "未知卡"
RESULT_LEFT = "离职卡"
RESULT_NO_PERM = "无权限"
RESULT_OUT_TIME = "越权时段"


@app.route("/")
def index():
    modules = [
        ("员工 / 部门管理", "第 1 周", "已完成"),
        ("打卡记录", "第 2 周", "已完成"),
        ("考勤月报", "第 2 周", "已完成"),
        ("门禁权限", "第 3 周", "已完成"),
        ("设备在线状态", "第 3 周", "进行中"),
        ("网络规划", "第 4 周", "待开始"),
    ]
    return render_template("index.html", modules=modules)


@app.route("/employees")
def employees():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM employee ORDER BY CASE status WHEN '在职' THEN 0 ELSE 1 END, id DESC"
    ).fetchall()
    conn.close()
    return render_template("employees.html", employees=rows)


@app.route("/employees/add", methods=["POST"])
def employee_add():
    name = request.form.get("name", "").strip()
    dept = request.form.get("dept", "").strip()
    card_no = request.form.get("card_no", "").strip()
    if name and dept and card_no:
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO employee (name, dept, card_no) VALUES (?, ?, ?)",
                (name, dept, card_no),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            app.logger.warning("员工新增失败: %s", e)
        finally:
            conn.close()
    return redirect(url_for("employees"))


@app.route("/employees/<int:emp_id>/leave", methods=["POST"])
def employee_leave(emp_id):
    conn = get_conn()
    conn.execute("UPDATE employee SET status = '离职' WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("employees"))


@app.route("/employees/<int:emp_id>/back", methods=["POST"])
def employee_back(emp_id):
    conn = get_conn()
    conn.execute("UPDATE employee SET status = '在职' WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("employees"))


@app.route("/permissions")
def permissions():
    conn = get_conn()
    perms = conn.execute("""
        SELECT p.*, e.name, e.card_no
        FROM door_permission p
        LEFT JOIN employee e ON e.id = p.employee_id
        ORDER BY p.id DESC
    """).fetchall()
    emps = conn.execute("SELECT * FROM employee WHERE status = '在职' ORDER BY id").fetchall()
    conn.close()
    return render_template("permissions.html", perms=perms, employees=emps, doors=DOORS)


@app.route("/permissions/add", methods=["POST"])
def permission_add():
    employee_id = request.form.get("employee_id")
    door_id = request.form.get("door_id")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    if employee_id and door_id and start_time and end_time:
        conn = get_conn()
        conn.execute(
            "INSERT INTO door_permission (employee_id, door_id, start_time, end_time) VALUES (?, ?, ?, ?)",
            (employee_id, door_id, start_time, end_time),
        )
        conn.commit()
        conn.close()
    return redirect(url_for("permissions"))


@app.route("/permissions/<int:perm_id>/toggle", methods=["POST"])
def permission_toggle(perm_id):
    conn = get_conn()
    row = conn.execute("SELECT enabled FROM door_permission WHERE id = ?", (perm_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE door_permission SET enabled = ? WHERE id = ?",
            (0 if row["enabled"] == 1 else 1, perm_id),
        )
        conn.commit()
    conn.close()
    return redirect(url_for("permissions"))


def check_permission(conn, employee_id, door_id, now_time):
    rows = conn.execute(
        "SELECT * FROM door_permission WHERE employee_id = ? AND door_id = ? AND enabled = 1",
        (employee_id, door_id),
    ).fetchall()
    if not rows:
        return RESULT_NO_PERM
    for r in rows:
        if r["start_time"] <= now_time <= r["end_time"]:
            return RESULT_OK
    return RESULT_OUT_TIME


@app.route("/devices")
def devices():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM device ORDER BY door_id").fetchall()
    conn.close()

    now = datetime.now()
    items = []
    for r in rows:
        try:
            last = datetime.strptime(r["last_heartbeat"], TIME_FMT)
            age = int((now - last).total_seconds())
        except Exception:
            age = 999999
        items.append({
            "device_id": r["device_id"],
            "door_id": r["door_id"],
            "ip": r["ip"],
            "last_heartbeat": r["last_heartbeat"],
            "age": age,
            "online": age <= OFFLINE_SEC,
        })

    online_cnt = sum(1 for i in items if i["online"])
    return render_template(
        "devices.html",
        devices=items,
        total=len(items),
        online=online_cnt,
        offline_sec=OFFLINE_SEC,
    )


@app.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    """门禁设备心跳上报。设备首次上报时自动注册。"""
    data = request.get_json(silent=True) or request.form
    device_id = (data.get("device_id") or "").strip()
    door_id = (data.get("door_id") or "D01").strip()
    ip = (data.get("ip") or "").strip()
    now = datetime.now().strftime(TIME_FMT)

    if not device_id:
        return {"ok": False, "msg": "device_id 不能为空"}, 400

    conn = get_conn()
    row = conn.execute("SELECT * FROM device WHERE device_id = ?", (device_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE device SET last_heartbeat = ?, ip = ?, door_id = ? WHERE device_id = ?",
            (now, ip or row["ip"], door_id, device_id),
        )
    else:
        conn.execute(
            "INSERT INTO device (device_id, door_id, ip, last_heartbeat) VALUES (?, ?, ?, ?)",
            (device_id, door_id, ip, now),
        )
    conn.commit()
    conn.close()
    return {"ok": True, "device_id": device_id, "time": now}


@app.route("/attendance")
def attendance():
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.*, COALESCE(e.name, '未知') AS name
        FROM attendance_log a
        LEFT JOIN employee e ON e.card_no = a.card_no
        ORDER BY a.id DESC
        LIMIT 50
    """).fetchall()

    today = datetime.now().strftime("%Y-%m-%d")
    cond = today + "%"
    total = conn.execute(
        "SELECT COUNT(*) c FROM attendance_log WHERE punch_time LIKE ?", (cond,)
    ).fetchone()["c"]
    people = conn.execute(
        "SELECT COUNT(DISTINCT card_no) c FROM attendance_log WHERE result = '通过' AND punch_time LIKE ?",
        (cond,),
    ).fetchone()["c"]
    deny = conn.execute(
        "SELECT COUNT(*) c FROM attendance_log WHERE result <> '通过' AND punch_time LIKE ?", (cond,)
    ).fetchone()["c"]
    conn.close()
    return render_template(
        "attendance.html", logs=rows, total=total, people=people, deny=deny, today=today
    )


@app.route("/api/punch", methods=["POST"])
def api_punch():
    data = request.get_json(silent=True) or request.form
    card_no = (data.get("card_no") or "").strip()
    door_id = (data.get("door_id") or "D01").strip()
    now = datetime.now().strftime(TIME_FMT)
    now_time = now[11:19]

    conn = get_conn()
    emp = conn.execute("SELECT * FROM employee WHERE card_no = ?", (card_no,)).fetchone()

    if not emp:
        result = RESULT_UNKNOWN
    elif emp["status"] != "在职":
        result = RESULT_LEFT
    else:
        result = check_permission(conn, emp["id"], door_id, now_time)

    conn.execute(
        "INSERT INTO attendance_log (card_no, door_id, punch_time, result) VALUES (?, ?, ?, ?)",
        (card_no, door_id, now, result),
    )
    conn.commit()
    conn.close()

    return {
        "ok": result == RESULT_OK,
        "card_no": card_no,
        "name": emp["name"] if emp else None,
        "door": DOORS.get(door_id, door_id),
        "result": result,
        "time": now,
    }


def build_month_stats(month):
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.card_no, a.punch_time, e.name, e.dept
        FROM attendance_log a
        LEFT JOIN employee e ON e.card_no = a.card_no
        WHERE a.punch_time LIKE ? AND a.result = '通过'
        ORDER BY a.punch_time
    """, (month + "%",)).fetchall()
    conn.close()

    agg = {}
    for r in rows:
        day = r["punch_time"][:10]
        tm = r["punch_time"][11:19]
        item = agg.setdefault(r["card_no"], {
            "card_no": r["card_no"],
            "name": r["name"] or "未知",
            "dept": r["dept"] or "-",
            "days": set(),
            "late": 0,
        })
        if day not in item["days"]:
            item["days"].add(day)
            if tm > WORK_START:
                item["late"] += 1

    stats = [{
        "card_no": it["card_no"],
        "name": it["name"],
        "dept": it["dept"],
        "days": len(it["days"]),
        "late": it["late"],
    } for it in agg.values()]
    stats.sort(key=lambda x: (-x["days"], x["card_no"]))
    return stats


@app.route("/report")
def report():
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")
    stats = build_month_stats(month)
    return render_template(
        "report.html",
        month=month,
        stats=stats,
        total_late=sum(s["late"] for s in stats),
        work_start=WORK_START,
    )


@app.route("/report/export")
def report_export():
    month = request.args.get("month") or datetime.now().strftime("%Y-%m")
    stats = build_month_stats(month)

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["卡号", "姓名", "部门", "出勤天数", "迟到次数"])
    for s in stats:
        writer.writerow([s["card_no"], s["name"], s["dept"], s["days"], s["late"]])

    data = "\ufeff" + buf.getvalue()
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=attendance_{month}.csv"},
    )


@app.route("/api/stats")
def api_stats():
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    cond = today + "%"
    total = conn.execute(
        "SELECT COUNT(*) c FROM attendance_log WHERE punch_time LIKE ?", (cond,)
    ).fetchone()["c"]
    deny = conn.execute(
        "SELECT COUNT(*) c FROM attendance_log WHERE result <> '通过' AND punch_time LIKE ?", (cond,)
    ).fetchone()["c"]
    conn.close()
    return {"date": today, "total": total, "deny": deny}


@app.route("/health")
def health():
    return {"status": "ok", "service": "access-attendance"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

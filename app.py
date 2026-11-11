import csv
from datetime import datetime
from io import StringIO

from flask import Flask, Response, render_template, request, redirect, url_for
from db import get_conn, init_db

app = Flask(__name__)
init_db()

DOORS = {"D01": "一号门（大厅）", "D02": "二号门（机房）"}
WORK_START = "09:00"


@app.route("/")
def index():
    modules = [
        ("员工 / 部门管理", "第 1 周", "已完成"),
        ("打卡记录", "第 2 周", "已完成"),
        ("考勤月报", "第 2 周", "已完成"),
        ("门禁权限", "第 3 周", "待开始"),
        ("设备在线状态", "第 3 周", "待开始"),
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
        "SELECT COUNT(DISTINCT card_no) c FROM attendance_log WHERE punch_time LIKE ?", (cond,)
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_conn()
    emp = conn.execute("SELECT * FROM employee WHERE card_no = ?", (card_no,)).fetchone()
    if not emp:
        result = "未知卡"
    elif emp["status"] != "在职":
        result = "离职卡"
    else:
        result = "通过"

    conn.execute(
        "INSERT INTO attendance_log (card_no, door_id, punch_time, result) VALUES (?, ?, ?, ?)",
        (card_no, door_id, now, result),
    )
    conn.commit()
    conn.close()

    return {
        "ok": result == "通过",
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

    stats = []
    for it in agg.values():
        stats.append({
            "card_no": it["card_no"],
            "name": it["name"],
            "dept": it["dept"],
            "days": len(it["days"]),
            "late": it["late"],
        })
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

    data = "\ufeff" + buf.getvalue()  # BOM，保证 WPS/Excel 打开中文不乱码
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

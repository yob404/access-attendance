from flask import Flask, render_template, request, redirect, url_for
from db import get_conn, init_db

app = Flask(__name__)
init_db()


@app.route("/")
def index():
    modules = [
        ("员工 / 部门管理", "第 1 周", "进行中"),
        ("打卡记录", "第 2 周", "待开始"),
        ("考勤月报", "第 2 周", "待开始"),
        ("门禁权限", "第 3 周", "待开始"),
        ("设备在线状态", "第 3 周", "待开始"),
        ("网络规划", "第 4 周", "待开始"),
    ]
    return render_template("index.html", modules=modules)


@app.route("/employees")
def employees():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM employee ORDER BY id DESC").fetchall()
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


@app.route("/employees/<int:emp_id>/delete", methods=["POST"])
def employee_delete(emp_id):
    conn = get_conn()
    conn.execute("DELETE FROM employee WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("employees"))


@app.route("/health")
def health():
    return {"status": "ok", "service": "access-attendance"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

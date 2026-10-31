from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from pathlib import Path
import os, time, uuid

app = Flask(__name__)
app.secret_key = "local-demo-secret-change-me"
app.config["UPLOAD_FOLDER"] = Path("uploads")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = 1800
app.config["UPLOAD_FOLDER"].mkdir(exist_ok=True)

# Demo-only data store. Replace with SQLite in a later milestone.
APPLICATIONS = {}

def scenario(name):
    return request.args.get(name) == "1" or request.form.get("scenario_" + name) == "1"

def flags():
    names = ["legacy", "expire_session", "popup", "slow", "flaky_500", "rename_ids", "gate", "inject"]
    return {name: request.args.get(name) == "1" for name in names}

@app.before_request
def simulate_portal_conditions():
    if request.endpoint == "static":
        return
    if request.args.get("slow") == "1":
        time.sleep(2)
    if request.args.get("flaky_500") == "1" and request.args.get("fail_once") != "0":
        # Deterministic demo failure; append ?fail_once=0 to continue after observing it.
        return render_template("error.html", message="Temporary server error (demo scenario).",
                               hint="Reload with fail_once=0 to continue the demo."), 500
    if session.get("logged_in") and request.args.get("expire_session") == "1":
        session.clear()
        if request.endpoint not in ("login",):
            return redirect(url_for("login", **flags()))

@app.route("/", methods=["GET"])
def index():
    if session.get("logged_in"):
        return redirect(url_for("application", step=1, **flags()))
    return redirect(url_for("login", **flags()))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Synthetic demo credentials only.
        if request.form.get("username") == "student" and request.form.get("password") == "demo123":
            session["logged_in"] = True
            session["student_name"] = "Aarav Sharma"
            return redirect(url_for("application", step=1, **flags()))
        flash("Invalid demo credentials. Try the credentials shown below.", "error")
    return render_template("login.html", flags=flags())

@app.route("/application/<int:step>", methods=["GET", "POST"])
def application(step):
    if not session.get("logged_in"):
        return redirect(url_for("login", **flags()))
    if step not in (1, 2, 3):
        return redirect(url_for("application", step=1, **flags()))

    if request.method == "POST":
        data = session.get("application_data", {})
        if step == 1:
            data.update({
                "full_name": request.form.get("full_name", ""),
                "dob": request.form.get("dob", ""),
                "category": request.form.get("category", ""),
                "course": request.form.get("course", ""),
                "state": request.form.get("state", ""),
                "district": request.form.get("district", ""),
                "block": request.form.get("block", ""),
            })
            if not data["full_name"] or not data["dob"]:
                flash("Please complete the required personal details.", "error")
                session["application_data"] = data
                return redirect(url_for("application", step=1, **flags()))
        elif step == 2:
            data.update({
                "college": request.form.get("college", ""),
                "course_year": request.form.get("course_year", ""),
                "marks": request.form.get("marks", ""),
                "annual_income": request.form.get("annual_income", ""),
            })
            uploaded = request.files.get("marksheet")
            if uploaded and uploaded.filename:
                if len(uploaded.read()) > 2 * 1024 * 1024:
                    flash("File too large. Maximum upload size is 2 MB.", "error")
                    return redirect(url_for("application", step=2, **flags()))
                uploaded.seek(0)
                safe_name = secure_filename(uploaded.filename)
                stored_name = f"{uuid.uuid4().hex}_{safe_name}"
                uploaded.save(app.config["UPLOAD_FOLDER"] / stored_name)
                data["marksheet"] = safe_name
        else:
            data["declaration"] = request.form.get("declaration") == "yes"
            if not data["declaration"]:
                flash("Please accept the declaration to continue.", "error")
                session["application_data"] = data
                return redirect(url_for("application", step=3, **flags()))
            session["application_data"] = data
            if request.args.get("gate") == "1":
                return redirect(url_for("human_gate", **flags()))
            return redirect(url_for("review", **flags()))
        session["application_data"] = data
        return redirect(url_for("application", step=step + 1, **flags()))

    return render_template(f"step{step}.html", step=step, data=session.get("application_data", {}),
                           flags=flags(), legacy=request.args.get("legacy") == "1",
                           rename_ids=request.args.get("rename_ids") == "1",
                           popup=request.args.get("popup") == "1",
                           inject=request.args.get("inject") == "1")

@app.route("/human-check", methods=["GET", "POST"])
def human_gate():
    if not session.get("logged_in"):
        return redirect(url_for("login", **flags()))
    if request.method == "POST":
        if request.form.get("captcha") == "DEMO-1234" and request.form.get("otp") == "123456":
            return redirect(url_for("review", **flags()))
        flash("Demo CAPTCHA or OTP did not match. Please try again.", "error")
    return render_template("gate.html", flags=flags())

@app.route("/review", methods=["GET"])
def review():
    if not session.get("logged_in"):
        return redirect(url_for("login", **flags()))
    return render_template("review.html", data=session.get("application_data", {}), flags=flags())

@app.route("/submit", methods=["POST"])
def submit():
    if not session.get("logged_in"):
        return redirect(url_for("login", **flags()))
    if request.form.get("approved") != "yes":
        return redirect(url_for("review", **flags()))
    # Prevent duplicate submissions for this browser session.
    if session.get("receipt_id"):
        return redirect(url_for("receipt", receipt_id=session["receipt_id"]))
    receipt_id = "SCH-" + uuid.uuid4().hex[:8].upper()
    APPLICATIONS[receipt_id] = dict(session.get("application_data", {}))
    session["receipt_id"] = receipt_id
    return redirect(url_for("receipt", receipt_id=receipt_id))

@app.route("/receipt/<receipt_id>")
def receipt(receipt_id):
    if receipt_id not in APPLICATIONS:
        return render_template("error.html", message="Receipt not found.", hint="Submit a demo application first."), 404
    return render_template("receipt.html", receipt_id=receipt_id, data=APPLICATIONS[receipt_id])

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.errorhandler(413)
def too_large(_):
    return render_template("error.html", message="Upload too large.", hint="Use a file smaller than 2 MB."), 413

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

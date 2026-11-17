import os
import io
import base64
import mysql.connector
import qrcode
from cryptography.fernet import Fernet
from flask import Flask, request, render_template_string, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vibe_coding_secret_key")

FERNET_KEY = b'8co2_kP9vL4mN7qR1sT5uW8xZ0aB3cE6fH9jK2lM5nP='
cipher = Fernet(FERNET_KEY)

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQLHOST", "127.0.0.1"),
        user=os.environ.get("MYSQLUSER", "root"),
        password=os.environ.get("MYSQLPASSWORD", ""),
        database=os.environ.get("MYSQLDATABASE", "certificate_db"),
        port=int(os.environ.get("MYSQLPORT", 3306))
    )

def init_db():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                dept_id INT AUTO_INCREMENT PRIMARY KEY,
                dept_name VARCHAR(100) UNIQUE NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                course_id INT AUTO_INCREMENT PRIMARY KEY,
                dept_id INT,
                course_name VARCHAR(100) NOT NULL,
                FOREIGN KEY (dept_id) REFERENCES departments(dept_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS certificates (
                cert_id INT AUTO_INCREMENT PRIMARY KEY,
                reg_no VARCHAR(50) UNIQUE NOT NULL,
                student_name VARCHAR(100) NOT NULL,
                dob DATE NOT NULL,
                dept_id INT,
                course_id INT,
                photo_b64 LONGTEXT,
                encrypted_token VARCHAR(500) UNIQUE NOT NULL,
                qr_b64 LONGTEXT,
                issue_date DATE DEFAULT (CURRENT_DATE),
                FOREIGN KEY (dept_id) REFERENCES departments(dept_id),
                FOREIGN KEY (course_id) REFERENCES courses(course_id)
            )
        """)
        cursor.execute("INSERT IGNORE INTO departments (dept_id, dept_name) VALUES (1, 'Computer Applications'), (2, 'Computer Science')")
        cursor.execute("INSERT IGNORE INTO courses (course_id, dept_id, course_name) VALUES (1, 1, 'BCA'), (2, 2, 'B.Sc. Computer Science')")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("DB Init Note:", e)

init_db()

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Digital Certificate Verification</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; }
        .cert-box { border: 8px double #1a365d; padding: 25px; background: #fff; border-radius: 8px; }
    </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
    <div class="container">
        <a class="navbar-brand fw-bold" href="/">🎓 CertVerify QR</a>
        <div>
            <a href="/" class="btn btn-outline-light btn-sm me-2">Verifier</a>
            {% if session.get('admin') %}
                <a href="/admin" class="btn btn-light btn-sm me-2">Admin</a>
                <a href="/logout" class="btn btn-danger btn-sm">Logout</a>
            {% else %}
                <a href="/login" class="btn btn-warning btn-sm">Admin Login</a>
            {% endif %}
        </div>
    </div>
</nav>
<div class="container pb-5">
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, msg in messages %}
            <div class="alert alert-{{ category }} alert-dismissible fade show">{{ msg }}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        {% endfor %}
    {% endwith %}
    {{ content | safe }}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/')
def index():
    content = """
    <div class="row justify-content-center">
        <div class="col-md-10">
            <div class="text-center mb-4">
                <h2 class="fw-bold text-primary">Academic Certificate Verification</h2>
                <p class="text-muted">Scan QR via Camera, Upload QR Image, or Verify Manually</p>
            </div>
            <div class="row g-4">
                <!-- Method 1: Live Camera or QR File Upload -->
                <div class="col-md-6">
                    <div class="card shadow-sm h-100">
                        <div class="card-header bg-dark text-white fw-bold">Method 1: Scan or Upload QR Code</div>
                        <div class="card-body">
                            <div id="reader" class="mb-3"></div>
                            <form id="qrForm" action="/verify/qr" method="POST">
                                <input type="hidden" name="token" id="qrTokenInput">
                            </form>
                            <div class="text-muted small">Allow camera access to scan live, or click "Scan an Image File" above to upload a downloaded QR code.</div>
                        </div>
                    </div>
                </div>
                <!-- Method 2: Manual Entry -->
                <div class="col-md-6">
                    <div class="card shadow-sm h-100">
                        <div class="card-header bg-secondary text-white fw-bold">Method 2: Manual Verification</div>
                        <div class="card-body">
                            <form action="/verify/manual" method="POST">
                                <div class="mb-2">
                                    <label class="form-label">Registration Number</label>
                                    <input type="text" name="reg_no" class="form-control" required>
                                </div>
                                <div class="mb-2">
                                    <label class="form-label">Student Full Name</label>
                                    <input type="text" name="student_name" class="form-control" required>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Date of Birth</label>
                                    <input type="date" name="dob" class="form-control" required>
                                </div>
                                <button type="submit" class="btn btn-success w-100">Verify Details</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
    <script>
        function onScanSuccess(decodedText) {
            document.getElementById('qrTokenInput').value = decodedText;
            document.getElementById('qrForm').submit();
        }
        let html5QrcodeScanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 220 });
        html5QrcodeScanner.render(onScanSuccess);
    </script>
    """
    return render_template_string(BASE_HTML, content=content)

@app.route('/verify/qr', methods=['POST'])
def verify_qr():
    token = request.form.get('token', '').strip()
    if not token:
        flash("❌ No QR data received.", "danger")
        return redirect(url_for('index'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT reg_no FROM certificates WHERE encrypted_token = %s", (token,))
    cert = cursor.fetchone()
    cursor.close()
    conn.close()

    if not cert:
        flash("⚠️ FAKE / INVALID CERTIFICATE: QR signature does not match any official record!", "danger")
        return redirect(url_for('index'))

    return redirect(url_for('view_certificate', reg_no=cert['reg_no'], verified=1))

@app.route('/verify/manual', methods=['POST'])
def verify_manual():
    reg_no = request.form['reg_no'].strip()
    student_name = request.form['student_name'].strip()
    dob = request.form['dob']

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT reg_no FROM certificates 
        WHERE reg_no = %s AND LOWER(student_name) = LOWER(%s) AND dob = %s
    """, (reg_no, student_name, dob))
    cert = cursor.fetchone()
    cursor.close()
    conn.close()

    if not cert:
        flash("❌ Verification Failed: Details do not match any issued certificate.", "danger")
        return redirect(url_for('index'))

    return redirect(url_for('view_certificate', reg_no=cert['reg_no'], verified=1))

@app.route('/certificate/<reg_no>')
def view_certificate(reg_no):
    verified = request.args.get('verified')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.*, d.dept_name, co.course_name 
        FROM certificates c
        JOIN departments d ON c.dept_id = d.dept_id
        JOIN courses co ON c.course_id = co.course_id
        WHERE c.reg_no = %s
    """, (reg_no,))
    cert = cursor.fetchone()
    cursor.close()
    conn.close()

    if not cert:
        flash("Certificate not found.", "danger")
        return redirect(url_for('index'))

    badge = '<div class="alert alert-success text-center fw-bold">✅ VERIFIED AUTHENTIC DIGITAL CERTIFICATE</div>' if verified else ''
    
    content = f"""
    {badge}
    <div class="cert-box shadow mx-auto" style="max-width: 800px;">
        <div class="row align-items-center mb-4">
            <div class="col-8">
                <h3 class="text-uppercase fw-bold text-primary mb-0">Certificate of Completion</h3>
                <small class="text-muted">Official Tamper-Proof Academic Credential</small>
            </div>
            <div class="col-4 text-end">
                <img src="data:image/jpeg;base64,{cert['photo_b64']}" alt="Student Photo" class="img-thumbnail" style="width: 110px; height: 130px; object-fit: cover;">
            </div>
        </div>
        <hr>
        <p class="fs-5">This is to certify that <strong>{cert['student_name']}</strong> (Reg No: <strong>{cert['reg_no']}</strong>), born on <strong>{cert['dob']}</strong>, has successfully completed the requirements for:</p>
        <h4 class="text-center my-3 text-dark fw-bold">{cert['course_name']}</h4>
        <p class="text-center text-muted">Department of {cert['dept_name']}</p>
        <hr>
        <div class="row align-items-center mt-4">
            <div class="col-6">
                <p class="mb-1"><strong>Issue Date:</strong> {cert['issue_date']}</p>
                <p class="mb-0 text-success small">Digitally Signed & QR Encrypted</p>
            </div>
            <div class="col-6 text-end">
                <img src="data:image/png;base64,{cert['qr_b64']}" alt="QR Code" style="width: 120px;">
                <div class="small text-muted">Scan or Upload to Verify</div>
            </div>
        </div>
    </div>
    <div class="text-center mt-3">
        <button onclick="window.print()" class="btn btn-outline-primary">🖨️ Print / Save PDF</button>
        <a href="data:image/png;base64,{cert['qr_b64']}" download="{cert['reg_no']}_QR.png" class="btn btn-outline-dark">⬇️ Download QR Image</a>
    </div>
    """
    return render_template_string(BASE_HTML, content=content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session['admin'] = True
            return redirect(url_for('admin'))
        flash("Invalid credentials", "danger")
    
    content = """
    <div class="row justify-content-center">
        <div class="col-md-4">
            <div class="card shadow-sm">
                <div class="card-header bg-primary text-white fw-bold">Administrator Login</div>
                <div class="card-body">
                    <form method="POST">
                        <div class="mb-3">
                            <label class="form-label">Username</label>
                            <input type="text" name="username" class="form-control" value="admin" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">Password</label>
                            <input type="password" name="password" class="form-control" value="admin123" required>
                        </div>
                        <button type="submit" class="btn btn-primary w-100">Login</button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, content=content)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_dept':
            cursor.execute("INSERT IGNORE INTO departments (dept_name) VALUES (%s)", (request.form['dept_name'],))
            conn.commit()
            flash("Department added!", "success")
        elif action == 'add_course':
            cursor.execute("INSERT INTO courses (dept_id, course_name) VALUES (%s, %s)", (request.form['dept_id'], request.form['course_name']))
            conn.commit()
            flash("Course added!", "success")
        elif action == 'generate_cert':
            reg_no = request.form['reg_no'].strip()
            student_name = request.form['student_name'].strip()
            dob = request.form['dob']
            dept_id = request.form['dept_id']
            course_id = request.form['course_id']
            
            photo_bytes = request.files['photo'].read()
            photo_b64 = base64.b64encode(photo_bytes).decode('utf-8')

            raw_payload = f"{reg_no}|{student_name}|{dob}".encode()
            encrypted_token = cipher.encrypt(raw_payload).decode()

            qr_img = qrcode.make(encrypted_token)
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            try:
                cursor.execute("""
                    INSERT INTO certificates (reg_no, student_name, dob, dept_id, course_id, photo_b64, encrypted_token, qr_b64)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (reg_no, student_name, dob, dept_id, course_id, photo_b64, encrypted_token, qr_b64))
                conn.commit()
                flash("Certificate generated!", "success")
                return redirect(url_for('view_certificate', reg_no=reg_no))
            except mysql.connector.Error as err:
                flash(f"Error: {err}", "danger")

    cursor.execute("SELECT * FROM departments")
    depts = cursor.fetchall()
    cursor.execute("SELECT c.*, d.dept_name FROM courses c JOIN departments d ON c.dept_id = d.dept_id")
    courses = cursor.fetchall()
    cursor.execute("SELECT c.*, co.course_name FROM certificates c JOIN courses co ON c.course_id = co.course_id ORDER BY c.cert_id DESC")
    certs = cursor.fetchall()
    cursor.close()
    conn.close()

    dept_options = "".join([f'<option value="{d["dept_id"]}">{d["dept_name"]}</option>' for d in depts])
    course_options = "".join([f'<option value="{c["course_id"]}">{c["course_name"]} ({c["dept_name"]})</option>' for c in courses])
    cert_rows = "".join([f"""
        <tr>
            <td>{c['reg_no']}</td>
            <td>{c['student_name']}</td>
            <td>{c['course_name']}</td>
            <td><a href="/certificate/{c['reg_no']}" class="btn btn-sm btn-info text-white">View / QR</a></td>
        </tr>
    """ for c in certs])

    content = f"""
    <div class="row g-4">
        <div class="col-md-7">
            <div class="card shadow-sm">
                <div class="card-header bg-primary text-white fw-bold">Issue New Digital Certificate</div>
                <div class="card-body">
                    <form method="POST" enctype="multipart/form-data">
                        <input type="hidden" name="action" value="generate_cert">
                        <div class="row g-2 mb-2">
                            <div class="col-md-6">
                                <label class="form-label">Registration No</label>
                                <input type="text" name="reg_no" class="form-control" required>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Student Name</label>
                                <input type="text" name="student_name" class="form-control" required>
                            </div>
                        </div>
                        <div class="row g-2 mb-2">
                            <div class="col-md-6">
                                <label class="form-label">Date of Birth</label>
                                <input type="date" name="dob" class="form-control" required>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Student Photo</label>
                                <input type="file" name="photo" class="form-control" accept="image/*" required>
                            </div>
                        </div>
                        <div class="row g-2 mb-3">
                            <div class="col-md-6">
                                <label class="form-label">Department</label>
                                <select name="dept_id" class="form-select" required>{dept_options}</select>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Course</label>
                                <select name="course_id" class="form-select" required>{course_options}</select>
                            </div>
                        </div>
                        <button type="submit" class="btn btn-success w-100">Generate Certificate & QR</button>
                    </form>
                </div>
            </div>
        </div>
        <div class="col-md-5">
            <div class="card shadow-sm mb-3">
                <div class="card-header bg-dark text-white fw-bold">Add Department</div>
                <div class="card-body">
                    <form method="POST" class="d-flex gap-2">
                        <input type="hidden" name="action" value="add_dept">
                        <input type="text" name="dept_name" class="form-control" placeholder="Department Name" required>
                        <button class="btn btn-primary">Add</button>
                    </form>
                </div>
            </div>
            <div class="card shadow-sm">
                <div class="card-header bg-dark text-white fw-bold">Add Course</div>
                <div class="card-body">
                    <form method="POST">
                        <input type="hidden" name="action" value="add_course">
                        <select name="dept_id" class="form-select mb-2" required>{dept_options}</select>
                        <div class="d-flex gap-2">
                            <input type="text" name="course_name" class="form-control" placeholder="Course Name" required>
                            <button class="btn btn-primary">Add</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        <div class="col-12">
            <div class="card shadow-sm">
                <div clas

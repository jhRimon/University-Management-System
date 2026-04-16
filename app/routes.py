from flask import Blueprint, redirect, render_template, request, url_for

from app.db import get_db_connection

bp = Blueprint("main", __name__)

THEORY_LIMITS = {
    "quiz": 15.0,
    "attendance": 10.0,
    "presentation": 10.0,
    "mid": 25.0,
    "final": 40.0,
}

LAB_LIMITS = {
    "lab_report": 30.0,
    "lab_eval": 20.0,
    "lab_final": 50.0,
}

DELETE_META = {
    "department": {
        "label": "Department",
        "list_endpoint": "main.departments",
        "summary_query": """
            SELECT dept_id AS id, dept_name AS title,
                   office_location AS subtitle,
                   CONCAT('Department ID #', dept_id) AS meta
            FROM department
            WHERE dept_id=%s
        """,
    },
    "faculty": {
        "label": "Faculty Member",
        "list_endpoint": "main.faculty",
        "summary_query": """
            SELECT faculty_id AS id, name AS title,
                   email AS subtitle,
                   CONCAT('Designation: ', designation) AS meta
            FROM faculty
            WHERE faculty_id=%s
        """,
    },
    "student": {
        "label": "Student",
        "list_endpoint": "main.students",
        "summary_query": """
            SELECT student_id AS id, name AS title,
                   email AS subtitle,
                   CONCAT('Registration: ', student_reg_no) AS meta
            FROM student
            WHERE student_id=%s
        """,
    },
    "course": {
        "label": "Course",
        "list_endpoint": "main.courses",
        "summary_query": """
            SELECT course_id AS id, course_name AS title,
                   course_code AS subtitle,
                   CONCAT('Type: ', course_type) AS meta
            FROM course
            WHERE course_id=%s
        """,
    },
    "section": {
        "label": "Section",
        "list_endpoint": "main.sections",
        "summary_query": """
            SELECT s.section_id AS id,
                   CONCAT(c.course_name, ' - Section ', s.section_name) AS title,
                   s.semester AS subtitle,
                   CONCAT('Faculty: ', COALESCE(f.name, 'Unassigned')) AS meta
            FROM section s
            LEFT JOIN course c ON s.course_id = c.course_id
            LEFT JOIN faculty f ON s.faculty_id = f.faculty_id
            WHERE s.section_id=%s
        """,
    },
    "enrollment": {
        "label": "Enrollment",
        "list_endpoint": "main.enrollments",
        "summary_query": """
            SELECT e.enrollment_id AS id,
                   CONCAT(s.name, ' enrolled in ', c.course_name) AS title,
                   sec.section_name AS subtitle,
                   CONCAT('Enrollment ID #', e.enrollment_id) AS meta
            FROM enrollment e
            LEFT JOIN student s ON e.student_id = s.student_id
            LEFT JOIN section sec ON e.section_id = sec.section_id
            LEFT JOIN course c ON sec.course_id = c.course_id
            WHERE e.enrollment_id=%s
        """,
    },
}


def redirect_with_status(endpoint, status, message, **values):
    values["status"] = status
    values["message"] = message
    return redirect(url_for(endpoint, **values))


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def validate_component_scores(form, limits):
    cleaned = {}
    for field, limit in limits.items():
        value = safe_float(form.get(field))
        if value < 0 or value > limit:
            raise ValueError(f"{field.replace('_', ' ').title()} must be between 0 and {limit:g}.")
        cleaned[field] = value
    return cleaned


def normalize_course_type(course_type):
    return "lab" if "lab" in (course_type or "").strip().lower() else "theory"


def calculate_grade(total):
    if total >= 90:
        return "A", 4.0
    if total >= 85:
        return "A-", 3.75
    if total >= 80:
        return "B+", 3.5
    if total >= 75:
        return "B", 3.0
    if total >= 70:
        return "B-", 2.75
    if total >= 65:
        return "C+", 2.5
    if total >= 60:
        return "C", 2.0
    if total >= 50:
        return "D", 1.0
    return "F", 0.0


def get_section_context(cursor, section_id):
    cursor.execute(
        """
        SELECT s.section_id, s.section_name, s.semester,
               c.course_id, c.course_name, c.course_code, c.course_type,
               f.faculty_id, f.name AS faculty_name,
               cl.room_number
        FROM section s
        LEFT JOIN course c ON s.course_id = c.course_id
        LEFT JOIN faculty f ON s.faculty_id = f.faculty_id
        LEFT JOIN classroom cl ON s.classroom_id = cl.classroom_id
        WHERE s.section_id=%s
        """,
        (section_id,),
    )
    return cursor.fetchone()


def get_filtered_enrollments(cursor, section_id=None, faculty_id=None):
    query = """
        SELECT e.enrollment_id, e.enroll_date,
               s.student_id, s.student_reg_no, s.name AS student_name, s.batch,
               sec.section_id, sec.section_name, sec.semester,
               c.course_name, c.course_code, c.course_type,
               f.faculty_id, f.name AS faculty_name
        FROM enrollment e
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN faculty f ON sec.faculty_id = f.faculty_id
        WHERE 1=1
    """
    params = []

    if section_id:
        query += " AND sec.section_id=%s"
        params.append(section_id)

    if faculty_id:
        query += " AND f.faculty_id=%s"
        params.append(faculty_id)

    query += " ORDER BY c.course_name, sec.section_name, s.name"
    cursor.execute(query, tuple(params))
    return cursor.fetchall()


def get_grade_ready_enrollments(cursor):
    cursor.execute(
        """
        SELECT e.enrollment_id,
               s.name AS student_name,
               s.student_reg_no,
               sec.section_name,
               sec.semester,
               c.course_name,
               c.course_type,
               tm.quiz_marks,
               tm.attendance_marks,
               tm.presentation_marks,
               tm.mid_marks,
               tm.final_marks,
               lm.lab_report_marks,
               lm.lab_evaluation_marks,
               lm.lab_final_marks,
               g.grade_id
        FROM enrollment e
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN theory_marks tm ON e.enrollment_id = tm.enrollment_id
        LEFT JOIN lab_marks lm ON e.enrollment_id = lm.enrollment_id
        LEFT JOIN grade g ON e.enrollment_id = g.enrollment_id
        ORDER BY c.course_name, s.name
        """
    )
    enrollments = cursor.fetchall()

    for row in enrollments:
        course_mode = normalize_course_type(row["course_type"])
        if course_mode == "lab":
            total = (
                safe_float(row.get("lab_report_marks"))
                + safe_float(row.get("lab_evaluation_marks"))
                + safe_float(row.get("lab_final_marks"))
            )
            row["grading_basis"] = "Lab"
            row["is_grade_ready"] = any(
                row.get(field) is not None
                for field in ("lab_report_marks", "lab_evaluation_marks", "lab_final_marks")
            )
        else:
            total = (
                safe_float(row.get("quiz_marks"))
                + safe_float(row.get("attendance_marks"))
                + safe_float(row.get("presentation_marks"))
                + safe_float(row.get("mid_marks"))
                + safe_float(row.get("final_marks"))
            )
            row["grading_basis"] = "Theory"
            row["is_grade_ready"] = any(
                row.get(field) is not None
                for field in (
                    "quiz_marks",
                    "attendance_marks",
                    "presentation_marks",
                    "mid_marks",
                    "final_marks",
                )
            )

        row["computed_total"] = round(total, 2)

    return enrollments


def calculate_grade_payload(cursor, enrollment_id):
    cursor.execute(
        """
        SELECT e.enrollment_id,
               s.name AS student_name,
               s.student_reg_no,
               sec.section_name,
               sec.semester,
               c.course_name,
               c.course_code,
               c.course_type,
               tm.quiz_marks,
               tm.attendance_marks,
               tm.presentation_marks,
               tm.mid_marks,
               tm.final_marks,
               lm.lab_report_marks,
               lm.lab_evaluation_marks,
               lm.lab_final_marks
        FROM enrollment e
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN theory_marks tm ON e.enrollment_id = tm.enrollment_id
        LEFT JOIN lab_marks lm ON e.enrollment_id = lm.enrollment_id
        WHERE e.enrollment_id=%s
        """,
        (enrollment_id,),
    )
    record = cursor.fetchone()

    if not record:
        return None, "Enrollment not found."

    course_mode = normalize_course_type(record["course_type"])

    if course_mode == "lab":
        scores = (
            record.get("lab_report_marks"),
            record.get("lab_evaluation_marks"),
            record.get("lab_final_marks"),
        )
        if not any(score is not None for score in scores):
            return None, "Lab marks are missing for this enrollment."
        total = sum(safe_float(score) for score in scores)
        breakdown = [
            ("Lab report", safe_float(record.get("lab_report_marks"))),
            ("Lab evaluation", safe_float(record.get("lab_evaluation_marks"))),
            ("Lab final", safe_float(record.get("lab_final_marks"))),
        ]
    else:
        scores = (
            record.get("quiz_marks"),
            record.get("attendance_marks"),
            record.get("presentation_marks"),
            record.get("mid_marks"),
            record.get("final_marks"),
        )
        if not any(score is not None for score in scores):
            return None, "Theory marks are missing for this enrollment."
        total = sum(safe_float(score) for score in scores)
        breakdown = [
            ("Quiz", safe_float(record.get("quiz_marks"))),
            ("Attendance", safe_float(record.get("attendance_marks"))),
            ("Presentation", safe_float(record.get("presentation_marks"))),
            ("Mid", safe_float(record.get("mid_marks"))),
            ("Final", safe_float(record.get("final_marks"))),
        ]

    letter_grade, grade_point = calculate_grade(total)
    record["computed_total"] = round(total, 2)
    record["letter_grade"] = letter_grade
    record["grade_point"] = grade_point
    record["grading_basis"] = "Lab" if course_mode == "lab" else "Theory"
    record["breakdown"] = breakdown
    return record, None


def build_transcript_rows(cursor, student_id=None):
    query = """
        SELECT e.enrollment_id,
               s.student_id,
               s.student_reg_no,
               s.name AS student_name,
               s.batch,
               sec.semester,
               sec.section_name,
               c.course_code,
               c.course_name,
               c.course_type,
               c.credit_hours,
               tm.quiz_marks,
               tm.attendance_marks,
               tm.presentation_marks,
               tm.mid_marks,
               tm.final_marks,
               lm.lab_report_marks,
               lm.lab_evaluation_marks,
               lm.lab_final_marks
        FROM enrollment e
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN theory_marks tm ON e.enrollment_id = tm.enrollment_id
        LEFT JOIN lab_marks lm ON e.enrollment_id = lm.enrollment_id
        WHERE 1=1
    """
    params = []
    if student_id:
        query += " AND s.student_id=%s"
        params.append(student_id)

    query += " ORDER BY s.name, sec.semester, c.course_code"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()

    for row in rows:
        course_mode = normalize_course_type(row["course_type"])
        if course_mode == "lab":
            total = (
                safe_float(row.get("lab_report_marks"))
                + safe_float(row.get("lab_evaluation_marks"))
                + safe_float(row.get("lab_final_marks"))
            )
            is_ready = any(
                row.get(field) is not None
                for field in ("lab_report_marks", "lab_evaluation_marks", "lab_final_marks")
            )
        else:
            total = (
                safe_float(row.get("quiz_marks"))
                + safe_float(row.get("attendance_marks"))
                + safe_float(row.get("presentation_marks"))
                + safe_float(row.get("mid_marks"))
                + safe_float(row.get("final_marks"))
            )
            is_ready = any(
                row.get(field) is not None
                for field in (
                    "quiz_marks",
                    "attendance_marks",
                    "presentation_marks",
                    "mid_marks",
                    "final_marks",
                )
            )

        row["computed_total"] = round(total, 2)
        row["is_grade_ready"] = is_ready
        if is_ready:
            letter_grade, grade_point = calculate_grade(total)
            row["computed_letter_grade"] = letter_grade
            row["computed_grade_point"] = grade_point
        else:
            row["computed_letter_grade"] = None
            row["computed_grade_point"] = None
    return rows


def build_student_transcript(cursor, student_id):
    transcript_rows = build_transcript_rows(cursor, student_id=student_id)
    if not transcript_rows:
        return None

    student = {
        "student_id": transcript_rows[0]["student_id"],
        "student_reg_no": transcript_rows[0]["student_reg_no"],
        "student_name": transcript_rows[0]["student_name"],
        "batch": transcript_rows[0]["batch"],
    }

    semesters = []
    current_semester = None
    cumulative_quality_points = 0.0
    cumulative_credits = 0.0

    for row in transcript_rows:
        if current_semester is None or current_semester["semester"] != row["semester"]:
            if current_semester is not None:
                if current_semester["earned_credits"] > 0:
                    current_semester["sgpa"] = round(
                        current_semester["quality_points"] / current_semester["earned_credits"], 2
                    )
                else:
                    current_semester["sgpa"] = None

                if cumulative_credits > 0:
                    current_semester["cgpa"] = round(cumulative_quality_points / cumulative_credits, 2)
                else:
                    current_semester["cgpa"] = None
                semesters.append(current_semester)

            current_semester = {
                "semester": row["semester"],
                "courses": [],
                "total_credits": 0.0,
                "earned_credits": 0.0,
                "quality_points": 0.0,
                "sgpa": None,
                "cgpa": None,
            }

        credit_hours = safe_float(row["credit_hours"])
        course_entry = {
            "course_code": row["course_code"],
            "course_name": row["course_name"],
            "course_type": row["course_type"],
            "section_name": row["section_name"],
            "credit_hours": credit_hours,
            "computed_total": row["computed_total"],
            "computed_letter_grade": row["computed_letter_grade"],
            "computed_grade_point": row["computed_grade_point"],
            "is_grade_ready": row["is_grade_ready"],
        }
        current_semester["courses"].append(course_entry)
        current_semester["total_credits"] += credit_hours

        if row["computed_grade_point"] is not None:
            quality_points = row["computed_grade_point"] * credit_hours
            current_semester["earned_credits"] += credit_hours
            current_semester["quality_points"] += quality_points
            cumulative_quality_points += quality_points
            cumulative_credits += credit_hours

    if current_semester is not None:
        if current_semester["earned_credits"] > 0:
            current_semester["sgpa"] = round(
                current_semester["quality_points"] / current_semester["earned_credits"], 2
            )
        if cumulative_credits > 0:
            current_semester["cgpa"] = round(cumulative_quality_points / cumulative_credits, 2)
        semesters.append(current_semester)

    overall = {
        "total_semesters": len(semesters),
        "registered_credits": round(sum(semester["total_credits"] for semester in semesters), 2),
        "earned_credits": round(cumulative_credits, 2),
        "cgpa": round(cumulative_quality_points / cumulative_credits, 2) if cumulative_credits > 0 else None,
    }

    return {
        "student": student,
        "semesters": semesters,
        "overall": overall,
    }


def get_delete_record(cursor, entity, record_id):
    meta = DELETE_META.get(entity)
    if not meta:
        return None
    cursor.execute(meta["summary_query"], (record_id,))
    return cursor.fetchone()


def get_delete_blocker(cursor, entity, record_id):
    if entity == "department":
        cursor.execute("SELECT 1 FROM faculty WHERE dept_id=%s LIMIT 1", (record_id,))
        if cursor.fetchone():
            return "This department still has faculty members assigned to it."
        cursor.execute("SELECT 1 FROM student WHERE dept_id=%s LIMIT 1", (record_id,))
        if cursor.fetchone():
            return "This department still has students assigned to it."
        cursor.execute("SELECT 1 FROM course WHERE dept_id=%s LIMIT 1", (record_id,))
        if cursor.fetchone():
            return "This department still has courses assigned to it."
        return None

    if entity == "faculty":
        cursor.execute("SELECT 1 FROM section WHERE faculty_id=%s LIMIT 1", (record_id,))
        if cursor.fetchone():
            return "This faculty member is still assigned to one or more sections."
        return None

    if entity == "student":
        cursor.execute("SELECT 1 FROM enrollment WHERE student_id=%s LIMIT 1", (record_id,))
        if cursor.fetchone():
            return "This student still has enrollment history."
        return None

    if entity == "course":
        cursor.execute("SELECT 1 FROM section WHERE course_id=%s LIMIT 1", (record_id,))
        if cursor.fetchone():
            return "This course is already being used in a section."
        return None

    if entity == "section":
        cursor.execute("SELECT 1 FROM enrollment WHERE section_id=%s LIMIT 1", (record_id,))
        if cursor.fetchone():
            return "This section still has enrolled students."
        return None

    if entity == "enrollment":
        related_tables = (
            ("attendance", "attendance records"),
            ("theory_marks", "theory marks"),
            ("lab_marks", "lab marks"),
            ("grade", "grade records"),
        )
        for table_name, label in related_tables:
            cursor.execute(
                f"SELECT 1 FROM {table_name} WHERE enrollment_id=%s LIMIT 1",
                (record_id,),
            )
            if cursor.fetchone():
                return f"This enrollment already has {label} linked to it."
        return None

    return "Unknown delete target."


def execute_delete(cursor, entity, record_id):
    if entity == "department":
        cursor.execute("DELETE FROM department WHERE dept_id=%s", (record_id,))
    elif entity == "faculty":
        cursor.execute("DELETE FROM faculty WHERE faculty_id=%s", (record_id,))
    elif entity == "student":
        cursor.execute("DELETE FROM student WHERE student_id=%s", (record_id,))
    elif entity == "course":
        cursor.execute("DELETE FROM course WHERE course_id=%s", (record_id,))
    elif entity == "section":
        cursor.execute("DELETE FROM section WHERE section_id=%s", (record_id,))
    elif entity == "enrollment":
        cursor.execute("DELETE FROM enrollment WHERE enrollment_id=%s", (record_id,))
    else:
        raise ValueError("Unsupported entity")


@bp.route("/")
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM department) AS departments,
            (SELECT COUNT(*) FROM faculty) AS faculty,
            (SELECT COUNT(*) FROM student) AS students,
            (SELECT COUNT(*) FROM course) AS courses,
            (SELECT COUNT(*) FROM section) AS sections,
            (SELECT COUNT(*) FROM enrollment) AS enrollments,
            (
                SELECT COUNT(*)
                FROM enrollment e
                LEFT JOIN grade g ON e.enrollment_id = g.enrollment_id
                WHERE g.grade_id IS NULL
            ) AS pending_grades
        """
    )
    stats = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("dashboard.html", stats=stats)


@bp.route("/teacher_portal")
def teacher_portal():
    faculty_id = request.args.get("faculty_id", type=int)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT faculty_id, name, designation FROM faculty ORDER BY name")
    faculty_members = cursor.fetchall()

    sections = []
    selected_faculty = None

    if faculty_id:
        cursor.execute(
            """
            SELECT f.faculty_id, f.name, f.designation, d.dept_name
            FROM faculty f
            LEFT JOIN department d ON f.dept_id = d.dept_id
            WHERE f.faculty_id=%s
            """,
            (faculty_id,),
        )
        selected_faculty = cursor.fetchone()

        cursor.execute(
            """
            SELECT s.section_id, s.section_name, s.semester,
                   c.course_name, c.course_code, c.course_type,
                   cl.room_number,
                   COUNT(e.enrollment_id) AS enrollment_count
            FROM section s
            LEFT JOIN course c ON s.course_id = c.course_id
            LEFT JOIN classroom cl ON s.classroom_id = cl.classroom_id
            LEFT JOIN enrollment e ON s.section_id = e.section_id
            WHERE s.faculty_id=%s
            GROUP BY s.section_id, s.section_name, s.semester,
                     c.course_name, c.course_code, c.course_type, cl.room_number
            ORDER BY s.semester DESC, c.course_name, s.section_name
            """,
            (faculty_id,),
        )
        sections = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "teacher_portal.html",
        faculty_members=faculty_members,
        selected_faculty=selected_faculty,
        sections=sections,
    )


@bp.route("/section_workspace/<int:section_id>")
def section_workspace(section_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    section = get_section_context(cursor, section_id)

    if not section:
        cursor.close()
        conn.close()
        return redirect_with_status("main.teacher_portal", "danger", "Section not found.")

    cursor.execute(
        """
        SELECT e.enrollment_id, e.enroll_date,
               s.student_reg_no, s.name AS student_name, s.batch,
               tm.quiz_marks, tm.attendance_marks, tm.presentation_marks,
               tm.mid_marks, tm.final_marks,
               lm.lab_report_marks, lm.lab_evaluation_marks, lm.lab_final_marks,
               g.total_marks, g.letter_grade, g.grade_point
        FROM enrollment e
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN theory_marks tm ON e.enrollment_id = tm.enrollment_id
        LEFT JOIN lab_marks lm ON e.enrollment_id = lm.enrollment_id
        LEFT JOIN grade g ON e.enrollment_id = g.enrollment_id
        WHERE e.section_id=%s
        ORDER BY s.name
        """,
        (section_id,),
    )
    roster = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("section_workspace.html", section=section, roster=roster)


@bp.route("/departments")
def departments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM department ORDER BY dept_name")
    departments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("departments.html", departments=departments)


@bp.route("/faculty")
def faculty():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT f.*, d.dept_name,
               COUNT(s.section_id) AS section_count
        FROM faculty f
        LEFT JOIN department d ON f.dept_id = d.dept_id
        LEFT JOIN section s ON f.faculty_id = s.faculty_id
        GROUP BY f.faculty_id, f.name, f.email, f.designation, f.dept_id, d.dept_name
        ORDER BY f.name
        """
    )
    faculty_members = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("faculty.html", faculty=faculty_members)


@bp.route("/add_faculty", methods=["GET", "POST"])
def add_faculty():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM department ORDER BY dept_name")
    departments = cursor.fetchall()

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        designation = request.form["designation"].strip()
        dept_id = request.form["dept_id"]

        cursor.execute("SELECT 1 FROM faculty WHERE email=%s LIMIT 1", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status("main.add_faculty", "danger", "A faculty member already uses that email.")

        cursor.execute(
            "INSERT INTO faculty (name, email, designation, dept_id) VALUES (%s, %s, %s, %s)",
            (name, email, designation, dept_id),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return redirect_with_status("main.faculty", "success", "Faculty member added successfully.")

    cursor.close()
    conn.close()
    return render_template("add_faculty.html", departments=departments)


@bp.route("/students")
def students():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT s.*, d.dept_name,
               COUNT(e.enrollment_id) AS enrollment_count
        FROM student s
        LEFT JOIN department d ON s.dept_id = d.dept_id
        LEFT JOIN enrollment e ON s.student_id = e.student_id
        GROUP BY s.student_id, s.student_reg_no, s.name, s.email, s.batch, s.dept_id, d.dept_name
        ORDER BY s.name
        """
    )
    student_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("students.html", students=student_rows)


@bp.route("/add_student", methods=["GET", "POST"])
def add_student():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM department ORDER BY dept_name")
    departments = cursor.fetchall()

    if request.method == "POST":
        student_reg_no = request.form["student_reg_no"].strip()
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        batch = request.form["batch"].strip()
        dept_id = request.form["dept_id"]

        cursor.execute("SELECT 1 FROM student WHERE student_reg_no=%s LIMIT 1", (student_reg_no,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status("main.add_student", "danger", "Student registration number already exists.")

        cursor.execute("SELECT 1 FROM student WHERE email=%s LIMIT 1", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status("main.add_student", "danger", "Student email already exists.")

        cursor.execute(
            """
            INSERT INTO student (student_reg_no, name, email, batch, dept_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (student_reg_no, name, email, batch, dept_id),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return redirect_with_status("main.students", "success", "Student added successfully.")

    cursor.close()
    conn.close()
    return render_template("add_student.html", departments=departments)


@bp.route("/courses")
def courses():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT c.*, d.dept_name,
               COUNT(s.section_id) AS section_count
        FROM course c
        LEFT JOIN department d ON c.dept_id = d.dept_id
        LEFT JOIN section s ON c.course_id = s.course_id
        GROUP BY c.course_id, c.course_code, c.course_name, c.credit_hours, c.course_type, c.dept_id, d.dept_name
        ORDER BY c.course_code
        """
    )
    course_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("courses.html", courses=course_rows)


@bp.route("/add_course", methods=["GET", "POST"])
def add_course():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM department ORDER BY dept_name")
    departments = cursor.fetchall()

    if request.method == "POST":
        code = request.form["course_code"].strip().upper()
        name = request.form["course_name"].strip()
        credit = request.form["credit_hours"].strip()
        course_type = request.form["course_type"].strip()
        dept_id = request.form["dept_id"]

        cursor.execute("SELECT 1 FROM course WHERE course_code=%s LIMIT 1", (code,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status("main.add_course", "danger", "Course code already exists.")

        cursor.execute(
            """
            INSERT INTO course (course_code, course_name, credit_hours, course_type, dept_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (code, name, credit, course_type, dept_id),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return redirect_with_status("main.courses", "success", "Course added successfully.")

    cursor.close()
    conn.close()
    return render_template("add_course.html", departments=departments)


@bp.route("/sections")
def sections():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT s.*, c.course_name, c.course_code, c.course_type,
               f.name AS faculty_name, cl.room_number,
               COUNT(e.enrollment_id) AS enrollment_count
        FROM section s
        LEFT JOIN course c ON s.course_id = c.course_id
        LEFT JOIN faculty f ON s.faculty_id = f.faculty_id
        LEFT JOIN classroom cl ON s.classroom_id = cl.classroom_id
        LEFT JOIN enrollment e ON s.section_id = e.section_id
        GROUP BY s.section_id, s.course_id, s.faculty_id, s.classroom_id,
                 s.section_name, s.semester,
                 c.course_name, c.course_code, c.course_type,
                 f.name, cl.room_number
        ORDER BY s.semester DESC, c.course_name, s.section_name
        """
    )
    section_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("sections.html", sections=section_rows)


@bp.route("/add_section", methods=["GET", "POST"])
def add_section():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM course ORDER BY course_code")
    courses = cursor.fetchall()
    cursor.execute("SELECT * FROM faculty ORDER BY name")
    faculty_members = cursor.fetchall()
    cursor.execute("SELECT * FROM classroom ORDER BY room_number")
    classrooms = cursor.fetchall()

    if request.method == "POST":
        course_id = request.form["course_id"]
        faculty_id = request.form["faculty_id"]
        classroom_id = request.form["classroom_id"]
        section_name = request.form["section_name"].strip().upper()
        semester = request.form["semester"].strip()

        cursor.execute(
            """
            SELECT 1
            FROM section
            WHERE course_id=%s AND section_name=%s AND semester=%s
            LIMIT 1
            """,
            (course_id, section_name, semester),
        )
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status("main.add_section", "danger", "That section already exists for the semester.")

        cursor.execute(
            """
            INSERT INTO section (course_id, faculty_id, classroom_id, section_name, semester)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (course_id, faculty_id, classroom_id, section_name, semester),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return redirect_with_status("main.sections", "success", "Section created successfully.")

    cursor.close()
    conn.close()
    return render_template(
        "add_section.html",
        courses=courses,
        faculty=faculty_members,
        classrooms=classrooms,
    )


@bp.route("/enrollments")
def enrollments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT e.*, s.student_reg_no, s.name AS student_name, s.batch,
               c.course_name, c.course_code, sec.section_name, sec.semester,
               f.name AS faculty_name
        FROM enrollment e
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN faculty f ON sec.faculty_id = f.faculty_id
        ORDER BY e.enroll_date DESC, c.course_name, s.name
        """
    )
    enrollment_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("enrollments.html", enrollments=enrollment_rows)


@bp.route("/add_enrollment", methods=["GET", "POST"])
def add_enrollment():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT s.student_id, s.student_reg_no, s.name, s.batch, d.dept_name
        FROM student s
        LEFT JOIN department d ON s.dept_id = d.dept_id
        ORDER BY s.name
        """
    )
    students = cursor.fetchall()

    cursor.execute(
        """
        SELECT sec.section_id, sec.section_name, sec.semester,
               c.course_name, c.course_code, c.course_type,
               f.name AS faculty_name, cl.room_number
        FROM section sec
        LEFT JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN faculty f ON sec.faculty_id = f.faculty_id
        LEFT JOIN classroom cl ON sec.classroom_id = cl.classroom_id
        ORDER BY sec.semester DESC, c.course_name, sec.section_name
        """
    )
    sections = cursor.fetchall()

    if request.method == "POST":
        student_id = request.form["student_id"]
        section_id = request.form["section_id"]

        cursor.execute(
            """
            SELECT 1
            FROM enrollment
            WHERE student_id=%s AND section_id=%s
            LIMIT 1
            """,
            (student_id, section_id),
        )
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status("main.add_enrollment", "danger", "Student is already enrolled in this section.")

        cursor.execute(
            """
            SELECT sec.course_id, sec.semester
            FROM section sec
            WHERE sec.section_id=%s
            """,
            (section_id,),
        )
        target_section = cursor.fetchone()

        cursor.execute(
            """
            SELECT 1
            FROM enrollment e
            LEFT JOIN section sec ON e.section_id = sec.section_id
            WHERE e.student_id=%s AND sec.course_id=%s AND sec.semester=%s
            LIMIT 1
            """,
            (student_id, target_section["course_id"], target_section["semester"]),
        )
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status(
                "main.add_enrollment",
                "danger",
                "Student is already enrolled in this course for the selected semester.",
            )

        cursor.execute(
            """
            INSERT INTO enrollment (student_id, section_id, enroll_date)
            VALUES (%s, %s, NOW())
            """,
            (student_id, section_id),
        )
        conn.commit()

        cursor.close()
        conn.close()
        return redirect_with_status("main.enrollments", "success", "Enrollment completed successfully.")

    cursor.close()
    conn.close()
    return render_template("add_enrollment.html", students=students, sections=sections)


@bp.route("/attendance")
def attendance():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT a.*, s.student_reg_no, s.name AS student_name,
               c.course_name, sec.section_name, sec.semester,
               f.name AS faculty_name
        FROM attendance a
        LEFT JOIN enrollment e ON a.enrollment_id = e.enrollment_id
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN faculty f ON sec.faculty_id = f.faculty_id
        ORDER BY a.class_date DESC, c.course_name, s.name
        """
    )
    attendance_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("attendance.html", attendance=attendance_rows)


@bp.route("/add_attendance", methods=["GET", "POST"])
def add_attendance():
    section_id = request.args.get("section_id", type=int)
    faculty_id = request.args.get("faculty_id", type=int)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    faculty_members = []
    selected_faculty = None
    selected_section = None

    if faculty_id:
        cursor.execute("SELECT faculty_id, name FROM faculty WHERE faculty_id=%s", (faculty_id,))
        selected_faculty = cursor.fetchone()

    cursor.execute("SELECT faculty_id, name FROM faculty ORDER BY name")
    faculty_members = cursor.fetchall()

    if section_id:
        selected_section = get_section_context(cursor, section_id)

    enrollments = get_filtered_enrollments(cursor, section_id=section_id, faculty_id=faculty_id)

    if request.method == "POST":
        enrollment_id = request.form["enrollment_id"]
        class_date = request.form["class_date"]
        status = request.form["status"]

        cursor.execute(
            """
            SELECT 1
            FROM attendance
            WHERE enrollment_id=%s AND class_date=%s
            LIMIT 1
            """,
            (enrollment_id, class_date),
        )

        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE attendance
                SET status=%s
                WHERE enrollment_id=%s AND class_date=%s
                """,
                (status, enrollment_id, class_date),
            )
            message = "Attendance updated successfully."
        else:
            cursor.execute(
                """
                INSERT INTO attendance (enrollment_id, class_date, status)
                VALUES (%s, %s, %s)
                """,
                (enrollment_id, class_date, status),
            )
            message = "Attendance recorded successfully."

        conn.commit()
        cursor.close()
        conn.close()
        return redirect_with_status(
            "main.add_attendance",
            "success",
            message,
            section_id=section_id,
            faculty_id=faculty_id,
        )

    cursor.close()
    conn.close()
    return render_template(
        "add_attendance.html",
        enrollments=enrollments,
        faculty_members=faculty_members,
        selected_faculty=selected_faculty,
        selected_section=selected_section,
    )


@bp.route("/theory_marks")
def theory_marks():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT tm.*, s.student_reg_no, s.name AS student_name,
               c.course_name, sec.section_name, sec.semester,
               (COALESCE(tm.quiz_marks, 0) + COALESCE(tm.attendance_marks, 0) +
                COALESCE(tm.presentation_marks, 0) + COALESCE(tm.mid_marks, 0) +
                COALESCE(tm.final_marks, 0)) AS total_marks
        FROM theory_marks tm
        LEFT JOIN enrollment e ON tm.enrollment_id = e.enrollment_id
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        ORDER BY c.course_name, s.name
        """
    )
    marks = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("theory_marks.html", marks=marks)


@bp.route("/lab_marks")
def lab_marks():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT lm.*, s.student_reg_no, s.name AS student_name,
               c.course_name, sec.section_name, sec.semester,
               (COALESCE(lm.lab_report_marks, 0) + COALESCE(lm.lab_evaluation_marks, 0) +
                COALESCE(lm.lab_final_marks, 0)) AS total_marks
        FROM lab_marks lm
        LEFT JOIN enrollment e ON lm.enrollment_id = e.enrollment_id
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        ORDER BY c.course_name, s.name
        """
    )
    marks = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("lab_marks.html", marks=marks)


@bp.route("/add_theory_marks", methods=["GET", "POST"])
def add_theory_marks():
    section_id = request.args.get("section_id", type=int)
    faculty_id = request.args.get("faculty_id", type=int)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            scores = validate_component_scores(request.form, THEORY_LIMITS)
        except ValueError as exc:
            cursor.close()
            conn.close()
            return redirect_with_status(
                "main.add_theory_marks",
                "danger",
                str(exc),
                section_id=section_id,
                faculty_id=faculty_id,
            )

        enrollment_id = request.form["enrollment_id"]

        cursor.execute(
            "SELECT 1 FROM theory_marks WHERE enrollment_id=%s LIMIT 1",
            (enrollment_id,),
        )

        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE theory_marks
                SET quiz_marks=%s, attendance_marks=%s, presentation_marks=%s,
                    mid_marks=%s, final_marks=%s
                WHERE enrollment_id=%s
                """,
                (
                    scores["quiz"],
                    scores["attendance"],
                    scores["presentation"],
                    scores["mid"],
                    scores["final"],
                    enrollment_id,
                ),
            )
            message = "Theory marks updated successfully."
        else:
            cursor.execute(
                """
                INSERT INTO theory_marks
                (enrollment_id, quiz_marks, attendance_marks, presentation_marks, mid_marks, final_marks)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    enrollment_id,
                    scores["quiz"],
                    scores["attendance"],
                    scores["presentation"],
                    scores["mid"],
                    scores["final"],
                ),
            )
            message = "Theory marks saved successfully."

        conn.commit()
        cursor.close()
        conn.close()
        return redirect_with_status(
            "main.add_theory_marks",
            "success",
            message,
            section_id=section_id,
            faculty_id=faculty_id,
        )

    selected_section = get_section_context(cursor, section_id) if section_id else None
    enrollments = get_filtered_enrollments(cursor, section_id=section_id, faculty_id=faculty_id)

    cursor.close()
    conn.close()
    return render_template(
        "add_theory_marks.html",
        enrollments=enrollments,
        selected_section=selected_section,
        limits=THEORY_LIMITS,
        faculty_id=faculty_id,
    )


@bp.route("/add_lab_marks", methods=["GET", "POST"])
def add_lab_marks():
    section_id = request.args.get("section_id", type=int)
    faculty_id = request.args.get("faculty_id", type=int)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        try:
            scores = validate_component_scores(request.form, LAB_LIMITS)
        except ValueError as exc:
            cursor.close()
            conn.close()
            return redirect_with_status(
                "main.add_lab_marks",
                "danger",
                str(exc),
                section_id=section_id,
                faculty_id=faculty_id,
            )

        enrollment_id = request.form["enrollment_id"]

        cursor.execute(
            "SELECT 1 FROM lab_marks WHERE enrollment_id=%s LIMIT 1",
            (enrollment_id,),
        )

        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE lab_marks
                SET lab_report_marks=%s, lab_evaluation_marks=%s, lab_final_marks=%s
                WHERE enrollment_id=%s
                """,
                (
                    scores["lab_report"],
                    scores["lab_eval"],
                    scores["lab_final"],
                    enrollment_id,
                ),
            )
            message = "Lab marks updated successfully."
        else:
            cursor.execute(
                """
                INSERT INTO lab_marks
                (enrollment_id, lab_report_marks, lab_evaluation_marks, lab_final_marks)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    enrollment_id,
                    scores["lab_report"],
                    scores["lab_eval"],
                    scores["lab_final"],
                ),
            )
            message = "Lab marks saved successfully."

        conn.commit()
        cursor.close()
        conn.close()
        return redirect_with_status(
            "main.add_lab_marks",
            "success",
            message,
            section_id=section_id,
            faculty_id=faculty_id,
        )

    selected_section = get_section_context(cursor, section_id) if section_id else None
    enrollments = get_filtered_enrollments(cursor, section_id=section_id, faculty_id=faculty_id)

    cursor.close()
    conn.close()
    return render_template(
        "add_lab_marks.html",
        enrollments=enrollments,
        selected_section=selected_section,
        limits=LAB_LIMITS,
        faculty_id=faculty_id,
    )


@bp.route("/add_department", methods=["GET", "POST"])
def add_department():
    if request.method == "POST":
        name = request.form["dept_name"].strip()
        location = request.form["office_location"].strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM department WHERE dept_name=%s LIMIT 1", (name,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return redirect_with_status("main.add_department", "danger", "Department name already exists.")

        cursor.execute(
            "INSERT INTO department (dept_name, office_location) VALUES (%s, %s)",
            (name, location),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return redirect_with_status("main.departments", "success", "Department added successfully.")

    return render_template("add_department.html")


@bp.route("/grades")
def grades():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT g.*, s.student_reg_no, s.name AS student_name,
               c.course_name, c.course_type,
               sec.section_name, sec.semester
        FROM grade g
        LEFT JOIN enrollment e ON g.enrollment_id = e.enrollment_id
        LEFT JOIN student s ON e.student_id = s.student_id
        LEFT JOIN section sec ON e.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        ORDER BY sec.semester DESC, c.course_name, s.name
        """
    )
    grade_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("grades.html", grades=grade_rows)


@bp.route("/student_transcript")
def student_transcript():
    student_id = request.args.get("student_id", type=int)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT student_id, student_reg_no, name, batch
        FROM student
        ORDER BY name
        """
    )
    students = cursor.fetchall()

    transcript = build_student_transcript(cursor, student_id) if student_id else None

    cursor.close()
    conn.close()

    return render_template(
        "student_transcript.html",
        students=students,
        selected_student_id=student_id,
        transcript=transcript,
    )


@bp.route("/generate_grade", methods=["GET", "POST"])
def generate_grade():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        enrollment_id = request.form["enrollment_id"]
        payload, error_message = calculate_grade_payload(cursor, enrollment_id)

        if error_message:
            cursor.close()
            conn.close()
            return redirect_with_status("main.generate_grade", "danger", error_message)

        cursor.execute(
            "SELECT 1 FROM grade WHERE enrollment_id=%s LIMIT 1",
            (enrollment_id,),
        )

        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE grade
                SET total_marks=%s, letter_grade=%s, grade_point=%s
                WHERE enrollment_id=%s
                """,
                (
                    payload["computed_total"],
                    payload["letter_grade"],
                    payload["grade_point"],
                    enrollment_id,
                ),
            )
            message = "Grade recalculated successfully."
        else:
            cursor.execute(
                """
                INSERT INTO grade (enrollment_id, total_marks, letter_grade, grade_point)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    enrollment_id,
                    payload["computed_total"],
                    payload["letter_grade"],
                    payload["grade_point"],
                ),
            )
            message = "Grade generated successfully."

        conn.commit()
        cursor.close()
        conn.close()
        return redirect_with_status("main.grades", "success", message)

    grade_candidates = get_grade_ready_enrollments(cursor)

    cursor.close()
    conn.close()

    return render_template("generate_grade.html", marks=grade_candidates)


@bp.route("/confirm_delete/<entity>/<int:record_id>")
def confirm_delete(entity, record_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    record = get_delete_record(cursor, entity, record_id)

    if not record:
        cursor.close()
        conn.close()
        return redirect_with_status("main.dashboard", "danger", "Requested record was not found.")

    blocker = get_delete_blocker(cursor, entity, record_id)
    meta = DELETE_META[entity]

    cursor.close()
    conn.close()

    return render_template(
        "confirm_delete.html",
        entity=entity,
        label=meta["label"],
        record=record,
        blocker=blocker,
        list_endpoint=meta["list_endpoint"],
    )


@bp.route("/delete/<entity>/<int:record_id>", methods=["POST"])
def delete_record(entity, record_id):
    meta = DELETE_META.get(entity)
    if not meta:
        return redirect_with_status("main.dashboard", "danger", "Unsupported delete request.")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    record = get_delete_record(cursor, entity, record_id)
    if not record:
        cursor.close()
        conn.close()
        return redirect_with_status(meta["list_endpoint"], "danger", "Record not found.")

    blocker = get_delete_blocker(cursor, entity, record_id)
    if blocker:
        cursor.close()
        conn.close()
        return redirect_with_status(meta["list_endpoint"], "danger", blocker)

    execute_delete(cursor, entity, record_id)
    conn.commit()

    cursor.close()
    conn.close()
    return redirect_with_status(meta["list_endpoint"], "success", f"{meta['label']} deleted successfully.")

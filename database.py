import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path


DB_PATH = Path(
    os.environ.get(
        "MACROSNAP_DB_PATH",
        Path(__file__).with_name("macrosnap.db"),
    )
)

MEAL_SLOT_DEFAULTS = {
    "breakfast": {"label": "Breakfast", "enabled": True},
    "morning_snack": {"label": "Morning snack", "enabled": False},
    "lunch": {"label": "Lunch", "enabled": True},
    "evening_snack": {"label": "Evening snack", "enabled": False},
    "dinner": {"label": "Dinner", "enabled": True},
}


@contextmanager
def connection(database_path=DB_PATH):
    database = sqlite3.connect(database_path, timeout=10)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")

    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def init_db(database_path=DB_PATH):
    with connection(database_path) as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                email TEXT,
                name TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                height_cm REAL,
                weight_kg REAL,
                starting_weight_kg REAL,
                target_weight_kg REAL,
                activity_level TEXT,
                goal TEXT,
                calorie_goal INTEGER,
                protein_goal REAL,
                carb_goal REAL,
                fat_goal REAL,
                water_goal_ml INTEGER,
                food_preferences TEXT NOT NULL DEFAULT '',
                dietary_preference TEXT NOT NULL DEFAULT 'Flexible',
                foods_to_avoid TEXT NOT NULL DEFAULT '',
                wake_time TEXT NOT NULL DEFAULT '07:00',
                sleep_time TEXT NOT NULL DEFAULT '23:00',
                daily_schedule TEXT NOT NULL DEFAULT '',
                reminders_enabled INTEGER NOT NULL DEFAULT 0,
                fitness_goal TEXT NOT NULL DEFAULT 'Improve fitness',
                body_goal TEXT NOT NULL DEFAULT 'Improve overall body shape',
                fitness_experience TEXT NOT NULL DEFAULT 'Beginner',
                exercise_location TEXT NOT NULL DEFAULT 'Home',
                exercise_equipment TEXT NOT NULL DEFAULT '[]',
                available_workout_minutes INTEGER NOT NULL DEFAULT 20,
                exercise_preferences TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                meal_name TEXT NOT NULL,
                food_items TEXT NOT NULL DEFAULT '[]',
                calories REAL NOT NULL DEFAULT 0,
                protein_g REAL NOT NULL DEFAULT 0,
                carbs_g REAL NOT NULL DEFAULT 0,
                fat_g REAL NOT NULL DEFAULT 0,
                nutrition_notes TEXT NOT NULL DEFAULT '',
                alternatives TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL,
                nutrition_score INTEGER NOT NULL DEFAULT 0,
                score_categories TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS meals_user_created_idx
                ON meals(user_phone, created_at);

            CREATE TABLE IF NOT EXISTS daily_water (
                user_phone TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                day TEXT NOT NULL,
                intake_ml INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_phone, day)
            );

            CREATE TABLE IF NOT EXISTS weight_history (
                user_phone TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                recorded_on TEXT NOT NULL,
                weight_kg REAL NOT NULL,
                PRIMARY KEY (user_phone, recorded_on)
            );

            CREATE TABLE IF NOT EXISTS meal_plans (
                user_phone TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                plan_date TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                target_calories INTEGER NOT NULL DEFAULT 0,
                total_calories REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_phone, plan_date)
            );

            CREATE TABLE IF NOT EXISTS meal_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                meal_type TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                food_plan TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                last_sent_date TEXT,
                plan_date TEXT,
                claim_until TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (user_id, meal_type)
            );

            CREATE INDEX IF NOT EXISTS meal_reminders_due_idx
                ON meal_reminders(enabled, plan_date, scheduled_time, last_sent_date);

            CREATE TABLE IF NOT EXISTS body_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                measurement_date TEXT NOT NULL,
                weight_kg REAL,
                waist_cm REAL,
                hip_cm REAL,
                chest_cm REAL,
                arm_cm REAL,
                thigh_cm REAL,
                updated_at TEXT NOT NULL,
                UNIQUE (user_phone, measurement_date)
            );

            CREATE TABLE IF NOT EXISTS workout_plans (
                user_phone TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                week_start TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_phone, week_start)
            );

            CREATE TABLE IF NOT EXISTS workout_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT NOT NULL REFERENCES users(phone) ON DELETE CASCADE,
                workout_date TEXT NOT NULL,
                exercise_key TEXT NOT NULL,
                exercise_name TEXT NOT NULL,
                sets_completed INTEGER NOT NULL DEFAULT 0,
                reps_completed INTEGER NOT NULL DEFAULT 0,
                duration_minutes REAL NOT NULL DEFAULT 0,
                difficulty TEXT NOT NULL DEFAULT 'Beginner',
                completed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE (user_phone, workout_date, exercise_key)
            );

            CREATE TABLE IF NOT EXISTS workout_reminders (
                user_phone TEXT PRIMARY KEY REFERENCES users(phone) ON DELETE CASCADE,
                enabled INTEGER NOT NULL DEFAULT 0,
                scheduled_time TEXT NOT NULL DEFAULT '18:00',
                focus TEXT NOT NULL DEFAULT 'Full body',
                duration_minutes INTEGER NOT NULL DEFAULT 20,
                last_sent_date TEXT,
                claim_until TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_summary_reminders (
                user_phone TEXT PRIMARY KEY REFERENCES users(phone) ON DELETE CASCADE,
                enabled INTEGER NOT NULL DEFAULT 0,
                scheduled_time TEXT NOT NULL DEFAULT '20:00',
                last_sent_date TEXT,
                claim_until TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )

        user_columns = {
            row["name"]
            for row in database.execute("PRAGMA table_info(users)").fetchall()
        }
        migrations = {
            "email": "TEXT",
            "phone_verified": "INTEGER NOT NULL DEFAULT 0",
            "email_verified": "INTEGER NOT NULL DEFAULT 0",
            "preferred_otp_method": "TEXT NOT NULL DEFAULT 'whatsapp'",
            "last_login": "TEXT",
            "dietary_preference": "TEXT NOT NULL DEFAULT 'Flexible'",
            "foods_to_avoid": "TEXT NOT NULL DEFAULT ''",
            "wake_time": "TEXT NOT NULL DEFAULT '07:00'",
            "sleep_time": "TEXT NOT NULL DEFAULT '23:00'",
            "daily_schedule": "TEXT NOT NULL DEFAULT ''",
            "reminders_enabled": "INTEGER NOT NULL DEFAULT 0",
            "fitness_goal": "TEXT NOT NULL DEFAULT 'Improve fitness'",
            "body_goal": "TEXT NOT NULL DEFAULT 'Improve overall body shape'",
            "fitness_experience": "TEXT NOT NULL DEFAULT 'Beginner'",
            "exercise_location": "TEXT NOT NULL DEFAULT 'Home'",
            "exercise_equipment": "TEXT NOT NULL DEFAULT '[]'",
            "available_workout_minutes": "INTEGER NOT NULL DEFAULT 20",
            "exercise_preferences": "TEXT NOT NULL DEFAULT ''",
        }
        for column, declaration in migrations.items():
            if column not in user_columns:
                database.execute(
                    f"ALTER TABLE users ADD COLUMN {column} {declaration}"
                )


def get_user(phone, database_path=DB_PATH):
    with connection(database_path) as database:
        row = database.execute(
            "SELECT * FROM users WHERE phone = ?",
            (phone,)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_phone_or_email(phone=None, email=None, database_path=DB_PATH):
    if not phone and not email:
        return None
    with connection(database_path) as database:
        if phone:
            row = database.execute(
                "SELECT * FROM users WHERE phone = ? OR email = ? LIMIT 1",
                (phone, phone),
            ).fetchone()
            if row:
                return dict(row)
        if email:
            row = database.execute(
                "SELECT * FROM users WHERE email = ? OR phone = ? LIMIT 1",
                (email, email),
            ).fetchone()
            if row:
                return dict(row)
    return None


def save_user(phone, profile, database_path=DB_PATH, email=None):
    fields = (
        "name", "age", "gender", "height_cm", "weight_kg",
        "starting_weight_kg", "target_weight_kg", "activity_level", "goal",
        "calorie_goal", "protein_goal", "carb_goal", "fat_goal",
        "water_goal_ml", "food_preferences", "dietary_preference",
        "foods_to_avoid", "wake_time", "sleep_time", "daily_schedule",
        "reminders_enabled", "fitness_goal", "body_goal",
        "fitness_experience", "exercise_location", "exercise_equipment",
        "available_workout_minutes", "exercise_preferences",
    )
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    values = [profile.get(field) for field in fields]
    defaults = {
        "food_preferences": "",
        "dietary_preference": "Flexible",
        "foods_to_avoid": "",
        "wake_time": "07:00",
        "sleep_time": "23:00",
        "daily_schedule": "",
        "reminders_enabled": 0,
        "fitness_goal": "Improve fitness",
        "body_goal": "Improve overall body shape",
        "fitness_experience": "Beginner",
        "exercise_location": "Home",
        "exercise_equipment": "[]",
        "available_workout_minutes": 20,
        "exercise_preferences": "",
    }
    equipment_index = fields.index("exercise_equipment")
    if isinstance(values[equipment_index], (list, tuple)):
        values[equipment_index] = json.dumps(values[equipment_index])
    values = [
        value if value is not None else defaults.get(field)
        for field, value in zip(fields, values)
    ]
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(
        f"{field} = excluded.{field}"
        for field in fields
    )

    with connection(database_path) as database:
        email_value = email or profile.get("email")
        if email_value:
            database.execute(
                "UPDATE users SET email = ? WHERE phone = ?",
                (email_value, phone),
            )
        database.execute(
            f"""
            INSERT INTO users (phone, email, {columns}, created_at, updated_at)
            VALUES (?, ?, {placeholders}, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
                email = excluded.email,
                {updates}, updated_at = excluded.updated_at
            """,
            (phone, email_value, *values, now, now)
        )

    return get_user(phone, database_path)


def save_meal(phone, meal, database_path=DB_PATH):
    created_at = meal.get("created_at") or datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    with connection(database_path) as database:
        cursor = database.execute(
            """
            INSERT INTO meals (
                user_phone, created_at, meal_name, food_items, calories,
                protein_g, carbs_g, fat_g, nutrition_notes, alternatives,
                source, nutrition_score, score_categories
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                phone,
                created_at,
                meal.get("meal_name") or "Meal",
                json.dumps(meal.get("food_items", [])),
                float(meal.get("calories", 0)),
                float(meal.get("protein_g", 0)),
                float(meal.get("carbs_g", 0)),
                float(meal.get("fat_g", 0)),
                meal.get("nutrition_notes", ""),
                json.dumps(meal.get("alternatives", [])),
                meal.get("source", "text"),
                int(meal.get("nutrition_score", 0)),
                json.dumps(meal.get("score_categories", {}))
            )
        )
        return cursor.lastrowid


def get_meals(phone, start_date=None, end_date=None, limit=100, database_path=DB_PATH):
    clauses = ["user_phone = ?"]
    parameters = [phone]

    if start_date is not None:
        clauses.append("substr(created_at, 1, 10) >= ?")
        parameters.append(start_date.isoformat())

    if end_date is not None:
        clauses.append("substr(created_at, 1, 10) <= ?")
        parameters.append(end_date.isoformat())

    query = (
        "SELECT * FROM meals WHERE "
        + " AND ".join(clauses)
        + " ORDER BY created_at DESC"
    )
    if limit is not None:
        query += " LIMIT ?"
        parameters.append(int(limit))

    with connection(database_path) as database:
        rows = database.execute(query, parameters).fetchall()

    meals = []
    for row in rows:
        meal = dict(row)
        for field in ("food_items", "alternatives", "score_categories"):
            meal[field] = json.loads(meal[field] or "{}")
        meals.append(meal)
    return meals


def get_daily_totals(phone, day=None, database_path=DB_PATH):
    selected_day = day or date.today()
    with connection(database_path) as database:
        row = database.execute(
            """
            SELECT COUNT(*) AS meal_count,
                   COALESCE(SUM(calories), 0) AS calories,
                   COALESCE(SUM(protein_g), 0) AS protein_g,
                   COALESCE(SUM(carbs_g), 0) AS carbs_g,
                   COALESCE(SUM(fat_g), 0) AS fat_g
            FROM meals
            WHERE user_phone = ? AND substr(created_at, 1, 10) = ?
            """,
            (phone, selected_day.isoformat())
        ).fetchone()
    return dict(row)


def get_weekly_totals(phone, start_date, end_date, database_path=DB_PATH):
    with connection(database_path) as database:
        rows = database.execute(
            """
            SELECT substr(created_at, 1, 10) AS day,
                   COALESCE(SUM(calories), 0) AS calories,
                   COALESCE(SUM(protein_g), 0) AS protein_g,
                   COALESCE(SUM(carbs_g), 0) AS carbs_g,
                   COALESCE(SUM(fat_g), 0) AS fat_g
            FROM meals
            WHERE user_phone = ?
              AND substr(created_at, 1, 10) BETWEEN ? AND ?
            GROUP BY substr(created_at, 1, 10)
            ORDER BY day
            """,
            (phone, start_date.isoformat(), end_date.isoformat())
        ).fetchall()
    return {row["day"]: dict(row) for row in rows}


def get_water(phone, day=None, database_path=DB_PATH):
    selected_day = (day or date.today()).isoformat()
    with connection(database_path) as database:
        row = database.execute(
            "SELECT intake_ml FROM daily_water WHERE user_phone = ? AND day = ?",
            (phone, selected_day)
        ).fetchone()
    return int(row["intake_ml"]) if row else 0


def add_water(phone, amount_ml, day=None, database_path=DB_PATH):
    if amount_ml <= 0:
        raise ValueError("Water amount must be positive.")

    selected_day = (day or date.today()).isoformat()
    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO daily_water (user_phone, day, intake_ml)
            VALUES (?, ?, ?)
            ON CONFLICT(user_phone, day) DO UPDATE SET
                intake_ml = daily_water.intake_ml + excluded.intake_ml
            """,
            (phone, selected_day, int(amount_ml))
        )
    return get_water(phone, day, database_path)


def reset_water(phone, day=None, database_path=DB_PATH):
    selected_day = (day or date.today()).isoformat()
    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO daily_water (user_phone, day, intake_ml)
            VALUES (?, ?, 0)
            ON CONFLICT(user_phone, day) DO UPDATE SET intake_ml = 0
            """,
            (phone, selected_day)
        )


def record_weight(phone, weight_kg, recorded_on=None, database_path=DB_PATH):
    if weight_kg <= 0:
        raise ValueError("Weight must be positive.")

    selected_day = (recorded_on or date.today()).isoformat()
    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO weight_history (user_phone, recorded_on, weight_kg)
            VALUES (?, ?, ?)
            ON CONFLICT(user_phone, recorded_on) DO UPDATE SET
                weight_kg = excluded.weight_kg
            """,
            (phone, selected_day, float(weight_kg))
        )


def get_weight_history(phone, start_date=None, database_path=DB_PATH):
    query = (
        "SELECT recorded_on, weight_kg FROM weight_history "
        "WHERE user_phone = ?"
    )
    parameters = [phone]
    if start_date is not None:
        query += " AND recorded_on >= ?"
        parameters.append(start_date.isoformat())
    query += " ORDER BY recorded_on"

    with connection(database_path) as database:
        rows = database.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_reminder_settings(phone, database_path=DB_PATH):
    with connection(database_path) as database:
        rows = database.execute(
            "SELECT * FROM meal_reminders WHERE user_id = ? ORDER BY id",
            (phone,),
        ).fetchall()
    return {row["meal_type"]: dict(row) for row in rows}


def save_reminder_settings(phone, settings, database_path=DB_PATH):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with connection(database_path) as database:
        for meal_type, setting in settings.items():
            if meal_type not in MEAL_SLOT_DEFAULTS:
                raise ValueError("Unknown meal reminder type.")
            scheduled_time = str(setting["scheduled_time"])
            if len(scheduled_time) != 5 or scheduled_time[2] != ":":
                raise ValueError("Reminder times must use HH:MM format.")
            database.execute(
                """
                INSERT INTO meal_reminders (
                    user_id, meal_type, scheduled_time, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, meal_type) DO UPDATE SET
                    scheduled_time = excluded.scheduled_time,
                    enabled = excluded.enabled
                """,
                (
                    phone,
                    meal_type,
                    scheduled_time,
                    int(bool(setting["enabled"])),
                    now,
                ),
            )

        plan_row = database.execute(
            "SELECT plan_date, plan_json FROM meal_plans WHERE user_phone = ? ORDER BY plan_date DESC LIMIT 1",
            (phone,),
        ).fetchone()
        if plan_row:
            plan = json.loads(plan_row["plan_json"])
            for meal in plan.get("meals", []):
                setting = settings.get(meal.get("meal_type"))
                if setting:
                    meal["time"] = str(setting["scheduled_time"])
                    database.execute(
                        """
                        UPDATE meal_reminders
                        SET food_plan = ?
                        WHERE user_id = ? AND meal_type = ?
                        """,
                        (
                            json.dumps(meal, ensure_ascii=False),
                            phone,
                            meal["meal_type"],
                        ),
                    )
            database.execute(
                "UPDATE meal_plans SET plan_json = ? WHERE user_phone = ? AND plan_date = ?",
                (json.dumps(plan, ensure_ascii=False), phone, plan_row["plan_date"]),
            )


def get_daily_meal_plan(phone, plan_date=None, database_path=DB_PATH):
    selected_date = (plan_date or date.today()).isoformat()
    with connection(database_path) as database:
        row = database.execute(
            "SELECT * FROM meal_plans WHERE user_phone = ? AND plan_date = ?",
            (phone, selected_date),
        ).fetchone()
    if row is None:
        return None
    plan = dict(row)
    plan["plan"] = json.loads(plan.pop("plan_json"))
    return plan


def save_daily_meal_plan(phone, plan, plan_date=None, database_path=DB_PATH):
    selected_date = (plan_date or date.today()).isoformat()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    plan_json = json.dumps(plan, ensure_ascii=False)
    total_calories = sum(float(meal.get("calories", 0)) for meal in plan["meals"])

    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO meal_plans (
                user_phone, plan_date, plan_json, target_calories,
                total_calories, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_phone, plan_date) DO UPDATE SET
                plan_json = excluded.plan_json,
                target_calories = excluded.target_calories,
                total_calories = excluded.total_calories,
                created_at = excluded.created_at
            """,
            (
                phone,
                selected_date,
                plan_json,
                int(plan.get("target_calories", 0)),
                total_calories,
                now,
            ),
        )

        for meal in plan["meals"]:
            existing = database.execute(
                "SELECT enabled FROM meal_reminders WHERE user_id = ? AND meal_type = ?",
                (phone, meal["meal_type"]),
            ).fetchone()
            default_enabled = MEAL_SLOT_DEFAULTS[meal["meal_type"]]["enabled"]
            enabled = int(existing["enabled"]) if existing else int(default_enabled)
            database.execute(
                """
                INSERT INTO meal_reminders (
                    user_id, meal_type, scheduled_time, food_plan, enabled,
                    plan_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, meal_type) DO UPDATE SET
                    scheduled_time = excluded.scheduled_time,
                    food_plan = excluded.food_plan,
                    plan_date = excluded.plan_date,
                    claim_until = NULL
                """,
                (
                    phone,
                    meal["meal_type"],
                    meal["time"],
                    json.dumps(meal, ensure_ascii=False),
                    enabled,
                    selected_date,
                    now,
                ),
            )


def ensure_default_reminder_settings(phone, default_times, database_path=DB_PATH):
    settings = get_reminder_settings(phone, database_path)
    missing = {}
    for meal_type, defaults in MEAL_SLOT_DEFAULTS.items():
        if meal_type not in settings:
            missing[meal_type] = {
                "scheduled_time": default_times[meal_type],
                "enabled": defaults["enabled"],
            }
    if missing:
        save_reminder_settings(phone, missing, database_path)
    return get_reminder_settings(phone, database_path)


def claim_due_reminders(now=None, lease_minutes=5, database_path=DB_PATH):
    current = now or datetime.now().astimezone()
    today = current.date().isoformat()
    current_time = current.strftime("%H:%M")
    claim_until = (current + timedelta(minutes=lease_minutes)).isoformat(timespec="seconds")
    claimed = []

    with connection(database_path) as database:
        database.execute("BEGIN IMMEDIATE")
        rows = database.execute(
            """
            SELECT r.id, r.user_id, r.meal_type, r.scheduled_time,
                   r.food_plan, u.name
            FROM meal_reminders AS r
            JOIN users AS u ON u.phone = r.user_id
            WHERE r.enabled = 1
                            AND u.reminders_enabled = 1
              AND r.plan_date = ?
              AND r.scheduled_time <= ?
              AND (r.last_sent_date IS NULL OR r.last_sent_date != ?)
              AND (r.claim_until IS NULL OR r.claim_until < ?)
            ORDER BY r.scheduled_time
            """,
            (today, current_time, today, current.isoformat(timespec="seconds")),
        ).fetchall()

        for row in rows:
            updated = database.execute(
                """
                UPDATE meal_reminders SET claim_until = ?
                WHERE id = ?
                  AND (last_sent_date IS NULL OR last_sent_date != ?)
                  AND (claim_until IS NULL OR claim_until < ?)
                """,
                (
                    claim_until,
                    row["id"],
                    today,
                    current.isoformat(timespec="seconds"),
                ),
            )
            if updated.rowcount:
                reminder = dict(row)
                reminder["food_plan"] = json.loads(reminder["food_plan"] or "{}")
                claimed.append(reminder)
    return claimed


def mark_reminder_sent(reminder_id, sent_date=None, database_path=DB_PATH):
    selected_date = (sent_date or date.today()).isoformat()
    with connection(database_path) as database:
        database.execute(
            "UPDATE meal_reminders SET last_sent_date = ?, claim_until = NULL WHERE id = ?",
            (selected_date, reminder_id),
        )


def release_reminder_claim(reminder_id, database_path=DB_PATH):
    with connection(database_path) as database:
        database.execute(
            "UPDATE meal_reminders SET claim_until = NULL WHERE id = ?",
            (reminder_id,),
        )


BODY_MEASUREMENT_FIELDS = (
    "weight_kg", "waist_cm", "hip_cm", "chest_cm", "arm_cm", "thigh_cm",
)


def save_body_measurements(phone, measurements, measured_on=None, database_path=DB_PATH):
    values = {}
    for field in BODY_MEASUREMENT_FIELDS:
        value = measurements.get(field)
        if value in (None, ""):
            values[field] = None
            continue
        try:
            value = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field.replace('_', ' ').title()} must be a number.") from error
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{field.replace('_', ' ').title()} must be positive.")
        values[field] = value
    if not any(value is not None for value in values.values()):
        raise ValueError("Enter at least one measurement.")

    selected_date = (measured_on or date.today()).isoformat()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    updates = ", ".join(
        f"{field} = COALESCE(excluded.{field}, body_measurements.{field})"
        for field in BODY_MEASUREMENT_FIELDS
    )
    with connection(database_path) as database:
        database.execute(
            f"""
            INSERT INTO body_measurements (
                user_phone, measurement_date, {", ".join(BODY_MEASUREMENT_FIELDS)}, updated_at
            ) VALUES (?, ?, {", ".join("?" for _ in BODY_MEASUREMENT_FIELDS)}, ?)
            ON CONFLICT(user_phone, measurement_date) DO UPDATE SET
                {updates}, updated_at = excluded.updated_at
            """,
            (phone, selected_date, *(values[field] for field in BODY_MEASUREMENT_FIELDS), now),
        )
        if values["weight_kg"] is not None:
            database.execute(
                """
                INSERT INTO weight_history (user_phone, recorded_on, weight_kg)
                VALUES (?, ?, ?)
                ON CONFLICT(user_phone, recorded_on) DO UPDATE SET
                    weight_kg = excluded.weight_kg
                """,
                (phone, selected_date, values["weight_kg"]),
            )
    return get_body_measurements(phone, database_path=database_path)[-1]


def get_body_measurements(phone, start_date=None, end_date=None, database_path=DB_PATH):
    clauses = ["user_phone = ?"]
    parameters = [phone]
    if start_date is not None:
        clauses.append("measurement_date >= ?")
        parameters.append(start_date.isoformat())
    if end_date is not None:
        clauses.append("measurement_date <= ?")
        parameters.append(end_date.isoformat())
    with connection(database_path) as database:
        rows = database.execute(
            "SELECT * FROM body_measurements WHERE "
            + " AND ".join(clauses)
            + " ORDER BY measurement_date",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def save_workout_plan(phone, week_start, plan, database_path=DB_PATH):
    selected_date = week_start.isoformat() if hasattr(week_start, "isoformat") else str(week_start)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO workout_plans (user_phone, week_start, plan_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_phone, week_start) DO UPDATE SET
                plan_json = excluded.plan_json, updated_at = excluded.updated_at
            """,
            (phone, selected_date, json.dumps(plan, ensure_ascii=False), now),
        )


def get_workout_plan(phone, week_start, database_path=DB_PATH):
    selected_date = week_start.isoformat() if hasattr(week_start, "isoformat") else str(week_start)
    with connection(database_path) as database:
        row = database.execute(
            "SELECT plan_json, updated_at FROM workout_plans "
            "WHERE user_phone = ? AND week_start = ?",
            (phone, selected_date),
        ).fetchone()
    if row is None:
        return None
    return {"plan": json.loads(row["plan_json"]), "updated_at": row["updated_at"]}


def save_workout_log(phone, workout_date, exercise, log, database_path=DB_PATH):
    selected_date = workout_date.isoformat() if hasattr(workout_date, "isoformat") else str(workout_date)
    sets_completed = int(log.get("sets_completed", 0))
    reps_completed = int(log.get("reps_completed", 0))
    duration_minutes = float(log.get("duration_minutes", 0))
    if min(sets_completed, reps_completed) < 0 or not math.isfinite(duration_minutes) or duration_minutes < 0:
        raise ValueError("Workout progress values cannot be negative.")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO workout_logs (
                user_phone, workout_date, exercise_key, exercise_name,
                sets_completed, reps_completed, duration_minutes, difficulty,
                completed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_phone, workout_date, exercise_key) DO UPDATE SET
                exercise_name = excluded.exercise_name,
                sets_completed = excluded.sets_completed,
                reps_completed = excluded.reps_completed,
                duration_minutes = excluded.duration_minutes,
                difficulty = excluded.difficulty,
                completed = excluded.completed,
                updated_at = excluded.updated_at
            """,
            (
                phone, selected_date, exercise["key"], exercise["name"],
                sets_completed, reps_completed, duration_minutes,
                str(log.get("difficulty", "Beginner")),
                int(bool(log.get("completed"))), now,
            ),
        )


def get_workout_logs(phone, start_date=None, end_date=None, database_path=DB_PATH):
    clauses = ["user_phone = ?"]
    parameters = [phone]
    if start_date is not None:
        clauses.append("workout_date >= ?")
        parameters.append(start_date.isoformat())
    if end_date is not None:
        clauses.append("workout_date <= ?")
        parameters.append(end_date.isoformat())
    with connection(database_path) as database:
        rows = database.execute(
            "SELECT * FROM workout_logs WHERE "
            + " AND ".join(clauses)
            + " ORDER BY workout_date DESC, id",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def save_workout_reminder(phone, enabled, scheduled_time, focus, duration_minutes, database_path=DB_PATH):
    if len(scheduled_time) != 5 or scheduled_time[2] != ":":
        raise ValueError("Reminder time must use HH:MM format.")
    try:
        datetime.strptime(scheduled_time, "%H:%M")
    except ValueError as error:
        raise ValueError("Reminder time must use HH:MM format.") from error
    duration_minutes = int(duration_minutes)
    if not 10 <= duration_minutes <= 180:
        raise ValueError("Workout reminder duration must be between 10 and 180 minutes.")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO workout_reminders (
                user_phone, enabled, scheduled_time, focus, duration_minutes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_phone) DO UPDATE SET
                enabled = excluded.enabled,
                scheduled_time = excluded.scheduled_time,
                focus = excluded.focus,
                duration_minutes = excluded.duration_minutes,
                claim_until = NULL,
                updated_at = excluded.updated_at
            """,
            (phone, int(bool(enabled)), scheduled_time, str(focus).strip()[:100], duration_minutes, now),
        )


def get_workout_reminder(phone, database_path=DB_PATH):
    with connection(database_path) as database:
        row = database.execute(
            "SELECT * FROM workout_reminders WHERE user_phone = ?", (phone,)
        ).fetchone()
    return dict(row) if row else None


def claim_due_workout_reminders(now=None, lease_minutes=5, database_path=DB_PATH):
    current = now or datetime.now().astimezone()
    today = current.date().isoformat()
    current_time = current.strftime("%H:%M")
    current_iso = current.isoformat(timespec="seconds")
    claim_until = (current + timedelta(minutes=lease_minutes)).isoformat(timespec="seconds")
    claimed = []
    with connection(database_path) as database:
        database.execute("BEGIN IMMEDIATE")
        rows = database.execute(
            """
            SELECT r.*, u.name FROM workout_reminders AS r
            JOIN users AS u ON u.phone = r.user_phone
            WHERE r.enabled = 1 AND r.scheduled_time <= ?
              AND (r.last_sent_date IS NULL OR r.last_sent_date != ?)
              AND (r.claim_until IS NULL OR r.claim_until < ?)
            ORDER BY r.scheduled_time
            """,
            (current_time, today, current_iso),
        ).fetchall()
        for row in rows:
            updated = database.execute(
                """
                UPDATE workout_reminders SET claim_until = ?
                WHERE user_phone = ?
                  AND (last_sent_date IS NULL OR last_sent_date != ?)
                  AND (claim_until IS NULL OR claim_until < ?)
                """,
                (claim_until, row["user_phone"], today, current_iso),
            )
            if updated.rowcount:
                claimed.append(dict(row))
    return claimed


def mark_workout_reminder_sent(phone, sent_date=None, database_path=DB_PATH):
    selected_date = (sent_date or date.today()).isoformat()
    with connection(database_path) as database:
        database.execute(
            "UPDATE workout_reminders SET last_sent_date = ?, claim_until = NULL "
            "WHERE user_phone = ?",
            (selected_date, phone),
        )


def release_workout_reminder_claim(phone, database_path=DB_PATH):
    with connection(database_path) as database:
        database.execute(
            "UPDATE workout_reminders SET claim_until = NULL WHERE user_phone = ?",
            (phone,),
        )


def save_daily_summary_reminder(phone, enabled, scheduled_time, database_path=DB_PATH):
    try:
        datetime.strptime(scheduled_time, "%H:%M")
    except (TypeError, ValueError) as error:
        raise ValueError("Reminder time must use HH:MM format.") from error
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    with connection(database_path) as database:
        database.execute(
            """
            INSERT INTO daily_summary_reminders (
                user_phone, enabled, scheduled_time, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(user_phone) DO UPDATE SET
                enabled = excluded.enabled,
                scheduled_time = excluded.scheduled_time,
                claim_until = NULL,
                updated_at = excluded.updated_at
            """,
            (phone, int(bool(enabled)), scheduled_time, now),
        )


def get_daily_summary_reminder(phone, database_path=DB_PATH):
    with connection(database_path) as database:
        row = database.execute(
            "SELECT * FROM daily_summary_reminders WHERE user_phone = ?",
            (phone,),
        ).fetchone()
    return dict(row) if row else None


def claim_due_daily_summaries(now=None, lease_minutes=5, database_path=DB_PATH):
    current = now or datetime.now().astimezone()
    today = current.date().isoformat()
    current_time = current.strftime("%H:%M")
    current_iso = current.isoformat(timespec="seconds")
    claim_until = (current + timedelta(minutes=lease_minutes)).isoformat(timespec="seconds")
    claimed = []
    with connection(database_path) as database:
        database.execute("BEGIN IMMEDIATE")
        rows = database.execute(
            """
            SELECT r.user_phone, r.scheduled_time, u.name
            FROM daily_summary_reminders AS r
            JOIN users AS u ON u.phone = r.user_phone
            WHERE r.enabled = 1 AND r.scheduled_time <= ?
              AND (r.last_sent_date IS NULL OR r.last_sent_date != ?)
              AND (r.claim_until IS NULL OR r.claim_until < ?)
            ORDER BY r.scheduled_time
            """,
            (current_time, today, current_iso),
        ).fetchall()
        for row in rows:
            updated = database.execute(
                """
                UPDATE daily_summary_reminders SET claim_until = ?
                WHERE user_phone = ?
                  AND (last_sent_date IS NULL OR last_sent_date != ?)
                  AND (claim_until IS NULL OR claim_until < ?)
                """,
                (claim_until, row["user_phone"], today, current_iso),
            )
            if updated.rowcount:
                claimed.append(dict(row))
    return claimed


def mark_daily_summary_sent(phone, sent_date=None, database_path=DB_PATH):
    selected_date = (sent_date or date.today()).isoformat()
    with connection(database_path) as database:
        database.execute(
            "UPDATE daily_summary_reminders SET last_sent_date = ?, claim_until = NULL "
            "WHERE user_phone = ?",
            (selected_date, phone),
        )


def release_daily_summary_claim(phone, database_path=DB_PATH):
    with connection(database_path) as database:
        database.execute(
            "UPDATE daily_summary_reminders SET claim_until = NULL WHERE user_phone = ?",
            (phone,),
        )
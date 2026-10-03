import hashlib
import json
import mimetypes
import re
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

import database
import gemini_service
from error_handling import safe_error
from exercise import (
    BODY_AREAS,
    BODY_GOALS,
    EQUIPMENT_OPTIONS,
    EXERCISES,
    EXERCISE_BY_KEY,
    EXPERIENCE_LEVELS,
    FITNESS_GOALS,
    WORKOUT_DURATIONS,
    WORKOUT_LOCATIONS,
    available_exercises,
    build_workout_plan_prompt,
    default_workout_plan,
    movement_svg,
    parse_workout_plan,
    week_start_for,
)


MEASUREMENT_FIELDS = {
    "weight_kg": ("Weight", "kg"),
    "waist_cm": ("Waist", "cm"),
    "hip_cm": ("Hip", "cm"),
    "chest_cm": ("Chest", "cm"),
    "arm_cm": ("Arm", "cm"),
    "thigh_cm": ("Thigh", "cm"),
}


def _equipment(profile):
    value = profile.get("exercise_equipment", [])
    if isinstance(value, str):
        try:
            value = __import__("json").loads(value)
        except ValueError:
            value = []
    return value if isinstance(value, list) else []


def _log_defaults(exercise, existing):
    reps = re.search(r"\d+", str(exercise.get("reps", "0")))
    return {
        "sets_completed": int(existing.get("sets_completed", exercise.get("sets", 0))) if existing else int(exercise.get("sets", 0)),
        "reps_completed": int(existing.get("reps_completed", reps.group(0) if reps else 0)) if existing else int(reps.group(0)) if reps else 0,
        "duration_minutes": float(existing.get("duration_minutes", exercise.get("duration_min", 0))) if existing else float(exercise.get("duration_min", 0)),
        "difficulty": existing.get("difficulty", exercise.get("difficulty", "Beginner")) if existing else exercise.get("difficulty", "Beginner"),
        "completed": bool(existing.get("completed", False)) if existing else False,
    }


def _render_exercise_card(exercise, phone, workout_date=None, existing_log=None):
    catalog = EXERCISE_BY_KEY[exercise["key"]]
    planned = dict(catalog)
    for field in ("sets", "reps", "rest_sec", "duration_min", "difficulty"):
        if field in exercise:
            planned[field] = exercise[field]

    with st.container(border=True):
        st.subheader(catalog["name"])
        st.caption(
            f"Target: {', '.join(catalog['areas'])} · {catalog['target']} · "
            f"{planned['difficulty']}"
        )
        required_equipment = ", ".join(catalog["equipment"]) or "No equipment"
        st.caption(f"Equipment: {required_equipment}")
        st.caption(
            f"{planned['sets']} sets × {planned['reps']} · "
            f"Rest {planned['rest_sec']} sec · about {planned['duration_min']} min"
        )
        st.image(movement_svg(catalog), width="stretch")
        st.caption("Watch demo · Start → move → end position → return. Original MacroSnap movement diagram.")

        with st.expander("How to do this exercise"):
            st.markdown("**Starting position**")
            st.write(catalog["instructions"][0])
            st.markdown("**Movement**")
            for step_number, instruction in enumerate(catalog["instructions"][1:], start=2):
                st.write(f"{step_number}. {instruction}")
            st.write(f"**Breathing:** {catalog['breathing']}")
            st.write(f"**Common mistake:** {catalog['mistakes']}")
            st.write(f"**Safety:** {catalog['safety']}")
            st.write(f"**Beginner option:** {catalog['beginner']}")
            st.write(f"**More challenging option:** {catalog['advanced']}")

        if workout_date is None:
            return

        defaults = _log_defaults(planned, existing_log)
        with st.form(f"exercise_log_{workout_date}_{catalog['key']}"):
            with st.container(horizontal=True):
                sets_done = st.number_input(
                    "Sets done", min_value=0, max_value=20,
                    value=min(defaults["sets_completed"], 20), step=1,
                )
                reps_done = st.number_input(
                    "Reps done", min_value=0, max_value=200,
                    value=min(defaults["reps_completed"], 200), step=1,
                    help="For timed movements, record 0 reps and use duration.",
                )
                duration = st.number_input(
                    "Minutes", min_value=0.0, max_value=180.0,
                    value=min(defaults["duration_minutes"], 180.0), step=1.0,
                )
                difficulty = st.selectbox(
                    "Difficulty felt like",
                    EXPERIENCE_LEVELS,
                    index=(EXPERIENCE_LEVELS.index(defaults["difficulty"])
                           if defaults["difficulty"] in EXPERIENCE_LEVELS else 0),
                )
            completed = st.checkbox("Exercise completed", value=defaults["completed"])
            submitted = st.form_submit_button("Save workout log", icon=":material/save:")
        if submitted:
            database.save_workout_log(
                phone,
                workout_date,
                catalog,
                {
                    "sets_completed": sets_done,
                    "reps_completed": reps_done,
                    "duration_minutes": duration,
                    "difficulty": difficulty,
                    "completed": completed,
                },
            )
            st.success("Workout progress saved.")
            st.rerun()


def _render_plan_editor(phone, plan, selected_day, week_start, profile):
    equipment = _equipment(profile)
    available = available_exercises("Full body", profile.get("exercise_location", "Home"), equipment)
    if not available:
        available = list(EXERCISES)
    exercise_names = [item["name"] for item in available]
    name_to_exercise = {item["name"]: item for item in available}
    rows = [
        {
            "Exercise": EXERCISE_BY_KEY[item["key"]]["name"],
            "Sets": item["sets"],
            "Reps": item["reps"],
            "Rest (sec)": item["rest_sec"],
            "Minutes": item["duration_min"],
        }
        for item in selected_day["exercises"]
        if item.get("key") in EXERCISE_BY_KEY
    ]
    editor_frame = pd.DataFrame(
        rows,
        columns=["Exercise", "Sets", "Reps", "Rest (sec)", "Minutes"],
    )
    with st.expander("Adjust this day's workout"):
        st.caption("Choose movements from the library and adjust the volume or duration.")
        with st.form(f"workout_plan_edit_{selected_day['date']}"):
            focus = st.text_input("Workout focus", value=selected_day["focus"])
            duration = st.number_input(
                "Available workout time (minutes)", min_value=0, max_value=180,
                value=min(int(selected_day["duration_minutes"]), 180), step=5,
            )
            warmup = st.text_input("Warm-up", value=selected_day["warmup"])
            cooldown = st.text_input("Cool-down", value=selected_day["cooldown"])
            edited = st.data_editor(
                editor_frame,
                hide_index=True,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "Exercise": st.column_config.SelectboxColumn(
                        "Exercise", options=exercise_names, required=True,
                    ),
                    "Sets": st.column_config.NumberColumn("Sets", min_value=1, max_value=5, step=1),
                    "Reps": st.column_config.TextColumn("Reps"),
                    "Rest (sec)": st.column_config.NumberColumn("Rest (sec)", min_value=0, max_value=180, step=15),
                    "Minutes": st.column_config.NumberColumn("Minutes", min_value=1, max_value=180, step=1),
                },
                key=f"workout_day_editor_{selected_day['date']}",
            )
            save_day = st.form_submit_button("Save this day's plan", icon=":material/save:")
        if save_day:
            exercises = []
            for row in edited.to_dict("records"):
                catalog = name_to_exercise.get(str(row.get("Exercise", "")))
                if catalog is None:
                    continue
                try:
                    sets = max(1, min(5, int(row.get("Sets", catalog["sets"]))))
                    rest = max(0, min(180, int(row.get("Rest (sec)", catalog["rest_sec"]))))
                    minutes = max(1, min(180, int(row.get("Minutes", catalog["duration_min"]))))
                except (TypeError, ValueError):
                    continue
                exercises.append(
                    {
                        "key": catalog["key"],
                        "name": catalog["name"],
                        "sets": sets,
                        "reps": str(row.get("Reps", catalog["reps"]))[:24],
                        "rest_sec": rest,
                        "duration_min": minutes,
                        "difficulty": profile.get("fitness_experience", "Beginner"),
                    }
                )
            selected_day.update(
                {
                    "focus": focus.strip()[:80] or "Workout",
                    "duration_minutes": int(duration),
                    "warmup": warmup.strip()[:240],
                    "cooldown": cooldown.strip()[:240],
                    "rest": not exercises,
                    "exercises": exercises,
                }
            )
            database.save_workout_plan(phone, week_start, plan)
            st.success("Workout plan updated.")
            st.rerun()


def _render_today_tab(phone, profile, generate_text):
    today = date.today()
    week_start = week_start_for(today)
    saved = database.get_workout_plan(phone, week_start)
    plan = saved["plan"] if saved else default_workout_plan(profile, week_start)
    st.subheader("Today's workout")
    st.caption("Training activity is tracked separately and never subtracted from your food target.")

    if st.button(
        "What workout should I do now?",
        type="primary",
        icon=":material/bolt:",
        key="exercise_generate_workout",
    ):
        history = database.get_workout_logs(phone, today - timedelta(days=30), today)
        prompt = build_workout_plan_prompt(
            profile,
            history,
            week_start,
        )
        with st.spinner("Building a plan around your goals and recent activity…"):
            answer = generate_text(prompt, json_response=True)
        personalized = parse_workout_plan(answer, profile, week_start) if answer else None
        if personalized is None:
            plan = default_workout_plan(profile, week_start)
            st.warning("A personalized AI plan was unavailable, so a conservative editable starter week is shown.")
        else:
            plan = personalized
            st.success("Your personalized week is ready. Adjust any day before or after training.")
        database.save_workout_plan(phone, week_start, plan)

    choices = [day["day"] for day in plan.get("days", [])]
    if not choices:
        plan = default_workout_plan(profile, week_start)
        choices = [day["day"] for day in plan["days"]]
    selected_name = st.selectbox(
        "Workout day",
        choices,
        index=min(today.weekday(), len(choices) - 1),
        key="exercise_selected_day",
    )
    selected_day = next(day for day in plan["days"] if day["day"] == selected_name)
    workout_date = date.fromisoformat(selected_day["date"])
    week_logs = database.get_workout_logs(
        phone,
        week_start,
        week_start + timedelta(days=6),
    )
    weekly_status = []
    for planned_day in plan["days"]:
        day_logs = [item for item in week_logs if item["workout_date"] == planned_day["date"]]
        done = sum(bool(item["completed"]) for item in day_logs)
        total = len(planned_day["exercises"])
        status = (
            "Rest"
            if planned_day["rest"]
            else "Completed"
            if total and done == total
            else "In progress"
            if done
            else "Planned"
        )
        weekly_status.append(
            {
                "Day": planned_day["day"],
                "Focus": planned_day["focus"],
                "Status": status,
            }
        )
    st.dataframe(pd.DataFrame(weekly_status), hide_index=True)
    logs = database.get_workout_logs(phone, workout_date, workout_date)
    log_by_key = {item["exercise_key"]: item for item in logs}
    total_exercises = len(selected_day["exercises"])
    completed_count = sum(
        bool(log_by_key.get(item["key"], {}).get("completed"))
        for item in selected_day["exercises"]
    )

    if selected_day["rest"] or not total_exercises:
        st.info(f"{selected_day['day']} is a recovery day. Gentle mobility is optional; rest is part of training.")
    else:
        with st.container(horizontal=True):
            st.metric("Planned time", f"{selected_day['duration_minutes']} min")
            st.metric("Workout completion", f"{completed_count} / {total_exercises}")
        st.progress(completed_count / total_exercises, text=f"{completed_count / total_exercises:.0%} complete")
        st.write(f"**Warm-up:** {selected_day['warmup']}")
        for item in selected_day["exercises"]:
            if item.get("key") not in EXERCISE_BY_KEY:
                continue
            _render_exercise_card(
                item,
                phone,
                workout_date,
                log_by_key.get(item["key"]),
            )
        st.write(f"**Cool-down:** {selected_day['cooldown']}")
    _render_plan_editor(phone, plan, selected_day, week_start, profile)


def _render_library_tab(profile):
    st.subheader("Exercise library")
    area = st.pills(
        "Body area",
        BODY_AREAS,
        selection_mode="single",
        default="Full body",
        key="exercise_library_area",
        wrap=True,
    ) or "Full body"
    exercises = available_exercises(
        area,
        profile.get("exercise_location", "Home"),
        _equipment(profile),
    )
    if not exercises:
        st.info("No movements match this equipment and location. Update training preferences to see more options.")
        return
    for offset in range(0, len(exercises), 2):
        columns = st.columns(2)
        for column, item in zip(columns, exercises[offset:offset + 2]):
            with column:
                _render_exercise_card(item, None)


def _render_goals_tab(phone, profile):
    st.subheader("Fitness goals")
    st.caption(f"Fitness goal: {profile.get('fitness_goal', 'Improve fitness')} · Body goal: {profile.get('body_goal', 'Improve overall body shape')}")
    st.info(
        "Training can strengthen and develop selected muscles, but it cannot selectively "
        "remove fat from one body part. Overall fat loss depends on total energy balance "
        "and individual physiology."
    )

    area = st.pills(
        "What do you want to focus on?",
        BODY_AREAS,
        selection_mode="single",
        default="Full body",
        key="exercise_body_area",
        wrap=True,
    ) or "Full body"
    focused_exercises = available_exercises(
        area,
        profile.get("exercise_location", "Home"),
        _equipment(profile),
    )
    if focused_exercises:
        for offset in range(0, len(focused_exercises), 2):
            columns = st.columns(2)
            for column, item in zip(columns, focused_exercises[offset:offset + 2]):
                with column:
                    _render_exercise_card(item, None)

    st.subheader("Training preferences")
    with st.form("exercise_preferences_form"):
        fitness_goal = st.selectbox(
            "Fitness goal", FITNESS_GOALS,
            index=FITNESS_GOALS.index(profile.get("fitness_goal", "Improve fitness")),
        )
        body_goal = st.selectbox(
            "Body goal", BODY_GOALS,
            index=BODY_GOALS.index(profile.get("body_goal", "Improve overall body shape")),
        )
        experience = st.selectbox(
            "Fitness experience", EXPERIENCE_LEVELS,
            index=EXPERIENCE_LEVELS.index(profile.get("fitness_experience", "Beginner")),
        )
        location = st.selectbox(
            "Where do you exercise?", WORKOUT_LOCATIONS,
            index=WORKOUT_LOCATIONS.index(profile.get("exercise_location", "Home")),
        )
        equipment = st.multiselect(
            "Available equipment", EQUIPMENT_OPTIONS,
            default=[item for item in _equipment(profile) if item in EQUIPMENT_OPTIONS],
        )
        duration = st.selectbox(
            "Available workout time", WORKOUT_DURATIONS,
            index=(WORKOUT_DURATIONS.index(int(profile.get("available_workout_minutes", 20)))
                   if int(profile.get("available_workout_minutes", 20)) in WORKOUT_DURATIONS else 2),
            format_func=lambda value: "60 minutes+" if value == 60 else f"{value} minutes",
        )
        preferences = st.text_input(
            "Exercise preferences", value=profile.get("exercise_preferences", ""),
            placeholder="Walking, low-impact movement, short sessions…",
        )
        saved_preferences = st.form_submit_button("Save training preferences", icon=":material/save:")
    if saved_preferences:
        updated = dict(profile)
        updated.update(
            {
                "fitness_goal": fitness_goal,
                "body_goal": body_goal,
                "fitness_experience": experience,
                "exercise_location": location,
                "exercise_equipment": equipment,
                "available_workout_minutes": duration,
                "exercise_preferences": preferences.strip(),
            }
        )
        database.save_user(phone, updated)
        st.success("Training preferences saved.")
        st.rerun()

    st.subheader("WhatsApp workout reminders")
    reminder = database.get_workout_reminder(phone) or {}
    try:
        reminder_time = datetime.strptime(reminder.get("scheduled_time", "18:00"), "%H:%M").time()
    except ValueError:
        reminder_time = time(18, 0)
    with st.form("workout_reminder_form"):
        enabled = st.checkbox("Send me a daily workout reminder", value=bool(reminder.get("enabled", 0)))
        scheduled_time = st.time_input("Reminder time", value=reminder_time)
        reminder_focus = st.selectbox(
            "Reminder focus", BODY_AREAS,
            index=(BODY_AREAS.index(reminder.get("focus", "Full body"))
                   if reminder.get("focus", "Full body") in BODY_AREAS else 0),
        )
        reminder_duration = st.selectbox(
            "Reminder duration", WORKOUT_DURATIONS,
            index=(WORKOUT_DURATIONS.index(int(reminder.get("duration_minutes", 20)))
                   if int(reminder.get("duration_minutes", 20)) in WORKOUT_DURATIONS else 2),
            format_func=lambda value: "60 minutes+" if value == 60 else f"{value} minutes",
        )
        save_reminder = st.form_submit_button("Save reminder settings", icon=":material/schedule:")
    if save_reminder:
        database.save_workout_reminder(
            phone,
            enabled,
            scheduled_time.strftime("%H:%M"),
            reminder_focus,
            reminder_duration,
        )
        st.success("Workout reminder settings saved.")
    st.caption("Scheduled messages are delivered by the separate reminder worker, not this browser page.")


def _render_progress_tab(phone):
    today = date.today()
    st.subheader("Record measurements")
    st.caption("Measurements are optional. Enter 0 for any item you do not want to record.")
    with st.form("body_measurement_form"):
        measured_on = st.date_input("Measurement date", value=today, max_value=today)
        columns = st.columns(3)
        values = {}
        for index, (field, (label, unit)) in enumerate(MEASUREMENT_FIELDS.items()):
            with columns[index % len(columns)]:
                maximum = 350.0 if field == "weight_kg" else 300.0
                values[field] = st.number_input(
                    f"{label} ({unit})", min_value=0.0, max_value=maximum,
                    value=0.0, step=0.1,
                )
        save_measurement = st.form_submit_button("Save measurements", icon=":material/save:")
    if save_measurement:
        measurements = {key: value for key, value in values.items() if value > 0}
        if not measurements:
            st.warning("Enter at least one measurement, or leave the form unchanged.")
        else:
            try:
                database.save_body_measurements(phone, measurements, measured_on)
                st.success("Measurements saved.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    measurements = database.get_body_measurements(phone)
    if measurements:
        measured_fields = [
            field for field in MEASUREMENT_FIELDS
            if any(row.get(field) is not None for row in measurements)
        ]
        selected_field = st.selectbox(
            "Measurement trend",
            measured_fields,
            format_func=lambda field: f"{MEASUREMENT_FIELDS[field][0]} ({MEASUREMENT_FIELDS[field][1]})",
        )
        measurement_frame = pd.DataFrame(measurements)
        measurement_frame["Date"] = pd.to_datetime(measurement_frame["measurement_date"])
        measurement_frame = measurement_frame.dropna(subset=[selected_field])
        st.line_chart(
            measurement_frame,
            x="Date",
            y=selected_field,
            y_label=MEASUREMENT_FIELDS[selected_field][1],
        )
        st.dataframe(
            measurement_frame[["measurement_date", selected_field]].rename(
                columns={"measurement_date": "Date", selected_field: MEASUREMENT_FIELDS[selected_field][0]}
            ),
            hide_index=True,
        )
    else:
        st.info("Add optional measurements to start a body-measurement trend.")

    st.subheader("Workout consistency")
    start = today - timedelta(days=27)
    logs = database.get_workout_logs(phone, start, today)
    if logs:
        frame = pd.DataFrame(logs)
        frame["completed"] = frame["completed"].astype(bool)
        completed = frame[frame["completed"]]
        st.metric("Completed workout days · last 28 days", completed["workout_date"].nunique())
        daily_minutes = completed.groupby("workout_date", as_index=False)["duration_minutes"].sum()
        daily_minutes = daily_minutes.rename(columns={"workout_date": "Date", "duration_minutes": "Minutes"})
        st.bar_chart(daily_minutes, x="Date", y="Minutes")
        completed_exercises = completed[completed["reps_completed"] > 0]
        if not completed_exercises.empty:
            exercise_names = sorted(completed_exercises["exercise_name"].unique())
            selected_exercise = st.selectbox("Repetition progress", exercise_names)
            strength = completed_exercises[completed_exercises["exercise_name"] == selected_exercise]
            st.line_chart(strength, x="workout_date", y="reps_completed", y_label="Repetitions")
    else:
        st.info("Log completed exercises to see workout frequency, duration, and repetition trends.")


def _render_history_tab(phone):
    st.subheader("Workout history")
    today = date.today()
    date_range = st.date_input(
        "Date range",
        value=(today - timedelta(days=27), today),
        max_value=today,
        key="workout_history_range",
    )
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
    elif isinstance(date_range, date):
        start_date = end_date = date_range
    else:
        start_date, end_date = today - timedelta(days=27), today
    logs = database.get_workout_logs(phone, start_date, end_date)
    if not logs:
        st.info("No exercises logged in this date range yet.")
        return
    frame = pd.DataFrame(logs)
    frame["Status"] = frame["completed"].map({1: "Completed", 0: "Not completed"})
    frame = frame.rename(
        columns={
            "workout_date": "Date",
            "exercise_name": "Exercise",
            "sets_completed": "Sets",
            "reps_completed": "Reps",
            "duration_minutes": "Minutes",
            "difficulty": "Difficulty",
        }
    )
    st.dataframe(
        frame[["Date", "Exercise", "Sets", "Reps", "Minutes", "Difficulty", "Status"]],
        hide_index=True,
    )


def _analysis_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _render_exercise_photo_analysis(profile, analyze_image):
    st.subheader("📸 Upload Exercise Photo")
    st.caption(
        "Get general observations from one still image. This is educational guidance, "
        "not a medical assessment or a complete movement evaluation."
    )
    goals = (
        "Weight Loss",
        "General Fitness",
        "Strength",
        "Muscle Building",
        "Flexibility",
        "Better Mobility",
    )
    exercise_names = ["Auto Detect Exercise"] + [item["name"] for item in EXERCISES]
    selected_goal = st.selectbox("Select goal", goals, key="exercise_photo_goal")
    selected_exercise = st.selectbox(
        "Select exercise",
        exercise_names,
        key="exercise_photo_movement",
    )
    uploaded_photo = st.file_uploader(
        "Exercise photo",
        type=["jpg", "jpeg", "png", "webp"],
        max_upload_size=10,
        key="exercise_photo_upload",
    )
    uploaded_video = st.file_uploader(
        "Optional exercise video",
        type=["mp4", "mov", "webm"],
        key="exercise_video_upload",
    )
    if uploaded_video is not None:
        st.info("Video analysis is not enabled in this version. Upload a still photo for exercise guidance.")

    if uploaded_photo is None:
        return

    photo_bytes = uploaded_photo.getvalue()
    mime_type = uploaded_photo.type or mimetypes.guess_type(uploaded_photo.name)[0]
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        st.error("Please upload a JPG, PNG, or WEBP exercise photo.")
        return

    photo_hash = hashlib.sha256(photo_bytes).hexdigest()
    st.image(photo_bytes, caption="Uploaded exercise photo", width="stretch")
    if st.button(
        "Analyze Exercise",
        type="primary",
        icon=":material/auto_awesome:",
        key="analyze_exercise_photo",
    ):
        with st.spinner("Analyzing your exercise photo…"):
            result_text = analyze_image(
                photo_bytes,
                mime_type,
                selected_goal,
                selected_exercise,
                profile,
            )
        if result_text:
            try:
                result = gemini_service.parse_json_object(result_text)
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                safe_error(
                    "Gemini could not format the exercise analysis. Please try the photo again.",
                    error,
                )
                st.session_state.pop("exercise_photo_analysis", None)
                return
            st.session_state.exercise_photo_analysis = {
                "photo_hash": photo_hash,
                "result": result,
            }
        else:
            st.error(
                st.session_state.pop(
                    "gemini_error_message",
                    "Exercise analysis is unavailable right now. Please try again.",
                )
            )

    saved_analysis = st.session_state.get("exercise_photo_analysis", {})
    if saved_analysis.get("photo_hash") != photo_hash:
        return

    result = saved_analysis.get("result", {})
    if not result.get("image_clear", True):
        st.warning(
            result.get(
                "limitation",
                "The image is unclear, so this analysis may be limited.",
            )
        )
    elif result.get("limitation"):
        st.caption(result["limitation"])

    st.subheader("🏋️ Exercise Detected")
    st.write(result.get("detected_exercise", "Unclear from this image."))
    st.subheader("📐 Form Observation")
    st.write(result.get("body_position", "Not enough visible information."))
    for item in _analysis_list(result.get("posture_observations")):
        st.write(f"- {item}")
    st.subheader("✅ What You're Doing Well")
    for item in _analysis_list(result.get("doing_well")) or ["The image does not show enough to assess this."]:
        st.write(f"- {item}")
    st.subheader("⚠️ Possible Form Issues")
    for item in _analysis_list(result.get("possible_issues")) or ["No clear issue can be assessed from this single image."]:
        st.write(f"- {item}")
    st.subheader("💡 How To Improve")
    for item in _analysis_list(result.get("corrections")) + _analysis_list(result.get("movement_guidance")):
        st.write(f"- {item}")
    st.subheader("Beginner-friendly instructions")
    for item in _analysis_list(result.get("beginner_instructions")):
        st.write(f"- {item}")
    st.subheader("🔁 Suggested Repetitions")
    st.write(result.get("suggested_repetitions", "Not enough information."))
    st.subheader("⏱️ Suggested Duration")
    st.write(result.get("suggested_duration", "Keep the session comfortable and take breaks as needed."))
    st.subheader("🛡️ Safety Tips")
    for item in _analysis_list(result.get("safety_tips")):
        st.write(f"- {item}")
    st.caption("Stop if you feel pain, dizziness, or difficulty breathing. A single photo cannot show the full movement.")


def render_exercise_page(generate_text, analyze_image):
    phone = st.session_state.user_phone
    profile = database.get_user(phone)
    st.title("Exercise", icon=":material/fitness_center:")
    st.caption("Practical movement guidance and progress tracking. Exercise suggestions are educational, not medical advice.")
    warning = (
        "Stop exercising and seek appropriate medical attention for chest pain, severe pain, "
        "dizziness, fainting, serious injury, or difficulty breathing. If you are pregnant, "
        "have a medical condition, or have a significant injury, consult a qualified healthcare professional first."
    )
    st.warning(warning)

    today_tab, library_tab, photo_tab, goals_tab, history_tab, progress_tab = st.tabs(
        ["Today's workout", "Exercise library", "Photo analysis", "Body goals", "Workout history", "Progress"]
    )
    with today_tab:
        _render_today_tab(phone, profile, generate_text)
    with library_tab:
        _render_library_tab(profile)
    with photo_tab:
        _render_exercise_photo_analysis(profile, analyze_image)
    with goals_tab:
        _render_goals_tab(phone, profile)
    with progress_tab:
        _render_progress_tab(phone)
    with history_tab:
        _render_history_tab(phone)
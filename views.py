import json
import mimetypes
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from google.genai import types

import database
import design_system
import whatsapp_service
from exercise import (
    BODY_GOALS,
    EQUIPMENT_OPTIONS,
    EXPERIENCE_LEVELS,
    FITNESS_GOALS,
    WORKOUT_DURATIONS,
    WORKOUT_LOCATIONS,
    day_for_date,
    week_start_for,
)
from nutrition import (
    MEAL_SLOT_LABELS,
    MEAL_SLOT_TYPES,
    build_smart_meal_schedule_prompt,
    calculate_profile_targets,
    format_meal_analysis,
    parse_meal_response,
    parse_daily_meal_plan,
    plan_respects_preferences,
    score_meal,
    suggest_meal_times,
)


def _profile():
    return database.get_user(st.session_state.user_phone)


def _today_meals(phone):
    today = date.today()
    return database.get_meals(phone, today, today, limit=None)


def _render_meal_card(meal, compact=False):
    created = datetime.fromisoformat(meal["created_at"])
    items = meal.get("food_items", [])
    food_labels = [
        f"{item.get('name', 'Food')} ({item.get('portion', 'portion not specified')})"
        for item in items
        if isinstance(item, dict)
    ]

    with st.container(border=True):
        st.markdown(f"**{meal['meal_name']}** · {meal['calories']:.0f} kcal")
        st.caption(
            f"{created.strftime('%b %d, %I:%M %p')} · "
            f"{meal['source'].title()} estimate"
        )
        st.write(
            f"Protein {meal['protein_g']:.0f} g · "
            f"Carbs {meal['carbs_g']:.0f} g · "
            f"Fat {meal['fat_g']:.0f} g"
        )
        if food_labels:
            st.caption(" · ".join(food_labels))
        if compact:
            with st.expander("View details"):
                st.caption(
                    f"Nutrition score: {meal['nutrition_score']}/100 "
                    "(app heuristic, not a medical assessment)"
                )
                if meal.get("nutrition_notes"):
                    st.write(meal["nutrition_notes"])
                alternatives = meal.get("alternatives", [])
                if alternatives:
                    st.markdown("**Food alternatives**")
                    for alternative in alternatives:
                        st.write(f"- {alternative['name']}: {alternative['reason']}")
        else:
            st.caption(
                f"Nutrition score: {meal['nutrition_score']}/100 "
                "(app heuristic, not a medical assessment)"
            )
            if meal.get("nutrition_notes"):
                st.write(meal["nutrition_notes"])
            alternatives = meal.get("alternatives", [])
            if alternatives:
                st.markdown("**Healthier alternatives**")
                for alternative in alternatives:
                    st.write(
                        f"- {alternative['name']}: {alternative['reason']}"
                    )


def _weekly_frame(phone):
    today = date.today()
    start = today - timedelta(days=6)
    totals = database.get_weekly_totals(phone, start, today)
    rows = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        daily = totals.get(day.isoformat(), {})
        rows.append(
            {
                "Day": day.strftime("%a"),
                "Date": day.isoformat(),
                "Calories": round(daily.get("calories", 0)),
                "Protein": round(daily.get("protein_g", 0)),
                "Carbs": round(daily.get("carbs_g", 0)),
                "Fat": round(daily.get("fat_g", 0)),
            }
        )
    return pd.DataFrame(rows)


def render_dashboard():
    profile = _profile()
    phone = st.session_state.user_phone
    today = date.today()
    totals = database.get_daily_totals(phone, today)
    water = database.get_water(phone, today)
    calorie_goal = profile["calorie_goal"] or 0
    protein_goal = profile["protein_goal"] or 0
    carbs_goal = profile["carb_goal"] or 0
    fat_goal = profile["fat_goal"] or 0
    water_goal = profile["water_goal_ml"] or 0

    design_system.render_dashboard_hero(profile["name"], today)
    st.caption("Nutrition values are estimates; exercise activity is tracked separately.")

    with st.container(horizontal=True):
        st.metric(
            "Calories",
            f"{totals['calories']:.0f} / {calorie_goal} kcal",
            border=True,
            icon=":material/local_fire_department:",
        )
        st.metric(
            "Protein",
            f"{totals['protein_g']:.0f} / {protein_goal} g",
            border=True,
            icon=":material/fitness_center:",
        )
        st.metric(
            "Carbohydrates",
            f"{totals['carbs_g']:.0f} / {carbs_goal} g",
            border=True,
            icon=":material/grain:",
        )
        st.metric(
            "Fat",
            f"{totals['fat_g']:.0f} / {fat_goal} g",
            border=True,
            icon=":material/water_drop:",
        )
        st.metric(
            "Water",
            f"{water} / {water_goal} ml",
            border=True,
            icon=":material/local_drink:",
        )

    remaining = calorie_goal - totals["calories"]
    remaining_label = (
        f"{remaining:.0f} kcal remaining"
        if remaining >= 0
        else f"{abs(remaining):.0f} kcal over goal"
    )
    st.progress(
        min(totals["calories"] / calorie_goal, 1.0)
        if calorie_goal
        else 0.0,
        text=f"Daily calorie goal · {remaining_label}",
    )

    meal_col, goal_col = st.columns([1.5, 1], gap="large")
    with meal_col:
        st.subheader("Today's meals", icon=":material/restaurant:")
        meals = _today_meals(phone)
        if meals:
            for meal in meals:
                _render_meal_card(meal, compact=True)
        else:
            with st.container(border=True):
                st.write("No meals logged today.")
                st.caption("Scan your meal to get AI nutrition analysis.")

    with goal_col:
        st.subheader("Hydration", icon=":material/local_drink:")
        with st.container(border=True):
            st.metric("Intake today", f"{water} / {water_goal} ml")
            st.progress(
                min(water / water_goal, 1.0) if water_goal else 0.0,
                text="Approximate daily water target",
            )
            with st.container(horizontal=True):
                for amount in (250, 500, 750):
                    if st.button(
                        f"+{amount} ml",
                        icon=":material/add:",
                        key=f"dashboard_water_add_{amount}",
                    ):
                        database.add_water(phone, amount)
                        st.rerun()

        st.subheader("Weight goal")
        with st.container(border=True):
            current = float(profile["weight_kg"] or 0)
            starting = float(profile["starting_weight_kg"] or current)
            target = float(profile["target_weight_kg"] or current)
            total_change = abs(starting - target)
            if total_change:
                progress = min(
                    max(1 - abs(target - current) / total_change, 0),
                    1,
                )
            else:
                progress = 1.0
            st.metric("Current weight", f"{current:.1f} kg")
            st.caption(f"Target {target:.1f} kg")
            st.progress(progress, text=f"{progress * 100:.0f}% toward target")
            st.caption("Update weight and goals from the Goals page.")

    st.subheader("Exercise today", icon=":material/fitness_center:")
    plan_row = database.get_workout_plan(phone, week_start_for(today))
    workout_day = day_for_date(plan_row["plan"], today) if plan_row else None
    workout_logs = database.get_workout_logs(phone, today, today)
    completed_logs = [item for item in workout_logs if item["completed"]]
    active_minutes = sum(item["duration_minutes"] for item in completed_logs)
    if workout_day and workout_day["exercises"]:
        completed_count = sum(
            any(
                item["exercise_key"] == planned["key"] and item["completed"]
                for item in completed_logs
            )
            for planned in workout_day["exercises"]
        )
        exercise_label = f"{completed_count} / {len(workout_day['exercises'])} exercises"
    elif completed_logs:
        exercise_label = f"{len(completed_logs)} exercises logged"
    else:
        exercise_label = "No exercise logged"
    with st.container(border=True):
        st.metric("Workout activity", exercise_label)
        st.caption(
            f"{active_minutes:.0f} active minutes logged. Exercise is tracked separately; "
            "no exercise calories are subtracted from your food target."
        )
        if workout_day and workout_day["exercises"]:
            st.progress(
                completed_count / len(workout_day["exercises"]),
                text=f"Today's workout · {completed_count / len(workout_day['exercises']):.0%} complete",
            )
        elif not workout_day:
            st.caption("Open Exercise to create a personalized workout plan.")

    calorie_progress = min(totals["calories"] / calorie_goal, 1.0) if calorie_goal else 0.0
    protein_progress = min(totals["protein_g"] / protein_goal, 1.0) if protein_goal else 0.0
    water_progress = min(water / water_goal, 1.0) if water_goal else 0.0
    if workout_day and workout_day["rest"]:
        workout_progress = 1.0
        workout_status = "Recovery day"
    elif workout_day and workout_day["exercises"]:
        workout_progress = completed_count / len(workout_day["exercises"])
        workout_status = "Completed" if workout_progress >= 1 else f"{workout_progress:.0%} complete"
    else:
        workout_progress = 1.0 if completed_logs else 0.0
        workout_status = "Completed" if completed_logs else "Not completed"
    daily_progress = round(100 * (calorie_progress + protein_progress + water_progress + workout_progress) / 4)
    st.subheader("Today's goal", icon=":material/track_changes:")
    with st.container(border=True):
        st.progress(daily_progress / 100, text=f"Overall daily progress · {daily_progress}%")
        goal_columns = st.columns(4)
        goal_values = (
            ("Calories", f"{totals['calories']:.0f} / {calorie_goal} kcal"),
            ("Protein", f"{totals['protein_g']:.0f} / {protein_goal} g"),
            ("Water", f"{water} / {water_goal} ml"),
            ("Workout", workout_status),
        )
        for column, (label, value) in zip(goal_columns, goal_values):
            with column:
                st.caption(label)
                st.markdown(f"**{value}**")

    st.subheader("7-day calorie trend")
    week = _weekly_frame(phone)
    st.area_chart(week, x="Day", y="Calories", color="#648b49")
    st.caption("Approximate meal estimates saved in the last seven days.")


def _render_chat_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "image":
            st.image(message["content"])
        elif message["kind"] == "audio":
            st.audio(message["content"], format="audio/wav")
        elif message["role"] == "assistant":
            parsed = parse_meal_response(message["content"])
            if parsed and parsed.get("is_food"):
                score, categories = score_meal(parsed)
                parsed["nutrition_score"] = score
                text = format_meal_analysis(parsed)
                st.markdown(text)
                category_maximums = {
                    "Protein": 20,
                    "Vegetables/fiber": 20,
                    "Calories": 15,
                    "Fat": 15,
                    "Carbohydrates": 15,
                    "Food balance": 15,
                }
                st.caption(
                    "Score breakdown: "
                    + " · ".join(
                        f"{name} {value}/{category_maximums[name]}"
                        for name, value in categories.items()
                    )
                )
            elif parsed:
                st.write(parsed["reply"])
            else:
                st.write(message["content"])
        else:
            st.write(message["content"])


def _add_chat_message(role, kind, content):
    message = {"role": role, "kind": kind, "content": content}
    st.session_state.messages.append(message)
    _render_chat_message(message)


def render_scan_meal(ask_gemini):
    st.title("Scan your meal", icon=":material/photo_camera:")
    st.caption("Upload a photo or describe your meal. MacroSnap will estimate nutrition and save valid analyses to today's meals.")

    messages = st.session_state.messages
    if not messages:
        welcome = {
            "role": "assistant",
            "kind": "text",
            "content": st.session_state.welcome_message,
        }
        messages.append(welcome)

    for message in messages:
        _render_chat_message(message)

    user_input = st.chat_input(
        "Describe a meal, attach a photo, or record a voice question",
        accept_file=True,
        accept_audio=True,
        file_type=["jpg", "jpeg", "png", "webp"],
        max_upload_size=10,
        submit_mode="disable",
    )

    if not user_input:
        return

    photo = user_input.files[0] if user_input.files else None
    audio = user_input.audio
    text = user_input.text.strip()
    if photo is None and audio is None and not text:
        st.warning("Add a meal description, photo, or voice recording first.")
        return

    parts = []
    source = "image" if photo is not None else "text"

    if photo is not None:
        photo_bytes = photo.getvalue()
        mime_type = photo.type or mimetypes.guess_type(photo.name)[0] or ""
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            st.error("Please upload a JPG, PNG, or WEBP meal photo.")
            return
        if len(photo_bytes) > 10 * 1024 * 1024:
            st.error("That photo is too large. Choose an image under 10 MB.")
            return
        parts.append(
            types.Part.from_bytes(
                data=photo_bytes,
                mime_type=mime_type,
            )
        )
        _add_chat_message("user", "image", photo_bytes)

    if audio is not None:
        audio_bytes = audio.getvalue()
        parts.append(
            types.Part.from_bytes(
                data=audio_bytes,
                mime_type=audio.type,
            )
        )
        parts.append("Transcribe the food description in this voice recording and estimate the meal.")
        _add_chat_message("user", "audio", audio_bytes)

    if text:
        parts.append(text)
        _add_chat_message("user", "text", text)

    if photo is not None and not text:
        parts.append("Identify the food, estimate each portion size, and estimate the meal's nutrition.")

    profile = _profile() or {}
    parts.append(
        "Optional user context for practical personalization (do not repeat personal details): "
        + json.dumps(
            {
                "age": profile.get("age"),
                "weight_kg": profile.get("weight_kg"),
                "height_cm": profile.get("height_cm"),
                "activity_level": profile.get("activity_level"),
                "nutrition_goal": profile.get("goal"),
                "fitness_goal": profile.get("fitness_goal"),
                "dietary_preference": profile.get("dietary_preference"),
                "food_preferences": profile.get("food_preferences"),
                "foods_to_avoid": profile.get("foods_to_avoid"),
                "daily_targets": {
                    "calories": profile.get("calorie_goal"),
                    "protein_g": profile.get("protein_goal"),
                    "carbs_g": profile.get("carb_goal"),
                    "fat_g": profile.get("fat_goal"),
                },
            },
            ensure_ascii=False,
        )
    )

    with st.spinner("Analyzing your meal..."):
        answer = ask_gemini(parts)

    if not answer:
        answer = json.dumps(
            {
                "is_food": False,
                "reply": st.session_state.pop(
                    "gemini_error_message",
                    "I couldn't analyze that just now. Please try again in a moment.",
                ),
            }
        )
    else:
        meal = parse_meal_response(answer)
        if meal and meal.get("is_food"):
            score, categories = score_meal(meal)
            meal["nutrition_score"] = score
            meal["score_categories"] = categories
            meal["source"] = source
            try:
                database.save_meal(st.session_state.user_phone, meal)
            except Exception:
                st.error("The estimate is ready, but it could not be saved to meal history.")
        elif meal is None:
            answer = json.dumps(
                {
                    "is_food": False,
                    "reply": "I couldn't read a reliable nutrition estimate from that. Please try a clearer description or photo.",
                }
            )

    _add_chat_message("assistant", "text", answer)


def render_meal_history():
    phone = st.session_state.user_phone
    st.title("Meal history", icon=":material/restaurant:")
    st.caption("Saved meal estimates, with approximate portions and macros.")
    today = date.today()
    date_range = st.date_input(
        "Date range",
        value=(today - timedelta(days=6), today),
        max_value=today,
        key="meal_history_range",
    )
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
    elif isinstance(date_range, date):
        start_date = end_date = date_range
    else:
        start_date, end_date = today - timedelta(days=6), today

    meals = database.get_meals(
        phone,
        start_date=start_date,
        end_date=end_date,
        limit=500,
    )
    if not meals:
        st.info("No meals were saved in this date range yet.")
        return

    meals_by_date = {}
    for meal in meals:
        moment = datetime.fromisoformat(meal["created_at"])
        meals_by_date.setdefault(moment.date(), []).append((moment, meal))

    for meal_date in sorted(meals_by_date, reverse=True):
        day_label = (
            "Today"
            if meal_date == today
            else "Yesterday"
            if meal_date == today - timedelta(days=1)
            else meal_date.strftime("%A, %B %d")
        )
        st.subheader(day_label)
        for moment, meal in meals_by_date[meal_date]:
            food_items = ", ".join(
                item.get("name", "Food")
                for item in meal.get("food_items", [])
                if isinstance(item, dict)
            )
            with st.container(border=True):
                st.markdown(f"**{meal['meal_name']}**")
                st.caption(f"{moment.strftime('%I:%M %p')} · {meal['source'].title()} estimate")
                if food_items:
                    st.write(food_items)
                st.markdown(
                    f"**{meal['calories']:.0f} kcal** · Protein {meal['protein_g']:.0f} g · "
                    f"Carbs {meal['carbs_g']:.0f} g · Fat {meal['fat_g']:.0f} g"
                )
                with st.expander("View details"):
                    st.caption(
                        f"Nutrition score: {meal['nutrition_score']}/100 "
                        "(app heuristic, not a medical assessment)"
                    )
                    if meal.get("nutrition_notes"):
                        st.write(meal["nutrition_notes"])
                    for alternative in meal.get("alternatives", []):
                        st.write(f"{alternative['name']}: {alternative['reason']}")


def render_progress():
    phone = st.session_state.user_phone
    st.title("Progress", icon=":material/monitoring:")
    st.caption("Nutrition, body measurements, and workout trends from your saved history.")
    week = _weekly_frame(phone)

    chart_columns = st.columns(2, gap="large")
    chart_specs = [
        ("Calories", "kcal"),
        ("Protein", "g"),
        ("Carbs", "g"),
        ("Fat", "g"),
    ]
    for index, (metric, unit) in enumerate(chart_specs):
        with chart_columns[index % 2]:
            with st.container(border=True):
                st.subheader(metric)
                st.line_chart(
                    week,
                    x="Day",
                    y=metric,
                    y_label=unit,
                    height=220,
                )

    st.subheader("Weight history")
    history = database.get_weight_history(phone)
    if history:
        weight_frame = pd.DataFrame(history)
        weight_frame["Date"] = pd.to_datetime(weight_frame["recorded_on"])
        st.line_chart(
            weight_frame,
            x="Date",
            y="weight_kg",
            y_label="Weight (kg)",
        )
    else:
        st.info("Record your weight on the Goals page to start a trend.")

    measurements = database.get_body_measurements(phone)
    if measurements:
        fields = [
            field for field in ("waist_cm", "hip_cm", "chest_cm", "arm_cm", "thigh_cm")
            if any(row.get(field) is not None for row in measurements)
        ]
        if fields:
            st.subheader("Body measurements")
            selected_field = st.selectbox(
                "Measurement trend",
                fields,
                format_func=lambda field: f"{field.replace('_cm', '').title()} (cm)",
                key="progress_body_measurement",
            )
            measurement_frame = pd.DataFrame(measurements)
            measurement_frame["Date"] = pd.to_datetime(measurement_frame["measurement_date"])
            measurement_frame = measurement_frame.dropna(subset=[selected_field])
            st.line_chart(measurement_frame, x="Date", y=selected_field, y_label="cm")

    st.subheader("Workout consistency")
    today = date.today()
    workout_logs = database.get_workout_logs(phone, today - timedelta(days=27), today)
    if workout_logs:
        workout_frame = pd.DataFrame(workout_logs)
        completed_workouts = workout_frame[workout_frame["completed"].astype(bool)]
        st.metric("Completed workout days · 28 days", completed_workouts["workout_date"].nunique())
        if not completed_workouts.empty:
            duration_frame = completed_workouts.groupby(
                "workout_date", as_index=False
            )["duration_minutes"].sum()
            duration_frame = duration_frame.rename(
                columns={"workout_date": "Date", "duration_minutes": "Minutes"}
            )
            st.bar_chart(duration_frame, x="Date", y="Minutes")
    else:
        st.info("Log completed exercises to see your workout consistency and duration.")
    st.caption("Nutrition and weight values are estimates; progress varies by person.")


def render_goals():
    phone = st.session_state.user_phone
    profile = _profile()
    st.title("Goals and weight", icon=":material/track_changes:")
    st.caption("Targets are approximate and are not medical advice.")

    current = float(profile["weight_kg"] or 0)
    starting = float(profile["starting_weight_kg"] or current)
    target = float(profile["target_weight_kg"] or current)
    with st.form("weight_goal_form"):
        current_input = st.number_input(
            "Current weight (kg)",
            min_value=30.0,
            max_value=350.0,
            value=current,
            step=0.1,
        )
        target_input = st.number_input(
            "Target weight (kg)",
            min_value=30.0,
            max_value=350.0,
            value=target,
            step=0.1,
        )
        saved_weight = st.form_submit_button("Save weight and target")

    if saved_weight:
        updated = dict(profile)
        updated["weight_kg"] = current_input
        updated["target_weight_kg"] = target_input
        database.save_user(phone, updated)
        database.record_weight(phone, current_input)
        st.success("Weight and target saved.")
        st.rerun()

    distance = abs(starting - target)
    progress = min(max(1 - abs(target - current) / distance, 0), 1) if distance else 1
    st.metric("Progress toward target", f"{progress * 100:.0f}%")
    st.progress(progress)
    st.caption(f"Starting {starting:.1f} kg · Current {current:.1f} kg · Target {target:.1f} kg")
    with st.container(horizontal=True):
        st.metric("Daily calories", f"{profile['calorie_goal']} kcal")
        st.metric("Protein target", f"{profile['protein_goal']} g")
        st.metric("Water target", f"{profile['water_goal_ml']} ml")
        st.metric("Fitness goal", profile.get("fitness_goal", "Improve fitness"))

    history = database.get_weight_history(phone)
    if history:
        st.subheader("Weight history")
        frame = pd.DataFrame(history)
        frame["Date"] = pd.to_datetime(frame["recorded_on"])
        st.line_chart(frame, x="Date", y="weight_kg", y_label="Weight (kg)")


def render_water():
    phone = st.session_state.user_phone
    profile = _profile()
    goal = int(profile["water_goal_ml"] or 2500)
    intake = database.get_water(phone)
    st.title("Water tracker", icon=":material/local_drink:")
    st.metric("Today's water", f"{intake} / {goal} ml")
    st.progress(min(intake / goal, 1.0) if goal else 0.0)

    with st.container(horizontal=True):
        add_amount = None
        for amount in (250, 500, 750):
            if st.button(f"+{amount} ml", icon=":material/add:", key=f"water_add_{amount}"):
                add_amount = amount
        reset = st.button("Reset today", icon=":material/restart_alt:")
    if add_amount:
        database.add_water(phone, add_amount)
        st.rerun()
    if reset:
        database.reset_water(phone)
        st.rerun()
    st.caption("Water goal is a general tracking target, not individualized medical advice.")


def _meal_time_text(value):
    return datetime.strptime(value, "%H:%M").strftime("%I:%M %p").lstrip("0")


def _format_reminder_message(name, meal):
    foods = "\n".join(f"• {food}" for food in meal.get("foods", []))
    return (
        f"MacroSnap meal reminder for {name}\n\n"
        f"It's time for {meal['name'].lower()}!\n\n"
        f"Today's suggestion:\n{foods}\n\n"
        f"Estimated: {meal['calories']} kcal · "
        f"{meal['protein_g']} g protein\n"
        "Nutrition values are estimates. Enjoy your meal!"
    )


def _next_plan_meal(plan, now=None):
    current = now or datetime.now().astimezone()
    current_minutes = current.hour * 60 + current.minute
    meals = sorted(
        plan.get("meals", []),
        key=lambda meal: datetime.strptime(meal["time"], "%H:%M").hour * 60
        + datetime.strptime(meal["time"], "%H:%M").minute,
    )
    for meal in meals:
        meal_time = datetime.strptime(meal["time"], "%H:%M").time()
        if meal_time.hour * 60 + meal_time.minute >= current_minutes:
            return meal
    return meals[0] if meals else None


def render_meal_planner(generate_text, send_whatsapp):
    profile = _profile()
    phone = st.session_state.user_phone
    today = date.today()
    st.title("AI Smart Meal Scheduler", icon=":material/auto_awesome:")
    st.caption(
        "Personalized meal ideas and timing estimates, not medical advice. "
        "For allergies or medical nutrition needs, consult a qualified professional."
    )

    default_times = suggest_meal_times(
        profile.get("wake_time", "07:00"),
        profile.get("sleep_time", "23:00"),
    )
    settings = database.ensure_default_reminder_settings(phone, default_times)
    current_plan_row = database.get_daily_meal_plan(phone, today)
    current_plan = current_plan_row["plan"] if current_plan_row else None

    st.subheader("Reminder settings")
    with st.form("smart_meal_schedule_form"):
        reminders_enabled = st.checkbox(
            "Enable WhatsApp meal reminders",
            value=bool(profile.get("reminders_enabled", 0)),
        )
        updated_settings = {}
        for meal_type in MEAL_SLOT_TYPES:
            current_setting = settings.get(meal_type, {})
            scheduled_time = datetime.strptime(
                current_setting.get("scheduled_time", default_times[meal_type]),
                "%H:%M",
            ).time()
            with st.container(border=True):
                time_column, enabled_column = st.columns([1, 1])
                with time_column:
                    selected_time = st.time_input(
                        MEAL_SLOT_LABELS[meal_type],
                        value=scheduled_time,
                        key=f"smart_meal_time_{meal_type}",
                    )
                with enabled_column:
                    enabled = st.checkbox(
                        f"{MEAL_SLOT_LABELS[meal_type]} reminder",
                        value=bool(current_setting.get("enabled", 0)),
                        key=f"smart_meal_enabled_{meal_type}",
                    )
            updated_settings[meal_type] = {
                "scheduled_time": selected_time.strftime("%H:%M"),
                "enabled": enabled,
            }

        save_settings = st.form_submit_button("Save meal times and reminders")

    if save_settings:
        try:
            database.save_reminder_settings(phone, updated_settings)
            updated_profile = dict(profile)
            updated_profile["reminders_enabled"] = int(reminders_enabled)
            database.save_user(phone, updated_profile)
            st.success("Reminder times and settings saved.")
            st.rerun()
        except Exception:
            st.error("We couldn't save the reminder settings. Please try again.")

    totals = database.get_daily_totals(phone, today)
    age = profile.get("age")
    if age is None:
        st.warning("Add your age on the Profile page before generating a personalized schedule.")
    else:
        remaining = {
            "calories": max(0, round(float(profile["calorie_goal"] or 0) - totals["calories"])),
            "protein_g": max(0, round(float(profile["protein_goal"] or 0) - totals["protein_g"], 1)),
            "carbs_g": max(0, round(float(profile["carb_goal"] or 0) - totals["carbs_g"], 1)),
            "fat_g": max(0, round(float(profile["fat_goal"] or 0) - totals["fat_g"], 1)),
        }
        if int(age) < 18:
            st.info(
                "For users under 18, targets use a maintenance-style estimate and suggestions avoid weight-loss deficits. "
                "Discuss weight or nutrition concerns with a parent/guardian and a qualified professional."
            )

        st.write(
            f"Today's target: {profile['calorie_goal']} kcal · "
            f"{profile['protein_goal']} g protein · "
            f"{profile['carb_goal']} g carbs · {profile['fat_goal']} g fat"
        )
        if int(age) >= 18:
            st.caption(
                f"Already logged: {totals['calories']:.0f} kcal · "
                f"remaining estimate: {remaining['calories']} kcal"
            )

        if st.button(
            "Generate today's food plan",
            type="primary",
            icon=":material/auto_awesome:",
            disabled=age is None,
        ):
            schedule = {
                meal_type: settings.get(meal_type, {}).get(
                    "scheduled_time", default_times[meal_type]
                )
                for meal_type in MEAL_SLOT_TYPES
            }
            prompt = build_smart_meal_schedule_prompt(
                profile,
                schedule,
                remaining,
                totals,
            )
            with st.spinner("Planning today's meals around your schedule…"):
                result = generate_text(prompt, json_response=True)

            parsed = parse_daily_meal_plan(result or "", schedule)
            if parsed is None:
                st.error(
                    st.session_state.pop(
                        "gemini_error_message",
                        "Gemini didn't return a usable five-meal schedule. Please try again.",
                    )
                )
            elif not plan_respects_preferences(
                parsed,
                profile.get("dietary_preference", "Flexible"),
                profile.get("foods_to_avoid", ""),
            ):
                st.error(
                    "The generated suggestions conflicted with a food restriction. "
                    "Nothing was saved; update your restrictions or try again."
                )
            else:
                parsed.update(
                    {
                        "target_calories": remaining["calories"],
                        "daily_calorie_goal": int(profile["calorie_goal"] or 0),
                        "consumed_calories": round(totals["calories"]),
                        "age": int(age),
                        "minor_safe": int(age) < 18,
                    }
                )
                database.save_daily_meal_plan(phone, parsed, today)
                st.session_state.pop("selected_smart_meal", None)
                st.success("Today's personalized food plan was saved.")
                st.rerun()

    current_plan_row = database.get_daily_meal_plan(phone, today)
    current_plan = current_plan_row["plan"] if current_plan_row else None
    if current_plan:
        st.subheader("Today's AI food plan")
        st.caption(
            f"Daily target: {current_plan.get('daily_calorie_goal', current_plan.get('target_calories', 0))} kcal · "
            f"Plan total: {current_plan.get('total_calories', 0)} kcal · "
            f"Protein {current_plan.get('total_protein_g', 0)} g · "
            f"Carbs {current_plan.get('total_carbs_g', 0)} g · "
            f"Fat {current_plan.get('total_fat_g', 0)} g · estimates"
        )
        if current_plan.get("minor_safe"):
            st.info("Balanced, non-restrictive suggestions for a minor; no weight-loss deficit was applied.")
        for meal in current_plan.get("meals", []):
            with st.container(border=True):
                st.markdown(
                    f"**{_meal_time_text(meal['time'])} · {meal['name']}**"
                )
                st.write(" · ".join(meal["foods"]))
                st.caption(
                    f"~{meal['calories']} kcal · "
                    f"Protein {meal['protein_g']} g · "
                    f"Carbs {meal['carbs_g']} g · Fat {meal['fat_g']} g"
                )

        current_meal = st.session_state.get("selected_smart_meal")
        if st.button("What should I eat now?", icon=":material/restaurant:"):
            current_meal = _next_plan_meal(current_plan)
            st.session_state.selected_smart_meal = current_meal

        if current_meal:
            st.markdown(f"**Next meal: {current_meal['name']}**")
            st.write(" · ".join(current_meal["foods"]))
            st.caption(
                f"Estimated ~{current_meal['calories']} kcal · "
                f"Protein {current_meal['protein_g']} g"
            )
            if st.button("Send this to WhatsApp", icon=":material/send:"):
                message = _format_reminder_message(
                    profile["name"],
                    current_meal,
                )
                success, info = send_whatsapp(phone, profile["name"], message)
                if success:
                    st.success("Meal suggestion sent to WhatsApp.")
                else:
                    st.error(info)

        if current_plan.get("age", 18) >= 18:
            st.caption(
                "Already consumed today: "
                f"{totals['calories']:.0f} kcal. Remaining calorie estimate: "
                f"{max(0, profile['calorie_goal'] - totals['calories']):.0f} kcal."
            )


def render_profile():
    phone = st.session_state.user_phone
    profile = _profile()
    st.title("Personal profile", icon=":material/person:")
    st.caption("Update your profile and approximate nutrition targets.")

    genders = ["Female", "Male", "Other / prefer not to say"]
    activities = [
        "Sedentary",
        "Lightly active",
        "Moderately active",
        "Very active",
        "Extra active",
    ]
    goals = ["Lose weight", "Maintain weight", "Gain weight"]
    fitness_goals = list(FITNESS_GOALS)
    body_goals = list(BODY_GOALS)
    locations = list(WORKOUT_LOCATIONS)
    experience_levels = list(EXPERIENCE_LEVELS)
    equipment_options = list(EQUIPMENT_OPTIONS)
    age_options = ["Select age"] + [str(value) for value in range(13, 101)]
    selected_age = str(profile["age"]) if profile.get("age") else "Select age"
    dietary_options = ["Flexible", "Vegetarian", "Vegan", "Non-vegetarian"]
    wake_default = datetime.strptime(profile.get("wake_time") or "07:00", "%H:%M").time()
    sleep_default = datetime.strptime(profile.get("sleep_time") or "23:00", "%H:%M").time()

    with st.form("profile_form"):
        st.markdown("#### Personal information")
        name = st.text_input("Name", value=profile["name"])
        age = st.selectbox(
            "Age",
            age_options,
            index=age_options.index(selected_age) if selected_age in age_options else 0,
        )
        gender = st.selectbox(
            "Gender",
            genders,
            index=genders.index(profile["gender"]) if profile["gender"] in genders else 2,
        )
        height = st.number_input(
            "Height (cm)",
            min_value=100.0,
            max_value=250.0,
            value=float(profile["height_cm"] or 170),
            step=0.5,
        )
        weight = st.number_input(
            "Current weight (kg)",
            min_value=30.0,
            max_value=350.0,
            value=float(profile["weight_kg"] or 70),
            step=0.1,
        )
        target_weight = st.number_input(
            "Target weight (kg)",
            min_value=30.0,
            max_value=350.0,
            value=float(profile["target_weight_kg"] or profile["weight_kg"] or 70),
            step=0.1,
        )
        activity = st.selectbox(
            "Activity level",
            activities,
            index=activities.index(profile["activity_level"]) if profile["activity_level"] in activities else 2,
        )
        st.markdown("#### Nutrition goals")
        goal = st.selectbox(
            "Goal",
            goals,
            index=goals.index(profile["goal"]) if profile["goal"] in goals else 1,
        )
        st.markdown("#### Fitness goals")
        fitness_goal = st.selectbox(
            "Fitness goal",
            fitness_goals,
            index=fitness_goals.index(profile.get("fitness_goal", "Improve fitness")),
        )
        body_goal = st.selectbox(
            "Body goal",
            body_goals,
            index=body_goals.index(profile.get("body_goal", "Improve overall body shape")),
        )
        fitness_experience = st.selectbox(
            "Fitness experience",
            experience_levels,
            index=experience_levels.index(profile.get("fitness_experience", "Beginner")),
        )
        exercise_location = st.selectbox(
            "Where do you exercise?",
            locations,
            index=locations.index(profile.get("exercise_location", "Home")),
        )
        try:
            exercise_equipment = json.loads(profile.get("exercise_equipment", "[]"))
        except (TypeError, json.JSONDecodeError):
            exercise_equipment = []
        exercise_equipment = st.multiselect(
            "Available equipment",
            equipment_options,
            default=[item for item in exercise_equipment if item in equipment_options],
        )
        workout_duration = int(profile.get("available_workout_minutes", 20))
        workout_duration = st.selectbox(
            "Available workout time",
            WORKOUT_DURATIONS,
            index=(WORKOUT_DURATIONS.index(workout_duration)
                   if workout_duration in WORKOUT_DURATIONS else 2),
            format_func=lambda value: "60 minutes+" if value == 60 else f"{value} minutes",
        )
        st.markdown("##### Exercise preferences")
        exercise_preferences = st.text_input(
            "Exercise preferences",
            value=profile.get("exercise_preferences", ""),
            placeholder="Walking, low-impact movement, short sessions…",
        )
        st.markdown("#### Food preferences")
        preferences = st.text_input(
            "Food preferences",
            value=profile.get("food_preferences", ""),
            placeholder="Spice level, cuisine, favorite foods…",
        )
        dietary_preference = st.selectbox(
            "Diet preference",
            dietary_options,
            index=(
                dietary_options.index(profile["dietary_preference"])
                if profile.get("dietary_preference") in dietary_options
                else 0
            ),
        )
        foods_to_avoid = st.text_input(
            "Foods or ingredients to avoid",
            value=profile.get("foods_to_avoid", ""),
            placeholder="Peanuts, mushrooms, shellfish…",
        )
        st.markdown("#### Schedule")
        wake_time = st.time_input("Wake-up time", value=wake_default)
        sleep_time = st.time_input("Sleep time", value=sleep_default)
        daily_schedule = st.text_area(
            "Typical work/college schedule",
            value=profile.get("daily_schedule", ""),
            placeholder="Classes 9:00 AM–3:00 PM",
        )
        update_profile = st.form_submit_button("Save profile")

    if update_profile:
        if not name.strip() or age == "Select age":
            st.error("Enter your name and select your age.")
        else:
            try:
                updated = dict(profile)
                updated.update(
                    {
                        "name": name.strip(),
                        "age": int(age),
                        "gender": gender,
                        "height_cm": height,
                        "weight_kg": weight,
                        "target_weight_kg": target_weight,
                        "activity_level": activity,
                        "goal": goal,
                        "fitness_goal": fitness_goal,
                        "body_goal": body_goal,
                        "fitness_experience": fitness_experience,
                        "exercise_location": exercise_location,
                        "exercise_equipment": exercise_equipment,
                        "available_workout_minutes": workout_duration,
                        "exercise_preferences": exercise_preferences.strip(),
                        "food_preferences": preferences.strip(),
                        "dietary_preference": dietary_preference,
                        "foods_to_avoid": foods_to_avoid.strip(),
                        "wake_time": wake_time.strftime("%H:%M"),
                        "sleep_time": sleep_time.strftime("%H:%M"),
                        "daily_schedule": daily_schedule.strip(),
                    }
                )
                updated.update(calculate_profile_targets(updated))
                database.save_user(phone, updated)
                database.record_weight(phone, weight)
                st.success("Profile and estimated targets updated.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    st.subheader("Daily targets")
    with st.form("targets_form"):
        calories = st.number_input(
            "Calories (kcal)", min_value=1000, max_value=10000,
            value=int(profile["calorie_goal"] or 2000), step=50,
        )
        protein = st.number_input(
            "Protein (g)", min_value=0.0, max_value=1000.0,
            value=float(profile["protein_goal"] or 100), step=5.0,
        )
        carbs = st.number_input(
            "Carbohydrates (g)", min_value=0.0, max_value=1500.0,
            value=float(profile["carb_goal"] or 250), step=5.0,
        )
        fat = st.number_input(
            "Fat (g)", min_value=0.0, max_value=1000.0,
            value=float(profile["fat_goal"] or 65), step=5.0,
        )
        water = st.number_input(
            "Water (ml)", min_value=250, max_value=10000,
            value=int(profile["water_goal_ml"] or 2500), step=250,
        )
        save_targets = st.form_submit_button("Save daily targets")

    if save_targets:
        updated = dict(profile)
        updated.update(
            {
                "calorie_goal": calories,
                "protein_goal": protein,
                "carb_goal": carbs,
                "fat_goal": fat,
                "water_goal_ml": water,
            }
        )
        database.save_user(phone, updated)
        st.success("Daily targets saved.")
        st.rerun()

    st.caption(f"WhatsApp summaries go to {phone}.")


def render_settings(twilio_configured=False, gemini_diagnostic=None):
    phone = st.session_state.user_phone
    profile = _profile()
    workout_reminder = database.get_workout_reminder(phone) or {}
    summary_reminder = database.get_daily_summary_reminder(phone) or {}
    try:
        workout_time = datetime.strptime(
            workout_reminder.get("scheduled_time", "18:00"), "%H:%M"
        ).time()
    except ValueError:
        workout_time = datetime.strptime("18:00", "%H:%M").time()
    try:
        summary_time = datetime.strptime(
            summary_reminder.get("scheduled_time", "20:00"), "%H:%M"
        ).time()
    except ValueError:
        summary_time = datetime.strptime("20:00", "%H:%M").time()

    st.title("Settings", icon=":material/settings:")
    st.caption("Manage account notifications and scheduled delivery.")
    with st.container(border=True):
        st.subheader("WhatsApp notifications", icon=":material/send:")
        if twilio_configured:
            st.badge("Connected", icon=":material/check_circle:", color="green")
        else:
            st.badge("Not connected", icon=":material/warning:", color="orange")
        st.caption("Scheduled delivery runs in the separate reminder worker.")

        with st.form("notification_settings_form"):
            meal_enabled = st.toggle(
                "Meal reminders",
                value=bool(profile.get("reminders_enabled", 0)),
            )
            st.caption("Choose individual meal times and meal slots in Meal Planner.")
            workout_enabled = st.toggle(
                "Workout reminders",
                value=bool(workout_reminder.get("enabled", 0)),
            )
            workout_time_input = st.time_input(
                "Workout reminder time", value=workout_time
            )
            summary_enabled = st.toggle(
                "Daily summary",
                value=bool(summary_reminder.get("enabled", 0)),
            )
            summary_time_input = st.time_input(
                "Daily summary time", value=summary_time
            )
            save_notifications = st.form_submit_button(
                "Save notification settings",
                type="primary",
                icon=":material/save:",
            )

        if save_notifications:
            updated_profile = dict(profile)
            updated_profile["reminders_enabled"] = int(meal_enabled)
            database.save_user(phone, updated_profile)
            database.save_workout_reminder(
                phone,
                workout_enabled,
                workout_time_input.strftime("%H:%M"),
                workout_reminder.get("focus", "Full body"),
                workout_reminder.get("duration_minutes", 20),
            )
            database.save_daily_summary_reminder(
                phone,
                summary_enabled,
                summary_time_input.strftime("%H:%M"),
            )
            st.success("Notification settings saved.")
            st.rerun()

    with st.container(border=True):
        st.subheader("Gemini food and exercise analysis", icon=":material/auto_awesome:")
        st.caption("The app tries your configured Gemini model and available API models when it is unavailable.")
        if st.button("Test Gemini connection", key="test_gemini_connection"):
            if gemini_diagnostic is None:
                st.error("Gemini diagnostics are unavailable.")
            else:
                with st.spinner("Checking Gemini model access…"):
                    connected, message = gemini_diagnostic()
                if connected:
                    st.success(message)
                else:
                    st.error(message)


def _next_meal_suggestion_prompt(profile, totals):
    context = {
        "goal": profile.get("goal"),
        "fitness_goal": profile.get("fitness_goal"),
        "dietary_preference": profile.get("dietary_preference"),
        "food_preferences": profile.get("food_preferences"),
        "foods_to_avoid": profile.get("foods_to_avoid"),
        "daily_targets": {
            "calories": profile.get("calorie_goal"),
            "protein_g": profile.get("protein_goal"),
            "carbs_g": profile.get("carb_goal"),
            "fat_g": profile.get("fat_goal"),
        },
        "consumed_today": totals,
    }
    return (
        "Suggest one practical next meal for this MacroSnap user. Respect the dietary preference, "
        "food preferences, and foods to avoid. Keep nutrition estimates approximate, avoid medical "
        "claims, and give a flexible time and portion. Return JSON only with string fields "
        '"meal", "time", and "portion". User context: '
        + json.dumps(context, ensure_ascii=False)
    )


def render_whatsapp(send_whatsapp, twilio_issues=None, generate_suggestion=None):
    profile = _profile()
    phone = st.session_state.user_phone
    today = date.today()
    totals = database.get_daily_totals(phone, today)
    meals = _today_meals(phone)
    water = database.get_water(phone, today)
    workout_logs = database.get_workout_logs(phone, today, today)
    completed_workouts = [item for item in workout_logs if item["completed"]]
    exercise_minutes = sum(item["duration_minutes"] for item in completed_workouts)
    suggestion_key = f"whatsapp_meal_suggestion_{phone}_{today.isoformat()}"
    suggestion = st.session_state.get(suggestion_key) or whatsapp_service.default_next_meal_suggestion(profile)

    st.title("WhatsApp", icon=":material/send:")
    if not twilio_issues:
        st.badge("Connected", icon=":material/check_circle:", color="green")
    else:
        st.badge("Not connected", icon=":material/warning:", color="orange")
        st.warning("WhatsApp configuration needs attention: " + ", ".join(twilio_issues) + ".")

    if generate_suggestion and st.button(
        "Generate an AI next-meal suggestion",
        icon=":material/auto_awesome:",
        key="generate_whatsapp_meal_suggestion",
    ):
        with st.spinner("Preparing a personalized suggestion…"):
            generated = generate_suggestion(_next_meal_suggestion_prompt(profile, totals))
        if generated:
            st.session_state[suggestion_key] = generated
            st.rerun()
        else:
            st.error(
                st.session_state.pop(
                    "gemini_error_message",
                    "A suggestion could not be generated right now. The default suggestion is still available.",
                )
            )

    suggestion = st.session_state.get(suggestion_key) or suggestion
    summary = whatsapp_service.build_daily_summary(
        profile,
        totals,
        water,
        exercise_minutes,
        meals,
        today,
        suggestion=suggestion,
    )
    st.subheader("Today's summary preview")
    st.caption("Your saved profile number is used as the WhatsApp destination.")
    with st.container(border=True):
        st.text(summary)

    if st.button("Send today's summary", type="primary", icon=":material/send:"):
        success, info = send_whatsapp(phone, profile["name"], summary)
        if success:
            st.success("✅ Today's summary was sent to WhatsApp.")
        else:
            st.error(info)

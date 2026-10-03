import json
import re
from datetime import date, timedelta


FITNESS_GOALS = (
    "Lose weight",
    "Lose body fat",
    "Build muscle",
    "Gain weight",
    "Maintain weight",
    "Improve fitness",
    "Improve strength",
    "Improve endurance",
    "General health",
)

BODY_GOALS = (
    "Reduce overall body fat",
    "Reduce waist size",
    "Reduce belly fat appearance",
    "Improve arms",
    "Improve legs",
    "Improve shoulders",
    "Improve chest",
    "Improve back",
    "Improve overall body shape",
)

BODY_AREAS = (
    "Full body", "Core", "Legs", "Glutes", "Arms", "Shoulders",
    "Chest", "Back", "Cardio", "Flexibility",
)

EXPERIENCE_LEVELS = ("Beginner", "Intermediate", "Advanced")
WORKOUT_LOCATIONS = ("Home", "Gym", "Outdoor", "No equipment")
EQUIPMENT_OPTIONS = (
    "Dumbbells", "Resistance bands", "Treadmill", "Exercise bike",
    "Bench", "Machines",
)
WORKOUT_DURATIONS = (10, 15, 20, 30, 45, 60)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


EXERCISES = (
    {
        "key": "bodyweight_squat",
        "name": "Bodyweight squat",
        "areas": ("Legs", "Glutes"),
        "target": "Quadriceps, glutes, and trunk stabilizers",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 3,
        "reps": "8-12",
        "rest_sec": 60,
        "duration_min": 6,
        "movement": "squat",
        "instructions": (
            "Stand with feet about shoulder-width apart.",
            "Brace gently and send your hips back as your knees bend.",
            "Lower only as far as feels controlled and comfortable.",
            "Press through your whole foot to stand tall again.",
        ),
        "breathing": "Inhale as you lower; exhale as you stand.",
        "mistakes": "Knees collapsing inward, heels lifting, or forcing extra depth.",
        "safety": "Use a comfortable range and stop if you feel sharp or worsening pain.",
        "beginner": "Sit back toward a sturdy chair and stand up with support nearby.",
        "advanced": "Add a slow three-second lowering phase before standing.",
    },
    {
        "key": "reverse_lunge",
        "name": "Supported reverse lunge",
        "areas": ("Legs", "Glutes"),
        "target": "Quadriceps and glutes",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 2,
        "reps": "6-10 each side",
        "rest_sec": 75,
        "duration_min": 7,
        "movement": "lunge",
        "instructions": (
            "Stand tall beside a wall or sturdy support.",
            "Step one foot back and keep your front foot flat.",
            "Bend both knees only as far as comfortable.",
            "Push through the front foot to return; switch sides.",
        ),
        "breathing": "Inhale as you step back and lower; exhale to return.",
        "mistakes": "Taking an unstable step, letting the front heel lift, or forcing depth.",
        "safety": "Hold support and shorten the step if balance or knees feel uncomfortable.",
        "beginner": "Practice a small step-back without lowering deeply.",
        "advanced": "Use a smooth, controlled reverse lunge without support.",
    },
    {
        "key": "glute_bridge",
        "name": "Glute bridge",
        "areas": ("Glutes", "Legs", "Core"),
        "target": "Glutes and hamstrings",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 3,
        "reps": "10-15",
        "rest_sec": 45,
        "duration_min": 5,
        "movement": "bridge",
        "instructions": (
            "Lie on your back with knees bent and feet flat.",
            "Gently brace your trunk and press through your feet.",
            "Lift your hips until your body forms a comfortable line.",
            "Pause briefly, then lower with control.",
        ),
        "breathing": "Exhale as your hips lift; inhale as you lower.",
        "mistakes": "Arching the lower back or pushing through the neck.",
        "safety": "Keep the movement comfortable and avoid pushing into back pain.",
        "beginner": "Lift your hips only a few inches.",
        "advanced": "Pause for two seconds at the top of each repetition.",
    },
    {
        "key": "calf_raise",
        "name": "Supported calf raise",
        "areas": ("Legs",),
        "target": "Calf muscles",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 2,
        "reps": "10-15",
        "rest_sec": 45,
        "duration_min": 4,
        "movement": "raise",
        "instructions": (
            "Stand near a wall or chair and hold it lightly.",
            "Keep your feet pointing forward and rise onto your toes.",
            "Pause briefly at a comfortable height.",
            "Lower your heels slowly to the floor.",
        ),
        "breathing": "Breathe steadily throughout the movement.",
        "mistakes": "Bouncing quickly or rolling the ankles outward.",
        "safety": "Use support for balance and stay within a pain-free range.",
        "beginner": "Use both feet and hold support with both hands.",
        "advanced": "Slow the lowering phase to three seconds.",
    },
    {
        "key": "wall_pushup",
        "name": "Wall push-up",
        "areas": ("Chest", "Arms", "Shoulders"),
        "target": "Chest, triceps, and shoulders",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 3,
        "reps": "8-12",
        "rest_sec": 60,
        "duration_min": 5,
        "movement": "pushup",
        "instructions": (
            "Face a clear wall and place hands around chest height.",
            "Step back until your body forms a straight, comfortable line.",
            "Bend your elbows and bring your chest toward the wall.",
            "Press the wall away to return to the start.",
        ),
        "breathing": "Inhale as you approach the wall; exhale as you press away.",
        "mistakes": "Flaring elbows wide or letting the hips sag.",
        "safety": "Use a stable wall and keep wrists comfortable.",
        "beginner": "Stand closer to the wall to reduce effort.",
        "advanced": "Step farther from the wall while keeping good control.",
    },
    {
        "key": "incline_pushup",
        "name": "Incline push-up",
        "areas": ("Chest", "Arms", "Shoulders", "Core"),
        "target": "Chest, triceps, shoulders, and trunk stabilizers",
        "difficulty": "Beginner",
        "equipment": ("Bench",),
        "sets": 3,
        "reps": "6-12",
        "rest_sec": 75,
        "duration_min": 6,
        "movement": "pushup",
        "instructions": (
            "Place hands on a stable, non-slip counter or bench.",
            "Walk your feet back and align your head, trunk, and legs.",
            "Bend your elbows and lower your chest toward the surface.",
            "Press away and keep your body aligned.",
        ),
        "breathing": "Inhale as you lower; exhale as you press away.",
        "mistakes": "Using an unstable surface or letting the hips sag.",
        "safety": "Check that the surface cannot slide or tip before starting.",
        "beginner": "Use a higher, sturdy surface or do wall push-ups.",
        "advanced": "Use a lower stable surface while maintaining alignment.",
    },
    {
        "key": "dumbbell_row",
        "name": "Supported dumbbell row",
        "areas": ("Back", "Arms", "Shoulders"),
        "target": "Upper back and arms",
        "difficulty": "Beginner",
        "equipment": ("Dumbbells", "Bench"),
        "sets": 3,
        "reps": "8-12 each side",
        "rest_sec": 60,
        "duration_min": 7,
        "movement": "row",
        "instructions": (
            "Support one hand on a stable bench or chair.",
            "Keep your back long and hold a light dumbbell in the other hand.",
            "Draw your elbow toward your hip without twisting your trunk.",
            "Lower slowly and complete the other side.",
        ),
        "breathing": "Exhale as you row; inhale as the weight lowers.",
        "mistakes": "Rounding the back, shrugging, or swinging the weight.",
        "safety": "Start with a light load and use a sturdy support surface.",
        "beginner": "Practice the rowing motion without weight.",
        "advanced": "Pause for one second with the elbow near your side.",
    },
    {
        "key": "dead_bug",
        "name": "Dead bug",
        "areas": ("Core",),
        "target": "Deep trunk stabilizers",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 2,
        "reps": "6-10 each side",
        "rest_sec": 45,
        "duration_min": 5,
        "movement": "core",
        "instructions": (
            "Lie on your back with knees bent above your hips and arms raised.",
            "Gently brace your trunk while keeping your back comfortable.",
            "Slowly lower one heel and the opposite arm toward the floor.",
            "Return to the start and alternate sides.",
        ),
        "breathing": "Breathe out as your arm and heel move away; breathe in to return.",
        "mistakes": "Rushing or allowing the back to arch uncomfortably.",
        "safety": "Use a smaller range if your back feels strained.",
        "beginner": "Move only one heel at a time and keep arms still.",
        "advanced": "Extend the leg farther while maintaining control.",
    },
    {
        "key": "incline_plank",
        "name": "Incline plank hold",
        "areas": ("Core", "Shoulders"),
        "target": "Trunk and shoulder stabilizers",
        "difficulty": "Beginner",
        "equipment": ("Bench",),
        "sets": 3,
        "reps": "15-30 sec",
        "rest_sec": 45,
        "duration_min": 4,
        "movement": "plank",
        "instructions": (
            "Place your hands on a stable raised surface.",
            "Step back and align your head, trunk, and legs.",
            "Brace gently and hold while breathing normally.",
            "End the hold before your position starts to change.",
        ),
        "breathing": "Keep breathing steadily; do not hold your breath.",
        "mistakes": "Hips sagging, hips lifting too high, or breath holding.",
        "safety": "Choose a stable surface and stop if you feel pain or dizziness.",
        "beginner": "Stand closer to the surface to reduce the hold difficulty.",
        "advanced": "Use a lower stable surface and keep the hold short and controlled.",
    },
    {
        "key": "brisk_walk",
        "name": "Brisk walk",
        "areas": ("Cardio", "Legs", "Full body"),
        "target": "Heart and whole-body aerobic fitness",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 1,
        "reps": "Comfortable continuous pace",
        "rest_sec": 0,
        "duration_min": 10,
        "movement": "walk",
        "instructions": (
            "Choose a familiar, safe route or clear indoor space.",
            "Start with an easy pace for a few minutes.",
            "Walk at a pace that still allows you to speak in short sentences.",
            "Slow down gradually at the end.",
        ),
        "breathing": "Breathe comfortably and slow down if conversation becomes difficult.",
        "mistakes": "Starting too fast or continuing in unsafe weather or surroundings.",
        "safety": "Use safe footwear and a route that suits your mobility and environment.",
        "beginner": "Use an easy pace and short intervals with breaks as needed.",
        "advanced": "Add short brisk intervals only if they feel comfortable.",
    },
    {
        "key": "march_in_place",
        "name": "March in place",
        "areas": ("Cardio", "Legs", "Full body"),
        "target": "Whole-body aerobic fitness and coordination",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 1,
        "reps": "Comfortable continuous pace",
        "rest_sec": 0,
        "duration_min": 5,
        "movement": "walk",
        "instructions": (
            "Stand in a clear space near a stable support if needed.",
            "March gently, lifting each foot only as high as comfortable.",
            "Move your arms naturally and keep your posture relaxed.",
            "Slow the pace or pause whenever needed.",
        ),
        "breathing": "Breathe steadily and keep a comfortable pace.",
        "mistakes": "Lifting knees too high or moving faster than feels controlled.",
        "safety": "Keep the floor clear and use support if balance is uncertain.",
        "beginner": "March slowly while holding a stable counter.",
        "advanced": "Increase the pace slightly without losing control.",
    },
    {
        "key": "standing_mobility",
        "name": "Standing mobility flow",
        "areas": ("Flexibility", "Full body"),
        "target": "Gentle shoulder, hip, and ankle mobility",
        "difficulty": "Beginner",
        "equipment": (),
        "sets": 1,
        "reps": "5-8 comfortable repetitions",
        "rest_sec": 0,
        "duration_min": 5,
        "movement": "mobility",
        "instructions": (
            "Stand comfortably with feet about hip-width apart.",
            "Make slow shoulder circles within a comfortable range.",
            "Shift weight gently side to side and bend your ankles softly.",
            "Move without bouncing or forcing a stretch.",
        ),
        "breathing": "Keep breathing naturally throughout each movement.",
        "mistakes": "Bouncing or pushing through a painful range.",
        "safety": "Keep movements small and stop if pain, numbness, or dizziness occurs.",
        "beginner": "Hold a stable support and make smaller movements.",
        "advanced": "Add a few extra controlled repetitions, not forceful range.",
    },
)

EXERCISE_BY_KEY = {exercise["key"]: exercise for exercise in EXERCISES}


def available_exercises(area="Full body", location="Home", equipment=()):
    available_equipment = set(equipment or ())
    results = []
    for exercise in EXERCISES:
        if area != "Full body" and area not in exercise["areas"]:
            continue
        if any(item not in available_equipment for item in exercise["equipment"]):
            continue
        if location in ("Outdoor", "No equipment") and exercise["equipment"]:
            continue
        results.append(exercise)
    return results


def week_start_for(day=None):
    selected_day = day or date.today()
    return selected_day - timedelta(days=selected_day.weekday())


def default_workout_plan(profile, week_start=None):
    start = week_start or week_start_for()
    level = profile.get("fitness_experience", "Beginner")
    area = profile.get("body_area_focus", "Full body")
    if area not in BODY_AREAS:
        area = "Full body"
    equipment = profile.get("exercise_equipment", [])
    if isinstance(equipment, str):
        try:
            equipment = json.loads(equipment)
        except json.JSONDecodeError:
            equipment = []
    choices = available_exercises(area, profile.get("exercise_location", "Home"), equipment)
    if not choices:
        choices = available_exercises("Full body", profile.get("exercise_location", "Home"), equipment)
    strength = [exercise for exercise in choices if "Cardio" not in exercise["areas"] and "Flexibility" not in exercise["areas"]]
    cardio = [exercise for exercise in choices if "Cardio" in exercise["areas"]]
    mobility = [exercise for exercise in choices if "Flexibility" in exercise["areas"]]
    if not strength:
        strength = list(choices[:4])
    if not cardio:
        cardio = [EXERCISE_BY_KEY["brisk_walk"]]
    if not mobility:
        mobility = [EXERCISE_BY_KEY["standing_mobility"]]

    workout_minutes = int(profile.get("available_workout_minutes", 20) or 20)
    strength_keys = [exercise["key"] for exercise in strength[:4]]
    cardio_key = cardio[0]["key"]
    mobility_key = mobility[0]["key"]
    weekly_sessions = {
        "Monday": ("Full-body strength", strength_keys),
        "Tuesday": ("Light cardio and mobility", [cardio_key, mobility_key]),
        "Wednesday": ("Strength and movement", strength_keys[:3]),
        "Thursday": ("Recovery", []),
        "Friday": ("Full-body strength", strength_keys),
        "Saturday": ("Easy cardio", [cardio_key, mobility_key]),
        "Sunday": ("Rest", []),
    }
    if profile.get("fitness_goal") == "Improve endurance":
        weekly_sessions["Wednesday"] = ("Easy cardio", [cardio_key, mobility_key])
        weekly_sessions["Friday"] = ("Full-body strength", strength_keys[:3])

    days = []
    for offset, weekday in enumerate(WEEKDAYS):
        focus, keys = weekly_sessions[weekday]
        planned_exercises = _fit_exercises(
            [serialize_exercise(EXERCISE_BY_KEY[key], level) for key in keys],
            workout_minutes,
        )
        days.append(
            {
                "date": (start + timedelta(days=offset)).isoformat(),
                "day": weekday,
                "focus": focus,
                "duration_minutes": workout_minutes if keys else 0,
                "rest": not keys,
                "warmup": "Start with 3-5 minutes of comfortable walking or gentle movement.",
                "cooldown": "Finish with 2-3 minutes of easy movement and relaxed breathing.",
                "exercises": planned_exercises,
            }
        )
    return {"week_start": start.isoformat(), "days": days}


def serialize_exercise(exercise, level="Beginner"):
    return {
        "key": exercise["key"],
        "name": exercise["name"],
        "sets": exercise["sets"],
        "reps": exercise["reps"],
        "rest_sec": exercise["rest_sec"],
        "duration_min": exercise["duration_min"],
        "difficulty": level if level in EXPERIENCE_LEVELS else exercise["difficulty"],
    }


def _fit_exercises(exercises, available_minutes):
    remaining = max(1, int(available_minutes) - 5)
    fitted = []
    for exercise in exercises:
        if remaining <= 0:
            break
        item = dict(exercise)
        item["duration_min"] = min(max(1, int(item["duration_min"])), remaining)
        remaining -= item["duration_min"]
        fitted.append(item)
    return fitted


def build_workout_plan_prompt(profile, recent_history, week_start, measurements=None):
    equipment = profile.get("exercise_equipment", [])
    if isinstance(equipment, str):
        try:
            equipment = json.loads(equipment)
        except json.JSONDecodeError:
            equipment = []
    context = {
        "age": profile.get("age"),
        "height_cm": profile.get("height_cm"),
        "weight_kg": profile.get("weight_kg"),
        "target_weight_kg": profile.get("target_weight_kg"),
        "fitness_goal": profile.get("fitness_goal", "Improve fitness"),
        "body_goal": profile.get("body_goal", "Improve overall body shape"),
        "body_area_focus": profile.get("body_area_focus", "Full body"),
        "fitness_experience": profile.get("fitness_experience", "Beginner"),
        "activity_level": profile.get("activity_level"),
        "exercise_location": profile.get("exercise_location", "Home"),
        "available_equipment": equipment,
        "available_minutes_per_workout": profile.get("available_workout_minutes", 20),
        "exercise_preferences": str(profile.get("exercise_preferences", ""))[:300],
        "current_date": date.today().isoformat(),
        "optional_measurements": {
            field: measurements.get(field)
            for field in ("weight_kg", "waist_cm", "hip_cm", "chest_cm", "arm_cm", "thigh_cm")
            if measurements and measurements.get(field) is not None
        },
        "recent_workouts": [
            {
                field: workout.get(field)
                for field in (
                    "workout_date", "exercise_name", "sets_completed",
                    "reps_completed", "duration_minutes", "difficulty", "completed",
                )
            }
            for workout in recent_history[:20]
        ],
        "week_start": week_start.isoformat(),
    }
    library = [
        {
            "key": exercise["key"],
            "name": exercise["name"],
            "areas": exercise["areas"],
            "equipment": exercise["equipment"],
            "difficulty": exercise["difficulty"],
        }
        for exercise in EXERCISES
    ]
    return (
        "Create an editable, conservative 7-day workout plan as one valid JSON object. "
        "Use only exercise keys in the supplied library; do not invent exercises. "
        "Use days Monday through Sunday, include recovery/rest days, and keep every session "
        "within the user's available minutes, counting the warm-up and cool-down too. Beginners need manageable volume and easy "
        "modifications. Never prescribe extreme workouts or diagnose conditions. For any "
        "body-area goal, explain that training can strengthen the area but cannot selectively "
        "remove fat there; overall fat loss depends on energy balance and individual physiology. "
        "Do not promise a weight or measurement change. Return JSON with shape: "
        '{"days":[{"day":"Monday","focus":"...","duration_minutes":20,"rest":false,'
        '"warmup":"...","cooldown":"...","exercises":[{"key":"bodyweight_squat",'
        '"sets":3,"reps":"8-12","rest_sec":60,"duration_min":6}]}]}. '
        "For rest days set rest=true, duration_minutes=0, and exercises=[]. "
        "Keep all coaching factual, concise, and non-medical.\n\n"
        f"User context:\n{json.dumps(context, ensure_ascii=False)}\n\n"
        f"Exercise library:\n{json.dumps(library, ensure_ascii=False)}"
    )


def parse_workout_plan(response_text, profile, week_start):
    text = str(response_text or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("days"), list):
        return None

    maximum_minutes = int(profile.get("available_workout_minutes", 20) or 20)
    experience = profile.get("fitness_experience", "Beginner")
    equipment = profile.get("exercise_equipment", [])
    if isinstance(equipment, str):
        try:
            equipment = json.loads(equipment)
        except json.JSONDecodeError:
            equipment = []
    allowed_keys = {
        item["key"]
        for item in available_exercises(
            "Full body",
            profile.get("exercise_location", "Home"),
            equipment,
        )
    }
    by_day = {
        str(item.get("day", "")).strip().casefold(): item
        for item in payload["days"]
        if isinstance(item, dict)
    }
    days = []
    start = week_start
    for offset, weekday in enumerate(WEEKDAYS):
        raw = by_day.get(weekday.casefold(), {})
        raw_exercises = raw.get("exercises", [])
        if not isinstance(raw_exercises, list):
            raw_exercises = []
        exercises = []
        time_budget = max(1, maximum_minutes - 5)
        for raw_exercise in raw_exercises:
            if len(exercises) >= 6 or time_budget <= 0:
                break
            item = {"key": raw_exercise} if isinstance(raw_exercise, str) else raw_exercise
            if not isinstance(item, dict):
                continue
            catalog = EXERCISE_BY_KEY.get(str(item.get("key", "")))
            if catalog is None or catalog["key"] not in allowed_keys:
                continue
            exercise = serialize_exercise(catalog, experience)
            try:
                exercise["sets"] = max(1, min(5, int(item.get("sets", exercise["sets"]))))
            except (TypeError, ValueError):
                pass
            exercise["reps"] = str(item.get("reps", exercise["reps"]))[:24]
            try:
                exercise["rest_sec"] = max(0, min(180, int(item.get("rest_sec", exercise["rest_sec"]))))
            except (TypeError, ValueError):
                pass
            try:
                requested_duration = max(1, min(maximum_minutes, int(item.get("duration_min", exercise["duration_min"]))))
                exercise["duration_min"] = min(requested_duration, time_budget)
                time_budget -= exercise["duration_min"]
            except (TypeError, ValueError):
                pass
            exercises.append(exercise)

        is_rest = bool(raw.get("rest", False)) or not exercises
        try:
            duration = max(0, min(maximum_minutes, int(raw.get("duration_minutes", maximum_minutes if exercises else 0))))
        except (TypeError, ValueError):
            duration = maximum_minutes if exercises else 0
        days.append(
            {
                "date": (start + timedelta(days=offset)).isoformat(),
                "day": weekday,
                "focus": str(raw.get("focus", "Rest and recovery" if is_rest else "Workout"))[:80],
                "duration_minutes": 0 if is_rest else duration,
                "rest": is_rest,
                "warmup": str(raw.get("warmup", "Start with 3-5 minutes of comfortable movement."))[:240],
                "cooldown": str(raw.get("cooldown", "Finish with easy movement and relaxed breathing."))[:240],
                "exercises": [] if is_rest else exercises,
            }
        )
    if not any(day["exercises"] for day in days):
        return None
    return {"week_start": start.isoformat(), "days": days}


def day_for_date(plan, selected_date):
    target = selected_date.isoformat()
    return next((day for day in plan.get("days", []) if day.get("date") == target), None)


def movement_svg(exercise):
    movement = exercise.get("movement", "mobility")
    stages = ("Start", "Move", "End", "Return")
    frames = []
    for index, stage in enumerate(stages):
        x = 12 + index * 156
        head_x = x + 78
        if movement in ("pushup", "plank"):
            head_x = x + 34
            body = f"M {x + 48} 88 L {x + 122} 88"
            arms = f"M {x + 62} 88 L {x + 68} 116 L {x + 48} 132"
            legs = f"M {x + 110} 88 L {x + 124} 112 L {x + 137} 132"
            if movement == "pushup" and index in (1, 2):
                body = f"M {x + 48} {92 + index * 3} L {x + 122} {92 + index * 3}"
                arms = f"M {x + 62} {92 + index * 3} L {x + 69} 112 L {x + 48} 132"
        elif movement in ("bridge", "core"):
            head_x = x + 37
            head_y = 112
            body = f"M {x + 50} 114 Q {x + 84} {86 if index in (1, 2) else 112} {x + 119} 114"
            arms = f"M {x + 63} 108 L {x + 79} 127 M {x + 88} 105 L {x + 103} 126"
            legs = f"M {x + 118} 114 L {x + 132} 96 L {x + 145} 114"
        else:
            head_y = 31 if movement != "squat" or index not in (1, 2) else 42
            hip_y = 72 if movement != "squat" or index not in (1, 2) else 88
            torso = f"M {head_x} {head_y + 12} L {head_x} {hip_y}"
            arms = f"M {head_x} {head_y + 20} L {head_x - 22} {head_y + 42} M {head_x} {head_y + 20} L {head_x + 22} {head_y + 42}"
            legs = f"M {head_x} {hip_y} L {head_x - 16} {hip_y + 30} L {head_x - 18} 132 M {head_x} {hip_y} L {head_x + 16} {hip_y + 30} L {head_x + 18} 132"
            if movement == "lunge":
                legs = f"M {head_x} {hip_y} L {head_x - 25} {hip_y + 20} L {head_x - 28} 132 M {head_x} {hip_y} L {head_x + 23} {hip_y + 12} L {head_x + 34} 132"
            elif movement == "row":
                torso = f"M {head_x} {head_y + 12} L {head_x + 18} {hip_y}"
                arms = f"M {head_x + 4} {head_y + 23} L {head_x + 31} {head_y + 38} M {head_x + 4} {head_y + 23} L {head_x - 17} {head_y + 45}"
            elif movement == "walk":
                legs = f"M {head_x} {hip_y} L {head_x - 20} {hip_y + 20} L {head_x - 35} 132 M {head_x} {hip_y} L {head_x + 20} {hip_y + 20} L {head_x + 35} 132"
            elif movement == "mobility":
                arms = f"M {head_x} {head_y + 20} L {head_x - 24} {head_y - 4} M {head_x} {head_y + 20} L {head_x + 24} {head_y - 4}"
            body = torso

        frame = (
            f'<rect x="{x}" y="8" width="144" height="148" rx="10" fill="#f2f5f1"/>'
            f'<text x="{x + 72}" y="27" text-anchor="middle" class="label">{stage}</text>'
            '<g fill="none" stroke="#355c4b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">'
            f'<circle cx="{head_x}" cy="{head_y if movement in ("bridge", "core") else (31 if movement not in ("pushup", "plank") else 83)}" r="9" fill="#d9a07e" stroke="none"/>'
            f'<path d="{body}"/><path d="{arms}"/><path d="{legs}"/>'
            '</g>'
        )
        frames.append(frame)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 164" role="img" '
        f'aria-label="Original movement sequence for {exercise["name"]}">'
        '<style>text{font-family:Arial,sans-serif}.label{font-size:12px;font-weight:600;fill:#3d554a}</style>'
        + "".join(frames)
        + "</svg>"
    )
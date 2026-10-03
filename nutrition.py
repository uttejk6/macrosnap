import json
import math
import re
from datetime import datetime


ACTIVITY_FACTORS = {
    "Sedentary": 1.2,
    "Lightly active": 1.375,
    "Moderately active": 1.55,
    "Very active": 1.725,
    "Extra active": 1.9,
}

GOAL_ADJUSTMENTS = {
    "Lose weight": -400,
    "Maintain weight": 0,
    "Gain weight": 300,
}

MEAL_SLOT_TYPES = (
    "breakfast",
    "morning_snack",
    "lunch",
    "evening_snack",
    "dinner",
)

MEAL_SLOT_LABELS = {
    "breakfast": "Breakfast",
    "morning_snack": "Morning snack",
    "lunch": "Lunch",
    "evening_snack": "Evening snack",
    "dinner": "Dinner",
}

PLANT_FOOD_TERMS = {
    "vegetable", "spinach", "tomato", "onion", "pepper", "broccoli",
    "carrot", "cabbage", "lettuce", "salad", "fruit", "apple", "banana",
    "berry", "bean", "lentil", "chickpea", "dal", "pea", "oat", "wholegrain",
    "whole grain", "brown rice", "millet", "mushroom", "pumpkin", "potato",
}


def calculate_profile_targets(profile):
    age = int(profile["age"])
    height_cm = float(profile["height_cm"])
    weight_kg = float(profile["weight_kg"])
    gender = profile["gender"]
    activity_level = profile["activity_level"]
    goal = profile["goal"]

    if not 13 <= age <= 100:
        raise ValueError("Age must be between 13 and 100.")
    if not 100 <= height_cm <= 250:
        raise ValueError("Height must be between 100 and 250 cm.")
    if not 30 <= weight_kg <= 350:
        raise ValueError("Weight must be between 30 and 350 kg.")
    if activity_level not in ACTIVITY_FACTORS:
        raise ValueError("Choose a valid activity level.")
    if goal not in GOAL_ADJUSTMENTS:
        raise ValueError("Choose a valid goal.")

    gender_adjustment = {
        "Male": 5,
        "Female": -161,
        "Other / prefer not to say": -78,
    }.get(gender, -78)

    resting_calories = (
        10 * weight_kg
        + 6.25 * height_cm
        - 5 * age
        + gender_adjustment
    )
    goal_adjustment = 0 if age < 18 else GOAL_ADJUSTMENTS[goal]
    daily_calories = max(
        1000,
        round(
            resting_calories * ACTIVITY_FACTORS[activity_level]
            + goal_adjustment
        )
    )
    protein_goal = round(weight_kg * 1.6)
    fat_goal = round(daily_calories * 0.30 / 9)
    carbs_goal = round(
        max(daily_calories - protein_goal * 4 - fat_goal * 9, 0) / 4
    )
    water_goal_ml = min(5000, max(1000, round(weight_kg * 35 / 250) * 250))

    return {
        "calorie_goal": daily_calories,
        "protein_goal": protein_goal,
        "carb_goal": carbs_goal,
        "fat_goal": fat_goal,
        "water_goal_ml": water_goal_ml,
    }


def suggest_meal_times(wake_time="07:00", sleep_time="23:00"):
    try:
        wake = datetime.strptime(wake_time, "%H:%M")
        sleep = datetime.strptime(sleep_time, "%H:%M")
    except (TypeError, ValueError) as error:
        raise ValueError("Wake and sleep times must use HH:MM format.") from error

    wake_minutes = wake.hour * 60 + wake.minute
    sleep_minutes = sleep.hour * 60 + sleep.minute
    if sleep_minutes <= wake_minutes:
        sleep_minutes += 24 * 60
    waking_minutes = sleep_minutes - wake_minutes
    proportions = (0.08, 0.27, 0.49, 0.70, 0.88)
    times = {}
    previous = wake_minutes - 1

    for meal_type, proportion in zip(MEAL_SLOT_TYPES, proportions):
        meal_minutes = wake_minutes + round(waking_minutes * proportion)
        meal_minutes = max(meal_minutes, previous + 60)
        meal_minutes = min(meal_minutes, sleep_minutes - 30)
        minute_of_day = meal_minutes % (24 * 60)
        times[meal_type] = f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"
        previous = meal_minutes

    return times


def _number(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _parse_json_response(response_text):
    text = response_text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _normalize_items(values):
    if not isinstance(values, list):
        return []
    items = []
    for value in values:
        if isinstance(value, str):
            items.append({"name": value, "portion": "Not specified"})
        elif isinstance(value, dict):
            name = str(value.get("name", "Food item")).strip()
            portion = str(value.get("portion", "Not specified")).strip()
            items.append({"name": name, "portion": portion})
    return items


def _normalize_alternatives(values):
    if not isinstance(values, list):
        return []
    alternatives = []
    for value in values:
        if isinstance(value, str):
            alternatives.append({"name": value, "reason": "A different preparation may reduce added fat or increase fiber."})
        elif isinstance(value, dict):
            alternatives.append(
                {
                    "name": str(value.get("name", "Alternative")).strip(),
                    "reason": str(value.get("reason", "A different preparation or ingredient balance.")).strip(),
                }
            )
    return alternatives


def parse_meal_response(response_text):
    payload = _parse_json_response(response_text)
    if not isinstance(payload, dict):
        return None

    if payload.get("is_food") is False:
        return {
            "is_food": False,
            "reply": str(payload.get("reply", "Let's keep the conversation focused on food and nutrition.")),
        }

    calories = _number(payload.get("calories"))
    protein_g = _number(payload.get("protein_g", payload.get("protein")))
    carbs_g = _number(payload.get("carbs_g", payload.get("carbohydrates", payload.get("carbs"))))
    fat_g = _number(payload.get("fat_g", payload.get("fat")))
    if None in (calories, protein_g, carbs_g, fat_g):
        return None

    fiber_g = _number(payload.get("fiber_g"))
    nutrition_notes = str(
        payload.get("nutrition_notes", "Values are approximate estimates.")
    ).strip()
    if fiber_g is not None and "fiber" not in nutrition_notes.lower():
        nutrition_notes = f"{nutrition_notes} Estimated fiber: about {fiber_g:.1f} g."

    return {
        "is_food": True,
        "meal_name": str(payload.get("meal_name", "Meal estimate")).strip(),
        "food_items": _normalize_items(payload.get("food_items")),
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "nutrition_notes": nutrition_notes,
        "fiber_g": fiber_g,
        "alternatives": _normalize_alternatives(payload.get("healthier_alternatives", payload.get("alternatives", []))),
        "reply": str(payload.get("reply", "")),
    }


def score_meal(meal):
    calories = max(float(meal.get("calories", 0)), 1)
    protein = max(float(meal.get("protein_g", 0)), 0)
    carbs = max(float(meal.get("carbs_g", 0)), 0)
    fat = max(float(meal.get("fat_g", 0)), 0)
    items = meal.get("food_items", [])
    names = " ".join(
        str(item.get("name", ""))
        for item in items
        if isinstance(item, dict)
    ).lower()
    plant_count = sum(term in names for term in PLANT_FOOD_TERMS)

    protein_score = min(20, round(protein / 20 * 20))
    plant_score = min(20, plant_count * 8)
    calorie_score = 15 if 250 <= calories <= 700 else 11 if 150 <= calories <= 900 else 7
    fat_share = fat * 9 / calories
    fat_score = 15 if fat_share <= 0.35 else 11 if fat_share <= 0.5 else 7
    carb_share = carbs * 4 / calories
    carb_score = 15 if 0.25 <= carb_share <= 0.65 else 10 if carb_share <= 0.8 else 6
    balance_score = min(15, len(items) * 4 + (3 if plant_count else 0))
    categories = {
        "Protein": protein_score,
        "Vegetables/fiber": plant_score,
        "Calories": calorie_score,
        "Fat": fat_score,
        "Carbohydrates": carb_score,
        "Food balance": balance_score,
    }
    return min(100, sum(categories.values())), categories


def format_meal_analysis(meal):
    lines = [
        f"**{meal['meal_name']}** · approximate estimate",
        f"**{meal['calories']:.0f} kcal**  |  Protein {meal['protein_g']:.1f} g  |  Carbs {meal['carbs_g']:.1f} g  |  Fat {meal['fat_g']:.1f} g",
    ]
    if meal.get("fiber_g") is not None:
        lines.append(f"Fiber ~{meal['fiber_g']:.1f} g")

    if meal.get("food_items"):
        lines.extend(["", "**Food and portion estimates**"])
        lines.extend(
            f"- {item['name']}: ~{item['portion']}"
            for item in meal["food_items"]
        )

    lines.extend(["", meal.get("nutrition_notes", "Values are approximate estimates.")])
    lines.extend(
        [
            "",
            f"**Nutrition score: {meal.get('nutrition_score', 0)}/100** · App-generated heuristic, not a medical assessment.",
        ]
    )

    if meal.get("alternatives"):
        lines.extend(["", "**Healthier alternatives**"])
        lines.extend(
            f"- {alternative['name']}: {alternative['reason']}"
            for alternative in meal["alternatives"]
        )

    return "\n".join(lines)


def build_meal_plan_prompt(profile):
    return f"""Create a practical one-day meal plan using these approximate daily targets:
- Calories: {profile.get('calorie_goal') or 'not set'} kcal
- Protein: {profile.get('protein_goal') or 'not set'} g
- Carbohydrates: {profile.get('carb_goal') or 'not set'} g
- Fat: {profile.get('fat_goal') or 'not set'} g
- Goal: {profile.get('goal') or 'not set'}
- Food preferences: {profile.get('food_preferences') or 'none specified'}

Include Breakfast, Morning snack, Lunch, Evening snack, and Dinner. Give a short list of foods and estimated calories/protein/carbs/fat for each, then daily totals. Label every number as an estimate. Avoid medical claims and allow simple substitutions."""


def build_smart_meal_schedule_prompt(profile, schedule, remaining_targets, consumed):
    age = int(profile["age"])
    minor_guidance = (
        "The user is under 18. Do not create weight-loss targets, calorie deficits, restrictive portions, or weight-loss advice. Recommend regular, balanced meals and suggest involving a parent/guardian and a qualified healthcare professional for nutrition concerns."
        if age < 18
        else "The user is an adult. Targets are estimates, not medical prescriptions."
    )
    dietary = profile.get("dietary_preference", "Flexible")
    avoid = profile.get("foods_to_avoid", "").strip()
    restrictions = {
        "Vegetarian": "Do not include meat, poultry, fish, or seafood. Eggs and dairy are acceptable unless separately avoided.",
        "Vegan": "Do not include meat, poultry, fish, seafood, eggs, dairy, honey, or other animal-derived ingredients.",
        "Non-vegetarian": "Animal foods are allowed, but do not require them; respect the avoid list.",
        "Flexible": "Use a balanced mix of foods; respect the avoid list.",
    }.get(dietary, "Respect the user's food preferences and avoid list.")
    time_lines = "\n".join(
        f"- {MEAL_SLOT_LABELS[meal_type]}: {schedule[meal_type]}"
        for meal_type in MEAL_SLOT_TYPES
    )
    foods_to_avoid = avoid or "None specified"
    schedule_context = profile.get("daily_schedule", "").strip() or "No work/college schedule provided"
    plan_goal = (
        "Regular balanced meals and growth support; no weight-loss planning"
        if age < 18
        else profile.get("goal")
    )

    return f"""Create a personalized one-day meal schedule as ONLY valid JSON.

User profile:
- Age: {age}
- Gender: {profile.get('gender', 'Not specified')}
- Height: {profile.get('height_cm')} cm
- Weight: {profile.get('weight_kg')} kg
- Target weight: {profile.get('target_weight_kg')} kg
- Activity level: {profile.get('activity_level')}
- Goal: {plan_goal}
- Diet preference: {dietary}
- Food preferences: {profile.get('food_preferences') or 'None specified'}
- Foods/allergens to avoid: {foods_to_avoid}
- Wake-up: {profile.get('wake_time', '07:00')}
- Sleep: {profile.get('sleep_time', '23:00')}
- Work/college schedule: {schedule_context}

Diet rules: {restrictions}
Safety: {minor_guidance} Never diagnose or claim a food is medically required. If allergies or medical dietary needs are mentioned, advise checking with a qualified professional and do not include the avoided item.

Today's schedule:
{time_lines}

Remaining estimated targets after food already logged today:
- Calories: {remaining_targets['calories']} kcal
- Protein: {remaining_targets['protein_g']} g
- Carbohydrates: {remaining_targets['carbs_g']} g
- Fat: {remaining_targets['fat_g']} g
Already consumed today: {consumed['calories']:.0f} kcal, {consumed['protein_g']:.0f} g protein, {consumed['carbs_g']:.0f} g carbs, {consumed['fat_g']:.0f} g fat.

Create exactly five slots in the same order and use the provided times. Spread the remaining calorie estimate approximately across the slots with about 25% breakfast, 10% morning snack, 35% lunch, 10% evening snack, and 20% dinner. Do not exceed the remaining target unnecessarily, but never tell the user to skip a meal or recommend a zero-calorie meal; if little or no target remains, suggest a modest balanced option without restrictive advice. Food names and portions should be practical and culturally adaptable.

JSON format:
{{"meals":[{{"meal_type":"breakfast","name":"Breakfast","time":"08:00","foods":["food with estimated portion"],"calories":400,"protein_g":20,"carbs_g":45,"fat_g":12}},{{"meal_type":"morning_snack","name":"Morning snack","time":"10:30","foods":["food with estimated portion"],"calories":150,"protein_g":8,"carbs_g":20,"fat_g":4}},{{"meal_type":"lunch","name":"Lunch","time":"13:00","foods":["food with estimated portion"],"calories":500,"protein_g":30,"carbs_g":55,"fat_g":15}},{{"meal_type":"evening_snack","name":"Evening snack","time":"16:30","foods":["food with estimated portion"],"calories":150,"protein_g":8,"carbs_g":18,"fat_g":5}},{{"meal_type":"dinner","name":"Dinner","time":"19:30","foods":["food with estimated portion"],"calories":400,"protein_g":25,"carbs_g":45,"fat_g":12}}]}}

All calories, macros, portions, and times are estimates. Return JSON only."""


def parse_daily_meal_plan(response_text, scheduled_times):
    payload = _parse_json_response(response_text)
    if not isinstance(payload, dict) or not isinstance(payload.get("meals"), list):
        return None

    received = {}
    for meal in payload["meals"]:
        if not isinstance(meal, dict):
            return None
        meal_type = str(meal.get("meal_type", "")).strip().lower()
        if meal_type not in MEAL_SLOT_TYPES or meal_type in received:
            return None

        calories = _number(meal.get("calories"))
        protein_g = _number(meal.get("protein_g"))
        carbs_g = _number(meal.get("carbs_g"))
        fat_g = _number(meal.get("fat_g"))
        foods = meal.get("foods")
        if None in (calories, protein_g, carbs_g, fat_g) or not isinstance(foods, list) or not foods:
            return None

        received[meal_type] = {
            "meal_type": meal_type,
            "name": MEAL_SLOT_LABELS[meal_type],
            "time": scheduled_times[meal_type],
            "foods": [str(food).strip() for food in foods if str(food).strip()],
            "calories": round(calories),
            "protein_g": round(protein_g, 1),
            "carbs_g": round(carbs_g, 1),
            "fat_g": round(fat_g, 1),
        }

    if set(received) != set(MEAL_SLOT_TYPES):
        return None

    meals = [received[meal_type] for meal_type in MEAL_SLOT_TYPES]
    return {
        "meals": meals,
        "total_calories": sum(meal["calories"] for meal in meals),
        "total_protein_g": round(sum(meal["protein_g"] for meal in meals), 1),
        "total_carbs_g": round(sum(meal["carbs_g"] for meal in meals), 1),
        "total_fat_g": round(sum(meal["fat_g"] for meal in meals), 1),
    }


def plan_respects_preferences(plan, dietary_preference, foods_to_avoid=""):
    combined = " ".join(
        f"{meal['name']} {' '.join(meal['foods'])}"
        for meal in plan.get("meals", [])
    ).lower()
    avoid_terms = [
        term.strip().lower()
        for term in re.split(r"[,;\n]", foods_to_avoid)
        if term.strip()
    ]
    if any(term in combined for term in avoid_terms):
        return False

    restrictions = {
        "Vegetarian": ("chicken", "beef", "pork", "lamb", "fish", "seafood", "shrimp", "turkey", "bacon"),
        "Vegan": ("chicken", "beef", "pork", "lamb", "fish", "seafood", "shrimp", "turkey", "bacon", "egg", "milk", "cheese", "yogurt", "curd", "butter", "ghee", "honey"),
    }
    return not any(term in combined for term in restrictions.get(dietary_preference, ()))
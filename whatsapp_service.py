import json
import logging
import re
from datetime import datetime, time, timedelta

from auth import normalize_phone_number
from twilio.rest import Client


LOGGER = logging.getLogger("macrosnap.whatsapp")
REQUIRED_SETTINGS = (
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_FROM",
    "TWILIO_CONTENT_SID",
)


def missing_settings(settings):
    missing = []
    for key in REQUIRED_SETTINGS:
        value = str(settings.get(key, "") or "").strip()
        if not value or value.lower() == "xxxx" or "your_" in value.lower():
            missing.append(key)
    return missing


def normalize_whatsapp_address(number):
    value = str(number or "").strip()
    if value.lower().startswith("whatsapp:"):
        value = value.split(":", 1)[1].strip()
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10 and not digits.startswith(tuple("6789")):
        return None
    normalized = normalize_phone_number(value)
    if not normalized:
        return None
    normalized_digits = re.sub(r"\D", "", normalized)
    if not 8 <= len(normalized_digits) <= 15 or normalized_digits.startswith("0"):
        return None
    return f"whatsapp:{normalized}"


def normalize_whatsapp_sender(sender):
    normalized = normalize_whatsapp_address(sender)
    if not normalized:
        return None
    return normalized


def clean_whatsapp_text(text, maximum_length=1497):
    lines = [" ".join(line.split()) for line in str(text or "").splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    if not cleaned:
        return "No nutrition summary available."
    return cleaned[: maximum_length - 3] + "..." if len(cleaned) > maximum_length else cleaned


def default_next_meal_suggestion(profile, current=None):
    diet = str(profile.get("dietary_preference", "Flexible")).lower()
    protein_choices = {
        "vegan": ("dal", "chickpeas", "tofu"),
        "vegetarian": ("dal", "paneer", "yogurt"),
        "non-vegetarian": ("eggs", "chicken", "fish", "dal"),
    }
    choices = protein_choices.get(diet, ("dal", "tofu", "eggs", "chicken"))
    avoid = str(profile.get("foods_to_avoid", "")).lower()
    available = [choice for choice in choices if choice not in avoid]
    protein = (
        ", ".join(available[:-1]) + f", or {available[-1]}"
        if len(available) > 1
        else available[0]
        if available
        else "a protein source that fits your listed food restrictions"
    )
    now = current or datetime.now()
    if now.hour >= 21:
        try:
            wake_time = time.fromisoformat(str(profile.get("wake_time", "07:00")))
        except ValueError:
            wake_time = time(7, 0)
        meal_time = "around " + datetime.combine(now.date() + timedelta(days=1), wake_time).strftime("%I:%M %p").lstrip("0") + " tomorrow"
    else:
        meal_time = "around " + (now + timedelta(hours=2)).strftime("%I:%M %p").lstrip("0")
    return {
        "meal": f"A balanced plate with {protein}, vegetables, and a whole-grain side.",
        "time": meal_time,
        "portion":         "1 palm-sized protein serving, 1 fist of grains, and 1 to 2 fists of vegetables.",
    }


def _meal_group_name(meal):
    try:
        hour = datetime.fromisoformat(meal["created_at"]).hour
    except (KeyError, TypeError, ValueError):
        return "Snacks"
    if 5 <= hour < 11:
        return "Breakfast"
    if 11 <= hour < 16:
        return "Lunch"
    if hour >= 17:
        return "Dinner"
    return "Snacks"


def build_daily_summary(
    profile,
    totals,
    water,
    exercise_minutes,
    meals,
    today,
    suggestion=None,
    current=None,
):
    suggestion = suggestion or default_next_meal_suggestion(profile, current)
    grouped_meals = {label: [] for label in ("Breakfast", "Lunch", "Dinner", "Snacks")}
    for meal in meals:
        grouped_meals[_meal_group_name(meal)].append(
            f"{str(meal.get('meal_name', 'Meal'))[:36]} ({float(meal.get('calories', 0)):.0f} kcal)"
        )

    lines = [
        "MacroSnap Daily Summary 🥗",
        f"Date: {today.strftime('%b %d, %Y')}",
        f"Calories: {totals['calories']:.0f} / {profile.get('calorie_goal') or 0} kcal",
        f"Protein: {totals['protein_g']:.0f} / {profile.get('protein_goal') or 0} g",
        f"Carbs: {totals['carbs_g']:.0f} / {profile.get('carb_goal') or 0} g",
        f"Fat: {totals['fat_g']:.0f} / {profile.get('fat_goal') or 0} g",
        f"Water: {water} ml / {profile.get('water_goal_ml') or 0} ml",
        f"Exercise: {exercise_minutes:.0f} minutes completed",
    ]
    for label, entries in grouped_meals.items():
        details = ", ".join(entries[:3]) if entries else "none logged"
        lines.append(f"{label}: {details}")
    lines.extend(
        [
            f"Current weight: {float(profile.get('weight_kg') or 0):.1f} kg",
            f"Goal: {profile.get('goal') or profile.get('fitness_goal') or 'General fitness'}",
            f"Suggested next meal: {suggestion.get('meal', '')}",
            f"Suggested eating time: {suggestion.get('time', '')}",
            f"Suggested portion: {suggestion.get('portion', '')}",
            "Nutrition values are estimates.",
        ]
    )
    return clean_whatsapp_text("\n".join(lines), maximum_length=1497)


def _safe_twilio_message(error, settings):
    message = str(getattr(error, "msg", "") or "Twilio rejected the WhatsApp request.")
    for secret_name in ("TWILIO_AUTH_TOKEN", "TWILIO_ACCOUNT_SID"):
        secret = str(settings.get(secret_name, "") or "")
        if secret:
            message = message.replace(secret, "[redacted]")
    message = re.sub(r"(?i)(auth_token|token)=\S+", r"\1=[redacted]", message)
    message = " ".join(message.split())
    code = getattr(error, "code", None)
    if code:
        return f"Twilio could not send the message (error {code}): {message[:300]}"
    return f"Twilio could not send the message: {message[:300]}"


def send_whatsapp_summary(to_number, user_name, summary, settings, client=None):
    missing = missing_settings(settings)
    if missing:
        return False, "WhatsApp is not configured. Add the following setting(s) to Streamlit secrets: " + ", ".join(missing) + "."

    destination = normalize_whatsapp_address(to_number)
    if not destination:
        return False, "The WhatsApp number in your profile is invalid. Update it to a valid international number."

    sender = normalize_whatsapp_sender(settings.get("TWILIO_WHATSAPP_FROM"))
    if not sender:
        return False, "TWILIO_WHATSAPP_FROM must be a valid WhatsApp sender number, such as whatsapp:+14155550123."

    try:
        configured_client = client or Client(
            settings["TWILIO_ACCOUNT_SID"],
            settings["TWILIO_AUTH_TOKEN"],
        )
        message = configured_client.messages.create(
            from_=sender,
            to=destination,
            content_sid=settings["TWILIO_CONTENT_SID"],
            content_variables=json.dumps(
                {
                    "1": str(user_name or "MacroSnap user"),
                    "2": clean_whatsapp_text(summary),
                },
                ensure_ascii=False,
            ),
        )
        return True, getattr(message, "sid", "sent")
    except Exception as error:
        LOGGER.warning("Twilio WhatsApp delivery failed (%s).", type(error).__name__)
        return False, _safe_twilio_message(error, settings)

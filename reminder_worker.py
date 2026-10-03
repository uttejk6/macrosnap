import json
import logging
from datetime import datetime

import streamlit as st
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from twilio.rest import Client as TwilioClient

import database
import whatsapp_service
from exercise import day_for_date, week_start_for


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("macrosnap.reminder_worker")


def load_twilio_settings():
    try:
        account_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
        auth_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
        sender = st.secrets.get("TWILIO_WHATSAPP_FROM", "")
        content_sid = st.secrets.get("TWILIO_CONTENT_SID", "")
    except Exception as error:
        raise RuntimeError(
            "Streamlit secrets could not be loaded. Run this worker from the project directory."
        ) from error

    settings = {
        "TWILIO_ACCOUNT_SID": account_sid,
        "TWILIO_AUTH_TOKEN": auth_token,
        "TWILIO_WHATSAPP_FROM": sender,
        "TWILIO_CONTENT_SID": content_sid,
    }
    missing = whatsapp_service.missing_settings(settings)
    if missing:
        raise RuntimeError(
            "Set valid " + ", ".join(missing) + " in .streamlit/secrets.toml."
        )

    normalized_sender = whatsapp_service.normalize_whatsapp_sender(sender)
    if not normalized_sender:
        raise RuntimeError(
            "TWILIO_WHATSAPP_FROM must be a valid WhatsApp sender number, such as whatsapp:+14155550123."
        )

    return account_sid, auth_token, normalized_sender, content_sid


def format_reminder(reminder):
    meal = reminder["food_plan"]
    foods = "\n".join(f"• {food}" for food in meal.get("foods", []))
    meal_name = meal.get("name", reminder["meal_type"].replace("_", " ").title())
    return (
        f"MacroSnap meal reminder · {meal_name}\n\n"
        "It's time for your meal.\n\n"
        f"Today's suggestion:\n{foods}\n\n"
        f"Estimated: {meal.get('calories', 0)} kcal · "
        f"{meal.get('protein_g', 0)} g protein\n"
        "Nutrition values are estimates. Enjoy your meal!"
    )[:1497]


def format_workout_reminder(reminder, workout_day=None):
    lines = [
        f"MacroSnap workout reminder · {reminder['focus']}",
        "It's time for today's movement.",
        f"Planned duration: {reminder['duration_minutes']} minutes",
    ]
    exercises = workout_day.get("exercises", []) if workout_day else []
    if workout_day and workout_day.get("rest"):
        lines.append("Today's plan is a recovery day. Rest is part of training.")
    elif exercises:
        lines.append("Today's plan:")
        for index, exercise in enumerate(exercises[:6], start=1):
            lines.append(
                f"{index}. {exercise['name']} · {exercise['sets']} × {exercise['reps']}"
            )
    else:
        lines.append("Open MacroSnap Exercise for today's workout and movement demos.")
    lines.append("Log your sets, reps, and completion in MacroSnap Exercise after your session.")
    lines.append("Stop if you feel severe pain, chest pain, dizziness, or difficulty breathing.")
    return "\n".join(lines)[:1497]


def send_due_reminders(now=None, client=None, sender=None, content_sid=None):
    if client is None or not sender or not content_sid:
        raise ValueError("A configured Twilio client, sender, and content template are required.")

    current = now or datetime.now().astimezone()
    claimed = database.claim_due_reminders(current)
    sent = 0

    for reminder in claimed:
        destination = whatsapp_service.normalize_whatsapp_address(reminder["user_id"])
        if not destination:
            database.release_reminder_claim(reminder["id"])
            LOGGER.warning("Reminder %s has an invalid WhatsApp destination.", reminder["id"])
            continue
        content_variables = json.dumps(
            {
                "1": reminder["name"],
                "2": format_reminder(reminder),
            },
            ensure_ascii=False,
        )
        try:
            client.messages.create(
                from_=sender,
                to=destination,
                content_sid=content_sid,
                content_variables=content_variables,
            )
            database.mark_reminder_sent(
                reminder["id"],
                current.date(),
            )
            sent += 1
        except Exception as error:
            database.release_reminder_claim(reminder["id"])
            LOGGER.warning(
                "Reminder %s failed (%s).",
                reminder["id"],
                type(error).__name__,
            )

    return sent


def send_due_workout_reminders(now=None, client=None, sender=None, content_sid=None):
    if client is None or not sender or not content_sid:
        raise ValueError("A configured Twilio client, sender, and content template are required.")

    current = now or datetime.now().astimezone()
    claimed = database.claim_due_workout_reminders(current)
    sent = 0
    for reminder in claimed:
        phone = reminder["user_phone"]
        plan_row = database.get_workout_plan(phone, week_start_for(current.date()))
        workout_day = (
            day_for_date(plan_row["plan"], current.date())
            if plan_row
            else None
        )
        destination = whatsapp_service.normalize_whatsapp_address(phone)
        if not destination:
            database.release_workout_reminder_claim(phone)
            LOGGER.warning("Workout reminder for %s has an invalid WhatsApp destination.", phone[-4:])
            continue
        content_variables = json.dumps(
            {
                "1": reminder["name"],
                "2": format_workout_reminder(reminder, workout_day),
            },
            ensure_ascii=False,
        )
        try:
            client.messages.create(
                from_=sender,
                to=destination,
                content_sid=content_sid,
                content_variables=content_variables,
            )
            database.mark_workout_reminder_sent(phone, current.date())
            sent += 1
        except Exception as error:
            database.release_workout_reminder_claim(phone)
            LOGGER.warning(
                "Workout reminder for %s failed (%s).",
                phone[-4:],
                type(error).__name__,
            )
    return sent


def format_daily_summary_reminder(phone, name, current):
    profile = database.get_user(phone) or {"name": name}
    totals = database.get_daily_totals(phone, current.date())
    water = database.get_water(phone, current.date())
    meals = database.get_meals(phone, current.date(), current.date(), limit=None)
    workout_logs = database.get_workout_logs(phone, current.date(), current.date())
    completed = [item for item in workout_logs if item["completed"]]
    return whatsapp_service.build_daily_summary(
        profile,
        totals,
        water,
        sum(item["duration_minutes"] for item in completed),
        meals,
        current.date(),
        current=current,
    )


def send_due_daily_summaries(now=None, client=None, sender=None, content_sid=None):
    if client is None or not sender or not content_sid:
        raise ValueError("A configured Twilio client, sender, and content template are required.")

    current = now or datetime.now().astimezone()
    claimed = database.claim_due_daily_summaries(current)
    sent = 0
    for reminder in claimed:
        phone = reminder["user_phone"]
        destination = whatsapp_service.normalize_whatsapp_address(phone)
        if not destination:
            database.release_daily_summary_claim(phone)
            LOGGER.warning("Daily summary for %s has an invalid WhatsApp destination.", phone[-4:])
            continue
        content_variables = json.dumps(
            {
                "1": reminder["name"],
                "2": format_daily_summary_reminder(phone, reminder["name"], current),
            },
            ensure_ascii=False,
        )
        try:
            client.messages.create(
                from_=sender,
                to=destination,
                content_sid=content_sid,
                content_variables=content_variables,
            )
            database.mark_daily_summary_sent(phone, current.date())
            sent += 1
        except Exception as error:
            database.release_daily_summary_claim(phone)
            LOGGER.warning(
                "Daily summary delivery failed (%s).",
                type(error).__name__,
            )
    return sent


def main():
    database.init_db()
    account_sid, auth_token, sender, content_sid = load_twilio_settings()
    client = TwilioClient(account_sid, auth_token)

    def poll():
        meal_count = send_due_reminders(
            client=client,
            sender=sender,
            content_sid=content_sid,
        )
        workout_count = send_due_workout_reminders(
            client=client,
            sender=sender,
            content_sid=content_sid,
        )
        summary_count = send_due_daily_summaries(
            client=client,
            sender=sender,
            content_sid=content_sid,
        )
        if meal_count:
            LOGGER.info("Sent %s scheduled meal reminder(s).", meal_count)
        if workout_count:
            LOGGER.info("Sent %s scheduled workout reminder(s).", workout_count)
        if summary_count:
            LOGGER.info("Sent %s scheduled daily summary message(s).", summary_count)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        poll,
        IntervalTrigger(minutes=1),
        id="meal_reminder_poll",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=55,
    )
    poll()
    LOGGER.info("Meal reminder worker is running; stop with Ctrl+C.")
    scheduler.start()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None

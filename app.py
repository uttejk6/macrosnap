import json
import logging
import re
import sqlite3
from datetime import date, datetime
import streamlit as st
from google.genai import types
from streamlit.errors import StreamlitSecretNotFoundError

from auth import normalize_phone_number
import database
import design_system
import exercise_views
import gemini_service
import views
import whatsapp_service
from error_handling import safe_error
from exercise import (
    BODY_GOALS,
    EQUIPMENT_OPTIONS,
    EXPERIENCE_LEVELS,
    FITNESS_GOALS,
    WORKOUT_DURATIONS,
    WORKOUT_LOCATIONS,
)
from nutrition import calculate_profile_targets
from prompts import (
    EXERCISE_ANALYSIS_SYSTEM_PROMPT,
    EXERCISE_ANALYSIS_PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
)


LOGGER = logging.getLogger("macrosnap.app")

st.set_page_config(
    page_title="MacroSnap",
    page_icon="🥗",
    layout="wide"
)
design_system.inject_global_styles()

# ============================================================
# API KEYS / SECRETS
# ============================================================

def read_secret(name, default=""):
    try:
        value = st.secrets.get(name, default)
    except StreamlitSecretNotFoundError:
        return default
    return str(value or "").strip()


def read_gemini_api_key():
    try:
        return str(st.secrets["GEMINI_API_KEY"] or "").strip()
    except (KeyError, StreamlitSecretNotFoundError):
        return ""


GEMINI_API_KEY = read_gemini_api_key()
GEMINI_NOT_CONFIGURED_MESSAGE = (
    "Gemini is not configured. Please check your Streamlit secrets."
)
MODEL_NAME = read_secret("GEMINI_MODEL", gemini_service.DEFAULT_MODEL_NAME)
MODEL_FALLBACKS = tuple(
    model.strip()
    for model in read_secret("GEMINI_MODEL_FALLBACKS").split(",")
    if model.strip()
)
TWILIO_SETTINGS = {
    setting: read_secret(setting)
    for setting in whatsapp_service.REQUIRED_SETTINGS
}


@st.cache_resource
def get_gemini_client(api_key):
    if not api_key or "your_" in api_key.lower():
        return None
    try:
        return gemini_service.get_client(api_key)
    except Exception as error:
        LOGGER.warning("Gemini client initialization failed (%s).", type(error).__name__)
        return None


@st.cache_resource
def get_twilio_client(account_sid, auth_token):
    if not account_sid or not auth_token:
        return None
    if "your_" in account_sid.lower() or "your_" in auth_token.lower():
        return None
    try:
        from twilio.rest import Client

        return Client(account_sid, auth_token)
    except Exception as error:
        LOGGER.warning("Twilio client initialization failed (%s).", type(error).__name__)
        return None


gemini_client = get_gemini_client(GEMINI_API_KEY)
twilio_client = get_twilio_client(
    TWILIO_SETTINGS["TWILIO_ACCOUNT_SID"],
    TWILIO_SETTINGS["TWILIO_AUTH_TOKEN"],
)


def normalize_indian_whatsapp_number(phone_number):
    phone_digits = re.sub(r"\D", "", phone_number)
    if phone_digits.startswith("91") and len(phone_digits) == 12:
        phone_digits = phone_digits[2:]
    if not re.fullmatch(r"[6-9]\d{9}", phone_digits):
        return None
    return f"+91{phone_digits}"


def ask_gemini(parts):
    if gemini_client is None:
        st.session_state.gemini_error_message = GEMINI_NOT_CONFIGURED_MESSAGE
        return None

    response = None
    chat = st.session_state.get("chat")
    if chat is not None:
        try:
            response = chat.send_message(parts)
        except Exception as error:
            LOGGER.warning(
                "Gemini chat request failed; trying model fallback (%s).",
                type(error).__name__,
            )

    if not getattr(response, "text", None):
        try:
            response, model_used = gemini_service.generate_content(
                gemini_client,
                MODEL_NAME,
                parts,
                SYSTEM_PROMPT,
                json_response=True,
                configured_fallbacks=MODEL_FALLBACKS,
            )
            st.session_state.gemini_model_used = model_used
        except Exception as error:
            LOGGER.warning("Gemini model fallback failed (%s).", type(error).__name__)
            st.session_state.gemini_error_message = gemini_service.friendly_error_message(error)
            return None
    if not getattr(response, "text", None):
        st.session_state.gemini_error_message = "Gemini returned an empty response. Please try again."
        return None
    st.session_state.pop("gemini_error_message", None)
    return response.text


def generate_text(prompt, json_response=False):
    if gemini_client is None:
        st.session_state.gemini_error_message = GEMINI_NOT_CONFIGURED_MESSAGE
        return None

    system_instruction = (
        "You are MacroSnap's nutrition and fitness planner. Return only valid JSON when requested. "
        "Nutrition and exercise guidance is educational, not a medical prescription."
        if json_response
        else (
            "You are MacroSnap, a friendly nutrition planner. "
            "Answer with a concise, readable Markdown one-day meal plan. "
            "Include breakfast, morning snack, lunch, evening snack, dinner, "
            "and estimated daily calorie and macro totals. Label values as "
            "approximate and do not make medical claims."
        )
    )
    try:
        response, model_used = gemini_service.generate_content(
            gemini_client,
            MODEL_NAME,
            prompt,
            system_instruction,
            json_response=json_response,
            configured_fallbacks=MODEL_FALLBACKS,
        )
    except Exception as error:
        LOGGER.warning("Gemini text request failed (%s).", type(error).__name__)
        st.session_state.gemini_error_message = gemini_service.friendly_error_message(error)
        return None

    st.session_state.gemini_model_used = model_used
    if not getattr(response, "text", None):
        st.session_state.gemini_error_message = "Gemini returned an empty response. Please try again."
        return None
    st.session_state.pop("gemini_error_message", None)
    return response.text


def create_chat():
    if gemini_client is None:
        return None
    chat, model_used = gemini_service.create_chat(
        gemini_client,
        MODEL_NAME,
        SYSTEM_PROMPT,
        configured_fallbacks=MODEL_FALLBACKS,
    )
    if chat is None:
        st.session_state.gemini_error_message = (
            "Gemini is temporarily unavailable. Please check your API key and model access."
        )
        return None
    st.session_state.gemini_model_used = model_used
    return chat


def analyze_exercise_image(image_bytes, mime_type, goal, exercise, profile):
    if gemini_client is None:
        st.session_state.gemini_error_message = GEMINI_NOT_CONFIGURED_MESSAGE
        return None

    profile_context = {
        "age": profile.get("age"),
        "weight_kg": profile.get("weight_kg"),
        "height_cm": profile.get("height_cm"),
        "experience": profile.get("fitness_experience", "Beginner"),
        "fitness_goal": profile.get("fitness_goal", "Improve fitness"),
        "exercise_preferences": profile.get("exercise_preferences", ""),
    }
    prompt = EXERCISE_ANALYSIS_PROMPT_TEMPLATE.format(
        selected_goal=goal,
        selected_exercise=exercise,
        profile=json.dumps(profile_context, ensure_ascii=False),
    )
    try:
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type,
        )
        response, model_used = gemini_service.generate_content(
            gemini_client,
            MODEL_NAME,
            [image_part, prompt],
            EXERCISE_ANALYSIS_SYSTEM_PROMPT,
            json_response=True,
            configured_fallbacks=MODEL_FALLBACKS,
        )
    except Exception as error:
        LOGGER.warning("Gemini exercise image analysis failed (%s).", type(error).__name__)
        st.session_state.gemini_error_message = gemini_service.friendly_error_message(error)
        return None

    st.session_state.gemini_model_used = model_used
    if not getattr(response, "text", None):
        st.session_state.gemini_error_message = "Gemini returned an empty response. Please try a clearer photo."
        return None
    st.session_state.pop("gemini_error_message", None)
    return response.text


def generate_meal_suggestion(prompt):
    if gemini_client is None:
        st.session_state.gemini_error_message = GEMINI_NOT_CONFIGURED_MESSAGE
        return None
    try:
        response, model_used = gemini_service.generate_content(
            gemini_client,
            MODEL_NAME,
            prompt,
            "You are MacroSnap, a concise, safety-conscious nutrition assistant. "
            "Return only valid JSON with string fields meal, time, and portion. "
            "Nutrition estimates are approximate; do not make medical claims.",
            json_response=True,
            configured_fallbacks=MODEL_FALLBACKS,
        )
        result = gemini_service.parse_json_object(response.text)
        suggestion = {
            key: str(result.get(key, "")).strip()
            for key in ("meal", "time", "portion")
        }
        if not all(suggestion.values()):
            raise ValueError("Gemini returned an incomplete meal suggestion.")
    except Exception as error:
        LOGGER.warning("Gemini next-meal suggestion failed (%s).", type(error).__name__)
        st.session_state.gemini_error_message = gemini_service.friendly_error_message(error)
        return None

    st.session_state.gemini_model_used = model_used
    st.session_state.pop("gemini_error_message", None)
    return suggestion


def send_whatsapp(to_number, user_name, summary):
    return whatsapp_service.send_whatsapp_summary(
        to_number,
        user_name,
        summary,
        TWILIO_SETTINGS,
        client=twilio_client,
    )


def activate_user(phone, profile, preserve_session=False):
    existing_chat = st.session_state.get("chat") if preserve_session else None
    existing_messages = (
        st.session_state.get("messages", [])
        if preserve_session
        else []
    )
    st.session_state.user_phone = phone
    st.session_state.name = profile["name"]
    st.session_state.whatsapp_number = phone
    st.session_state.chat = existing_chat or create_chat()
    st.session_state.messages = existing_messages
    st.session_state.welcome_message = WELCOME_MESSAGE_TEMPLATE.format(
        name=profile["name"]
    )
    st.session_state.onboarded = True


def render_brand_panel():
    st.markdown(
        """
        <div class="login-copy">
            <div class="login-brand">🥗 MacroSnap</div>
            <h1>Your AI nutrition<br />&amp; fitness buddy.</h1>
            <p>Food clarity, movement, and progress in one place.</p>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_login_screen():
    brand_col, login_col = st.columns(
        [1.08, 0.92],
        gap="large",
        vertical_alignment="center"
    )

    with brand_col:
        st.markdown(
            """
            <div class="login-left-panel">
                <div class="login-brand-block">
                    <span class="login-brand-mark">🥗</span>
                    <span>MacroSnap</span>
                </div>
                <h1>Your AI nutrition<br />&amp; fitness buddy.</h1>
                <p>Food clarity, movement, and progress in one place.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with login_col:
        st.markdown(
            """
            <div class="login-card-header">
                <h2>Welcome</h2>
                <p>Log in to your account to continue</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("onboarding_form"):
            name = st.text_input("Your name (new profiles only)")
            country_code_col, phone_number_col = st.columns([1, 3], gap="small")
            with country_code_col:
                st.text_input("Country code", value="+91", disabled=True)
            with phone_number_col:
                phone_number = st.text_input(
                    "WhatsApp number",
                    placeholder="9989764628",
                    help="Enter your 10-digit mobile number. +91 is added automatically.",
                )
            submitted = st.form_submit_button("Let's go 🚀", use_container_width=True)

        if not submitted:
            return

        normalized_phone = normalize_indian_whatsapp_number(phone_number.strip())
        if not phone_number.strip():
            st.warning("Please enter your mobile number.")
            return
        if normalized_phone is None:
            st.warning("Enter a valid 10-digit Indian mobile number.")
            return

        try:
            profile = database.get_user(normalized_phone)
            if profile:
                activate_user(normalized_phone, profile)
            elif name.strip():
                st.session_state.setup_phone = normalized_phone
                st.session_state.setup_name = name.strip()
            else:
                st.warning("Enter your name to set up a new profile.")
                return
            st.rerun()
        except sqlite3.Error:
            st.error("We couldn't access your saved profile. Please try again.")


def render_profile_setup(phone, name):
    if not phone:
        phone = st.text_input("Phone number", placeholder="9989764628")
        if not phone:
            st.info("Add your phone number to continue with profile setup.")
            st.stop()
        normalize_phone = normalize_phone_number(phone, default_country_code="+91")
        if normalize_phone is None:
            st.warning("Please enter a valid 10-digit Indian mobile number.")
            st.stop()
        phone = normalize_phone

    brand_col, form_col = st.columns(
        [1.05, 0.95],
        gap="large",
        vertical_alignment="center"
    )
    with brand_col:
        render_brand_panel()

    with form_col:
        st.markdown(
            """
            <div class="login-form-heading">
                <span>YOUR PROFILE</span>
                <h2>Set your nutrition goals</h2>
                <p>We use these details for rough daily estimates.</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.form("profile_setup_form"):
            age_options = ["Select age"] + [str(value) for value in range(13, 101)]
            age = st.selectbox("Age", age_options, index=0)
            gender = st.selectbox(
                "Gender",
                ["Female", "Male", "Other / prefer not to say"],
                index=2,
            )
            height = st.number_input(
                "Height (cm)", min_value=100.0, max_value=250.0,
                value=170.0, step=0.5,
            )
            weight = st.number_input(
                "Current weight (kg)", min_value=30.0, max_value=350.0,
                value=70.0, step=0.1,
            )
            target_weight = st.number_input(
                "Target weight (kg)", min_value=30.0, max_value=350.0,
                value=70.0, step=0.1,
            )
            activity = st.selectbox(
                "Activity level",
                ["Sedentary", "Lightly active", "Moderately active", "Very active", "Extra active"],
                index=2,
            )
            fitness_goal = st.selectbox("Fitness goal", FITNESS_GOALS, index=5)
            body_goal = st.selectbox("Body goal", BODY_GOALS, index=8)
            fitness_experience = st.selectbox("Fitness experience", EXPERIENCE_LEVELS)
            exercise_location = st.selectbox("Where do you exercise?", WORKOUT_LOCATIONS)
            exercise_equipment = st.multiselect("Available equipment", EQUIPMENT_OPTIONS)
            available_workout_minutes = st.selectbox(
                "Available workout time",
                WORKOUT_DURATIONS,
                index=2,
                format_func=lambda value: "60 minutes+" if value == 60 else f"{value} minutes",
            )
            exercise_preferences = st.text_input(
                "Exercise preferences (optional)",
                placeholder="Walking, low-impact movement, short sessions…",
            )
            goal = st.selectbox(
                "Goal",
                ["Lose weight", "Maintain weight", "Gain weight"],
                index=1,
            )
            st.caption("Optional measurements. Enter 0 for any value you do not want to record.")
            measure_columns = st.columns(3)
            with measure_columns[0]:
                waist_cm = st.number_input("Waist (cm)", min_value=0.0, max_value=300.0, value=0.0, step=0.1)
                chest_cm = st.number_input("Chest (cm)", min_value=0.0, max_value=300.0, value=0.0, step=0.1)
            with measure_columns[1]:
                hip_cm = st.number_input("Hip (cm)", min_value=0.0, max_value=300.0, value=0.0, step=0.1)
                arm_cm = st.number_input("Arm (cm)", min_value=0.0, max_value=200.0, value=0.0, step=0.1)
            with measure_columns[2]:
                thigh_cm = st.number_input("Thigh (cm)", min_value=0.0, max_value=200.0, value=0.0, step=0.1)
            dietary_preference = st.selectbox(
                "Diet preference",
                ["Flexible", "Vegetarian", "Vegan", "Non-vegetarian"],
            )
            preferences = st.text_input(
                "Food preferences (optional)",
                placeholder="Vegetarian, dairy-free, no peanuts…",
            )
            foods_to_avoid = st.text_input(
                "Foods or ingredients to avoid",
                placeholder="Peanuts, mushrooms, shellfish…",
            )
            wake_time = st.time_input(
                "Wake-up time",
                value=datetime.strptime("07:00", "%H:%M").time(),
            )
            sleep_time = st.time_input(
                "Sleep time",
                value=datetime.strptime("23:00", "%H:%M").time(),
            )
            daily_schedule = st.text_area(
                "Typical work/college schedule",
                placeholder="For example: classes 9:00 AM–3:00 PM",
            )
            submitted = st.form_submit_button("Open my dashboard", type="primary")

        if submitted:
            if age == "Select age":
                st.error("Select your age to create a personalized profile.")
                st.stop()
            try:
                profile = {
                    "name": name,
                    "age": int(age),
                    "gender": gender,
                    "height_cm": height,
                    "weight_kg": weight,
                    "starting_weight_kg": weight,
                    "target_weight_kg": target_weight,
                    "activity_level": activity,
                    "goal": goal,
                    "fitness_goal": fitness_goal,
                    "body_goal": body_goal,
                    "fitness_experience": fitness_experience,
                    "exercise_location": exercise_location,
                    "exercise_equipment": exercise_equipment,
                    "available_workout_minutes": available_workout_minutes,
                    "exercise_preferences": exercise_preferences.strip(),
                    "food_preferences": preferences.strip(),
                    "dietary_preference": dietary_preference,
                    "foods_to_avoid": foods_to_avoid.strip(),
                    "wake_time": wake_time.strftime("%H:%M"),
                    "sleep_time": sleep_time.strftime("%H:%M"),
                    "daily_schedule": daily_schedule.strip(),
                }
                profile.update(calculate_profile_targets(profile))
                profile = database.save_user(phone, profile)
                database.record_weight(phone, weight)
                database.save_body_measurements(
                    phone,
                    {
                        "weight_kg": weight,
                        "waist_cm": waist_cm or None,
                        "hip_cm": hip_cm or None,
                        "chest_cm": chest_cm or None,
                        "arm_cm": arm_cm or None,
                        "thigh_cm": thigh_cm or None,
                    },
                    date.today(),
                )
                activate_user(
                    phone,
                    profile,
                    preserve_session=st.session_state.get("legacy_onboarding", False),
                )
                st.session_state.pop("setup_phone", None)
                st.session_state.pop("setup_name", None)
                st.session_state.pop("legacy_onboarding", None)
                st.rerun()
            except (ValueError, sqlite3.Error):
                st.error("We couldn't save your profile. Please try again.")


# ============================================================
# STEP 1 - ONBOARDING
# ============================================================

try:
    database.init_db()
except sqlite3.Error:
    st.error("MacroSnap could not open its local nutrition database.")
    st.stop()

if st.session_state.get("onboarded") and not st.session_state.get("user_phone"):
    legacy_phone = normalize_indian_whatsapp_number(
        st.session_state.get("whatsapp_number", "")
    )
    if legacy_phone:
        legacy_profile = database.get_user(legacy_phone)
        if legacy_profile is None:
            st.session_state.pop("onboarded", None)
            st.session_state.setup_phone = legacy_phone
            st.session_state.setup_name = st.session_state.get("name", "")
            st.session_state.legacy_onboarding = True
        else:
            st.session_state.user_phone = legacy_phone
            st.session_state.name = legacy_profile["name"]
            st.session_state.whatsapp_number = legacy_phone
            if "chat" not in st.session_state:
                st.session_state.chat = create_chat()
            st.session_state.setdefault("messages", [])
            st.session_state.setdefault(
                "welcome_message",
                WELCOME_MESSAGE_TEMPLATE.format(name=legacy_profile["name"]),
            )

if "onboarded" not in st.session_state:
    if st.session_state.get("setup_phone"):
        render_profile_setup(
            st.session_state.setup_phone,
            st.session_state.setup_name,
        )
        st.stop()
    render_login_screen()
    st.stop()

if st.session_state.get("onboarded") and not st.session_state.get("user_phone"):
    if st.session_state.get("setup_phone"):
        render_profile_setup(
            st.session_state.setup_phone,
            st.session_state.setup_name,
        )
        st.stop()

    legacy_phone = normalize_indian_whatsapp_number(
        st.session_state.get("whatsapp_number", "")
    )
    if legacy_phone:
        legacy_profile = database.get_user(legacy_phone)
        if legacy_profile is None:
            st.session_state.pop("onboarded", None)
            st.session_state.setup_phone = legacy_phone
            st.session_state.setup_name = st.session_state.get("name", "")
            st.session_state.legacy_onboarding = True
        else:
            st.session_state.user_phone = legacy_phone
            st.session_state.name = legacy_profile["name"]
            st.session_state.whatsapp_number = legacy_phone
            if "chat" not in st.session_state:
                st.session_state.chat = create_chat()
            st.session_state.setdefault("messages", [])
            st.session_state.setdefault(
                "welcome_message",
                WELCOME_MESSAGE_TEMPLATE.format(name=legacy_profile["name"]),
            )

if st.session_state.get("setup_phone"):
    render_profile_setup(
        st.session_state.setup_phone,
        st.session_state.setup_name,
    )
    st.stop()


# ============================================================
# APP NAVIGATION
# ============================================================

def scan_meal_page():
    views.render_scan_meal(ask_gemini)


def meal_planner_page():
    views.render_meal_planner(generate_text, send_whatsapp)


def whatsapp_page():
    missing = whatsapp_service.missing_settings(TWILIO_SETTINGS)
    if not whatsapp_service.normalize_whatsapp_sender(
        TWILIO_SETTINGS.get("TWILIO_WHATSAPP_FROM", "")
    ):
        missing.append("TWILIO_WHATSAPP_FROM (valid whatsapp:+ number)")
    if twilio_client is None and not missing:
        missing.append("valid Twilio account credentials")
    views.render_whatsapp(
        send_whatsapp,
        missing,
        generate_meal_suggestion,
    )


def check_gemini_connection():
    return gemini_service.check_model(gemini_client, MODEL_NAME)


def settings_page():
    views.render_settings(
        not whatsapp_service.missing_settings(TWILIO_SETTINGS)
        and whatsapp_service.normalize_whatsapp_sender(
            TWILIO_SETTINGS.get("TWILIO_WHATSAPP_FROM", "")
        ) is not None
        and twilio_client is not None,
        check_gemini_connection,
    )


def exercise_page():
    exercise_views.render_exercise_page(generate_text, analyze_exercise_image)


design_system.render_sidebar_brand()


navigation = st.navigation(
    {
        "HOME": [
            st.Page(
                views.render_dashboard,
                title="Dashboard",
                icon=":material/home:",
                default=True,
            ),
        ],
        "TRACK": [
            st.Page(
                scan_meal_page,
                title="Scan Meal",
                icon=":material/photo_camera:",
            ),
            st.Page(
                views.render_meal_history,
                title="Meal History",
                icon=":material/restaurant:",
            ),
            st.Page(
                exercise_page,
                title="Exercise",
                icon=":material/fitness_center:",
            ),
            st.Page(
                views.render_progress,
                title="Progress",
                icon=":material/monitoring:",
            ),
        ],
        "YOUR PLAN": [
            st.Page(
                views.render_goals,
                title="Goals",
                icon=":material/track_changes:",
            ),
            st.Page(
                views.render_water,
                title="Water",
                icon=":material/local_drink:",
            ),
            st.Page(
                meal_planner_page,
                title="Meal Planner",
                icon=":material/auto_awesome:",
            ),
            st.Page(
                views.render_profile,
                title="Profile",
                icon=":material/person:",
            ),
        ],
        "ACCOUNT": [
            st.Page(
                whatsapp_page,
                title="WhatsApp",
                icon=":material/send:",
            ),
            st.Page(
                settings_page,
                title="Settings",
                icon=":material/settings:",
            ),
        ],
    },
    position="sidebar",
    expanded=True,
)

with st.sidebar:
    design_system.render_sidebar_account(st.session_state.name)
    if gemini_client is None:
        st.caption("Gemini not configured. Check Streamlit secrets.")
    else:
        st.caption("Gemini configured ✓")

try:
    navigation.run()
except sqlite3.Error:
    st.error("MacroSnap hit a local database error. Your saved data was not discarded.")
except Exception as error:
    safe_error(
        "MacroSnap encountered an unexpected issue. Please try again, and check the app logs if it continues.",
        error,
    )
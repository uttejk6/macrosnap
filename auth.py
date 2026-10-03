import logging
import re
from typing import Optional, Tuple

from twilio.rest import Client as TwilioClient


LOGGER = logging.getLogger("macrosnap.auth")


def normalize_phone_number(phone_number, default_country_code: str = "+91") -> Optional[str]:
    if phone_number is None:
        return None

    value = str(phone_number).strip()
    if not value:
        return None

    digits = re.sub(r"\D", "", value)
    if not digits:
        return None

    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) == 10:
        return f"{default_country_code}{digits}"

    cleaned_country = default_country_code.replace("+", "")
    if digits.startswith(cleaned_country) and len(digits) == len(cleaned_country) + 10:
        return f"+{digits}"

    if digits.startswith("91") and len(digits) == 12:
        return f"+{digits}"

    if digits.startswith("0") and len(digits) == 11:
        return f"{default_country_code}{digits[1:]}"

    if digits.isdigit() and 8 <= len(digits) <= 15:
        return f"+{digits}"

    return None


def validate_email_address(value) -> bool:
    if value is None:
        return False
    email = str(value).strip()
    if not email:
        return False
    return bool(re.fullmatch(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$", email))


def is_valid_otp_code(value) -> bool:
    if value is None:
        return False
    otp = str(value).strip()
    return bool(re.fullmatch(r"\d{6}", otp))


def mask_phone_number(phone_number: str) -> str:
    if not phone_number:
        return ""
    fallback = str(phone_number).strip()
    if "+" in fallback:
        digits = re.sub(r"\D", "", fallback)
        if len(digits) >= 10:
            return f"{fallback[:3]}******{fallback[-4:]}" if len(fallback) > 8 else fallback
    return "******"


def get_twilio_verify_client(account_sid: str, auth_token: str):
    if not account_sid or not auth_token:
        return None
    if "your_" in account_sid.lower() or "your_" in auth_token.lower():
        return None
    try:
        return TwilioClient(account_sid, auth_token)
    except Exception as error:
        LOGGER.warning("Twilio Verify client initialization failed (%s).", type(error).__name__)
        return None


def send_verification_code(target: str, channel: str, verify_service_sid: str, account_sid: str, auth_token: str) -> Tuple[bool, str]:
    if not target:
        return False, "Enter a valid phone number and try again."
    if not channel or not verify_service_sid:
        return False, "Phone verification is not configured. Check the Streamlit secrets."

    client = get_twilio_verify_client(account_sid, auth_token)
    if client is None:
        return False, "Phone verification is not configured. Check the Streamlit secrets."

    try:
        client.verify.v2.services(verify_service_sid).verifications.create(
            to=target,
            channel=channel,
        )
        return True, "OTP sent successfully."
    except Exception as error:
        LOGGER.warning("Twilio Verify could not send a code (%s).", type(error).__name__)
        return False, "Unable to send OTP right now. Please check your details and try again."


def verify_code(target: str, otp_code: str, verify_service_sid: str, account_sid: str, auth_token: str) -> Tuple[bool, str]:
    if not is_valid_otp_code(otp_code):
        return False, "Please enter the 6-digit OTP."

    if not target or not verify_service_sid:
        return False, "Phone verification is not configured. Check the Streamlit secrets."

    client = get_twilio_verify_client(account_sid, auth_token)
    if client is None:
        return False, "Phone verification is not configured. Check the Streamlit secrets."

    try:
        verification_check = client.verify.v2.services(verify_service_sid).verification_checks.create(
            to=target,
            code=str(otp_code).strip(),
        )
        status = str(getattr(verification_check, "status", "") or "")
        if status == "approved":
            return True, "✓ Account verified successfully!"
        if status in {"expired", "canceled"}:
            return False, "This OTP has expired. Please request a new OTP."
        return False, "Incorrect OTP. Please try again."
    except Exception as error:
        LOGGER.warning("Twilio Verify could not verify a code (%s).", type(error).__name__)
        return False, "Unable to verify OTP right now. Please try again."

import unittest
from unittest.mock import MagicMock, patch

from auth import (
    is_valid_otp_code,
    normalize_phone_number,
    send_verification_code,
    validate_email_address,
    verify_code,
)


class AuthHelperTests(unittest.TestCase):
    def test_normalize_phone_number_supports_indian_numbers(self):
        self.assertEqual(normalize_phone_number("9989764628", default_country_code="+91"), "+919989764628")
        self.assertEqual(normalize_phone_number("+91 99897 64628", default_country_code="+91"), "+919989764628")

    def test_normalize_phone_number_rejects_invalid_input(self):
        self.assertIsNone(normalize_phone_number("123", default_country_code="+91"))
        self.assertIsNone(normalize_phone_number("", default_country_code="+91"))

    def test_validate_email_address(self):
        self.assertTrue(validate_email_address("user@example.com"))
        self.assertFalse(validate_email_address("not-an-email"))
        self.assertFalse(validate_email_address(""))

    def test_is_valid_otp_code_requires_six_digits(self):
        self.assertTrue(is_valid_otp_code("012345"))
        self.assertFalse(is_valid_otp_code("12345"))
        self.assertFalse(is_valid_otp_code("12345a"))

    @patch("auth.get_twilio_verify_client")
    def test_send_verification_code_uses_twilio_verify(self, get_client):
        client = MagicMock()
        get_client.return_value = client

        sent, message = send_verification_code(
            "+919989764628",
            "sms",
            "VA123",
            "AC123",
            "token",
        )

        self.assertTrue(sent)
        self.assertEqual(message, "OTP sent successfully.")
        client.verify.v2.services("VA123").verifications.create.assert_called_once_with(
            to="+919989764628",
            channel="sms",
        )

    @patch("auth.get_twilio_verify_client")
    def test_verify_code_requires_approved_twilio_check(self, get_client):
        client = MagicMock()
        client.verify.v2.services.return_value.verification_checks.create.return_value.status = (
            "approved"
        )
        get_client.return_value = client

        verified, message = verify_code(
            "+919989764628",
            "012345",
            "VA123",
            "AC123",
            "token",
        )

        self.assertTrue(verified)
        self.assertIn("verified successfully", message)
        client.verify.v2.services("VA123").verification_checks.create.assert_called_once_with(
            to="+919989764628",
            code="012345",
        )

    @patch("auth.get_twilio_verify_client")
    def test_verify_code_rejects_invalid_code_before_calling_twilio(self, get_client):
        verified, message = verify_code(
            "+919989764628",
            "123",
            "VA123",
            "AC123",
            "token",
        )

        self.assertFalse(verified)
        self.assertEqual(message, "Please enter the 6-digit OTP.")
        get_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()

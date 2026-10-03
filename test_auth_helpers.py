import unittest

from auth import normalize_phone_number, validate_email_address


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

if __name__ == "__main__":
    unittest.main()

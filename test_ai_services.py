import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gemini_service
import nutrition
import whatsapp_service


class FakeGeminiModelError(Exception):
    code = 404


class FakeGeminiQuotaError(Exception):
    code = 429


class FakeGeminiUnavailableError(Exception):
    code = 503


class FakeTwilioError(Exception):
    code = 20003
    msg = "Rejected token private-token"


class GeminiServiceTests(unittest.TestCase):
    def test_model_candidates_put_configured_model_first_then_available_flash_models(self):
        client = SimpleNamespace(
            models=SimpleNamespace(
                list=Mock(
                    return_value=[
                        SimpleNamespace(
                            name="models/gemini-pro",
                            supported_actions=["embedContent"],
                        ),
                        SimpleNamespace(
                            name="models/gemini-z-flash",
                            supported_actions=["generateContent"],
                        ),
                        SimpleNamespace(
                            name="models/gemini-a-flash",
                            supported_actions=["generateContent"],
                        ),
                    ]
                )
            )
        )

        self.assertEqual(
            gemini_service.model_candidates(client, "custom-model"),
            ["custom-model", "gemini-a-flash", "gemini-z-flash"],
        )

    def test_generate_content_falls_back_to_a_listed_available_model(self):
        client = SimpleNamespace(
            models=SimpleNamespace(
                list=Mock(
                    return_value=[
                        SimpleNamespace(
                            name="models/gemini-supported-flash",
                            supported_actions=["generateContent"],
                        )
                    ]
                ),
                generate_content=Mock(
                    side_effect=[
                        FakeGeminiModelError("Model not found"),
                        SimpleNamespace(text="OK"),
                    ]
                ),
            )
        )

        response, model_name = gemini_service.generate_content(
            client,
            "not-enabled",
            "Test",
            "Test system prompt",
            configured_fallbacks=("gemini-supported-flash",),
        )

        self.assertEqual(response.text, "OK")
        self.assertEqual(model_name, "gemini-supported-flash")

    def test_generate_content_falls_back_after_an_empty_response(self):
        client = SimpleNamespace(
            models=SimpleNamespace(
                list=Mock(
                    return_value=[
                        SimpleNamespace(
                            name="models/gemini-supported-flash",
                            supported_actions=["generateContent"],
                        )
                    ]
                ),
                generate_content=Mock(
                    side_effect=[
                        SimpleNamespace(text=None),
                        SimpleNamespace(text="OK"),
                    ]
                ),
            )
        )

        response, model_name = gemini_service.generate_content(
            client,
            "empty-model",
            "Test",
            "Test system prompt",
            configured_fallbacks=("gemini-supported-flash",),
        )

        self.assertEqual(response.text, "OK")
        self.assertEqual(model_name, "gemini-supported-flash")

    def test_rate_limited_model_tries_only_one_available_fallback(self):
        client = SimpleNamespace(
            models=SimpleNamespace(
                list=Mock(
                    return_value=[
                        SimpleNamespace(
                            name="models/gemini-supported-flash",
                            supported_actions=["generateContent"],
                        )
                    ]
                ),
                generate_content=Mock(
                    side_effect=[
                        FakeGeminiQuotaError("rate limited"),
                        FakeGeminiModelError("Model not found"),
                        SimpleNamespace(text="OK"),
                    ]
                ),
            )
        )

        response, model_name = gemini_service.generate_content(
            client,
            "rate-limited-model",
            "Test",
            "Test system prompt",
        )

        self.assertEqual(response.text, "OK")
        self.assertEqual(model_name, "gemini-supported-flash")
        self.assertEqual(client.models.generate_content.call_count, 3)

    def test_temporary_503_retries_then_succeeds(self):
        client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=Mock(
                    side_effect=[
                        FakeGeminiUnavailableError("service unavailable"),
                        SimpleNamespace(text="OK"),
                    ]
                )
            )
        )

        with patch("gemini_service.time.sleep"):
            response, model_name = gemini_service.generate_content(
                client,
                "gemini-2.5-flash",
                "Test",
                "Test system prompt",
            )

        self.assertEqual(response.text, "OK")
        self.assertEqual(model_name, "gemini-2.5-flash")
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_503_has_actionable_temporary_error_message(self):
        self.assertEqual(
            gemini_service.friendly_error_message(
                FakeGeminiUnavailableError("service unavailable")
            ),
            "Gemini is temporarily busy. Please try again in a few seconds.",
        )

    def test_json_response_parser_accepts_fenced_json(self):
        self.assertEqual(
            gemini_service.parse_json_object('```json\n{"meal":"dal"}\n```'),
            {"meal": "dal"},
        )

    def test_food_response_keeps_reasonable_fiber_estimate_visible(self):
        meal = nutrition.parse_meal_response(
            json.dumps(
                {
                    "is_food": True,
                    "meal_name": "Dosa with sambar",
                    "food_items": [{"name": "Dosa", "portion": "2 medium"}],
                    "calories": 320,
                    "protein_g": 9,
                    "carbs_g": 52,
                    "fat_g": 8,
                    "fiber_g": 5,
                    "nutrition_notes": "Values are approximate estimates.",
                    "healthier_alternatives": [],
                }
            )
        )

        self.assertEqual(meal["fiber_g"], 5)
        self.assertIn("Estimated fiber: about 5.0 g.", meal["nutrition_notes"])
        self.assertIn("Fiber ~5.0 g", nutrition.format_meal_analysis(meal))


class WhatsAppServiceTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "TWILIO_ACCOUNT_SID": "AC" + "X" * 32,
            "TWILIO_AUTH_TOKEN": "private-token",
            "TWILIO_WHATSAPP_FROM": "whatsapp:+14155550123",
            "TWILIO_CONTENT_SID": "HX" + "X" * 32,
        }

    def test_normalizes_profile_number_and_sender(self):
        self.assertEqual(
            whatsapp_service.normalize_whatsapp_address("+919876543210"),
            "whatsapp:+919876543210",
        )
        self.assertEqual(
            whatsapp_service.normalize_whatsapp_sender("+14155550123"),
            "whatsapp:+14155550123",
        )

    def test_missing_settings_are_reported_by_name(self):
        self.assertEqual(
            whatsapp_service.missing_settings({"TWILIO_ACCOUNT_SID": "ACx"}),
            [
                "TWILIO_AUTH_TOKEN",
                "TWILIO_WHATSAPP_FROM",
                "TWILIO_CONTENT_SID",
            ],
        )

    def test_send_uses_twilio_content_template_and_summary_variables(self):
        client = SimpleNamespace(messages=SimpleNamespace(create=Mock(return_value=SimpleNamespace(sid="SM123"))))

        success, info = whatsapp_service.send_whatsapp_summary(
            "+919876543210",
            "Asha",
            "MacroSnap Daily Summary\nCalories: 100 / 1800 kcal",
            self.settings,
            client=client,
        )

        self.assertTrue(success)
        self.assertEqual(info, "SM123")
        call = client.messages.create.call_args.kwargs
        self.assertEqual(call["from_"], "whatsapp:+14155550123")
        self.assertEqual(call["to"], "whatsapp:+919876543210")
        self.assertEqual(call["content_sid"], self.settings["TWILIO_CONTENT_SID"])
        self.assertEqual(
            json.loads(call["content_variables"]),
            {
                "1": "Asha",
                "2": "MacroSnap Daily Summary\nCalories: 100 / 1800 kcal",
            },
        )

    def test_twilio_error_does_not_reveal_auth_token(self):
        client = SimpleNamespace(
            messages=SimpleNamespace(
                create=Mock(
                    side_effect=FakeTwilioError()
                )
            )
        )

        success, message = whatsapp_service.send_whatsapp_summary(
            "+919876543210",
            "Asha",
            "Summary",
            self.settings,
            client=client,
        )

        self.assertFalse(success)
        self.assertNotIn("private-token", message)
        self.assertIn("20003", message)

    def test_daily_summary_contains_targets_meal_slots_and_recommendation(self):
        profile = {
            "calorie_goal": 1800,
            "protein_goal": 100,
            "carb_goal": 200,
            "fat_goal": 60,
            "water_goal_ml": 2500,
            "weight_kg": 70,
            "goal": "Maintain weight",
        }
        totals = {
            "calories": 900,
            "protein_g": 45,
            "carbs_g": 100,
            "fat_g": 30,
        }
        message = whatsapp_service.build_daily_summary(
            profile,
            totals,
            1250,
            20,
            [
                {
                    "created_at": "2026-10-02T08:00:00+05:30",
                    "meal_name": "Dosa",
                    "calories": 320,
                }
            ],
            date(2026, 10, 2),
            suggestion={"meal": "Dal and vegetables", "time": "7:00 PM", "portion": "1 plate"},
        )

        self.assertIn("MacroSnap Daily Summary 🥗", message)
        self.assertIn("Calories: 900 / 1800 kcal", message)
        self.assertIn("Water: 1250 ml / 2500 ml", message)
        self.assertIn("Breakfast: Dosa (320 kcal)", message)
        self.assertIn("Suggested next meal: Dal and vegetables", message)
        self.assertLessEqual(len(message), 1497)


if __name__ == "__main__":
    unittest.main()

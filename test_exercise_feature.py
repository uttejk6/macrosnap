import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import database
import exercise
import reminder_worker


class ExerciseDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "exercise.db"
        self.phone = "+15550000001"
        database.init_db(self.database_path)
        database.save_user(
            self.phone,
            {"name": "Test", "exercise_equipment": ["Dumbbells"]},
            self.database_path,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_initialization_is_repeatable(self):
        database.init_db(self.database_path)
        database.init_db(self.database_path)
        profile = database.get_user(self.phone, self.database_path)
        self.assertEqual(json.loads(profile["exercise_equipment"]), ["Dumbbells"])

    def test_optional_measurements_update_without_erasing_same_day_values(self):
        measured_on = date(2026, 10, 1)
        database.save_body_measurements(
            self.phone, {"waist_cm": 84}, measured_on, self.database_path
        )
        database.save_body_measurements(
            self.phone, {"weight_kg": 72}, measured_on, self.database_path
        )
        measurements = database.get_body_measurements(
            self.phone, database_path=self.database_path
        )
        self.assertEqual(measurements[0]["waist_cm"], 84)
        self.assertEqual(measurements[0]["weight_kg"], 72)
        self.assertEqual(
            database.get_weight_history(self.phone, database_path=self.database_path)[0]["weight_kg"],
            72,
        )

    def test_workout_plan_and_logs_round_trip(self):
        workout_date = date(2026, 10, 1)
        plan = {"days": [{"date": workout_date.isoformat(), "exercises": []}]}
        database.save_workout_plan(self.phone, workout_date, plan, self.database_path)
        self.assertEqual(
            database.get_workout_plan(self.phone, workout_date, self.database_path)["plan"],
            plan,
        )
        database.save_workout_log(
            self.phone,
            workout_date,
            {"key": "bodyweight_squat", "name": "Bodyweight squat"},
            {"sets_completed": 3, "reps_completed": 10, "completed": True},
            self.database_path,
        )
        log = database.get_workout_logs(self.phone, database_path=self.database_path)[0]
        self.assertEqual(log["sets_completed"], 3)
        self.assertEqual(log["completed"], 1)

    def test_workout_reminder_claim_is_single_and_retryable(self):
        database.save_workout_reminder(
            self.phone, True, "08:00", "Full body", 20, self.database_path
        )
        now = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(
            len(database.claim_due_workout_reminders(now, database_path=self.database_path)),
            1,
        )
        self.assertEqual(
            database.claim_due_workout_reminders(now, database_path=self.database_path),
            [],
        )
        database.release_workout_reminder_claim(self.phone, self.database_path)
        self.assertEqual(
            len(database.claim_due_workout_reminders(now, database_path=self.database_path)),
            1,
        )
        database.mark_workout_reminder_sent(self.phone, now.date(), self.database_path)
        self.assertEqual(
            database.claim_due_workout_reminders(now, database_path=self.database_path),
            [],
        )

    def test_daily_summary_reminder_claim_is_single_and_retryable(self):
        database.save_daily_summary_reminder(
            self.phone, True, "20:00", self.database_path
        )
        now = datetime(2026, 10, 1, 20, 5, tzinfo=timezone.utc)
        self.assertEqual(
            len(database.claim_due_daily_summaries(now, database_path=self.database_path)),
            1,
        )
        self.assertEqual(
            database.claim_due_daily_summaries(now, database_path=self.database_path),
            [],
        )
        database.release_daily_summary_claim(self.phone, self.database_path)
        self.assertEqual(
            len(database.claim_due_daily_summaries(now, database_path=self.database_path)),
            1,
        )
        database.mark_daily_summary_sent(self.phone, now.date(), self.database_path)
        self.assertEqual(
            database.claim_due_daily_summaries(now, database_path=self.database_path),
            [],
        )


class ExerciseLogicTests(unittest.TestCase):
    def test_ai_plan_is_limited_to_available_catalog_and_time(self):
        profile = {
            "fitness_experience": "Beginner",
            "exercise_location": "Home",
            "exercise_equipment": [],
            "available_workout_minutes": 15,
        }
        payload = {
            "days": [
                {
                    "day": weekday,
                    "exercises": [
                        {"key": "dumbbell_row", "sets": 10, "duration_min": 50},
                        {"key": "bodyweight_squat", "sets": 3, "duration_min": 20},
                    ],
                }
                for weekday in exercise.WEEKDAYS
            ]
        }
        parsed = exercise.parse_workout_plan(
            json.dumps(payload), profile, date(2026, 10, 5)
        )
        self.assertIsNotNone(parsed)
        for day in parsed["days"]:
            self.assertEqual([item["key"] for item in day["exercises"]], ["bodyweight_squat"])
            self.assertLessEqual(day["exercises"][0]["duration_min"], 15)
            self.assertLessEqual(day["exercises"][0]["sets"], 5)
            self.assertLessEqual(
                sum(item["duration_min"] for item in day["exercises"]),
                10,
            )

    def test_workout_prompt_omits_account_identifiers(self):
        prompt = exercise.build_workout_plan_prompt(
            {"available_workout_minutes": 20},
            [{"user_phone": "+15550000001", "id": 18, "exercise_name": "Squat"}],
            date(2026, 9, 28),
            {"waist_cm": 84, "user_phone": "+15550000001"},
        )
        self.assertNotIn("+15550000001", prompt)
        self.assertNotIn('"id"', prompt)
        self.assertIn('"exercise_name": "Squat"', prompt)
        self.assertIn('"waist_cm": 84', prompt)

    def test_workout_reminder_uses_saved_plan_with_mocked_client(self):
        class Messages:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)

        class Client:
            def __init__(self):
                self.messages = Messages()

        now = datetime(2026, 10, 1, 18, 5, tzinfo=timezone.utc)
        reminder = {
            "user_phone": "+15550000001",
            "name": "Test",
            "focus": "Legs",
            "duration_minutes": 20,
        }
        plan = {
            "plan": {
                "days": [
                    {
                        "date": "2026-10-01",
                        "rest": False,
                        "exercises": [{"name": "Squat", "sets": 3, "reps": "8-12"}],
                    }
                ]
            }
        }
        client = Client()
        with patch.object(database, "claim_due_workout_reminders", return_value=[reminder]), \
             patch.object(database, "get_workout_plan", return_value=plan), \
             patch.object(database, "mark_workout_reminder_sent") as mark_sent:
            sent = reminder_worker.send_due_workout_reminders(
                now, client, "whatsapp:+100", "HXtemplate"
            )
        self.assertEqual(sent, 1)
        mark_sent.assert_called_once()
        variables = json.loads(client.messages.calls[0]["content_variables"])
        self.assertIn("Squat", variables["2"])

    def test_daily_summary_worker_uses_mocked_client(self):
        class Messages:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)

        class Client:
            def __init__(self):
                self.messages = Messages()

        now = datetime(2026, 10, 1, 20, 5, tzinfo=timezone.utc)
        reminder = {"user_phone": "+15550000001", "name": "Test"}
        client = Client()
        with patch.object(database, "claim_due_daily_summaries", return_value=[reminder]), \
             patch.object(database, "get_daily_totals", return_value={"calories": 1200, "protein_g": 80, "carbs_g": 140, "fat_g": 40}), \
             patch.object(database, "get_water", return_value=1500), \
             patch.object(database, "get_meals", return_value=[]), \
             patch.object(database, "get_workout_logs", return_value=[]), \
             patch.object(database, "mark_daily_summary_sent") as mark_sent:
            sent = reminder_worker.send_due_daily_summaries(
                now, client, "whatsapp:+100", "HXtemplate"
            )
        self.assertEqual(sent, 1)
        mark_sent.assert_called_once()
        variables = json.loads(client.messages.calls[0]["content_variables"])
        self.assertIn("Calories: 1200", variables["2"])
        self.assertIn("Water: 1500 ml", variables["2"])


if __name__ == "__main__":
    unittest.main()
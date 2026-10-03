# MacroSnap nutrition and workout tracking

MacroSnap stores profiles, meal history, exercise preferences, workout plans, measurements, and reminder settings in SQLite. Scheduled reminder delivery runs in a separate worker process, not in the Streamlit browser session.

## Exercise

The Exercise page includes an editable, AI-personalized weekly plan, a filtered exercise library, original four-step movement diagrams, workout logging, and optional body-measurement trends. Gemini-generated plans are limited to the built-in exercise library and the user's available equipment and time. If Gemini is unavailable, the page can use a conservative starter plan.

The Exercise page also supports single-photo exercise guidance. Choose a fitness goal and movement (or Auto Detect Exercise), upload a JPG, PNG, or WEBP photo, and select **Analyze Exercise**. Results are visual, general observations only; they are not a medical assessment or a full movement analysis. Video analysis is not enabled.

Exercise and body-composition guidance is educational, not medical advice. Exercises can strengthen selected muscles but cannot selectively remove fat from one body area. Stop for chest pain, severe pain, dizziness, fainting, serious injury, or difficulty breathing; users with relevant medical conditions, pregnancy, or significant injuries should consult a qualified healthcare professional before exercising.

Exercise activity is tracked separately from food intake. Workout calories are not automatically subtracted from calorie targets.

## Run the app

From the project directory:

```powershell
.\venv\Scripts\python.exe -m streamlit run app.py --server.port 8506
```

The local run command uses port 8506. Streamlit Community Cloud supplies its own port when it starts the app.

## Deploy on Streamlit Community Cloud

Create an app from the `uttejk6/macrosnap` GitHub repository, select the `main` branch, and set `app.py` as the entry point. Add the required credentials under the app's **Settings → Secrets** before sharing its URL:

```toml
TWILIO_ACCOUNT_SID = "your-account-sid"
TWILIO_AUTH_TOKEN = "your-auth-token"
TWILIO_VERIFY_SERVICE_SID = "your-verify-service-sid"

# Optional AI features
GEMINI_API_KEY = "your-gemini-api-key"
GEMINI_MODEL = "gemini-2.5-flash"

# Optional WhatsApp reminders
TWILIO_WHATSAPP_FROM = "whatsapp:+your-enabled-sender-number"
TWILIO_CONTENT_SID = "your-approved-content-template-sid"
```

Phone sign-in requires an active Twilio Verify service that can send SMS to the user's number. Keep credentials in Cloud Secrets; never add them to the repository. Community Cloud's local filesystem is not durable storage, so the SQLite database may be reset when the app restarts. Use a persistent hosted database before relying on the deployment for real user records.

## Configure Twilio

Keep credentials in `.streamlit/secrets.toml`. Replace every `XXXX` placeholder with a value from the corresponding provider; never commit this file.

```toml
GEMINI_API_KEY = "XXXX"
GEMINI_MODEL = "gemini-2.5-flash"
# Optional: GEMINI_MODEL_FALLBACKS = "model-id-1,model-id-2"

TWILIO_ACCOUNT_SID = "XXXX"
TWILIO_AUTH_TOKEN = "XXXX"
TWILIO_WHATSAPP_FROM = "whatsapp:+XXXX"
TWILIO_CONTENT_SID = "XXXX"
```

The app checks the configured Gemini model and falls back to models exposed by the configured API key when needed. Use the **Test Gemini connection** button in Settings to check access.

The approved Twilio Content Template must accept two variables: `{{1}}` for the user's name and `{{2}}` for the summary/reminder text. The WhatsApp sender must be enabled for that template. The WhatsApp page preview includes daily consumed-versus-target macros, water, completed exercise, meals grouped by approximate time, weight, and a next-meal suggestion. An optional control can ask Gemini to personalize that suggestion.

## Run the reminder worker

From the project directory, start the worker in a separate process:

```powershell
.\venv\Scripts\python.exe reminder_worker.py
```

The process polls once a minute for meal reminders, workout reminders, and enabled daily summaries and can be stopped with `Ctrl+C`. Notification toggles and daily summary time are managed from Settings; meal-slot times remain in Meal Planner. Messages use the configured Twilio Content Template and include today's saved workout when available. Workout completion and progress are logged in MacroSnap; replying to a WhatsApp message is not currently wired to an inbound webhook.

For reminders to continue after closing the browser or signing out of Windows, configure Windows Task Scheduler to run this command at system startup under an account that can access the project and network. Set the task's **Start in** directory to the MacroSnap project folder and enable restart-on-failure.

The worker shares the app's SQLite file. Keep `MACROSNAP_DB_PATH` unset for the default `macrosnap.db`, or set it identically for both the app and worker when using a custom database path.

## Install dependencies

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

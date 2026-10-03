import logging
import re
import time

from google import genai
from google.genai import types


LOGGER = logging.getLogger("macrosnap.gemini")
DEFAULT_MODEL_NAME = "gemini-3-flash-preview"
TEMPORARY_ERROR_MARKERS = ("503", "unavailable", "resource_exhausted", "429")
MODEL_ERROR_MARKERS = (
    "not found",
    "does not exist",
    "unsupported model",
    "model is not supported",
    "invalid model",
)
MAX_DISCOVERED_FALLBACKS = 4


def get_client(api_key):
    if not api_key or "your_" in api_key.lower():
        return None
    return genai.Client(api_key=api_key)


def _model_name(model):
    name = getattr(model, "name", None)
    if not name:
        return None
    return str(name).rsplit("/", 1)[-1]


def _supports_generate_content(model):
    actions = (
        getattr(model, "supported_actions", None)
        or getattr(model, "supported_generation_methods", None)
    )
    if not actions:
        return True
    if isinstance(actions, str):
        actions = [actions]
    return any("generatecontent" in str(action).replace("_", "").lower() for action in actions)


def discover_model_names(client):
    try:
        models = client.models.list()
        discovered = {
            name
            for model in models
            if _supports_generate_content(model)
            if (name := _model_name(model))
            and name.startswith("gemini-")
            and not any(
                marker in name.lower()
                for marker in ("-image", "-tts", "audio", "-live", "embedding")
            )
        }
    except Exception as error:
        LOGGER.warning("Gemini model discovery failed (%s).", type(error).__name__)
        return []

    return sorted(
        discovered,
        key=lambda name: (
            "flash" not in name.lower(),
            "preview" in name.lower(),
            name,
        ),
    )


def model_candidates(client, preferred_model, configured_fallbacks=()):
    candidates = []
    for model_name in (preferred_model, *configured_fallbacks, *discover_model_names(client)):
        normalized = str(model_name or "").strip().rsplit("/", 1)[-1]
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _configured_candidates(preferred_model, configured_fallbacks):
    candidates = []
    for model_name in (
        preferred_model,
        *configured_fallbacks,
        DEFAULT_MODEL_NAME,
    ):
        normalized = str(model_name or "").strip().rsplit("/", 1)[-1]
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _error_status(error):
    return getattr(error, "code", None) or getattr(error, "status_code", None)


def _is_model_error(error):
    message = str(error).lower()
    return (
        _error_status(error) == 404
        or any(marker in message for marker in MODEL_ERROR_MARKERS)
        or ("model" in message and "not available" in message)
    )


def _is_temporary_error(error):
    message = str(error).lower()
    status = _error_status(error)
    return status in (429, 503) or any(marker in message for marker in TEMPORARY_ERROR_MARKERS)


def friendly_error_message(error):
    status = _error_status(error)
    message = str(error).lower()
    if status in (401, 403) or "api key" in message or "permission" in message:
        return "Gemini could not authenticate this request. Check GEMINI_API_KEY and API access."
    if status == 404 or _is_model_error(error):
        return "Gemini is temporarily unavailable. Please check your API key and model access."
    if status == 429 or "quota" in message or "resource_exhausted" in message:
        return (
            "Google Gemini has rate-limited this API key. Wait for the quota to reset, "
            "or check Google AI Studio → Usage and billing for this project's limits. "
            "Trying another model cannot bypass a project-wide quota."
        )
    if status == 503 or "unavailable" in message:
        return "Gemini is temporarily unavailable. Please try again shortly."
    return "Gemini could not complete the request. Check the connection and API configuration, then try again."


def _generate_for_candidates(client, preferred_model, contents, config, configured_fallbacks=()):
    candidates = _configured_candidates(preferred_model, configured_fallbacks)
    last_error = None
    discovered = False
    index = 0
    while index < len(candidates):
        model_name = candidates[index]
        index += 1
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as error:
                last_error = error
                if _is_model_error(error) or _error_status(error) == 429:
                    LOGGER.info("Gemini model %s is unavailable (%s).", model_name, type(error).__name__)
                    if not discovered:
                        discovered = True
                        available_fallback = next(
                            (
                                available
                                for available in discover_model_names(client)
                                if available not in candidates
                            ),
                            None,
                        )
                        if available_fallback:
                            candidates.append(available_fallback)
                    break
                if _is_temporary_error(error) and attempt < 2:
                    time.sleep(1 + attempt)
                    continue
                if _is_temporary_error(error):
                    LOGGER.warning(
                        "Gemini model %s remained unavailable after retries (%s).",
                        model_name,
                        type(error).__name__,
                    )
                    break
                raise
            if getattr(response, "text", None):
                return response, model_name

            last_error = RuntimeError(
                f"Gemini model {model_name} returned an empty response."
            )
            LOGGER.info("Gemini model %s returned no text.", model_name)
            if not discovered:
                discovered = True
                for available_model in discover_model_names(client)[
                    :MAX_DISCOVERED_FALLBACKS
                ]:
                    if available_model not in candidates:
                        candidates.append(available_model)
            break

    if last_error is not None:
        raise last_error
    raise RuntimeError("No Gemini models are available for content generation.")


def generate_content(
    client,
    preferred_model,
    contents,
    system_instruction,
    json_response=False,
    configured_fallbacks=(),
):
    if client is None:
        raise ValueError("Gemini is not configured.")

    config = {"system_instruction": system_instruction}
    if json_response:
        config["response_mime_type"] = "application/json"
    return _generate_for_candidates(
        client,
        preferred_model,
        contents,
        types.GenerateContentConfig(**config),
        configured_fallbacks,
    )


def create_chat(
    client,
    preferred_model,
    system_instruction,
    configured_fallbacks=(),
):
    if client is None:
        return None, None

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
    )
    last_error = None
    candidates = _configured_candidates(preferred_model, configured_fallbacks)
    discovered = False
    index = 0
    while index < len(candidates):
        model_name = candidates[index]
        index += 1
        try:
            return client.chats.create(model=model_name, config=config), model_name
        except Exception as error:
            last_error = error
            if _is_model_error(error) or _error_status(error) == 429:
                LOGGER.info("Gemini chat model %s is unavailable (%s).", model_name, type(error).__name__)
                if not discovered:
                    discovered = True
                    available_fallback = next(
                        (
                            available
                            for available in discover_model_names(client)
                            if available not in candidates
                        ),
                        None,
                    )
                    if available_fallback:
                        candidates.append(available_fallback)
                continue
            break

    if last_error is not None:
        LOGGER.warning("Gemini chat initialization failed (%s).", type(last_error).__name__)
    return None, None


def check_model(client, model_name, configured_fallbacks=()):
    if client is None:
        return False, "Gemini is not configured. Add GEMINI_API_KEY to Streamlit secrets."
    if not model_name:
        return False, "Set GEMINI_MODEL to the model name enabled for your API key."

    try:
        _, working_model = _generate_for_candidates(
            client,
            model_name,
            "Reply with OK.",
            types.GenerateContentConfig(max_output_tokens=64),
            configured_fallbacks,
        )
    except Exception as error:
        LOGGER.warning("Gemini model diagnostic failed (%s).", type(error).__name__)
        return False, "Gemini could not use the configured model. Check the API key and model access."

    if working_model == model_name:
        return True, f"Gemini is connected and {model_name} is available."
    return True, f"Gemini is connected. {model_name} is unavailable; using {working_model} as a fallback."


def parse_json_object(value):
    import json

    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("The Gemini response was not a JSON object.")
    return result

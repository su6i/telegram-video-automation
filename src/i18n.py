import os

_MESSAGES = {
    "en": {
        "welcome": "🚀 Telegram Video Automation CLI",
        "error_no_action": "❌ Error: No action specified. Please choose an action (e.g., --url, --scan)."
    },
    "fr": {
        "welcome": "🚀 Automatisation Vidéo Telegram CLI",
        "error_no_action": "❌ Erreur : Aucune action spécifiée. Veuillez choisir une action (ex : --url, --scan)."
    },
    "fa": {
        "welcome": "🚀 اتوماسیون ویدیو تلگرام CLI",
        "error_no_action": "❌ خطا: هیچ عملیاتی مشخص نشده است. لطفا یک عملیات انتخاب کنید (مانند --url, --scan)."
    }
}

def get_message(key, lang=None):
    if not lang:
        lang = os.environ.get("LANG", "en").split('_')[0]
        if lang not in _MESSAGES:
            lang = "en"
    return _MESSAGES.get(lang, _MESSAGES["en"]).get(key, key)

def t(key):
    return get_message(key)

from Mibs.settings import TEMPLATES

TEMPLATES[0]["OPTIONS"]["context_processors"].append(
    "biometric.context_processors.biometric_is_installed",
)

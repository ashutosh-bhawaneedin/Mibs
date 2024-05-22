from Mibs.settings import TEMPLATES

TEMPLATES[0]["OPTIONS"]["context_processors"].append(
    "Mibs_crumbs.context_processors.breadcrumbs",
)

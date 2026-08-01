from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
    label = "knowledge"
    verbose_name = "Knowledge"

    def ready(self):
        # Ensure Celery discovers ingest task even if not imported elsewhere.
        from apps.knowledge import tasks  # noqa: F401

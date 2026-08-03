from django.apps import AppConfig

class ListeningToolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # full dotted path since the app is nested under the project package
    name = "ai_listening_tool.listening_tool"

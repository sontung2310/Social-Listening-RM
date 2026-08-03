from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "tool/",
        include(("ai_listening_tool.listening_tool.urls", "listening_tool"),
                namespace="listening_tool"),
    ),
]

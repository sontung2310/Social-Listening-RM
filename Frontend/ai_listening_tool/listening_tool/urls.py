from django.urls import path
from . import views

app_name = "listening_tool"
urlpatterns = [
    path("", views.search_page, name="search"),
    path("results/", views.results_page, name="results"),
    path("simple/", views.simple_results_page, name="simple_results"),
    path("debug/", views.debug_results_page, name="debug_results"),
    path("history/", views.history_page, name="history"),
]
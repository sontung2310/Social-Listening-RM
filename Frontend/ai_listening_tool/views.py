# ai_listening_tool/views.py
from django.shortcuts import render

def search_page(request):
    return render(request, "search.html")


def results_page(request):
    return render(request, "results.html")


def history_page(request):
    return render(request, "history.html")

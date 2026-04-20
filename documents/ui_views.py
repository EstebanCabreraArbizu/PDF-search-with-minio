from django.shortcuts import render


def login_ui(request):
    return render(request, "documents/login.html")


def constancias_ui(request):
    return render(request, "documents/search_constancias.html")

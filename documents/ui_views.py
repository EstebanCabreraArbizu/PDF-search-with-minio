from django.shortcuts import render


def login_ui(request):
    return render(request, "documents/login.html")


def constancias_ui(request):
    return render(
        request,
        "documents/search_constancias.html",
        {
            "active_module": "constancias",
            "active_admin": "",
        },
    )


def files_ui(request):
    requested_section = str(request.GET.get("section", "")).strip().lower()
    active_admin = "sync" if requested_section == "sync" else "files"

    return render(
        request,
        "documents/search_files.html",
        {
            "active_module": "",
            "active_admin": active_admin,
        },
    )

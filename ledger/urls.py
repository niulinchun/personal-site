from django.urls import path

from ledger import views

app_name = "ledger"

urlpatterns = [
    path("", views.ledger_index, name="index"),
    path("report/", views.ledger_report, name="report"),
    # API
    path("api/records/", views.api_records_dispatch, name="api_records"),
    path("api/records/<int:pk>/", views.api_record_detail, name="api_record_detail"),
    path("api/categories/", views.api_categories, name="api_categories"),
]

from django.urls import path

from . import collect, views

app_name = "svederlytics"
urlpatterns = [
    path("", collect.collect, name="collect"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("session/<int:pk>/", views.session_detail, name="session"),
    path("visitor/<int:pk>/", views.visitor_detail, name="visitor"),
]

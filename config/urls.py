from django.urls import path

from planner import views

urlpatterns = [
    path("api/health", views.health),
    path("api/plan", views.plan),
]

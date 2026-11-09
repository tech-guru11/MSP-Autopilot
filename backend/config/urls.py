from accounts.views import MeView
from customers.views import CustomerViewSet
from django.contrib import admin
from django.urls import include, path
from incidents.views import (
    AlertViewSet,
    IncidentViewSet,
    RemediationActionViewSet,
)
from infrastructure.views import AssetViewSet
from organizations.views import (
    MembershipViewSet,
    OrganizationViewSet,
)
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from config.views import health, task_status

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")
router.register("memberships", MembershipViewSet, basename="membership")
router.register("customers", CustomerViewSet, basename="customer")
router.register("assets", AssetViewSet, basename="asset")
router.register("incidents", IncidentViewSet, basename="incident")
router.register("alerts", AlertViewSet, basename="alert")
router.register(
    "remediation-actions",
    RemediationActionViewSet,
    basename="remediation-action",
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/health/", health, name="api-health"),
    path(
        "api/tasks/<str:task_id>/",
        task_status,
        name="task-status",
    ),
    path("api-token-auth/", obtain_auth_token, name="api-token-auth"),
    path("api/me/", MeView.as_view(), name="me"),
    path("api-auth/", include("rest_framework.urls")),
    path("api/", include(router.urls)),
]

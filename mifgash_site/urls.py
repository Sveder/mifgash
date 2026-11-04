from django.contrib import admin
from django.urls import include, path

from planner import ops

ops.limit_admin_login(admin.site)  # T278: same login cap as /ops/login/

urlpatterns = [
    path("ops/", ops.ops, name="ops"),
    path("ops/login/", ops.OpsLogin.as_view(), name="ops_login"),
    path("ops/admin/", admin.site.urls),
    path("_sl/", include("svederlytics.urls")),
    path("api/v1/", include("planner.api_urls")),
    path("", include("planner.urls")),
]

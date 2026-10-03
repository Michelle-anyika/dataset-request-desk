from rest_framework.routers import SimpleRouter

from apps.requests_desk.import_views import RequestImportViewSet
from apps.requests_desk.views import DatasetRequestViewSet

router = SimpleRouter()
router.register("requests", DatasetRequestViewSet, basename="request")
router.register("request-imports", RequestImportViewSet, basename="request-import")

urlpatterns = router.urls

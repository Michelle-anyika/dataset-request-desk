from rest_framework.routers import SimpleRouter

from apps.requests_desk.views import DatasetRequestViewSet

router = SimpleRouter()
router.register("requests", DatasetRequestViewSet, basename="request")

urlpatterns = router.urls

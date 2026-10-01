from rest_framework.routers import SimpleRouter

from apps.catalog.views import ImportBatchViewSet

router = SimpleRouter()
router.register("imports", ImportBatchViewSet, basename="import")

urlpatterns = router.urls

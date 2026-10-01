from rest_framework.routers import SimpleRouter

from apps.catalog.views import EpisodeViewSet, ImportBatchViewSet

router = SimpleRouter()
router.register("imports", ImportBatchViewSet, basename="import")
router.register("episodes", EpisodeViewSet, basename="episode")

urlpatterns = router.urls

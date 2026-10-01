from django.db import models

# Robots the recording system is known to use (seed/README.md). Episodes for any other robot are rejected.
KNOWN_ROBOTS = ("arm-01", "arm-02", "arm-03", "mobile-01", "humanoid-01")


class Robot(models.Model):
    id = models.CharField(primary_key=True, max_length=32)  # natural key from the recording system
    kind = models.CharField(max_length=32)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "robots"
        ordering = ["id"]

    def __str__(self):
        return self.id

    @staticmethod
    def kind_from_id(robot_id: str) -> str:
        """`arm-01` -> `arm`."""
        return robot_id.rsplit("-", 1)[0]


class Quality(models.TextChoices):
    GOOD = "good", "Good"
    USABLE = "usable", "Usable"
    BAD = "bad", "Bad"


# Only these can be delivered to clients.
ASSIGNABLE_QUALITIES = (Quality.GOOD, Quality.USABLE)


class Episode(models.Model):
    """One recorded clip, imported from the recording system's CSV export.

    bigint primary key, not UUID: this is the high-volume table (millions of rows), so its indexes stay small.
    """

    episode_id = models.CharField(max_length=32, unique=True)  # natural key from the recording system
    robot = models.ForeignKey(Robot, on_delete=models.PROTECT, related_name="episodes")
    task_name = models.CharField(max_length=120)  # normalised, see apps.catalog.normalise
    recorded_at = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()
    operator_name = models.CharField(max_length=100, blank=True)  # optional in the export
    quality = models.CharField(max_length=8, choices=Quality.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "episodes"
        ordering = ["-recorded_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_seconds__gt=0), name="episodes_duration_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(quality__in=Quality.values), name="episodes_quality_valid"
            ),
        ]
        indexes = [
            # Analytics: episodes per day per robot over a date range.
            models.Index(fields=["recorded_at", "robot"], name="episodes_recorded_robot_idx"),
            # Analytics top tasks by good episodes, and the operator's task/quality filters.
            models.Index(fields=["quality", "task_name"], name="episodes_quality_task_idx"),
        ]

    def __str__(self):
        return self.episode_id

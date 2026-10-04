from django.conf import settings
from django.db import models
from django.utils import timezone

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
    # The import that last created or changed this episode: traceability back to the source file.
    import_batch = models.ForeignKey(
        "ImportBatch", on_delete=models.SET_NULL, null=True, blank=True, related_name="episodes"
    )
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
            # The assignment screen: one task's episodes, newest first, and their count for pagination.
            models.Index(fields=["task_name", "recorded_at"], name="episodes_task_recorded_idx"),
        ]

    def __str__(self):
        return self.episode_id


class ImportStatus(models.TextChoices):
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ImportBatch(models.Model):
    """One run of the episode import, kept as its report."""

    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64)  # recognises the same file imported again
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=ImportStatus.choices, default=ImportStatus.RUNNING)
    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    fixed_count = models.PositiveIntegerField(default=0)  # imported rows whose values had to be normalised
    error_message = models.TextField(blank=True)  # why a failed import stopped
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "import_batches"
        ordering = ["-started_at", "-id"]

    def __str__(self):
        return f"{self.file_name} ({self.status})"


class IssueSeverity(models.TextChoices):
    SKIPPED = "skipped", "Skipped"  # the row was not imported
    FIXED = "fixed", "Fixed"  # the row was imported after normalising a value


class ImportRowIssue(models.Model):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="issues")
    row_number = models.PositiveIntegerField()  # line in the file, so a person can find it
    episode_id = models.CharField(max_length=64, blank=True)
    severity = models.CharField(max_length=8, choices=IssueSeverity.choices)
    reason_code = models.CharField(max_length=50)
    message = models.TextField()
    raw_row = models.JSONField(default=dict)  # the original values, exactly as read

    class Meta:
        db_table = "import_row_issues"
        ordering = ["row_number", "id"]
        indexes = [models.Index(fields=["batch", "severity"], name="issues_batch_severity_idx")]

    def __str__(self):
        return f"line {self.row_number}: {self.reason_code}"

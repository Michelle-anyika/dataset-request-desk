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

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower


class Role(models.TextChoices):
    CLIENT = "client", "Client"
    OPERATOR = "operator", "Operator"
    ADMIN = "admin", "Admin"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **fields):
        email = (email or "").strip().lower()
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=email, **fields)
        user.set_password(password)  # hashes with the configured hasher (PBKDF2)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **fields):
        fields["role"] = Role.ADMIN
        return self.create_user(email, password, **fields)


class User(AbstractBaseUser):
    """Email login with a single role.

    Authorization is role-based, so Django's group and permission tables are not used.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True)
    full_name = models.CharField(max_length=150)
    organisation = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CLIENT)
    # Deactivate instead of delete: requests and audit events keep pointing at the user.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="users_email_ci_unique"),
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="users_role_valid"),
        ]

    def __str__(self):
        return self.email

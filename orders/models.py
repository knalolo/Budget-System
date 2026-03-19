"""Models for the orders app: Project and ExpenseCategory."""

from django.db import models


class Project(models.Model):
    """An MC-numbered project that purchase requests are charged against."""

    mc_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["mc_number"]

    def __str__(self) -> str:
        return f"{self.mc_number} - {self.name}"


class ExpenseCategory(models.Model):
    """A category used to classify project expenses (e.g., Prototype, Materials)."""

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Expense categories"

    def __str__(self) -> str:
        return self.name

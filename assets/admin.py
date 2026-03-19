"""Django admin registrations for the assets app."""

from django.contrib import admin

from .models import AssetItem, AssetRegistration


class AssetItemInline(admin.TabularInline):
    model = AssetItem
    extra = 0
    fields = [
        "asset_name",
        "asset_tag",
        "category",
        "serial_number",
        "purchase_date",
        "purchase_cost",
        "supplier",
        "location",
        "department",
        "assigned_to",
        "notes",
    ]


@admin.register(AssetRegistration)
class AssetRegistrationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "requester",
        "purchase_request",
        "status",
        "item_count",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["requester__username", "requester__first_name", "notes"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [AssetItemInline]

    @admin.display(description="Items")
    def item_count(self, obj: AssetRegistration) -> int:
        return obj.items.count()

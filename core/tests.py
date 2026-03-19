from decimal import Decimal

from django.test import TestCase

from .models import (
    ApprovalLog,
    CostItem,
    PORequest,
    PORequestStatus,
    Project,
    ProjectBudget,
)


class PORequestApprovalTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            project_code="PRJ-001",
            project_name="Budget System",
        )
        self.cost_item = CostItem.objects.create(
            code="EXT",
            name="External Services",
        )
        self.budget = ProjectBudget.objects.create(
            project=self.project,
            cost_item=self.cost_item,
            approved_budget=Decimal("1000.00"),
            actual_spent=Decimal("0.00"),
        )

    def test_budget_updates_when_po_is_created_as_approved(self):
        PORequest.objects.create(
            request_no="PO-001",
            project=self.project,
            cost_item=self.cost_item,
            requester_name="Alice",
            supplier_name="Vendor A",
            description="Approved purchase",
            amount=Decimal("120.00"),
            status=PORequestStatus.APPROVED,
        )

        self.budget.refresh_from_db()
        self.assertEqual(self.budget.actual_spent, Decimal("120.00"))
        self.assertEqual(ApprovalLog.objects.count(), 1)

    def test_budget_updates_only_once_when_status_becomes_approved(self):
        po_request = PORequest.objects.create(
            request_no="PO-002",
            project=self.project,
            cost_item=self.cost_item,
            requester_name="Bob",
            supplier_name="Vendor B",
            description="Submitted purchase",
            amount=Decimal("200.00"),
            status=PORequestStatus.SUBMITTED,
        )

        self.budget.refresh_from_db()
        self.assertEqual(self.budget.actual_spent, Decimal("0.00"))

        po_request.status = PORequestStatus.APPROVED
        po_request.save()

        self.budget.refresh_from_db()
        self.assertEqual(self.budget.actual_spent, Decimal("200.00"))
        self.assertEqual(ApprovalLog.objects.count(), 1)

        po_request.approval_comment = "Approved and saved again"
        po_request.save()

        self.budget.refresh_from_db()
        self.assertEqual(self.budget.actual_spent, Decimal("200.00"))
        self.assertEqual(ApprovalLog.objects.count(), 1)

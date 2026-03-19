from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, get_object_or_404
from .models import Project, ProjectBudget


def dashboard(request):
    projects = Project.objects.all().prefetch_related("budgets__cost_item")

    total_approved = sum(project.total_approved_budget for project in projects)
    total_actual = sum(project.total_actual_spent for project in projects)
    total_remaining = sum(project.total_remaining_budget for project in projects)

    context = {
        "projects": projects,
        "total_approved": total_approved,
        "total_actual": total_actual,
        "total_remaining": total_remaining,
    }
    return render(request, "core/dashboard.html", context)


def project_detail(request, project_id):
    project = get_object_or_404(
        Project.objects.prefetch_related("budgets__cost_item"),
        id=project_id
    )

    budgets = ProjectBudget.objects.filter(project=project).select_related("cost_item")

    context = {
        "project": project,
        "budgets": budgets,
    }
    return render(request, "core/project_detail.html", context)
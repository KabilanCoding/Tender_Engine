"""
Calculation helper for the Project Estimation module.
Implements the Excel-style formula logic for feature hours, project overheads,
resource allocation and cost summary.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.estimation_project import EstimationProject

# ---------------------------------------------------------------------------
# Complexity-to-hours lookup
# ---------------------------------------------------------------------------
COMPLEXITY_HOURS: dict[str, dict[str, float]] = {
    "data_model":     {"simple": 1,  "medium": 2,  "complex": 3},
    "api":            {"simple": 1,  "medium": 3,  "complex": 6},
    "business_rules": {"simple": 3,  "medium": 6,  "complex": 12},
    "ui":             {"simple": 4,  "medium": 10, "complex": 15},
}

# QA split ratios (must sum to 0.40)
QA_PLAN_RATIO       = 0.12
QA_EXECUTION_RATIO  = 0.16
QA_REGRESSION_RATIO = 0.12
QA_TOTAL_RATIO      = 0.40  # plan + execution + regression

# ---------------------------------------------------------------------------
# Default roles
# ---------------------------------------------------------------------------
DEFAULT_ROLES: list[dict] = [
    {
        "role": "Solution Architect",
        "responsibility": "Overall design, architecture, technical reviews",
        "count": 1,
        "effort_pct": 0.05,
        "hourly_rate": 2000.0,
        "sort_order": 1,
    },
    {
        "role": "Backend Developers",
        "responsibility": "Core logic, APIs, tracking engine, AI integration",
        "count": 2,
        "effort_pct": 0.25,
        "hourly_rate": 1600.0,
        "sort_order": 2,
    },
    {
        "role": "Frontend Developers",
        "responsibility": "Web admin panels, dashboards, UI",
        "count": 2,
        "effort_pct": 0.20,
        "hourly_rate": 1600.0,
        "sort_order": 3,
    },
    {
        "role": "QA Engineers",
        "responsibility": "Functional testing, regression, UAT, go-live support",
        "count": 1,
        "effort_pct": 0.05,
        "hourly_rate": 1200.0,
        "sort_order": 4,
    },
    {
        "role": "Project Manager",
        "responsibility": "Planning, tracking, delivery, stakeholder coordination",
        "count": 1,
        "effort_pct": 0.05,
        "hourly_rate": 2000.0,
        "sort_order": 5,
    },
    {
        "role": "UI / UX",
        "responsibility": "Wireframes, user journeys, design system",
        "count": 1,
        "effort_pct": 0.04,
        "hourly_rate": 1000.0,
        "sort_order": 6,
    },
    {
        "role": "Business Analyst (BA)",
        "responsibility": "Requirements, process flows, user stories, UAT support",
        "count": 1,
        "effort_pct": 0.04,
        "hourly_rate": 1200.0,
        "sort_order": 7,
    },
    {
        "role": "DevOps",
        "responsibility": "CI/CD, environments, deployments, monitoring",
        "count": 1,
        "effort_pct": 0.04,
        "hourly_rate": 1600.0,
        "sort_order": 8,
    },
]


# ---------------------------------------------------------------------------
# Per-feature calculation
# ---------------------------------------------------------------------------
def _complexity_hours(component: str, complexity: str | None) -> float:
    """Return the hours for one component at the given complexity level."""
    if not complexity:
        return 0.0
    return COMPLEXITY_HOURS.get(component, {}).get(complexity.lower(), 0.0)


def calc_feature(feature_row, project_settings) -> dict:
    """
    Compute all derived hours for a single feature row.

    Parameters
    ----------
    feature_row :
        An EstimationFeature ORM object (or any object with matching attrs).
    project_settings :
        An EstimationProject ORM object carrying the buffer percentages.

    Returns
    -------
    dict with keys: base_hours, total_dev_hours, total_qa_hours, total_hours
    """
    data_model_hrs      = _complexity_hours("data_model",     feature_row.data_model_complexity)
    api_hrs             = _complexity_hours("api",            feature_row.api_complexity)
    business_rules_hrs  = _complexity_hours("business_rules", feature_row.business_rules_complexity)
    ui_hrs              = _complexity_hours("ui",             feature_row.ui_complexity)
    fixed_hrs           = float(feature_row.fixed_hours or 0)

    base_hours = data_model_hrs + api_hrs + business_rules_hrs + ui_hrs + fixed_hrs

    complexity_adj    = base_hours * float(project_settings.complexity_pct)
    unit_testing_adj  = base_hours * float(project_settings.unit_testing_pct)
    rework_adj        = base_hours * float(project_settings.rework_pct)

    total_dev  = base_hours + complexity_adj + unit_testing_adj + rework_adj
    total_qa   = total_dev * QA_TOTAL_RATIO
    total_feat = total_dev + total_qa

    return {
        "base_hours":       round(base_hours, 4),
        "total_dev_hours":  round(total_dev, 4),
        "total_qa_hours":   round(total_qa, 4),
        "total_hours":      round(total_feat, 4),
    }


# ---------------------------------------------------------------------------
# Full project calculation
# ---------------------------------------------------------------------------
def calc_project(project) -> dict:
    """
    Compute the full project summary given an EstimationProject with loaded
    features and resources.

    Returns a plain dict with all intermediate and final numbers.
    """
    # --- Step 1: per-feature hours ---
    feature_results: list[dict] = []
    for feat in project.features:
        res = calc_feature(feat, project)
        feature_results.append(res)

    sum_dev_hours = sum(r["total_dev_hours"] for r in feature_results)
    sum_qa_hours  = sum(r["total_qa_hours"]  for r in feature_results)

    # --- Step 2: project-level overheads (applied on sum_dev_hours) ---
    pm_hours           = sum_dev_hours * float(project.pm_pct)
    design_arch_hours  = sum_dev_hours * float(project.design_arch_pct)
    spec_uiux_hours    = sum_dev_hours * float(project.spec_uiux_pct)
    dev_buffer_hours   = sum_dev_hours * float(project.dev_buffer_pct)

    grand_total_dev = (
        sum_dev_hours
        + pm_hours
        + design_arch_hours
        + spec_uiux_hours
        + dev_buffer_hours
    )
    grand_total = grand_total_dev + sum_qa_hours

    # --- Step 3: resource allocation ---
    resource_rows: list[dict] = []
    # We use the project's stored resources if available, else DEFAULT_ROLES
    source_resources = project.resources if project.resources else []

    for res in source_resources:
        is_active = getattr(res, 'is_active', True)
        if not is_active:
            effort_hours = 0.0
            total_cost   = 0.0
        else:
            effort_hours = grand_total_dev * float(res.effort_pct)
            total_cost   = effort_hours * float(res.hourly_rate)
        resource_rows.append({
            "id":           res.id,
            "role":         res.role,
            "responsibility": res.responsibility,
            "count":        res.count,
            "effort_pct":   res.effort_pct,
            "effort_hours": round(effort_hours, 2),
            "hourly_rate":  res.hourly_rate,
            "total_cost":   round(total_cost, 2),
        })

    internal_cost  = sum(r["total_cost"] for r in resource_rows)
    margin_amount  = internal_cost * float(project.margin_pct)
    total_project_cost = internal_cost + margin_amount + float(project.infra_cost)

    return {
        "feature_results":    feature_results,
        "total_dev_hours":    round(sum_dev_hours, 2),
        "total_qa_hours":     round(sum_qa_hours, 2),
        "pm_hours":           round(pm_hours, 2),
        "design_arch_hours":  round(design_arch_hours, 2),
        "spec_uiux_hours":    round(spec_uiux_hours, 2),
        "dev_buffer_hours":   round(dev_buffer_hours, 2),
        "grand_total_dev":    round(grand_total_dev, 2),
        "grand_total_hours":  round(grand_total, 2),
        "resource_rows":      resource_rows,
        "internal_cost":      round(internal_cost, 2),
        "margin_amount":      round(margin_amount, 2),
        "total_project_cost": round(total_project_cost, 2),
    }


# ---------------------------------------------------------------------------
# Mutate ORM objects in-place
# ---------------------------------------------------------------------------
def recalculate_project(project) -> None:
    """
    Mutate the EstimationProject (and its child features / resources) with
    freshly computed values.  Call db.commit() after this function.
    """
    summary = calc_project(project)

    # Update each feature
    for feat, res in zip(project.features, summary["feature_results"]):
        feat.base_hours      = res["base_hours"]
        feat.total_dev_hours = res["total_dev_hours"]
        feat.total_qa_hours  = res["total_qa_hours"]
        feat.total_hours     = res["total_hours"]

    # Update each resource
    for res_dict in summary["resource_rows"]:
        for res_orm in project.resources:
            if res_orm.id == res_dict["id"]:
                res_orm.effort_hours = res_dict["effort_hours"]
                res_orm.total_cost   = res_dict["total_cost"]

    # Update project summary
    project.total_dev_hours    = summary["total_dev_hours"]
    project.total_qa_hours     = summary["total_qa_hours"]
    project.grand_total_hours  = summary["grand_total_hours"]
    project.internal_cost      = summary["internal_cost"]
    project.margin_amount      = summary["margin_amount"]
    project.total_project_cost = summary["total_project_cost"]

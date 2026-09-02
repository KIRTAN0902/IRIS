"""Deterministic priority engine tests (spec §40).

Key invariant: strategic weighting (STARTUP=1.5) can NEVER outrank an
imminent deadline -- a task due within 2h gets +40 while strategy caps ~15.
"""

from __future__ import annotations

import pytest

from app.models.enums import TaskStatus
from app.services.priority_engine import rank_tasks, score_task
from tests.conftest import days_from_now, hours_from_now, make_goal, make_task


def test_startup_beats_college_when_both_relaxed(db, user_id):
    startup = make_task(db, user_id, title="Startup work", area="STARTUP")
    college = make_task(db, user_id, title="College reading", area="COLLEGE")

    ranked = rank_tasks(db, [startup, college])
    assert ranked[0][0].id == startup.id
    # The gap comes from the bounded strategic component.
    s_breakdown = ranked[0][1]
    c_breakdown = ranked[1][1]
    assert s_breakdown.strategic_score > c_breakdown.strategic_score


def test_urgent_college_deadline_overrides_startup_strategy(db, user_id):
    startup = make_task(db, user_id, title="Startup outreach", area="STARTUP")
    college = make_task(
        db,
        user_id,
        title="Assignment due in 2 hours",
        area="COLLEGE",
        deadline=hours_from_now(1.5),
        priority="CRITICAL",
    )

    ranked = rank_tasks(db, [startup, college])
    assert ranked[0][0].id == college.id
    bd = ranked[0][1]
    assert bd.deadline_score >= 40  # imminent-deadline tier
    # And even the best possible strategic score could not close that gap.
    assert bd.deadline_score > score_task(db, startup).strategic_score


def test_startup_behind_on_weekly_target_gets_goal_boost(db, user_id):
    goal = make_goal(
        db,
        user_id,
        name="Contact 100 prospects",
        target_value=100,
        current_value=10,
        unit="prospects",
        status="BEHIND",
    )
    behind = make_task(db, user_id, title="Contact 20 prospects", goal_id=goal.id)
    plain = make_task(db, user_id, title="Generic startup task")

    b_behind = score_task(db, behind)
    b_plain = score_task(db, plain)
    assert b_behind.goal_alignment_score >= 8.0
    assert b_behind.total > b_plain.total


def test_overdue_task_ranks_first_and_gets_penalty_component(db, user_id):
    overdue = make_task(db, user_id, title="Overdue report", deadline=hours_from_now(-5))
    fresh = make_task(db, user_id, title="Nice-to-have", deadline=days_from_now(10))
    no_deadline = make_task(db, user_id, title="Someday")

    ranked = rank_tasks(db, [fresh, no_deadline, overdue])
    assert ranked[0][0].id == overdue.id
    bd = ranked[0][1]
    assert bd.overdue_penalty == pytest.approx(25.0)
    assert "Overdue" in bd.notes


def test_task_that_cannot_fit_window_gets_misfit_penalty(db, user_id):
    big = make_task(db, user_id, title="Deep work 3h", estimated_duration=180)
    small = make_task(db, user_id, title="Quick reply", estimated_duration=20)

    b_big = score_task(db, big, available_minutes=60)
    b_small = score_task(db, small, available_minutes=60)
    assert b_big.effort_fit_score < 0
    assert b_small.effort_fit_score > 0


def test_in_progress_boost_applies(db, user_id):
    wip = make_task(db, user_id, status=TaskStatus.IN_PROGRESS.value)
    todo = make_task(db, user_id)
    assert score_task(db, wip).in_progress_boost == pytest.approx(3.0)
    assert score_task(db, todo).in_progress_boost == pytest.approx(0.0)


def test_total_is_clamped_to_100(db, user_id):
    monster = make_task(
        db,
        user_id,
        title="Everything at once",
        priority="CRITICAL",
        deadline=hours_from_now(1),
        status=TaskStatus.IN_PROGRESS.value,
    )
    assert score_task(db, monster, available_minutes=600).total <= 100.0

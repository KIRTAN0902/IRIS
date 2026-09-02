"""Seed IRIS with realistic real-world routine, MARKETORY context, and development data.

Usage (from backend/):
    python scripts/seed.py            # seed if empty
    python scripts/seed.py --force    # wipe and reseed

Distinguishes:
- User facts, operating preferences, and routine commitments
- MARKETORY & NEXUS vertical AI context & 90-day measurable goals
- Recurring schedule records with explicit FIXED, FLEXIBLE, WORK, PERSONAL, SLEEP types
- College (B.Tech AI & ML 4th sem) and Internship context
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, SessionLocal  # noqa: E402
from app.utils.datetime import utcnow  # noqa: E402


def _days_ago(days: float):
    return utcnow() - timedelta(days=days)


def _in_days(days: float):
    return utcnow() + timedelta(days=days)


def wipe(db) -> None:
    """Delete all data rows but keep the default user account."""
    from app.models.user import User

    for table in reversed(Base.metadata.sorted_tables):
        if table.name == User.__tablename__:
            continue
        db.execute(table.delete())
    db.commit()


def seed() -> None:
    from alembic.config import Config

    from alembic import command
    from app.core.security import get_current_user
    from app.models.calendar_event import CalendarEvent
    from app.models.enums import LifeArea, ScheduleBlockType
    from app.models.experiment import Experiment
    from app.models.focus_session import FocusSession
    from app.models.goal import Goal
    from app.models.lead import Lead
    from app.models.outreach import OutreachActivity
    from app.models.project import Project
    from app.models.recurring_schedule import RecurringSchedule
    from app.models.startup import Startup
    from app.models.task import Task
    from app.models.time_block import TimeBlock

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")

    db = SessionLocal()
    try:
        force = "--force" in sys.argv
        if force:
            wipe(db)
        # Creates the default user on first use; keeps it across reseeds.
        user = get_current_user(db)
        user.name = "Kirtan"
        user.timezone = "Asia/Kolkata"
        all_days = "Mon,Tue,Wed,Thu,Fri,Sat,Sun"
        work_days = "Mon,Tue,Wed,Thu,Fri"

        all_days_list = all_days.split(",")
        work_days_list = work_days.split(",")

        user.facts = {
            "wake": "06:00",
            "sleep": "23:00",
            "routine": [
                {"name": "Yoga", "start": "06:00", "end": "07:30", "days": all_days_list},
                {"name": "Bath", "start": "07:30", "end": "08:00", "days": all_days_list},
                {"name": "Puja", "start": "08:00", "end": "08:30", "days": all_days_list},
                {"name": "Breakfast", "start": "08:30", "end": "09:00", "days": all_days_list},
                {"name": "Internship", "start": "11:00", "end": "20:00", "days": work_days_list},
                {"name": "Dinner", "start": "20:00", "end": "21:00", "days": all_days_list},
            ],
            "college": {
                "degree": "B.Tech AI & ML",
                "semester": "4th semester",
                "subjects": [
                    "Agentic AI",
                    "Compiler Design",
                    "Software Project Management",
                    "DSA (MOOC)",
                ],
                "attendance_policy": "Usually attends only when required",
                "pending_assignments_count": 0,
            },
            "internship": {
                "role": "AI Intern",
                "schedule": "Monday–Friday, 11:00 AM – 8:00 PM",
                "fixed_hours_start": "11:00",
                "fixed_hours_end": "20:00",
            },
            "startup": {
                "name": "MARKETORY",
                "product": "NEXUS",
                "company_type": "AI systems company",
                "product_type": "Vertical AI system for digital marketing agencies",
                "purpose": (
                    "Performance intelligence and investigation system for digital "
                    "marketing agencies."
                ),
                "problem": (
                    "Marketing teams have abundant fragmented data and dashboards, "
                    "but performance changes still require manual investigation."
                ),
                "target_audience": "Digital marketing and performance marketing agency founders",
                "stage": "Pre-revenue / early validation / prototype",
                "paying_customers": 0,
                "current_bottleneck": "Customer validation + distribution",
                "current_objective": "Founder acquisition + outreach",
                "strategy": "Founder-led outbound + LinkedIn content",
                "initial_geographic_focus": "Ahmedabad",
                "validation_approach": "Talk → Observe → Test → Iterate → Validate",
                "ninety_day_objectives": [
                    "30–50 meaningful conversations",
                    "10+ deep discovery conversations",
                    "5+ agencies testing NEXUS",
                    "2–5 potential design partners",
                    "First paying customers",
                    "Strong evidence that core problem is worth pursuing",
                    "Clearer product direction based on real usage",
                ],
            },
        }
        user.preferences = {
            "primary_long_term_goal": "STARTUP",
            "startup_time_allocation": "as_much_as_reasonably_possible",
            "optimization_objective": "meaningful_progress_over_busywork",
            "schedule_sustainability": "sustainable_without_artificial_filler",
            "hard_constraints_must_win": True,
        }
        db.commit()
        if not force and db.query(Task).filter(Task.user_id == user.id).count():
            print("Data already exists; use --force to wipe and reseed. Skipping.")
            return
        print(f"Seeding REAL-WORLD and DEVELOPMENT data for {user.email} ...")

        # --- Recurring Schedules (User Routine) -------------------------------
        recurring_blocks = [
            RecurringSchedule(
                user_id=user.id,
                name="Yoga",
                type=ScheduleBlockType.PERSONAL.value,
                days_of_week=all_days,
                start_time="06:00",
                end_time="07:30",
                is_hard_constraint=True,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Bath",
                type=ScheduleBlockType.PERSONAL.value,
                days_of_week=all_days,
                start_time="07:30",
                end_time="08:00",
                is_hard_constraint=True,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Puja",
                type=ScheduleBlockType.PERSONAL.value,
                days_of_week=all_days,
                start_time="08:00",
                end_time="08:30",
                is_hard_constraint=True,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Breakfast",
                type=ScheduleBlockType.PERSONAL.value,
                days_of_week=all_days,
                start_time="08:30",
                end_time="09:00",
                is_hard_constraint=True,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Morning Flexible Window",
                type=ScheduleBlockType.FLEXIBLE.value,
                days_of_week=all_days,
                start_time="09:00",
                end_time="10:30",
                is_hard_constraint=False,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Buffer",
                type=ScheduleBlockType.BUFFER.value,
                days_of_week=all_days,
                start_time="10:30",
                end_time="11:00",
                is_hard_constraint=False,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Internship",
                type=ScheduleBlockType.WORK.value,
                days_of_week=work_days,
                start_time="11:00",
                end_time="20:00",
                is_hard_constraint=True,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Dinner",
                type=ScheduleBlockType.PERSONAL.value,
                days_of_week=all_days,
                start_time="20:00",
                end_time="21:00",
                is_hard_constraint=True,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Night Flexible Window",
                type=ScheduleBlockType.FLEXIBLE.value,
                days_of_week=all_days,
                start_time="21:00",
                end_time="23:00",
                is_hard_constraint=False,
            ),
            RecurringSchedule(
                user_id=user.id,
                name="Sleep",
                type=ScheduleBlockType.SLEEP.value,
                days_of_week=all_days,
                start_time="23:00",
                end_time="06:00",
                is_hard_constraint=True,
            ),
        ]
        db.add_all(recurring_blocks)
        db.flush()

        # --- Startup ---------------------------------------------------------
        marketory = Startup(
            user_id=user.id,
            name="MARKETORY",
            description=(
                "AI systems company building vertical AI performance intelligence & "
                "investigation system (NEXUS) for digital marketing agencies."
            ),
            current_objective="Founder acquisition + outreach (Customer validation bottleneck)",
            status="BUILDING",
        )
        db.add(marketory)
        db.flush()

        # --- Goals (Hierarchy & 90-Day Objectives) ----------------------------
        g_root = Goal(
            user_id=user.id,
            name="Build MARKETORY into a leading AI systems company",
            area=LifeArea.STARTUP.value,
            description="Primary long-term strategic goal.",
        )
        db.add(g_root)
        db.flush()

        g_conversations = Goal(
            user_id=user.id,
            name="30–50 meaningful conversations",
            area=LifeArea.STARTUP.value,
            parent_goal_id=g_root.id,
            target_value=40,
            current_value=0,
            unit="conversations",
            deadline=_in_days(90),
            status="ACTIVE",
        )
        g_discovery = Goal(
            user_id=user.id,
            name="10+ deep problem-discovery conversations",
            area=LifeArea.STARTUP.value,
            parent_goal_id=g_root.id,
            target_value=10,
            current_value=0,
            unit="discovery_calls",
            deadline=_in_days(90),
            status="ACTIVE",
        )
        g_testing = Goal(
            user_id=user.id,
            name="5+ agencies testing NEXUS",
            area=LifeArea.STARTUP.value,
            parent_goal_id=g_root.id,
            target_value=5,
            current_value=0,
            unit="agency_pilots",
            deadline=_in_days(90),
            status="ACTIVE",
        )
        g_partners = Goal(
            user_id=user.id,
            name="2–5 potential design partners",
            area=LifeArea.STARTUP.value,
            parent_goal_id=g_root.id,
            target_value=3,
            current_value=0,
            unit="design_partners",
            deadline=_in_days(90),
            status="ACTIVE",
        )
        g_paying = Goal(
            user_id=user.id,
            name="First paying customers",
            area=LifeArea.STARTUP.value,
            parent_goal_id=g_root.id,
            target_value=1,
            current_value=0,
            unit="paying_customers",
            deadline=_in_days(90),
            status="ACTIVE",
        )
        g_college = Goal(
            user_id=user.id,
            name="B.Tech AI & ML Semester 4 Excellence",
            area=LifeArea.COLLEGE.value,
            description="Agentic AI, Compiler Design, SPM, DSA",
            status="ACTIVE",
        )
        db.add_all(
            [
                g_conversations,
                g_discovery,
                g_testing,
                g_partners,
                g_paying,
                g_college,
            ]
        )
        db.flush()

        # --- Projects ----------------------------------------------------------
        nexus_project = Project(
            user_id=user.id,
            name="NEXUS Founder Acquisition & Validation",
            description=(
                "Get NEXUS in front of real agencies and validate whether the problem is "
                "painful and frequent enough that agencies will change workflow and pay."
            ),
            area=LifeArea.STARTUP.value,
            status="ACTIVE",
            deadline=_in_days(90),
        )
        spm_project = Project(
            user_id=user.id,
            name="SPM Practical Submission",
            description="Software Project Management practical file.",
            area=LifeArea.COLLEGE.value,
            status="ACTIVE",
            deadline=_in_days(3),
        )
        db.add_all([nexus_project, spm_project])
        db.flush()

        # --- Tasks ---------------------------------------------------------------
        nexus_tasks = [
            Task(
                user_id=user.id,
                title="Define target agency founder profile",
                description="Profile ICP for digital marketing and performance agency founders.",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_conversations.id,
                priority="HIGH",
                estimated_duration=60,
                energy_level="DEEP_WORK",
            ),
            Task(
                user_id=user.id,
                title="Build initial agency prospect list",
                description="Identify 30-50 agency founders/operators in Ahmedabad/India.",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_conversations.id,
                priority="HIGH",
                estimated_duration=90,
                deadline=_in_days(2),
                energy_level="NORMAL",
            ),
            Task(
                user_id=user.id,
                title="Prepare founder outreach message",
                description="Draft personalized cold outbound and LinkedIn messages.",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_conversations.id,
                priority="HIGH",
                estimated_duration=60,
            ),
            Task(
                user_id=user.id,
                title="Start founder-led outreach",
                description="Contact initial batch of 15 agency founders.",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_conversations.id,
                priority="HIGH",
                estimated_duration=90,
                deadline=_in_days(1),
            ),
            Task(
                user_id=user.id,
                title="Prepare discovery conversation questions",
                description=(
                    "Structure problem discovery interview questions around reporting pains."
                ),
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_discovery.id,
                priority="MEDIUM",
                estimated_duration=60,
            ),
            Task(
                user_id=user.id,
                title="Conduct problem-discovery conversations",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_discovery.id,
                priority="HIGH",
                estimated_duration=60,
            ),
            Task(
                user_id=user.id,
                title="Get NEXUS in front of agencies",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_testing.id,
                priority="MEDIUM",
                estimated_duration=90,
            ),
            Task(
                user_id=user.id,
                title="Collect feedback from agency operators",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_testing.id,
                priority="MEDIUM",
                estimated_duration=45,
            ),
            Task(
                user_id=user.id,
                title="Follow up with interested agencies",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_partners.id,
                priority="MEDIUM",
                estimated_duration=45,
            ),
            Task(
                user_id=user.id,
                title="Track agencies testing NEXUS",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_testing.id,
                priority="LOW",
                estimated_duration=30,
            ),
            Task(
                user_id=user.id,
                title="Document recurring pain points",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_discovery.id,
                priority="MEDIUM",
                estimated_duration=45,
            ),
            Task(
                user_id=user.id,
                title="Iterate NEXUS based on evidence",
                area=LifeArea.STARTUP.value,
                project_id=nexus_project.id,
                goal_id=g_testing.id,
                priority="MEDIUM",
                estimated_duration=90,
            ),
        ]

        college_tasks = [
            Task(
                user_id=user.id,
                title="SPM Practical 1 write-up",
                description="Software Project Management practical report.",
                area=LifeArea.COLLEGE.value,
                project_id=spm_project.id,
                priority="HIGH",
                estimated_duration=90,
                deadline=_in_days(0.6),
                energy_level="DEEP_WORK",
                goal_id=g_college.id,
            ),
            Task(
                user_id=user.id,
                title="SPM Practical 2 write-up",
                area=LifeArea.COLLEGE.value,
                project_id=spm_project.id,
                priority="HIGH",
                estimated_duration=90,
                deadline=_in_days(1.2),
                goal_id=g_college.id,
            ),
        ]

        internship_tasks = [
            Task(
                user_id=user.id,
                title="Research caching strategies for dashboard API",
                area=LifeArea.INTERNSHIP.value,
                priority="MEDIUM",
                estimated_duration=60,
                deadline=_in_days(1),
                energy_level="DEEP_WORK",
            ),
        ]

        all_tasks = nexus_tasks + college_tasks + internship_tasks
        db.add_all(all_tasks)
        db.flush()

        # One overdue task for priority engine validation
        overdue = Task(
            user_id=user.id,
            title="Send internship timesheet",
            area=LifeArea.INTERNSHIP.value,
            priority="HIGH",
            estimated_duration=15,
            deadline=_days_ago(0.4),
        )
        db.add(overdue)

        # Completed tasks for analytics
        done1 = Task(
            user_id=user.id,
            title="Draft initial NEXUS architecture spec",
            area=LifeArea.STARTUP.value,
            priority="MEDIUM",
            status="COMPLETED",
            estimated_duration=120,
            actual_duration=140,
            goal_id=g_root.id,
        )
        done2 = Task(
            user_id=user.id,
            title="Compiler Design Lab quiz 1",
            area=LifeArea.COLLEGE.value,
            priority="MEDIUM",
            status="COMPLETED",
            estimated_duration=45,
            actual_duration=35,
            goal_id=g_college.id,
        )
        db.add_all([done1, done2])
        db.flush()
        done1.completed_at = _days_ago(1.2)
        done2.completed_at = _days_ago(0.8)

        # --- Calendar events ---------------------------------------------------
        tomorrow9 = (_in_days(1)).replace(hour=9, minute=0, second=0, microsecond=0)
        db.add_all(
            [
                CalendarEvent(
                    user_id=user.id,
                    title="Internship standup",
                    start_time=tomorrow9,
                    end_time=tomorrow9 + timedelta(minutes=30),
                    source="INTERNAL",
                ),
            ]
        )

        # --- Time blocks -------------------------------------------------------
        block_start = utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        db.add(
            TimeBlock(
                user_id=user.id,
                task_id=nexus_tasks[0].id,
                start_time=block_start,
                end_time=block_start + timedelta(minutes=60),
                type="FOCUS",
                notes="DEV SEED BLOCK",
            )
        )

        # --- Focus sessions ------------------------------------------------------
        db.add_all(
            [
                FocusSession(
                    user_id=user.id,
                    task_id=done1.id,
                    started_at=_days_ago(1.3),
                    ended_at=_days_ago(1.3) + timedelta(minutes=140),
                    planned_duration=120,
                    actual_duration=140,
                    status="COMPLETED",
                ),
                FocusSession(
                    user_id=user.id,
                    task_id=done2.id,
                    started_at=_days_ago(0.9),
                    ended_at=_days_ago(0.9) + timedelta(minutes=35),
                    planned_duration=45,
                    actual_duration=35,
                    status="COMPLETED",
                ),
            ]
        )

        # --- Leads & Outreach (Sample startup CRM data) -----------------------
        lead_rows = [
            ("Aarav Mehta", "GrowthPulse Media", "Founder & CEO", "aarav@gp.agency", "LEAD"),
            ("Priya Nair", "ScalePeak Digital", "MD", "priya@scalepeak.in", "CONTACTED"),
            ("Rohan Gupta", "AdSphere Media", "Founder", "rohan@adsphere.co", "REPLIED"),
            ("Ishita Shah", "MetricWise Agency", "Lead", "ishita@mw.io", "INTERESTED"),
        ]
        leads: dict[str, Lead] = {}
        for i, (name, company, role, email, status) in enumerate(lead_rows):
            lead = Lead(
                startup_id=marketory.id,
                name=name,
                company=company,
                role=role,
                email=email,
                website=f"https://{company.lower().replace(' ', '')}.com",
                source="LINKEDIN" if i % 2 == 0 else "COLD_EMAIL",
                status=status,
                notes="AGENCY FOUNDER ICP",
                last_contacted=_days_ago(i + 1) if status != "LEAD" else None,
                next_follow_up=_in_days(2 + i) if status in ("REPLIED", "INTERESTED") else None,
            )
            db.add(lead)
            leads[name] = lead
        db.flush()

        history = [
            ("Priya Nair", "EMAIL", "SENT", 3, "Intro message on NEXUS analytics."),
            ("Rohan Gupta", "LINKEDIN", "REPLIED", 2, "Asked for a 15-min discovery call."),
            ("Ishita Shah", "LINKEDIN", "REPLIED", 1, "Interested in automated audit features."),
        ]
        for name, otype, res, days_back, note in history:
            db.add(
                OutreachActivity(
                    startup_id=marketory.id,
                    lead_id=leads[name].id,
                    type=otype,
                    result=res,
                    notes=note,
                    timestamp=_days_ago(days_back),
                )
            )

        db.add(
            Experiment(
                startup_id=marketory.id,
                name="Founder LinkedIn Outbound v1",
                hypothesis=(
                    "Direct problem-focused messaging achieves >20% reply rate "
                    "from agency founders."
                ),
                status="RUNNING",
                started_at=_days_ago(7),
            )
        )

        db.commit()
        print("Seed complete.")
        print(
            f"  users=1 startups=1 goals={db.query(Goal).count()} "
            f"projects={db.query(Project).count()} tasks={db.query(Task).count()}"
        )
        print(
            f"  recurring_schedules={db.query(RecurringSchedule).count()} "
            f"leads={db.query(Lead).count()} outreach={db.query(OutreachActivity).count()}"
        )
        print("NOTE: Seed executed successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

"""
Create (or reset) demo accounts for trying the app.

    python manage.py seed_demo_accounts
    python manage.py seed_demo_accounts --password "SomethingElse1"
    python manage.py seed_demo_accounts --delete       # remove them again

In Docker:
    docker compose exec web python manage.py seed_demo_accounts

Accounts (all share the same password, default DEMO_PASSWORD below):

    demo.student.new@studypulse.test  student, verified, nothing filled in -> goes through profile setup + assessment
    demo.student@studypulse.test      student, profile complete (+ evaluated assessment if a template exists) -> lands on home
    demo.teacher@studypulse.test      teacher, with Teacher record and TeacherProfile -> lands on teacher dashboard

Running it again resets the password and the profile fields; it never sends email.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import UserRole

DEMO_PASSWORD = "DemoPass123!"
NEW_STUDENT = "demo.student.new@studypulse.test"
STUDENT = "demo.student@studypulse.test"
TEACHER = "demo.teacher@studypulse.test"
ALL_EMAILS = [NEW_STUDENT, STUDENT, TEACHER]


class Command(BaseCommand):
    help = "Create or reset demo student and teacher accounts."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEMO_PASSWORD, help="Password for all demo accounts.")
        parser.add_argument("--delete", action="store_true", help="Delete the demo accounts instead.")

    def handle(self, *args, password, delete, **options):
        User = get_user_model()
        if delete:
            from teachers.models import Teacher

            Teacher.objects.filter(email__in=ALL_EMAILS).delete()
            count, _ = User.objects.filter(email__in=ALL_EMAILS).delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted demo accounts ({count} rows incl. related)."))
            return

        if not settings.DEBUG:
            self.stdout.write(self.style.WARNING(
                "DEBUG is off: these accounts have a known password. Remove them with --delete when done."
            ))

        with transaction.atomic():
            self._new_student(User, password)
            assessment = self._student(User, password)
            self._teacher(User, password)

        self.stdout.write(self.style.SUCCESS("Demo accounts ready (password set by --password, default in this command's source):"))
        self.stdout.write(f"  student (new)      {NEW_STUDENT}")
        self.stdout.write(f"  student (ready)    {STUDENT}" + ("" if assessment else "  (no active assessment template, so assessment is still pending)"))
        self.stdout.write(f"  teacher            {TEACHER}")

    # -- accounts -----------------------------------------------------------

    def _user(self, User, email, full_name, role, password, **flags):
        user, _ = User.objects.get_or_create(email=email, defaults={"full_name": full_name, "role": role})
        user.full_name = full_name
        user.role = role
        user.is_active = True
        user.is_email_verified = True
        for key, value in flags.items():
            setattr(user, key, value)
        user.set_password(password)
        user.save()
        return user

    def _new_student(self, User, password):
        from students.models import StudentAssessmentAttempt, StudentProfile

        user = self._user(User, NEW_STUDENT, "Demo New Student", UserRole.STUDENT, password,
                          is_profile_completed=False, is_first_assement_completed=False)
        StudentProfile.objects.filter(student=user).delete()
        StudentAssessmentAttempt.objects.filter(student=user).delete()

    def _student(self, User, password):
        from students.models import (
            AssessmentAttemptStatus,
            AssessmentTemplate,
            StudentAssessmentAttempt,
            StudentProfile,
        )

        user = self._user(User, STUDENT, "Demo Student", UserRole.STUDENT, password, is_profile_completed=True)
        StudentProfile.objects.update_or_create(
            student=user,
            defaults={
                "student_name": "Demo Student",
                "phone_number": "+994500000001",
                "age": 21,
                "gender": "female",
                "last_achieved_degree": "High school",
                "preferred_study_time": ["morning"],
                "preferred_study_mode": ["online"],
                "preferred_study_language": ["English"],
            },
        )

        template = AssessmentTemplate.objects.filter(is_active=True).order_by("id").first()
        if template is None:
            user.is_first_assement_completed = False
            user.save(update_fields=["is_first_assement_completed", "updated_at"])
            return False

        now = timezone.now()
        StudentAssessmentAttempt.objects.filter(student=user).delete()
        StudentAssessmentAttempt.objects.create(
            student=user, template=template, status=AssessmentAttemptStatus.EVALUATED,
            submitted_at=now, evaluated_at=now, total_score=0, is_passed=True,
        )
        user.is_first_assement_completed = True
        user.save(update_fields=["is_first_assement_completed", "updated_at"])
        return True

    def _teacher(self, User, password):
        from teachers.models import Teacher, TeacherLevel, TeacherProfile

        # Create the user first: the Teacher post_save signal then skips making
        # its own account and sending a welcome email with a random password.
        user = self._user(User, TEACHER, "Demo Teacher", UserRole.TEACHER, password)
        teacher, _ = Teacher.objects.get_or_create(email=TEACHER, defaults={"name": "Demo Teacher"})
        teacher.capability_level.set(TeacherLevel.objects.all())
        TeacherProfile.objects.update_or_create(
            user=user,
            defaults={
                "name": "Demo Teacher",
                "phone_number": "+994500000002",
                "age": 30,
                "gender": "male",
                "qualification": "MA English Language Teaching",
                "experience": "5",
                "teaching_medium": "English",
                "courses_classes_taught": "General English",
            },
        )

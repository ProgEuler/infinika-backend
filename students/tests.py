from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from accounts.models import UserRole
from students.models import InterestSummary, Intterest

User = get_user_model()


class IntterestModelTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="student@example.com",
            full_name="Student User",
            password="StrongPass123",
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
        )

    def test_interest_summary_percentage_is_based_on_student_count(self):
        other_student = User.objects.create_user(
            email="student2@example.com",
            full_name="Student User Two",
            password="StrongPass123",
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
        )
        third_student = User.objects.create_user(
            email="student3@example.com",
            full_name="Student User Three",
            password="StrongPass123",
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
        )

        Intterest.objects.create(student=self.student, interest_name="IELTS")
        Intterest.objects.create(student=other_student, interest_name="IELTS")
        Intterest.objects.create(student=third_student, interest_name="Professionals")

        ielts_summary = InterestSummary.objects.get(interest_name="IELTS")
        professional_summary = InterestSummary.objects.get(interest_name="Professionals")

        self.assertEqual(ielts_summary.student_count, 2)
        self.assertEqual(ielts_summary.percentage, Decimal("66.67"))
        self.assertEqual(professional_summary.student_count, 1)
        self.assertEqual(professional_summary.percentage, Decimal("33.33"))

    def test_same_interest_name_can_exist_for_different_students(self):
        other_student = User.objects.create_user(
            email="student2@example.com",
            full_name="Student User Two",
            password="StrongPass123",
            role=UserRole.STUDENT,
            is_active=True,
            is_email_verified=True,
        )

        Intterest.objects.create(student=self.student, interest_name="IELTS")
        Intterest.objects.create(student=other_student, interest_name="IELTS")

        self.assertEqual(Intterest.objects.filter(interest_name="IELTS").count(), 2)


class DashboardUpcomingSessionTests(APITestCase):
    def test_upcoming_session_includes_booking_id_for_cancel(self):
        from datetime import time, timedelta

        from django.utils import timezone

        from teachers.models import StudentBooking, TeacherProfile, TeacherSlot

        student = User.objects.create_user(email="s@example.com", full_name="S", password="StrongPass123")
        teacher_user = User.objects.create_user(
            email="t@example.com", full_name="T", password="StrongPass123", role=UserRole.TEACHER
        )
        profile = TeacherProfile.objects.create(user=teacher_user, name="T", phone_number="1", age=30)
        slot = TeacherSlot.objects.create(
            teacher=profile,
            date=timezone.localdate() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            mode="online",
        )
        booking = StudentBooking.objects.create(student=student, slot=slot)

        self.client.force_authenticate(student)
        r = self.client.get("/api/students/dashboard/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["data"]["upcoming_session"]["id"], booking.id)

        r = self.client.post(f"/api/students/cancel-booking/{booking.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(StudentBooking.objects.filter(pk=booking.pk).exists())


class ProfileSetupPayloadTests(APITestCase):
    def test_get_returns_saved_basic_details(self):
        student = User.objects.create_user(email="p@example.com", full_name="Aysel M", password="StrongPass123")
        self.client.force_authenticate(student)
        r = self.client.patch(
            "/api/students/profile-setup/",
            {"phone": "+994501112233", "age": 21, "gender": "female"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/students/profile-setup/").data["data"]
        self.assertEqual(data["name"], "Aysel M")
        self.assertEqual(data["phone"], "+994501112233")
        self.assertEqual(data["age"], 21)
        self.assertEqual(data["gender"], "female")


class ProfileSetupValidationTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="v@example.com", full_name="Kamran A", password="StrongPass123")
        self.client.force_authenticate(self.student)

    def _post(self, payload):
        return self.client.post("/api/students/profile-setup/", payload, format="json")

    def test_rejects_bad_phone_age_and_gender(self):
        r = self._post({"phone": "12ab", "age": 3, "gender": "robot", "parents_phone_number": "123"})
        self.assertEqual(r.status_code, 400)
        for field in ("phone", "age", "gender", "parents_phone_number"):
            self.assertIn(field, r.data["errors"])

    def test_normalizes_phone_and_gender(self):
        r = self._post({"phone": "+994 (50) 111-22-33", "age": 30, "gender": "Female"})
        self.assertIn(r.status_code, (200, 201), r.data)
        data = self.client.get("/api/students/profile-setup/").data["data"]
        self.assertEqual(data["phone"], "+994501112233")
        self.assertEqual(data["gender"], "female")

    def test_blank_name_and_zero_age_from_old_builds_are_ignored(self):
        r = self._post({"name": "", "age": 0, "preferred_study_time": ["Morning"]})
        self.assertIn(r.status_code, (200, 201), r.data)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, "Kamran A")
        self.assertIsNone(self.client.get("/api/students/profile-setup/").data["data"]["age"])


class DashboardQuizScoreTests(APITestCase):
    def setUp(self):
        from accounts.models import User

        self.user = User.objects.create_user("quiz@example.com", "Quiz Student", "StrongPass123")
        self.client.force_authenticate(self.user)

    def test_no_attempts_gives_null_quiz_score(self):
        res = self.client.get("/api/students/dashboard/")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data["data"]["quiz_score"])

    def test_quiz_score_average_change_and_history(self):
        from datetime import timedelta

        from django.utils import timezone

        from students.models import (
            AssessmentAttemptStatus,
            AssessmentQuestion,
            AssessmentSection,
            AssessmentTemplate,
            StudentAssessmentAttempt,
        )

        template = AssessmentTemplate.objects.create(name="Elementary")
        section = AssessmentSection.objects.create(template=template, title="Grammar", skill=AssessmentSection._meta.get_field("skill").choices[0][0])
        for i in range(10):
            AssessmentQuestion.objects.create(
                section=section,
                question_type=AssessmentQuestion._meta.get_field("question_type").choices[0][0],
                prompt=f"Q{i}",
                order=i + 1,
                marks=2,
            )  # 20 marks total
        now = timezone.now()
        for days_ago, score in [(10, 10), (3, 16), (1, 18)]:  # 50% last week; 80% and 90% this week
            StudentAssessmentAttempt.objects.create(
                student=self.user,
                template=template,
                status=AssessmentAttemptStatus.EVALUATED,
                evaluated_at=now - timedelta(days=days_ago),
                total_score=score,
            )

        quiz = self.client.get("/api/students/dashboard/").data["data"]["quiz_score"]
        self.assertEqual(quiz, {"score": 85, "change": 35, "history": [50, 80, 90]})

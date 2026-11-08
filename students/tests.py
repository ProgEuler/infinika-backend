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

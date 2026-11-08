import logging
from drf_spectacular.utils import OpenApiResponse, extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from common.responses import error_response, success_response
from accounts.models import UserRole
from teachers.models import TeacherProfile
from teachers.serializers import (
    TeacherSetPasswordSerializer,
    TeacherSetPasswordSuccessResponseSerializer,
    TeacherErrorResponseSerializer,
    TeacherProfileSerializer,
    TeachersLocationSerializer,
    TeacherAvailabilitySerializer,
    AvailableSlotSerializer,
    StudentBookingSerializer,
    SessionListSerializer,
    TeacherBookedSlotSerializer,
    TeacherStudentListSerializer,
    TeacherFeedbackSerializer,
    PendingRequestSerializer,
    CancellationRequestSubmitSerializer,
    SessionNoticeSerializer,
    TeacherDashboardSerializer,
)
from common.utils import send_expo_push_notification
from teachers.models import (
    TeacherAvailability,
    TeacherSlot,
    StudentBooking,
    SlotMode,
    PendingRequest,
    RequestStatus,
    RequestType,
)
from django.db import transaction
from django.db.models import F, Sum, Min
from datetime import datetime, timedelta



logger = logging.getLogger(__name__)

@extend_schema(
    methods=["GET"],
    tags=["Teachers Profile"],
    operation_id="teachers_profile_get",
    responses={200: TeacherProfileSerializer},
    description="Fetch the teacher's profile.",
)
@extend_schema(
    methods=["POST"],
    tags=["Teachers Profile"],
    operation_id="teachers_profile_create",
    request={
        "multipart/form-data": TeacherProfileSerializer,
    },
    responses={
        201: TeacherProfileSerializer,
        400: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Validation error or profile already exists."),
    },
    description="Create a new teacher profile. Supports multipart/form-data for profile_picture.",
)
@extend_schema(
    methods=["PATCH"],
    tags=["Teachers Profile"],
    operation_id="teachers_profile_update",
    request={
        "multipart/form-data": TeacherProfileSerializer,
    },
    responses={
        200: TeacherProfileSerializer,
        400: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Validation error."),
        404: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Profile not found."),
    },
    description="Update an existing teacher profile. Supports multipart/form-data for profile_picture.",
)
@api_view(["GET", "POST", "PATCH"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([IsAuthenticated])
def teacher_profile(request):
    if request.user.role != UserRole.TEACHER:
        return error_response(
            "Only teacher users can access this endpoint.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    try:
        profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        profile = None

    if request.method == "GET":
        if not profile:
            return error_response("Profile not found.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = TeacherProfileSerializer(profile, context={"request": request})
        return success_response(serializer.data, message="Profile fetched successfully.")

    if request.method == "POST":
        if profile:
            return error_response("Profile already exists. Use PATCH to update.", status_code=status.HTTP_400_BAD_REQUEST)
        serializer = TeacherProfileSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save(user=request.user)
            request.user.is_profile_completed = True
            request.user.save(update_fields=["is_profile_completed", "updated_at"])
            return success_response(serializer.data, message="Profile created successfully.", status_code=status.HTTP_201_CREATED)
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    if request.method == "PATCH":
        if not profile:
            return error_response("Profile not found. Use POST to create.", status_code=status.HTTP_404_NOT_FOUND)
        serializer = TeacherProfileSerializer(profile, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            request.user.is_profile_completed = True
            request.user.save(update_fields=["is_profile_completed", "updated_at"])
            return success_response(serializer.data, message="Profile updated successfully.")
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Teachers Authentication"],
    operation_id="teachers_set_password",
    request=TeacherSetPasswordSerializer,
    responses={
        200: TeacherSetPasswordSuccessResponseSerializer,
        400: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Validation error."),
        403: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Only teacher users can access this endpoint."),
    },
    description="Allows a teacher to set a new password. Usually used after the first login with a temporary password.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_set_password(request):
    if request.user.role != UserRole.TEACHER:
        return error_response(
            "Only teacher users can access this endpoint.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    serializer = TeacherSetPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(
            "Validation error",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    user.set_password(serializer.validated_data["new_password"])
    user.save()

    return success_response(
        message="Password updated successfully.",
    )


@extend_schema(
    methods=["POST"],
    tags=["Teachers Location"],
    operation_id="teachers_location_create",
    request=TeachersLocationSerializer,
    responses={
        201: TeachersLocationSerializer,
        400: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Validation error."),
        403: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Only teacher users can access this endpoint."),
        404: OpenApiResponse(response=TeacherErrorResponseSerializer, description="Profile not found."),
    },
    description="Store the teacher's current location (latitude and longitude).",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_location(request):
    if request.user.role != UserRole.TEACHER:
        return error_response(
            "Only teacher users can access this endpoint.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    try:
        profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return error_response("Teacher profile not found.", status_code=status.HTTP_404_NOT_FOUND)

    serializer = TeachersLocationSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(teacher=profile)
        return success_response(serializer.data, message="Location saved successfully.", status_code=status.HTTP_201_CREATED)
    return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    tags=["Teachers Availability"],
    operation_id="teachers_availability_list",
    responses={200: TeacherAvailabilitySerializer(many=True)},
    description="Fetch current teacher's weekly availability.",
)
@extend_schema(
    methods=["POST"],
    tags=["Teachers Availability"],
    operation_id="teachers_availability_create",
    request=TeacherAvailabilitySerializer,
    responses={201: TeacherAvailabilitySerializer},
    description="Teacher sets their weekly availability. Example: Monday 09:00:00 to 10:00:00 ONLINE.",
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def teacher_availability(request):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access availability.", status_code=status.HTTP_403_FORBIDDEN)

    try:
        profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return error_response("Teacher profile not found.", status_code=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        availabilities = TeacherAvailability.objects.filter(
            teacher=profile
        ).exclude(
            withdrawal_requests__status__in=[RequestStatus.PENDING, RequestStatus.APPROVED]
        ).distinct()
        serializer = TeacherAvailabilitySerializer(availabilities, many=True)
        return success_response(serializer.data, message="Availability fetched successfully.")

    if request.method == "POST":
        serializer = TeacherAvailabilitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(teacher=profile)
            return success_response(serializer.data, message="Availability added successfully.", status_code=status.HTTP_201_CREATED)
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    tags=["Student Booking"],
    operation_id="student_available_slots",
    responses={200: AvailableSlotSerializer(many=True)},
    parameters=[
        OpenApiParameter(name="date", description="Date in YYYY-MM-DD format", required=True, type=OpenApiTypes.DATE),
        OpenApiParameter(name="mode", description="Filter by mode: online or offline", required=False, type=OpenApiTypes.STR),
        OpenApiParameter(name="session_id", description="Filter by session ID to get slots for the specific teacher", required=False, type=OpenApiTypes.INT),
    ],
    description="Fetch available slots for students. Query params: date (YYYY-MM-DD), mode (online/offline).",
)
@api_view(["GET"])
def student_available_slots(request):
    date_str = request.query_params.get("date")
    mode = request.query_params.get("mode")

    if not date_str:
        return error_response("Date is required (YYYY-MM-DD).", status_code=status.HTTP_400_BAD_REQUEST)

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return error_response("Invalid date format. Use YYYY-MM-DD.", status_code=status.HTTP_400_BAD_REQUEST)

    day_name = target_date.strftime("%A")  # Monday, Tuesday, etc.

    availabilities = TeacherAvailability.objects.filter(
        day_of_week=day_name
    ).exclude(
        withdrawal_requests__status__in=[RequestStatus.PENDING, RequestStatus.APPROVED]
    ).select_related("teacher").distinct()
    
    session_id = request.query_params.get("session_id")
    if session_id:
        from teachers.models import CourseModuleSession
        try:
            session_instance = CourseModuleSession.objects.select_related("course_module__teacher").get(id=session_id)
            teacher = session_instance.course_module.teacher
            if teacher:
                availabilities = availabilities.filter(teacher__user__email=teacher.email)
            # Also override mode based on session if we want to show exact availability?
            # But the student is checking available times for the session, so we don't need to enforce mode here
            # since the session dictates the mode. We just want to know if the teacher is free.
        except CourseModuleSession.DoesNotExist:
            pass

    if mode and not session_id:
        availabilities = availabilities.filter(mode=mode)

    # Group by time, mode and location
    slots_map = {}
    for avail in availabilities:
        location = avail.teacher.offline_location if avail.mode == SlotMode.OFFLINE else None
        key = (avail.start_time, avail.end_time, avail.mode, location)
        if key not in slots_map:
            slots_map[key] = {"total_capacity": 0, "total_booked": 0}
        slots_map[key]["total_capacity"] += 40

    # Subtract current bookings
    # We need to find TeacherSlot records for this date
    booked_slots = TeacherSlot.objects.filter(date=target_date).select_related("teacher")
    for bs in booked_slots:
        location = bs.teacher.offline_location if bs.mode == SlotMode.OFFLINE else None
        key = (bs.start_time, bs.end_time, bs.mode, location)
        if key in slots_map:
            slots_map[key]["total_booked"] += bs.booked_students

    available_slots = []
    for (start, end, smode, sloc), counts in slots_map.items():
        capacity_left = counts["total_capacity"] - counts["total_booked"]
        if capacity_left > 0:
            available_slots.append({
                "date": target_date,
                "start_time": start,
                "end_time": end,
                "mode": smode,
                "available_capacity": capacity_left,
                "offline_location": sloc
            })

    # Sort by start time
    available_slots.sort(key=lambda x: x["start_time"])

    serializer = AvailableSlotSerializer(available_slots, many=True)
    return success_response(serializer.data, message="Available slots fetched successfully.")


@extend_schema(
    methods=["POST"],
    tags=["Student Booking"],
    operation_id="student_book_slot",
    request=StudentBookingSerializer,
    responses={201: StudentBookingSerializer},
    description="Book a slot as a student. The system automatically assigns the least booked available teacher.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_book_slot(request):
    if request.user.role != UserRole.STUDENT:
        return error_response("Only students can book slots.", status_code=status.HTTP_403_FORBIDDEN)
    
    serializer = StudentBookingSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    date = serializer.validated_data["date"]
    start_time = serializer.validated_data["start_time"]
    mode = serializer.validated_data["mode"]
    offline_location = serializer.validated_data.get("offline_location")
    session_id = serializer.validated_data.get("session_id")
    course_id = serializer.validated_data.get("course_id")
    day_name = date.strftime("%A")

    # Check if the student already has a booking on this date and start_time
    duplicate_booking = StudentBooking.objects.filter(
        student=request.user,
        slot__date=date,
        slot__start_time=start_time
    ).exists()
    
    if duplicate_booking:
        return error_response(
            "You have already booked a session at this date and time.",
            status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        with transaction.atomic():
            session_instance = None
            chosen_teacher_id = None

            if session_id:
                # ── SESSION-BASED BOOKING ─────────────────────────────────────────
                # session_id থাকলে availability check করার দরকার নেই।
                # Session এ already teacher assigned আছে, তাকেই book করবো।
                # ─────────────────────────────────────────────────────────────────
                from teachers.models import CourseModuleSession
                try:
                    session_instance = CourseModuleSession.objects.select_related("course_module__teacher").get(id=session_id)
                except CourseModuleSession.DoesNotExist:
                    return error_response("Session not found.", status_code=status.HTTP_404_NOT_FOUND)

                teacher = session_instance.course_module.teacher
                if not teacher:
                    return error_response("No teacher assigned to this session.", status_code=status.HTTP_400_BAD_REQUEST)

                try:
                    teacher_profile = TeacherProfile.objects.get(user__email=teacher.email)
                    chosen_teacher_id = teacher_profile.id
                except TeacherProfile.DoesNotExist:
                    return error_response("Teacher profile not found for this session.", status_code=status.HTTP_404_NOT_FOUND)

                # Session এর নিজস্ব mode ও location override করো
                mode = SlotMode.ONLINE if session_instance.is_online else SlotMode.OFFLINE
                offline_location = session_instance.offline_location
                if not session_instance.is_online and not offline_location:
                    offline_location = teacher_profile.offline_location

            else:
                # ── NORMAL AVAILABILITY-BASED BOOKING ────────────────────────────
                avail_filters = {
                    "day_of_week": day_name,
                    "start_time": start_time,
                    "mode": mode
                }
                if mode == SlotMode.OFFLINE and offline_location:
                    avail_filters["teacher__offline_location"] = offline_location

                available_teachers = TeacherAvailability.objects.filter(
                    **avail_filters
                ).exclude(
                    withdrawal_requests__status__in=[RequestStatus.PENDING, RequestStatus.APPROVED]
                ).values_list("teacher_id", flat=True).distinct()

                if not available_teachers:
                    return error_response("No teachers available for this slot.", status_code=status.HTTP_404_NOT_FOUND)

                # Least-booked teacher বাছাই করো
                existing_slots = TeacherSlot.objects.select_for_update().filter(
                    teacher_id__in=available_teachers,
                    date=date,
                    start_time=start_time,
                    mode=mode
                )
                slots_by_teacher = {s.teacher_id: s for s in existing_slots}
                min_booked = 41

                for t_id in available_teachers:
                    booked = slots_by_teacher[t_id].booked_students if t_id in slots_by_teacher else 0
                    if booked < 40 and booked < min_booked:
                        min_booked = booked
                        chosen_teacher_id = t_id

            if chosen_teacher_id is None:
                return error_response("All slots are full for this time.", status_code=status.HTTP_400_BAD_REQUEST)

            # 3. Get or create the slot instance and increment
            slot_instance, created = TeacherSlot.objects.get_or_create(
                teacher_id=chosen_teacher_id,
                date=date,
                start_time=start_time,
                mode=mode,
                defaults={
                    "end_time": (datetime.combine(date, start_time) + timedelta(hours=1)).time() if "end_time" not in request.data else request.data.get("end_time")
                }
            )
            # If created, end_time logic above is a bit messy, let's fix it.
            if created:
                # Find end_time from availability
                avail = TeacherAvailability.objects.filter(teacher_id=chosen_teacher_id, day_of_week=day_name, start_time=start_time).first()
                if avail:
                    slot_instance.end_time = avail.end_time
                else:
                    slot_instance.end_time = (datetime.combine(date, start_time) + timedelta(hours=1)).time()
                slot_instance.save()

            if slot_instance.booked_students >= slot_instance.max_students:
                return error_response("Slot just became full. Please try another.", status_code=status.HTTP_400_BAD_REQUEST)

            # Increment atomically
            TeacherSlot.objects.filter(pk=slot_instance.pk).update(booked_students=F("booked_students") + 1)
            slot_instance.refresh_from_db()

            # 4. Create Booking
            course_instance = None
            if course_id:
                from students.models import RecommendedCourse
                try:
                    course_instance = RecommendedCourse.objects.get(id=course_id)
                except RecommendedCourse.DoesNotExist:
                    pass

            booking = StudentBooking.objects.create(
                student=request.user,
                slot=slot_instance,
                session=session_instance,
                course=course_instance
            )
            
            # 5. Send notifications (optional - celery নাও থাকতে পারে)
            try:
                from teachers.tasks import send_class_reminder_push_notification, send_teacher_booking_email
                from django.utils import timezone as tz

                try:
                    teacher_email = slot_instance.teacher.user.email
                    student_name = request.user.full_name
                    slot_date_str = date.strftime("%Y-%m-%d")
                    slot_time_str = start_time.strftime("%I:%M %p")
                    send_teacher_booking_email.delay(teacher_email, student_name, slot_date_str, slot_time_str)
                except Exception as e:
                    logger.exception("Failed to queue teacher booking email")

                try:
                    session_start = tz.make_aware(datetime.combine(date, start_time))
                    notification_time = session_start - timedelta(minutes=30)
                    if tz.now() < notification_time:
                        send_class_reminder_push_notification.apply_async(args=[request.user.id, slot_instance.id], eta=notification_time)
                    elif tz.now() < session_start:
                        send_class_reminder_push_notification.delay(request.user.id, slot_instance.id)
                except Exception as e:
                    logger.exception("Failed to queue class reminder")

            except ImportError:
                logger.warning("Celery not available, skipping booking notifications.")
            
            res_serializer = StudentBookingSerializer(booking)
            return success_response(res_serializer.data, message="Slot booked successfully.", status_code=status.HTTP_201_CREATED)

    except Exception as e:
        from django.db import IntegrityError
        if isinstance(e, IntegrityError) or "unique" in str(e).lower():
            return error_response(
                "You have already booked a session at this date and time.",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        logger.exception("Booking failed for user %s", request.user.pk)
        return error_response("Booking failed. Please try again.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    methods=["POST"],
    tags=["Student Booking"],
    operation_id="student_cancel_booking",
    responses={200: OpenApiResponse(description="Booking cancelled successfully.")},
    description="Cancel a student booking. Atomically decrements the booked_students count.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def student_cancel_booking(request, booking_id):
    try:
        with transaction.atomic():
            booking = StudentBooking.objects.select_related("slot").get(id=booking_id, student=request.user)
            slot = booking.slot
            
            # Decrement booked_students
            TeacherSlot.objects.filter(pk=slot.pk).update(booked_students=F("booked_students") - 1)
            
            # Delete booking
            booking.delete()
            
            return success_response(message="Booking cancelled successfully.")
    except StudentBooking.DoesNotExist:
        return error_response("Booking not found.", status_code=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Booking cancellation failed for booking %s", booking_id)
        return error_response("Cancellation failed. Please try again.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    methods=["GET"],
    tags=["Teachers Sessions"],
    operation_id="teachers_booked_sessions_list",
    responses={200: TeacherBookedSlotSerializer(many=True)},
    description="Fetch the list of sessions (slots) that have at least one booking for the logged-in teacher.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_booked_sessions(request):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    try:
        profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return error_response("Teacher profile not found.", status_code=status.HTTP_404_NOT_FOUND)

    # Filter slots that have at least one booking without feedback
    slots = TeacherSlot.objects.filter(
        teacher=profile,
        bookings__marks__isnull=True,
        bookings__feedback__isnull=True
    ).exclude(
        cancellation_requests__status=RequestStatus.PENDING
    ).distinct().order_by("-date", "-start_time")
    
    serializer = TeacherBookedSlotSerializer(slots, many=True)
    return success_response(serializer.data, message="Booked sessions fetched successfully.")


@extend_schema(
    methods=["GET"],
    tags=["Teachers Sessions"],
    operation_id="teachers_pending_students_list",
    parameters=[
        OpenApiParameter(name="search", description="Search by student name", required=False, type=OpenApiTypes.STR),
        OpenApiParameter(name="date", description="Filter by date (YYYY-MM-DD)", required=False, type=OpenApiTypes.DATE),
        OpenApiParameter(name="mode", description="Filter by mode (online/offline)", required=False, type=OpenApiTypes.STR),
        OpenApiParameter(name="time", description="Filter by time (HH:MM or HH:MM:SS)", required=False, type=OpenApiTypes.TIME),
    ],
    responses={200: TeacherStudentListSerializer(many=True)},
    description="Fetch the list of students for the teacher who have pending assessments (no feedback yet). Supports search by name, date, mode, and time.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_pending_students(request):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    # All bookings for the logged-in teacher that haven't received feedback/marks
    bookings = StudentBooking.objects.filter(
        slot__teacher__user=request.user,
        marks__isnull=True, 
        feedback__isnull=True
    ).exclude(
        slot__cancellation_requests__status=RequestStatus.PENDING
    ).select_related("student", "slot")

    # Apply filters
    search_query = request.query_params.get("search", "").strip()
    if search_query:
        from django.db.models import Q
        bookings = bookings.filter(
            Q(student__full_name__icontains=search_query) | 
            Q(student__student_profile__student_name__icontains=search_query)
        )

    date_filter = request.query_params.get("date")
    if date_filter:
        bookings = bookings.filter(slot__date=date_filter)

    mode_filter = request.query_params.get("mode")
    if mode_filter:
        bookings = bookings.filter(slot__mode=mode_filter.lower())

    time_filter = request.query_params.get("time")
    if time_filter:
        bookings = bookings.filter(slot__start_time=time_filter)

    # Order by booked_at descending or slot date
    bookings = bookings.order_by("-slot__date", "-slot__start_time")

    serializer = TeacherStudentListSerializer(bookings, many=True, context={"request": request})
    return success_response(serializer.data, message="Student list fetched successfully.")


@extend_schema(
    methods=["POST"],
    tags=["Teachers Sessions"],
    operation_id="teachers_student_feedback",
    request=TeacherFeedbackSerializer,
    responses={200: TeacherStudentListSerializer},
    description="Provide feedback and marks for a specific student's pending assessment.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_student_feedback(request, student_id):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    # Find pending booking(s) for this student and teacher
    bookings = StudentBooking.objects.filter(
        student_id=student_id, 
        slot__teacher__user=request.user,
        marks__isnull=True,
        feedback__isnull=True
    ).order_by('booked_at')

    booking = bookings.first()
    if not booking:
        return error_response("No pending assessment found for this student.", status_code=status.HTTP_404_NOT_FOUND)

    serializer = TeacherFeedbackSerializer(booking, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return success_response(TeacherStudentListSerializer(booking, context={"request": request}).data, message="Feedback submitted successfully.")
    return error_response("Invalid data.", errors=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["DELETE"],
    tags=["Teachers Sessions"],
    operation_id="teachers_remove_student",
    responses={200: OpenApiResponse(description="Student removed successfully.")},
    description="Teacher removes a student from pending assessments by student ID. This deletes their pending booking(s) and decrements slot count.",
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def teacher_remove_student(request, student_id):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    try:
        with transaction.atomic():
            # Find all pending bookings for this student and this teacher
            bookings = StudentBooking.objects.select_related("slot").filter(
                student_id=student_id, 
                slot__teacher__user=request.user,
                marks__isnull=True,
                feedback__isnull=True
            )
            
            if not bookings.exists():
                return error_response("No pending booking found for this student.", status_code=status.HTTP_404_NOT_FOUND)
            
            # Decrement booked_students for each slot
            for booking in bookings:
                TeacherSlot.objects.filter(pk=booking.slot.pk).update(booked_students=F("booked_students") - 1)
            
            # Delete bookings
            deleted_count, _ = bookings.delete()
            
            return success_response(message=f"Student removed from the list successfully. Deleted {deleted_count} pending booking(s).")
    except Exception as e:
        logger.exception("Removing student %s failed", student_id)
        return error_response("Removal failed. Please try again.", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    methods=["POST"],
    tags=["Teachers Requests"],
    operation_id="teachers_request_cancellation",
    request=CancellationRequestSubmitSerializer,
    responses={201: PendingRequestSerializer},
    description="Teacher submits a cancellation request (Session or Availability).",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_request_cancellation(request):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can submit requests.", status_code=status.HTTP_403_FORBIDDEN)

    try:
        profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return error_response("Teacher profile not found.", status_code=status.HTTP_404_NOT_FOUND)

    serializer = CancellationRequestSubmitSerializer(data=request.data)
    if serializer.is_valid():
        request_type = serializer.validated_data["request_type"]
        details = serializer.validated_data.get("details", "")
        slot_id = serializer.validated_data.get("slot_id")
        availability_id = serializer.validated_data.get("availability_id")
        
        slot_obj = None
        avail_obj = None

        # 1. Handle Session Cancellation
        if request_type == RequestType.SESSION_CANCELLATION:
            if slot_id:
                try:
                    slot_obj = TeacherSlot.objects.get(id=slot_id, teacher=profile)
                    date_str = slot_obj.date.strftime("%Y-%m-%d")
                    start_time_str = slot_obj.start_time.strftime("%I:%M %p")
                    details = f"Session: {slot_obj.title} on {date_str} at {start_time_str}"
                except TeacherSlot.DoesNotExist:
                    return error_response("Slot not found or does not belong to you.", status_code=status.HTTP_404_NOT_FOUND)
            elif not details:
                return error_response("Slot ID or specific details are required for session cancellation.", status_code=status.HTTP_400_BAD_REQUEST)

        # 2. Handle Availability Withdrawal
        elif request_type == RequestType.AVAILABILITY_WITHDRAWAL:
            if availability_id:
                try:
                    avail_obj = TeacherAvailability.objects.get(id=availability_id, teacher=profile)
                    start_str = avail_obj.start_time.strftime("%I:%M %p")
                    end_str = avail_obj.end_time.strftime("%I:%M %p")
                    details = f"Availability: {avail_obj.day_of_week} ({start_str} - {end_str}) {avail_obj.mode.upper()}"
                except TeacherAvailability.DoesNotExist:
                    return error_response("Availability record not found or does not belong to you.", status_code=status.HTTP_404_NOT_FOUND)
            elif not details:
                return error_response("Availability ID or specific details are required for withdrawal.", status_code=status.HTTP_400_BAD_REQUEST)

        pending_request = PendingRequest.objects.create(
            teacher=profile,
            request_type=request_type,
            details=details,
            cancellation_reason=serializer.validated_data.get("cancellation_reason", ""),
            slot=slot_obj,
            availability=avail_obj,
            status=RequestStatus.PENDING
        )
        return success_response(
            PendingRequestSerializer(pending_request).data,
            message="Request submitted successfully.",
            status_code=status.HTTP_201_CREATED
        )
    return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)


@extend_schema(
    methods=["GET"],
    tags=["Teachers Requests"],
    operation_id="teachers_pending_requests_list",
    responses={200: PendingRequestSerializer(many=True)},
    description="Fetch the list of cancellation requests for the logged-in teacher.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_pending_requests(request):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    try:
        profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return error_response("Teacher profile not found.", status_code=status.HTTP_404_NOT_FOUND)

    requests = PendingRequest.objects.filter(teacher=profile).order_by("-created_at")
    serializer = PendingRequestSerializer(requests, many=True)
    return success_response(serializer.data, message="Pending requests fetched successfully.")


@extend_schema(
    methods=["GET"],
    tags=["Admin Notification"],
    operation_id="admin_notification_count",
    responses={200: OpenApiResponse(description="Count of pending requests.")},
    description="Fetch the count of pending requests for the admin notification icon.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_notification_count(request):
    if request.user.role != UserRole.ADMIN:
        return error_response("Only admins can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    count = PendingRequest.objects.filter(status=RequestStatus.PENDING).count()
    return success_response({"count": count}, message="Notification count fetched successfully.")


@extend_schema(
    tags=["Teachers Sessions"],
    operation_id="teachers_send_session_notice",
    request=SessionNoticeSerializer,
    responses={
        200: OpenApiResponse(description="Notice sent successfully."),
        400: OpenApiResponse(description="Validation error."),
        403: OpenApiResponse(description="Permission denied."),
        404: OpenApiResponse(description="Slot not found."),
    },
    description="Teacher sends a push notification to all students who have booked a specific slot.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def teacher_send_session_notice(request, slot_id):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can send notices.", status_code=status.HTTP_403_FORBIDDEN)

    try:
        slot = TeacherSlot.objects.get(id=slot_id, teacher__user=request.user)
    except TeacherSlot.DoesNotExist:
        return error_response("Slot not found or you don't have access to it.", status_code=status.HTTP_404_NOT_FOUND)

    serializer = SessionNoticeSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", serializer.errors, status.HTTP_400_BAD_REQUEST)

    # Get all students who have booked this slot and have an expo_push_token and is_push_notification enabled
    bookings = slot.bookings.select_related("student").filter(
        student__expo_push_token__isnull=False,
        student__is_push_notification=True
    ).exclude(student__expo_push_token="")
    
    push_tokens = [booking.student.expo_push_token for booking in bookings]
    
    if not push_tokens:
        return success_response(message="No students with valid push tokens found for this session.")

    title = serializer.validated_data["title"]
    body = serializer.validated_data["body"]
    
    # Save notifications to database
    from students.models import StudentNotification
    notifications_to_create = []
    for booking in bookings:
        notifications_to_create.append(
            StudentNotification(
                student=booking.student,
                title=title,
                body=body
            )
        )
    if notifications_to_create:
        StudentNotification.objects.bulk_create(notifications_to_create)

    # Send push notifications
    result = send_expo_push_notification(
        push_tokens=push_tokens,
        title=title,
        body=body,
        data={"slot_id": slot_id, "screen": "session_details"}
    )

    return success_response(
        data={"expo_result": result},
        message=f"Notice sent and saved for {len(push_tokens)} students."
    )


@extend_schema(
    tags=["Teachers Dashboard"],
    operation_id="teachers_dashboard",
    responses={200: TeacherDashboardSerializer},
    description="Fetch teacher dashboard data: stats, curriculum, and upcoming sessions.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_dashboard(request):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access the dashboard.", status_code=status.HTTP_403_FORBIDDEN)

    try:
        profile = TeacherProfile.objects.get(user=request.user)
    except TeacherProfile.DoesNotExist:
        return error_response("Teacher profile not found.", status_code=status.HTTP_404_NOT_FOUND)

    now = timezone.now()
    today = now.date()
    seven_days_ago = today - timedelta(days=7)

    # 1. Today's sessions count
    today_sessions_count = TeacherSlot.objects.filter(teacher=profile, date=today).count()

    # 2. Last 7 days sessions count
    week_sessions_count = TeacherSlot.objects.filter(
        teacher=profile, 
        date__gte=seven_days_ago, 
        date__lt=today
    ).count()

    # 3. Total students (unique students booked in their slots)
    total_students = StudentBooking.objects.filter(slot__teacher=profile).values("student").distinct().count()

    # 4. Curriculum list (Sessions with curriculum)
    # Showing slots that have a curriculum uploaded
    curriculum_slots = TeacherSlot.objects.filter(
        teacher=profile, 
        teachers_curriculum__isnull=False
    ).exclude(
        teachers_curriculum=""
    ).exclude(
        cancellation_requests__status=RequestStatus.PENDING
    ).order_by("-date")

    # 5. Upcoming sessions
    upcoming_sessions = TeacherSlot.objects.filter(
        teacher=profile, 
        date__gte=today
    ).exclude(
        cancellation_requests__status=RequestStatus.PENDING
    ).order_by("date", "start_time")[:5]

    payload = {
        "teacher_name": profile.name,
        "profile_picture": request.build_absolute_uri(profile.profile_picture.url) if profile.profile_picture else None,
        "stats": {
            "today": today_sessions_count,
            "week": week_sessions_count,
            "students": total_students,
        },
        "teacher_room": profile.teachers_room,
        "curriculum": TeacherBookedSlotSerializer(curriculum_slots, many=True, context={"request": request}).data,
        "upcoming_sessions": TeacherBookedSlotSerializer(upcoming_sessions, many=True, context={"request": request}).data,
    }

    return success_response(payload, message="Teacher dashboard data fetched successfully.")


@extend_schema(
    methods=["GET"],
    tags=["Teachers Sessions"],
    operation_id="teachers_student_progress",
    responses={200: OpenApiResponse(description="Student progress fetched successfully.")},
    description="Fetch a specific student's progress including assessment attempts and booking feedback.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_student_progress(request, student_id):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    from accounts.models import User
    try:
        student = User.objects.get(id=student_id, role=UserRole.STUDENT)
    except User.DoesNotExist:
        return error_response("Student not found.", status_code=status.HTTP_404_NOT_FOUND)

    from students.models import StudentProfile, StudentAssessmentAttempt, AssessmentAttemptStatus
    from decimal import Decimal
    
    try:
        profile = student.student_profile
        student_name = profile.student_name if profile.student_name else student.full_name
        profile_picture = request.build_absolute_uri(profile.profile_picture.url) if profile.profile_picture else None
    except StudentProfile.DoesNotExist:
        student_name = student.full_name
        profile_picture = None

    # Assessment Attempts
    assessments = StudentAssessmentAttempt.objects.filter(
        student=student,
        status=AssessmentAttemptStatus.EVALUATED
    ).order_by("-evaluated_at")
    
    assessment_progress = []
    for att in assessments:
        total_max = sum(q.marks for s in att.template.sections.all() for q in s.questions.all())
        overall_pct = (att.total_score * Decimal("100") / total_max).quantize(Decimal("0.01")) if total_max > 0 else Decimal("0")
        
        assessment_progress.append({
            "id": att.id,
            "template_name": att.template.name,
            "total_score": att.total_score,
            "percentage": f"{overall_pct}%",
            "is_passed": att.is_passed,
            "evaluated_at": att.evaluated_at,
        })

    # Bookings with Marks (Session Progress)
    bookings_with_marks = StudentBooking.objects.filter(
        student=student,
        marks__isnull=False
    ).order_by("booked_at")
    
    session_progress = []
    for i, b in enumerate(bookings_with_marks):
        session_progress.append({
            "id": b.id,
            "test_name": f"Progress test {i + 1}",
            "percentage": f"{b.marks}%",
            "feedback": b.feedback if b.feedback else "Good progress!",
            "date": b.slot.date,
        })

    payload = {
        "student_name": student_name,
        "profile_picture": profile_picture,
        "assessments": assessment_progress,
        "session_progress": session_progress,
    }

    return success_response(payload, message="Student progress fetched successfully.")


@extend_schema(
    methods=["GET"],
    tags=["Teachers Sessions"],
    operation_id="teachers_student_assessment_result",
    responses={200: OpenApiResponse(description="Assessment result fetched successfully.")},
    description="Get the detailed result (score breakdown) of a specific student's assessment attempt.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teacher_student_assessment_result(request, attempt_id):
    if request.user.role != UserRole.TEACHER:
        return error_response("Only teachers can access this endpoint.", status_code=status.HTTP_403_FORBIDDEN)

    from students.models import StudentAssessmentAttempt, AssessmentAttemptStatus, AssessmentLevelBand
    from decimal import Decimal

    try:
        attempt = StudentAssessmentAttempt.objects.select_related("template", "student").get(
            id=attempt_id,
            status=AssessmentAttemptStatus.EVALUATED
        )
    except StudentAssessmentAttempt.DoesNotExist:
        return error_response("Assessment attempt not found or not yet evaluated.", status_code=status.HTTP_404_NOT_FOUND)

    template = attempt.template

    # Calculate max scores per skill
    skill_max = {}
    for section in template.sections.all():
        skill = section.skill
        section_max = sum(q.marks for q in section.questions.all())
        skill_max[skill] = skill_max.get(skill, Decimal("0")) + section_max

    total_max = sum(skill_max.values(), Decimal("0"))
    overall_pct = (attempt.total_score * Decimal("100") / total_max).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total_max > 0 else Decimal("0")

    # Find mapped level
    mapped_level = None
    level_band = AssessmentLevelBand.objects.filter(
        template=template,
        min_score__lte=overall_pct,
        max_score__gte=overall_pct
    ).first()
    
    if level_band:
        mapped_level = level_band.get_label_display()

    skill_field_map = {
        "reading": attempt.reading_score,
        "listening": attempt.listening_score,
        "writing": attempt.writing_score,
        "grammar": attempt.grammar_score,
        "vocabulary": attempt.vocabulary_score,
    }

    skill_scores = []
    for skill, max_s in skill_max.items():
        earned = skill_field_map.get(skill) or Decimal("0")
        pct = (earned * Decimal("100") / max_s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if max_s > 0 else Decimal("0")
        skill_scores.append({
            "skill": skill,
            "score": earned,
            "max_score": max_s,
            "percentage": pct,
        })

    try:
        profile = attempt.student.student_profile
        student_name = profile.student_name if profile.student_name else attempt.student.full_name
        profile_picture = request.build_absolute_uri(profile.profile_picture.url) if profile.profile_picture else None
    except Exception:
        student_name = attempt.student.full_name
        profile_picture = None

    result = {
        "student_name": student_name,
        "profile_picture": profile_picture,
        "attempt_id": attempt.id,
        "template_name": template.name,
        "total_score": attempt.total_score,
        "max_total_score": total_max,
        "overall_percentage": overall_pct,
        "is_passed": attempt.is_passed,
        "pass_percentage": template.pass_percentage,
        "mapped_level": mapped_level,
        "skill_scores": skill_scores,
    }

    return success_response(result, message="Assessment result fetched successfully.")


@extend_schema(
    methods=["GET"],
    tags=["Teachers Sessions"],
    operation_id="course_sessions_list",
    responses={200: OpenApiResponse(description="List of sessions for a course module.")},
    description="Fetch all sessions (session name and availability date range) for a given course module ID or banner ID.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_course_sessions(request, course_id):
    from teachers.models import CourseModuleSession, TeacherProfile
    from django.db.models import Q
    
    sessions = CourseModuleSession.objects.filter(
        Q(course_module_id=course_id) | Q(course_module__banner_id=course_id)
    ).select_related("course_module__teacher").distinct()
    
    teacher_emails = [s.course_module.teacher.email for s in sessions if s.course_module and s.course_module.teacher]
    profiles = TeacherProfile.objects.filter(user__email__in=teacher_emails).select_related('user')
    email_to_profile_id = {p.user.email: p.id for p in profiles}
    
    data = []
    for s in sessions:
        t_id = None
        if s.course_module and s.course_module.teacher:
            t_id = email_to_profile_id.get(s.course_module.teacher.email)
            
        data.append({
            "id": s.id,
            "session_name": s.session_name,
            "availability_date_range": s.availability_date_range,
            "teacher_id": t_id
        })
    
    return success_response(data, message="Sessions fetched successfully.")


@extend_schema(
    methods=["GET"],
    tags=["Teachers Sessions"],
    operation_id="session_dates_list",
    responses={200: OpenApiResponse(description="List of dates and times for a session.")},
    description="Fetch available dates and times for a specific session.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_session_dates(request, session_id, teacher_id):
    from teachers.models import CourseModuleSession, TeacherProfile
    from datetime import datetime, timedelta

    try:
        session = CourseModuleSession.objects.select_related("course_module__teacher").get(id=session_id)
    except CourseModuleSession.DoesNotExist:
        return error_response("Session not found.", status_code=status.HTTP_404_NOT_FOUND)

    if not session.availability_date_range:
        return success_response([], message="No date range available for this session.")

    # Try to parse date range assuming "YYYY-MM-DD to YYYY-MM-DD"
    try:
        parts = session.availability_date_range.split("to")
        if len(parts) == 2:
            start_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        else:
            return error_response("Invalid date range format. Expected 'YYYY-MM-DD to YYYY-MM-DD'.", status_code=status.HTTP_400_BAD_REQUEST)
    except ValueError:
        return error_response("Invalid date range format. Expected 'YYYY-MM-DD to YYYY-MM-DD'.", status_code=status.HTTP_400_BAD_REQUEST)

    try:
        profile = TeacherProfile.objects.get(id=teacher_id)
    except TeacherProfile.DoesNotExist:
        return error_response("Teacher profile not found.", status_code=status.HTTP_404_NOT_FOUND)

    availabilities = profile.availabilities.all()
    # Group availabilities by day of week
    avail_by_day = {}
    for avail in availabilities:
        day_name = avail.day_of_week
        if day_name not in avail_by_day:
            avail_by_day[day_name] = []
        avail_by_day[day_name].append({
            "start_time": avail.start_time,
            "end_time": avail.end_time,
            "mode": avail.mode
        })

    data = []
    current_date = start_date
    while current_date <= end_date:
        day_name = current_date.strftime("%A")
        if day_name in avail_by_day:
            data.append({
                "date": current_date,
                "day_of_week": day_name,
                "times": avail_by_day[day_name]
            })
        current_date += timedelta(days=1)
        
    response_data = {
        "teacher_id": profile.id,
        "teacher_name": profile.name,
        "dates": data
    }

    return success_response(response_data, message="Session dates fetched successfully.")


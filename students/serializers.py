from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

import re

from students.models import AssessmentTemplate, AssessmentSection, AssessmentQuestion, AssessmentOption, StudentAssessmentAttempt, StudentLocation

STUDENT_AGE_MIN = 5
STUDENT_AGE_MAX = 100
GENDER_CHOICES = ("male", "female", "other")
_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def _validate_phone(value):
    """Blank is allowed; otherwise 7-15 digits with an optional leading +. Returns it without separators."""
    value = re.sub(r"[\s\-().]", "", value or "")
    if value and not _PHONE_RE.match(value):
        raise serializers.ValidationError("Enter a valid phone number (7-15 digits, optional leading +).")
    return value


class StudentProfileSetupUpsertSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    age = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=120)
    gender = serializers.CharField(max_length=20, required=False, allow_blank=True)
    last_achieved_degree = serializers.CharField(max_length=255, required=False, allow_blank=True)
    profile_picture = extend_schema_field(OpenApiTypes.BINARY)(
        serializers.ImageField(required=False, allow_null=True)
    )
    parents_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    parents_phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    core_reasons_of_learning = serializers.ListField(
        child=serializers.CharField(max_length=255),
        required=False,
    )
    preferred_study_time = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
    )
    preferred_study_mode = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
    )
    preferred_study_language = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
    )

    @staticmethod
    def _normalize_list(values):
        normalized = []
        seen = set()
        for item in values:
            value = str(item).strip()
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def validate_phone(self, value):
        return _validate_phone(value)

    def validate_parents_phone_number(self, value):
        return _validate_phone(value)

    def validate_age(self, value):
        # 0 is what older app builds sent for "not given".
        if value in (None, 0):
            return None
        if not (STUDENT_AGE_MIN <= value <= STUDENT_AGE_MAX):
            raise serializers.ValidationError(f"Enter an age between {STUDENT_AGE_MIN} and {STUDENT_AGE_MAX}.")
        return value

    def validate_gender(self, value):
        value = (value or "").strip().lower()
        if value and value not in GENDER_CHOICES:
            raise serializers.ValidationError("Choose male, female or other.")
        return value

    def validate_core_reasons_of_learning(self, value):
        return self._normalize_list(value)

    def validate_preferred_study_time(self, value):
        return self._normalize_list(value)

    def validate_preferred_study_mode(self, value):
        return self._normalize_list(value)

    def validate_preferred_study_language(self, value):
        return self._normalize_list(value)


class StudentProfileSetupDataSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    age = serializers.IntegerField(required=False, allow_null=True)
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    last_achieved_degree = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    profile_picture = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    parents_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    parents_phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_location = serializers.BooleanField(required=False, default=False)
    core_reasons_of_learning = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    preferred_study_time = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    preferred_study_mode = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    preferred_study_language = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    core_reasons_options = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    interest_options = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class StudentProfileSetupSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = StudentProfileSetupDataSerializer()


class StudentErrorResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=False)
    message = serializers.CharField()
    errors = serializers.JSONField(required=False)


class StudentInterestOptionsDataSerializer(serializers.Serializer):
    interests = serializers.ListField(child=serializers.CharField())


class StudentInterestOptionsSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = StudentInterestOptionsDataSerializer()


class AssessmentOptionDisplaySerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentOption
        fields = ["id", "text", "order"]


class AssessmentQuestionDisplaySerializer(serializers.ModelSerializer):
    options = AssessmentOptionDisplaySerializer(many=True, read_only=True)
    question_type = serializers.SerializerMethodField()
    audio_file = serializers.SerializerMethodField()

    def get_question_type(self, obj):
        skill = obj.section.skill
        if skill == "reading":
            return "passage"
        elif skill == "listening":
            return "audio"
        return obj.question_type

    def get_audio_file(self, obj):
        if not obj.audio_file:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.audio_file.url)
        return obj.audio_file.url

    class Meta:
        model = AssessmentQuestion
        fields = ["id", "question_type", "prompt", "audio_file", "max_listens", "transcript", "marks", "options"]


class RandomQuizQuestionSerializer(AssessmentQuestionDisplaySerializer):
    level_name = serializers.SerializerMethodField()
    level_id = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField())
    def get_level_name(self, obj) -> str:
        return obj.section.template.name

    @extend_schema_field(serializers.IntegerField())
    def get_level_id(self, obj) -> int:
        return obj.section.template.id

    class Meta(AssessmentQuestionDisplaySerializer.Meta):
        fields = AssessmentQuestionDisplaySerializer.Meta.fields + ["level_name", "level_id"]


class RandomQuizSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = RandomQuizQuestionSerializer(many=True)


class RandomQuizLevelBreakdownSerializer(serializers.Serializer):
    level_name = serializers.CharField()
    total = serializers.IntegerField()
    correct = serializers.IntegerField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2)
    max_score = serializers.DecimalField(max_digits=6, decimal_places=2)
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)


class RandomQuizDetailedResultSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    prompt = serializers.CharField()
    level_name = serializers.CharField()
    submitted_option_id = serializers.IntegerField(allow_null=True)
    is_correct = serializers.BooleanField()
    correct_option_id = serializers.IntegerField(allow_null=True)
    correct_option_text = serializers.CharField(allow_blank=True, allow_null=True)


class RandomQuizResultDataSerializer(serializers.Serializer):
    total_questions = serializers.IntegerField()
    total_correct = serializers.IntegerField()
    overall_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    max_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    overall_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    suggested_level = serializers.CharField()
    level_breakdown = RandomQuizLevelBreakdownSerializer(many=True)
    detailed_results = RandomQuizDetailedResultSerializer(many=True)


class RandomQuizSubmitResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = RandomQuizResultDataSerializer()


class RandomQuizScoreDetailSerializer(serializers.Serializer):
    attempt_id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    student_email = serializers.CharField()
    overall_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    max_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    overall_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    suggested_level = serializers.CharField()
    evaluated_at = serializers.DateTimeField()


class RandomQuizScoresListResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = RandomQuizScoreDetailSerializer(many=True)


class RandomQuizStatsDataSerializer(serializers.Serializer):
    average_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    average_score_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    score_difference = serializers.DecimalField(max_digits=5, decimal_places=2)
    score_difference_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    change_type = serializers.CharField()


class RandomQuizStatsSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = RandomQuizStatsDataSerializer()


class AssessmentSectionDisplaySerializer(serializers.ModelSerializer):
    questions = AssessmentQuestionDisplaySerializer(many=True, read_only=True)
    
    class Meta:
        model = AssessmentSection
        fields = ["id", "title", "skill", "instructions", "weight", "questions"]


class AssessmentTemplateDisplaySerializer(serializers.ModelSerializer):
    sections = AssessmentSectionDisplaySerializer(many=True, read_only=True)
    
    class Meta:
        model = AssessmentTemplate
        fields = ["id", "name", "version", "pass_percentage", "sections"]


class AssessmentTemplateListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentTemplate
        fields = ["id", "name", "version", "pass_percentage"]


class AssessmentTemplateSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = AssessmentTemplateDisplaySerializer()


class AssessmentTemplateListSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = AssessmentTemplateListSerializer(many=True)


# ─── Exam Submit Serializers ───────────────────────────────────────────────────

class AnswerSubmitSerializer(serializers.Serializer):
    """Single answer: question id + selected option id (MCQ) or text."""
    question_id = serializers.IntegerField()
    selected_option_id = serializers.IntegerField(required=False, allow_null=True)
    text_answer = serializers.CharField(required=False, allow_blank=True, default="")


class ExamSubmitRequestSerializer(serializers.Serializer):
    answers = AnswerSubmitSerializer(many=True)


class SkillScoreSerializer(serializers.Serializer):
    skill = serializers.CharField()
    score = serializers.DecimalField(max_digits=8, decimal_places=2)
    max_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)


class AssessmentResultDataSerializer(serializers.Serializer):
    attempt_id = serializers.IntegerField()
    template_name = serializers.CharField()
    total_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    max_total_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    overall_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_passed = serializers.BooleanField()
    pass_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    mapped_level = serializers.CharField(allow_null=True)
    skill_scores = SkillScoreSerializer(many=True)


class AssessmentResultSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = AssessmentResultDataSerializer()


class StudentDashboardProgressSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    test_name = serializers.CharField()
    percentage = serializers.CharField()
    feedback = serializers.CharField(allow_null=True, allow_blank=True)


class StudentDashboardDataSerializer(serializers.Serializer):
    student_name = serializers.CharField()
    profile_picture = serializers.ImageField()
    upcoming_session = serializers.JSONField(required=False, allow_null=True)
    my_progress = StudentDashboardProgressSerializer(many=True)


class StudentDashboardSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = StudentDashboardDataSerializer()


# ─── Student Location Serializers ─────────────────────────────────────────────

class StudentLocationUpsertSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=20, decimal_places=15)
    longitude = serializers.DecimalField(max_digits=20, decimal_places=15)


class StudentLocationDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentLocation
        fields = ["latitude", "longitude", "updated_at"]


class StudentLocationSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = StudentLocationDataSerializer()


class RecommendedCourseDataSerializer(serializers.ModelSerializer):
    is_enrolled = serializers.BooleanField(required=False)
    sessions = serializers.ListField(required=False)

    class Meta:
        from students.models import RecommendedCourse
        model = RecommendedCourse
        fields = ["id", "course_name", "banner", "is_enrolled", "sessions"]


class RecommendedCourseSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = RecommendedCourseDataSerializer()


class GeneralInfoDataSerializer(serializers.ModelSerializer):
    class Meta:
        from teachers.models import GeneralInfo
        model = GeneralInfo
        fields = [
            "id", "facebook_link", "youtube_link", "whatsapp_link",
            "library_link", "adult_learning_club_link", "kids_learning_club_link",
            "calender_type", "calender_upload"
        ]


class GeneralInfoSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = GeneralInfoDataSerializer()


class StudentNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        from students.models import StudentNotification
        model = StudentNotification
        fields = ["id", "title", "body", "is_read", "created_at"]


class StudentNotificationSuccessResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    data = StudentNotificationSerializer(many=True)

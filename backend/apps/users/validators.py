from django.core.exceptions import ValidationError


class MaximumLengthValidator:
    def __init__(self, max_length=128):
        self.max_length = max_length

    def validate(self, password, user=None):
        if len(password) > self.max_length:
            raise ValidationError(
                f"비밀번호는 {self.max_length}자를 넘을 수 없습니다.",
                code="password_too_long",
            )

    def get_help_text(self):
        return f"비밀번호는 {self.max_length}자 이하여야 합니다."

import random
from typing import List

from django.apps import apps


class CodeGenerator:
    ALLOWED_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789'

    @classmethod
    def generate_unique_codes_batch(cls, app_label: str, model_name: str,
                                    code_field_name: str, length: int, count: int) -> List[str]:
        """Generate multiple unique codes in one batch, querying the DB only once."""
        model = apps.get_model(app_label=app_label, model_name=model_name)
        existing_codes = set(model.objects.values_list(code_field_name, flat=True))

        generated_codes = []
        max_attempts = count * 10

        for _ in range(max_attempts):
            if len(generated_codes) >= count:
                break
            code = cls._random_code(length)
            if code not in existing_codes:
                generated_codes.append(code)
                existing_codes.add(code)

        if len(generated_codes) < count:
            raise ValueError(f"Could not generate {count} unique codes after {max_attempts} attempts")

        return generated_codes

    @classmethod
    def generate_unique_code(cls, app_label: str, model_name: str,
                             code_field_name: str, length: int) -> str:
        codes = cls.generate_unique_codes_batch(app_label, model_name, code_field_name, length, 1)
        return codes[0]

    @classmethod
    def _random_code(cls, length):
        return ''.join(random.choice(cls.ALLOWED_CHARS) for _ in range(length))

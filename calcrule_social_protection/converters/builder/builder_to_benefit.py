from calcrule_social_protection.utils import CodeGenerator
from calcrule_social_protection.apps import CalcruleSocialProtectionConfig
from payroll.models import BenefitConsumptionStatus


class BuilderToBenefitConverter:
    TYPE = None

    def __init__(self):
        self._code_cache = []
        self._cache_index = 0

    def _pregenerate_codes(self, count):
        self._code_cache = CodeGenerator.generate_unique_codes_batch(
            'payroll', 'BenefitConsumption', 'code',
            CalcruleSocialProtectionConfig.code_length, count
        )
        self._cache_index = 0

    def to_benefit_obj(self, entity, amount, payment_plan, payment_cycle):
        benefit = {}
        self._build_individual(benefit, entity)
        self._build_code(benefit)
        self._build_amount(benefit, amount)
        self._build_date_dates(benefit, payment_plan, payment_cycle)
        self._build_type(benefit)
        self._build_status(benefit)
        return benefit

    def _build_individual(self, benefit, entity):
        pass

    def _build_code(self, benefit):
        if self._cache_index < len(self._code_cache):
            code = self._code_cache[self._cache_index]
            self._cache_index += 1
        else:
            code = CodeGenerator.generate_unique_code(
                'payroll', 'BenefitConsumption', 'code',
                CalcruleSocialProtectionConfig.code_length
            )
        benefit["code"] = code

    @classmethod
    def _build_amount(cls, benefit, amount):
        benefit["amount"] = amount

    @classmethod
    def _build_date_dates(cls, benefit, payment_plan, payment_cycle):
        benefit["date_due"] = f"{payment_cycle.end_date}"
        benefit["date_valid_from"] = f"{payment_plan.benefit_plan.date_valid_from}"
        benefit["date_valid_to"] = f"{payment_plan.benefit_plan.date_valid_to}"

    @classmethod
    def _build_type(cls, benefit):
        benefit["type"] = 'Cash Transfer'

    @classmethod
    def _build_status(cls, benefit):
        benefit["status"] = BenefitConsumptionStatus.ACCEPTED.value

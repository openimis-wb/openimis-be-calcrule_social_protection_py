from social_protection.models import GroupBeneficiary

from calcrule_social_protection.converters import (
    GroupToBillConverter,
    GroupToBillItemConverter,
    GroupToBenefitConverter
)
from calcrule_social_protection.strategies.benefit_package_base_strategy import BaseBenefitPackageStrategy


class GroupBenefitPackageStrategy(BaseBenefitPackageStrategy):
    TYPE = "GROUP"
    BENEFICIARY_OBJECT = GroupBeneficiary
    BENEFICIARY_TYPE = "group"
    CONVERTER = GroupToBillConverter
    CONVERTER_BENEFIT = GroupToBenefitConverter

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        group = kwargs.get('group', None)
        additional_parameters = {
            "entity": group,
            "converter": kwargs.get('converter') or cls._init_converter(cls.CONVERTER, 1, None),
            "converter_item": GroupToBillItemConverter,
            "converter_benefit": kwargs.get('converter_benefit') or cls._init_converter(cls.CONVERTER_BENEFIT, 1, None),
            **kwargs
        }
        return super().convert(payment_plan, **additional_parameters)

    @classmethod
    def _prefetch_converter_data(cls, converter_benefit, beneficiaries):
        if converter_benefit and hasattr(converter_benefit, 'prefetch_recipients'):
            converter_benefit.prefetch_recipients(beneficiaries)

    @classmethod
    def _collect_convert_results(cls, calculation, payment_plan, **kwargs):
        group = kwargs.get('group', None)
        additional_parameters = {
            "entity": group,
            "converter": kwargs.get('converter') or cls._init_converter(cls.CONVERTER, 1, None),
            "converter_item": GroupToBillItemConverter,
            "converter_benefit": kwargs.get('converter_benefit') or cls._init_converter(cls.CONVERTER_BENEFIT, 1, None),
            **kwargs
        }
        return super()._collect_convert_results(calculation, payment_plan, **additional_parameters)

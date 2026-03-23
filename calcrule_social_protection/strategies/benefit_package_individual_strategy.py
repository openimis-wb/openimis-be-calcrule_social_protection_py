from social_protection.models import Beneficiary
from calcrule_social_protection.converters import (
    BeneficiaryToBillConverter,
    BeneficiaryToBillItemConverter,
    BeneficiaryToBenefitConverter
)
from calcrule_social_protection.strategies.benefit_package_base_strategy import BaseBenefitPackageStrategy


class IndividualBenefitPackageStrategy(BaseBenefitPackageStrategy):
    TYPE = "INDIVIDUAL"
    BENEFICIARY_OBJECT = Beneficiary
    BENEFICIARY_TYPE = "beneficiary"
    CONVERTER = BeneficiaryToBillConverter
    CONVERTER_BENEFIT = BeneficiaryToBenefitConverter

    @classmethod
    def _get_select_related(cls):
        return ['individual']

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        beneficiary = kwargs.get('beneficiary', None)
        additional_parameters = {
            "entity": beneficiary,
            "converter": kwargs.get('converter') or cls._init_converter(cls.CONVERTER, 1, None),
            "converter_item": BeneficiaryToBillItemConverter,
            "converter_benefit": kwargs.get('converter_benefit') or cls._init_converter(cls.CONVERTER_BENEFIT, 1, None),
            **kwargs
        }
        return super().convert(payment_plan, **additional_parameters)

    @classmethod
    def _collect_convert_results(cls, calculation, payment_plan, **kwargs):
        beneficiary = kwargs.get('beneficiary', None)
        additional_parameters = {
            "entity": beneficiary,
            "converter": kwargs.get('converter') or cls._init_converter(cls.CONVERTER, 1, None),
            "converter_item": BeneficiaryToBillItemConverter,
            "converter_benefit": kwargs.get('converter_benefit') or cls._init_converter(cls.CONVERTER_BENEFIT, 1, None),
            **kwargs
        }
        return super()._collect_convert_results(calculation, payment_plan, **additional_parameters)

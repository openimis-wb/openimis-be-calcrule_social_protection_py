import importlib
import inspect
from django.apps import AppConfig
from calculation.apps import CALCULATION_RULES

MODULE_NAME = 'calcrule_social_protection'
DEFAULT_CFG = {
    'calculate_business_event': 'calcrule_social_protection.calculate',
}


def read_all_calculation_rules():
    """function to read all calculation rules from that module"""
    for name, cls in inspect.getmembers(importlib.import_module('calcrule_social_protection.calculation_rule'),
                                        inspect.isclass):
        if cls.__module__.split('.')[1] == 'calculation_rule':
            CALCULATION_RULES.append(cls)
            cls.ready()


class CalcruleSocialProtectionConfig(AppConfig):
    name = MODULE_NAME

    calculate_business_event = None

    def ready(self):
        from core.models import ModuleConfiguration
        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CFG)
        read_all_calculation_rules()
        self.__load_config(cfg)

    @classmethod
    def __load_config(cls, cfg):
        """
        Load all config fields that match current AppConfig class fields, all custom fields have to be loaded separately
        """
        for field in cfg:
            if hasattr(CalcruleSocialProtectionConfig, field):
                setattr(CalcruleSocialProtectionConfig, field, cfg[field])

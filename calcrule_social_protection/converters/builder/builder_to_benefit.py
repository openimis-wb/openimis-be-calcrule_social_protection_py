from payroll.models import BenefitConsumptionStatus


class BuilderToBenefitConverter:
    TYPE = None

    def to_benefit_obj(self, entity, amount, payment_plan, payment_cycle):
        benefit = {}
        self._build_individual(benefit, entity)
        self._build_amount(benefit, amount)
        self._build_date_dates(benefit, payment_plan, payment_cycle)
        self._build_type(benefit)
        self._build_status(benefit)
        return benefit

    def _build_individual(self, benefit, entity):
        pass

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

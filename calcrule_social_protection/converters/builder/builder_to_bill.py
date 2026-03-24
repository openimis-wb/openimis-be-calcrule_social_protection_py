from django.contrib.contenttypes.models import ContentType
from invoice.apps import InvoiceConfig
from invoice.models import Bill


class BuilderToBillConverter:
    TYPE = None

    def __init__(self):
        self._subject_type_id = None
        self._thirdparty_type_id = None

    def to_bill_obj(self, payment_plan, entity, amount, end_date, payment_cycle):
        bill = {'code': ''}
        self._build_subject(bill, entity)
        self._build_thirdparty(bill, payment_plan)
        self._build_price(bill, amount)
        self._build_terms(bill, payment_plan, entity, end_date)
        self._build_date_dates(bill, payment_plan, payment_cycle)
        self._build_currency(bill)
        self._build_status(bill)
        return bill

    def _build_subject(self, bill, entity):
        bill["subject_id"] = f"{entity.id}"
        if self._subject_type_id is None:
            self._subject_type_id = ContentType.objects.get_for_model(entity).id
        bill['subject_type_id'] = f"{self._subject_type_id}"

    def _build_thirdparty(self, bill, payment_plan):
        bill["thirdparty_id"] = f"{payment_plan.id}"
        if self._thirdparty_type_id is None:
            self._thirdparty_type_id = ContentType.objects.get_for_model(payment_plan).id
        bill['thirdparty_type_id'] = f"{self._thirdparty_type_id}"

    @classmethod
    def _build_price(cls, bill, amount):
        bill["amount_net"] = amount

    @classmethod
    def _build_date_dates(cls, bill, payment_plan, payment_cycle):
        bill["date_due"] = f"{payment_cycle.end_date}"
        bill["date_bill"] = f"{payment_cycle.start_date}"
        bill["date_valid_from"] = f"{payment_plan.benefit_plan.date_valid_from}"
        bill["date_valid_to"] = f"{payment_plan.benefit_plan.date_valid_to}"

    @classmethod
    def _build_currency(cls, bill):
        bill["currency_tp_code"] = InvoiceConfig.default_currency_code
        bill["currency_code"] = InvoiceConfig.default_currency_code

    @classmethod
    def _build_status(cls, bill):
        bill["status"] = Bill.Status.VALIDATED.value

    @classmethod
    def _build_terms(cls, bill, payment_plan, entity, end_date):
        pass

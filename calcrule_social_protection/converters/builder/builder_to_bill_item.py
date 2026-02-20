from django.contrib.contenttypes.models import ContentType


class BuilderToBillItemConverter:
    _line_type_id_cache = None

    @classmethod
    def to_bill_item_obj(cls, payment_plan, entity, amount):
        bill_line_item = {}
        cls._build_line_fk(bill_line_item, entity)
        cls._build_code(bill_line_item, entity)
        cls._build_date_dates(bill_line_item, payment_plan)
        cls._build_price(bill_line_item, amount)
        cls._build_quantity(bill_line_item)
        return bill_line_item

    @classmethod
    def _build_line_fk(cls, bill_line_item, entity):
        bill_line_item["line_id"] = f"{entity.id}"
        if cls._line_type_id_cache is None:
            cls._line_type_id_cache = ContentType.objects.get_for_model(entity).id
        bill_line_item['line_type_id'] = f"{cls._line_type_id_cache}"

    @classmethod
    def _build_quantity(cls, bill_line_item):
        bill_line_item["quantity"] = 1

    @classmethod
    def _build_price(cls, bill_line_item, amount):
        bill_line_item["amount_total"] = amount
        bill_line_item["unit_price"] = amount

    @classmethod
    def _build_code(cls, bill_line_item, entity):
        pass

    @classmethod
    def _build_date_dates(cls, bill_line_item, payment_plan):
        bill_line_item["date_valid_from"] = f"{payment_plan.benefit_plan.date_valid_from}"
        bill_line_item["date_valid_to"] = f"{payment_plan.benefit_plan.date_valid_to}"

import logging
import uuid as uuid_module
import decimal
from datetime import datetime as py_datetime

from django.db import transaction

from calcrule_social_protection.apps import CalcruleSocialProtectionConfig
from core.models import User
from core.utils import convert_to_python_value
from core.signals import register_service_signal
from invoice.models import Bill, BillItem
from invoice.services import BillService
from social_protection.models import BeneficiaryStatus
from payroll.models import (
    BenefitConsumption,
    BenefitAttachment,
    PayrollBenefitConsumption,
)
from payroll.services import BenefitConsumptionService, PayrollService
from tasks_management.apps import TasksManagementConfig
from tasks_management.models import Task
from tasks_management.services import TaskService

from calcrule_social_protection.strategies.benefit_package_strategy_interface import BenefitPackageStrategyInterface


logger = logging.getLogger(__name__)


class BaseBenefitPackageStrategy(BenefitPackageStrategyInterface):
    BATCH_CHUNK_SIZE = 2000

    @classmethod
    def check_calculation(cls, calculation, payment_plan):
        return calculation.uuid == str(payment_plan.calculation)

    @classmethod
    def calculate(cls, calculation, payment_plan, **kwargs):
        payroll = kwargs.get('payroll', None)
        beneficiaries = kwargs.get('beneficiaries_queryset', None)
        if beneficiaries is None:
            beneficiaries = cls.BENEFICIARY_OBJECT.objects.filter(
                benefit_plan=payment_plan.benefit_plan, status=BeneficiaryStatus.ACTIVE
            )

        payment_plan_parameters = payment_plan.json_ext
        user_id, start_date, end_date, payment_cycle = \
            calculation.get_payment_cycle_parameters(**kwargs)
        user = User.objects.filter(id=user_id).first()
        payment = float(payment_plan_parameters['calculation_rule']['fixed_batch'])
        limit = None
        if payment_plan_parameters['calculation_rule']['limit_per_single_transaction'] != "":
            limit = float(payment_plan_parameters['calculation_rule']['limit_per_single_transaction'])
        advanced_filters_criteria = payment_plan_parameters['advanced_criteria'] if 'advanced_criteria' in payment_plan_parameters else []

        beneficiaries_list = list(beneficiaries.select_related(*cls._get_select_related()))
        beneficiary_count = len(beneficiaries_list)
        converter = cls._init_converter(cls.CONVERTER, beneficiary_count, payroll)
        converter_benefit = cls._init_converter(cls.CONVERTER_BENEFIT, beneficiary_count, payroll)
        cls._prefetch_converter_data(converter_benefit, beneficiaries_list)

        criteria_match_sets = cls._precompute_criteria_matches(
            beneficiaries_list, advanced_filters_criteria
        )

        batch_bill_results = []
        batch_benefit_results = []
        progress_step = max(beneficiary_count // 10, 10) if beneficiary_count >= 10 else 0

        for i, beneficiary in enumerate(beneficiaries_list):
            calculated_payment, is_exceed = cls._calculate_payment_from_precomputed(
                beneficiary, advanced_filters_criteria, criteria_match_sets, payment, limit
            )

            additional_params = {
                f"{cls.BENEFICIARY_TYPE}": beneficiary,
                "amount": calculated_payment,
                "user": user,
                "end_date": end_date,
                "payment_cycle": payment_cycle,
                "payroll": payroll,
                "converter": converter,
                "converter_benefit": converter_benefit,
            }

            if is_exceed:
                calculation.run_convert(
                    payment_plan,
                    is_exceed_limit=True,
                    **additional_params
                )
            else:
                convert_results, convert_results_benefit = cls._collect_convert_results(
                    calculation, payment_plan, **additional_params
                )
                batch_bill_results.append(convert_results)
                batch_benefit_results.append(convert_results_benefit)

            if len(batch_bill_results) >= cls.BATCH_CHUNK_SIZE:
                cls.create_and_save_business_entities_batch(
                    batch_bill_results,
                    batch_benefit_results,
                    payroll.id if payroll else None,
                    user
                )
                batch_bill_results = []
                batch_benefit_results = []

            if progress_step and (i + 1) % progress_step == 0:
                if payroll:
                    if payroll.json_ext is None:
                        payroll.json_ext = {}
                    payroll.json_ext['progress'] = int((i + 1) * 100 / beneficiary_count)
                    payroll.save(username=user.login_name)

        if batch_bill_results:
            cls.create_and_save_business_entities_batch(
                batch_bill_results,
                batch_benefit_results,
                payroll.id if payroll else None,
                user
            )

        return "Calculation and transformation into bills completed successfully."

    @classmethod
    def _collect_convert_results(cls, calculation, payment_plan, **kwargs):
        """Collect convert results for batch creation. Subclasses override to resolve
        entity from their beneficiary type key and set converter_item.
        """
        entity = kwargs.get('entity', None)
        amount = kwargs.get('amount', None)
        end_date = kwargs.get('end_date', None)
        converter = kwargs.get('converter')
        converter_item = kwargs.get('converter_item')
        converter_benefit = kwargs.get('converter_benefit')
        payment_cycle = kwargs.get('payment_cycle')
        convert_results = cls._convert_entity_to_bill(
            converter, converter_item, payment_plan, entity, amount, end_date, payment_cycle
        )
        convert_results['user'] = kwargs.get('user', None)
        convert_results_benefit = cls._convert_entity_to_benefit(
            converter_benefit, payment_plan, entity, amount, payment_cycle
        )
        return convert_results, convert_results_benefit

    @classmethod
    def _precompute_criteria_matches(cls, beneficiaries, advanced_filters_criteria):
        """Return a list of ID sets, one per criterion, of matching beneficiaries.
        Replaces M*N per-row exists() queries with M batch queries.
        """
        if not advanced_filters_criteria:
            return []

        criteria_match_sets = []
        beneficiary_ids = [b.id for b in beneficiaries]
        for criterion in advanced_filters_criteria:
            condition = criterion['custom_filter_condition']
            lookup_path, parsed_condition_value = cls._parse_condition(condition)
            matching_ids = set(
                cls.BENEFICIARY_OBJECT.objects.filter(
                    id__in=beneficiary_ids,
                    **{f'json_ext__{lookup_path}': parsed_condition_value}
                ).values_list('id', flat=True)
            )
            criteria_match_sets.append(matching_ids)

        return criteria_match_sets

    @classmethod
    def _calculate_payment_from_precomputed(
            cls, beneficiary, advanced_filters_criteria, criteria_match_sets, payment, limit
    ):
        for i, criterion in enumerate(advanced_filters_criteria):
            calculated_amount = float(criterion['amount'])
            if beneficiary.id in criteria_match_sets[i]:
                payment += calculated_amount
        is_exceed = (payment > limit) if limit else False
        return payment, is_exceed

    @classmethod
    def _does_beneficiary_meet_condition(cls, beneficiary, condition):
        lookup_path, parsed_condition_value = cls._parse_condition(condition)
        json_key = lookup_path.split('__')[0]
        if json_key in beneficiary.json_ext:
            return cls.BENEFICIARY_OBJECT.objects.filter(
                id=beneficiary.id, **{f'json_ext__{lookup_path}': parsed_condition_value}
            ).exists()
        return False

    @staticmethod
    def _parse_condition(condition):
        """Parse 'field__type=value' into (lookup_path, parsed_value).
        Type-hint suffixes (integer, string, numeric, boolean, date) are stripped.
        """
        condition_key, condition_value = condition.split("=", 1)
        parsed_value = convert_to_python_value(condition_value)
        if '__' in condition_key:
            field, value_type = condition_key.rsplit('__', 1)
            lookup_path = field if value_type in ('integer', 'string', 'numeric', 'boolean', 'date') else condition_key
        else:
            lookup_path = condition_key
        return lookup_path, parsed_value

    @classmethod
    def _init_converter(cls, converter_cls, count, payroll):
        if converter_cls is None:
            return None
        instance = converter_cls()
        return instance

    @classmethod
    def _get_select_related(cls):
        return []

    @classmethod
    def _prefetch_converter_data(cls, converter_benefit, beneficiaries):
        pass

    @classmethod
    def convert(cls, payment_plan, **kwargs):
        entity = kwargs.get('entity', None)
        amount = kwargs.get('amount', None)
        payroll = kwargs.get('payroll', None)
        end_date = kwargs.get('end_date', None)
        converter = kwargs.get('converter')
        converter_item = kwargs.get('converter_item')
        converter_benefit = kwargs.get('converter_benefit')
        payment_cycle = kwargs.get('payment_cycle')
        is_exceed_limit = kwargs.get('is_exceed_limit', False)
        convert_results = cls._convert_entity_to_bill(
            converter, converter_item, payment_plan, entity, amount, end_date, payment_cycle
        )
        convert_results['user'] = kwargs.get('user', None)
        convert_results_benefit = cls._convert_entity_to_benefit(
            converter_benefit, payment_plan, entity, amount, payment_cycle
        )
        user = convert_results['user']
        if not is_exceed_limit:
            cls.create_and_save_business_entities(
                convert_results,
                convert_results_benefit,
                payroll.id,
                user
            )
        else:
            cls.create_task_after_exceeding_limit(
                convert_results=convert_results,
                convert_results_benefit=convert_results_benefit,
                payroll=payroll
            )

    @classmethod
    def create_and_save_business_entities(
            cls, convert_results, convert_results_benefit, payroll_id, user, bill_status=None
    ):
        if bill_status is not None:
            convert_results['bill_data']['status'] = bill_status
        result_bill_creation = BillService.bill_create(convert_results=convert_results)
        if result_bill_creation["success"]:
            bill_id = result_bill_creation['data']['id']
            benefit_service = BenefitConsumptionService(user)
            benefit_result = benefit_service.create(convert_results_benefit['benefit_data'])
            if benefit_result["success"]:
                # create benefit attachemnts - attach bill to benefit
                bill_queryset = Bill.objects.filter(id__in=[bill_id])
                benefit_id = benefit_result['data']['id']
                benefit_service.create_or_update_benefit_attachment(bill_queryset, benefit_id)
                if payroll_id:
                    payroll_service = PayrollService(user=user)
                    payroll_service.attach_benefit_to_payroll(payroll_id, benefit_id)
        return result_bill_creation

    @classmethod
    @transaction.atomic
    def create_and_save_business_entities_batch(
            cls, batch_bill_results, batch_benefit_results, payroll_id, user
    ):
        """Bulk create Bills, BillItems, BenefitConsumptions, BenefitAttachments,
        and PayrollBenefitConsumptions in a single transaction.
        """
        now = py_datetime.now()

        bill_instances = []
        bill_item_instances = []
        benefit_instances = []
        attachment_instances = []
        payroll_benefit_instances = []

        for bill_result, benefit_result in zip(
            batch_bill_results, batch_benefit_results
        ):
            bill_data = bill_result['bill_data']
            bill_line_items = bill_result['bill_data_line']
            benefit_data = benefit_result['benefit_data']

            if not benefit_data.get('individual_id'):
                logger.warning(
                    f"Skipping batch entry for payroll {payroll_id}: "
                    f"no individual_id in benefit_data (bill code: {bill_data.get('code', 'unknown')})"
                )
                continue

            bill_uuid = uuid_module.uuid4()
            benefit_uuid = uuid_module.uuid4()

            bill = Bill(
                id=bill_uuid,
                subject_type_id=bill_data.get('subject_type_id'),
                subject_id=bill_data.get('subject_id'),
                thirdparty_type_id=bill_data.get('thirdparty_type_id'),
                thirdparty_id=bill_data.get('thirdparty_id'),
                code=bill_data.get('code', ''),
                code_tp=bill_data.get('code_tp'),
                code_ext=bill_data.get('code_ext'),
                date_due=bill_data.get('date_due'),
                date_bill=bill_data.get('date_bill'),
                date_valid_from=bill_data.get('date_valid_from'),
                date_valid_to=bill_data.get('date_valid_to'),
                currency_tp_code=bill_data.get('currency_tp_code'),
                currency_code=bill_data.get('currency_code'),
                status=bill_data.get('status', Bill.Status.VALIDATED),
                terms=bill_data.get('terms'),
                note=bill_data.get('note'),
                amount_net=cls._sum_line_items(bill_line_items, 'amount_total'),
                amount_total=cls._sum_line_items(bill_line_items, 'amount_total'),
                amount_discount=cls._sum_line_items(bill_line_items, 'discount'),
                user_created=user,
                user_updated=user,
                date_created=now,
                date_updated=now,
                version=1,
            )
            bill_instances.append(bill)

            for line_item_data in bill_line_items:
                bill_item = BillItem(
                    id=uuid_module.uuid4(),
                    bill_id=bill_uuid,
                    line_type_id=line_item_data.get('line_type_id'),
                    line_id=line_item_data.get('line_id'),
                    code=line_item_data.get('code', ''),
                    quantity=line_item_data.get('quantity', 1),
                    unit_price=line_item_data.get('unit_price', 0),
                    amount_total=line_item_data.get('amount_total', 0),
                    amount_net=line_item_data.get('amount_total', 0),
                    discount=line_item_data.get('discount', 0),
                    deduction=line_item_data.get('deduction', 0),
                    date_valid_from=line_item_data.get('date_valid_from'),
                    date_valid_to=line_item_data.get('date_valid_to'),
                    user_created=user,
                    user_updated=user,
                    date_created=now,
                    date_updated=now,
                    version=1,
                )
                bill_item_instances.append(bill_item)

            benefit = BenefitConsumption(
                id=benefit_uuid,
                individual_id=benefit_data.get('individual_id'),
                code=benefit_data.get('code', ''),
                date_due=benefit_data.get('date_due'),
                amount=benefit_data.get('amount'),
                type=benefit_data.get('type'),
                status=benefit_data.get('status'),
                date_valid_from=benefit_data.get('date_valid_from'),
                date_valid_to=benefit_data.get('date_valid_to'),
                user_created=user,
                user_updated=user,
                date_created=now,
                date_updated=now,
                version=1,
            )
            benefit_instances.append(benefit)

            attachment = BenefitAttachment(
                id=uuid_module.uuid4(),
                benefit_id=benefit_uuid,
                bill_id=bill_uuid,
                user_created=user,
                user_updated=user,
                date_created=now,
                date_updated=now,
                version=1,
            )
            attachment_instances.append(attachment)

            if payroll_id:
                pbc = PayrollBenefitConsumption(
                    id=uuid_module.uuid4(),
                    payroll_id=payroll_id,
                    benefit_id=benefit_uuid,
                    user_created=user,
                    user_updated=user,
                    date_created=now,
                    date_updated=now,
                    version=1,
                )
                payroll_benefit_instances.append(pbc)

        batch_size = len(bill_instances)
        logger.info(
            f"Bulk creating {batch_size} entities for payroll {payroll_id}: "
            f"{len(bill_instances)} bills, {len(bill_item_instances)} bill items, "
            f"{len(benefit_instances)} benefits, {len(attachment_instances)} attachments, "
            f"{len(payroll_benefit_instances)} payroll-benefit links"
        )

        try:
            BillService.bulk_create_bills(bill_instances)
            BillService.bulk_create_bill_items(bill_item_instances)

            benefit_service = BenefitConsumptionService(user)
            benefit_service.bulk_create(benefit_instances)
            benefit_service.bulk_create_attachments(attachment_instances)

            if payroll_benefit_instances:
                payroll_service = PayrollService(user=user)
                payroll_service.bulk_attach_benefits(payroll_benefit_instances)

            # Re-fetch to get trigger-assigned codes, then write history.
            bill_ids = [b.id for b in bill_instances]
            bill_item_ids = [bi.id for bi in bill_item_instances]
            benefit_ids = [b.id for b in benefit_instances]
            attachment_ids = [a.id for a in attachment_instances]

            persisted_bills = list(Bill.objects.filter(id__in=bill_ids))
            persisted_bill_items = list(BillItem.objects.filter(id__in=bill_item_ids))
            persisted_benefits = list(BenefitConsumption.objects.filter(id__in=benefit_ids))
            persisted_attachments = list(BenefitAttachment.objects.filter(id__in=attachment_ids))

            cls._bulk_write_creation_history(persisted_bills, Bill, user, now)
            cls._bulk_write_creation_history(persisted_bill_items, BillItem, user, now)
            cls._bulk_write_creation_history(persisted_benefits, BenefitConsumption, user, now)
            cls._bulk_write_creation_history(persisted_attachments, BenefitAttachment, user, now)

            if payroll_benefit_instances:
                pbc_ids = [p.id for p in payroll_benefit_instances]
                persisted_pbcs = list(PayrollBenefitConsumption.objects.filter(id__in=pbc_ids))
                cls._bulk_write_creation_history(persisted_pbcs, PayrollBenefitConsumption, user, now)

        except Exception:
            logger.error(
                f"Failed to bulk create entities for payroll {payroll_id} "
                f"(batch size: {batch_size})",
                exc_info=True,
            )
            raise

        logger.info(f"Bulk creation complete for payroll {payroll_id} ({batch_size} items)")

    @staticmethod
    def _sum_line_items(line_items, field):
        return sum(
            decimal.Decimal(str(item.get(field, 0)))
            for item in line_items
        )

    @staticmethod
    def _bulk_write_creation_history(instances, model_class, user, history_date):
        """Write simple-history creation records for bulk_create'd entities."""
        if not instances:
            return

        HistoricalModel = model_class.history.model
        concrete_field_names = [field.attname for field in model_class._meta.concrete_fields]

        historical_records = [
            HistoricalModel(
                history_type='+',
                history_date=history_date,
                history_user=user,
                history_change_reason=None,
                **{name: getattr(instance, name) for name in concrete_field_names}
            )
            for instance in instances
        ]
        HistoricalModel.objects.bulk_create(historical_records, batch_size=500)

    @classmethod
    def _convert_entity_to_bill(
        cls, converter, converter_item, payment_plan, entity, amount, end_date, payment_cycle
    ):
        bill = converter.to_bill_obj(
            payment_plan, entity, amount, end_date, payment_cycle
        )
        bill_line_items = [
            converter_item.to_bill_item_obj(payment_plan, entity, amount)
        ]
        return {
            'bill_data': bill,
            'bill_data_line': bill_line_items,
            'type_conversion': 'beneficiary - bill'
        }

    @classmethod
    def _convert_entity_to_benefit(
            cls, converter_benefit, payment_plan, entity, amount, payment_cycle
    ):
        benefit = converter_benefit.to_benefit_obj(entity, amount, payment_plan, payment_cycle)
        return {
            'benefit_data': benefit,
            'type_conversion': 'beneficiary - benefit'
        }

    @classmethod
    @transaction.atomic
    @register_service_signal('calcrule_social_protection.create_task')
    def create_task_after_exceeding_limit(cls, convert_results, convert_results_benefit, payroll):
        business_status = {"code": convert_results['bill_data'].get('code', '')}
        user = convert_results.pop('user')
        convert_results['benefit'] = convert_results_benefit
        convert_results['payroll_id'] = f"{payroll.id}"
        TaskService(user).create({
            'source': 'calcrule_social_protection',
            'entity': payroll,
            'status': Task.Status.RECEIVED,
            'executor_action_event': TasksManagementConfig.default_executor_event,
            'business_event': CalcruleSocialProtectionConfig.calculate_business_event,
            'business_status': business_status,
            'data': f"{convert_results}"
        })

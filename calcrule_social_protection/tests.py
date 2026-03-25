from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from core.test_helpers import LogInHelper
from social_protection.models import Beneficiary, BenefitPlan, BeneficiaryStatus
from individual.models import Individual
from invoice.models import Bill, BillItem
from payroll.models import (
    Payroll, BenefitConsumption, BenefitAttachment,
    PayrollBenefitConsumption, BenefitConsumptionStatus
)
from contribution_plan.models import PaymentPlan
from payment_cycle.models import PaymentCycle
from calcrule_social_protection.strategies.benefit_package_individual_strategy import IndividualBenefitPackageStrategy
from calcrule_social_protection.calculation_rule import SocialProtectionCalculationRule


class BenefitPackageStrategyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = LogInHelper().get_or_create_user_api(username='admin_bulk')

        bp = BenefitPlan(name="Test BP", date_valid_from="2020-01-01")
        bp.save(user=cls.user)
        cls.benefit_plan = bp

        i1 = Individual(first_name="Individual", last_name="I1", dob="1990-01-01")
        i1.save(user=cls.user)
        i1.json_ext = {"able_bodied": True}
        i1.save(user=cls.user)
        cls.i1 = i1

        b1 = Beneficiary(
            individual=cls.i1,
            benefit_plan=cls.benefit_plan,
            status=BeneficiaryStatus.ACTIVE,
            json_ext=cls.i1.json_ext,
        )
        b1.save(user=cls.user)
        cls.b1 = b1

        i2 = Individual(first_name="Individual", last_name="I2", dob="1990-01-01")
        i2.save(user=cls.user)
        i2.json_ext = {"able_bodied": False}
        i2.save(user=cls.user)
        cls.i2 = i2

        b2 = Beneficiary(
            individual=cls.i2,
            benefit_plan=cls.benefit_plan,
            status=BeneficiaryStatus.ACTIVE,
            json_ext=cls.i2.json_ext,
        )
        b2.save(user=cls.user)
        cls.b2 = b2

        pp = PaymentPlan(
            code="PP1",
            name="Payment Plan 1",
            benefit_plan=cls.benefit_plan,
            calculation=SocialProtectionCalculationRule.uuid,
            periodicity=1,
        )
        pp.save(user=cls.user)
        cls.payment_plan = pp

        pc = PaymentCycle(
            code="PC1",
            start_date="2020-01-01",
            end_date="2020-01-31",
            type=ContentType.objects.get_for_model(BenefitPlan),
        )
        pc.save(user=cls.user)
        cls.payment_cycle = pc

    def test_create_and_save_business_entities_batch(self):
        """Verify that the batch creation method persists all related entities correctly."""
        payroll = Payroll(name="BatchPayroll")
        payroll.save(user=self.user)

        batch_bill_results = [{
            'bill_data': {
                'code': f"BATCH_BILL_{i}",
                'subject_id': self.b1.id,
                'subject_type_id': ContentType.objects.get_for_model(Beneficiary).id,
                'amount_total': 100.0,
                'date_valid_from': "2020-01-01",
                'date_valid_to': "2020-12-31",
                'date_bill': "2020-01-01",
                'date_due': "2020-12-31",
                'currency_tp_code': "USD",
                'currency_code': "USD",
                'status': Bill.Status.VALIDATED
            },
            'bill_data_line': [{
                'amount_total': 100.0,
                'code': f"LINE_{i}",
                'date_valid_from': "2020-01-01",
                'date_valid_to': "2020-12-31",
            }],
            'user': self.user
        } for i in range(2)]

        batch_benefit_results = [{
            'benefit_data': {
                'individual_id': self.i1.id,
                'code': f"BATCH_BENEFIT_{i}",
                'beneficiary_id': self.b1.id,
                'amount': 100.0,
                'status': BenefitConsumptionStatus.ACCEPTED,
                'date_valid_from': "2020-01-01",
                'date_valid_to': "2020-12-31",
            }
        } for i in range(2)]

        IndividualBenefitPackageStrategy.create_and_save_business_entities_batch(
            batch_bill_results, batch_benefit_results, payroll.id, self.user
        )

        self.assertTrue(Bill.objects.filter(code='BATCH_BILL_0').exists())
        self.assertTrue(Bill.objects.filter(code='BATCH_BILL_1').exists())
        self.assertTrue(BillItem.objects.filter(code='LINE_1').exists())
        self.assertTrue(BenefitConsumption.objects.filter(code='BATCH_BENEFIT_1').exists())
        self.assertTrue(BenefitAttachment.objects.filter(
            benefit__code='BATCH_BENEFIT_1', bill__code='BATCH_BILL_1'
        ).exists())
        self.assertTrue(PayrollBenefitConsumption.objects.filter(
            payroll=payroll, benefit__code='BATCH_BENEFIT_1'
        ).exists())

    def test_db_default_code_generation(self):
        """Verify that DB sequences generate unique codes when no code is provided."""
        bc1 = BenefitConsumption(individual=self.i1, amount=50, status=BenefitConsumptionStatus.ACCEPTED, code='')
        bc1.save(user=self.user)
        bc1.refresh_from_db()

        bc2 = BenefitConsumption(individual=self.i2, amount=75, status=BenefitConsumptionStatus.ACCEPTED, code='')
        bc2.save(user=self.user)
        bc2.refresh_from_db()

        self.assertTrue(bc1.code.startswith('BEN-'), f"Expected BEN- prefix, got: {bc1.code}")
        self.assertTrue(bc2.code.startswith('BEN-'), f"Expected BEN- prefix, got: {bc2.code}")
        self.assertNotEqual(bc1.code, bc2.code, "Sequential codes must be unique")

        beneficiary_ct = ContentType.objects.get_for_model(Beneficiary)
        bill1 = Bill(
            subject_id=str(self.b1.id),
            subject_type=beneficiary_ct,
            code='',
            amount_net=100,
            status=Bill.Status.VALIDATED,
            currency_tp_code='USD',
            currency_code='USD',
        )
        bill1.save(user=self.user)
        bill1.refresh_from_db()

        bill2 = Bill(
            subject_id=str(self.b2.id),
            subject_type=beneficiary_ct,
            code='',
            amount_net=200,
            status=Bill.Status.VALIDATED,
            currency_tp_code='USD',
            currency_code='USD',
        )
        bill2.save(user=self.user)
        bill2.refresh_from_db()

        self.assertTrue(bill1.code.startswith('BIL-'), f"Expected BIL- prefix, got: {bill1.code}")
        self.assertTrue(bill2.code.startswith('BIL-'), f"Expected BIL- prefix, got: {bill2.code}")
        self.assertNotEqual(bill1.code, bill2.code, "Sequential bill codes must be unique")

    def test_bulk_create_triggers_assign_codes(self):
        """Verify DB triggers assign codes to bulk-created Bills and BenefitConsumptions."""
        payroll = Payroll(name="TriggerCodePayroll")
        payroll.save(user=self.user)

        batch_bill_results = [{
            'bill_data': {
                'code': '',  # Empty — DB trigger should assign BIL-YY-XXXXXXXXXX
                'subject_id': self.b1.id,
                'subject_type_id': ContentType.objects.get_for_model(Beneficiary).id,
                'amount_total': 50.0,
                'date_valid_from': "2020-01-01",
                'date_valid_to': "2020-12-31",
                'date_bill': "2020-01-01",
                'currency_tp_code': "USD",
                'currency_code': "USD",
                'status': Bill.Status.VALIDATED
            },
            'bill_data_line': [{'amount_total': 50.0, 'date_valid_from': "2020-01-01", 'date_valid_to': "2020-12-31"}],
            'user': self.user
        }]
        batch_benefit_results = [{
            'benefit_data': {
                'individual_id': self.i1.id,
                'code': '',  # Empty — DB trigger should assign BEN-YY-XXXXXXXXXX
                'amount': 50.0,
                'status': BenefitConsumptionStatus.ACCEPTED,
                'date_valid_from': "2020-01-01",
                'date_valid_to': "2020-12-31",
            }
        }]

        IndividualBenefitPackageStrategy.create_and_save_business_entities_batch(
            batch_bill_results, batch_benefit_results, payroll.id, self.user
        )

        benefit = BenefitConsumption.objects.filter(
            payrollbenefitconsumption__payroll=payroll, is_deleted=False
        ).first()
        self.assertIsNotNone(benefit)
        self.assertTrue(benefit.code.startswith('BEN-'), f"Expected BEN- prefix from trigger, got: {benefit.code!r}")

        bill = Bill.objects.filter(
            benefitattachment__benefit=benefit, is_deleted=False
        ).first()
        self.assertIsNotNone(bill)
        self.assertTrue(bill.code.startswith('BIL-'), f"Expected BIL- prefix from trigger, got: {bill.code!r}")

    def test_calculate_payment_exceed_limit(self):
        """Verify _calculate_payment_from_precomputed correctly identifies limit exceedances
        and that _precompute_criteria_matches correctly partitions beneficiaries.
        """
        advanced_criteria = [
            {'custom_filter_condition': 'able_bodied__boolean=True', 'amount': '200'},
        ]
        criteria_match_sets = IndividualBenefitPackageStrategy._precompute_criteria_matches(
            [self.b1, self.b2], advanced_criteria
        )

        self.assertEqual(len(criteria_match_sets), 1)
        self.assertIn(self.b1.id, criteria_match_sets[0], "b1 (able_bodied=True) must match criterion")
        self.assertNotIn(self.b2.id, criteria_match_sets[0], "b2 (able_bodied=False) must not match criterion")

        # b1: base 100 + criteria 200 = 300, limit 150 → exceeds
        payment_b1, is_exceed_b1 = IndividualBenefitPackageStrategy._calculate_payment_from_precomputed(
            self.b1, advanced_criteria, criteria_match_sets, 100.0, 150.0
        )
        self.assertEqual(payment_b1, 300.0)
        self.assertTrue(is_exceed_b1, "b1 should exceed limit of 150 (300 > 150)")

        # b2: base 100 only = 100, limit 150 → does not exceed
        payment_b2, is_exceed_b2 = IndividualBenefitPackageStrategy._calculate_payment_from_precomputed(
            self.b2, advanced_criteria, criteria_match_sets, 100.0, 150.0
        )
        self.assertEqual(payment_b2, 100.0)
        self.assertFalse(is_exceed_b2, "b2 should not exceed limit (100 < 150)")


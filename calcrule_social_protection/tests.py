import decimal
import uuid
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from core.test_helpers import LogInHelper
from social_protection.models import Beneficiary, BenefitPlan, Project, BeneficiaryStatus
from individual.models import Individual
from invoice.models import Bill, BillItem
from payroll.models import (
    Payroll, BenefitConsumption, BenefitAttachment, 
    PayrollBenefitConsumption, BenefitConsumptionStatus
)
from contribution_plan.models import PaymentPlan
from payment_cycle.models import PaymentCycle
from calcrule_social_protection.strategies.benefit_package_individual_strategy import IndividualBenefitPackageStrategy
from calcrule_social_protection.converters.builder.builder_to_bill import BuilderToBillConverter

class BenefitPackageStrategyTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = LogInHelper().get_or_create_user_api(username='admin_bulk')
            
        cls.benefit_plan = BenefitPlan.objects.create(
            name="Test BP", 
            date_valid_from="2020-01-01",
            user_created=cls.user
        )
        
        # Create beneficiaries with specific json_ext for criteria testing
        cls.i1 = Individual.objects.create(first_name="Individual", last_name="I1", dob="1990-01-01", user_created=cls.user)
        cls.i1.json_ext = {"able_bodied": True}
        cls.i1.save()
        cls.b1 = Beneficiary.objects.create(
            individual=cls.i1, 
            benefit_plan=cls.benefit_plan, 
            status=BeneficiaryStatus.ACTIVE,
            json_ext=cls.i1.json_ext,
            user_created=cls.user
        )
        
        cls.i2 = Individual.objects.create(first_name="Individual", last_name="I2", dob="1990-01-01", user_created=cls.user)
        cls.i2.json_ext = {"able_bodied": False}
        cls.i2.save()
        cls.b2 = Beneficiary.objects.create(
            individual=cls.i2, 
            benefit_plan=cls.benefit_plan, 
            status=BeneficiaryStatus.ACTIVE,
            json_ext=cls.i2.json_ext,
            user_created=cls.user
        )

        cls.payment_plan = PaymentPlan.objects.create(
            code="PP1", 
            name="Payment Plan 1", 
            benefit_plan=cls.benefit_plan,
            calculation="32d96b58-898a-460a-b357-5fd4b95cd87c",
            periodicity=1,
            user_created=cls.user
        )
        cls.payment_cycle = PaymentCycle.objects.create(
            code="PC1", 
            start_date="2020-01-01", 
            end_date="2020-01-31",
            type=ContentType.objects.get_for_model(BenefitPlan),
            user_created=cls.user
        )

    def test_precompute_criteria_matches(self):
        """Verify that criteria match pre-computation avoids per-row queries."""
        criteria = [
            {"custom_filter_condition": "able_bodied__boolean=True", "amount": 10},
            {"custom_filter_condition": "able_bodied__boolean=False", "amount": 20}
        ]
        beneficiaries = Beneficiary.objects.all()
        
        match_sets = IndividualBenefitPackageStrategy._precompute_criteria_matches(beneficiaries, criteria)
        
        self.assertEqual(len(match_sets), 2)
        self.assertIn(self.b1.id, match_sets[0])
        self.assertNotIn(self.b2.id, match_sets[0])
        self.assertIn(self.b2.id, match_sets[1])
        self.assertNotIn(self.b1.id, match_sets[1])




    def test_create_and_save_business_entities_batch(self):
        """Verify that the batch creation method persists all related entities correctly."""
        payroll = Payroll.objects.create(
            name="BatchPayroll",
            user_created=self.user,
            user_updated=self.user
        )
        
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
        
        # Verify persistence
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

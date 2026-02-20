from calcrule_social_protection.converters.builder import BuilderToBenefitConverter


class BeneficiaryToBenefitConverter(BuilderToBenefitConverter):

    def _build_individual(self, benefit, entity):
        benefit["individual_id"] = f"{entity.individual.id}"

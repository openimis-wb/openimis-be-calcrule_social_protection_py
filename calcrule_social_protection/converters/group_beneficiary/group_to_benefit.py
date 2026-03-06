import logging

from calcrule_social_protection.converters.builder import BuilderToBenefitConverter
from individual.models import GroupIndividual

logger = logging.getLogger(__name__)


class GroupToBenefitConverter(BuilderToBenefitConverter):

    RECIPIENT_LOOKUPS = [
        {"recipient_type": GroupIndividual.RecipientType.PRIMARY.value},
        {"role": GroupIndividual.Role.HEAD.value},
        {},
    ]

    def __init__(self):
        super().__init__()
        self._recipient_cache = None

    def prefetch_recipients(self, beneficiaries):
        """Prefetch all group members for all beneficiaries in a single query,
        then build a group_id -> best individual_id lookup.

        The priority is: PRIMARY recipient_type > HEAD role > any member.
        """
        group_ids = [b.group_id for b in beneficiaries]
        if not group_ids:
            self._recipient_cache = {}
            return

        members = GroupIndividual.objects.filter(
            group_id__in=group_ids,
            is_deleted=False,
        ).values_list('group_id', 'recipient_type', 'role', 'individual_id')

        group_members = {}
        for group_id, recipient_type, role, individual_id in members:
            group_members.setdefault(group_id, []).append(
                (recipient_type, role, individual_id)
            )

        primary_type = GroupIndividual.RecipientType.PRIMARY.value
        head_role = GroupIndividual.Role.HEAD.value
        cache = {}
        for group_id, member_list in group_members.items():
            chosen = (
                next((ind_id for rt, _, ind_id in member_list if rt == primary_type), None)
                or next((ind_id for _, rl, ind_id in member_list if rl == head_role), None)
                or (member_list[0][2] if member_list else None)
            )
            if chosen is not None:
                cache[group_id] = chosen

        self._recipient_cache = cache

    def _build_individual(self, benefit, entity):
        if self._recipient_cache is not None:
            individual_id = self._recipient_cache.get(entity.group_id)
            if individual_id:
                benefit["individual_id"] = f"{individual_id}"
            else:
                logger.warning(
                    f"No active recipient found for group {entity.group_id} "
                    f"(beneficiary {entity.id}); individual_id will be unset."
                )
            return

        # Fallback to per-entity lookup if prefetch wasn't called
        for lookup in self.RECIPIENT_LOOKUPS:
            recipient = GroupIndividual.objects.filter(
                group_id=entity.group.id,
                is_deleted=False,
                **lookup
            ).first()
            if recipient:
                benefit["individual_id"] = f"{recipient.individual.id}"
                return

        logger.warning(
            f"No active recipient found for group {entity.group_id} "
            f"(beneficiary {entity.id}) in fallback lookup; individual_id will be unset."
        )

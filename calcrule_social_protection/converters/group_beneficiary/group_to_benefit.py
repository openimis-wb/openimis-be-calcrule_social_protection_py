from calcrule_social_protection.converters.builder import BuilderToBenefitConverter
from individual.models import GroupIndividual


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

        # Build per-group buckets
        group_members = {}
        for group_id, recipient_type, role, individual_id in members:
            group_members.setdefault(group_id, []).append(
                (recipient_type, role, individual_id)
            )

        # Pick best recipient per group using the same priority as RECIPIENT_LOOKUPS
        primary_type = GroupIndividual.RecipientType.PRIMARY.value
        head_role = GroupIndividual.Role.HEAD.value
        cache = {}
        for group_id, member_list in group_members.items():
            chosen = None
            # Priority 1: PRIMARY recipient
            for rt, rl, ind_id in member_list:
                if rt == primary_type:
                    chosen = ind_id
                    break
            # Priority 2: HEAD role
            if chosen is None:
                for rt, rl, ind_id in member_list:
                    if rl == head_role:
                        chosen = ind_id
                        break
            # Priority 3: any member
            if chosen is None and member_list:
                chosen = member_list[0][2]
            if chosen is not None:
                cache[group_id] = chosen

        self._recipient_cache = cache

    def _build_individual(self, benefit, entity):
        if self._recipient_cache is not None:
            individual_id = self._recipient_cache.get(entity.group_id)
            if individual_id:
                benefit["individual_id"] = f"{individual_id}"
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

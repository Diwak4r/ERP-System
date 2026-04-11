from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ProductionEntry, DailyLedger, ProcessFlowEdge, DayLock

@receiver(post_save, sender=ProductionEntry)
@receiver(post_delete, sender=ProductionEntry)
def update_ledger_on_production_entry(sender, instance, **kwargs):
    # Update current section output
    ledger, _ = DailyLedger.objects.get_or_create(
        date=instance.entry_date,
        section=instance.section,
        item=instance.item
    )

    from django.db.models import Sum
    total_output = ProductionEntry.objects.filter(
        entry_date=instance.entry_date,
        section=instance.section,
        item=instance.item
    ).aggregate(total=Sum('actual_qty'))['total'] or 0

    ledger.output = total_output
    ledger.recompute()
    ledger.save()

    # Propagate to next sections
    edges = ProcessFlowEdge.objects.filter(from_section=instance.section, item=instance.item)
    for edge in edges:
        from datetime import timedelta
        target_date = instance.entry_date + timedelta(days=edge.lead_days)
        next_ledger, _ = DailyLedger.objects.get_or_create(
            date=target_date,
            section=edge.to_section,
            item=instance.item
        )
        # Recalculate received_from_prev for the downstream ledger
        # We need to sum the outputs of all incoming edges for that target date, item and section.
        total_received = 0
        incoming_edges = ProcessFlowEdge.objects.filter(to_section=edge.to_section, item=instance.item)
        for inc_edge in incoming_edges:
            source_date = target_date - timedelta(days=inc_edge.lead_days)
            source_ledger = DailyLedger.objects.filter(
                date=source_date,
                section=inc_edge.from_section,
                item=instance.item
            ).first()
            if source_ledger:
                total_received += source_ledger.output

        next_ledger.received_from_prev = total_received
        next_ledger.recompute()
        next_ledger.save()

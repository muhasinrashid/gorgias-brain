from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.tickets.models import Qualification, Ticket
from apps.tickets.services.qualification import (
    apply_qualification_to_ticket,
    flag_autoresponder_messages,
)


class Command(BaseCommand):
    help = "Re-run ticket qualification. backends: rules | hybrid | llm"

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", default="")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--backend",
            choices=["rules", "hybrid", "llm"],
            default="rules",
            help="rules=regex only; hybrid=rules then LLM on leftovers; llm=LLM every ticket",
        )
        parser.add_argument(
            "--only-unclear",
            action="store_true",
            help="Only process tickets currently marked UNCLEAR (good for hybrid top-up).",
        )

    def handle(self, *args, **options):
        backend = options["backend"]
        qs = Ticket.objects.all().order_by("id")
        if options["team_slug"]:
            qs = qs.filter(team__slug=options["team_slug"])
        if options["only_unclear"]:
            qs = qs.filter(qualification=Qualification.UNCLEAR)
        if options["limit"]:
            qs = qs[: options["limit"]]

        counts: dict[str, int] = {}
        llm_calls = 0
        n = 0
        for ticket in qs.iterator():
            before = ticket.qualification
            result = apply_qualification_to_ticket(ticket, backend=backend)
            flag_autoresponder_messages(ticket)
            counts[result.qualification] = counts.get(result.qualification, 0) + 1
            if "llm:" in result.reason or result.version.startswith("llm") or result.version.startswith("hybrid"):
                if "llm" in result.reason or result.version == "llm-v1":
                    llm_calls += 1
            n += 1
            if options["verbosity"] >= 2:
                self.stdout.write(
                    f"{ticket.external_id}: {before} -> {result.qualification} "
                    f"({result.confidence:.2f}) {result.reason[:80]}"
                )

        self.stdout.write(self.style.SUCCESS(f"Qualified {n} tickets with backend={backend}"))
        for key, value in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            self.stdout.write(f"  {key}: {value}")

        agg_qs = Ticket.objects.all()
        if options["team_slug"]:
            agg_qs = agg_qs.filter(team__slug=options["team_slug"])
        self.stdout.write("DB breakdown:")
        for row in agg_qs.values("qualification").annotate(c=Count("id")).order_by("-c"):
            self.stdout.write(f"  {row['qualification']}: {row['c']}")

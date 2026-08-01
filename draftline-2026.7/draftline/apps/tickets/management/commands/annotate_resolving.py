from django.core.management.base import BaseCommand

from apps.tickets.models import Ticket
from apps.tickets.services.resolving import annotate_thread_messages


class Command(BaseCommand):
    help = "Annotate autoresponder + resolving-reply flags on ticket messages."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", default="")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--support-only", action="store_true")

    def handle(self, *args, **options):
        qs = Ticket.objects.all().order_by("id")
        if options["team_slug"]:
            qs = qs.filter(team__slug=options["team_slug"])
        if options["support_only"]:
            qs = qs.filter(qualification="SUPPORT")
        if options["limit"]:
            qs = qs[: options["limit"]]

        resolving = 0
        autores = 0
        n = 0
        for ticket in qs.iterator():
            stats = annotate_thread_messages(ticket)
            resolving += stats["resolving"]
            autores += stats["autoresponders"]
            n += 1
        self.stdout.write(
            self.style.SUCCESS(f"Annotated {n} tickets; resolving={resolving} autoresponder_msgs={autores}")
        )

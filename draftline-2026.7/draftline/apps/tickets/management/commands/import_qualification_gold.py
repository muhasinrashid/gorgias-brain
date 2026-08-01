import csv

from django.core.management.base import BaseCommand

from apps.teams.models import Team
from apps.tickets.models import Qualification, QualificationGoldLabel, Ticket


class Command(BaseCommand):
    help = "Import gold labels from CSV produced by eval_qualification --export (gold_label column filled)."

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True)
        parser.add_argument("--team-slug", required=True)

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        allowed = {c.value for c in Qualification}
        n = 0
        with open(options["csv"], newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                label = (row.get("gold_label") or "").strip().upper()
                if not label or label not in allowed:
                    continue
                ticket = Ticket.objects.get(pk=int(row["ticket_id"]), team=team)
                QualificationGoldLabel.objects.update_or_create(
                    team=team,
                    ticket=ticket,
                    defaults={"label": label, "notes": row.get("notes") or ""},
                )
                n += 1
        self.stdout.write(self.style.SUCCESS(f"Imported {n} gold labels"))

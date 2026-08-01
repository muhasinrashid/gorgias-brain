from django.core.management.base import BaseCommand

from apps.knowledge.services.resolution_pairs import extract_resolution_pairs_for_team
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Extract ResolutionPairs from SUPPORT tickets with resolving replies."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--min-confidence", type=float, default=0.8)

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        result = extract_resolution_pairs_for_team(
            team,
            limit=options["limit"],
            min_confidence=options["min_confidence"],
        )
        self.stdout.write(self.style.SUCCESS(f"ResolutionPairs: {result}"))

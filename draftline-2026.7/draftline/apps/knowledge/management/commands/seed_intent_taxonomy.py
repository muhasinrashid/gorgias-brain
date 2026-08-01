from django.core.management.base import BaseCommand

from apps.knowledge.services.intent_taxonomy import seed_intent_taxonomy
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Seed intent taxonomy (HC categories / macro leaves / NOT_SUPPORT)."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--no-macros", action="store_true")
        parser.add_argument("--no-web", action="store_true")

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        result = seed_intent_taxonomy(
            team,
            include_macros=not options["no_macros"],
            include_web_titles=not options["no_web"],
        )
        self.stdout.write(self.style.SUCCESS(str(result)))

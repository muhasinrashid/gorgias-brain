from django.core.management.base import BaseCommand

from apps.knowledge.services.web_quarantine import quarantine_noisy_web_sources
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Deactivate crawled web pages that are not FAQ/help knowledge (collections, legal, PDP, etc.)."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        result = quarantine_noisy_web_sources(team)
        self.stdout.write(self.style.SUCCESS(str(result)))

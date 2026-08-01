from django.core.management.base import BaseCommand

from apps.knowledge.services.chunking import chunk_sources_for_team
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Create text Chunks for active Sources (no embeddings yet)."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument(
            "--types",
            type=str,
            default="",
            help="Comma-separated SourceType values (default: all active)",
        )

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        types = [t.strip() for t in (options["types"] or "").split(",") if t.strip()] or None
        result = chunk_sources_for_team(team, source_types=types, limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Chunked {result['sources']} sources → {result['chunks']} chunks"))

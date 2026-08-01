from django.core.management.base import BaseCommand

from apps.knowledge.services.embed_jobs import embed_chunks, embed_resolution_pairs
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Embed Chunks and/or ResolutionPairs for a team (Azure text-embedding-3-small)."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--pairs", action="store_true", help="Embed resolution pairs")
        parser.add_argument("--chunks", action="store_true", help="Embed chunks (default if neither flag)")
        parser.add_argument("--all-existing", action="store_true", help="Re-embed even if already set")
        parser.add_argument("--sync", action="store_true", help="Run inline instead of Celery .delay")

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        do_chunks = options["chunks"] or not options["pairs"]
        do_pairs = options["pairs"]
        only_missing = not options["all_existing"]
        limit = options["limit"]
        run = (lambda task, *a, **kw: task.run(*a, **kw)) if options["sync"] else (lambda task, *a, **kw: task.delay(*a, **kw))

        if do_chunks:
            result = run(embed_chunks, team.id, limit=limit, only_missing=only_missing)
            self.stdout.write(self.style.SUCCESS(f"chunks: {result}"))
        if do_pairs:
            result = run(embed_resolution_pairs, team.id, limit=limit, only_missing=only_missing)
            self.stdout.write(self.style.SUCCESS(f"pairs: {result}"))

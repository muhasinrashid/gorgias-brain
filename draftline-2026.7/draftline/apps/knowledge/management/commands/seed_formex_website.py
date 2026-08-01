from django.core.management.base import BaseCommand

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.knowledge.services.ingest import ingest_website
from apps.teams.models import Team

FORMEX_FAQ_URLS = [
    "https://formexwatch.com/faqs/",
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Freturns-154421",
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fshipping-154418",
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fpayment-154417",
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fgift-options-154416",
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fstraps-bracelets-and-bezels-154415",
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Ftechnical-questions-154414",
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fwarranty-and-service-154420",
]


class Command(BaseCommand):
    help = "Create or update a Website connection with Formex FAQ seed URLs and queue crawl."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--sync", action="store_true", help="Run crawl inline (.run) instead of .delay")
        parser.add_argument("--display-name", default="Formex FAQ")

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        connection, created = Connection.objects.update_or_create(
            team=team,
            provider=Provider.WEBSITE,
            display_name=options["display_name"],
            defaults={
                "config": {"seed_urls": FORMEX_FAQ_URLS, "max_pages": 30, "max_depth": 2},
                "status": ConnectionStatus.PENDING,
                "health": {"seeded": True},
            },
        )
        self.stdout.write(f"{'Created' if created else 'Updated'} connection id={connection.id}")
        if options["sync"]:
            result = ingest_website.run(team.id, connection.id)
            self.stdout.write(self.style.SUCCESS(f"Crawl result: {result}"))
        else:
            ingest_website.delay(team.id, connection.id)
            self.stdout.write(self.style.SUCCESS("Crawl queued (Celery)."))

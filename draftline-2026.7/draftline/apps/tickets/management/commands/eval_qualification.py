import csv
import random

from django.core.management.base import BaseCommand

from apps.tickets.models import Qualification, QualificationGoldLabel, Ticket


class Command(BaseCommand):
    help = "Export a stratified sample for gold labelling, or evaluate predictions vs gold labels."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--export", type=str, default="", help="CSV path to export sample")
        parser.add_argument("--sample-size", type=int, default=300)
        parser.add_argument("--eval", action="store_true", help="Evaluate current predictions vs gold labels")

    def handle(self, *args, **options):
        team_slug = options["team_slug"]
        tickets = Ticket.objects.filter(team__slug=team_slug)
        if options["export"]:
            self._export(tickets, options["export"], options["sample_size"])
        if options["eval"]:
            self._eval(tickets)
        if not options["export"] and not options["eval"]:
            self.stderr.write("Pass --export path.csv and/or --eval")

    def _export(self, tickets, path, sample_size):
        by_q = {}
        for q, _ in Qualification.choices:
            ids = list(tickets.filter(qualification=q).values_list("id", flat=True))
            by_q[q] = ids
        # Stratified: aim for mix; oversample SUPPORT and UNCLEAR
        weights = {
            "SUPPORT": 0.35,
            "UNCLEAR": 0.25,
            "VENDOR_PITCH": 0.1,
            "SYSTEM_NOTIFICATION": 0.1,
            "SOCIAL_NOTIFICATION": 0.08,
            "SPAM_PHISHING": 0.07,
            "MARKETING_INBOUND": 0.03,
            "INTERNAL": 0.02,
        }
        chosen: list[int] = []
        for q, frac in weights.items():
            need = max(1, int(sample_size * frac))
            pool = by_q.get(q) or []
            random.shuffle(pool)
            chosen.extend(pool[:need])
        # fill remainder
        remaining = sample_size - len(chosen)
        if remaining > 0:
            rest = list(tickets.exclude(id__in=chosen).values_list("id", flat=True))
            random.shuffle(rest)
            chosen.extend(rest[:remaining])

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["ticket_id", "external_id", "subject", "channel", "predicted", "confidence", "gold_label", "notes"]
            )
            for t in Ticket.objects.filter(id__in=chosen).order_by("id"):
                writer.writerow(
                    [
                        t.id,
                        t.external_id,
                        t.subject[:200],
                        t.channel,
                        t.qualification,
                        t.qualification_confidence or "",
                        "",
                        "",
                    ]
                )
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(chosen)} rows to {path}"))
        self.stdout.write("Fill gold_label column, then: manage.py import_qualification_gold --csv ...")

    def _eval(self, tickets):
        team = tickets.first().team if tickets.exists() else None
        if not team:
            self.stderr.write("No tickets")
            return
        gold = list(QualificationGoldLabel.objects.filter(team=team).select_related("ticket"))
        if not gold:
            self.stderr.write("No gold labels. Export a CSV, label it, import, then --eval.")
            return

        # Confusion-style metrics; precision on SUPPORT is the gate
        support_pred_pos = [g for g in gold if g.ticket.qualification == Qualification.SUPPORT]
        support_true_pos = [g for g in support_pred_pos if g.label == Qualification.SUPPORT]
        support_gold = [g for g in gold if g.label == Qualification.SUPPORT]

        precision = len(support_true_pos) / len(support_pred_pos) if support_pred_pos else 0.0
        recall = len(support_true_pos) / len(support_gold) if support_gold else 0.0
        agreement = sum(1 for g in gold if g.ticket.qualification == g.label) / len(gold)

        self.stdout.write(f"Gold labels: {len(gold)}")
        self.stdout.write(f"Overall agreement: {agreement:.3f}")
        self.stdout.write(f"SUPPORT precision: {precision:.3f} (gate ≥ 0.95)")
        self.stdout.write(f"SUPPORT recall: {recall:.3f}")
        if precision < 0.95:
            self.stdout.write(self.style.ERROR("GATE FAIL: SUPPORT precision below 0.95"))
        else:
            self.stdout.write(self.style.SUCCESS("GATE PASS: SUPPORT precision ≥ 0.95"))

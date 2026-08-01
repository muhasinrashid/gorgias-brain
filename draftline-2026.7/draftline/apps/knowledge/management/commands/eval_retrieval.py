from pathlib import Path

from django.core.management.base import BaseCommand

from apps.knowledge.services.eval_retrieval import (
    build_held_out_from_faqs,
    build_held_out_from_pairs,
    build_mixed_held_out,
    evaluate_retrieval,
    load_eval_set,
    save_eval_set,
)
from apps.teams.models import Team


class Command(BaseCommand):
    help = "Build or run retrieval eval (recall@k + language match). Default mode=mixed (FAQ-first)."

    def add_arguments(self, parser):
        parser.add_argument("--team-slug", required=True)
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--k", type=int, default=5)
        parser.add_argument(
            "--mode",
            choices=["mixed", "faq", "pairs"],
            default="mixed",
            help="mixed=FAQ pad with pairs (PRODUCT_SPEC gate); faq=FAQ only; pairs=ResolutionPairs",
        )
        parser.add_argument(
            "--json",
            type=str,
            default="docs/retrieval_eval_heldout.json",
            help="Path to write/read the held-out set",
        )
        parser.add_argument("--build-only", action="store_true")
        parser.add_argument("--eval-only", action="store_true")
        parser.add_argument(
            "--include-source-pair",
            action="store_true",
            help="Do not exclude the gold pair (pair-recovery sanity)",
        )

    def handle(self, *args, **options):
        team = Team.objects.get(slug=options["team_slug"])
        path = Path(options["json"])
        if not path.is_absolute():
            path = Path.cwd() / path

        if not options["eval_only"]:
            mode = options["mode"]
            if mode == "faq":
                questions = build_held_out_from_faqs(team, limit=options["limit"])
            elif mode == "pairs":
                questions = build_held_out_from_pairs(team, limit=options["limit"])
            else:
                questions = build_mixed_held_out(team, limit=options["limit"])
            save_eval_set(path, questions)
            self.stdout.write(
                self.style.SUCCESS(f"Wrote {len(questions)} questions (mode={mode}) → {path}")
            )
            if options["build_only"]:
                return
        else:
            questions = load_eval_set(path)
            self.stdout.write(f"Loaded {len(questions)} questions from {path}")

        result = evaluate_retrieval(
            team,
            questions,
            k=options["k"],
            exclude_source_pair=not options["include_source_pair"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"recall@{result['k']}={result['recall_at_k']:.3f} "
                f"({result['hits']}/{result['n']}) "
                f"language_match={result['language_match_rate']}"
            )
        )
        if result["recall_at_k"] < 0.85:
            self.stdout.write(
                self.style.WARNING("Below PRODUCT_SPEC gate recall@5 ≥ 0.85 — embed more corpus / tune retrieval.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Meets recall@5 ≥ 0.85 gate (this run)."))
        if result["language_match_rate"] is not None and result["language_match_rate"] >= 0.90:
            self.stdout.write(self.style.SUCCESS("Meets language_match ≥ 0.90 gate (this run)."))
        elif result["language_match_rate"] is not None:
            self.stdout.write(
                self.style.WARNING(
                    f"Below language_match ≥ 0.90 (got {result['language_match_rate']:.3f})."
                )
            )

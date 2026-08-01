from django.db import connection, models
from django.test import TestCase
from django.test.utils import isolate_apps

from apps.teams.context import current_team
from apps.teams.forms import TeamChangeForm
from apps.teams.helpers import get_next_unique_team_slug
from apps.teams.models import Team, TeamScopedManager
from apps.utils.models import BaseModel
from apps.utils.slug import get_next_unique_slug

# isolate_apps keeps the test-only model out of the global app registry, so the
# migration autodetector doesn't see it (the missing-migrations test would
# otherwise flag it as a pending migration).
with isolate_apps():

    class StrictTeamSlugModel(BaseModel):
        """
        Test-only model mirroring the "strict team access" customization from the docs,
        where the unfiltered manager is renamed to `all_objects` and `objects` is replaced
        with the team-scoped manager.
        """

        team = models.ForeignKey(Team, on_delete=models.CASCADE)
        name = models.CharField(max_length=100)
        slug = models.SlugField(max_length=100, unique=True)

        # declared first, so this is the model's _default_manager
        all_objects = models.Manager()
        objects = TeamScopedManager()

        class Meta:
            app_label = "teams"


class StrictTeamAccessSlugTest(TestCase):
    """
    Regression tests: slug uniqueness must be checked through _default_manager, not
    `objects`, so that models whose `objects` manager is team-scoped (per the "strict
    team access" docs) still enforce global uniqueness across teams.
    """

    @classmethod
    def setUpClass(cls):
        # StrictTeamSlugModel has no migration, so create its table by hand.
        # This must happen before super() so the schema edit runs outside the
        # class-level transaction (required on SQLite).
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(StrictTeamSlugModel)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(StrictTeamSlugModel)

    def test_slug_collision_across_teams(self):
        team1 = Team.objects.create(name="Team One", slug="team-one")
        team2 = Team.objects.create(name="Team Two", slug="team-two")

        with current_team(team1):
            slug = get_next_unique_slug(StrictTeamSlugModel, "My Thing", "slug")
            self.assertEqual(slug, "my-thing")
            StrictTeamSlugModel.all_objects.create(team=team1, name="My Thing", slug=slug)

        with current_team(team2):
            # the slug must be de-duped against team1's object despite the scoped manager
            slug = get_next_unique_slug(StrictTeamSlugModel, "My Thing", "slug")
            self.assertEqual(slug, "my-thing-2")
            StrictTeamSlugModel.all_objects.create(team=team2, name="My Thing", slug=slug)

    def test_slug_collision_without_team_context(self):
        team = Team.objects.create(name="Team One", slug="team-one")
        StrictTeamSlugModel.all_objects.create(team=team, name="My Thing", slug="my-thing")

        # with no team context, the scoped manager returns an empty queryset, which
        # would let the colliding slug through
        self.assertEqual(get_next_unique_slug(StrictTeamSlugModel, "My Thing", "slug"), "my-thing-2")


class UniqueSlugTest(TestCase):
    def test_unique_slug_no_conflict(self):
        self.assertEqual("a-slug", get_next_unique_team_slug("A Slug"))

    def test_unique_slug_conflicts(self):
        Team.objects.create(name="A Team", slug="a-slug")
        self.assertEqual("a-slug-2", get_next_unique_team_slug("A Slug"))
        Team.objects.create(name="A Team", slug="a-slug-2")
        Team.objects.create(name="A Team", slug="a-slug-4")
        self.assertEqual("a-slug-3", get_next_unique_team_slug("A Slug"))
        Team.objects.create(name="A Team", slug="a-slug-3")
        self.assertEqual("a-slug-5", get_next_unique_team_slug("A Slug"))


class TeamChangeFormSlugTest(TestCase):
    def test_blank_slug_generated_from_name(self):
        form = TeamChangeForm(data={"name": "A Team", "slug": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["slug"], "a-team")

    def test_unicode_only_name_falls_back_to_default_slug(self):
        # slugify() returns "" for non-ASCII-only names, which must not yield an empty slug
        form = TeamChangeForm(data={"name": "日本語", "slug": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["slug"])
        self.assertEqual(form.cleaned_data["slug"], "team")

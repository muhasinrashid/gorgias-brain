from django.test import TestCase

from apps.teams.celery import team_task
from apps.teams.context import get_current_team, unset_current_team
from apps.teams.models import Team


class TestTeamTaskDecorator(TestCase):
    def setUp(self):
        unset_current_team()
        self.team = Team.objects.create(name="Test Team", slug="test-team")

    def tearDown(self):
        unset_current_team()

    def test_sets_team_context_for_unbound_task(self):
        captured = {}

        @team_task(name="test_celery.unbound")
        def task(team_id, payload):
            captured["team"] = get_current_team()
            captured["payload"] = payload

        task(self.team.pk, "hello")

        self.assertEqual(captured["team"], self.team)
        self.assertEqual(captured["payload"], "hello")

    def test_sets_team_context_for_bound_task(self):
        captured = {}

        @team_task(bind=True, name="test_celery.bound")
        def task(self_task, team_id, payload):
            captured["team"] = get_current_team()
            captured["task_name"] = self_task.name
            captured["payload"] = payload

        task(self.team.pk, "world")

        self.assertEqual(captured["team"], self.team)
        self.assertEqual(captured["payload"], "world")
        self.assertEqual(captured["task_name"], "test_celery.bound")

    def test_restores_team_context_after_task(self):
        @team_task(name="test_celery.restores")
        def task(team_id):
            pass

        self.assertIsNone(get_current_team())
        task(self.team.pk)
        self.assertIsNone(get_current_team())

    def test_propagates_exceptions_from_body(self):
        @team_task(name="test_celery.raises")
        def task(team_id):
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            task(self.team.pk)

    def test_restores_team_context_even_when_body_raises(self):
        @team_task(name="test_celery.raises_restores")
        def task(team_id):
            raise ValueError("boom")

        self.assertIsNone(get_current_team())
        with self.assertRaises(ValueError):
            task(self.team.pk)
        self.assertIsNone(get_current_team())

    def test_raises_when_team_does_not_exist(self):
        @team_task(name="test_celery.missing_team")
        def task(team_id):
            pass

        with self.assertRaises(Team.DoesNotExist):
            task(999999)

    def test_supports_team_id_as_kwarg(self):
        captured = {}

        @team_task(name="test_celery.kwarg_team_id")
        def task(team_id):
            captured["team"] = get_current_team()

        task(team_id=self.team.pk)

        self.assertEqual(captured["team"], self.team)

    def test_supports_team_id_as_kwarg_when_bound(self):
        captured = {}

        @team_task(bind=True, name="test_celery.kwarg_team_id_bound")
        def task(self_task, team_id):
            captured["team"] = get_current_team()

        task(team_id=self.team.pk)

        self.assertEqual(captured["team"], self.team)

    def test_raises_helpful_error_when_team_id_missing(self):
        @team_task(name="test_celery.no_team_id")
        def task(team_id):
            pass

        with self.assertRaises(TypeError) as ctx:
            task()

        message = str(ctx.exception)
        self.assertIn("team_id", message)

    def test_supports_kwargs_passthrough(self):
        captured = {}

        @team_task(name="test_celery.kwargs")
        def task(team_id, *, label):
            captured["label"] = label
            captured["team"] = get_current_team()

        task(self.team.pk, label="kw")

        self.assertEqual(captured["label"], "kw")
        self.assertEqual(captured["team"], self.team)

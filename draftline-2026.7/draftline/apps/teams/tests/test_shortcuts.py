from django.http import Http404
from django.test import TestCase

from apps.teams.context import current_team, unset_current_team
from apps.teams.models import Invitation, Team
from apps.teams.shortcuts import get_team_object_or_404
from apps.users.models import CustomUser


class GetTeamObjectOr404Test(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create(username="inviter@example.com")
        cls.team1 = Team.objects.create(name="Team 1", slug="team-1")
        cls.team2 = Team.objects.create(name="Team 2", slug="team-2")
        cls.invitation1 = Invitation.objects.create(team=cls.team1, email="a@example.com", invited_by=cls.user)
        cls.invitation2 = Invitation.objects.create(team=cls.team2, email="b@example.com", invited_by=cls.user)

    def setUp(self):
        unset_current_team()

    def tearDown(self):
        unset_current_team()

    def test_returns_object_when_team_matches(self):
        with current_team(self.team1):
            result = get_team_object_or_404(Invitation, pk=self.invitation1.pk)
        self.assertEqual(result, self.invitation1)

    def test_raises_404_when_no_team_in_context(self):
        with self.assertRaises(Http404):
            get_team_object_or_404(Invitation, pk=self.invitation1.pk)

    def test_raises_404_when_object_belongs_to_different_team(self):
        # the footgun: invitation2 exists, but is not in team1
        with current_team(self.team1), self.assertRaises(Http404):
            get_team_object_or_404(Invitation, pk=self.invitation2.pk)

    def test_raises_404_when_object_does_not_exist(self):
        with current_team(self.team1), self.assertRaises(Http404):
            get_team_object_or_404(Invitation, pk="00000000-0000-0000-0000-000000000000")

    def test_returns_object_when_explicit_team_matches_context(self):
        with current_team(self.team1):
            result = get_team_object_or_404(Invitation, team=self.team1, pk=self.invitation1.pk)
        self.assertEqual(result, self.invitation1)

    def test_raises_when_explicit_team_differs_from_context(self):
        with current_team(self.team1), self.assertRaises(ValueError):
            get_team_object_or_404(Invitation, team=self.team2, pk=self.invitation1.pk)

from allauth.account.models import EmailAddress
from django.test import RequestFactory, TestCase

from apps.teams import roles
from apps.teams.helpers import get_open_invitations_for_user
from apps.teams.invitations import clear_invite_from_session, get_invitation_id_from_request, process_invitation
from apps.teams.models import Invitation, Membership, Team
from apps.users.models import CustomUser


def _create_user(email, **email_address_kwargs):
    user = CustomUser.objects.create(username=email, email=email)
    if email_address_kwargs:
        EmailAddress.objects.create(user=user, email=email, **email_address_kwargs)
    return user


class ProcessInvitationTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.inviter = _create_user("admin@example.com")
        self.team.members.add(self.inviter, through_defaults={"role": roles.ROLE_ADMIN})

    def test_process_invitation_adds_member_with_role(self):
        invitee = _create_user("invitee@example.com")
        invitation = Invitation.objects.create(
            team=self.team, email=invitee.email, role=roles.ROLE_MEMBER, invited_by=self.inviter
        )

        process_invitation(invitation, invitee)

        membership = Membership.objects.get(team=self.team, user=invitee)
        self.assertEqual(membership.role, roles.ROLE_MEMBER)
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_accepted)
        self.assertEqual(invitation.accepted_by, invitee)

    def test_process_invitation_with_admin_role(self):
        invitee = _create_user("invitee@example.com")
        invitation = Invitation.objects.create(
            team=self.team, email=invitee.email, role=roles.ROLE_ADMIN, invited_by=self.inviter
        )

        process_invitation(invitation, invitee)

        self.assertTrue(Membership.objects.get(team=self.team, user=invitee).is_admin())


class GetOpenInvitationsForUserTest(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Test Team", slug="test-team")
        self.inviter = _create_user("admin@example.com")
        self.team.members.add(self.inviter, through_defaults={"role": roles.ROLE_ADMIN})

    def _invite(self, email, team=None):
        return Invitation.objects.create(
            team=team or self.team, email=email, role=roles.ROLE_MEMBER, invited_by=self.inviter
        )

    def test_open_invitation_for_verified_email(self):
        user = _create_user("invitee@example.com", verified=True, primary=True)
        invitation = self._invite(user.email)

        invitations = get_open_invitations_for_user(user)

        self.assertEqual(len(invitations), 1)
        self.assertEqual(invitations[0]["id"], invitation.id)
        self.assertEqual(invitations[0]["team_name"], self.team.name)
        self.assertTrue(invitations[0]["verified"])

    def test_invitation_for_unverified_email_is_flagged(self):
        user = _create_user("invitee@example.com", verified=False, primary=True)
        self._invite(user.email)

        invitations = get_open_invitations_for_user(user)

        self.assertEqual(len(invitations), 1)
        self.assertFalse(invitations[0]["verified"])

    def test_matches_secondary_email(self):
        user = _create_user("primary@example.com", verified=True, primary=True)
        EmailAddress.objects.create(user=user, email="secondary@example.com", verified=True, primary=False)
        self._invite("secondary@example.com")

        invitations = get_open_invitations_for_user(user)

        self.assertEqual(len(invitations), 1)
        self.assertEqual(invitations[0]["email"], "secondary@example.com")

    def test_excludes_teams_user_is_already_member_of(self):
        user = _create_user("invitee@example.com", verified=True, primary=True)
        self._invite(user.email)
        self.team.members.add(user, through_defaults={"role": roles.ROLE_MEMBER})

        self.assertEqual(get_open_invitations_for_user(user), [])

    def test_excludes_accepted_invitations(self):
        user = _create_user("invitee@example.com", verified=True, primary=True)
        invitation = self._invite(user.email)
        invitation.is_accepted = True
        invitation.save()

        self.assertEqual(get_open_invitations_for_user(user), [])

    def test_user_without_email_records_gets_nothing(self):
        user = _create_user("invitee@example.com")
        self._invite(user.email)

        self.assertEqual(get_open_invitations_for_user(user), [])


class InvitationSessionHelpersTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_invitation_id_from_url(self):
        request = self.factory.get("/", {"invitation_id": "from-url"})
        request.session = {}
        self.assertEqual(get_invitation_id_from_request(request), "from-url")

    def test_invitation_id_from_session(self):
        request = self.factory.get("/")
        request.session = {"invitation_id": "from-session"}
        self.assertEqual(get_invitation_id_from_request(request), "from-session")

    def test_url_takes_precedence_over_session(self):
        request = self.factory.get("/", {"invitation_id": "from-url"})
        request.session = {"invitation_id": "from-session"}
        self.assertEqual(get_invitation_id_from_request(request), "from-url")

    def test_no_invitation_id(self):
        request = self.factory.get("/")
        request.session = {}
        self.assertIsNone(get_invitation_id_from_request(request))

    def test_clear_invite_from_session(self):
        request = self.factory.get("/")
        request.session = {"invitation_id": "abc", "other": "value"}
        clear_invite_from_session(request)
        self.assertEqual(request.session, {"other": "value"})

    def test_clear_invite_from_session_is_noop_when_missing(self):
        request = self.factory.get("/")
        request.session = {}
        clear_invite_from_session(request)  # should not raise
        self.assertEqual(request.session, {})

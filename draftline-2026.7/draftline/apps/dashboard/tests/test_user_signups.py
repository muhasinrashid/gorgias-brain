import datetime

from allauth.account.models import EmailAddress
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.dashboard.services import get_user_signups
from apps.users.models import CustomUser


def _create_user(email, days_ago=0, verified=None):
    user = CustomUser.objects.create(
        username=email,
        email=email,
        date_joined=timezone.now() - datetime.timedelta(days=days_ago),
    )
    if verified is not None:
        EmailAddress.objects.create(user=user, email=email, verified=verified, primary=True)
    return user


class GetUserSignupsTest(TestCase):
    def test_counts_signups_by_date(self):
        _create_user("a@example.com", days_ago=3)
        _create_user("b@example.com", days_ago=3)
        _create_user("c@example.com", days_ago=1)

        data = get_user_signups(include_unconfirmed=True)

        expected_day_3 = timezone.localdate(timezone.now() - datetime.timedelta(days=3))
        expected_day_1 = timezone.localdate(timezone.now() - datetime.timedelta(days=1))
        self.assertEqual(data, [{"date": expected_day_3, "count": 2}, {"date": expected_day_1, "count": 1}])

    def test_default_window_excludes_old_signups(self):
        _create_user("old@example.com", days_ago=100)
        _create_user("recent@example.com", days_ago=5)

        data = get_user_signups(include_unconfirmed=True)

        self.assertEqual(sum(item["count"] for item in data), 1)

    def test_explicit_date_range(self):
        _create_user("in-range@example.com", days_ago=5)
        _create_user("too-recent@example.com", days_ago=1)

        end = timezone.now() - datetime.timedelta(days=3)
        data = get_user_signups(start=end - datetime.timedelta(days=30), end=end, include_unconfirmed=True)

        self.assertEqual(sum(item["count"] for item in data), 1)

    def test_excludes_unconfirmed_users(self):
        _create_user("verified@example.com", days_ago=2, verified=True)
        _create_user("unverified@example.com", days_ago=2, verified=False)
        _create_user("no-email-record@example.com", days_ago=2)

        data = get_user_signups(include_unconfirmed=False)

        self.assertEqual(sum(item["count"] for item in data), 1)

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="mandatory")
    def test_mandatory_verification_setting_excludes_unconfirmed_by_default(self):
        _create_user("verified@example.com", days_ago=2, verified=True)
        _create_user("unverified@example.com", days_ago=2, verified=False)

        data = get_user_signups()

        self.assertEqual(sum(item["count"] for item in data), 1)

    def test_user_with_multiple_verified_emails_counted_once(self):
        # regression test: the emailaddress join duplicates the user row per verified
        # email, so the count needs distinct=True
        user = _create_user("multi@example.com", days_ago=2, verified=True)
        EmailAddress.objects.create(user=user, email="multi-alt@example.com", verified=True, primary=False)

        data = get_user_signups(include_unconfirmed=False)

        self.assertEqual(sum(item["count"] for item in data), 1)

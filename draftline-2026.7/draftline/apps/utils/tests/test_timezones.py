import zoneinfo

from django.test import SimpleTestCase

from apps.utils.timezones import get_common_timezones, get_timezones_display


class TimezonesTest(SimpleTestCase):
    def test_all_common_timezones_are_valid_iana_keys(self):
        available = zoneinfo.available_timezones()
        for tz in get_common_timezones():
            with self.subTest(tz=tz):
                self.assertIn(tz, available)

    def test_display_choices_include_not_set_option(self):
        choices = list(get_timezones_display())
        self.assertEqual(choices[0], ("", "Not Set"))
        self.assertEqual(len(choices), len(get_common_timezones()) + 1)
        for value, label in choices[1:]:
            self.assertEqual(value, label)

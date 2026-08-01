from django.test import SimpleTestCase

from apps.tickets.models import Qualification
from apps.tickets.services.qualification import is_autoresponder_text, qualify_ticket


class QualificationRulesTests(SimpleTestCase):
    def test_social_mention(self):
        r = qualify_ticket(subject="Mention in smooth_bezel's story")
        self.assertEqual(r.qualification, Qualification.SOCIAL_NOTIFICATION)

    def test_vendor_pitch(self):
        r = qualify_ticket(subject="A local manufacturing partner for your jewelry packaging")
        self.assertEqual(r.qualification, Qualification.VENDOR_PITCH)

    def test_system_oos(self):
        r = qualify_ticket(subject="Out of stock notification for Automatic Chronometer")
        self.assertEqual(r.qualification, Qualification.SYSTEM_NOTIFICATION)

    def test_system_abwesend(self):
        r = qualify_ticket(subject="ABWESEND")
        self.assertEqual(r.qualification, Qualification.SYSTEM_NOTIFICATION)

    def test_spam_ad_account(self):
        r = qualify_ticket(subject="Warning: Your ad account and your Fanpage will be disabled within 48 hours.")
        self.assertEqual(r.qualification, Qualification.SPAM_PHISHING)

    def test_support_product_question(self):
        r = qualify_ticket(
            subject="Product question - FORMEX Swiss Made Watches (en-US)",
            channel="help-center",
        )
        self.assertEqual(r.qualification, Qualification.SUPPORT)

    def test_support_watch_issue(self):
        r = qualify_ticket(subject="Issues with my watch")
        self.assertEqual(r.qualification, Qualification.SUPPORT)

    def test_support_bezel(self):
        r = qualify_ticket(
            subject="I have an older (2021) Reef with the 60 click bezel. Can I swap bezels with this version?"
        )
        self.assertEqual(r.qualification, Qualification.SUPPORT)

    def test_unclear_when_unknown(self):
        r = qualify_ticket(subject="asdf qwer zxcv")
        self.assertEqual(r.qualification, Qualification.UNCLEAR)

    def test_autoresponder(self):
        self.assertTrue(
            is_autoresponder_text(
                "Hi there, Thank you for contacting us. We’ve received your message and appreciate your interest."
            )
        )
        self.assertFalse(is_autoresponder_text("Your Reef is covered under warranty for two years."))

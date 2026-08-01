from django.test import TestCase, override_settings

from apps.utils.locks import lock_cache, single_flight

LOCMEM_LOCKS = {
    "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
    "locks": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-locks",
    },
}


@override_settings(CACHES=LOCMEM_LOCKS)
class SingleFlightTests(TestCase):
    def setUp(self):
        lock_cache().clear()

    def test_second_caller_is_refused_while_first_holds_lock(self):
        with single_flight("job:1") as first:
            self.assertTrue(first)
            with single_flight("job:1") as second:
                self.assertFalse(second)

    def test_lock_released_after_block(self):
        with single_flight("job:1") as first:
            self.assertTrue(first)
        with single_flight("job:1") as again:
            self.assertTrue(again)

    def test_different_keys_do_not_block_each_other(self):
        with single_flight("job:1") as first, single_flight("job:2") as second:
            self.assertTrue(first)
            self.assertTrue(second)

    def test_lock_released_when_body_raises(self):
        with self.assertRaises(ValueError), single_flight("job:1"):
            raise ValueError("boom")
        with single_flight("job:1") as again:
            self.assertTrue(again)

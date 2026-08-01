from django.test import SimpleTestCase, TestCase

from ...users.models import CustomUser
from ..slug import get_next_slug, get_next_unique_slug, get_next_unique_slug_value


class NextSlugTest(SimpleTestCase):
    def test_next_slug_basic(self):
        self.assertEqual("slug-11", get_next_slug("slug", 11))

    def test_next_slug_truncate(self):
        self.assertEqual("slug-11", get_next_slug("slug", 11, max_length=7))
        self.assertEqual("slu-11", get_next_slug("slug", 11, max_length=6))
        self.assertEqual("slu-100", get_next_slug("slug", 100, max_length=7))
        self.assertEqual("sl-100", get_next_slug("slug", 100, max_length=6))

    def test_next_slug_fail(self):
        with self.assertRaises(ValueError):
            get_next_slug("slug", 11111, max_length=6)

    def test_next_slug_strips_trailing_hyphen(self):
        # truncating "foo-bar" to 4 chars yields "foo-"; the trailing hyphen is dropped
        # so we get "foo-2" rather than "foo--2"
        self.assertEqual("foo-2", get_next_slug("foo-bar", 2, max_length=6))

    def test_next_slug_unbounded(self):
        # max_length=None means no truncation, however long the base
        self.assertEqual("a-really-long-base-2", get_next_slug("a-really-long-base", 2, max_length=None))


class NextUniqueSlugTest(TestCase):
    # we test with CustomUsers because that's a model we know exists in the project.
    def test_basic(self):
        self.assertEqual("slug", get_next_unique_slug(CustomUser, "Slug", "username"))
        self.assertEqual("slug", get_next_unique_slug_value(CustomUser, "slug", "username"))
        user = CustomUser(username="slug")
        user.save()
        self.assertEqual("slug-2", get_next_unique_slug(CustomUser, "Slug", "username"))
        self.assertEqual("slug-2", get_next_unique_slug_value(CustomUser, "slug", "username"))

    def test_long_value_truncated_to_field_max_length(self):
        # regression: a value longer than the field (username is varchar(150)) must be
        # truncated so it fits the column instead of raising a DataError on save
        slug = get_next_unique_slug_value(CustomUser, "a" * 200, "username")
        self.assertEqual("a" * 150, slug)
        self.assertEqual(150, len(slug))

    def test_long_value_truncated_with_collision_suffix(self):
        # the suffix must also fit within the field's max_length
        CustomUser.objects.create(username="a" * 150)
        slug = get_next_unique_slug_value(CustomUser, "a" * 200, "username")
        self.assertTrue(slug.endswith("-2"))
        self.assertLessEqual(len(slug), 150)

    def test_extra_filter_args(self):
        CustomUser.objects.create(username="u1", first_name="alice", last_name="slug")
        self.assertEqual(
            "slug-2",
            get_next_unique_slug_value(CustomUser, "slug", "last_name", extra_filter_args={"first_name": "alice"}),
        )
        self.assertEqual(
            "slug", get_next_unique_slug_value(CustomUser, "slug", "last_name", extra_filter_args={"first_name": "bob"})
        )

    def test_consecutive_collisions(self):
        CustomUser.objects.create(username="slug")
        CustomUser.objects.create(username="slug-2")
        CustomUser.objects.create(username="slug-3")
        self.assertEqual("slug-4", get_next_unique_slug_value(CustomUser, "slug", "username"))

    def test_unrelated_prefix_matches_are_ignored(self):
        # "slugger" starts with "slug" but must not be treated as a collision
        CustomUser.objects.create(username="slugger")
        self.assertEqual("slug", get_next_unique_slug_value(CustomUser, "slug", "username"))

    def test_empty_value_returned_as_is(self):
        # An empty base is returned unchanged (never suffixed into a bare "-2"); callers
        # are responsible for supplying their own fallback.
        self.assertEqual("", get_next_unique_slug_value(CustomUser, "", "username"))

    def test_non_ascii_name_returns_empty(self):
        # slugify() returns "" for a name with no ASCII characters; the helper passes that
        # through rather than emitting a bare "-2".
        self.assertEqual("", get_next_unique_slug(CustomUser, "日本語", "username"))

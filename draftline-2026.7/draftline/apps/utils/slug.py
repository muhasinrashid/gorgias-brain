from django.db.models import Model
from django.utils.text import slugify


def get_next_unique_slug(
    model_class: type[Model], display_name: str, slug_field_name: str, extra_filter_args: dict | None = None
) -> str:
    """
    Gets the next unique slug based on the name. Appends -2, -3, etc. until it finds
    a unique value.
    """
    return get_next_unique_slug_value(model_class, slugify(display_name), slug_field_name, extra_filter_args)


def get_next_unique_slug_value(
    model_class: type[Model], slug_value: str, slug_field_name: str, extra_filter_args: dict | None = None
) -> str:
    """
    Gets the next unique slug based on the value. Appends -2, -3, etc. until it finds
    a unique value.
    """
    # Truncate to the field's max_length so long values (e.g. a record named after its
    # whole description) don't overflow the column. rstrip avoids a trailing "-" when the
    # cut lands mid-word. Unbounded fields (TextField, max_length=None) need no truncation.
    # getattr default of None handles both unbounded fields and relation descriptors
    # (ForeignObjectRel), which have no max_length.
    max_length = getattr(model_class._meta.get_field(slug_field_name), "max_length", None)
    if max_length is not None:
        slug_value = slug_value[:max_length].rstrip("-")
    if not slug_value:
        # An empty base can't be meaningfully uniquified (suffixing would emit a bare "-2"),
        # so return it as-is and let the caller apply its own fallback.
        return slug_value
    extra_filter_args = extra_filter_args or dict()
    filter_kwargs = extra_filter_args.copy()
    filter_kwargs[slug_field_name] = slug_value
    # _default_manager instead of .objects: it's equivalent for our models and declared on the base Model type
    manager = model_class._default_manager
    if manager.filter(**filter_kwargs).exists():
        # todo make this do fewer queries
        suffix = 2
        while True:
            next_slug = get_next_slug(slug_value, suffix, max_length=max_length)
            filter_kwargs[slug_field_name] = next_slug
            if not manager.filter(**filter_kwargs).exists():
                return next_slug
            else:
                suffix += 1
    else:
        return slug_value


def get_next_slug(base_value: str, suffix: int, max_length: int | None = 100) -> str:
    """
    Gets the next slug from base_value such that "base_value-suffix" will not exceed max_length characters.
    A max_length of None means unbounded: the suffix is appended without truncating base_value.
    """
    if max_length is None:
        return f"{base_value}-{suffix}"

    suffix_length = len(str(suffix)) + 1  # + 1 for the "-" character
    if suffix_length >= max_length:
        raise ValueError(f"Suffix {suffix} is too long to create a unique slug! ")

    return f"{base_value[: max_length - suffix_length].rstrip('-')}-{suffix}"

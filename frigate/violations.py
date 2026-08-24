"""Shared definition of what counts as a Rasid360 violation event.

Violations are represented as ordinary Frigate events that carry a ``sub_label``.
That alone is not a sufficient test: upstream Frigate also writes ``sub_label``
for enrichment results -- face recognition
(``frigate/data_processing/real_time/face.py``) and license plate recognition
both publish it via ``EventMetadataTypeEnum.sub_label``. Filtering on
``sub_label IS NOT NULL`` therefore counts every recognized face and plate as a
violation.

Rasid360's detectors pass a ``source_type`` when creating their events, which
``TrackedObjectProcessor.create_manual_event`` stores as ``Event.data["type"]``.
Matching on that marker distinguishes a real violation from an enrichment result.
"""

from frigate.models import Event

# source_type values used by the detectors in frigate/extras/actions/.
# Keep in sync with the create_event() calls there.
VIOLATION_SOURCE_TYPES = (
    "dsl_violation_detector",
    "wrong_way_detector",
    "custom_action",
)


def violation_events_clause():
    """Peewee expression matching only Rasid360-generated violation events."""
    return Event.sub_label.is_null(False) & (
        Event.data["type"].cast("text").in_(list(VIOLATION_SOURCE_TYPES))
    )

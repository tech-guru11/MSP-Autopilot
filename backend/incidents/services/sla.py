from django.utils import timezone


def calculate_elapsed_minutes(started_at, ended_at=None):
    if started_at is None:
        raise ValueError("started_at is required.")

    if ended_at is None:
        ended_at = timezone.now()

    elapsed = ended_at - started_at
    return elapsed.total_seconds() / 60


def calculate_resolution_minutes(incident):
    return calculate_elapsed_minutes(
        incident.started_at,
        incident.resolved_at,
    )

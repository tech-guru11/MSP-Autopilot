import uuid

from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Membership


def get_active_membership(request):
    if hasattr(request, "_active_membership"):
        return request._active_membership

    organization_id = request.headers.get("X-Organization-ID")

    if not organization_id:
        raise ValidationError("X-Organization-ID header is required.")

    try:
        uuid.UUID(str(organization_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(
            "X-Organization-ID header must be a valid UUID."
        ) from exc

    membership = (
        Membership.objects.select_related("organization")
        .filter(
            user=request.user,
            organization_id=organization_id,
        )
        .first()
    )

    if membership is None:
        raise PermissionDenied("You do not have access to this organization.")

    request._active_membership = membership
    return membership


def get_active_organization(request):
    return get_active_membership(request).organization

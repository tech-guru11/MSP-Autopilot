from organizations.serializers import MembershipSerializer
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSerializer


class MeView(APIView):
    def get(self, request):
        data = UserSerializer(request.user).data
        memberships = request.user.memberships.select_related(
            "organization"
        ).order_by("organization__name")
        data["memberships"] = MembershipSerializer(
            memberships,
            many=True,
        ).data
        return Response(data)

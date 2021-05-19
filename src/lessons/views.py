
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lessons(request):
    return Response({"lessons": ["Hello, world!", "Second lesson"]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson(request):
    return Response({"lesson": {
        "title": "This is the title"
    }})


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lessons(request):
    return Response({"lessons": [{
        "id": "ij3449dsnfksldfsd",
        "title": "Title of an example lesson",
        "category": "reclamation"
    }]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson(request):
    return Response({"lesson": {
        "title": "This is the title"
    }})

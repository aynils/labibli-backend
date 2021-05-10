from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def get_lessons(request):
    return Response({"lessons": ["Hello, world!", "Second lesson"]})

@api_view(['GET'])
def get_lesson(request):
    return Response({"lesson": {
        "title": "This is the title"
    }})

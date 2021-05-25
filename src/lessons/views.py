import dataclasses

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED

from lessons.comfortable import api


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lessons(request, category: str) -> Response:
    lessons = api.get_lessons(category=category)
    return Response(dataclasses.asdict(lessons))


@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def get_lesson(request, lesson_id: str):
    lesson = api.get_lesson(lesson_id=lesson_id)
    return Response(dataclasses.asdict(lesson))

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_categories(request):
    return Response(
        {
            "categories": [
                {
                    "id": "environment",
                    "name": "Environment"
                },
                {
                    "id": "legal",
                    "name": "Legal"
                },
                {
                    "id": "otherCategory",
                    "name": "Other Category"
                },
                {
                    "id": "category4",
                    "name": "Category 4"
                }
            ]
        }
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def post_picture(request):
    return Response(request.data, status=HTTP_201_CREATED)

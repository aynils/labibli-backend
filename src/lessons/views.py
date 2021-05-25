import dataclasses
from typing import List

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED

from lessons.comfortable import api
from lessons.comfortable.classes import Lesson


@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def get_lessons(request, category: str) -> Response:
    lessons = api.get_lessons(category=category)
    return Response(dataclasses.asdict(lessons))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson(request, lesson_id: str):
    return Response({"lesson": {
        "id": lesson_id,
        "title": "This is the title",
        "category": "This is the category",
        "content": {
            "sections": [
                {
                    "title": "first section title",
                    "video_url": "video_url (gonna need to store the video locally)"
                }, {
                    "title": "second section title",
                    "video_url": "video_url (gonna need to store the video locally)"
                }
            ]
        },
        "quiz_id": "iamaquizid",
    }})


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

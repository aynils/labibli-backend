import dataclasses

from django.http import HttpResponseBadRequest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED
from lessons.forms import UploadFileForm

from lessons.comfortable import api

CATEGORIES = [
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


@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def get_lessons(request, category: str) -> Response:
    lessons = api.get_lessons(category=category)
    return Response(dataclasses.asdict(lessons))


@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def get_lesson(request, lesson_id: str):
    lesson = api.get_lesson(lesson_id=lesson_id)
    return Response(dataclasses.asdict(lesson))

@api_view(['GET'])
# @permission_classes([IsAuthenticated])
def get_categories(request):
    return Response(
        {
            "categories": CATEGORIES
        }
    )


@api_view(['POST'])
# @permission_classes([IsAuthenticated])
def post_picture(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            # handle_uploaded_file(request.FILES['file'])
            picture = form.save(commit=False)
            picture.user_id = request.user.id
            picture.save()
            return Response(status=HTTP_201_CREATED)
        else:
            return HttpResponseBadRequest()

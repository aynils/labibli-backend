from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lessons(request):
    return Response({"lessons": [{
        "id": "ij3449dsnfksldfsd",
        "title": "Title of an example lesson",
        "category": "This is the category"
    }]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson(request, lesson_id: str):
    return Response({"lesson": {
        "id": lesson_id,
        "title": "This is the title",
        "category": "This is the category",
        "content": {
            "sections": {
                "1": {
                    "title": "first section title",
                    "video": "video_url (gonna need to store the video locally)"
                },
                "2": {
                    "title": "second section title",
                    "video": "video_url (gonna need to store the video locally)"
                },

        }
        },
        "quiz_id": "iamaquizid",
    }})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_quiz(request, quiz_id: str):
    return Response(
        {"quiz": {
            "id": quiz_id,
            "questions": [
                {"question": "I'm the first question",
                 "type": "multiplechoice",
                 "choices": [
                     {"a": "The answer A"},
                     {"b": "The answer B"},
                     {"c": "The answer C"},
                     {"d": "The answer D"}
                 ]},
                {"question": "I'm the second question",
                 "type": "multiplechoice",
                 "choices": [
                     {"a": "The answer A"},
                     {"b": "The answer B"},
                     {"c": "The answer C"},
                     {"d": "The answer D"}
                 ]},
            ]
        }})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def post_picture(request):
    return Response(request.data, status=HTTP_201_CREATED)

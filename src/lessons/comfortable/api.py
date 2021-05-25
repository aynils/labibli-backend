import os
import string

import requests

from lessons.comfortable.classes import (Collection, LessonMeta, Lesson, Quiz, Question, Choice, LessonContent,
                                         LessonSection, EnvironmentSection)

COMFORTABLE_API_KEY = os.getenv('COMFORTABLE_API_KEY')
COMFORTABLE_API_URL = "https://api.cmft.io/v1/kpma"
DEFAULT_QUIZZ_TYPE = "multichoice"

HEADERS = {
    "Authorization": COMFORTABLE_API_KEY
}

PARAMS = {
    "embedAssets": True
}

ALPHABET = list(string.ascii_lowercase)


# API CALLS

def get_lessons(category: str) -> Collection:
    url = f"{COMFORTABLE_API_URL}/collections/{category}"
    response = requests.get(url=url, params=PARAMS, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        collection = parse_collection(raw_collection=data, category=category)
        return collection
    else:
        print(f"ERROR - {response.status_code} - {response.json()}")


def get_lesson(lesson_id: str) -> Lesson:
    url = f"{COMFORTABLE_API_URL}/documents/{lesson_id}"
    response = requests.get(url=url, params=PARAMS, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        lesson = parse_lesson(raw_document=data)
        return lesson
    else:
        print(f"ERROR - {response.status_code} - {response.json()}")


# Parsers

def parse_collection(raw_collection: dict, category: str) -> Collection:
    raw_lessons = raw_collection.get('data')
    lessons = []
    for lesson in raw_lessons:
        fields = lesson.get('fields')
        info = fields.get('info')
        meta = lesson.get('meta')
        lesson = LessonMeta(
            id=meta.get('id'),
            title=info.get('title'),
            description=info.get('description'),
            updated_at=meta.get('updatedAt'),
        )
        lessons.append(lesson)

    collection = Collection(
        category=category,
        lessons=lessons
    )

    return collection


def parse_lesson(raw_document: dict) -> Lesson:
    fields = raw_document.get('fields')
    info = fields.get('info')
    content = fields.get('content')
    raw_quiz = fields.get('quiz')
    meta = raw_document.get('meta')

    quiz = parse_quiz(raw_quiz=raw_quiz)
    lesson = Lesson(
        id=meta.get('id'),
        title=info.get('title'),
        description=info.get('description'),
        updated_at=meta.get('updatedAt'),
        quiz=quiz,
        category=meta.get('contentType'),
        content=LessonContent(
            introduction=content.get('introduction'),
            sections=[EnvironmentSection(
                title=video.get('fields').get('title'),
                description=video.get('fields').get('description'),
                updated_at=video.get('meta').get('updatedAt'),
                video_url=video.get('fields').get('file').get('url'),
            ) for video in content.get('video')]
        )
    )

    return lesson


def parse_quiz(raw_quiz) -> Quiz:
    raw_questions = raw_quiz.get('questions')
    questions = []
    for raw_question in raw_questions:
        answers = raw_question.split("\n")
        question = answers.pop(0)
        correct_answer = ''
        choices = []
        for index, answer in zip(ALPHABET, answers):
            if answer.startswith('!'):
                answer = answer[1:]
                correct_answer = index
            choice = Choice(
                index=index,
                value=answer
            )
            choices.append(choice)

        question = Question(
            question=question,
            type=DEFAULT_QUIZZ_TYPE,
            correct_answer=correct_answer,
            choices=choices,
        )
        questions.append(question)

    quiz = Quiz(
        questions=questions
    )
    return quiz

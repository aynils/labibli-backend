from rest_framework import serializers


class FileUploadSerializer:
    file = serializers.FileField()

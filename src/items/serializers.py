from rest_framework import serializers

from items.models import Book, Category, Collection


class BookSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source='organization.name')

    class Meta:
        model = Book
        fields = [
            "archived",
            "featured",
            "status",
            "author",
            "title",
            "isbn",
            "publisher",
            "picture",
            "lang",
            "published_year",
            "description",
            "categories",
            "collections",
            "organization",
        ]


class CategorySerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source='organization.name')

    class Meta:
        model = Category
        fields = [
            "name",
            "organization",
        ]


class CollectionSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source='organization.name')

    class Meta:
        model = Collection
        fields = [
            "name",
            "organization",
        ]

from rest_framework import serializers

from customers.serializers import CustomerSerializer
from items.models import Book, Category, Collection, Lending


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
            # "collections",
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
    books = BookSerializer(source='book_set', many=True, read_only=True)

    class Meta:
        model = Collection
        fields = [
            "name",
            "organization",
            "books",
            "book_set"
        ]


class LendingSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source='organization.name')
    # customer = CustomerSerializer(source='customer', read_only=True)
    def to_representation(self, instance):
        self.fields['book'] = BookSerializer(read_only=False)
        self.fields['customer'] = CustomerSerializer(read_only=False)
        return super(LendingSerializer, self).to_representation(instance)

    class Meta:
        model = Lending
        fields = [
            "organization",
            "allowance_days",
            "lent_at",
            "returned_at",
            "book",
            "customer",
        ]

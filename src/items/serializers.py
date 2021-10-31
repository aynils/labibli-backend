from rest_framework import serializers

from customers.serializers import CustomerSerializer
from items.models import Book, Category, Collection, Lending


class CategorySerializer(serializers.ModelSerializer):
    # organization = serializers.ReadOnlyField(source='organization.name')
    id=serializers.CharField(max_length=255)
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
        ]


class BookSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source='organization.name')
    categories = serializers.ListSerializer(child=CategorySerializer(), read_only=False)
    isbn = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def to_representation(self, instance):
        response = super().to_representation(instance)
        response['categories'] = CategorySerializer(instance.categories, many=True).data
        return response

    def update(self, instance, validated_data):
        categories = validated_data.pop('categories')
        categories_ids = [category.get('id') for category in categories]
        instance.categories.set(Category.objects.filter(id__in=categories_ids))

        return super(BookSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        categories = validated_data.pop('categories')
        categories_ids = [category.get('id') for category in categories]
        instance = Book.objects.create(**validated_data)
        instance.categories.set(Category.objects.filter(id__in=categories_ids))
        instance.save()

        return instance

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
            "id",
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
    due_at = serializers.ReadOnlyField()
    is_past_due = serializers.ReadOnlyField()

    def to_representation(self, instance):
        self.fields['book'] = BookSerializer(read_only=False)
        self.fields['customer'] = CustomerSerializer(read_only=False)
        return super(LendingSerializer, self).to_representation(instance)

    def return_book(self, instance, returned_at):
        instance.returned_at = returned_at
        instance.save()
        return self.to_representation(instance)

    class Meta:
        model = Lending
        fields = [
            "organization",
            "allowance_days",
            "lent_at",
            "due_at",
            "returned_at",
            "book",
            "customer",
            "is_past_due",
            "id",
        ]



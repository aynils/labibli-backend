from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from rest_framework import serializers

from src.customers.serializers import CustomerSerializer
from src.helpers.query_params import is_true, positive_int
from src.items.models import Book, Category, Collection, Lending


class CategorySerializer(serializers.ModelSerializer):
    id = serializers.CharField(max_length=255, required=False)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
        ]


class BookSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source="organization.name")
    categories = serializers.ListSerializer(
        child=CategorySerializer(), read_only=False, required=False
    )

    isbn = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    # ⛔ Pas de `to_representation` qui re-sérialise `instance.categories` : le
    # champ `categories` déclaré ci-dessus le fait DÉJÀ, et à l'identique. Le
    # doublon coûtait deux requêtes par ouvrage — 48 sur une page de 24 — pour
    # écraser un résultat par le même.

    def update(self, instance, validated_data):
        categories = validated_data.pop("categories", [])
        categories_ids = [category.get("id") for category in categories]
        instance.categories.set(Category.objects.filter(id__in=categories_ids))
        instance.collections.set(
            Collection.objects.filter(
                organization=self.context.get("request").user.employee_of_organization
            )
        )
        validated_data.pop("collections", [])

        return super(BookSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        categories = validated_data.pop("categories", [])
        del validated_data["collections"]
        categories_ids = [category.get("id") for category in categories]
        instance = Book.objects.create(**validated_data)
        instance.categories.set(Category.objects.filter(id__in=categories_ids))

        # For now, we always set the org ID as collection ID as there is only one collection per org
        instance.collections.set(
            Collection.objects.filter(
                organization=self.context.get("request").user.employee_of_organization
            )
        )
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
            "inventory",
            "lang",
            "published_year",
            "description",
            "categories",
            "collections",
            "organization",
            "id",
            "location",
        ]


class CollectionSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source="organization.name")
    # ⚠️ Conservé le temps qu'aucun navigateur ne serve plus l'ancien bundle :
    # la modale d'emprunt le lisait. ⏳ À RETIRER — c'est l'adresse personnelle
    # de la propriétaire, et elle part à qui appelle l'API publique.
    organization_email = serializers.ReadOnlyField(source="organization.owner.email")
    # L'adresse que la bibliothèque a CHOISI de rendre publique.
    contact_email = serializers.ReadOnlyField(source="organization.contact_email")
    books = serializers.SerializerMethodField("paginated_books")

    def paginated_books(self, obj):
        request = self.context.get("request")
        query = request.query_params.get("query")
        available = request.query_params.get("available")
        category_ids = request.query_params.getlist("categoryId")
        # 🔴 Le cloisonnement est celui de `obj` : `obj.book_set` ne rend que
        # les ouvrages rattachés À CETTE collection, et une collection
        # appartient à une organisation. Ni le `select_related` ni les
        # `prefetch_related` ci-dessous n'élargissent cet ensemble : ils
        # ramènent en une requête ce que la sérialisation allait chercher
        # ouvrage par ouvrage.
        queryset = (
            obj.book_set.select_related("organization")
            .prefetch_related("categories", "collections")
            .with_lending_status()
            .order_by("-featured", "-created_at")
        )
        # Archivé vaut caché. La vitrine publique n'a même pas le droit de
        # demander le contraire : un ouvrage sorti de la circulation ne doit
        # pas être proposé à quelqu'un qui ne peut ni l'emprunter, ni savoir
        # pourquoi il est grisé. Le filtre est ici et non côté navigateur,
        # sinon la pagination compterait des ouvrages jamais affichés.
        show_archived = not self.context.get("public") and is_true(
            request.query_params.get("archived")
        )
        if not show_archived:
            queryset = queryset.exclude(archived=True)
        if query:
            queryset = queryset.filter(
                Q(title__unaccent__icontains=query)
                | Q(author__unaccent__icontains=query)
                | Q(isbn__unaccent__icontains=query)
            )
        if is_true(available):
            queryset = queryset.filter(
                Q(lendings__isnull=True) | Q(lendings__returned_at__isnull=False)
            )

        for category_id in category_ids:
            queryset = queryset.filter(categories__in=[category_id])

        page_size = positive_int(
            request.query_params.get("size"), settings.DEFAULT_BOOK_PAGE_SIZE
        )
        paginator = Paginator(queryset.all(), page_size)
        # La page demandée est ramenée dans les bornes plutôt que de lever.
        # Une vitrine publique reçoit des liens partagés et des numéros de
        # page tapés à la main, et masquer des ouvrages fait rétrécir la
        # pagination : une page hier valide rendait sinon une erreur 500.
        page = positive_int(request.query_params.get("page"), 1)
        page = min(page, paginator.num_pages)

        books = paginator.page(page)
        serializer = BookSerializer(books, many=True)

        collection_url = self.context["request"].build_absolute_uri(
            reverse("get_collection_shared", kwargs={"slug": obj.slug})
        )
        if page < paginator.num_pages:
            next = collection_url + f"?page={page+1}"
        else:
            next = None

        if page <= 1:
            previous = None
        else:
            previous = collection_url + f"?page={page-1}"

        return {
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "results": serializer.data,
            "previous": previous,
            "next": next,
        }

    class Meta:
        model = Collection
        fields = [
            # ⚠️ « id » est indispensable pour RENOMMER : sans lui, l'écran de
            # compte reçoit la collection mais n'a rien à mettre dans l'URL du
            # PATCH. Le champ de renommage ne s'affichait tout simplement pas,
            # sans erreur — il attendait un identifiant que l'API ne donnait
            # pas. C'est le genre d'absence qu'on cherche du mauvais côté.
            "id",
            "name",
            "organization",
            "books",
            "slug",
            "organization_email",
            "contact_email",
        ]


class LendingSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source="organization.name")
    due_at = serializers.ReadOnlyField()
    is_past_due = serializers.ReadOnlyField()

    def to_representation(self, instance):
        self.fields["book"] = BookSerializer(read_only=False)
        self.fields["customer"] = CustomerSerializer(read_only=False)
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

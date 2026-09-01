from rest_framework import serializers

from src.customers.models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    organization = serializers.ReadOnlyField(source="organization.name")
    # Un membre se retire par DELETE et se réinscrit en le rajoutant : ce
    # drapeau est le résultat de ces deux gestes, jamais leur commande. En
    # écriture, un PATCH pourrait sinon masquer un membre sans passer par
    # `perform_destroy`, donc sans le commentaire qui explique pourquoi on ne
    # supprime pas.
    is_active = serializers.BooleanField(read_only=True)

    def validate(self, attrs):
        """Rend un 400 lisible là où la base rendait un 500.

        DRF ne génère PAS de `UniqueTogetherValidator` pour
        `Customer.Meta.unique_together` : il n'en pose un que si tous les
        champs de la contrainte sont inscriptibles, or `organization` est un
        `ReadOnlyField`. La collision partait donc en `IntegrityError` nue —
        « duplicate key value violates unique constraint
        customers_customer_organization_id_first_na_… » — c'est-à-dire un 500
        pour une bibliothèque qui corrige simplement un courriel.

        Deux règles, et la distinction compte :

        - à l'**inscription**, seule une fiche ACTIVE fait conflit. Une fiche
          retirée n'en est pas un : `CustomersList.perform_create` la
          réinscrit, et la refuser ici casserait précisément ce rattrapage ;
        - à l'**édition**, toute autre fiche fait conflit, retirée comprise :
          la contrainte de la base, elle, ne fait pas le tri.
        """
        request = self.context.get("request")
        organization = getattr(
            getattr(request, "user", None), "employee_of_organization", None
        )
        if organization is None:
            return attrs

        def value(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None)

        first_name, last_name = value("first_name"), value("last_name")
        if not first_name or not last_name:
            return attrs

        for field in ("email", "phone"):
            current = value(field)
            if not current:
                # Deux NULL sont distincts en Postgres : sans valeur, la
                # contrainte ne se déclenche pas, il n'y a rien à refuser.
                continue
            # 🔴 Le filtre porte l'organisation : sans elle, on refuserait
            # un membre inscrit dans une AUTRE bibliothèque.
            clash = Customer.objects.filter(
                organization=organization,
                first_name=first_name,
                last_name=last_name,
                **{field: current},
            )
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            else:
                clash = clash.filter(is_active=True)
            if clash.exists():
                raise serializers.ValidationError(
                    {
                        field: [
                            "Un membre portant ce nom et ce contact est déjà "
                            "inscrit dans votre bibliothèque."
                        ]
                    }
                )
        return attrs

    class Meta:
        model = Customer
        fields = [
            "organization",
            "is_active",
            "first_name",
            "last_name",
            "email",
            "phone",
            "language",
            "note",
            "id",
        ]

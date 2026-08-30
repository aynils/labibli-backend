"""Jouer un import ligne à ligne et en rendre un compte rendu exploitable.

Ce module ne sait rien des livres ni des membres : il tient la mécanique que
les deux partagent — le cloisonnement par organisation, le dédoublonnage, le
décompte, et surtout la LISTE de ce qui n'est pas passé. Une bibliothécaire
qui importe mille lignes n'a que faire d'un total : ce qu'il lui faut, c'est
les lignes à reprendre.
"""
from dataclasses import dataclass, field


@dataclass
class ImportReport:
    created: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    not_found: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def as_dict(self) -> dict:
        """Le rapport tel qu'il part vers l'interface.

        Les listes sont conservées À CÔTÉ des totaux, jamais remplacées par
        eux : c'est la liste des échecs qui permet de reprendre l'import.
        """
        return {
            "created": self.created,
            "duplicates": self.duplicates,
            "not_found": self.not_found,
            "errors": self.errors,
            "created_count": len(self.created),
            "duplicates_count": len(self.duplicates),
            "not_found_count": len(self.not_found),
            "errors_count": len(self.errors),
            "total": len(self.created) + len(self.duplicates) + len(self.not_found) + len(self.errors),
        }


class Importer:
    """Ce qu'un import doit savoir faire de ses propres lignes.

    Les quatre méthodes sont le seul endroit où l'on parle de livres ou de
    membres ; tout le reste est commun.
    """

    columns = ()

    def label(self, record) -> str:
        """Comment nommer cette ligne dans le compte rendu."""
        raise NotImplementedError

    def dedupe_keys(self, record) -> list:
        """Clés qui font de cette ligne un doublon si elles existent déjà.

        Plusieurs clés sont possibles : un membre est un doublon par courriel
        OU par téléphone, comme le dit `Customer.Meta.unique_together`.
        """
        raise NotImplementedError

    def existing_keys(self, organization_id) -> set:
        """Toutes les clés DÉJÀ en base pour cette organisation, en une requête.

        Chargées une fois avant la boucle : un `exists()` par ligne coûtait
        une requête par ouvrage, soit des milliers sur une collection entière.
        """
        raise NotImplementedError

    def build(self, record, organization_id):
        """Rend l'objet à enregistrer, ou None si la ligne reste introuvable.

        L'implémentation DOIT poser `organization_id` elle-même : rien de ce
        que produit un import ne doit exister hors d'une organisation.
        """
        raise NotImplementedError


def run_import(records, importer, organization_id) -> ImportReport:
    """Joue l'import et rend le compte rendu.

    Le dédoublonnage regarde deux choses : ce que l'organisation possède
    déjà, et ce que le fichier lui-même contient en double — un inventaire
    tenu à la main en compte toujours (87 fiches redondantes chez l'Alliance
    Française de Siem Reap), et rien en base ne les arrêterait tant que
    l'ISBN est absent.
    """
    if not organization_id:
        raise ValueError("Un import se fait toujours dans une organisation.")

    report = ImportReport()
    seen = set(importer.existing_keys(organization_id))

    for record in records:
        name = importer.label(record)
        keys = [key for key in importer.dedupe_keys(record) if key]
        if any(key in seen for key in keys):
            report.duplicates.append(name)
            continue
        try:
            created = importer.build(record, organization_id)
        except Exception as error:
            report.errors.append({"line": name, "reason": str(error)})
            continue
        if created is None:
            report.not_found.append(name)
            continue
        seen.update(keys)
        report.created.append(name)
    return report

"""Jouer un import ligne à ligne et en rendre un compte rendu exploitable.

Ce module ne sait rien des livres ni des membres : il tient la mécanique que
les deux partagent — le cloisonnement par organisation, le dédoublonnage, le
décompte, et surtout la LISTE de ce qui n'est pas passé. Une bibliothécaire
qui importe mille lignes n'a que faire d'un total : ce qu'il lui faut, c'est
les lignes à reprendre.

🔑 **Une ligne déjà connue n'est plus un cul-de-sac.** Jusqu'au 01/09/2026, une
ligne dont la clé existait déjà partait en « doublon » et rien n'était comparé.
Une bibliothécaire qui corrigeait ses éditeurs dans son tableur et renvoyait le
fichier recevait « 862 doublons » et pas une seule de ses corrections — perdues
en silence, sous une étiquette qui a l'air normale. C'est pire que l'écrasement,
qui au moins fait quelque chose et le dit.

⛔ La règle qui rend le complément sûr, et qui permet qu'il soit actif par
défaut : **on ne remplit que les vides.** Un champ déjà rempli n'est jamais
touché ; quand le fichier le contredit, l'écart est SIGNALÉ et la décision reste
à la bibliothèque. Aucune perte n'est possible, même si un vieux fichier est
renvoyé par erreur.
"""
from dataclasses import dataclass, field


@dataclass
class ImportReport:
    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    not_found: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    discrepancies: list = field(default_factory=list)

    def as_dict(self) -> dict:
        """Le rapport tel qu'il part vers l'interface.

        Les listes sont conservées À CÔTÉ des totaux, jamais remplacées par
        eux : c'est la liste des échecs qui permet de reprendre l'import.

        ⚠️ `total` compte les SORTS, et une ligne n'en a qu'un. Les écarts
        n'en sont pas un : une même ligne peut être complétée sur l'éditeur
        et signalée sur l'auteur. Les compter dans le total ferait un rapport
        dont les nombres ne s'additionnent pas.
        """
        return {
            "created": self.created,
            "updated": self.updated,
            "duplicates": self.duplicates,
            "not_found": self.not_found,
            "errors": self.errors,
            "discrepancies": self.discrepancies,
            "created_count": len(self.created),
            "updated_count": len(self.updated),
            "duplicates_count": len(self.duplicates),
            "not_found_count": len(self.not_found),
            "errors_count": len(self.errors),
            "discrepancies_count": len(self.discrepancies),
            "total": (
                len(self.created) + len(self.updated) + len(self.duplicates)
                + len(self.not_found) + len(self.errors)
            ),
        }


class AlreadyPresent(Exception):
    """La ligne désigne un ouvrage que l'organisation possède déjà.

    Elle n'est levée qu'APRÈS la résolution : le fichier ne portait pas
    d'ISBN, on en a retrouvé un, et c'est lui qui révèle le doublon. Avant
    le 31/08/2026 ces lignes partaient en `IntegrityError` — dix-neuf pavés
    d'erreur Postgres dans le compte rendu d'une bibliothèque qui renvoyait
    simplement son fichier après y avoir ajouté vingt titres.
    """


def fill_blanks(existing, record, fields, dry_run=False):
    """Recopie les champs du fichier dans ceux de l'objet qui sont VIDES.

    Le seul endroit du dépôt où l'on décide ce que « compléter » veut dire ;
    les deux imports s'en servent, la règle ne peut donc pas diverger de
    l'un à l'autre.

    Rend `(remplis, écarts)` :

    - **remplis** — les champs qui étaient vides et que le fichier a remplis ;
    - **écarts** — les champs déjà remplis dont le fichier dit autre chose.
      ⛔ Ils ne sont PAS écrits. On les nomme pour que la bibliothèque
      tranche : nous ne savons pas si son fichier est une correction ou une
      vieille copie, et deviner à sa place est précisément ce qui fait perdre
      du travail.

    N'enregistre rien : l'appelant décide, et un mode à blanc coûte donc zéro
    ligne de code en plus.
    """
    remplis, ecarts = {}, []
    for champ in fields:
        depuis_le_fichier = record.get(champ)
        if depuis_le_fichier in (None, ""):
            # Une colonne absente ou vide ne veut jamais dire « efface ».
            continue
        actuel = getattr(existing, champ, None)
        if actuel in (None, ""):
            remplis[champ] = depuis_le_fichier
            if not dry_run:
                setattr(existing, champ, depuis_le_fichier)
        elif str(actuel).strip() != str(depuis_le_fichier).strip():
            ecarts.append({
                "field": champ,
                "existing": actuel,
                "file": depuis_le_fichier,
            })
    return remplis, ecarts


class Importer:
    """Ce qu'un import doit savoir faire de ses propres lignes.

    Les méthodes ci-dessous sont le seul endroit où l'on parle de livres ou
    de membres ; tout le reste est commun.
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

    def existing_objects(self, organization_id) -> dict:
        """Les objets DÉJÀ en base pour cette organisation, indexés par clé.

        Une seule requête, avant la boucle : un `exists()` par ligne coûtait
        une requête par ouvrage, soit des milliers sur une collection
        entière.

        🔴 C'est l'OBJET qui est rendu, pas seulement sa clé. Sans lui il n'y
        a rien à compléter : on ne peut que constater le doublon et jeter la
        ligne, ce que faisait ce module jusqu'au 01/09/2026.
        """
        raise NotImplementedError

    def same(self, existing, record) -> bool:
        """L'objet trouvé par la clé est-il VRAIMENT celui de cette ligne ?

        Une clé peut mentir. En production, six ISBN de la seule collection de
        Siem Reap sont portés par plusieurs fiches distinctes : la résolution
        par titre a donné à « Durandal 1, 2 et 3 » l'ISBN du tome 1. Tant que
        ces lignes étaient jetées, la donnée fausse dormait ; les compléter
        écrirait le contenu d'un tome sur un autre, sans lever d'erreur.

        Par défaut on fait confiance à la clé — c'est le cas des membres, dont
        les clés portent déjà le nom.
        """
        return True

    def merge(self, existing, record, dry_run=False):
        """Complète l'objet déjà en base avec ce que le fichier ajoute.

        Rend `(remplis, écarts)`, comme `fill_blanks`. ⛔ Ne remplit QUE les
        champs vides, et ne retire jamais rien : ni une catégorie, ni une
        couverture, ni un état.

        Par défaut, un import ne sait rien compléter — c'est le comportement
        d'avant, et il reste celui d'un importateur qui ne le redéfinit pas.
        """
        return {}, []

    def build(self, record, organization_id):
        """Rend l'objet à enregistrer, ou None si la ligne reste introuvable.

        L'implémentation DOIT poser `organization_id` elle-même : rien de ce
        que produit un import ne doit exister hors d'une organisation. Elle
        lève `AlreadyPresent` si la résolution révèle un doublon que les clés
        de la ligne ne montraient pas.
        """
        raise NotImplementedError

    def created_keys(self, created) -> list:
        """Les clés de l'objet RÉELLEMENT écrit.

        Elles peuvent différer de celles de la ligne : un ISBN retrouvé pour
        deux titres du même auteur ferait entrer le second en collision avec
        le premier, dans le même fichier. Par défaut, rien de plus que les
        clés de la ligne.
        """
        return []


def run_import(
    records, importer, organization_id, on_progress=None, complete=True, dry_run=False
) -> ImportReport:
    """Joue l'import et rend le compte rendu.

    `on_progress` est appelé après chaque ligne avec son rang, le total et
    le sort qui lui a été réservé. Un import de collection entière dure plus
    d'une heure : sans ça, il est aveugle jusqu'à la dernière ligne.

    Le dédoublonnage regarde deux choses : ce que l'organisation possède
    déjà, et ce que le fichier lui-même contient en double — un inventaire
    tenu à la main en compte toujours (87 fiches redondantes chez l'Alliance
    Française de Siem Reap), et rien en base ne les arrêterait tant que
    l'ISBN est absent.

    🔑 Les deux se COMPLÈTENT désormais au lieu d'être jetées. Y compris à
    l'intérieur d'un même fichier : deux lignes du même ouvrage, l'une avec
    l'ISBN et l'autre avec la cote, ne s'annulent plus — la seconde achève la
    première. C'est le cas ordinaire des inventaires tenus au tableur.

    `complete=False` retrouve le comportement d'avant, pour rejouer un vieil
    import à l'identique. `dry_run=True` calcule tout et n'écrit rien.
    """
    if not organization_id:
        raise ValueError("Un import se fait toujours dans une organisation.")

    report = ImportReport()
    # 🔴 Clé -> OBJET, et non plus un simple ensemble de clés. Le
    # cloisonnement tient à `existing_objects`, qui filtre sur
    # l'organisation : c'est la seule requête de ce module qui lit la base.
    connus = dict(importer.existing_objects(organization_id))
    total = len(records)

    def announce(index, name, outcome):
        if not on_progress:
            return
        try:
            on_progress(index=index, total=total, label=name, outcome=outcome)
        except Exception:
            # L'affichage ne doit jamais coûter l'import : une console qui
            # refuse un caractère ou une sortie redirigée ferait perdre une
            # heure de travail et le compte rendu avec, en laissant des
            # lignes déjà écrites en base.
            pass

    # Les clés sous lesquelles chaque objet est actuellement rangé. Sans ce
    # registre, retirer une clé périmée demanderait de balayer tout l'index à
    # chaque ligne — quadratique sur un fichier de 3 000 titres.
    cles_de = {}

    def retenir(objet, secours=()):
        """(Re)range l'objet sous ses clés, pour la suite du fichier.

        🔴 Les clés d'INDEX, pas celles de recherche. Un ouvrage se cherche
        aussi par titre + auteur seuls, mais ne se range pas sous cette clé
        faible dès lors qu'il porte un éditeur : deux éditions du même titre
        s'y confondraient.

        Et les clés périmées sont RETIRÉES. Une fiche sans éditeur est rangée
        sous la clé faible ; le complément lui en donne un ; elle doit alors
        cesser de répondre à cette clé, sinon une troisième ligne portant un
        autre éditeur viendrait la compléter au lieu d'exister.
        """
        cles = [key for key in importer.created_keys(objet) if key]
        if not cles:
            # L'importateur ne se prononce pas : les clés de la ligne font foi.
            cles = [key for key in secours if key]
        for perimee in cles_de.get(id(objet), ()):
            if perimee not in cles and connus.get(perimee) is objet:
                del connus[perimee]
        cles_de[id(objet)] = cles
        for key in cles:
            connus[key] = objet

    for index, record in enumerate(records, 1):
        name = importer.label(record)
        keys = [key for key in importer.dedupe_keys(record) if key]
        connue = next((key for key in keys if key in connus), None)

        if connue is not None:
            deja_la = connus[connue]
            # ⚠️ La clé est connue mais l'objet peut ne pas l'être : un
            # importateur peut n'indexer que des clés. On ne complète alors
            # rien, mais on ne recrée SURTOUT pas — retomber dans la branche
            # de création dupliquerait la fiche en silence.
            if not complete or deja_la is None:
                report.duplicates.append(name)
                announce(index, name, "duplicate")
                continue
            if not importer.same(deja_la, record):
                # La clé correspond mais l'objet n'est pas le bon. On ne
                # complète rien, et surtout on ne CRÉE rien : la contrainte
                # d'unicité rendrait une erreur Postgres brute. La ligne est
                # un doublon, et l'écart dit pourquoi il faut aller voir.
                report.duplicates.append(name)
                report.discrepancies.append({
                    "line": name,
                    "field": "identité",
                    "existing": getattr(deja_la, "title", str(deja_la)),
                    "file": name,
                })
                announce(index, name, "duplicate")
                continue
            try:
                remplis, ecarts = importer.merge(deja_la, record, dry_run=dry_run)
            except Exception as error:
                report.errors.append({"line": name, "reason": str(error)})
                announce(index, name, "error")
                continue
            for ecart in ecarts:
                report.discrepancies.append({"line": name, **ecart})
            # La ligne apporte quelque chose, ou elle n'apporte rien : dans
            # le second cas c'est un doublon ordinaire, et il ne doit pas se
            # déguiser en modification. Un réimport à l'identique doit
            # afficher zéro complété, sans quoi le nombre ne veut rien dire.
            if remplis:
                report.updated.append({"line": name, "fields": remplis})
                announce(index, name, "updated")
            else:
                report.duplicates.append(name)
                announce(index, name, "duplicate")
            # L'objet est réindexé sur ses clés À JOUR : il vient peut-être
            # de gagner l'éditeur ou l'ISBN qui lui manquait, et ça change
            # sous quelles clés il doit répondre pour la suite du fichier.
            retenir(deja_la, keys)
            continue

        if dry_run:
            # ⚠️ On ne construit pas : `build` écrit, et interroge les
            # catalogues pour décider. Une ligne neuve est donc annoncée
            # comme entrante sans qu'on puisse promettre qu'elle trouvera
            # une notice — le mode à blanc sert à prouver qu'un réimport ne
            # duplique rien, pas à prédire un enrichissement.
            report.created.append(name)
            announce(index, name, "created")
            continue

        try:
            created = importer.build(record, organization_id)
        except AlreadyPresent:
            # Le doublon n'apparaît qu'une fois l'ISBN retrouvé : c'est un
            # doublon, pas une erreur, et le compte rendu doit le dire.
            report.duplicates.append(name)
            announce(index, name, "duplicate")
            continue
        except Exception as error:
            report.errors.append({"line": name, "reason": str(error)})
            announce(index, name, "error")
            continue
        if created is None:
            report.not_found.append(name)
            announce(index, name, "not_found")
            continue
        retenir(created, keys)
        report.created.append(name)
        announce(index, name, "created")
    return report

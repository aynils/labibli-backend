"""Les rappels de retard : à qui on écrit, et surtout à qui on n'écrit PAS.

Deux envois, deux destinataires, deux interrupteurs :

  * le RAPPEL part au membre en retard. Il engage la bibliothèque auprès de
    quelqu'un qui n'est pas notre client ;
  * le RÉCAPITULATIF part à la bibliothécaire. Il ne regarde qu'elle, et c'est
    lui que promet la page d'accueil : « on vous prévient quand un retour est
    en retard ».

⛔ Aucun des deux ne commande l'autre. Une bibliothèque qui surveille ses
retards sans encore oser écrire à ses membres est le cas NORMAL, pas
l'exception — c'est même par là qu'on commence quand on n'a jamais envoyé un
courriel à personne.

⚠️ Et une asymétrie assumée : le rappel a une fréquence, le récapitulatif
n'en a pas. Un rappel est une relance sur UN prêt, et il faut donc pouvoir
espacer les relances. Un récapitulatif est l'état des retards du JOUR : sa
cadence est celle de la tâche planifiée (8 h, heure de l'Est), et un réglage
de fréquence en plus du `cron` finirait par le contredire en silence — deux
horloges qui ne disent pas la même heure. Ce qu'il faut ici n'est pas une
fréquence, c'est une garantie de non-doublon, et elle est dans la base.

Ce module ne contient qu'une seule chose difficile, et ce n'est pas l'envoi
du courriel : c'est la SÉLECTION. Un rappel envoyé de travers ne lève aucune
erreur, ne remplit aucun journal d'incident et n'est vu par personne chez
nous — il est vu par une personne qui n'est pas notre cliente, au nom d'une
bibliothèque qui n'a rien demandé, et c'est elle qui l'apprend à sa
bibliothécaire. Il n'y a pas de rattrapage : un courriel parti est parti.

Les sept gardes, dans l'ordre où elles s'appliquent :

  1. l'organisation a ACTIVÉ les rappels. Éteint par défaut, pour les
     dix-sept organisations déjà en production ;
  2. l'organisation est active (`is_active`) — une bibliothèque suspendue
     n'écrit pas à ses membres ;
  3. 🔴 le prêt appartient à CETTE organisation. La garde qui compte le plus,
     et celle qui ne lèverait jamais d'erreur si elle sautait : la requête
     rendrait des prêts parfaitement valides, appartenant à quelqu'un
     d'autre ;
  4. le prêt n'est pas rendu (`returned_at` vide) ;
  5. l'échéance est passée. On prévient d'un RETARD, pas d'une échéance à
     venir — c'est ce que promet la page d'accueil ;
  6. le membre n'est pas archivé, et il a une adresse ;
  7. on ne lui a pas déjà écrit pour ce prêt dans la fenêtre de fréquence.

Et une règle d'écriture : un membre en retard sur quatre livres reçoit UN
courriel qui liste les quatre, pas quatre courriels. Ça se voit à l'usage,
et ça change la façon dont le rappel est reçu.
"""
import dataclasses
import datetime
from typing import List, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.timezone import now

from src.items.models import Lending, LendingReminder, LibrarianDigest

# La langue du MEMBRE, pas celle de l'organisation. Une Alliance Française
# tient sa collection en français et prête à des personnes qui ne le lisent
# pas encore : leur écrire dans la langue de la bibliothèque, c'est leur
# écrire dans une langue qu'elles apprennent tout juste.
LANGUES = ("fr", "en")
LANGUE_PAR_DEFAUT = "fr"


def normaliser_langue(valeur: Optional[str]) -> str:
    """« English », « en-CA », « EN » → « en ». Tout le reste → « fr ».

    Le champ est une chaîne libre saisie à la main, et il l'est depuis le
    début : la base contient « fr », « français », « En », et des vides.
    """
    if not valeur:
        return LANGUE_PAR_DEFAUT
    code = str(valeur).strip().lower().replace("_", "-")
    for langue in LANGUES:
        if code == langue or code.startswith(f"{langue}-"):
            return langue
    if code.startswith("en"):
        return "en"
    return LANGUE_PAR_DEFAUT


@dataclasses.dataclass
class RappelPrevu:
    """Un courriel, une personne, un ou plusieurs prêts en retard."""

    customer: object
    lendings: list

    @property
    def email(self) -> str:
        return self.customer.email

    @property
    def langue(self) -> str:
        return normaliser_langue(self.customer.language)


@dataclasses.dataclass
class Rapport:
    organization_name: str = ""
    organization_id: Optional[int] = None
    prevus: List[RappelPrevu] = dataclasses.field(default_factory=list)
    envoyes: int = 0
    prets_rappeles: int = 0
    echecs: List[str] = dataclasses.field(default_factory=list)
    inactive: bool = False
    desactive: bool = False


def prets_en_retard(organization, at=None) -> list:
    """TOUS les prêts en retard de CETTE organisation. Sans exception.

    C'est la vue de la bibliothécaire, et elle ne doit rien cacher : le membre
    archivé et le membre sans adresse ont eux aussi un livre qui n'est pas
    revenu. Ce sont même les seuls que le rappel automatique n'atteindra
    jamais, donc les seuls dont elle doive s'occuper à la main.

    ⚠️ L'échéance (`due_at`) n'est pas une colonne : elle se calcule à partir
    de `lent_at` et de `allowance_days`. Elle est donc filtrée en Python, et
    c'est assumé — le cloisonnement, lui, est fait par la BASE, en premier, et
    c'est le seul filtre dont dépend la sécurité.
    """
    at = at or now()
    lendings = (
        Lending.objects.filter(
            # 🔴 Le cloisonnement. Sans lui, cette fonction rend les prêts de
            # toutes les bibliothèques à la fois, sans lever la moindre erreur.
            organization=organization,
            returned_at__isnull=True,
        )
        .select_related("customer", "book")
        .order_by("customer_id", "lent_at")
    )
    # On prévient d'un RETARD, pas d'une échéance à venir.
    return [lending for lending in lendings if lending.due_at <= at]


def joignable(customer) -> bool:
    """Peut-on écrire à ce membre ?

    Deux façons de ne pas pouvoir, et les deux existent dans la base : une
    fiche archivée (on l'a sortie de la circulation, lui écrire est exactement
    ce que le geste voulait empêcher) et une fiche sans adresse (`email` est
    « blank=True, null=True », et une liste de membres réelle en comporte
    toujours). La chaîne d'espaces compte pour un vide : elle vient des
    imports de tableurs.
    """
    return not customer.archived and bool((customer.email or "").strip())


def prets_en_retard_a_rappeler(organization, at=None) -> list:
    """Les prêts dont le MEMBRE doit être relancé maintenant."""
    at = at or now()
    retards = [
        lending
        for lending in prets_en_retard(organization, at=at)
        if joignable(lending.customer)
    ]

    fenetre = at - datetime.timedelta(
        days=organization.member_reminder_frequency_days
    )

    # Les prêts déjà rappelés dans la fenêtre, en UNE requête.
    #
    # ⚠️ Un `.exists()` par prêt ferait une requête par prêt en retard. Sur
    # une collection de trois mille ouvrages, la tournée de nuit passerait
    # son temps à demander la même chose. La question se pose une fois.
    #
    # Le filtre porte l'organisation : il est vrai qu'un identifiant de prêt
    # est unique dans toute la base, si bien que le résultat serait le même
    # sans lui — mais il évite de rapatrier la trace des seize autres
    # bibliothèques pour la jeter ensuite, et il dit à la relecture où est
    # le cloisonnement.
    deja_rappeles = set(
        LendingReminder.objects.filter(
            organization=organization, sent_at__gt=fenetre
        ).values_list("lending_id", flat=True)
    )
    return [lending for lending in retards if lending.id not in deja_rappeles]


def grouper_par_membre(lendings) -> List[RappelPrevu]:
    """Un courriel par personne, pas un courriel par livre."""
    par_membre = {}
    for lending in lendings:
        par_membre.setdefault(lending.customer_id, []).append(lending)
    return [
        RappelPrevu(customer=prets[0].customer, lendings=prets)
        for prets in par_membre.values()
    ]


def contexte(rappel: RappelPrevu, organization) -> dict:
    return {
        "organization": organization,
        "customer": rappel.customer,
        "lendings": [
            {
                "title": lending.book.title,
                "author": lending.book.author,
                "due_at": lending.due_at,
                "days_late": (now() - lending.due_at).days,
            }
            for lending in rappel.lendings
        ],
    }


def envoyer_un_rappel(rappel: RappelPrevu, organization) -> None:
    """Construit et envoie LE courriel. Ne décide de rien."""
    langue = rappel.langue

    # 🔑 `translation.override` et pas seulement le nom du gabarit.
    #
    # Le filtre `date` de Django formate selon la langue ACTIVE, pas selon le
    # fichier dans lequel il se trouve. Sans cette bascule, le gabarit anglais
    # s'envoyait avec « due on août 18, 2026 » : la phrase en anglais, le mois
    # en français, dans le même souffle. Le réglage global du produit est
    # `fr-fr`, donc c'était le comportement par défaut, et il ne se voyait
    # nulle part ailleurs que dans le courriel lui-même.
    with translation.override(langue):
        sujet = render_to_string(
            f"rappels/rappel_{langue}_subject.txt", contexte(rappel, organization)
        ).strip()
        corps_texte = render_to_string(
            f"rappels/rappel_{langue}.txt", contexte(rappel, organization)
        )
        corps_html = render_to_string(
            f"rappels/rappel_{langue}.html", contexte(rappel, organization)
        )

    # ⛔ Aucun BCC. `authemail` met `EMAIL_BCC` sur tous ses courriels, ce qui
    # se défend pour une poignée d'inscriptions ; le faire ici copierait à
    # Aynils l'adresse de chaque membre de chaque bibliothèque, à chaque
    # rappel. C'est une fuite de données personnelles, et un envoi de masse
    # vers une seule boîte.
    message = EmailMultiAlternatives(
        subject=sujet,
        body=corps_texte,
        from_email=settings.EMAIL_FROM,
        to=[rappel.email],
        # La réponse va à la bibliothèque, pas à nous : c'est elle qui sait
        # si le livre a été rendu au comptoir sans être saisi.
        reply_to=[organization.owner.email] if organization.owner_id else None,
    )
    message.attach_alternative(corps_html, "text/html")
    message.send()


def envoyer_les_rappels(organization, at=None, dry_run=False) -> Rapport:
    """Le point d'entrée. Rend ce qui a été fait, et ce qui a échoué."""
    at = at or now()
    rapport = Rapport(
        organization_name=organization.name, organization_id=organization.id
    )

    if not organization.member_reminders_enabled:
        # 🔴 Le consentement de la bibliothèque. Il est vérifié ici ET dans la
        # sélection des organisations de la commande : deux fois, parce que
        # c'est la garde dont l'oubli se voit le moins et coûte le plus.
        rapport.desactive = True
        return rapport
    if not organization.is_active:
        rapport.inactive = True
        return rapport

    rapport.prevus = grouper_par_membre(
        prets_en_retard_a_rappeler(organization, at=at)
    )

    if dry_run:
        # ⛔ On sort AVANT la boucle. Rien n'est envoyé, rien n'est tracé — et
        # « rien » veut dire qu'on n'entre même pas dans le code qui envoie.
        return rapport

    for rappel in rapport.prevus:
        try:
            with transaction.atomic():
                # La trace est écrite AVANT l'envoi, dans la même transaction.
                # Si l'envoi lève, la transaction est annulée et la trace
                # disparaît : le rappel repartira au prochain passage. Dans
                # l'autre ordre, un envoi réussi suivi d'une panne d'écriture
                # ferait renvoyer le même courriel à chaque exécution.
                for lending in rappel.lendings:
                    LendingReminder.objects.create(
                        organization=organization,
                        lending=lending,
                        sent_at=at,
                        sent_on=at.date(),
                        to_email=rappel.email,
                        language=rappel.langue,
                    )
                envoyer_un_rappel(rappel, organization)
        except Exception as erreur:  # noqa: BLE001
            # Un membre dont l'envoi échoue ne doit pas coûter la tournée.
            rapport.echecs.append(f"{rappel.email} : {erreur}")
            continue
        rapport.envoyes += 1
        rapport.prets_rappeles += len(rappel.lendings)

    return rapport


# ═══════════════════════════════════════════════════════════════════════
#  Le récapitulatif à la bibliothécaire
# ═══════════════════════════════════════════════════════════════════════


@dataclasses.dataclass
class RapportRecap:
    organization_name: str = ""
    organization_id: Optional[int] = None
    retards: list = dataclasses.field(default_factory=list)
    destinataire: Optional[str] = None
    envoye: bool = False
    desactive: bool = False
    inactive: bool = False
    deja_envoye: bool = False
    sans_destinataire: bool = False
    echec: Optional[str] = None


def contexte_recapitulatif(organization, retards, at) -> dict:
    """Ce que la bibliothécaire doit voir, et rien de décoratif.

    `joignable` est calculé ici plutôt que dans le gabarit : c'est la colonne
    qui transforme une liste en liste de tâches. Les membres injoignables sont
    exactement ceux qu'aucun envoi automatique n'atteindra, donc les seuls sur
    lesquels elle doive faire quelque chose elle-même.
    """
    return {
        "organization": organization,
        "at": at,
        # ⚠️ On dit à la bibliothécaire si ses membres ont été prévenus ou
        # non. Sans cette ligne, un récapitulatif de douze retards se lit
        # comme un reproche alors que, l'interrupteur des membres étant
        # éteint, PERSONNE n'a été relancé et elle ne peut pas le deviner.
        "member_reminders_enabled": organization.member_reminders_enabled,
        "lendings": [
            {
                "title": lending.book.title,
                "author": lending.book.author,
                "customer": f"{lending.customer.first_name} {lending.customer.last_name}".strip(),
                "email": (lending.customer.email or "").strip(),
                "phone": (lending.customer.phone or "").strip(),
                "archived": lending.customer.archived,
                "joignable": joignable(lending.customer),
                "due_at": lending.due_at,
                "days_late": (at - lending.due_at).days,
            }
            for lending in retards
        ],
        "injoignables": [
            lending for lending in retards if not joignable(lending.customer)
        ],
    }


def envoyer_un_recapitulatif(organization, retards, at) -> None:
    """Construit et envoie LE courriel. Ne décide de rien."""
    contexte_rendu = contexte_recapitulatif(organization, retards, at)

    # 🔑 Le français, faute de mieux, et c'est une limite connue : la
    # bibliothécaire est un `User`, et `User` n'a PAS de champ de langue —
    # contrairement à `Customer`. On ne devine pas une langue, donc on prend
    # celle du produit (`LANGUAGE_CODE = "fr-fr"`). Le jour où une
    # bibliothèque anglophone s'abonne, c'est un champ à ajouter, pas un
    # gabarit à traduire dans l'urgence.
    with translation.override(LANGUE_PAR_DEFAUT):
        sujet = render_to_string(
            "rappels/recapitulatif_fr_subject.txt", contexte_rendu
        ).strip()
        corps_texte = render_to_string("rappels/recapitulatif_fr.txt", contexte_rendu)
        corps_html = render_to_string("rappels/recapitulatif_fr.html", contexte_rendu)

    # ⛔ Aucun BCC ici non plus : le récapitulatif porte le nom et l'adresse
    # de chaque membre en retard. C'est la pièce la plus sensible que ce
    # produit envoie, et elle ne part qu'à une seule personne.
    message = EmailMultiAlternatives(
        subject=sujet,
        body=corps_texte,
        from_email=settings.EMAIL_FROM,
        to=[organization.owner.email],
    )
    message.attach_alternative(corps_html, "text/html")
    message.send()


def envoyer_le_recapitulatif(organization, at=None, dry_run=False) -> RapportRecap:
    """Un seul courriel, à la bibliothécaire, avec les retards de SA maison.

    Les gardes, dans l'ordre — et la première est celle qui compte :

      1. 🔴 `librarian_digest_enabled`, et PAS `member_reminders_enabled`.
         Les deux interrupteurs sont indépendants ; les confondre ferait
         partir un envoi que personne n'a demandé, au motif qu'un AUTRE
         envoi, lui, a été autorisé ;
      2. l'organisation est active ;
      3. elle a une propriétaire, et cette propriétaire a une adresse ;
      4. il y a au moins un retard. Un récapitulatif vide est un courriel de
         plus dans une boîte déjà pleine, et c'est ainsi qu'on apprend aux
         gens à ne plus nous lire ;
      5. on n'en a pas déjà envoyé un aujourd'hui.
    """
    at = at or now()
    rapport = RapportRecap(
        organization_name=organization.name, organization_id=organization.id
    )

    if not organization.librarian_digest_enabled:
        rapport.desactive = True
        return rapport
    if not organization.is_active:
        rapport.inactive = True
        return rapport

    destinataire = ""
    if organization.owner_id:
        destinataire = (organization.owner.email or "").strip()
    if not destinataire:
        rapport.sans_destinataire = True
        return rapport
    rapport.destinataire = destinataire

    # 🔑 Le plus en retard d'abord. C'est une liste de tâches, pas un
    # journal : la bibliothécaire lit les trois premières lignes et agit.
    # Rendu dans l'ordre de la requête, le retard de quarante et un jours se
    # retrouvait coincé entre deux retards de trois jours.
    rapport.retards = sorted(
        prets_en_retard(organization, at=at), key=lambda lending: lending.due_at
    )
    if not rapport.retards:
        return rapport

    # 🔴 Le cloisonnement porte sur la trace AUSSI. Sans l'organisation ici,
    # le récapitulatif d'une bibliothèque empêcherait celui de toutes les
    # autres : une seule des dix-sept serait prévenue chaque matin, et les
    # seize autres n'auraient aucune erreur pour le leur dire.
    if LibrarianDigest.objects.filter(
        organization=organization, sent_on=at.date()
    ).exists():
        rapport.deja_envoye = True
        return rapport

    if dry_run:
        # ⛔ On sort AVANT l'envoi, pas dans une branche à l'intérieur.
        return rapport

    try:
        with transaction.atomic():
            # La trace est écrite AVANT l'envoi, dans la même transaction : si
            # l'envoi lève, tout est annulé et le récapitulatif repartira au
            # prochain passage. Dans l'autre ordre, un envoi réussi suivi
            # d'une panne d'écriture le referait partir chaque jour.
            LibrarianDigest.objects.create(
                organization=organization,
                sent_at=at,
                sent_on=at.date(),
                to_email=destinataire,
                lendings_count=len(rapport.retards),
            )
            envoyer_un_recapitulatif(organization, rapport.retards, at)
    except Exception as erreur:  # noqa: BLE001
        rapport.echec = f"{destinataire} : {erreur}"
        return rapport

    rapport.envoye = True
    return rapport

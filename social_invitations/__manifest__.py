{
    "name": "Social — Inviter (fiche + courriel)",
    "version": "20.0.1.0.0",
    "category": "Social / Communication",
    "summary": "Inviter à un groupe/cercle depuis une fiche ou par courriel, "
               "avec interception des membres existants",
    "description": """
Hub d'invitation (Phase 3, partie B). Ne modifie pas les modules du submodule
social : il s'y greffe.

- Bouton « Inviter… » sur la fiche d'un membre : liste mes groupes (où j'ai le
  droit d'inviter) et mes cercles ; crée une invitation in-site.
- Invitation par courriel :
  * courriel d'un membre existant → INTERCEPTION : on transforme en invitation
    in-site, aucun courriel envoyé, et l'inviteur n'apprend jamais que la
    personne est déjà membre (message identique dans tous les cas).
  * courriel inconnu → on enregistre l'intention (social_invitations.pending) et
    on déclenche l'invitation d'inscription (vouching). À l'inscription, l'invité
    reçoit l'invitation de groupe/cercle in-site (pas d'ajout silencieux).
    """,
    "author": "Bemade",
    "license": "LGPL-3",
    "depends": [
        "club_social_profile",
        "social_group",
        "social_circles",
        "social_safety",
        "social_reputation",
    ],
    "data": [
        "security/ir.access.csv",
        "data/cron.xml",
        "views/profile_invite_button.xml",
    ],
    "installable": True,
    "application": False,
}

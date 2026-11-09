"""Réparer le modèle d'invitation hérité d'Odoo 19.

Le modèle `auth_signup.set_password_email` est `noupdate` : la migration vers
Odoo 20 ne réécrit jamais son contenu, et les bases copiées depuis une instance
19 conservent l'expression d'origine :

    get_param('auth_signup.signup.validity.hours', 144)

`get_param` a disparu en Odoo 20 (ce sont `get_str` / `get_int` / …), donc
chaque invitation d'utilisateur levait une AttributeError — sans que rien ne le
signale, puisque créer un utilisateur n'est pas un geste quotidien.

Constaté le 2026-11-09 sur les trois bases de production.
"""

import logging

_logger = logging.getLogger(__name__)

ANCIEN = (
    "int(int(object.env['ir.config_parameter'].sudo()"
    ".get_param('auth_signup.signup.validity.hours',144))/24)"
)
NOUVEAU = (
    "(object.env['ir.config_parameter'].sudo()"
    ".get_int('auth_signup.signup.validity.hours') or 144)//24"
)


def migrate(cr, version):
    """Remplace l'expression fautive dans tous les gabarits de courriel."""
    cr.execute(
        """
        SELECT id FROM mail_template
        WHERE body_html::text LIKE %s
        """,
        ("%get_param(%",),
    )
    ids = [ligne[0] for ligne in cr.fetchall()]
    if not ids:
        _logger.info("Modèles d'invitation : rien à corriger.")
        return

    cr.execute(
        """
        UPDATE mail_template
        SET body_html = replace(body_html::text, %s, %s)::jsonb
        WHERE body_html::text LIKE %s
        """,
        (ANCIEN, NOUVEAU, "%get_param(%"),
    )
    _logger.info(
        "Modèles d'invitation réparés : %s (get_param → get_int).", ids
    )

    # Ce qui reste après le remplacement cible : un get_param écrit autrement.
    # On le signale sans le corriger à l'aveugle — le corriger supposerait de
    # connaître l'intention de l'auteur.
    cr.execute(
        """
        SELECT id, name->>'en_US' FROM mail_template
        WHERE body_html::text LIKE %s
        """,
        ("%get_param(%",),
    )
    restants = cr.fetchall()
    if restants:
        _logger.warning(
            "Modèles appelant encore get_param, à corriger à la main : %s",
            restants,
        )

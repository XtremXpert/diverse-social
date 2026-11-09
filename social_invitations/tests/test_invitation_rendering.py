from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInvitationRendering(TransactionCase):
    """Le courriel d'invitation doit se rendre à la création d'un utilisateur.

    Le 2026-11-09, les trois bases de production portaient encore la version
    Odoo 19 du modèle `auth_signup.set_password_email` :

        get_param('auth_signup.signup.validity.hours', 144)

    `get_param` n'existe plus en Odoo 20 (ce sont `get_str` / `get_int`), et le
    modèle est `noupdate` : la migration ne le réécrit jamais. Toute invitation
    d'utilisateur levait donc une AttributeError — silencieusement, puisque
    personne n'en crée tous les jours.

    Ce test crée un utilisateur avec un courriel : c'est exactement le chemin
    qui rend le modèle. Un modèle stocké en base redevenu invalide le fait
    échouer.
    """

    def test_creation_utilisateur_rend_l_invitation(self):
        user = self.env['res.users'].create({
            'name': 'Invité Test',
            'login': 'invite.test@example.invalid',
            'email': 'invite.test@example.invalid',
        })
        self.assertTrue(user.id)

    def test_le_modele_d_invitation_ne_contient_plus_get_param(self):
        """Garde-fou direct sur le contenu du modèle, pas seulement son rendu.

        Le rendu peut réussir par chance si le gabarit est vide ou si la branche
        fautive n'est pas évaluée ; l'expression, elle, ne doit simplement plus
        être là.
        """
        templates = self.env['mail.template'].search([
            ('model', '=', 'res.users'),
        ])
        fautifs = templates.filtered(
            lambda t: t.body_html and 'get_param(' in t.body_html
        )
        self.assertFalse(
            fautifs,
            "Modèles de courriel utilisateur appelant encore get_param, "
            "supprimé en Odoo 20 : %s" % ', '.join(fautifs.mapped('name')),
        )

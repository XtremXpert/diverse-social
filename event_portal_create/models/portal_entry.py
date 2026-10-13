from odoo import models

_GROUP = "event_portal_create.group_event_portal_organiser"


class PortalEntry(models.Model):
    """Odoo 20 : les cartes /my sont des enregistrements ; leur visibilité selon
    le groupe de l'utilisateur (organisateur ou non) se règle ici plutôt que par
    un t-if dans le gabarit."""

    _inherit = "portal.entry"

    def _filter_visible_portal_cards(self):
        cards = super()._filter_visible_portal_cards()
        is_organiser = self.env.user.has_group(_GROUP)
        hidden = self.env.ref(
            "event_portal_create.portal_entry_my_become_organiser"
            if is_organiser
            else "event_portal_create.portal_entry_my_events",
            raise_if_not_found=False,
        )
        return cards - hidden if hidden else cards

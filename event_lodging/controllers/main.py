import logging

from odoo.addons.website_event.controllers.main import WebsiteEventController
from odoo.http import request

_logger = logging.getLogger(__name__)


class WebsiteEventLodging(WebsiteEventController):

    def _process_tickets_form(self, event, form_details):
        """Ajoute lodging_type dans chaque entrée du résultat."""
        tickets = super()._process_tickets_form(event, form_details)
        for ticket_entry in tickets:
            ticket = ticket_entry.get('ticket')
            ticket_entry['lodging_type'] = ticket.lodging_type if ticket else 'none'
        return tickets

    def _process_attendees_form(self, event, form_details):
        """Extrait les champs partenaire 2 (non-standard) avant le traitement
        standard qui n'accepte que des entiers pour les clés à 2 segments."""
        partner2_by_index = {}
        clean_form = {}
        for key, value in form_details.items():
            parts = key.split('-')
            if len(parts) == 2 and parts[1] in ('partner2_name', 'partner2_email'):
                partner2_by_index.setdefault(parts[0], {})[parts[1]] = value
            else:
                clean_form[key] = value

        registrations = super()._process_attendees_form(event, clean_form)

        # Réinjecter les données partenaire 2 par position (index commence à 1)
        for i, reg in enumerate(registrations, start=1):
            p2 = partner2_by_index.get(str(i), {})
            if p2:
                reg['_partner2_name'] = p2.get('partner2_name', '')
                reg['_partner2_email'] = p2.get('partner2_email', '')

        return registrations

    def _create_attendees_from_registration_post(self, event, registration_data):
        """Convertit les données texte partenaire 2 en res.partner (find or create)."""
        Partner = request.env['res.partner'].sudo()

        for reg in registration_data:
            name = reg.pop('_partner2_name', None)
            email = reg.pop('_partner2_email', None)
            if not name:
                continue

            # Chercher un partenaire existant par email (comparaison exacte
            # insensible à la casse, qui est la norme pour les emails).
            if email:
                partners = Partner.search([('email', '=ilike', email)])
                if len(partners) > 1:
                    _logger.warning(
                        'event_lodging: %d partenaires trouvés pour l\'email %s — '
                        'le premier est utilisé.',
                        len(partners), email,
                    )
                partner = partners[:1]
            else:
                partner = Partner.browse()

            if not partner:
                partner = Partner.create({'name': name, 'email': email or False})
            elif partner.name != name:
                # Le nom fourni diffère du nom existant — on ne l'écrase pas
                # pour éviter de corrompre un enregistrement existant.
                _logger.info(
                    'event_lodging: partenaire %s (id=%d) trouvé par email %s '
                    'avec un nom différent ("%s" vs "%s") — nom existant conservé.',
                    partner.name, partner.id, email, name, partner.name,
                )

            reg['partner2_id'] = partner.id

        return super()._create_attendees_from_registration_post(event, registration_data)

from odoo import http
from odoo.http import request
from odoo.addons.website_event.controllers.main import WebsiteEvent


class WebsiteEventClub(WebsiteEvent):

    def _create_attendees_from_registration_post(self, event, registration_data):
        """Quand user_id est soumis, remplir automatiquement name (login),
        partner_id et email à partir du membre sélectionné.
        """
        for reg_vals in registration_data:
            user_id = reg_vals.get('user_id')
            if not user_id:
                continue
            user = request.env['res.users'].sudo().browse(user_id)
            if user.exists() and not user.share:
                reg_vals['name'] = user.login
                reg_vals['partner_id'] = user.partner_id.id
                reg_vals['email'] = reg_vals.get('email') or user.email
        return super()._create_attendees_from_registration_post(event, registration_data)

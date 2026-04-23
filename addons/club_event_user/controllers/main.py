from odoo import http
from odoo.http import request
from odoo.addons.website_event.controllers.main import WebsiteEvent


class WebsiteEventClub(WebsiteEvent):

    def _create_attendees_from_registration_post(self, event, registration_data):
        """Résoudre le login soumis dans 'name' vers un res.users.
        Remplace partner_id par le partenaire du membre et stocke user_id.
        """
        for reg_vals in registration_data:
            login = reg_vals.get('name', '').strip()
            if not login:
                continue
            user = request.env['res.users'].sudo().search(
                [('login', '=', login), ('share', '=', False), ('active', '=', True)],
                limit=1,
            )
            if user:
                reg_vals['user_id'] = user.id
                reg_vals['partner_id'] = user.partner_id.id
                reg_vals['email'] = reg_vals.get('email') or user.email
                reg_vals['name'] = user.login  # s'assurer que c'est bien le login stocké
        return super()._create_attendees_from_registration_post(event, registration_data)

from odoo import http
from odoo.addons.website_event.controllers.main import WebsiteEventController
from odoo.http import request


class WebsiteEventMembersOnly(WebsiteEventController):

    def _redirect_if_login_required(self):
        """Redirige vers la page de connexion si l'accès aux événements est restreint."""
        if request.website.event_login_required and request.env.user._is_public():
            redirect_url = request.httprequest.full_path
            return request.redirect(f'/web/login?redirect={redirect_url}')
        return None

    def events(self, **kwargs):
        redirect = self._redirect_if_login_required()
        if redirect:
            return redirect
        return super().events(**kwargs)

    def event(self, event, **post):
        redirect = self._redirect_if_login_required()
        if redirect:
            return redirect
        return super().event(event, **post)

    def event_page(self, event, page, **post):
        redirect = self._redirect_if_login_required()
        if redirect:
            return redirect
        return super().event_page(event, page, **post)

    def event_register(self, event, **post):
        redirect = self._redirect_if_login_required()
        if redirect:
            return redirect
        return super().event_register(event, **post)

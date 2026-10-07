from markupsafe import Markup

from odoo import _, http
from odoo.http import request


_DEFAULT_CHARTER_HTML = (
    "<p><em>No community charter has been configured yet. "
    "Set <code>social_help.charter_html</code> in System Parameters.</em></p>"
)


class CommunityHelp(http.Controller):

    @http.route('/community/help', auth='public', website=True, sitemap=True)
    def community_help(self, **kw):
        Param = request.env['ir.config_parameter'].sudo()
        community_name = (
            Param.get_str('social_help.community_name')
            or _('this community')
        )
        charter_html = (
            Param.get_str('social_help.charter_html')
            or _DEFAULT_CHARTER_HTML
        )
        return request.render('social_help.community_help_page', {
            'community_name': community_name,
            'charter_html': Markup(charter_html),
        })

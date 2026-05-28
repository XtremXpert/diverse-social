from odoo import models
from odoo.http import request

from ..utils import is_sensitive_path


class IrHttp(models.AbstractModel):
    """Adds X-Robots-Tag: noindex on responses for sensitive paths.

    Companion to the <meta name="robots"> tag in
    portal_share_lockdown.xml. The meta covers search engines that
    parse HTML; this header covers consumers that *only* look at
    headers — notably Slack, Discord, Signal and iMessage link
    unfurlers, plus a number of corporate crawlers. Without this, a
    member who pastes /my/profile/edit into a public Slack channel
    still triggers a preview fetch even though the meta says noindex.
    """
    _inherit = 'ir.http'

    @classmethod
    def _post_dispatch(cls, response):
        super()._post_dispatch(response)
        if not response:
            return
        try:
            path = request.httprequest.path
        except Exception:
            return
        if is_sensitive_path(path):
            response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'

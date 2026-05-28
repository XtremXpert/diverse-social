from odoo import api, models

from ..utils import is_sensitive_path


class SocialSafetyHelper(models.AbstractModel):
    """QWeb-accessible helper exposing path classification.

    The plain Python helper lives in utils.py (importable from anywhere
    in the addon). This AbstractModel is the bridge so templates can do
    `env['social_safety.helper'].is_sensitive_path(...)` without
    awkward __import__ tricks.
    """
    _name = 'social_safety.helper'
    _description = 'Social safety helpers (path classification, …)'

    @api.model
    def is_sensitive_path(self, path):
        return is_sensitive_path(path)

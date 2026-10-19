from odoo import fields, models


class DiscussCallHistory(models.Model):
    _inherit = 'discuss.call.history'

    involved_member_ids = fields.Many2many(
        'discuss.channel.member',
        'social_call_history_involved_member_rel',
        'history_id',
        'member_id',
        string="Personnes impliquées",
        help="Membres qui ont participé à l'appel ou y ont été invités. Tant qu'ils ne sont "
             "pas plus de deux, l'appel se termine quand il ne reste qu'une personne.",
    )

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Maximum number of free-text "developed" answers per member — keeps the form simple.
MAX_DETAILS = 5
DETAIL_MAX_CHARS = 300


class SocialEssenceQuestion(models.Model):
    """A catalogued questionnaire item, administrable by the club (no release needed)."""

    _name = 'social_essence.question'
    _description = 'Question du questionnaire essence'
    _order = 'section, sequence, id'

    name = fields.Char("Question", required=True, translate=True)
    section = fields.Selection([
        ('place', 'Place sur l\'application'),
        ('libertinage', 'Libertinage'),
        ('bdsm', 'BDSM'),
        ('lgbt', 'Identité et préférences'),
    ], required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    # Whether this item may carry one of the member's few free-text developments.
    allow_detail = fields.Boolean("Champ à développer permis", default=True)


class SocialEssenceSheet(models.Model):
    """One sheet per member: the hard-limit note and questionnaire completion."""

    _name = 'social_essence.sheet'
    _description = 'Fiche essence du membre'

    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True,
                              ondelete='cascade')
    hard_limit_text = fields.Char(
        "Limites absolues (une phrase)",
        help="Obligatoire si au moins une réponse « jamais » ; 300 caractères maximum.")
    answer_ids = fields.One2many('social_essence.answer', 'sheet_id', "Réponses")

    _user_uniq = models.Constraint('UNIQUE(user_id)', "Une seule fiche essence par membre.")

    @api.model
    def _mine(self):
        sheet = self.sudo().search([('user_id', '=', self.env.uid)], limit=1)
        return sheet or self.sudo().create({'user_id': self.env.uid})

    def _as_dict(self):
        self.ensure_one()
        return {
            'hard_limit_text': self.hard_limit_text or '',
            'needs_hard_limit': bool(self.answer_ids.filtered(lambda a: a.value == 'never'))
                                  and not self.hard_limit_text,
            'answers': [a._as_dict() for a in self.answer_ids],
        }


class SocialEssenceAnswer(models.Model):
    """A member's answer to one question: only / open / never, plus an optional short
    free-text development (at most MAX_DETAILS per member)."""

    _name = 'social_essence.answer'
    _description = 'Réponse essence'

    sheet_id = fields.Many2one('social_essence.sheet', required=True, index=True,
                               ondelete='cascade')
    question_id = fields.Many2one('social_essence.question', required=True, readonly=True,
                                  ondelete='cascade')
    section = fields.Selection(related='question_id.section', store=True, index=True)
    value = fields.Selection([
        ('only', 'Seulement ça'),
        ('open', 'Ouvert à ça'),
        ('never', 'Jamais ça'),
    ], required=True)
    detail = fields.Char("Détail", help="Une phrase, %s caractères maximum." % DETAIL_MAX_CHARS)

    _sheet_question_uniq = models.Constraint(
        'UNIQUE(sheet_id, question_id)', "Une réponse par question et par membre.")

    @api.constrains('detail')
    def _check_detail_budget(self):
        for rec in self:
            if rec.detail and len(rec.detail) > DETAIL_MAX_CHARS:
                raise ValidationError(_("Détail limité à %s caractères.", DETAIL_MAX_CHARS))
            if rec.detail:
                count = self.search_count([
                    ('sheet_id', '=', rec.sheet_id.id), ('detail', '!=', False),
                ])
                if count > MAX_DETAILS:
                    raise ValidationError(
                        _("Au plus %s réponses peuvent être développées.", MAX_DETAILS))

    @api.constrains('detail', 'question_id')
    def _check_detail_allowed(self):
        for rec in self.filtered(lambda r: r.detail and not r.question_id.allow_detail):
            raise ValidationError(_("Cette question n'accepte pas de détail."))

    def _as_dict(self):
        self.ensure_one()
        return {'id': self.id, 'question_id': self.question_id.id,
                'section': self.section, 'value': self.value, 'detail': self.detail or ''}

    @api.model
    def _api_set(self, question_id, value, detail=''):
        """Upsert the current member's answer to ``question_id``."""
        sheet = self.env['social_essence.sheet']._mine()
        if value not in ('only', 'open', 'never'):
            raise ValidationError(_("Réponse invalide : only, open ou never."))
        answer = self.sudo().search([('sheet_id', '=', sheet.id), ('question_id', '=', question_id)],
                                    limit=1)
        vals = {'value': value, 'detail': (detail or '')[:DETAIL_MAX_CHARS]}
        if answer:
            answer.write(vals)
        else:
            self.sudo().create(dict(vals, sheet_id=sheet.id, question_id=question_id))
        return sheet

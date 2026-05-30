from odoo import models, fields, api, _
from datetime import timedelta


class PrivacyRetentionRule(models.Model):
    _name = 'social_privacy.retention.rule'
    _description = 'Privacy Data Retention Rule'
    _order = 'sequence'

    name = fields.Char(string='Rule Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)

    target_model = fields.Char(
        string='Target Model',
        required=True,
        help='Technical name of the model this rule applies to (e.g. social_base.post)',
    )
    retention_days = fields.Integer(
        string='Retention Period (Days)',
        required=True,
        default=365,
        help='Number of days before the action is applied.',
    )
    action = fields.Selection([
        ('delete', 'Delete'),
        ('archive', 'Archive'),
        ('anonymize', 'Anonymize'),
    ], string='Action', required=True, default='archive')

    date_field = fields.Char(
        string='Date Field',
        default='create_date',
        required=True,
        help='Field on the target model used to compute age (e.g. create_date, write_date).',
    )

    state_filter = fields.Char(
        string='State Filter Domain',
        help='Optional domain to restrict records (e.g. [("state", "=", "published")]).',
    )

    last_run = fields.Datetime(string='Last Run')
    processed_count = fields.Integer(string='Records Processed (Last Run)', readonly=True)

    @api.model
    def cron_apply_retention_rules(self):
        now = fields.Datetime.now()
        for rule in self.search([('active', '=', True)]):
            cutoff = now - timedelta(days=rule.retention_days)
            Model = self.env.get(rule.target_model)
            if not Model:
                continue
            domain = [(rule.date_field, '<=', cutoff)]
            if rule.state_filter:
                try:
                    import ast
                    extra_domain = ast.literal_eval(rule.state_filter)
                    if isinstance(extra_domain, list):
                        domain.extend(extra_domain)
                except (ValueError, SyntaxError):
                    pass
            records = Model.search(domain)
            count = len(records)
            if count:
                if rule.action == 'delete':
                    records.unlink()
                elif rule.action == 'archive':
                    records.write({'active': False}) if hasattr(Model, 'active') else records.write({'state': 'archived'})
                elif rule.action == 'anonymize':
                    # Generic anonymization: clear author/content if fields exist
                    for rec in records:
                        vals = {}
                        if hasattr(rec, 'author_id'):
                            vals['author_id'] = False
                        if hasattr(rec, 'content'):
                            vals['content'] = '[Anonymized by retention policy]'
                        if vals:
                            rec.write(vals)
            rule.write({
                'last_run': now,
                'processed_count': count,
            })
        return True

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class GovernanceProposal(models.Model):
    _name = 'social_governance.proposal'
    _description = 'Community Proposal'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    name = fields.Char('Title', required=True)
    description = fields.Html('Description', required=True)
    author_id = fields.Many2one(
        'res.users', required=True,
        default=lambda self: self.env.user, ondelete='restrict',
    )
    category_id = fields.Many2one(
        'social_governance.proposal_category', string='Category', required=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Open for Comments'),
        ('voting', 'Voting'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ], default='draft', required=True, tracking=True)

    voting_opens_at = fields.Datetime('Voting Opens')
    voting_closes_at = fields.Datetime('Voting Closes')
    implemented_at = fields.Datetime('Implemented At', readonly=True)

    vote_ids = fields.One2many('social_governance.vote', 'proposal_id', 'Votes')
    vote_count = fields.Integer(compute='_compute_vote_stats')
    yes_count = fields.Integer(compute='_compute_vote_stats')
    no_count = fields.Integer(compute='_compute_vote_stats')
    abstain_count = fields.Integer(compute='_compute_vote_stats')
    approval_pct = fields.Integer(compute='_compute_vote_stats', string='Approval %')

    my_vote = fields.Selection(
        [('yes', 'Yes'), ('no', 'No'), ('abstain', 'Abstain')],
        compute='_compute_my_vote', string='My Vote',
    )

    @api.depends('vote_ids.choice')
    def _compute_vote_stats(self):
        for prop in self:
            votes = prop.vote_ids
            yes = len(votes.filtered(lambda v: v.choice == 'yes'))
            no = len(votes.filtered(lambda v: v.choice == 'no'))
            abstain = len(votes.filtered(lambda v: v.choice == 'abstain'))
            total = yes + no + abstain
            prop.vote_count = total
            prop.yes_count = yes
            prop.no_count = no
            prop.abstain_count = abstain
            decisive = yes + no
            prop.approval_pct = round(100 * yes / decisive) if decisive else 0

    @api.depends('vote_ids.voter_id')
    def _compute_my_vote(self):
        for prop in self:
            vote = prop.vote_ids.filtered(lambda v: v.voter_id == self.env.user)
            prop.my_vote = vote[:1].choice if vote else False

    @api.constrains('voting_opens_at', 'voting_closes_at')
    def _check_voting_dates(self):
        for prop in self:
            if prop.voting_opens_at and prop.voting_closes_at:
                if prop.voting_closes_at <= prop.voting_opens_at:
                    raise ValidationError(_('Voting close date must be after open date.'))

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_open(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only drafts can be opened.'))
        self.write({'state': 'open'})

    def action_start_voting(self):
        self.ensure_one()
        if self.state not in ('draft', 'open'):
            raise UserError(_('Cannot start voting from current state.'))
        if not self.voting_closes_at:
            raise UserError(_('Please set a voting close date before starting the vote.'))
        self.write({'state': 'voting'})

    def action_close_voting(self):
        self.ensure_one()
        if self.state != 'voting':
            raise UserError(_('Only a voting proposal can be closed.'))
        result = 'accepted' if self.yes_count > self.no_count else 'rejected'
        self.write({'state': result})

    def action_implement(self):
        self.ensure_one()
        if self.state != 'accepted':
            raise UserError(_('Only accepted proposals can be marked implemented.'))
        self.write({'implemented_at': fields.Datetime.now()})

    def action_withdraw(self):
        self.ensure_one()
        if self.env.user != self.author_id \
                and not self.env.user.has_group('social_base.group_social_moderator'):
            raise UserError(_('Only the author or a moderator can withdraw a proposal.'))
        if self.state in ('accepted', 'rejected'):
            raise UserError(_('Cannot withdraw a closed proposal.'))
        self.write({'state': 'withdrawn'})

    def action_vote(self, choice):
        """Cast or change the current user's vote."""
        self.ensure_one()
        if self.state != 'voting':
            raise UserError(_('Voting is not open for this proposal.'))
        if choice not in ('yes', 'no', 'abstain'):
            raise ValidationError(_('Invalid choice.'))
        existing = self.vote_ids.filtered(lambda v: v.voter_id == self.env.user)
        if existing:
            existing.write({'choice': choice})
        else:
            self.env['social_governance.vote'].create({
                'proposal_id': self.id,
                'voter_id': self.env.user.id,
                'choice': choice,
            })

    @api.model
    def cron_close_expired_votes(self):
        now = fields.Datetime.now()
        expired = self.search([
            ('state', '=', 'voting'),
            ('voting_closes_at', '<=', now),
        ])
        for prop in expired:
            prop.action_close_voting()
        return len(expired)


class GovernanceVote(models.Model):
    _name = 'social_governance.vote'
    _description = 'Governance Vote'

    proposal_id = fields.Many2one(
        'social_governance.proposal', required=True, ondelete='cascade', index=True,
    )
    voter_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        ondelete='restrict', index=True,
    )
    choice = fields.Selection([
        ('yes', 'Yes'), ('no', 'No'), ('abstain', 'Abstain'),
    ], required=True)
    create_date = fields.Datetime(readonly=True)

    _sql_constraints = [
        ('unique_vote', 'UNIQUE(proposal_id, voter_id)', 'You have already voted on this proposal.'),
    ]


class GovernanceProposalCategory(models.Model):
    _name = 'social_governance.proposal_category'
    _description = 'Proposal Category'
    _order = 'sequence asc'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(default=0)

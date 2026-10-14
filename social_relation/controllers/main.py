"""Relations dans l'API mobile (/api/social/v1/relations). Contrat : README.md du module."""
import base64
import binascii

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.social_mobile.controllers.main import API, ROUTE, error, json_body, json_response

MAX_IMAGE_BYTES = 5 * 1024 * 1024


class SocialRelationApi(http.Controller):

    def _relation(self, relation_id):
        """Relation dont l'utilisateur courant est membre ou invité (sinon 404, sans dire si elle existe)."""
        relation = request.env['social_relation.relation'].sudo().browse(relation_id).exists()
        if not relation or not relation.member_ids.filtered(
                lambda m: m.user_id == request.env.user and m.state in ('accepted', 'invited')):
            return None
        return relation.sudo(False)

    def _run(self, fn):
        try:
            return fn()
        except AccessError:
            return error(404, 'not_found', "Relation introuvable.")
        except (UserError, ValidationError) as e:
            return error(409, 'refused', str(e))

    def _payload(self, relation):
        return json_response({'relation': relation._api_payload(request.env.user)})

    @http.route(f'{API}/relations', methods=['GET'], **ROUTE)
    def list_relations(self):
        """Mes relations (membre ou invité), y compris celles en formation."""
        Member = request.env['social_relation.member'].sudo()
        lines = Member.search([('user_id', '=', request.env.uid), ('state', 'in', ('accepted', 'invited'))])
        relations = lines.relation_id.filtered(lambda r: r.state != 'dissolved')
        return json_response({'relations': [r._api_payload(request.env.user) for r in relations]})

    @http.route(f'{API}/relations', methods=['POST'], **ROUTE)
    def create_relation(self):
        body = json_body()
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        return self._run(lambda: self._payload(
            request.env['social_relation.relation'].action_create_relation(body.get('name'), body.get('description'))))

    @http.route(f'{API}/relations/<int:relation_id>', methods=['GET'], **ROUTE)
    def get_relation(self, relation_id):
        """Une de mes relations, ou une relation visible d'un autre membre."""
        relation = request.env['social_relation.relation'].sudo().browse(relation_id).exists()
        if not relation or not relation._visible_to(request.env.user):
            return error(404, 'not_found', "Relation introuvable.")
        return self._payload(relation)

    @http.route(f'{API}/relations/<int:relation_id>', methods=['PATCH'], **ROUTE)
    def update_relation(self, relation_id):
        relation, body = self._relation(relation_id), json_body()
        if not relation:
            return error(404, 'not_found', "Relation introuvable.")
        if body is None:
            return error(400, 'invalid_json', "Corps JSON attendu.")
        vals = {k: body[k] for k in ('name', 'description') if k in body}
        if body.get('image_base64'):
            try:
                image = base64.b64decode(body['image_base64'], validate=True)
            except (binascii.Error, ValueError):
                return error(400, 'invalid_image', "Image illisible.")
            if len(image) > MAX_IMAGE_BYTES:
                return error(413, 'image_too_large', "Image trop lourde (5 Mo au plus).")
            vals['image_1920'] = base64.b64encode(image)

        def run():
            relation.action_update(vals)
            return self._payload(relation)
        return self._run(run)

    @http.route(f'{API}/relations/<int:relation_id>/image', methods=['GET'], **ROUTE)
    def relation_image(self, relation_id):
        relation = request.env['social_relation.relation'].sudo().browse(relation_id).exists()
        if not relation or not relation._visible_to(request.env.user) or not relation.image_512:
            return error(404, 'not_found', "Image introuvable.")
        return request.make_response(base64.b64decode(relation.image_512), headers=[
            ('Content-Type', 'image/png'), ('Cache-Control', 'private, max-age=300')])

    @http.route(f'{API}/relations/<int:relation_id>/invite', methods=['POST'], **ROUTE)
    def invite(self, relation_id):
        relation, body = self._relation(relation_id), json_body() or {}
        if not relation:
            return error(404, 'not_found', "Relation introuvable.")
        user = request.env['res.users'].sudo().browse(int(body.get('user_id') or 0)).exists()
        if not user or not user.active:
            return error(404, 'user_not_found', "Membre introuvable.")

        def run():
            relation.action_invite(user)
            return self._payload(relation)
        return self._run(run)

    def _member_action(self, relation_id, member_id, method):
        relation = self._relation(relation_id)
        if not relation:
            return error(404, 'not_found', "Relation introuvable.")
        member = request.env['social_relation.member'].sudo().browse(member_id).exists()
        if not member or member.relation_id != relation.sudo():
            return error(404, 'not_found', "Proposition introuvable.")

        def run():
            getattr(member.sudo(False), method)()
            return self._payload(relation)
        return self._run(run)

    @http.route(f'{API}/relations/<int:relation_id>/members/<int:member_id>/approve', methods=['POST'], **ROUTE)
    def approve(self, relation_id, member_id):
        return self._member_action(relation_id, member_id, 'action_approve')

    @http.route(f'{API}/relations/<int:relation_id>/members/<int:member_id>/reject', methods=['POST'], **ROUTE)
    def reject(self, relation_id, member_id):
        return self._member_action(relation_id, member_id, 'action_reject')

    def _self_action(self, relation_id, fn):
        relation = self._relation(relation_id)
        if not relation:
            return error(404, 'not_found', "Relation introuvable.")

        def run():
            fn(relation)
            return self._payload(relation)
        return self._run(run)

    @http.route(f'{API}/relations/<int:relation_id>/accept', methods=['POST'], **ROUTE)
    def accept(self, relation_id):
        return self._self_action(relation_id, lambda r: r.action_accept())

    @http.route(f'{API}/relations/<int:relation_id>/decline', methods=['POST'], **ROUTE)
    def decline(self, relation_id):
        return self._self_action(relation_id, lambda r: r.action_decline())

    @http.route(f'{API}/relations/<int:relation_id>/leave', methods=['POST'], **ROUTE)
    def leave(self, relation_id):
        return self._self_action(relation_id, lambda r: r.action_leave())

    @http.route(f'{API}/relations/<int:relation_id>/share', methods=['POST'], **ROUTE)
    def share(self, relation_id):
        body = json_body() or {}
        return self._self_action(relation_id, lambda r: r.action_set_share(body.get('share') is True))

    @http.route(f'{API}/users/<int:user_id>/relations', methods=['GET'], **ROUTE)
    def user_relations(self, user_id):
        """Relations visibles d'un membre : jamais ses relations discrètes."""
        if not request.env.user.has_group('social_base.group_social_user'):
            return error(403, 'not_member', "Réservé aux membres.")
        user = request.env['res.users'].sudo().browse(user_id).exists()
        if not user or request.env['social_safety.block'].is_blocked(request.env.user, user):
            return error(404, 'not_found', "Membre introuvable.")
        lines = request.env['social_relation.member'].sudo().search([('user_id', '=', user.id), ('state', '=', 'accepted')])
        relations = lines.relation_id.filtered(lambda r: r._visible_to(request.env.user))
        return json_response({'relations': [r._api_payload(request.env.user) for r in relations]})

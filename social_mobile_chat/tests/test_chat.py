import base64
import json

from odoo.tools.misc import file_open

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged

API = '/api/social/v1'


@tagged('post_install', '-at_install')
class TestMobileChat(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.a, cls.b, cls.c = (cls._make_member(f'{n}.chat@example.com') for n in 'abc')
        # A et B sont connectés : ils peuvent s'écrire. C n'a aucun lien avec A.
        Connection = cls.env['club_social_profile.connection'].sudo()
        Connection.create({'user_id': cls.a.id, 'connected_user_id': cls.b.id, 'state': 'accepted'})
        Connection.create({'user_id': cls.b.id, 'connected_user_id': cls.a.id, 'state': 'accepted'})

    @classmethod
    def _make_member(cls, login):
        user = new_test_user(cls.env, login=login, groups='base.group_portal')
        profile = cls.env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
        profile.stealth_name = login.split('.')[0].upper()
        cls.env['social_reputation.vouching'].with_user(cls.admin).sudo().vouch_for(user)
        membership = cls.env['club_membership.membership'].sudo().create({
            'partner_id': user.partner_id.id,
            'membership_type_id': cls.env.ref('club_membership.membership_type_regular').id,
        })
        membership.action_activate()
        return user

    def call(self, method, path, user, body=None):
        key, _exp = self.env['res.users.apikeys'].with_user(user)._social_mobile_generate('test')
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
        return self.url_open(API + path, data=json.dumps(body) if body is not None else None, headers=headers, method=method)

    def open_chat(self, user, other):
        return self.call('POST', '/chats', user, {'user_id': other.id})

    def test_private_conversation(self):
        res = self.open_chat(self.a, self.b)
        self.assertEqual(res.status_code, 200, res.text)
        chat = res.json()['chat']
        self.assertEqual(chat['kind'], 'chat')
        self.assertEqual(chat['title'], 'B', "pseudonyme, jamais le vrai nom")
        cid = chat['id']
        self.assertEqual(self.open_chat(self.b, self.a).json()['chat']['id'], cid, "même conversation dans les deux sens")

        sent = self.call('POST', f'/chats/{cid}/messages', self.a, {'body': "Salut <b>toi</b> !"})
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()['message']['body'], "Salut <b>toi</b> !", "texte rendu tel quel, jamais en HTML")
        self.assertTrue(sent.json()['message']['is_mine'])

        self.assertEqual(self.call('GET', '/chats/unread', self.b).json()['unread'], 1)
        listed = self.call('GET', '/chats', self.b).json()['chats']
        self.assertEqual(listed[0]['unread'], 1)
        self.assertEqual(listed[0]['last_message']['author_name'], 'A')
        messages = self.call('GET', f'/chats/{cid}/messages', self.b).json()['messages']
        self.assertEqual([m['body'] for m in messages], ["Salut <b>toi</b> !"])
        self.assertFalse(messages[0]['is_mine'])
        self.call('POST', f'/chats/{cid}/read', self.b, {'last_message_id': messages[-1]['id']})
        self.assertEqual(self.call('GET', '/chats/unread', self.b).json()['unread'], 0)

        # Relève des nouveaux messages et pagination vers le passé.
        for i in range(3):
            self.call('POST', f'/chats/{cid}/messages', self.b, {'body': f"m{i}"})
        newer = self.call('GET', f"/chats/{cid}/messages?after={messages[-1]['id']}", self.a).json()['messages']
        self.assertEqual([m['body'] for m in newer], ['m0', 'm1', 'm2'])
        older = self.call('GET', f"/chats/{cid}/messages?before={newer[1]['id']}&limit=1", self.a).json()['messages']
        self.assertEqual([m['body'] for m in older], ['m0'])

    def test_contact_policy_and_outsiders(self):
        self.assertEqual(self.open_chat(self.a, self.c).status_code, 403, "aucun lien : pas de nouvelle conversation")
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        # C n'est pas membre de la conversation de A et B.
        self.assertEqual(self.call('GET', f'/chats/{cid}/messages', self.c).status_code, 404)
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.c, {'body': 'intrus'}).status_code, 404)
        self.assertEqual(self.call('GET', '/chats', self.c).json()['chats'], [])

    def test_block_stops_messages(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        self.env['social_safety.block'].sudo().create({'blocker_id': self.b.id, 'blocked_id': self.a.id})
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.a, {'body': 'encore'}).status_code, 403)
        self.assertEqual(self.open_chat(self.a, self.b).status_code, 403)

    def test_relation_conversation(self):
        Relation = self.env['social_relation.relation']
        relation = Relation.with_user(self.a).action_create_relation("A, B et C")
        relation.with_user(self.a).action_invite(self.c)
        relation.with_user(self.c).action_accept()
        chats = self.call('GET', '/chats', self.c).json()['chats']
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]['kind'], 'relation')
        self.assertEqual(chats[0]['relation_id'], relation.id)
        self.assertEqual(chats[0]['title'], "A, B et C")
        cid = chats[0]['id']
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.c, {'body': 'Bonjour à vous'}).status_code, 200)
        self.assertEqual(self.call('GET', '/chats/unread', self.a).json()['unread'], 1)
        # Quitter la relation retire de sa conversation.
        relation.with_user(self.c).action_leave()
        self.assertEqual(self.call('GET', f'/chats/{cid}/messages', self.c).status_code, 404)

    def _discuss_channel(self, channel_type, members, name=''):
        return self.env['discuss.channel'].sudo().create({
            'name': name, 'channel_type': channel_type,
            'channel_member_ids': [Command.create({'partner_id': u.partner_id.id}) for u in members],
        })

    def test_group_conversation_and_channel(self):
        # Groupe créé dans Discuss (sans relation) : listé, titré par les pseudonymes, ouvert à l'écriture.
        group = self._discuss_channel('group', self.a | self.b | self.c)
        chats = self.call('GET', '/chats', self.c).json()['chats']
        self.assertEqual([(c['id'], c['kind']) for c in chats], [(group.id, 'group')])
        self.assertEqual(chats[0]['title'], "A, B", "pseudonymes des autres membres, jamais les vrais noms")
        sent = self.call('POST', f'/chats/{group.id}/messages', self.c, {'body': 'Bonjour le groupe'})
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(self.call('GET', '/chats/unread', self.a).json()['unread'], 1)
        group.name = "Les trois"
        self.assertEqual(self.call('GET', '/chats', self.a).json()['chats'][0]['title'], "Les trois")

        # Canal Discuss : listé pour ses membres seulement.
        channel = self._discuss_channel('channel', self.a | self.b, name="Bénévoles")
        self.assertIn(channel.id, [c['id'] for c in self.call('GET', '/chats', self.a).json()['chats']])
        self.assertNotIn(channel.id, [c['id'] for c in self.call('GET', '/chats', self.c).json()['chats']])
        self.assertEqual(self.call('GET', f'/chats/{channel.id}/messages', self.c).status_code, 404)
        messages = self.call('GET', f'/chats/{channel.id}/messages', self.b)
        self.assertEqual(messages.status_code, 200, messages.text)

    def test_validation(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.a, {'body': '   '}).status_code, 403)
        self.assertEqual(self.call('POST', f'/chats/{cid}/messages', self.a, {'body': 'x' * 4001}).status_code, 403)
        self.assertEqual(self.call('POST', '/chats', self.a, {'user_id': self.a.id}).status_code, 403)
        outsider = new_test_user(self.env, login='hors.chat@example.com', groups='base.group_portal')
        self.assertEqual(self.call('GET', '/chats', outsider).status_code, 403)

    # ── Messages vocaux ──────────────────────────────────────────────────────

    def voice_data(self):
        with file_open('social_mobile_chat/tests/data/voice.m4a', 'rb') as f:
            return f.read()

    def send_voice(self, cid, user, data):
        return self.call('POST', f'/chats/{cid}/voice', user, {'data': base64.b64encode(data).decode()})

    def test_voice_message(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        data = self.voice_data()
        res = self.send_voice(cid, self.a, data)
        self.assertEqual(res.status_code, 200, res.text)
        voice = res.json()['message']['voice']
        self.assertEqual(voice['mimetype'], 'audio/mp4')
        # Comme un message vocal de Discuss : pièce jointe marquée vocale, dans la conversation.
        attachment = self.env['ir.attachment'].sudo().browse(voice['attachment_id'])
        self.assertTrue(attachment.voice_ids)
        self.assertEqual((attachment.res_model, attachment.res_id), ('discuss.channel', cid))
        # B le voit et le télécharge ; la notification est en file.
        message = self.call('GET', f'/chats/{cid}/messages', self.b).json()['messages'][-1]
        self.assertEqual((message['voice']['attachment_id'], message['attachment_count']), (attachment.id, 0))
        self.assertEqual(self.call('GET', '/chats', self.b).json()['chats'][0]['last_message']['voice']['attachment_id'],
                         attachment.id)
        got = self.call('GET', f"/chats/{cid}/attachments/{attachment.id}", self.b)
        self.assertEqual((got.status_code, got.headers['Content-Type'], got.content), (200, 'audio/mp4', data))
        if 'social_mobile.push_queue' in self.env:
            self.assertTrue(self.env['social_mobile.push_queue'].sudo().search([('user_id', '=', self.b.id)]))

    def test_voice_access(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        att_id = self.send_voice(cid, self.a, self.voice_data()).json()['message']['voice']['attachment_id']
        # Hors de la conversation : 404, sans dire si elle existe.
        self.assertEqual(self.call('GET', f'/chats/{cid}/attachments/{att_id}', self.c).status_code, 404)
        self.assertEqual(self.send_voice(cid, self.c, self.voice_data()).status_code, 404)
        # Pièce jointe d'une autre conversation, demandée par la sienne : 404.
        other = self.env['discuss.channel'].sudo().create({'name': 'ailleurs', 'channel_type': 'channel'})
        foreign = self.env['ir.attachment'].sudo().create({'name': 'x.m4a', 'raw': b'secret',
                                                           'res_model': 'discuss.channel', 'res_id': other.id})
        self.assertEqual(self.call('GET', f'/chats/{cid}/attachments/{foreign.id}', self.b).status_code, 404)
        self.assertEqual(self.call('GET', f'/chats/{cid}/attachments/999999', self.b).status_code, 404)
        # Bloqué : refusé, comme un message texte.
        self.env['social_safety.block'].sudo().create({'blocker_id': self.b.id, 'blocked_id': self.a.id})
        self.assertEqual(self.send_voice(cid, self.a, self.voice_data()).status_code, 403)

    def test_voice_validation(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        self.assertEqual(self.send_voice(cid, self.a, b'pas du tout un fichier audio').status_code, 403)
        self.assertEqual(self.send_voice(cid, self.a, b'\0\0\0\x1cftyp' + b'\0' * (3 * 1024 * 1024)).status_code, 403)
        self.assertEqual(self.call('POST', f'/chats/{cid}/voice', self.a, {'data': '%%%'}).status_code, 400)
        self.assertEqual(self.call('POST', f'/chats/{cid}/voice', self.a, {}).status_code, 400)

    # ── Photos et fichiers ──────────────────────────────────────────────────

    def _photo_with_gps(self):
        """JPEG 300 × 200 couché (orientation EXIF 6) avec une position GPS : ce que donne un téléphone."""
        import io
        from PIL import Image
        image = Image.new('RGB', (300, 200), (200, 30, 60))
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation : à tourner de 90°
        exif[0x8825] = {1: 'N', 2: (45.0, 30.0, 0.0), 3: 'W', 4: (73.0, 34.0, 0.0)}  # GPSInfo
        out = io.BytesIO()
        image.save(out, 'JPEG', exif=exif)
        return out.getvalue()

    def test_photo_is_sent_upright_and_without_location(self):
        import io
        from PIL import Image
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        data = self._photo_with_gps()
        self.assertIn(b'Exif', data[:200])
        res = self.call('POST', f'/chats/{cid}/attachments', self.a,
                        {'data': base64.b64encode(data).decode(), 'name': 'IMG_0001.jpg', 'body': "Regarde !"})
        self.assertEqual(res.status_code, 200, res.text)
        message = res.json()['message']
        self.assertEqual(message['body'], "Regarde !")
        [attachment] = message['attachments']
        self.assertEqual((attachment['name'], attachment['mimetype'], attachment['is_image']), ('IMG_0001.jpg', 'image/jpeg', True))
        self.assertEqual(message['attachment_count'], 1, "ancien champ, pour les versions installées")

        stored = self.call('GET', f"/chats/{cid}/attachments/{attachment['id']}", self.b)
        self.assertEqual(stored.status_code, 200)
        with Image.open(io.BytesIO(stored.content)) as image:
            self.assertEqual(image.size, (200, 300), "redressée d'après l'orientation EXIF")
            exif = image.getexif()
            self.assertNotIn(0x8825, exif, "aucune position GPS")
            self.assertNotIn(0x0112, exif)

        thumb = self.call('GET', f"/chats/{cid}/attachments/{attachment['id']}?thumb=1", self.b)
        self.assertEqual(thumb.headers['Content-Type'], 'image/jpeg')
        with Image.open(io.BytesIO(thumb.content)) as image:
            self.assertLessEqual(max(image.size), 512)

        listed = self.call('GET', f'/chats/{cid}/messages', self.b).json()['messages'][-1]
        self.assertEqual(listed['attachments'][0]['id'], attachment['id'])

    def test_file_is_sent_as_is(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        pdf = b'%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n'
        res = self.call('POST', f'/chats/{cid}/attachments', self.a, {'data': base64.b64encode(pdf).decode(), 'name': 'menu.pdf'})
        self.assertEqual(res.status_code, 200, res.text)
        [attachment] = res.json()['message']['attachments']
        self.assertEqual((attachment['mimetype'], attachment['is_image'], attachment['size']), ('application/pdf', False, len(pdf)))
        got = self.call('GET', f"/chats/{cid}/attachments/{attachment['id']}?thumb=1", self.b)
        self.assertEqual(got.content, pdf, "pas de miniature pour un fichier : l'original")

    def test_dangerous_and_invalid_files_are_refused(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        html = b'<!DOCTYPE html><html><body><script>alert(1)</script></body></html>'
        for data, name in ((svg, 'joli.svg'), (svg, 'joli.png'), (html, 'page.txt'), (b'texte', 'page.html')):
            res = self.call('POST', f'/chats/{cid}/attachments', self.a, {'data': base64.b64encode(data).decode(), 'name': name})
            self.assertEqual(res.status_code, 403, f"{name} accepté")
        self.assertEqual(self.call('POST', f'/chats/{cid}/attachments', self.a, {'data': 'pas du base64 !'}).status_code, 400)
        self.assertEqual(self.call('POST', f'/chats/{cid}/attachments', self.a, {'data': ''}).status_code, 403)
        big = base64.b64encode(b'0' * (15 * 1024 * 1024 + 1)).decode()
        self.assertEqual(self.call('POST', f'/chats/{cid}/attachments', self.a, {'data': big, 'name': 'gros.bin'}).status_code, 403)
        broken = b'\xff\xd8\xff\xe0' + b'\x00' * 64  # en-tête JPEG, image illisible
        self.assertEqual(self.call('POST', f'/chats/{cid}/attachments', self.a,
                                   {'data': base64.b64encode(broken).decode(), 'name': 'x.jpg'}).status_code, 403)
        self.assertFalse(self.call('GET', f'/chats/{cid}/messages', self.b).json()['messages'])

    def test_attachments_stay_in_their_conversation(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        res = self.call('POST', f'/chats/{cid}/attachments', self.a,
                        {'data': base64.b64encode(self._photo_with_gps()).decode(), 'name': 'p.jpg'})
        attachment_id = res.json()['message']['attachments'][0]['id']
        self.assertEqual(self.call('GET', f'/chats/{cid}/attachments/{attachment_id}', self.c).status_code, 404, "pas membre")
        self.assertEqual(self.call('POST', f'/chats/{cid}/attachments', self.c,
                                   {'data': base64.b64encode(b'%PDF-1.4').decode(), 'name': 'x.pdf'}).status_code, 404)
        # Une autre conversation de B ne donne pas accès à cette pièce jointe.
        Connection = self.env['club_social_profile.connection'].sudo()
        Connection.create({'user_id': self.b.id, 'connected_user_id': self.c.id, 'state': 'accepted'})
        Connection.create({'user_id': self.c.id, 'connected_user_id': self.b.id, 'state': 'accepted'})
        other = self.open_chat(self.b, self.c).json()['chat']['id']
        self.assertEqual(self.call('GET', f'/chats/{other}/attachments/{attachment_id}', self.b).status_code, 404)

    def test_image_sent_from_the_website_is_listed(self):
        cid = self.open_chat(self.a, self.b).json()['chat']['id']
        channel = self.env['discuss.channel'].browse(cid)
        # Comme Discuss sur le site : la pièce jointe est créée par son auteur, puis jointe au message.
        attachment = self.env['ir.attachment'].with_user(self.b).sudo().create({
            'name': 'site.png', 'raw': base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='),
            'res_model': 'discuss.channel', 'res_id': cid,
        })
        # Le site joint l'image par ses jetons d'accès ; ici, directement au message publié.
        message = channel.with_user(self.b).sudo().message_post(
            body='', message_type='comment', subtype_xmlid='mail.mt_comment')
        message.sudo().attachment_ids = [(4, attachment.id)]
        listed = self.call('GET', f'/chats/{cid}/messages', self.a).json()['messages'][-1]
        self.assertEqual([(a['name'], a['is_image']) for a in listed['attachments']], [('site.png', True)])
        self.assertIsNone(listed['voice'])

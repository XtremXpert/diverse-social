{
    'name': 'Social ntfy Push',
    'version': '20.0.1.0.2',
    'category': 'Social',
    'summary': 'Native iPhone/Android push via a self-hosted ntfy server (generic-payload, per-user topic)',
    'description': """
        Reliable mobile push for the social network through ntfy
        (https://ntfy.sh). Each member gets a secret per-user topic; when an
        in-app notification is created, Odoo POSTs a GENERIC payload (constant
        title + body, no actor name, no preview) to that topic on the
        self-hosted ntfy server, which the member's ntfy app receives as a
        native push.

        Mirrors the social_pwa decoupled architecture (outbox + cron + create
        hook) but uses an HTTP POST to ntfy instead of Web-Push/VAPID. The two
        channels are independent and can run side by side.

        Server side (out of scope of this module): a ntfy server reachable at
        social_ntfy.server_url, with a publish token in social_ntfy.publish_token.
    """,
    'author': 'Bemade',
    'license': 'LGPL-3',
    'depends': [
        'portal',
        'club_social_profile',
    ],
    'data': [
        'security/ir.access.csv',
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'views/portal_ntfy.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

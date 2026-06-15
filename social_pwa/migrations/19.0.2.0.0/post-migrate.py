"""Nettoyage : le modèle social_pwa.subscription n'existe plus."""


def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS social_pwa_subscription")

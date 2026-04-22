"""
Migration 19.0.2.0.0 — website_blog_restricted

author_name est un champ store=True figé à la création du post.
On recompute pour les posts dont l'auteur est un utilisateur portail,
afin qu'ils affichent le login plutôt que le nom du partenaire.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE blog_post bp
        SET author_name = ru.login
        FROM res_partner rp
        JOIN res_users ru ON ru.partner_id = rp.id
        WHERE bp.author_id = rp.id
          AND ru.share = true
          AND ru.active = true
          AND NOT EXISTS (
              SELECT 1 FROM res_users ru2
              WHERE ru2.partner_id = rp.id
                AND ru2.share = false
                AND ru2.active = true
          )
    """)

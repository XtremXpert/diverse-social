def migrate(cr, version):
    cr.execute("""
        UPDATE social_gallery_gallery
           SET visibility = 'connections'
         WHERE visibility = 'private'
    """)

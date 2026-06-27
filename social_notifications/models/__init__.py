from . import notification_ext
from . import circles_hooks
from . import event_hooks
from . import gallery_hooks
from . import governance_hooks
from . import group_hooks
# messaging_hooks defines a model that _inherit social_messaging.message —
# registry resolution fails when social_messaging isn't installed. social_messaging
# a été retiré au profit de Discuss (social_messaging_discuss), donc le module est
# désinstallé. Fichier conservé pour réactivation via un bridge si besoin.
# from . import messaging_hooks
# negotiation_hooks defines a model that _inherit social_negotiation.negotiation
# — registry resolution fails when social_negotiation isn't installed. Move to
# a bridge module (social_notifications_negotiation, auto_install) before
# importing again. File kept in place for future re-activation.
from . import reputation_hooks
from . import story_hooks
from . import res_users_ext
from . import digest_service

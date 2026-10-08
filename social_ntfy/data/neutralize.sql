-- Copie neutralisée (staging) : aucune notification ne part vers le serveur
-- ntfy réel, donc vers les appareils des membres.
DELETE FROM ir_config_parameter
 WHERE key IN ('social_ntfy.server_url', 'social_ntfy.publish_url', 'social_ntfy.publish_token');

-- Copie de la base (staging, restauration) : aucune notification ne doit partir vers les iPhone
-- des vrais membres. On efface la clé APNs et on désactive les appareils.
DELETE FROM ir_config_parameter WHERE key = 'social_mobile_push.apns_key';
UPDATE social_mobile_device SET active = false;
DELETE FROM social_mobile_push_queue;

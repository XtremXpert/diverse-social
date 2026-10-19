-- Copie de la base (staging, restauration) : aucune notification ne doit partir vers les téléphones
-- des vrais membres. On efface la clé APNs et le compte Firebase, et on désactive les appareils.
DELETE FROM ir_config_parameter WHERE key IN ('social_mobile_push.apns_key', 'social_mobile_push.fcm_service_account');
UPDATE social_mobile_device SET active = false;
DELETE FROM social_mobile_push_queue;

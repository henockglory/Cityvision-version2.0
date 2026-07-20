UPDATE org_demo_settings
SET source_mode='camera',
    active_camera_id='f691ef55-6791-495b-a35e-be215e7ac109',
    active_video_id=NULL,
    updated_at=NOW()
WHERE org_id='74d51ead-97a7-4e41-a488-503a9b90c466';
SELECT source_mode, active_camera_id FROM org_demo_settings;

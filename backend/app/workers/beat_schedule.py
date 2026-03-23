"""Celery Beat schedule configuration."""

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "fetch-highergov-rfps": {
        "task": "app.workers.tasks.fetch_highergov_rfps_task",
        "schedule": crontab(hour="6", minute="0"),  # 6 AM UTC daily
    },
    "sync-hubspot-outcomes": {
        "task": "app.workers.tasks.sync_hubspot_outcomes_task",
        "schedule": crontab(hour="*/6"),
    },
    "run-coda-etl": {
        "task": "app.workers.tasks.run_coda_etl_task",
        "schedule": crontab(hour="2", minute="0"),
    },
    "run-hubspot-etl": {
        "task": "app.workers.tasks.run_hubspot_etl_task",
        "schedule": crontab(hour="2", minute="15"),
    },
    "run-slack-etl": {
        "task": "app.workers.tasks.run_slack_etl_task",
        "schedule": crontab(hour="2", minute="30"),
    },
    "embed-winning-proposals": {
        "task": "app.workers.tasks.embed_winning_proposals_task",
        "schedule": crontab(hour="3", minute="0"),
    },
}

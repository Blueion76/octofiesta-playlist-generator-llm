### Scheduling

- **SCHEDULE_CRON**: 
  - Description: Specifies the cron schedule for automated execution.
- **TZ**: 
  - Description: Time zone for the scheduled runs.
- **MIN_RUN_INTERVAL_HOURS**: 
  - Description: Used for manual mode (when SCHEDULE_CRON is not set or set to "manual"). Defaults to 6 hours and prevents duplicate runs from container restarts.
